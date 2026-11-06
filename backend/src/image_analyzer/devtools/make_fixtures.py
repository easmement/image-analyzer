"""Generate a labelled fixture set for tests and threshold tuning.

Each source photo becomes a group of known variants (resized, recompressed, cropped, ...).
Variants of the same source are expected matches at the level given in EXPECTED; anything
from a different source is an expected non-match.

    uv run python -m image_analyzer.devtools.make_fixtures --source ~/Pictures/sample --out fixtures
    uv run python -m image_analyzer.devtools.make_fixtures --synthetic 12 --out fixtures

Output: <out>/images/<group>/<variant>.<ext> and <out>/manifest.json.
"""

import argparse
import json
import random
import shutil
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

SOURCE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
EXIF_ORIENTATION = 0x0112

# Each transform takes the upright RGB source and writes one variant file, returning its path.
Transform = Callable[[Image.Image, Path, Path], Path]


def _save_jpeg(img: Image.Image, dest: Path, quality: int = 92, **kw) -> Path:
    path = dest.with_suffix(".jpg")
    img.save(path, "JPEG", quality=quality, **kw)
    return path


def _copy(_img: Image.Image, _src: Path, dest: Path) -> Path:
    # Byte-for-byte copy of this group's "original" variant (written first), so the pair
    # shares a SHA-256 and exercises the "exact" level.
    path = dest.with_suffix(".jpg")
    shutil.copyfile(dest.parent / "original.jpg", path)
    return path


def _crop(img: Image.Image, _src: Path, dest: Path) -> Path:
    w, h = img.size
    dx, dy = int(w * 0.05), int(h * 0.05)  # 5% off each side = 10% smaller
    return _save_jpeg(img.crop((dx, dy, w - dx, h - dy)), dest)


def _watermark(img: Image.Image, _src: Path, dest: Path) -> Path:
    out = img.copy()
    draw = ImageDraw.Draw(out)
    w, h = out.size
    size = max(12, h // 12)
    draw.text((w * 0.05, h * 0.85), "© SAMPLE", fill=(255, 255, 255), font_size=size)
    return _save_jpeg(out, dest)


def _exif_rotated(img: Image.Image, _src: Path, dest: Path) -> Path:
    # Pixels stored rotated 90° CCW with Orientation=6 ("rotate 90° CW to display"),
    # so a viewer that honours EXIF shows exactly the original.
    exif = Image.Exif()
    exif[EXIF_ORIENTATION] = 6
    return _save_jpeg(img.rotate(90, expand=True), dest, exif=exif)


VARIANTS: dict[str, Transform] = {
    "original": lambda img, src, dest: _save_jpeg(img, dest, quality=95),
    "copy": _copy,
    "resize50": lambda img, src, dest: _save_jpeg(
        img.resize((img.width // 2, img.height // 2), Image.Resampling.LANCZOS), dest
    ),
    "jpeg_q40": lambda img, src, dest: _save_jpeg(img, dest, quality=40),
    "png": lambda img, src, dest: (img.save(p := dest.with_suffix(".png"), "PNG"), p)[1],
    "crop10": _crop,
    "bright20": lambda img, src, dest: _save_jpeg(ImageEnhance.Brightness(img).enhance(1.2), dest),
    "watermark": _watermark,
    "exif_rotated": _exif_rotated,
    "rot90": lambda img, src, dest: _save_jpeg(img.rotate(-90, expand=True), dest),
    "mirror": lambda img, src, dest: _save_jpeg(ImageOps.mirror(img), dest),
}

# Ground truth: the match level each variant should have against its group's "original".
# Levels: "exact" | "near_duplicate" | "similar".
# TODO(human): fill in one entry per key in VARIANTS. These labels define what the app
# counts as "the same picture" and drive the Phase 2 precision/recall numbers.
EXPECTED: dict[str, str] = {
    "original": "near_duplicate",
    "copy": "exact",
    "resize50": "near_duplicate",
    "jpeg_q40": "near_duplicate",
    "png": "near_duplicate",
    "crop10": "near_duplicate",
    "bright20": "near_duplicate",
    "watermark": "near_duplicate",
    "exif_rotated": "near_duplicate",
    "rot90": "near_duplicate",
    "mirror": "near_duplicate",
}


def synthetic_sources(n: int, out_dir: Path, seed: int = 0) -> list[Path]:
    """Procedural images for when no real photos are at hand. Fine for hash tests; too simple
    to judge semantic similarity, so prefer real photos for threshold tuning."""
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(n):
        img = Image.new("RGB", (800, 600), tuple(rng.randrange(256) for _ in range(3)))
        draw = ImageDraw.Draw(img)
        for _ in range(rng.randint(6, 14)):
            x0, y0 = rng.randrange(700), rng.randrange(500)
            box = (x0, y0, x0 + rng.randint(40, 300), y0 + rng.randint(40, 300))
            colour = tuple(rng.randrange(256) for _ in range(3))
            (draw.ellipse if rng.random() < 0.5 else draw.rectangle)(box, fill=colour)
        path = out_dir / f"synthetic_{i:03d}.png"
        img.save(path)
        paths.append(path)
    return paths


def build(sources: list[Path], out: Path) -> dict:
    missing = set(VARIANTS) - set(EXPECTED)
    if missing:
        print(f"warning: no EXPECTED label for {sorted(missing)}; manifest will have null labels")

    images_dir = out / "images"
    if images_dir.exists():
        shutil.rmtree(images_dir)
    entries = []
    for src in sources:
        group = src.stem
        group_dir = images_dir / group
        group_dir.mkdir(parents=True)
        with Image.open(src) as raw:
            img = ImageOps.exif_transpose(raw).convert("RGB")
        for name, transform in VARIANTS.items():
            path = transform(img, src, group_dir / name)
            entries.append(
                {
                    "path": str(path.relative_to(out)),
                    "group": group,
                    "variant": name,
                    "expected": EXPECTED.get(name),
                }
            )
    manifest = {"variants": list(VARIANTS), "expected": EXPECTED, "images": entries}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--source", type=Path, help="folder of source photos (~30 recommended)")
    src.add_argument("--synthetic", type=int, metavar="N", help="generate N procedural sources")
    p.add_argument("--out", type=Path, default=Path("fixtures"))
    args = p.parse_args()

    if args.source:
        sources = sorted(f for f in args.source.expanduser().iterdir() if f.suffix.lower() in SOURCE_EXTS)
        if not sources:
            p.error(f"no images found in {args.source}")
    else:
        sources = synthetic_sources(args.synthetic, args.out / "sources")

    manifest = build(sources, args.out)
    print(f"wrote {len(manifest['images'])} images in {len(sources)} groups to {args.out}/")


if __name__ == "__main__":
    main()
