"""Pixel-level comparison of two images: where exactly do they differ?

Both images are aligned first (B is rotated/mirrored to match A if that clearly fits better,
then resized to A's frame), then compared with SSIM (structural similarity), which scores local
structure rather than raw pixel values, so recompression noise barely registers while an added
watermark or a changed face does. The per-pixel SSIM map becomes a red heatmap overlay.
"""

import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import cast

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity

from image_analyzer.pipeline.decode import open_rgb
from image_analyzer.pipeline.hashing import ORIENTATIONS

MAX_SIDE = 1024  # comparison resolution; plenty to see where images differ, and fast
CHANGED_BELOW = 0.75  # local SSIM under this counts as a visibly changed pixel
ORIENTATION_MARGIN = 0.8  # another orientation must cut the error by 20% to beat "as is"


@dataclass(frozen=True)
class Comparison:
    width: int
    height: int
    orientation: int  # transform applied to B (index into hashing.ORIENTATIONS)
    ssim: float  # mean SSIM, -1..1; 1 = identical structure
    changed_fraction: float  # share of the frame where local SSIM < CHANGED_BELOW
    image_a: bytes  # aligned JPEGs, same size, for the side-by-side and swipe views
    image_b: bytes
    heatmap: bytes  # transparent PNG: red where the images differ


def _gray(img: Image.Image, size: tuple[int, int]) -> np.ndarray:
    return np.asarray(img.convert("L").resize(size, Image.Resampling.BILINEAR), dtype=np.float32) / 255.0


def best_orientation_of(a: Image.Image, b: Image.Image) -> int:
    """The orientation of b that best matches a, judged on 64x64 thumbnails."""
    target = _gray(a, (64, 64))
    errors = []
    for op, _ in ORIENTATIONS:
        candidate = b if op is None else b.transpose(op)
        errors.append(float(np.mean((_gray(candidate, (64, 64)) - target) ** 2)))
    best = int(np.argmin(errors))
    return best if errors[best] < errors[0] * ORIENTATION_MARGIN else 0


def compare(a: Image.Image, b: Image.Image, try_orientations: bool = True) -> Comparison:
    """try_orientations=False keeps B as is: for pairs the hashes didn't match rotated, every
    orientation fits badly and the "best" one would be noise."""
    scale = min(1.0, MAX_SIDE / max(a.size))
    size = (max(1, round(a.width * scale)), max(1, round(a.height * scale)))
    orientation = best_orientation_of(a, b) if try_orientations else 0
    op = ORIENTATIONS[orientation][0]
    a_aligned = a.resize(size, Image.Resampling.LANCZOS)
    b_aligned = (b if op is None else b.transpose(op)).resize(size, Image.Resampling.LANCZOS)

    # Gaussian-weighted SSIM as in the original paper (sigma 1.5); full=True gives the local map.
    # scikit-image's return type covers every flag combination; with full=True it's (score, map).
    score, ssim_map = cast(tuple[float, np.ndarray], structural_similarity(
        _gray(a_aligned, size), _gray(b_aligned, size), data_range=1.0, full=True,
        gaussian_weights=True, sigma=1.5, use_sample_covariance=False,
    ))
    # Heatmap: transparent where structure matches, increasingly opaque red where it doesn't.
    dissimilarity = np.clip((1.0 - ssim_map) / (1.0 - CHANGED_BELOW + 1e-6) * 0.5, 0, 1)
    rgba = np.zeros((*ssim_map.shape, 4), dtype=np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = 255, 40, 40
    rgba[..., 3] = (dissimilarity * 220).astype(np.uint8)

    return Comparison(
        width=size[0], height=size[1], orientation=orientation,
        ssim=round(float(score), 4),
        changed_fraction=round(float(np.mean(ssim_map < CHANGED_BELOW)), 4),
        image_a=_encode(a_aligned, "JPEG"), image_b=_encode(b_aligned, "JPEG"),
        heatmap=_encode(Image.fromarray(rgba, "RGBA"), "PNG"),
    )


def _encode(img: Image.Image, fmt: str) -> bytes:
    buf = io.BytesIO()
    img.save(buf, fmt, **({"quality": 90} if fmt == "JPEG" else {"optimize": False}))
    return buf.getvalue()


@lru_cache(maxsize=16)
def compare_files(path_a: Path, sha_a: str, path_b: Path, sha_b: str,
                  try_orientations: bool = True) -> Comparison:
    """Cached by path and content hash: the compare page fetches the scores and then three
    images for the same pair, and a changed file gets a new sha, so the cache can't go stale."""
    img_a, _ = open_rgb(path_a)
    img_b, _ = open_rgb(path_b)
    return compare(img_a, img_b, try_orientations)
