from image_analyzer.core.models import ImageInfo
from image_analyzer.search.grouping import pick_best


def _img(id: int, rel_path: str, *, w: int = 4000, h: int = 3000, size: int = 2_000_000, mtime: int = 0) -> ImageInfo:
    return ImageInfo(
        id=id, library_id=1, rel_path=rel_path, size_bytes=size, mtime_ns=mtime, sha256="x",
        width=w, height=h, format="JPEG", status="ok", error=None, indexed_at="",
    )


def test_camera_name_beats_copy_suffix():
    # Listed copy-first and newer-first, so neither order nor age can be what decides.
    images = [_img(1, "IMG_0012 (1).jpg"), _img(2, "IMG_0012.jpg", mtime=5)]
    assert pick_best(images) == 2


def test_shallower_folder_wins_when_names_match():
    images = [_img(1, "backup/2024/IMG_0012.jpg"), _img(2, "IMG_0012.jpg", mtime=5)]
    assert pick_best(images) == 2


def test_oldest_wins_when_nothing_else_differs():
    images = [_img(1, "a/copy.jpg", mtime=20), _img(2, "a/original.jpg", mtime=10)]
    assert pick_best(images) == 2


def test_resolution_beats_name():
    images = [_img(1, "IMG_0012.jpg", w=800, h=600), _img(2, "IMG_0012 (1).jpg")]
    assert pick_best(images) == 2


def test_deterministic_on_full_tie():
    a, b = _img(1, "x/IMG_0001.jpg"), _img(2, "y/IMG_0001.jpg")
    assert pick_best([a, b]) == pick_best([b, a]) == 1
