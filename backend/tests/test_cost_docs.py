"""BatonGate Task 6 (RED): docs + cost gate tests — written before implementation.

Covers: (a) stale endpoint flagged with file+line+offset; (b) no-evidence
input refused; (c) idle instance + unattached volume flagged with $ math
(stub Vultr client, canned instances/sizes); (d) demo=1 synthetic works with
no key / client failure; (e) text-input path works with no audio (no
voice_gate module — Task 8 owns voice).
"""

import pytest

from backend.app.cost_gate import estimate_cost
from backend.app.docs_gate import check_docs

DIFF_STALE = """\
--- a/src/app.py
+++ b/src/app.py
@@ -10,7 +10,7 @@
-GET /health
+GET /healthz
"""

README_STALE = """\
# Demo

Run a check:

GET /health
""".lstrip()


class StubVultrClient:
    """Canned read-only Vultr stub: 1 idle instance + 1 unattached volume."""

    def list_instances(self):
        return [{"id": "inst-1", "label": "web", "plan": "vc2-1c-2gb",
                 "cpu_recent_percent": 2.0}]

    def list_sizes(self):
        return [{"id": "vc2-1c-2gb", "price_per_month": 12.0},
                {"id": "vc2-1c-1gb", "price_per_month": 6.0}]

    def list_volumes(self):
        return [{"id": "vol-1", "label": "data", "size_gb": 10,
                 "monthly_price": 1.0, "attached_to": None}]


class FailingVultrClient:
    def list_instances(self):
        raise RuntimeError("no key / offline")

    def list_sizes(self):
        raise RuntimeError("no key / offline")

    def list_volumes(self):
        raise RuntimeError("no key / offline")


def test_docs_stale_endpoint_flagged():
    result = check_docs(DIFF_STALE, README_STALE)
    assert "stale" in result and not result.get("refused", False)
    assert len(result["stale"]) >= 1
    entry = result["stale"][0]
    for key in ("file", "line", "offset", "expected", "found",
                "proposed_patch"):
        assert key in entry, "missing key %r in %r" % (key, entry)
    assert entry["found"] == "/health"
    assert entry["expected"] == "/healthz"
    assert isinstance(entry["line"], int) and entry["line"] >= 1
    assert isinstance(entry["offset"], int) and entry["offset"] >= 0


def test_docs_no_evidence_refused():
    result = check_docs("", "")
    assert result.get("refused") is True
    assert result.get("reason")


def test_cost_idle_and_unattached_volume_flagged():
    result = estimate_cost(vultr_client=StubVultrClient())
    assert result["current"] == pytest.approx(13.0)
    assert result["simulated"] == pytest.approx(6.0)
    assert result["saved"] == pytest.approx(7.0)
    assert result["downgrade_cmd"]
    assert result["demo"] is False


def test_cost_demo_synthetic_without_key():
    result = estimate_cost(vultr_client=FailingVultrClient(), demo=True)
    assert result["demo"] is True
    assert result["current"] > 0
    assert result["simulated"] <= result["current"]
    assert result["saved"] == pytest.approx(result["current"] - result["simulated"])
    assert "co2_kg" in result and result["co2_kg"] >= 0


def test_text_input_works_with_no_audio():
    """Mocked voice-transcript path: no audio → transcript None, input kept.

    No voice_gate module involved (Task 8 owns voice); the stub resolver
    lives here to pin the text-always-works contract.
    """

    def _resolve_input(text_input, voice_fn=None, audio_b64=None):
        if audio_b64 is None or voice_fn is None:
            return {"repo_url": text_input, "voice_transcript": None}
        return {"repo_url": voice_fn(audio_b64) or text_input,
                "voice_transcript": voice_fn(audio_b64)}

    out = _resolve_input("https://github.com/owner/repo")
    assert out == {"repo_url": "https://github.com/owner/repo",
                   "voice_transcript": None}
