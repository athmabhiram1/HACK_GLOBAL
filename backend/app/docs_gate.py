"""BatonGate Task 6: docs gate (diff vs README, no network, no LLM decision).

check_docs(diff_text, readme_text) -> {stale:[...] | refused:True, reason}
Stale entry: {file, line, startColumn, offset, expected, found,
proposed_patch}. Pure functions, stdlib only, Python 3.11 compatible.
"""

import re

_ENDPOINT_RE = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[^\s\"'`]*)"
)

_REFUSED_REASON = "no evidence: empty diff and readme (refusing, not guessing)"


def _endpoints(lines):
    """Yield (method, path) pairs found in the given lines."""
    for line in lines:
        for m in _ENDPOINT_RE.finditer(line or ""):
            yield m.group(1), m.group(2)


def check_docs(diff_text, readme_text):
    """Flag endpoints removed in the diff but still documented in the readme."""
    diff_text = diff_text or ""
    readme_text = readme_text or ""
    if not diff_text.strip() and not readme_text.strip():
        return {"refused": True, "reason": _REFUSED_REASON}

    removed, added = [], []
    for line in diff_text.splitlines():
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-"):
            removed.extend(_endpoints([line[1:]]))
        elif line.startswith("+"):
            added.extend(_endpoints([line[1:]]))

    added_paths = {path for _, path in added}
    readme_lines = readme_text.splitlines()
    stale = []
    for method, found in removed:
        # A removal counts as stale only if a new endpoint was added and the
        # old one is still documented (i.e. docs lag the code change).
        if found in added_paths:
            continue
        expected = None
        for _, path in added:
            if path != found:
                expected = path
                break
        if expected is None:
            continue
        for lineno, rline in enumerate(readme_lines, 1):
            col = rline.find(found)
            if col == -1:
                continue
            offset = sum(len(l) + 1 for l in readme_lines[:lineno - 1]) + col
            stale.append({
                "file": "README.md",
                "line": lineno,
                "startColumn": col + 1,
                "offset": offset,
                "expected": expected,
                "found": found,
                "proposed_patch": rline.replace(found, expected),
            })
    return {"stale": stale}
