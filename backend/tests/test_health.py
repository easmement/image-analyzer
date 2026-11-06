from fastapi.testclient import TestClient

from image_analyzer.main import app


def test_health():
    r = TestClient(app, base_url="http://localhost").get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["data_dir"]
    assert isinstance(body["torch"]["cuda_available"], bool)
