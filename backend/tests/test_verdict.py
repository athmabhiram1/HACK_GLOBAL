"""BatonGate Task 8 (RED): verdict + inference + voice + dashboard wiring.

Covers: (a) BLOCKED on secret-found / build-fail / critical-reachable CVE,
SHIP when all pass (synthesized gate-result dicts, no real gates);
(b) score bounds 0-100 on adversarial inputs; (c) Inference called exactly
once with redacted prompt (stub inference_fn; no secrets/API keys in prompt);
timeout/exception -> static summary template; (d) voice stub: transcript fills
repo field, text-only works with voice_fn=None; (e) missing Exa/Wispr keys ->
verdict identical (compare with/without extras).
"""

import time

from fastapi.testclient import TestClient


# ---------------------------------------------------------------- helpers

def _gates_all_pass():
    return {
        "secrets": {"status": "pass", "summary": "no leaked keys",
                    "evidence": {"found": False, "sarif_ref": "/artifacts/x.sarif",
                                 "redactions": 0}},
        "deps": {"status": "pass", "summary": "no known CVEs",
                 "evidence": {"findings": [], "score": 100}},
        "docs": {"status": "pass", "summary": "docs match code", "evidence": {"stale": []}},
        "cost": {"status": "pass", "summary": "$6.00/mo, no waste",
                 "evidence": {"current": 6.0, "simulated": 6.0, "saved": 0.0}},
        "build": {"status": "pass", "summary": "GET /healthz 200",
                  "evidence": {"built": True, "healthz": "pass", "log_tail": "ok"}},
    }


def _gates_blocked_secret():
    gates = _gates_all_pass()
    gates["secrets"] = {"status": "fail", "summary": "2 leaked keys redacted",
                        "evidence": {"found": True, "sarif_ref": "/artifacts/x.sarif",
                                     "redactions": 2}}
    return gates


# ------------------------------------------------------------ (a) verdicts

def test_blocked_on_secret_found():
    from backend.app.verdict import decide

    out = decide(_gates_blocked_secret())
    assert out["verdict"] == "BLOCKED"


def test_blocked_on_build_fail():
    from backend.app.verdict import decide

    gates = _gates_all_pass()
    gates["build"] = {"status": "fail", "summary": "GET /healthz timeout",
                      "evidence": {"built": False, "healthz": "fail",
                                   "log_tail": "boom"}}
    out = decide(gates)
    assert out["verdict"] == "BLOCKED"


def test_blocked_on_critical_reachable_cve():
    from backend.app.verdict import decide

    gates = _gates_all_pass()
    gates["deps"] = {"status": "warn",
                     "summary": "jinja2@2.4.1 CVE-2023-30861 CVSS 9.8 reachable",
                     "evidence": {"findings": [{"pkg": "jinja2", "version": "2.4.1",
                                                "severity": "Critical", "cvss": 9.8,
                                                "reachable": True, "typo": False,
                                                "fix": "jinja2>=3.1"}],
                                  "score": 18}}
    out = decide(gates)
    assert out["verdict"] == "BLOCKED"


def test_ship_when_all_pass():
    from backend.app.verdict import decide

    out = decide(_gates_all_pass())
    assert out["verdict"] == "SHIP"
    assert 80 <= out["score"] <= 100


# --------------------------------------------------------------- (b) bounds

def test_score_bounds_on_adversarial_inputs():
    from backend.app.verdict import decide

    gates = _gates_all_pass()
    gates["deps"] = {"status": "warn", "summary": "x",
                     "evidence": {"findings": [], "score": 999}}
    assert 0 <= decide(gates)["score"] <= 100

    gates = _gates_all_pass()
    gates["deps"] = {"status": "warn", "summary": "x",
                     "evidence": {"findings": [], "score": -50}}
    assert 0 <= decide(gates)["score"] <= 100

    gates = _gates_all_pass()
    gates["deps"] = {"status": "warn", "summary": "x",
                     "evidence": {"findings": [], "score": None}}
    assert 0 <= decide(gates)["score"] <= 100

    gates = _gates_all_pass()
    gates["deps"] = {"status": "warn", "summary": "x",
                     "evidence": {"findings": [], "score": "high"}}
    out = decide(gates)
    assert 0 <= out["score"] <= 100
    assert out["verdict"] in ("SHIP", "FIX", "BLOCKED")


# ------------------------------------------------------------ (c) inference

SECRET = "ghp_fakesecretvalue1234567890"
API_KEY = "sk-live-fakeapikey999"


def test_inference_called_once_with_redacted_prompt():
    from backend.app import inference as inference_mod

    calls = []

    def fake_client(prompt):
        calls.append(prompt)
        return "Static test summary."

    gates = _gates_blocked_secret()
    gates["deps"] = {"status": "warn", "summary": "token " + SECRET,
                     "evidence": {"findings": [], "score": 60}}
    out = inference_mod.summarize(gates, client=fake_client)
    assert out == "Static test summary."
    assert len(calls) == 1
    assert SECRET not in calls[0]
    assert API_KEY not in (calls[0] if False else calls[0])
    assert "ghp_" not in calls[0]


