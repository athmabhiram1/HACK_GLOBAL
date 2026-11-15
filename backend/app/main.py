"""BatonGate backend: FastAPI (Tasks 1 + 8).

GET /api/healthz, GET / (dashboard), POST /api/gate -> 202 {job_id},
GET /api/jobs/{id} (full §4 report JSON), POST /api/voice (optional
transcript, never blocks), GET /artifacts/{name} (SARIF/log download).
Single-worker asyncio.Queue(maxsize=1) bound to lifespan; 429 when full.
All blocking work runs via asyncio.to_thread; gate failures never 500.
"""

import asyncio
import json
import os
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from backend.app import voice_gate
from backend.app.parsers import parse_repo_input
from backend.app.queue import RETRY_HINT, run_worker, submit_job

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
INDEX_FILE = STATIC_DIR / "index.html"
ARTIFACT_DIR = Path(tempfile.gettempdir()) / "batongate-artifacts"

CORE_ORDER = ("secrets", "deps", "docs", "cost", "build")

_FALLBACK_HTML = """<!doctype html>
<html><head><title>BatonGate</title></head>
<body>
<h1>BatonGate</h1>
<form id="gate-form" action="/api/gate" method="post">
<input name="repo_url" placeholder="https://github.com/owner/repo" />
<button type="submit">Score</button>
</form>
<div id="log"></div><div id="error"></div>
</body></html>
"""


def _pending_gates():
    return [{"name": name, "status": "queued", "summary": "waiting in queue",
             "evidence": {}} for name in CORE_ORDER]


def new_job_record(job_id, repo_url, voice_transcript=None, demo=False):
    return {
        "job_id": job_id,
        "status": "queued",
        "repo_url": repo_url,
        "score": None,
        "verdict": None,
        "demo_mode": bool(demo),
        "gates": _pending_gates(),
        "inference_summary": "",
        "exa_links": [],
        "voice_transcript": voice_transcript,
        "sarif_path": "/artifacts/%s.sarif" % job_id,
        "artifacts": {"sarif": "/artifacts/%s.sarif" % job_id,
                      "log": "/artifacts/%s.log" % job_id},
    }


def write_artifacts(job_id, sarif_data=None, log_tail=""):
    """Persist SARIF + log tail; returns {sarif, log} artifact paths."""
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    sarif = sarif_data if isinstance(sarif_data, dict) else {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{"tool": {"driver": {"name": "gitleaks", "rules": []}},
                  "results": []}],
    }
    sarif_path = ARTIFACT_DIR / ("%s.sarif" % job_id)
    log_path = ARTIFACT_DIR / ("%s.log" % job_id)
    try:
        sarif_path.write_text(json.dumps(sarif, indent=2), encoding="utf-8")
    except OSError:
        pass
    try:
        log_path.write_text(log_tail or "", encoding="utf-8", errors="replace")
    except OSError:
        pass
    return {"sarif": "/artifacts/%s.sarif" % job_id,
            "log": "/artifacts/%s.log" % job_id}


