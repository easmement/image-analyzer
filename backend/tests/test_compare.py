import io

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance

from conftest import scan
from image_analyzer.search.compare import best_orientation_of, compare


def _photo(size=(320, 240)) -> Image.Image:
    return Image.effect_mandelbrot(size, (-2, -1.2, 1, 1.2), 64).convert("RGB")


def test_identical_images_have_no_differences():
    img = _photo()
    c = compare(img, img.copy())
    assert c.ssim == 1.0 and c.changed_fraction == 0.0 and c.orientation == 0


def test_local_edit_is_localised():
    a = _photo()
    b = a.copy()
    ImageDraw.Draw(b).rectangle((10, 10, 60, 60), fill=(255, 255, 255))  # ~3% of the frame
    c = compare(a, b)
    assert c.ssim < 0.99
    assert 0 < c.changed_fraction < 0.1
    heat = Image.open(io.BytesIO(c.heatmap))
    assert heat.mode == "RGBA" and heat.size == (c.width, c.height)
    alpha = np.asarray(heat.getchannel("A"))
    assert alpha[35, 35] > alpha[200, 250]  # red where it changed


def test_rotated_copy_is_aligned_before_comparing():
    a = _photo()
    b = a.transpose(Image.Transpose.ROTATE_90).resize((120, 160))  # rotated and smaller
    assert best_orientation_of(a, b) != 0
    assert compare(a, b).ssim > 0.8


def test_global_brightness_change_keeps_structure():
    a = _photo()
    c = compare(a, ImageEnhance.Brightness(a).enhance(1.2))
    assert c.ssim > 0.8 and c.orientation == 0


# --- API -----------------------------------------------------------------------------------

def _ids(client, lib_id):
    items = client.get("/api/images", params={"library_id": lib_id, "limit": 500}).json()["items"]
    return {i["rel_path"]: i["id"] for i in items}


def test_compare_endpoint(client, library):
    lib, _ = library
    scan(client, lib["id"])
    ids = _ids(client, lib["id"])
    a, b = ids["synthetic_000/original.jpg"], ids["synthetic_000/watermark.jpg"]
    r = client.get("/api/compare", params={"a": a, "b": b})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] == "near_duplicate" and not body["same_sha"]
    assert 0 < body["ssim"] < 1 and body["changed_fraction"] < 0.2
    for kind, media in (("a", "image/jpeg"), ("b", "image/jpeg"), ("heatmap", "image/png")):
        img = client.get("/api/compare/image", params={"a": a, "b": b, "kind": kind})
        assert img.status_code == 200 and img.headers["content-type"] == media

    rot = client.get("/api/compare", params={"a": a, "b": ids["synthetic_000/rot90.jpg"]}).json()
    assert rot["aligned_orientation"] != 0 and rot["ssim"] > 0.8

    assert client.get("/api/compare", params={"a": a, "b": a}).status_code == 400
    broken = ids["broken.jpg"]
    assert client.get("/api/compare", params={"a": a, "b": broken}).status_code == 409


def test_search_by_uploaded_image(client, library):
    lib, root = library
    scan(client, lib["id"])
    data = (root / "synthetic_001" / "original.jpg").read_bytes()
    r = client.post("/api/search/image", files={"file": ("query.jpg", data, "image/jpeg")},
                    data={"library_id": str(lib["id"])})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["query"]["filename"] == "query.jpg" and body["query"]["embedded"]
    top = body["matches"][:2]
    assert {m["verdict"] for m in top} == {"exact"}  # original.jpg and its byte copy
    assert all(m["image"]["rel_path"].startswith("synthetic_001/") for m in top)

    # Uploading isn't indexing: the library is unchanged.
    assert client.get(f"/api/libraries/{lib['id']}").json()["image_count"] == 23


def test_search_rejects_non_images(client):
    r = client.post("/api/search/image", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_unrelated_pair_is_not_rotated(client, library):
    lib, _ = library
    scan(client, lib["id"])
    ids = _ids(client, lib["id"])
    r = client.get("/api/compare", params={"a": ids["synthetic_000/original.jpg"],
                                           "b": ids["synthetic_001/original.jpg"]}).json()
    assert r["verdict"] == "different" and r["aligned_orientation"] == 0
