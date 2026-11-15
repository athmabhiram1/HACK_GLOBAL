"""BatonGate Task 4: deps gate (OSV + typosquat + reachability).

Pure functions + injectable boundaries (mirrors secrets_gate runner-stub
pattern). stdlib only at import; httpx used lazily by the default HTTP
client. Python 3.11 compatible.

Entry: score_deps(packages, source_files={}, http_client=None,
                  distance_fn=None, cache=None, cache_ttl_s=86400)
  packages: list of {name, version, ecosystem?} or requirements.txt text.
  Returns {score 0-100, findings[{pkg, version, ecosystem, severity, cvss,
  reachable, typo, fix, risk}]}.
"""

import ast
import json
import re
import time

try:
    import httpx  # type: ignore
except ImportError:  # pragma: no cover - offline envs
    httpx = None

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_VULN_URL = "https://api.osv.dev/v1/vulns/{vid}"
CACHE_TTL_S = 86400
MAX_VULN_DETAIL = 5

_HOMOGLYPH = {
    "0": "o", "1": "l", "@": "a", "$": "s", "3": "e",
    "!": "i", "5": "s", "8": "b", "6": "g", "9": "g",
}

# Popular-package guard list for typosquat comparison (subset of top-200).
TOP_PACKAGES = frozenset({
    "requests", "urllib3", "numpy", "pandas", "flask", "django",
    "fastapi", "jinja2", "sqlalchemy", "pytest", "pip", "setuptools",
    "click", "redis", "celery", "pillow", "matplotlib", "scipy",
    "tensorflow", "torch", "express", "lodash", "react", "axios",
    "typescript", "webpack", "chalk", "commander", "debug", "moment",
    "async", "vue", "body-parser", "cors", "dotenv", "jsonwebtoken",
    "mongoose", "nodemon", "prop-types", "redux", "socketio",
})

_REQ_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([A-Za-z0-9_.\-+*!]+)")
_PY_IMPORT_RE = re.compile(r"^\s*(?:import\s+([\w\.]+)|from\s+([\w\.]+)\s+import\s+)", re.MULTILINE)
_JS_IMPORT_RE = re.compile(
    r"""require\(\s*['"]([^'"]+)['"]\s*\)|import\s+(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]"""
)
_CVSS_RE = re.compile(r"/(\d+(?:\.\d+)?)\s*$")


def normalize(name):
    """Lowercase, strip -_, apply homoglyph map."""
    text = (name or "").lower().replace("-", "").replace("_", "")
    return "".join(_HOMOGLYPH.get(ch, ch) for ch in text)


def _pure_levenshtein(a, b):
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[len(b)]


def default_distance(a, b):
    """Levenshtein via C-extension when installed, else pure-python."""
    try:
        import Levenshtein  # type: ignore
        return Levenshtein.distance(a, b)
    except ImportError:
        return _pure_levenshtein(a, b)


def typo_check(name, distance_fn=None):
    """Return (is_typo, target). Exact popular names are not typos."""
    dist = distance_fn or default_distance
    norm = normalize(name)
    for popular in TOP_PACKAGES:
        if norm == normalize(popular):
            return False, None
    best = None
    for popular in TOP_PACKAGES:
        if abs(len(norm) - len(popular)) > 2:
            continue
        if dist(norm, popular) <= 2:
            if best is None or popular < best:
                best = popular
    return (best is not None), best


