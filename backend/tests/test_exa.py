"""BatonGate Task 5 (RED): Exa fix-evidence — stubbed search, fallback, no-key skip."""

from backend.app import exa_gate


def _stub_search_ok(query, **kwargs):
    assert "CVE-2024-1234" in query
    return [
        {"url": "https://example.com/fix1", "title": "Fix 1",
         "highlights": ["h1", "h2"]},
        {"url": "https://example.com/fix2", "title": "Fix 2",
         "highlights": ["h3", "h4"]},
    ]


def test_fix_links_returns_two_links_with_highlights():
    out = exa_gate.fix_links("CVE-2024-1234", api_key="k",
                             search_fn=_stub_search_ok)
    assert len(out) == 2
    for item in out:
        assert item["url"] and item["title"]
        assert len(item["highlights"]) == 2


def _stub_search_boom(query, **kwargs):
    raise TimeoutError("exa down")


def test_timeout_falls_back_to_osv_fixed():
    out = exa_gate.fix_links("CVE-2024-1234", api_key="k",
                             search_fn=_stub_search_boom,
                             fixed_fallback="jinja2>=3.1")
    assert out == [{"url": "", "title": "jinja2>=3.1", "highlights": []}] or out == "jinja2>=3.1" or (
        len(out) == 1 and "jinja2>=3.1" in str(out[0]))


def test_no_key_returns_empty_without_calling():
    called = []

    def _should_not_run(query, **kwargs):
        called.append(query)
        return [{"url": "x", "title": "y", "highlights": ["a", "b"]}]

    out = exa_gate.fix_links("CVE-2024-1234", api_key=None,
                             search_fn=_should_not_run)
    assert out == []
    assert called == []
