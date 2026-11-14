"""BatonGate Task 2: repo intake + static parsers (pure functions only).

No network, no clone, no eval. Python 3.11 compatible.
Validation failures raise ValueError carrying a 400-style dict:
{"error": <short reason>, "fix_hint": <how to fix + demo suggestion>}.
"""

import re
from urllib.parse import urlparse

ALLOWED_HOSTS = frozenset({"github.com", "gitlab.com"})

MAX_SIZE_MB = 50

_DEMO_HINT = "Try one of the sample repos or re-run with ?demo=1 (DEMO REPLAY)."

_LOCALHOST_RE = re.compile(
    r"(localhost(?::\d+)?(?:/[^\s\"']*)?|127\.0\.0\.1(?::\d+)?(?:/[^\s\"']*)?)"
)
_EXPOSE_RE = re.compile(r"^\s*EXPOSE\b", re.IGNORECASE | re.MULTILINE)
_EXPOSE_PORTS_RE = re.compile(r"^\s*EXPOSE\s+(.+)$", re.IGNORECASE | re.MULTILINE)
_FROM_RE = re.compile(r"^\s*FROM\s+(?:--\S+\s+)*(\S+)", re.IGNORECASE | re.MULTILINE)
_COMPOSE_IMAGE_RE = re.compile(r"^\s*image\s*:\s*(\S+)\s*$", re.IGNORECASE | re.MULTILINE)
_PORT_MAPPING_RE = re.compile(r'"?(\d{1,5})\s*:\s*(\d{1,5})"?')


def _err(error: str, fix_hint: str) -> ValueError:
    return ValueError({"error": error, "fix_hint": fix_hint})


def parse_repo_input(url: str) -> dict:
    """Validate a pasted repo URL against the allowlist.

    Returns {"host", "owner", "repo"} or raises ValueError({error, fix_hint}).
    """
    if not isinstance(url, str) or not url.strip():
        raise _err("empty repo_url", "Paste an https://github.com/owner/repo URL. " + _DEMO_HINT)
    text = url.strip()
    if text.startswith("-"):
        raise _err(
            "repo_url must not start with '-'",
            "Remove the leading dash (option-injection guard). " + _DEMO_HINT,
        )
    if not text.startswith("https://"):
        raise _err(
            "only https:// repo URLs are accepted",
            "Re-paste the repo as https://github.com/owner/repo (or gitlab.com). "
            + _DEMO_HINT,
        )
    try:
        parsed = urlparse(text)
    except Exception:
        raise _err("unparseable repo_url", "Check the URL for typos. " + _DEMO_HINT)
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise _err(
            "host '%s' is not allowlisted (github.com, gitlab.com only)" % host,
            "Use a github.com or gitlab.com repo URL. " + _DEMO_HINT,
        )
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise _err(
            "repo_url must look like https://<host>/<owner>/<repo>",
            "Copy the full repo path, e.g. https://github.com/owner/repo. " + _DEMO_HINT,
        )
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    return {"host": host, "owner": parts[0], "repo": repo}


def _localhost_refs(text: str) -> list:
    return sorted(set(_LOCALHOST_RE.findall(text or "")))


def parse_dockerfile(text: str) -> dict:
    """Parse Dockerfile text: latest-tag, EXPOSE, ports, localhost refs."""
    text = text or ""
    base_image = None
    latest_tag = False
    for m in _FROM_RE.finditer(text):
        image = m.group(1)
        if base_image is None:
            base_image = image
        name = image.split("@")[0]  # strip digest pin
        if ":" not in name:
            latest_tag = True  # untagged FROM implies latest
        elif name.rsplit(":", 1)[1].lower() == "latest":
            latest_tag = True
    missing_expose = _EXPOSE_RE.search(text) is None
    ports: list = []
    for m in _EXPOSE_PORTS_RE.finditer(text):
        for tok in re.split(r"[\s,]+", m.group(1).strip()):
            num = tok.split("/")[0]
            if num.isdigit():
                ports.append(int(num))
    return {
        "base_image": base_image,
        "latest_tag": latest_tag,
        "missing_expose": missing_expose,
        "ports": ports,
        "localhost_refs": _localhost_refs(text),
    }


def parse_compose(text: str) -> dict:
    """Parse compose YAML as text (no yaml dep): ports, localhost refs, image tag."""
    text = text or ""
    ports: list = []
    for m in _PORT_MAPPING_RE.finditer(text):
        ports.append(int(m.group(2)))
    latest_tag = False
    for m in _COMPOSE_IMAGE_RE.finditer(text):
        image = m.group(1).strip().strip("\"'")
        name = image.split("@")[0]
        if ":" not in name or name.rsplit(":", 1)[1].lower() == "latest":
            latest_tag = True
    return {
        "latest_tag": latest_tag,
        "missing_expose": False,
        "ports": ports,
        "localhost_refs": _localhost_refs(text),
    }


def parse_env(text: str) -> dict:
    """Parse KEY=VALUE env text: vars, ports, localhost refs."""
    text = text or ""
    vars: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        vars[key.strip()] = val.strip().strip("\"'")
    ports: list = []
    for key in ("PORT", "APP_PORT", "HTTP_PORT"):
        if key in vars and vars[key].isdigit():
            ports.append(int(vars[key]))
    return {
        "vars": vars,
        "latest_tag": False,
        "missing_expose": False,
        "ports": ports,
        "localhost_refs": _localhost_refs(text),
    }


def parse_all(dockerfile_text: str = "", compose_text: str = "", env_text: str = "") -> dict:
    """Combined shape: {dockerfile, compose, ports, localhost_refs, latest_tag, missing_expose}."""
    df = parse_dockerfile(dockerfile_text)
    co = parse_compose(compose_text)
    en = parse_env(env_text)
    ports = sorted(set(df["ports"]) | set(co["ports"]) | set(en["ports"]))
    localhost_refs = sorted(set(df["localhost_refs"]) | set(co["localhost_refs"]) | set(en["localhost_refs"]))
    return {
        "dockerfile": {"base_image": df["base_image"]},
        "compose": {"ports": co["ports"]},
        "ports": ports,
        "localhost_refs": localhost_refs,
        "latest_tag": bool(df["latest_tag"] or co["latest_tag"]),
        "missing_expose": df["missing_expose"],
    }


def has_submodule_ref(text: str) -> bool:
    """True if text references git submodules (.gitmodules / [submodule])."""
    lowered = (text or "").lower()
    return "[submodule" in lowered or ".gitmodules" in lowered


def assert_no_submodules(text: str) -> None:
    """Raise 400-style ValueError if a submodule ref is present."""
    if has_submodule_ref(text):
        raise _err(
            "submodules are not accepted (.gitmodules/[submodule] ref found)",
            "Remove submodules (clone uses --recurse-submodules=no). " + _DEMO_HINT,
        )


def check_repo_size(size_bytes: int, limit_mb: int = MAX_SIZE_MB) -> None:
    """Raise 400-style ValueError when the pre-check size exceeds the limit."""
    if size_bytes is None:
        raise _err("unknown repo size", "Re-paste the repo URL. " + _DEMO_HINT)
    if size_bytes > limit_mb * 1024 * 1024:
        raise _err(
            "repo exceeds %dMB pre-check limit" % limit_mb,
            "Use a smaller repo or shallow snapshot. " + _DEMO_HINT,
        )
