"""BatonGate Task 3: secrets gate tests (TDD RED first).

Scanner is FAKED via injection: scan_secrets(repo_dir, runner=...)
with a stub runner returning a canned SARIF dict. No docker in tests.
"""

import json

import pytest

from backend.app.secrets_gate import scan_secrets

FAKE_SECRET = "ghp_fakesecretvalue1234567890abcdef"


def _canned_sarif_with_secret():
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [
            {
                "tool": {"driver": {"name": "gitleaks"}},
                "results": [
                    {
                        "ruleId": "gitleaks/generic-api-key",
                        "message": {"text": "found API_KEY=%s in config" % FAKE_SECRET},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": ".env"},
                                    "region": {"snippet": {"text": "API_KEY=%s" % FAKE_SECRET}},
                                }
                            }
                        ],
                    }
                ],
            }
        ],
    }


def _canned_clean_sarif():
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{"tool": {"driver": {"name": "gitleaks"}}, "results": []}],
    }


def test_planted_fake_key_is_found_and_redacted(tmp_path):
    (tmp_path / ".env").write_text("API_KEY=%s\n" % FAKE_SECRET)
    result = scan_secrets(str(tmp_path), runner=lambda repo_dir: _canned_sarif_with_secret())
    assert result["found"] is True
    assert FAKE_SECRET not in str(result), "raw secret leaked in result"
    assert result["redactions"] >= 1
    assert "potential exposure, not verified active key" in result["note"]
    # SARIF artifact on disk is valid JSON and also redacted
    assert result["sarif_path"]
    raw = open(result["sarif_path"]).read()
    assert FAKE_SECRET not in raw, "raw secret leaked in SARIF file"
    data = json.loads(raw)
    assert isinstance(data["runs"], list) and data["runs"]
    assert isinstance(data["runs"][0]["results"], list) and data["runs"][0]["results"]


def test_clean_dir_passes(tmp_path):
    (tmp_path / "README.md").write_text("hello world\n")
    result = scan_secrets(str(tmp_path), runner=lambda repo_dir: _canned_clean_sarif())
    assert result["found"] is False
    assert result["sarif_path"]


def test_sarif_file_parses_with_runs_results(tmp_path):
    (tmp_path / ".env").write_text("API_KEY=%s\n" % FAKE_SECRET)
    result = scan_secrets(str(tmp_path), runner=lambda repo_dir: _canned_sarif_with_secret())
    with open(result["sarif_path"]) as f:
        sarif_log = json.load(f)
    entries = sarif_log["runs"][0]["results"]
    assert isinstance(entries, list) and len(entries) >= 1


def test_misuse_raises_400_style_value_error():
    with pytest.raises(ValueError) as exc:
        scan_secrets("")
    payload = exc.value.args[0]
    assert "error" in payload and "fix_hint" in payload
