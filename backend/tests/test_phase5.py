"""Phase 5: error report and retry, settings/thresholds, watch mode, HNSW switch."""

import shutil
import time
from pathlib import Path

import numpy as np
import pytest

from conftest import scan
from image_analyzer.core import thresholds
from image_analyzer.jobs import watcher as watcher_module
from image_analyzer.jobs.watcher import can_watch
from image_analyzer.search import index as index_module
from image_analyzer.search.index import FeatureSet, LibraryIndex


@pytest.fixture
def restore_thresholds():
    yield
    thresholds.save(thresholds.DEFAULTS)


def test_error_report_groups_by_kind_and_retry(client, library):
    lib, root = library
    scan(client, lib["id"])
    report = client.get(f"/api/libraries/{lib['id']}/errors").json()
    assert report["total"] == 1 and report["items"][0]["rel_path"] == "broken.jpg"
    assert report["kinds"][0]["count"] == 1 and report["kinds"][0]["kind"] in report["kinds"][0]["example"]

    # An unchanged broken file isn't retried by a normal scan...
    assert scan(client, lib["id"])["total"] == 0
    # ...but retry_errors reprocesses it; once it's fixed, the error is gone.
    shutil.copyfile(root / "synthetic_000" / "original.jpg", root / "broken.jpg")
    job = scan(client, lib["id"], retry_errors="true")
    assert job["failed"] == 0
    assert client.get(f"/api/libraries/{lib['id']}/errors").json()["total"] == 0


def test_job_reports_elapsed_and_stage_timings(client, library):
    lib, _ = library
    job = scan(client, lib["id"])
    assert job["elapsed_s"] > 0
    assert {"walk", "wait", "embed", "write"} <= set(job["timings"])


def test_thresholds_change_verdicts_immediately(client, library, restore_thresholds):
    lib, _ = library
    scan(client, lib["id"])
    s = client.get("/api/settings").json()
    assert s["thresholds"] == s["defaults"] == {"near_phash": 12, "near_dhash": 14, "similar_cosine": 0.85}
    assert s["config"]["embedder"] == "fake"

    def near_groups():
        return client.get("/api/groups", params={"library_id": lib["id"], "level": "near_duplicate"}).json()

    before = sum(g["count"] for g in near_groups())
    r = client.put("/api/settings/thresholds", json={"near_phash": 0, "near_dhash": 0, "similar_cosine": 0.99})
    assert r.status_code == 200 and r.json()["thresholds"]["near_phash"] == 0
    after = sum(g["count"] for g in near_groups())
    assert after < before  # stricter thresholds, fewer near-duplicates, no rescan needed
    assert thresholds.current().near_phash == 0  # and persisted for eval / restarts

    bad = client.put("/api/settings/thresholds", json={"near_phash": 99, "near_dhash": 0, "similar_cosine": 0.9})
    assert bad.status_code == 422


def test_windows_drives_cannot_be_watched():
    assert can_watch(Path("/mnt/c/Users/someone/Pictures")) is not None
    assert can_watch(Path("/home/someone/Pictures")) is None


def test_watch_mode_rescans_after_changes(client, library, monkeypatch):
    lib, root = library
    monkeypatch.setattr(watcher_module, "DEBOUNCE_S", 0.3)
    scan(client, lib["id"])
    assert client.patch(f"/api/libraries/{lib['id']}", json={"watch": True}).json()["watch"] is True

    shutil.copyfile(root / "synthetic_000" / "original.jpg", root / "new_photo.jpg")
    info: dict = {}
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        info = client.get(f"/api/libraries/{lib['id']}").json()
        if info["image_count"] == 24 and not info["active_job_id"]:
            break
        time.sleep(0.2)
    assert info["image_count"] == 24  # picked up without a manual scan

    assert client.patch(f"/api/libraries/{lib['id']}", json={"watch": False}).json()["watch"] is False


def test_hnsw_used_above_threshold_and_agrees_with_flat(monkeypatch):
    rng = np.random.default_rng(0)
    n, dim = 400, 32
    emb = rng.normal(size=(n, dim)).astype(np.float32)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    codes = rng.integers(0, 256, (n, 8, 8), dtype=np.uint8)
    f = FeatureSet(ids=np.arange(n), sha=[str(i) for i in range(n)], phash=codes, dhash=codes,
                   emb=emb, has_emb=np.ones(n, dtype=bool))
    flat = LibraryIndex(f)
    monkeypatch.setattr(index_module, "HNSW_THRESHOLD", 100)
    hnsw = LibraryIndex(f)
    assert type(hnsw.emb_index).__name__ == "IndexHNSWFlat" and type(flat.emb_index).__name__ == "IndexFlatIP"
    top_flat = [r for r, _ in flat.neighbors(0, method="semantic", k=10, min_cosine=-1)]
    top_hnsw = [r for r, _ in hnsw.neighbors(0, method="semantic", k=10, min_cosine=-1)]
    assert len(set(top_flat) & set(top_hnsw)) >= 8  # approximate, but nearly the same neighbours
