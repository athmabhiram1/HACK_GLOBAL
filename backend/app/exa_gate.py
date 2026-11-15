"""BatonGate Task 5: Exa fix-evidence (OPTIONAL extra, never gates).

Caller is responsible for max 1 call per critical CVE (cap calls/job to
protect the $20 Exa credit budget). Missing key or any failure returns []
(or [fixed_fallback] entry when given); the verdict/score is never changed.

stdlib only at module import; exa-py is lazily imported inside the default
search path and only when api_key is present. No network in tests — inject
search_fn.
"""


def _normalize(items, max_results):
    out = []
    for raw in (items or [])[:max_results]:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url", "") or "")
        title = str(raw.get("title", "") or "")
        hl = raw.get("highlights", []) or []
        hl = [str(h) for h in hl if h][:2]
        if url or title:
            out.append({"url": url, "title": title, "highlights": hl})
    return out


def _default_search(query, api_key, timeout_s, max_results):
    """Shell to exa-py. Raises (incl. ImportError) when unavailable."""
    import exa_py  # lazy: stdlib-only at module import

    client = exa_py.Exa(api_key)
    kwargs = {"type": "auto", "contents": {"highlights": True},
              "num_results": max_results}
    try:
        res = client.search(query, timeout=timeout_s, **kwargs)
    except TypeError:
        res = client.search(query, **kwargs)
    results = getattr(res, "results", res)
    if isinstance(results, dict):
        results = results.get("results", [])
    items = []
    for r in results or []:
        if isinstance(r, dict):
            items.append({"url": r.get("url", ""), "title": r.get("title", ""),
                          "highlights": r.get("highlights", []) or []})
        else:
            items.append({"url": getattr(r, "url", ""),
                          "title": getattr(r, "title", ""),
                          "highlights": getattr(r, "highlights", []) or []})
    return items


def fix_links(cve_id, api_key=None, search_fn=None, fixed_fallback=None,
              timeout_s=10, max_results=2):
    """Return [{url, title, highlights[2]}] for a CVE, or fallback/[].

    - api_key None/empty → [] without calling anything.
    - Any exception/timeout from the search → [fixed_fallback entry]
      when fixed_fallback is given, else [].
    - Never affects any score; extras only.
    """
    if not api_key:
        return []
    if not cve_id:
        return []
    query = "fix " + str(cve_id)
    try:
        if search_fn is not None:
            raw = search_fn(query, type="auto",
                            contents={"highlights": True},
                            num_results=max_results, timeout=timeout_s)
        else:
            raw = _default_search(query, api_key, timeout_s, max_results)
        return _normalize(raw, max_results)
    except Exception:
        if fixed_fallback:
            return [{"url": "", "title": str(fixed_fallback),
                     "highlights": []}]
        return []
