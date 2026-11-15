"""BatonGate Task 8: voice gate (OPTIONAL input only, never verdict).

transcribe(audio_b64, client=None) -> {"transcript": str | None}.
Never raises: missing audio, missing client/key, or any failure returns
{"transcript": None} so text input always works and voice never blocks.
Python 3.11 compatible, stdlib only at import.
"""

import os


def _default_client(audio_b64, api_key=None, api_url=None, timeout_s=15):
    """Best-effort Wispr REST call; raises when unavailable."""
    key = api_key if api_key is not None else os.environ.get("WISPR_API_KEY", "")
    if not key:
        raise RuntimeError("no Wispr API key configured")
    url = api_url or os.environ.get("WISPR_API_URL", "")
    if not url:
        raise RuntimeError("no Wispr API URL configured")
    try:
        import httpx
    except ImportError:
        raise RuntimeError("httpx is not installed")
    resp = httpx.post(url,
                      headers={"Authorization": "Bearer " + key},
                      json={"audio_b64": audio_b64},
                      timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json()
    return data.get("transcript")


def transcribe(audio_b64, client=None):
    """Transcribe base64 wav audio; never raises, None on any failure."""
    try:
        if not audio_b64:
            return {"transcript": None}
        if client is None:
            text = _default_client(audio_b64)
        else:
            text = client(audio_b64)
        if not text or not str(text).strip():
            return {"transcript": None}
        return {"transcript": str(text)}
    except Exception:
        return {"transcript": None}
