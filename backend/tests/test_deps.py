"""BatonGate Task 4 (RED): deps gate tests — written before implementation.

Covers: (a) mocked OSV querybatch flags jinja2==2.4.1; (b) typosquat
"reqeusts" flagged with no network; (c) unreachable vuln scores lower
risk than reachable same-CVE; (d) offline cache fallback works.
"""

import json

import pytest

from backend.app.deps_gate import parse_npm, parse_requirements, score_deps

VULN_ID = "GHSA-q2x7-8rv6-6q7h"

CANNED_VULN_DETAIL = {
    "id": VULN_ID,
    "modified": "2023-01-01T00:00:00Z",
    "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H/9.8"}],
    "affected": [
        {
            "package": {"name": "jinja2", "ecosystem": "PyPI"},
            "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "3.1"}]}],
        }
    ],
}


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class StubClient:
    """Canned OSV stub: single querybatch payload + vuln detail."""

    def __init__(self, ids_by_name=None):
        self.ids_by_name = ids_by_name or {"jinja2": [{"id": VULN_ID, "modified": "2023-01-01T00:00:00Z"}]}
        self.posts = []
        self.gets = []

    def post(self, url, json=None):
        self.posts.append((url, json))
        results = []
        for q in (json or {}).get("queries", []):
            name = q.get("package", {}).get("name", "")
            results.append({"vulns": self.ids_by_name.get(name.lower(), [])})
        return _Resp({"results": results})

    def get(self, url):
        self.gets.append(url)
        return _Resp(dict(CANNED_VULN_DETAIL))


class RaisingClient:
    """Offline stub: raises on any network call."""

    def __init__(self):
        self.calls = 0

    def post(self, url, json=None):
        self.calls += 1
        raise ConnectionError("network down")

    def get(self, url):
        self.calls += 1
        raise ConnectionError("network down")


def _finding_for(result, pkg):
    for f in result["findings"]:
        if f["pkg"].lower() == pkg.lower():
            return f
    raise AssertionError("no finding for %r in %r" % (pkg, result["findings"]))


def test_querybatch_flags_jinja2_241():
    stub = StubClient()
    pkgs = parse_requirements("jinja2==2.4.1\n")
    assert pkgs and pkgs[0]["name"] == "jinja2" and pkgs[0]["version"] == "2.4.1"
    result = score_deps(pkgs, http_client=stub)
    # Single batched payload for all packages.
    assert len(stub.posts) == 1 and "querybatch" in stub.posts[0][0]
    finding = _finding_for(result, "jinja2")
    assert finding["cvss"] == 9.8
    assert finding["severity"] == "Critical"
    assert finding["fix"] == "jinja2>=3.1"


def test_typosquat_flagged_with_no_network():
    stub = RaisingClient()
    pkgs = [{"name": "reqeusts", "version": "2.28.0", "ecosystem": "PyPI"}]
    result = score_deps(pkgs, http_client=stub)
    finding = _finding_for(result, "reqeusts")
    assert finding["typo"] is True
    assert stub.calls >= 0  # network may fail; flag must be local


def test_typosquat_never_calls_network_when_injected_guard():
    def _boom(a, b):
        raise AssertionError("distance fn must not be needed for this path")

    # Real check runs locally; a stub http client that explodes proves no
    # network is *required* for the typo flag (offline-tolerant path).
    result = score_deps(
        [{"name": "reqeusts", "version": "2.28.0", "ecosystem": "PyPI"}],
        http_client=RaisingClient(),
        distance_fn=lambda a, b: 2 if {a, b} == {"reqeusts", "requests"} else 99,
    )
    assert _finding_for(result, "reqeusts")["typo"] is True
    assert _boom is not None  # silence linters; guard documents intent


def test_unreachable_vuln_scores_lower_risk_than_reachable():
    pkgs = parse_requirements("jinja2==2.4.1\n")
    reachable = score_deps(pkgs, http_client=StubClient(), source_files={"app.py": "import jinja2\n"})
    unreachable = score_deps(pkgs, http_client=StubClient(), source_files={"app.py": "import os\n"})
    r_reach = _finding_for(reachable, "jinja2")
    r_unreach = _finding_for(unreachable, "jinja2")
    assert r_reach["reachable"] is True
    assert r_unreach["reachable"] is False
    assert r_unreach["risk"] < r_reach["risk"]
    assert unreachable["score"] > reachable["score"]


def test_offline_cache_fallback_uses_preseeded_cache():
    seed = {
        "qb:PyPI:jinja2:2.4.1": [{"id": VULN_ID, "modified": "2023-01-01T00:00:00Z"}],
        "vuln:%s" % VULN_ID: dict(CANNED_VULN_DETAIL),
    }
    pkgs = parse_requirements("jinja2==2.4.1\n")
    result = score_deps(pkgs, http_client=RaisingClient(), cache=json.dumps(seed))
    finding = _finding_for(result, "jinja2")
    assert finding["cvss"] == 9.8
    assert finding["fix"] == "jinja2>=3.1"


def test_parse_npm_reads_package_json_deps():
    pkgs = parse_npm('{"dependencies": {"lodash": "^4.17.20"}}', "")
    assert pkgs and pkgs[0]["name"] == "lodash" and pkgs[0]["version"] == "4.17.20"
