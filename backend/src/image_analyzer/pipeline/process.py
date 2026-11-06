"""Per-file feature extraction. Runs in worker processes, so it must stay importable without
torch and must not touch the database."""

import hashlib
import os
from pathlib import Path

from PIL import Image

from image_analyzer.pipeline.decode import DecodeError, open_for_features
from image_analyzer.pipeline.embeddings import prepare
from image_analyzer.pipeline.hashing import perceptual_hashes

# Bump when the pipeline starts producing new features; scans reprocess rows below the target.
# 1: sha256, size, thumbnail. 2: + perceptual hashes. 3: + embedding.
# 5 / 6: hashes only / hashes + embedding, computed from a reduced-size decode
#    (open_for_features): same features, slightly different values, so all older rows are
#    recomputed to keep scores comparable. HASHES_VERSION < FEATURES_VERSION, so hashes-only
#    rows still get embedded once a model is available.
HASHES_VERSION = 5
FEATURES_VERSION = 6


def thumb_path(thumbs_dir: Path, sha256: str) -> Path:
    return thumbs_dir / sha256[:2] / f"{sha256}.webp"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def process_file(path: Path, thumbs_dir: Path, thumb_size: int, embed: bool = False) -> dict:
    """Hash, measure and thumbnail one image, and (if embed) prepare its model input, all from
    one decode. Never raises: failures come back as status=error."""
    try:
        sha = sha256_file(path)
    except OSError as e:
        return {"status": "error", "error": f"{type(e).__name__}: {e}"}
    try:
        img, fmt, (width, height) = open_for_features(path)
    except DecodeError as e:
        return {"status": "error", "error": str(e), "sha256": sha}

    # Hash before thumbnailing: img.thumbnail() shrinks the image in place.
    phash8, dhash8 = perceptual_hashes(img)
    result = {"status": "ok", "sha256": sha, "width": width, "height": height, "format": fmt,
              "phash8": phash8, "dhash8": dhash8}
    if embed:  # the scan thread batches these through the model on the GPU
        result["embed_input"] = prepare(img)
    thumb = thumb_path(thumbs_dir, sha)
    if not thumb.exists():  # shared by exact duplicates, and kept when a file moves
        thumb.parent.mkdir(parents=True, exist_ok=True)
        img.thumbnail((thumb_size, thumb_size), Image.Resampling.LANCZOS)
        # Per-process temp name: two workers may thumbnail identical files at the same time.
        tmp = thumb.with_suffix(f".{os.getpid()}.tmp")
        img.save(tmp, "WEBP", quality=80)
        tmp.replace(thumb)  # atomic, so a half-written file is never served
    return result