def parse_requirements(text):
    """Parse requirements.txt == pins (packaging-free regex)."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        m = _REQ_RE.match(line.split(";")[0].strip().rstrip("\\").strip())
        if m:
            out.append({"name": m.group(1), "version": m.group(2), "ecosystem": "PyPI"})
    return out


def _strip_spec(version):
    return re.sub(r"^[\^~>=<!\s]+", "", (version or "").strip()).split()[0] if version else ""


def parse_npm(package_json_text, lock_text):
    """Parse package.json deps + package-lock versions (no install)."""
    merged = {}
    try:
        data = json.loads(package_json_text or "{}")
    except ValueError:
        data = {}
    for section in ("dependencies", "devDependencies"):
        deps = data.get(section)
        if isinstance(deps, dict):
            for name, spec in deps.items():
                merged.setdefault(name, _strip_spec(str(spec)))
    try:
        lock = json.loads(lock_text or "{}")
    except ValueError:
        lock = {}
    packages = lock.get("packages")
    if isinstance(packages, dict):
        for key, entry in packages.items():
            if key.startswith("node_modules/") and isinstance(entry, dict):
                name = key[len("node_modules/"):]
                if "/" not in name and entry.get("version"):
                    merged[name] = merged.get(name) or str(entry["version"])
    deps_lock = lock.get("dependencies")
    if isinstance(deps_lock, dict):
        for name, entry in deps_lock.items():
            if isinstance(entry, dict) and entry.get("version"):
                merged[name] = merged.get(name) or str(entry["version"])
    return [{"name": n, "version": v, "ecosystem": "npm"} for n, v in sorted(merged.items())]


def _py_imports(source):
    found = set()
    try:
        tree = ast.parse(source or "")
    except (SyntaxError, ValueError):
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module.split(".")[0])
        return found
    for m in _PY_IMPORT_RE.finditer(source or ""):
        mod = m.group(1) or m.group(2)
        if mod:
            found.add(mod.split(".")[0])
    return found


def _js_imports(source):
    found = set()
    for m in _JS_IMPORT_RE.finditer(source or ""):
        mod = m.group(1) or m.group(2)
        if mod and not mod.startswith(".") and not mod.startswith("/"):
            found.add(mod.split("/")[0].lower())
    return found


def reachable_packages(source_files):
    """Collect imported top-level module names from a {path: content} tree."""
    found = set()
    for path, content in (source_files or {}).items():
        text = content or ""
        if str(path).endswith((".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs")):
            found |= _js_imports(text)
        else:
            found |= _py_imports(text)
    return {normalize(m) for m in found}


def _cvss_from_detail(detail):
    for sev in (detail or {}).get("severity", []) or []:
        if not isinstance(sev, dict):
            continue
        if "CVSS" in str(sev.get("type", "")).upper():
            m = _CVSS_RE.search(str(sev.get("score", "")))
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    pass
    return 0.0


def _fixed_for(detail, pkg, ecosystem):
    for aff in (detail or {}).get("affected", []) or []:
        if not isinstance(aff, dict):
            continue
        for rng in aff.get("ranges", []) or []:
            for ev in (rng or {}).get("events", []) or []:
                if isinstance(ev, dict) and ev.get("fixed"):
                    return "%s>=%s" % (pkg, ev["fixed"])
    return ""


def severity_for(cvss):
    if cvss >= 9.0:
        return "Critical"
    if cvss >= 7.0:
        return "High"
    if cvss >= 4.0:
        return "Medium"
    if cvss > 0:
        return "Low"
    return "Unknown"


def _norm_cache(cache):
    if cache is None:
        return {}
    if isinstance(cache, str):
        try:
            data = json.loads(cache)
        except ValueError:
            return {}
        return dict(data) if isinstance(data, dict) else {}
    return cache


def _cache_get(cache, key, now, ttl_s):
    if key not in cache:
        return None, False
    entry = cache[key]
    if isinstance(entry, dict) and "value" in entry and "ts" in entry:
        try:
            if now - float(entry["ts"]) > ttl_s:
                return None, False
        except (TypeError, ValueError):
            pass
        return entry["value"], True
    return entry, True


def _cache_set(cache, key, value, now):
    try:
        cache[key] = {"value": value, "ts": now}
    except TypeError:
        pass


class _DefaultHttpClient:
    def __init__(self, timeout_s=10):
        self._timeout_s = timeout_s

    def post(self, url, json=None):
        if httpx is None:
            raise RuntimeError("httpx is not installed")
        resp = httpx.post(url, json=json, timeout=self._timeout_s)
        resp.raise_for_status()
        return resp

    def get(self, url):
        if httpx is None:
            raise RuntimeError("httpx is not installed")
        resp = httpx.get(url, timeout=self._timeout_s)
        resp.raise_for_status()
        return resp


def _qb_key(pkg):
    return "qb:%s:%s:%s" % (pkg.get("ecosystem", "PyPI"), pkg.get("name", ""), pkg.get("version", ""))


def _querybatch(packages, http_client, cache, now, ttl_s):
    """Single batched OSV query; returns {index: [vuln ids]}. Offline-safe."""
    cached = {}
    missing = []
    for i, pkg in enumerate(packages):
        val, hit = _cache_get(cache, _qb_key(pkg), now, ttl_s)
        if hit:
            cached[i] = val or []
        else:
            missing.append((i, pkg))
    if missing and http_client is not None:
        payload = {
            "queries": [
                {
                    "package": {"name": p.get("name", ""), "ecosystem": p.get("ecosystem", "PyPI")},
                    "version": p.get("version", ""),
                }
                for _, p in missing
            ]
        }
        try:
            resp = http_client.post(OSV_BATCH_URL, json=payload)
            results = resp.json().get("results", [])
        except Exception:
            results = []
        for (i, pkg), res in zip(missing, results + [{}] * len(missing)):
            vulns = (res or {}).get("vulns", []) or []
            ids = [{"id": v.get("id"), "modified": v.get("modified", "")} for v in vulns if v.get("id")]
            cached[i] = ids
            _cache_set(cache, _qb_key(pkg), ids, now)
    for i, _ in missing:
        cached.setdefault(i, [])
    return cached


def _vuln_detail(vid, http_client, cache, now, ttl_s):
    val, hit = _cache_get(cache, "vuln:%s" % vid, now, ttl_s)
    if hit:
        return val or {}
    detail = {}
    if http_client is not None:
        try:
            detail = http_client.get(OSV_VULN_URL.format(vid=vid)).json() or {}
        except Exception:
            detail = {}
    if detail:
        _cache_set(cache, "vuln:%s" % vid, detail, now)
    return detail


def _risk(cvss, reachable, typo):
    return 0.6 * (min(max(cvss, 0.0), 10.0) / 10.0) + 0.3 * (1.0 if reachable else 0.0) + 0.1 * (1.0 if typo else 0.0)


def score_deps(packages, source_files=None, http_client=None, distance_fn=None,
               cache=None, cache_ttl_s=CACHE_TTL_S, max_vuln_detail=MAX_VULN_DETAIL):
    """Score parsed deps → {score 0-100, findings[]}. Never raises on OSV failure."""
    if isinstance(packages, str):
        packages = parse_requirements(packages)
    packages = list(packages or [])
    sources = source_files if source_files is not None else {}
    imported = reachable_packages(sources)
    store = _norm_cache(cache)
    client = http_client if http_client is not None else _DefaultHttpClient()
    id_map = _querybatch(packages, client, store, time.time(), cache_ttl_s)

    findings = []
    worst = 0.0
    for i, pkg in enumerate(packages):
        name = pkg.get("name", "")
        version = pkg.get("version", "")
        eco = pkg.get("ecosystem", "PyPI")
        is_typo, _target = typo_check(name, distance_fn)
        is_reach = normalize(name) in imported
        vulns = id_map.get(i, [])[:max_vuln_detail]
        if vulns:
            for v in vulns:
                detail = _vuln_detail(v.get("id"), client, store, time.time(), cache_ttl_s)
                cvss = _cvss_from_detail(detail)
                risk = _risk(cvss, is_reach, is_typo)
                worst = max(worst, risk)
                findings.append({
                    "pkg": name, "version": version, "ecosystem": eco,
                    "id": v.get("id", ""), "severity": severity_for(cvss),
                    "cvss": cvss, "reachable": is_reach, "typo": is_typo,
                    "fix": _fixed_for(detail, name, eco), "risk": round(risk, 4),
                })
        else:
            risk = _risk(0.0, is_reach, is_typo)
            if is_typo or is_reach:
                worst = max(worst, risk)
                findings.append({
                    "pkg": name, "version": version, "ecosystem": eco,
                    "id": "", "severity": "Unknown", "cvss": 0.0,
                    "reachable": is_reach, "typo": is_typo,
                    "fix": "", "risk": round(risk, 4),
                })
    return {"score": int(round(100 * (1.0 - worst))), "findings": findings}
