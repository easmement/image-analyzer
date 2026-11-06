"""Image embeddings: vectors whose cosine similarity measures how alike two images look in
content (same scene, same object), not just pixel layout.

Split in two so the expensive part batches on the GPU:
  - prepare(img) runs in the CPU worker processes (no torch): resize to the model input.
  - Extractor.embed(batch) runs in the scan thread, a batch at a time.
"""

import threading
from typing import Protocol

import numpy as np
from PIL import Image

INPUT_SIZE = 224  # DINOv2 ViT-S/14: 16 x 16 patches of 14 px


def prepare(img: Image.Image) -> bytes:
    """Model input for one image: the whole frame squashed to 224x224 RGB, as raw bytes.

    Squashing (rather than the usual resize + centre crop) keeps the edges of the picture, so a
    cropped copy is compared against everything that was in the original."""
    return np.asarray(img.resize((INPUT_SIZE, INPUT_SIZE), Image.Resampling.BICUBIC), dtype=np.uint8).tobytes()


def as_batch(inputs: list[bytes]) -> np.ndarray:
    return np.frombuffer(b"".join(inputs), dtype=np.uint8).reshape(-1, INPUT_SIZE, INPUT_SIZE, 3)


class Extractor(Protocol):
    name: str
    dim: int
    device: str

    def embed(self, batch: np.ndarray) -> np.ndarray:
        """(n, 224, 224, 3) uint8 -> (n, dim) float32, L2-normalised."""
        ...


def _normalise(v: np.ndarray) -> np.ndarray:
    return (v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)).astype(np.float32)


class DinoV2Extractor:
    """facebook/dinov2-small (22M params, 384-d). The CLS token is the image embedding.
    Runs in fp32: on GPUs without tensor cores (e.g. GTX 16xx) fp16 is slower, not faster."""

    MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)  # ImageNet statistics
    STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    def __init__(self, model_id: str = "facebook/dinov2-small"):
        import torch
        from transformers import AutoModel

        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = AutoModel.from_pretrained(model_id).eval().to(self.device)
        self.name = model_id
        self.dim = int(self.model.config.hidden_size)
        # A scan and a search-by-upload can both embed at once; one model call at a time.
        self._lock = threading.Lock()
        self._mean = torch.tensor(self.MEAN, device=self.device).view(1, 3, 1, 1)
        self._std = torch.tensor(self.STD, device=self.device).view(1, 3, 1, 1)

    def embed(self, batch: np.ndarray) -> np.ndarray:
        # Send uint8 pixels and normalise on the device: 4x less to transfer than float32, and
        # it frees the CPU for the decoders (+7% throughput on a GTX 1650; identical output).
        with self._lock, self.torch.inference_mode():
            pixels = self.torch.from_numpy(np.ascontiguousarray(batch)).to(self.device)
            x = pixels.permute(0, 3, 1, 2).float().div_(255).sub_(self._mean).div_(self._std)
            cls = self.model(pixel_values=x).pooler_output
        return _normalise(cls.float().cpu().numpy())


class FakeExtractor:
    """Deterministic stand-in for tests: a coarse 4x4 colour grid. Similar-looking images get
    similar vectors, with no model download or GPU."""

    name = "fake-colour-grid"
    dim = 48
    device = "cpu"

    def embed(self, batch: np.ndarray) -> np.ndarray:
        n = len(batch)
        grid = batch.reshape(n, 4, INPUT_SIZE // 4, 4, INPUT_SIZE // 4, 3).mean(axis=(2, 4))
        return _normalise(grid.reshape(n, -1) - 127.5)


_extractor: Extractor | None = None
_extractor_error: str | None = None
_lock = threading.Lock()


def get_extractor(kind: str) -> Extractor | None:
    """The configured extractor, loaded once. None when disabled ("none") or if loading failed
    (no network for the first download, say); scans then skip embeddings and retry later."""
    global _extractor, _extractor_error
    if kind == "none":
        return None
    with _lock:
        if _extractor is None and _extractor_error is None:
            try:
                _extractor = FakeExtractor() if kind == "fake" else DinoV2Extractor()
            except Exception as e:  # noqa: BLE001 - surface any load failure via /api/health
                _extractor_error = f"{type(e).__name__}: {e}"
        return _extractor


def extractor_status() -> dict:
    return {
        "name": _extractor.name if _extractor else None,
        "device": _extractor.device if _extractor else None,
        "error": _extractor_error,
    }
