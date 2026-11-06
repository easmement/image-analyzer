"""DNS-rebinding defence and CSV formula injection."""

import shutil

import pytest

from conftest import scan


@pytest.mark.parametrize("headers", [
    {},
    {"origin": "http://localhost:3000"},
    {"x-forwarded-host": "localhost:3000", "origin": "http://localhost:3000"},  # via the Next.js proxy
    {"host": "127.0.0.1:8001"},
    {"host": "[::1]:8001"},
])
def test_localhost_requests_allowed(client, headers):
    assert client.get("/api/health", headers=headers).status_code == 200


@pytest.mark.parametrize("headers", [
    {"host": "evil.example:8001"},  # rebinding straight at the backend
    {"x-forwarded-host": "evil.example:3000"},  # rebinding through the Next.js proxy
    {"origin": "http://evil.example:3000"},
    {"host": "localhost.evil.example"},
])
def test_rebinding_requests_rejected(client, headers):
    r = client.get("/api/health", headers=headers)
    assert r.status_code == 403 and "localhost" in r.json()["detail"]
    assert client.post("/api/libraries", json={"path": "/"}, headers=headers).status_code == 403


def test_csv_export_neutralises_formulas(client, library):
    lib, root = library
    shutil.copyfile(root / "synthetic_000" / "original.jpg", root / "=HYPERLINK(1).jpg")
    scan(client, lib["id"])
    csv = client.get("/api/groups/export", params={"library_id": lib["id"]}).text
    assert "'=HYPERLINK(1).jpg" in csv
    assert ",=HYPERLINK" not in csv
