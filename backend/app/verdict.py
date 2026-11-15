"""BatonGate Task 8: verdict — score + SHIP/FIX/BLOCKED from the 5 core gates.

BLOCKING (any one -> BLOCKED): secrets evidence found, build failure
(built False / healthz fail, unless explicitly skipped), critical+reachable
CVE in deps findings. Everything else is score-weighted SHIP/FIX.
Exa/Wispr/Inference extras are accepted but never change the verdict.
Scores are bounds-clamped to 0-100; adversarial inputs never raise.
Python 3.11 compatible, stdlib only.
"""

CORE_GATES = ("secrets", "deps", "docs", "cost", "build")


def _num(value, default=100.0):
    """Coerce to a 0-100 float; non-numeric/NaN/inf -> default (clamped)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return max(0.0, min(100.0, number))


def _status(gate):
    if isinstance(gate, dict):
        return str(gate.get("status", "warn") or "warn").lower()
    return "warn"


def _evidence(gate):
    if isinstance(gate, dict) and isinstance(gate.get("evidence"), dict):
        return gate["evidence"]
    return {}


def _gate_score(name, gate):
    """Per-gate 0-100 contribution (already clamped)."""
    ev = _evidence(gate)
    status = _status(gate)
    if name == "secrets":
        return 0.0 if ev.get("found") is True else 100.0
    if name == "deps":
        if "score" in ev:
            return _num(ev.get("score"), default=60.0)
        return {"pass": 100.0, "warn": 60.0, "fail": 0.0}.get(status, 60.0)
    if name == "docs":
        if isinstance(ev.get("stale"), list) and ev["stale"]:
            return 70.0
        return {"pass": 100.0, "refused": 85.0, "warn": 70.0,
                "fail": 40.0}.get(status, 85.0)
    if name == "cost":
        return 100.0  # informational only
    if name == "build":
        if ev.get("skipped") is True:
            return 70.0
        if ev.get("built") is True and ev.get("healthz") == "pass":
            return 100.0
        if status == "warn":
            return 60.0
        return 0.0
    return 60.0


def _blocking(gates):
    """Return a blocking reason string, or None."""
    secrets_ev = _evidence(gates.get("secrets"))
    if secrets_ev.get("found") is True:
        return "secret found"
    build_ev = _evidence(gates.get("build"))
    if build_ev.get("skipped") is not True:
        if build_ev.get("built") is False or build_ev.get("healthz") == "fail":
            return "build failed"
        if _status(gates.get("build")) == "fail":
            return "build failed"
    deps_ev = _evidence(gates.get("deps"))
    findings = deps_ev.get("findings")
    if isinstance(findings, list):
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            try:
                cvss = float(finding.get("cvss", 0.0) or 0.0)
            except (TypeError, ValueError):
                cvss = 0.0
            severity = str(finding.get("severity", "") or "").lower()
            critical = severity == "critical" or cvss >= 9.0
            if critical and finding.get("reachable") is True:
                return "critical reachable CVE"
    return None


def _as_dict(gates):
    """Accept {name: gate} or [{name, ...}] — extras pass through untouched."""
    if isinstance(gates, dict):
        return dict(gates)
    out = {}
    if isinstance(gates, list):
        for gate in gates:
            if isinstance(gate, dict) and gate.get("name"):
                out[str(gate["name"])] = gate
    return out


def decide(gates):
    """Decide {score 0-100, verdict SHIP|FIX|BLOCKED} from core gate results.

    Extra keys (exa_links, voice_transcript, inference_summary) are ignored.
    Never raises on adversarial input.
    """
    try:
        gates = _as_dict(gates)
    except Exception:
        gates = {}
    reason = _blocking(gates)
    scores = [_gate_score(name, gates.get(name)) for name in CORE_GATES]
    score = int(round(sum(scores) / len(scores)))
    score = max(0, min(100, score))
    if reason is not None:
        verdict = "BLOCKED"
    elif score >= 80 and all(_status(gates.get(n)) != "fail" for n in CORE_GATES):
        verdict = "SHIP"
    else:
        verdict = "FIX"
    return {"score": score, "verdict": verdict}
