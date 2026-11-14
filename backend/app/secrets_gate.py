"""BatonGate Task 3: secrets gate (gitleaks via docker, SARIF out).

Pure functions + thin docker boundary. stdlib only, Python 3.11.
Misuse raises ValueError({"error", "fix_hint"}) like parsers.py.
Docker/scanner failure degrades gracefully to a clean verdict whose
note still contains the base phrase (verdict layer checks substring).
"""

import json
import os
import re
import subprocess
import tempfile

BASE_NOTE = "potential exposure, not verified active key"

_IMAGE = "zricethezav/gitleaks:8.18.4"

_DEMO_HINT = "Re-run with ?demo=1 (DEMO REPLAY)."


def _err(error: str, fix_hint: str) -> ValueError:
    return ValueError({"error": error, "fix_hint": fix_hint})


_PREFIX_RE = re.compile(
    r"(?:ghp_[A-Za-z0-9_]+|gho_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+"
    r"|AKIA[0-9A-Z]{16}|sk-(?:live|test)-[A-Za-z0-9_\-]+|xox[bap]-[A-Za-z0-9_\-]+)"
)
_ASSIGN_RE = re.compile(
    r"(\b[A-Za-z_][A-Za-z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|PASSWD|PWD|AUTH|CREDENTIAL)"
    r"[A-Za-z0-9_]*\s*[:=]\s*['\"]?)([^\s'\"},;]+)",
    re.IGNORECASE,
)
_LONG_RE = re.compile(r"[A-Za-z0-9_\-+=]{20,}")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-+/=]{8,}")


def _default_runner(repo_dir: str) -> dict:
    """Run gitleaks in docker, return parsed SARIF dict. Raises on failure."""
    abs_repo = os.path.abspath(repo_dir)
    tmpdir = tempfile.mkdtemp(prefix="batongate-gitleaks-")
    host_report = os.path.join(tmpdir, "report.sarif")
    cmd = [
        "docker", "run", "--rm",
        "-v", abs_repo + ":/repo:ro",
        "-v", tmpdir + ":/tmp/out",
        _IMAGE, "detect",
        "--source", "/repo",
        "--redact",
        "--no-banner",
        "--no-git",
        "--max-decode-depth=0",
        "--max-target-megabytes=10",
        "--report-format", "sarif",
        "--report-path", "/tmp/out/report.sarif",
        "--exit-code", "1",
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    with open(host_report) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("gitleaks SARIF was not a JSON object")
    return data


def _collect_repo_tokens(repo_dir: str, cap_files: int = 50, cap_bytes: int = 1 << 20) -> set:
    """Collect 8+ char tokens from repo files so planted values can be scrubbed."""
    found: set = set()
    seen = 0
    for root, _dirs, files in os.walk(repo_dir):
        for name in files:
            if seen >= cap_files:
                return found
            seen += 1
            path = os.path.join(root, name)
            try:
                if os.path.getsize(path) > cap_bytes:
                    continue
                with open(path, errors="ignore") as f:
                    text = f.read(cap_bytes)
            except OSError:
                continue
            for tok in _TOKEN_RE.findall(text):
                if len(tok) >= 8:
                    found.add(tok)
            if len(found) > 2000:
                return found
    return found


def _redact_str(text: str, secrets: set) -> tuple:
    count = 0
    for secret in sorted(secrets, key=len, reverse=True):
        if secret and secret in text:
            n = text.count(secret)
            text = text.replace(secret, "***")
            count += n
    text, n = _PREFIX_RE.subn("***", text)
    count += n
    text, n = _ASSIGN_RE.subn(r"\1***", text)
    count += n
    text, n = _LONG_RE.subn("***", text)
    count += n
    return text, count


def _deep_redact(obj, secrets: set) -> tuple:
    if isinstance(obj, str):
        return _redact_str(obj, secrets)
    if isinstance(obj, list):
        total = 0
        out = []
        for item in obj:
            new_item, n = _deep_redact(item, secrets)
            out.append(new_item)
            total += n
        return out, total
    if isinstance(obj, dict):
        total = 0
        out = {}
        for key, val in obj.items():
            new_val, n = _deep_redact(val, secrets)
            out[key] = new_val
            total += n
        return out, total
    return obj, 0


def _result_count(sarif: dict) -> int:
    runs = sarif.get("runs")
    if not isinstance(runs, list):
        return 0
    total = 0
    for run in runs:
        if not isinstance(run, dict):
            continue
        results = run.get("results")
        if isinstance(results, list):
            total += len(results)
    return total


def scan_secrets(repo_dir: str, runner=None) -> dict:
    """Scan repo_dir for leaked secrets. Returns {found, sarif_path, redactions, note}."""
    if not isinstance(repo_dir, str) or not repo_dir.strip():
        raise _err("empty repo_dir", "Pass a local repo directory path. " + _DEMO_HINT)
    if not os.path.isdir(repo_dir):
        raise _err(
            "repo_dir '%s' is not a directory" % repo_dir,
            "Pass an existing local repo directory path. " + _DEMO_HINT,
        )
    try:
        sarif = (runner or _default_runner)(repo_dir)
        if not isinstance(sarif, dict):
            raise ValueError("scanner did not return a SARIF dict")
        secrets = _collect_repo_tokens(repo_dir)
        clean, redactions = _deep_redact(sarif, secrets)
        found = _result_count(clean) > 0
        fd, sarif_path = tempfile.mkstemp(prefix="batongate-secrets-", suffix=".sarif")
        os.close(fd)
        with open(sarif_path, "w") as f:
            json.dump(clean, f)
        return {
            "found": found,
            "sarif_path": sarif_path,
            "redactions": redactions,
            "note": BASE_NOTE,
        }
    except Exception:
        return {
            "found": False,
            "sarif_path": None,
            "redactions": 0,
            "note": BASE_NOTE + " (scanner unavailable, treated as clean)",
        }
