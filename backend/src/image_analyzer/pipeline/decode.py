"""Open images safely and normalise them, so every feature sees the same upright RGB pixels."""

import warnings
from pathlib import Path
from typing import IO

from PIL import Image, ImageOps

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}

try:  # optional HEIC/HEIF support
    from pillow_heif import register_heif_opener  # pyright: ignore[reportMissingImports]

    register_heif_opener()
    SUPPORTED_EXTS |= {".heic", ".heif"}
except ImportError:
    pass


class DecodeError(Exception):
    pass


# Smallest side the feature pipeline decodes to. Every feature is small (hashes from 32 px, the
# model input at 224 px, thumbnails at 256 px), so full-resolution pixels are never needed.
FEATURE_SIDE = 512
EXIF_ORIENTATION = 0x0112
SWAPS_AXES = {5, 6, 7, 8}  # EXIF orientations that rotate by 90 degrees


def open_rgb(source: Path | IO[bytes]) -> tuple[Image.Image, str]:
    """Return (upright RGB image, format name) at full resolution, from a path or an in-memory
    file. Raises DecodeError for unreadable images."""
    img, fmt, _ = _open(source, min_side=None)
    return img, fmt


def open_for_features(source: Path | IO[bytes]) -> tuple[Image.Image, str, tuple[int, int]]:
    """Like open_rgb, but decoded at reduced size (at least FEATURE_SIDE px a side) where the
    format allows it: JPEG decodes at 1/2, 1/4 or 1/8 scale straight from its DCT blocks, which is
    several times faster than a full decode. Also returns the true (width, height), upright.

    Every feature (scan, upload search, eval) must come through here, so they're comparable."""
    return _open(source, min_side=FEATURE_SIDE)


def _open(source: Path | IO[bytes], min_side: int | None) -> tuple[Image.Image, str, tuple[int, int]]:
    try:
        with warnings.catch_warnings():
            # Pillow warns above MAX_IMAGE_PIXELS and raises at twice that; treat both as errors.
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as img:
                suffix = source.suffix if isinstance(source, Path) else ""
                fmt = img.format or suffix.lstrip(".").upper()
                img.seek(0)  # first frame of animated GIF/WebP
                width, height = img.size  # from the header, before any reduced decode
                if img.getexif().get(EXIF_ORIENTATION) in SWAPS_AXES:
                    width, height = height, width
                if min_side:
                    img.draft("RGB", (min_side, min_side))  # no-op for formats other than JPEG
                img = ImageOps.exif_transpose(img)
                return _to_rgb(img), fmt, (width, height)
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as e:
        raise DecodeError(f"{type(e).__name__}: {e}") from e


def _to_rgb(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return img.convert("RGB")
