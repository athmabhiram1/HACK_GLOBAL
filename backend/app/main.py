"""BatonGate backend: FastAPI skeleton (Task 1).

Forked from hackglobal-starter/templates/chat-app/main.py.
Adds GET /api/healthz + static fallback for /.
Single-worker asyncio.Queue(maxsize=1) placeholder bound to lifespan
for the later job pipeline (Tasks 7-8 fill in the worker).
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


async def _queue_worker(queue: asyncio.Queue) -> None:
    """Placeholder single worker; real pipeline lands in Task 7."""
    while True:
        job = await queue.get()
        try:
            pass  # replaced by build pipeline in later tasks
        finally:
            queue.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    app.state.queue = queue
    worker = asyncio.create_task(_queue_worker(queue))
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
