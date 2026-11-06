import os
import tempfile
import time

# Must run before image_analyzer is imported: settings are read once, at import.
os.environ["IMAGE_ANALYZER_DATA_DIR"] = tempfile.mkdtemp(prefix="image-analyzer-test-")
os.environ.setdefault("IMAGE_ANALYZER_WORKERS", "2")
os.environ.setdefault("IMAGE_ANALYZER_EMBEDDER", "fake")  # no model download in tests

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from image_analyzer.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app, base_url="http://localhost") as c:  # the context manager runs the lifespan (DB init, job manager)
        yield c


def wait_for_job(client: TestClient, job_id: str, timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.1)
    raise TimeoutError(f"job {job_id} still running after {timeout}s")


def scan(client: TestClient, library_id: int, **params) -> dict:
    r = client.post(f"/api/libraries/{library_id}/scan", params=params)
    assert r.status_code == 202, r.text
    return wait_for_job(client, r.json()["id"])


@pytest.fixture
def library(client, tmp_path):
    """A fixture library: 2 synthetic groups (22 images), plus one corrupt file."""
    from image_analyzer.devtools.make_fixtures import build, synthetic_sources

    build(synthetic_sources(2, tmp_path / "src"), tmp_path / "set")
    root = tmp_path / "set" / "images"
    (root / "broken.jpg").write_bytes(b"not really a jpeg")
    r = client.post("/api/libraries", json={"path": str(root), "name": "fixtures"})
    assert r.status_code == 201, r.text
    lib = r.json()
    yield lib, root
    client.delete(f"/api/libraries/{lib['id']}")
