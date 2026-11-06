"""Perceptual hashes for every orientation of an image.

pHash (DCT) and dHash (gradient) are 64-bit fingerprints that survive resizing, recompression
and mild edits; Hamming distance between them measures how different two images look. Neither
survives rotation or mirroring, so we hash all 8 orientations (4 rotations x mirror) and store
them: index 0 is the image as displayed, the rest let a lookup match rotated/mirrored copies.

Both hash functions shrink to grayscale 32x32 (phash) or 9x8 (dhash) first, so we shrink once
and rotate the tiny image. Rotations and flips only permute pixels, so this gives the same
result as rotating the full image, far more cheaply.
"""

import imagehash
import numpy as np
from PIL import Image

HASH_BYTES = 8  # 64-bit hashes
N_ORIENTATIONS = 8

# Dihedral group of the square: index -> (PIL transpose op or None, label for the UI).
ORIENTATIONS: list[tuple[Image.Transpose | None, str]] = [
    (None, "as is"),
    (Image.Transpose.ROTATE_90, "rotated 90°"),
    (Image.Transpose.ROTATE_180, "rotated 180°"),
    (Image.Transpose.ROTATE_270, "rotated 270°"),
    (Image.Transpose.FLIP_LEFT_RIGHT, "mirrored"),
    (Image.Transpose.TRANSPOSE, "mirrored + rotated 90°"),
    (Image.Transpose.FLIP_TOP_BOTTOM, "mirrored + rotated 180°"),
    (Image.Transpose.TRANSVERSE, "mirrored + rotated 270°"),
]


def _pack(h: imagehash.ImageHash) -> bytes:
    return np.packbits(h.hash.flatten()).tobytes()


def perceptual_hashes(img: Image.Image) -> tuple[bytes, bytes]:
    """Return (phash8, dhash8): 8 orientations x 8 bytes each, orientation 0 first."""
    small = img.convert("L").resize((32, 32), Image.Resampling.LANCZOS)
    phashes, dhashes = [], []
    for op, _ in ORIENTATIONS:
        oriented = small if op is None else small.transpose(op)
        phashes.append(_pack(imagehash.phash(oriented)))
        dhashes.append(_pack(imagehash.dhash(oriented)))
    return b"".join(phashes), b"".join(dhashes)


def as_codes(blobs: list[bytes]) -> np.ndarray:
    """Stack hash blobs into a (n_images, N_ORIENTATIONS, HASH_BYTES) uint8 array."""
    return np.frombuffer(b"".join(blobs), dtype=np.uint8).reshape(-1, N_ORIENTATIONS, HASH_BYTES)


def hamming(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Bitwise Hamming distance between packed codes along the last axis (broadcasts)."""
    return np.bitwise_count(np.bitwise_xor(a, b)).sum(axis=-1, dtype=np.int64)
