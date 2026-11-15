"""BatonGate Task 7: build gate (sandboxed, last). Mocked docker in unit tests.

Clone hardening per PLAN/02-architecture §3.5: https-only + allowlist via
parse_repo_input, deny IP-literals/private/metadata ranges via DNS-resolve
check, git flags `-c protocol.ext.allow=never -c protocol.file.allow=never
-c http.followRedirects=false clone --depth 1 --recurse-submodules=no --
<url>`, reject `-` prefix, 60s clone timeout, 50MB pre-check via
check_repo_size, redacted log_tail, DEMO REPLAY fallback.
"""

import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

from backend.app.parsers import assert_no_submodules, check_repo_size, parse_repo_input

CLONE_TIMEOUT_S = 60
BUILD_TIMEOUT_S = 300
TAIL_LINES = 200

# Bridge-run flags per §3.5 (used by the real docker runner on the VM;
# mocked out in unit tests). NOTE: no `--network none` here — none +
# `-p` ignores the publish, so we probe the mapped port on the bridge
# (or `docker exec` curl when an isolated network is kept).
RUN_FLAGS = [
    "--rm",
    "--memory=512m",
    "--memory-swap=512m",
    "--cpus=0.5",
    "--pids-limit=64",
    "--read-only",
    "--cap-drop=ALL",
    "-u",
    "65534",
]

_REPLAY_PATH = (
    Path(__file__).resolve().parents[2] / "samples" / "broken-dockerfile" / "build-fail.log"
)

_SECRET_RES = [
    re.compile(r"(?i)(api[_-]?key|secret|token|passwd|password)(\s*[:=]\s*)\S+"),
    re.compile(r"ghp_[A-Za-z0-9]+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"),
]


def redact(text: str) -> str:
    out = text or ""
    out = _SECRET_RES[0].sub(r"\1\2***REDACTED***", out)
    for rx in _SECRET_RES[1:]:
        out = rx.sub("***REDACTED***", out)
    return out


def tail_lines(text: str, n: int = TAIL_LINES) -> str:
    lines = (text or "").splitlines()
    return "\n".join(lines[-n:])


def load_replay_tail() -> str:
    try:
        raw = _REPLAY_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError:
        raw = "ERROR: build failed (pre-recorded log missing)"
    return "[DEMO REPLAY]\n" + tail_lines(raw)


def build_clone_cmd(repo_url: str) -> list:
    return [
        "git",
        "-c",
        "protocol.ext.allow=never",
        "-c",
        "protocol.file.allow=never",
        "-c",
        "http.followRedirects=false",
        "clone",
        "--depth",
        "1",
        "--recurse-submodules=no",
        "--",
        repo_url,
    ]


def _deny_host(host: str) -> str | None:
    """Return a reason string when the host must be rejected, else None."""
    if not host:
        return "empty host"
    try:
        ipaddress.ip_address(host)
        return "IP literals are not accepted (got %s)" % host
    except ValueError:
        pass
    if host.lower() in ("metadata.google.internal",):
        return "metadata host denied"
    try:
        infos = socket.getaddrinfo(host, 443)
    except socket.gaierror:
        return "DNS resolution failed for %s" % host
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return "unparseable resolved address %s" % ip_str
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip_str == "169.254.169.254"
        ):
            return "resolved address %s is denied (private/metadata range)" % ip_str
    return None


def _fix(reason: str, tail: str = "", replay: bool = False) -> dict:
    return {
        "built": False,
        "healthz": "fail",
        "verdict": "FIX",
        "error": reason,
        "log_tail": redact(tail) if tail and not replay else tail,
        "replay": replay,
    }


def build_and_probe(repo_url, workdir, runner=None, timeout_s: int = BUILD_TIMEOUT_S) -> dict:
    """Clone (hardened) -> docker build (300s kill) -> bridge probe.

    `runner` is a fake in unit tests (clone/build/probe/cleanup/get_size).
    With runner=None a subprocess-backed default is used on the VM.
    Cleanup runs in `finally`, always.
    """
    from backend.app.queue import _default_runner  # local import: no cycle

    if isinstance(repo_url, str) and repo_url.startswith("-"):
        return _fix("repo_url must not start with '-'")
    try:
        parsed = parse_repo_input(repo_url)
    except ValueError as exc:
        detail = exc.args[0] if exc.args else {}
        msg = detail.get("error", str(exc)) if isinstance(detail, dict) else str(exc)
        return _fix(msg)
    host = urlparse(repo_url.strip()).hostname or parsed.get("host", "")
    denied = _deny_host(host)
    if denied:
        return _fix(denied)

    active = runner if runner is not None else _default_runner()
    size_bytes = None
    if hasattr(active, "get_size"):
        try:
            size_bytes = active.get_size(repo_url)
        except Exception:
            size_bytes = None
    if size_bytes is not None:
        try:
            check_repo_size(size_bytes)
            assert_no_submodules(repo_url)
        except ValueError as exc:
            detail = exc.args[0] if exc.args else {}
            msg = detail.get("error", str(exc)) if isinstance(detail, dict) else str(exc)
            return _fix(msg)

    cmd = build_clone_cmd(repo_url.strip())
    try:
        try:
            active.clone(cmd, CLONE_TIMEOUT_S)
        except TypeError:
            active.clone(cmd, timeout=CLONE_TIMEOUT_S)
        try:
            raw_log = active.build(str(workdir), timeout_s)
        except TypeError:
            raw_log = active.build(str(workdir), timeout=timeout_s)
        healthz = active.probe(str(workdir))
        return {
            "built": True,
            "healthz": healthz,
            "verdict": "SHIP" if healthz == "pass" else "FIX",
            "log_tail": redact(tail_lines(str(raw_log or ""))),
            "replay": False,
        }
    except TimeoutError as exc:
        return {
            "built": False,
            "healthz": "fail",
            "verdict": "FIX",
            "error": "build timed out after %ss: %s" % (timeout_s, exc),
            "log_tail": load_replay_tail(),
            "replay": True,
        }
    except Exception as exc:
        return {
            "built": False,
            "healthz": "fail",
            "verdict": "FIX",
            "error": str(exc),
            "log_tail": load_replay_tail(),
            "replay": True,
        }
    finally:
        try:
            cleanup = getattr(active, "cleanup", None)
            if cleanup is not None:
                try:
                    cleanup(str(workdir))
                except TypeError:
                    cleanup()
        except Exception:
            pass