def run_pipeline(job):
    """Default worker pipeline: best-effort gates, never raises, never 500.

    Real mapped-port probe / real docker stays VM-only (Task 9): unless
    BATON_LIVE_BUILD=1, the build gate is skipped (warn, skipped=True) so a
    deferred build never BLOCKEDs the verdict. demo_mode=True whenever any
    fallback/deferral was used.
    """
    from backend.app import inference as inference_mod
    from backend.app.build_gate import load_replay_tail, redact
    from backend.app.cost_gate import estimate_cost
    from backend.app.docs_gate import check_docs
    from backend.app.exa_gate import fix_links
    from backend.app.verdict import decide

    job_id = job.get("job_id", "local")
    voice_transcript = job.get("voice_transcript")
    demo_mode = True  # worker synthetics until Task 9 live build

    gates = {}
    try:
        gates["secrets"] = {
            "status": "warn", "summary": "secrets scan deferred (no repo snapshot)",
            "evidence": {"found": False, "sarif_ref": "/artifacts/%s.sarif" % job_id,
                         "redactions": 0,
                         "note": "potential exposure, not verified active key "
                                 "(scanner deferred in this worker)"},
        }
    except Exception:
        gates["secrets"] = {"status": "warn", "summary": "secrets unavailable",
                            "evidence": {"found": False, "redactions": 0}}

    try:
        gates["deps"] = {"status": "pass", "summary": "no manifests scored",
                         "evidence": {"findings": [], "score": 100}}
    except Exception:
        gates["deps"] = {"status": "warn", "summary": "deps unavailable",
                         "evidence": {"findings": [], "score": 60}}

    try:
        docs_out = check_docs("", "")
        gates["docs"] = {"status": "warn", "summary": "no diff evidence",
                         "evidence": docs_out}
    except Exception:
        gates["docs"] = {"status": "warn", "summary": "docs unavailable",
                         "evidence": {"refused": True, "reason": "unavailable"}}

    try:
        cost_out = estimate_cost()
        gates["cost"] = {
            "status": "pass",
            "summary": "$%.2f/mo, simulated $%.2f/mo" % (
                cost_out.get("current", 0.0), cost_out.get("simulated", 0.0)),
            "evidence": cost_out,
        }
    except Exception:
        gates["cost"] = {"status": "warn", "summary": "cost unavailable",
                         "evidence": {"current": 0.0, "simulated": 0.0,
                                      "saved": 0.0}}

    if os.environ.get("BATON_LIVE_BUILD") == "1":
        try:
            from backend.app.build_gate import build_and_probe

            out = build_and_probe(job.get("repo_url", ""), str(ARTIFACT_DIR / job_id),
                                  timeout_s=300)
            healthy = out.get("built") is True and out.get("healthz") == "pass"
            gates["build"] = {
                "status": "pass" if healthy else "fail",
                "summary": "GET /healthz %s" % out.get("healthz"),
                "evidence": {"built": out.get("built"),
                             "healthz": out.get("healthz"),
                             "log_tail": out.get("log_tail", "")},
            }
            log_tail = out.get("log_tail", "")
        except Exception as exc:
            gates["build"] = {"status": "fail", "summary": "build error: %s" % exc,
                              "evidence": {"built": False, "healthz": "fail",
                                           "log_tail": load_replay_tail()}}
            log_tail = gates["build"]["evidence"]["log_tail"]
    else:
        gates["build"] = {
            "status": "warn", "summary": "build deferred (VM-only, Task 9)",
            "evidence": {"built": False, "healthz": "skip", "skipped": True,
                         "log_tail": "build deferred: set BATON_LIVE_BUILD=1 on the VM."},
        }
        log_tail = gates["build"]["evidence"]["log_tail"]

    exa_links = []
    try:
        api_key = os.environ.get("EXA_API_KEY", "")
        cves = []
        findings = gates.get("deps", {}).get("evidence", {}).get("findings", [])
        if isinstance(findings, list):
            for finding in findings[:3]:
                if isinstance(finding, dict) and finding.get("id"):
                    cves.append(str(finding["id"]))
        for cve in cves:
            exa_links.extend(fix_links(cve, api_key=api_key))
    except Exception:
        exa_links = []

    decision = decide(gates)
    try:
        summary = inference_mod.summarize(
            {"gates": [{"name": n, "status": gates[n]["status"],
                        "summary": gates[n]["summary"]} for n in CORE_ORDER],
             "score": decision["score"], "verdict": decision["verdict"]})
    except Exception:
        summary = "Blocked by failing gates; fix and rebuild."

    artifacts = write_artifacts(job_id, log_tail=redact(log_tail))
    return {
        "gates": [{"name": n, "status": gates[n]["status"],
                   "summary": gates[n]["summary"],
                   "evidence": gates[n].get("evidence", {})} for n in CORE_ORDER],
        "score": decision["score"],
        "verdict": decision["verdict"],
        "demo_mode": demo_mode,
        "exa_links": exa_links,
        "voice_transcript": voice_transcript,
        "inference_summary": summary,
        "sarif_path": artifacts["sarif"],
        "artifacts": artifacts,
    }