def test_inference_timeout_or_exception_uses_static_template():
    from backend.app import inference as inference_mod

    def boom(prompt):
        raise TimeoutError("inference down")

    out = inference_mod.summarize(_gates_blocked_secret(), client=boom)
    assert isinstance(out, str) and out
    assert "fix" in out.lower() or "blocked" in out.lower()

    out2 = inference_mod.summarize(_gates_all_pass(), client=None,
                                   _env_key="")
    assert isinstance(out2, str) and out2


# ---------------------------------------------------------------- (d) voice

def test_voice_stub_transcript_fills_repo_field():
    from backend.app import voice_gate

    out = voice_gate.transcribe("aGVsbG8=", client=lambda b64: "https://github.com/owner/repo")
    assert out == {"transcript": "https://github.com/owner/repo"}


def test_text_only_works_with_no_audio():
    from backend.app import voice_gate

    out = voice_gate.transcribe(None, client=None)
    assert out == {"transcript": None}
    out2 = voice_gate.transcribe("", client=lambda b64: "x")
    assert out2 == {"transcript": None}


def test_voice_client_failure_never_raises():
    from backend.app import voice_gate

    def boom(b64):
        raise RuntimeError("wispr down")

    assert voice_gate.transcribe("aGVsbG8=", client=boom) == {"transcript": None}


# --------------------------------------------- (e) missing keys: same verdict

def test_missing_exa_wispr_keys_verdict_identical():
    from backend.app.verdict import decide

    base = decide(_gates_blocked_secret())
    with_extras = decide(dict(_gates_blocked_secret(),
                              exa_links=[{"url": "https://example.com/fix",
                                          "title": "Fix", "highlights": ["h"]}],
                              voice_transcript="https://github.com/owner/repo",
                              inference_summary="extra"))
    assert with_extras["verdict"] == base["verdict"]
    assert with_extras["score"] == base["score"]

    ship_base = decide(_gates_all_pass())
    ship_extra = decide(dict(_gates_all_pass(), exa_links=[], voice_transcript=None))
    assert ship_extra == ship_base


# ------------------------------------------------------- API wiring + shape

def _wait_done(client, job_id, timeout_s=10.0):
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        r = client.get("/api/jobs/%s" % job_id)
        assert r.status_code == 200
        last = r.json()
        if last.get("status") == "done":
            return last
        time.sleep(0.05)
    raise AssertionError("job %s never reached done: %r" % (job_id, last))


def test_gate_post_202_and_job_shape():
    from backend.app import main as main_mod

    def fake_pipeline(job):
        from backend.app.verdict import decide

        gates = _gates_all_pass()
        decision = decide(gates)
        return {"gates": [{"name": n, "status": gates[n]["status"],
                           "summary": gates[n]["summary"],
                           "evidence": gates[n]["evidence"]}
                          for n in ("secrets", "deps", "docs", "cost", "build")],
                "score": decision["score"],
                "verdict": decision["verdict"], "demo_mode": True,
                "exa_links": [], "voice_transcript": None,
                "inference_summary": "Ready to ship on Vultr.",
                "artifacts": {"sarif": "/artifacts/%s.sarif" % job["job_id"],
                              "log": "/artifacts/%s.log" % job["job_id"]}}

    with TestClient(main_mod.app) as client:
        main_mod.app.state.pipeline_fn = fake_pipeline
        try:
            r = client.post("/api/gate", json={"repo_url": "https://github.com/owner/repo"})
            assert r.status_code == 202
            job_id = r.json()["job_id"]
            body = _wait_done(client, job_id)
            assert body["score"] is not None and 0 <= body["score"] <= 100
            assert body["verdict"] in ("SHIP", "FIX", "BLOCKED")
            assert isinstance(body["gates"], list) and len(body["gates"]) == 5
            assert body["exa_links"] == []
            assert body["voice_transcript"] is None
            assert "demo_mode" in body
            assert body["artifacts"]["sarif"].endswith(".sarif")
            assert body["artifacts"]["log"].endswith(".log")
            assert body.get("inference_summary")
        finally:
            main_mod.app.state.pipeline_fn = main_mod.run_pipeline


def test_gate_post_rejects_bad_url_with_400():
    from backend.app import main as main_mod

    with TestClient(main_mod.app) as client:
        r = client.post("/api/gate", json={"repo_url": "http://evil.example/x"})
        assert r.status_code == 400
        assert "error" in r.json() and "fix_hint" in r.json()


def test_voice_endpoint_text_fallback():
    from backend.app import main as main_mod

    with TestClient(main_mod.app) as client:
        r = client.post("/api/voice", json={"audio_b64": None})
        assert r.status_code == 200
        assert r.json() == {"transcript": None}


def test_healthz_still_green():
    from backend.app import main as main_mod

    with TestClient(main_mod.app) as client:
        r = client.get("/api/healthz")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}
