"""Task 7 RED: build gate + queue with FAKE docker runner (no real docker)."""

import asyncio

import pytest


def _stub_runner(**overrides):
    """Minimal fake runner recording calls; tests inject behaviour."""
    calls = {"clone": 0, "build": 0, "probe": 0, "cleanup": 0, "clone_cmd": None}

    class Stub:
        def get_size(self, url):
            return overrides.get("size_bytes", 1024)

        def clone(self, cmd, timeout):
            calls["clone"] += 1
            calls["clone_cmd"] = list(cmd)
            if overrides.get("clone_fail"):
                raise RuntimeError(overrides["clone_fail"])
            return "cloned"

        def build(self, job_dir, timeout):
            calls["build"] += 1
            if overrides.get("build_timeout"):
                raise TimeoutError("build timed out after %ss" % timeout)
            if overrides.get("build_fail"):
                raise RuntimeError(overrides["build_fail"])
            return "STEP 1/2 ... Successfully built"

        def probe(self, job_dir):
            calls["probe"] += 1
            return overrides.get("probe_result", "pass")

        def cleanup(self, job_dir):
            calls["cleanup"] += 1

    return Stub(), calls


def test_build_success():
    from backend.app.build_gate import build_and_probe

    runner, calls = _stub_runner()
    out = build_and_probe(
        "https://github.com/owner/repo", "/tmp/job1", runner=runner, timeout_s=300
    )
    assert out["built"] is True
    assert out["healthz"] == "pass"
    assert out.get("log_tail")
    # clone hardening flags present
    cmd = calls["clone_cmd"]
    assert "-c" in cmd and "protocol.ext.allow=never" in cmd
    assert "protocol.file.allow=never" in cmd
    assert "--recurse-submodules=no" in cmd
    assert "--" in cmd


def test_build_timeout_gives_fix_hint_and_replay_tail():
    from backend.app.build_gate import build_and_probe

    runner, _ = _stub_runner(build_timeout=True)
    out = build_and_probe(
        "https://github.com/owner/repo", "/tmp/job2", runner=runner, timeout_s=1
    )
    assert out["built"] is False
    assert out.get("verdict") == "FIX" or "FIX" in str(out)
    assert out.get("log_tail")  # DEMO REPLAY tail present
    assert out.get("replay") is True or "REPLAY" in str(out.get("log_tail", ""))


def test_cleanup_always_called_on_failure():
    from backend.app.build_gate import build_and_probe

    runner, calls = _stub_runner(build_timeout=True)
    build_and_probe(
        "https://github.com/owner/repo", "/tmp/job3", runner=runner, timeout_s=1
    )
    assert calls["cleanup"] >= 1

    runner2, calls2 = _stub_runner(build_fail="boom")
    build_and_probe(
        "https://github.com/owner/repo", "/tmp/job4", runner=runner2, timeout_s=300
    )
    assert calls2["cleanup"] >= 1


def test_queue_second_submit_rejected_without_draining():
    from backend.app.queue import JobQueue

    async def _go():
        q = JobQueue(maxsize=1)
        first = q.submit({"id": "a"})
        second = q.submit({"id": "b"})
        assert first["accepted"] is True
        assert second["accepted"] is False
        assert second["status"] == 429
        assert second.get("retry_hint")

    asyncio.run(_go())
