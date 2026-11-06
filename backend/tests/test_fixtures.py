import numpy as np
from PIL import Image, ImageOps

from image_analyzer.devtools.make_fixtures import VARIANTS, build, synthetic_sources


def _upright(path):
    with Image.open(path) as img:
        return np.asarray(ImageOps.exif_transpose(img).convert("RGB"), dtype=np.int16)


def test_build_writes_every_variant(tmp_path):
    sources = synthetic_sources(2, tmp_path / "src")
    manifest = build(sources, tmp_path / "out")
    assert len(manifest["images"]) == 2 * len(VARIANTS)
    for entry in manifest["images"]:
        assert (tmp_path / "out" / entry["path"]).is_file()


def test_copy_is_byte_identical_to_original(tmp_path):
    sources = synthetic_sources(1, tmp_path / "src")
    build(sources, tmp_path / "out")
    group = tmp_path / "out" / "images" / sources[0].stem
    assert (group / "copy.jpg").read_bytes() == (group / "original.jpg").read_bytes()


def test_exif_rotated_displays_like_original(tmp_path):
    sources = synthetic_sources(1, tmp_path / "src")
    build(sources, tmp_path / "out")
    group = tmp_path / "out" / "images" / sources[0].stem
    original, rotated = _upright(group / "original.jpg"), _upright(group / "exif_rotated.jpg")
    assert original.shape == rotated.shape
    # Both are JPEG-encoded, so allow small compression differences.
    assert np.abs(original - rotated).mean() < 3
