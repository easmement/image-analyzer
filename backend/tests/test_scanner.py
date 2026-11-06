import os

from image_analyzer.pipeline.scanner import FileStat, diff, walk


def _touch(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_walk_filters_and_recurses(tmp_path):
    _touch(tmp_path / "a.jpg")
    _touch(tmp_path / "sub" / "deep" / "b.PNG")
    _touch(tmp_path / "notes.txt")
    _touch(tmp_path / ".hidden" / "c.jpg")
    _touch(tmp_path / ".d.jpg")
    assert sorted(f.rel_path for f in walk(tmp_path)) == ["a.jpg", "sub/deep/b.PNG"]


def test_walk_skips_symlinks(tmp_path):
    outside = tmp_path / "outside"
    _touch(outside / "secret.jpg")
    lib = tmp_path / "lib"
    _touch(lib / "real.jpg")
    os.symlink(outside, lib / "linked_dir")
    os.symlink(outside / "secret.jpg", lib / "linked.jpg")
    assert [f.rel_path for f in walk(lib)] == ["real.jpg"]


def test_diff_new_changed_unchanged_removed():
    files = [FileStat("same.jpg", 10, 1), FileStat("changed.jpg", 20, 2), FileStat("new.jpg", 5, 3)]
    existing = {"same.jpg": (1, 10, 1, 2), "changed.jpg": (2, 20, 99, 2), "gone.jpg": (3, 7, 7, 2)}
    d = diff(files, existing, features_version=2)
    assert sorted(f.rel_path for f in d.to_process) == ["changed.jpg", "new.jpg"]
    assert d.unchanged == 1
    assert d.removed_ids == [3]


def test_diff_full_reprocesses_everything():
    files = [FileStat("same.jpg", 10, 1)]
    d = diff(files, {"same.jpg": (1, 10, 1, 2)}, features_version=2, full=True)
    assert [f.rel_path for f in d.to_process] == ["same.jpg"]
    assert d.unchanged == 0


def test_diff_reprocesses_rows_from_older_pipeline():
    files = [FileStat("old.jpg", 10, 1), FileStat("current.jpg", 10, 1)]
    existing = {"old.jpg": (1, 10, 1, 1), "current.jpg": (2, 10, 1, 2)}
    d = diff(files, existing, features_version=2)
    assert [f.rel_path for f in d.to_process] == ["old.jpg"]
    assert d.unchanged == 1


def test_reduced_decode_keeps_true_size_and_orientation(tmp_path):
    from PIL import Image

    from image_analyzer.pipeline.decode import FEATURE_SIDE, open_for_features

    big = Image.effect_mandelbrot((2400, 1800), (-2, -1.2, 1, 1.2), 64).convert("RGB")
    big.save(tmp_path / "plain.jpg", quality=90)
    exif = Image.Exif()
    exif[0x0112] = 6  # stored sideways, displayed upright
    big.rotate(90, expand=True).save(tmp_path / "sideways.jpg", quality=90, exif=exif)

    img, fmt, size = open_for_features(tmp_path / "plain.jpg")
    assert fmt == "JPEG" and size == (2400, 1800)
    assert min(img.size) >= FEATURE_SIDE and img.width < 2400  # decoded at reduced scale
    img, _, size = open_for_features(tmp_path / "sideways.jpg")
    assert size == (2400, 1800) and img.width > img.height  # upright, true size
