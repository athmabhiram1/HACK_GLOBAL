import pytest

from backend.app.parsers import (
    assert_no_submodules,
    check_repo_size,
    parse_all,
    parse_compose,
    parse_dockerfile,
    parse_env,
    parse_repo_input,
)


def test_valid_github_url_parses():
    assert parse_repo_input("https://github.com/owner/repo") == {
        "host": "github.com",
        "owner": "owner",
        "repo": "repo",
    }


def test_rejects_non_allowlist_host():
    with pytest.raises(ValueError) as e:
        parse_repo_input("https://evil.com/owner/repo")
    assert "allowlist" in str(e.value.args[0]["error"])


def test_rejects_plain_http_even_on_github():
    with pytest.raises(ValueError):
        parse_repo_input("http://github.com/owner/repo")


def test_rejects_file_scheme():
    with pytest.raises(ValueError):
        parse_repo_input("file:///etc/passwd")


def test_rejects_arg_starting_with_dash():
    with pytest.raises(ValueError) as e:
        parse_repo_input("--upload-pack=touch pwned")
    assert "fix_hint" in e.value.args[0]


def test_detects_missing_expose():
    assert parse_dockerfile("FROM python:3.12-slim\nCMD foo\n")["missing_expose"] is True


def test_detects_hardcoded_localhost_3000():
    refs = parse_compose('ports:\n  - "3000:80"\n  url: http://localhost:3000/api')["localhost_refs"]
    assert any("localhost:3000" in r for r in refs)


def test_detects_127_0_0_1_as_localhost_ref():
    assert parse_env("API=http://127.0.0.1:8000/x")["localhost_refs"] != []


def test_detects_latest_tag():
    assert parse_dockerfile("FROM python:latest\nEXPOSE 8000\n")["latest_tag"] is True


def test_rejects_submodule_ref():
    with pytest.raises(ValueError):
        assert_no_submodules('[submodule "x"]\npath = x')


def test_rejects_oversize_signal():
    with pytest.raises(ValueError):
        check_repo_size(60 * 1024 * 1024)
    check_repo_size(10 * 1024 * 1024)  # under limit passes


def test_parse_all_matches_broken_fixture():
    with open("samples/broken-dockerfile/Dockerfile") as f:
        df = f.read()
    with open("samples/broken-dockerfile/compose.yaml") as f:
        co = f.read()
    out = parse_all(dockerfile_text=df, compose_text=co)
    assert out["missing_expose"] is True
    assert out["latest_tag"] is True
    assert out["localhost_refs"] != []
