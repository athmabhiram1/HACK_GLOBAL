"""BatonGate backend: FastAPI skeleton (Task 1).

Forked from hackglobal-starter/templates/chat-app/main.py.
Adds GET /api/healthz + static fallback for /.
Single-worker asyncio.Queue(maxsize=1) bound to lifespan;
worker drains via asyncio.to_thread (Task 7 wiring; Task 8 fills handler).
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

INDEX_HTML = """<!doctype html>
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


from backend.app.queue import JobQueue, _noop_handler


@asynccontextmanager
async def lifespan(app: FastAPI):
    jobs = JobQueue(maxsize=1)
    app.state.queue = jobs.queue
    app.state.jobs = jobs
    worker = asyncio.create_task(jobs.worker(_noop_handler))
    app.state.worker = worker
    yield
    worker.cancel()

app = FastAPI(title="BatonGate", lifespan=lifespan)


@app.get("/api/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home():
    return INDEX_HTML
