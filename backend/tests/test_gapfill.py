"""Gap-fill tests (backend implementer, TDD RED first).

Covers: voice None/empty with zero network, malformed /api/voice bodies,
GET / serving static index.html, unknown-job 404, full demo run -> SARIF.
"""

import json
import time

from fastapi.testclient import TestClient

from backend.app import main as main_mod
from backend.app import voice_gate


def test_transcribe_none_and_empty_no_network():
    calls = []

    def boom(audio_b64, *args, **kwargs):
        calls.append(audio_b64)
        raise AssertionError("network must not be touched for None/empty audio")

    orig = voice_gate._default_client
    voice_gate._default_client = boom
    try:
        assert voice_gate.transcribe(None) == {"transcript": None}
        assert voice_gate.transcribe("") == {"transcript": None}
    finally:
        voice_gate._default_client = orig
    assert calls == []


def test_voice_malformed_bodies_never_500():
    with TestClient(main_mod.app) as client:
        for body in ({}, {"audio_b64": "!!!not-base64!!!"}):
            r = client.post("/api/voice", json=body)
            assert r.status_code == 200, (body, r.status_code, r.text)
            assert r.json() == {"transcript": None}
        # non-dict JSON body: best-effort 200, never 4xx/500
        r = client.post("/api/voice", json="not-base64-string")
        assert r.status_code == 200, r.text
        assert r.json() == {"transcript": None}


def test_root_serves_static_index_html():
    with TestClient(main_mod.app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert main_mod.INDEX_FILE.is_file()
        assert r.text == main_mod.INDEX_FILE.read_text(encoding="utf-8")


def test_unknown_job_404_json():
    with TestClient(main_mod.app) as client:
        r = client.get("/api/jobs/no-such-job-xyz")
        assert r.status_code == 404
        assert "error" in r.json()


def test_demo_run_sarif_downloadable():
    with TestClient(main_mod.app) as client:
        r = client.post("/api/gate", json={"repo_url": "https://github.com/owner/repo"})
        assert r.status_code == 202, r.text
        job_id = r.json()["job_id"]
        deadline = time.time() + 15.0
        last = None
        while time.time() < deadline:
            jr = client.get("/api/jobs/%s" % job_id)
            assert jr.status_code == 200
            last = jr.json()
            if last.get("status") == "done":
                break
            time.sleep(0.05)
        assert last and last.get("status") == "done", last
        sarif_path = (last.get("artifacts") or {}).get("sarif") or last.get("sarif_path")
        assert sarif_path and sarif_path.endswith(".sarif")
        sr = client.get(sarif_path)
        assert sr.status_code == 200, sr.text[:200]
        data = json.loads(sr.text)
        log = data.get("sarifLog", data)
        assert isinstance(log.get("runs"), list)
