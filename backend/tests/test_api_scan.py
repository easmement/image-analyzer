"""End-to-end: register a library, scan it, browse it, group exact duplicates."""

import json
import shutil

from conftest import scan


def test_create_library_validation(client, tmp_path):
    assert client.post("/api/libraries", json={"path": "relative/dir"}).status_code == 400
    assert client.post("/api/libraries", json={"path": str(tmp_path / "nope")}).status_code == 400
    (tmp_path / "f.txt").write_text("x")
    assert client.post("/api/libraries", json={"path": str(tmp_path / "f.txt")}).status_code == 400


def test_duplicate_library_rejected(client, library):
    lib, root = library
    assert client.post("/api/libraries", json={"path": str(root)}).status_code == 409


def test_scan_indexes_images_and_isolates_bad_file(client, library):
    lib, _ = library
    job = scan(client, lib["id"])
    assert job["status"] == "completed", job
    assert (job["total"], job["done"], job["failed"]) == (23, 23, 1)

    info = client.get(f"/api/libraries/{lib['id']}").json()
    assert (info["image_count"], info["error_count"]) == (23, 1)
    assert info["last_scan_at"]

    errors = client.get("/api/images", params={"library_id": lib["id"], "status": "error"}).json()
    assert [i["rel_path"] for i in errors["items"]] == ["broken.jpg"]


def test_rescan_is_incremental(client, library):
    lib, root = library
    scan(client, lib["id"])
    (root / "broken.jpg").unlink()
    shutil.copyfile(root / "synthetic_000" / "png.png", root / "extra.png")

    job = scan(client, lib["id"])
    assert (job["total"], job["done"]) == (1, 1)  # only the new file
    assert job["message"] == "22 unchanged, 1 removed"
    assert scan(client, lib["id"], full="true")["total"] == 23


def test_pagination_covers_every_image_once(client, library):
    lib, _ = library
    scan(client, lib["id"])
    seen, cursor = [], None
    while True:
        params = {"library_id": lib["id"], "limit": 5, **({"cursor": cursor} if cursor else {})}
        page = client.get("/api/images", params=params).json()
        seen += [i["rel_path"] for i in page["items"]]
        if not (cursor := page["next_cursor"]):
            break
    assert len(seen) == 23 and seen == sorted(seen)


def test_thumbnail_and_file(client, library):
    lib, root = library
    scan(client, lib["id"])
    img = client.get("/api/images", params={"library_id": lib["id"], "status": "ok", "limit": 1}).json()["items"][0]

    thumb = client.get(f"/api/images/{img['id']}/thumbnail")
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/webp"
    assert "immutable" in thumb.headers["cache-control"]

    file = client.get(f"/api/images/{img['id']}/file")
    assert file.status_code == 200
    assert file.content == (root / img["rel_path"]).read_bytes()


def test_exact_groups(client, library):
    lib, _ = library
    scan(client, lib["id"])
    groups = client.get("/api/groups", params={"library_id": lib["id"]}).json()
    # Each synthetic group has original.jpg + copy.jpg as byte-identical files.
    assert len(groups) == 2
    for g in groups:
        assert g["level"] == "exact" and g["count"] == 2
        assert sorted(i["rel_path"].split("/")[1] for i in g["images"]) == ["copy.jpg", "original.jpg"]
        assert g["best_id"] in {i["id"] for i in g["images"]}
        assert g["reclaimable_bytes"] == g["total_bytes"] // 2

    csv = client.get("/api/groups/export", params={"library_id": lib["id"]})
    assert csv.headers["content-type"].startswith("text/csv")
    assert len(csv.text.strip().splitlines()) == 1 + 4


def test_scan_conflict_and_events(client, library):
    lib, _ = library
    r = client.post(f"/api/libraries/{lib['id']}/scan")
    job_id = r.json()["id"]
    assert client.post(f"/api/libraries/{lib['id']}/scan").status_code == 409

    events = []
    with client.stream("GET", f"/api/jobs/{job_id}/events") as stream:
        for line in stream.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line.removeprefix("data: ")))
    assert events[-1]["status"] == "completed"
    assert [e["done"] for e in events] == sorted(e["done"] for e in events)


def test_scan_stores_embeddings_and_similar_endpoint(client, library):
    lib, _ = library
    scan(client, lib["id"])
    health = client.get("/api/health").json()
    assert health["embedder"]["name"] == "fake-colour-grid"

    images = client.get("/api/images", params={"library_id": lib["id"], "status": "ok", "limit": 500}).json()["items"]
    original = next(i for i in images if i["rel_path"].endswith("synthetic_000/original.jpg"))
    near = client.get(f"/api/images/{original['id']}/similar").json()
    by_name = {m["image"]["rel_path"].split("/")[-1]: m for m in near}
    assert by_name["copy.jpg"]["verdict"] == "exact"
    assert by_name["rot90.jpg"]["verdict"] == "near_duplicate" and by_name["rot90.jpg"]["orientation"] != 0
    assert all(m["cosine"] is not None for m in near)

    semantic = client.get(f"/api/images/{original['id']}/similar", params={"method": "semantic"}).json()
    cosines = [m["cosine"] for m in semantic]
    assert semantic and cosines == sorted(cosines, reverse=True)


def test_group_levels_nest(client, library):
    lib, _ = library
    scan(client, lib["id"])
    counts = {}
    for level in ("exact", "near_duplicate", "similar"):
        groups = client.get("/api/groups", params={"library_id": lib["id"], "level": level}).json()
        counts[level] = sum(g["count"] for g in groups)
    # Each looser level groups at least as many images as the stricter one.
    assert counts["exact"] <= counts["near_duplicate"] <= counts["similar"]
