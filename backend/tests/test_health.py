from fastapi.testclient import TestClient

from backend.app.main import app


def test_healthz_200():
    with TestClient(app) as client:
        r = client.get("/api/healthz")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


def test_root_serves_form():
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