def _handle_job(app, job):
    store = app.state.store
    job_id = job.get("job_id")
    try:
        record = store.get(job_id)
        if record is not None:
            record["status"] = "running"
        report = app.state.pipeline_fn(job)
        if record is None:
            record = new_job_record(job_id, job.get("repo_url", ""),
                                    job.get("voice_transcript"), job.get("demo"))
            store[job_id] = record
        record.update(report)
        record["status"] = "done"
    except Exception as exc:
        fallback = store.get(job_id)
        if fallback is None:
            fallback = new_job_record(job_id, job.get("repo_url", ""))
            store[job_id] = fallback
        fallback.update({
            "status": "done", "score": 0, "verdict": "FIX",
            "demo_mode": True, "exa_links": [], "voice_transcript": None,
            "inference_summary": "Pipeline error (%s); fix and rebuild." % exc,
        })


@asynccontextmanager
async def lifespan(app: FastAPI):
    queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    app.state.queue = queue
    app.state.store = {}
    app.state.pipeline_fn = run_pipeline

    def _handler(job):
        _handle_job(app, job)

    worker = asyncio.create_task(run_worker(queue, _handler))
    app.state.worker = worker
    yield
    worker.cancel()

app = FastAPI(title="BatonGate", lifespan=lifespan)


@app.get("/api/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home():
    try:
        return INDEX_FILE.read_text(encoding="utf-8")
    except OSError:
        return _FALLBACK_HTML


@app.post("/api/gate")
def post_gate(body: dict):
    repo_url = body.get("repo_url", "") if isinstance(body, dict) else ""
    try:
        parse_repo_input(repo_url)
    except ValueError as exc:
        detail = exc.args[0] if exc.args else {}
        if isinstance(detail, dict):
            return JSONResponse(status_code=400, content=detail)
        return JSONResponse(status_code=400, content={"error": str(exc),
                                                      "fix_hint": "Use https://github.com/owner/repo."})
    job_id = uuid.uuid4().hex[:8]
    record = new_job_record(job_id, repo_url.strip(),
                            body.get("voice_transcript") if isinstance(body, dict) else None,
                            (body.get("demo") if isinstance(body, dict) else False))
    # mypy/state note: store is created in lifespan; TestClient runs lifespan.
    app.state.store[job_id] = record
    result = submit_job(app.state.queue, {"job_id": job_id, "repo_url": repo_url.strip(),
                                          "voice_transcript": record["voice_transcript"],
                                          "demo": record["demo_mode"]})
    if not result["accepted"]:
        return JSONResponse(status_code=429,
                            content={"error": "worker busy", "retry_hint": RETRY_HINT})
    return JSONResponse(status_code=202, content={"job_id": job_id, "status": "queued"})


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    record = app.state.store.get(job_id)
    if record is None:
        return JSONResponse(status_code=404, content={"error": "unknown job_id"})
    return record


@app.post("/api/voice")
async def post_voice(request: Request):
    """Best-effort transcript; any malformed body -> 200 {transcript: None}."""
    try:
        body = await request.json()
    except Exception:
        body = None
    if isinstance(body, dict):
        audio_b64 = body.get("audio_b64")
    elif isinstance(body, str):
        audio_b64 = body
    else:
        audio_b64 = None
    return voice_gate.transcribe(audio_b64)


@app.get("/artifacts/{fname}")
def get_artifact(fname: str):
    safe = os.path.basename(fname or "")
    if not safe or ".." in fname or "/" in fname:
        return JSONResponse(status_code=404, content={"error": "unknown artifact"})
    for suffix, media in ((".sarif", "application/json"), (".log", "text/plain")):
        if safe.endswith(suffix):
            path = ARTIFACT_DIR / safe
            if path.is_file():
                return FileResponse(str(path), media_type=media, filename=safe)
            return JSONResponse(status_code=404, content={"error": "unknown artifact"})
    return JSONResponse(status_code=404, content={"error": "unknown artifact"})
