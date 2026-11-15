"""BatonGate Task 8: inference summary (summary-only, never gates).

POSTs redacted gate summaries to the Vultr Inference OpenAI-compatible
endpoint with a server-side bearer key and a 10s timeout. Any failure
(missing key, no httpx, timeout, bad response) falls back to a static
template. The client boundary is injectable: pass client(prompt) -> str
in tests to assert single-call + redaction without network.
Python 3.11 compatible; httpx imported lazily.
"""

import os
import re

INFERENCE_URL = "https://api.vultrinference.com/v1/chat/completions"
TIMEOUT_S = 10

SYSTEM_PROMPT = (
    "Summarize gate results in 2 sentences, list fixes. No new verdicts."
)

_STATIC_SHIP = "Ready to ship on Vultr."

_SECRET_RES = [
    re.compile(r"(?i)(api[_-]?key|secret|token|passwd|password)(\s*[:=]\s*)\S+"),
    re.compile(r"ghp_[A-Za-z0-9]+"),
    re.compile(r"gho_[A-Za-z0-9]+"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)\bsk-(live|test)-[A-Za-z0-9_\-]+\b"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"),
]


def redact(text):
    out = text or ""
    out = _SECRET_RES[0].sub(r"\1\2***REDACTED***", out)
    for rx in _SECRET_RES[1:]:
        out = rx.sub("***REDACTED***", out)
    return out


def default_model():
    return (
        os.environ.get("INFERENCE_MODEL")
        or os.environ.get("LLM_MODEL")
        or "deepseek-v4.1-flash-1017"
    )


def build_prompt(gates):
    """Render redacted gate summaries only (names + status + short summary).

    Never includes keys, secrets, or full logs.
    """
    if isinstance(gates, dict):
        items = gates.get("gates", gates)
    else:
        items = gates
    if isinstance(items, dict):
        pairs = sorted(items.items())
    elif isinstance(items, list):
        pairs = [(g.get("name", "?"), g) for g in items if isinstance(g, dict)]
    else:
        pairs = []
    lines = []
    for name, gate in pairs:
        if str(name) in ("exa_links", "voice_transcript", "inference_summary",
                         "artifacts", "job_id", "status", "score", "verdict",
                         "demo_mode"):
            continue
        if not isinstance(gate, dict):
            continue
        status = str(gate.get("status", "?"))
        summary = redact(str(gate.get("summary", ""))[:200])
        lines.append("%s: %s - %s" % (name, status, summary))
    body = "\n".join(lines)[:2000] or "(no gate results)"
    return "Gate results (redacted):\n%s" % body


def _static_summary(gates):
    if isinstance(gates, dict):
        items = gates.get("gates", gates)
    else:
        items = gates
    if isinstance(items, dict):
        entries = list(items.values())
    elif isinstance(items, list):
        entries = items
    else:
        entries = []
    fails = [str(g.get("name", "?")) for g in entries
             if isinstance(g, dict) and str(g.get("status", "")).lower() == "fail"]
    warns = [str(g.get("name", "?")) for g in entries
             if isinstance(g, dict) and str(g.get("status", "")).lower() == "warn"]
    bad = fails + [w for w in warns if w not in fails]
    if not bad:
        return _STATIC_SHIP
    return "Blocked by %s; fix %s and rebuild." % (", ".join(bad), ", ".join(bad))


def _default_client(prompt, model=None, timeout_s=TIMEOUT_S, api_key=None):
    """Single POST to Vultr Inference; raises on any failure."""
    try:
        import httpx
    except ImportError:
        raise RuntimeError("httpx is not installed")
    key = api_key if api_key is not None else (
        os.environ.get("VULTR_INFERENCE_API_KEY") or os.environ.get("LLM_API_KEY") or "")
    if not key:
        raise RuntimeError("no inference API key configured")
    resp = httpx.post(
        INFERENCE_URL,
        headers={"Authorization": "Bearer " + key},
        json={"model": model or default_model(),
              "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt}]},
        timeout=timeout_s,
    )
    resp.raise_for_status()
    data = resp.json()
    return str(data["choices"][0]["message"]["content"])


def summarize(redacted_gates, client=None, model=None, timeout_s=TIMEOUT_S,
              _env_key=None):
    """Summarize gate results; exactly one client call; static fallback.

    client: optional f(prompt) -> str (stub-injectable). client=None uses
    the default HTTP client (key from env). _env_key overrides the env key
    lookup (tests pass "" to force the static path without network).
    """
    prompt = build_prompt(redacted_gates)
    try:
        if client is not None:
            text = client(prompt)
        else:
            key = _env_key if _env_key is not None else (
                os.environ.get("VULTR_INFERENCE_API_KEY")
                or os.environ.get("LLM_API_KEY") or "")
            text = _default_client(prompt, model=model, timeout_s=timeout_s,
                                   api_key=key)
        text = redact(str(text or "").strip())
        return text if text else _static_summary(redacted_gates)
    except Exception:
        return _static_summary(redacted_gates)
