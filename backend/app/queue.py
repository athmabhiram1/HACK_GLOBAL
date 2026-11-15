"""BatonGate Task 7: single-worker asyncio.Queue(maxsize=1), lifespan-bound.

submit() -> 202/queued or 429 + retry_hint. The worker drains via
asyncio.to_thread so blocking docker/subprocess calls never stall the
event loop. Never use FastAPI BackgroundTasks for the pipeline.
"""

import asyncio
import shutil
import subprocess

RETRY_HINT = "Build worker busy (concurrency=1); retry after the current job finishes."


class JobQueue:
    def __init__(self, maxsize: int = 1):
        self._q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)

    def submit(self, job) -> dict:
        try:
            self._q.put_nowait(job)
            return {"accepted": True, "status": 202, "state": "queued"}
        except asyncio.QueueFull:
            return {"accepted": False, "status": 429, "retry_hint": RETRY_HINT}

    async def worker(self, handler) -> None:
        while True:
            job = await self._q.get()
            try:
                await asyncio.to_thread(handler, job)
            finally:
                self._q.task_done()

    @property
    def queue(self) -> asyncio.Queue:
        return self._q


def submit_job(queue: asyncio.Queue, job) -> dict:
    try:
        queue.put_nowait(job)
        return {"accepted": True, "status": 202, "state": "queued"}
    except asyncio.QueueFull:
        return {"accepted": False, "status": 429, "retry_hint": RETRY_HINT}


async def run_worker(queue: asyncio.Queue, handler) -> None:
    while True:
        job = await queue.get()
        try:
            await asyncio.to_thread(handler, job)
        finally:
            queue.task_done()


def _noop_handler(job) -> dict:
    return {"job": job, "status": "done"}


class _DefaultRunner:
    """Subprocess-backed runner used on the VM (never in unit tests)."""

    def get_size(self, url):
        return None  # size pre-check skipped when unknown

    def clone(self, cmd, timeout=60):
        subprocess.run(cmd, timeout=timeout, check=True, capture_output=True)

    def build(self, job_dir, timeout=300):
        from backend.app.build_gate import RUN_FLAGS  # late import: no cycle

        tag = "baton:job"
        subprocess.run(
            ["docker", "build", "-t", tag, "."],
            cwd=job_dir,
            timeout=timeout,
            check=True,
            capture_output=True,
            text=True,
        )
        port = 18080  # VM wiring picks a random free port; fixed here only
        subprocess.run(
            ["docker", "run", "-d", "-p", "127.0.0.1:%d:80" % port] + RUN_FLAGS + [tag],
            timeout=30,
            check=True,
            capture_output=True,
            text=True,
        )
        return "build ok"

    def probe(self, job_dir):
        return "fail"

    def cleanup(self, job_dir=None):
        try:
            subprocess.run(["docker", "rm", "-f", "baton-job"], timeout=15, capture_output=True)
        except Exception:
            pass
        if job_dir:
            shutil.rmtree(job_dir, ignore_errors=True)


def _default_runner() -> _DefaultRunner:
    return _DefaultRunner()
