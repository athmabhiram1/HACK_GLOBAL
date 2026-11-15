"""BatonGate Task 6: cost gate (Vultr read-only + synthetic demo fallback).

estimate_cost(vultr_client=None, demo=False) ->
  {current, simulated, saved, co2_kg, downgrade_cmd, demo}
Injectable client (default None -> demo synthetic). Stdlib at import, httpx
only lazily inside the default live client. API keys are never logged.
Python 3.11 compatible.
"""

import os

VOLUME_GB_MONTH_RATE = 0.10
CO2_KG_PER_DOLLAR = 0.05

_DEMO_INSTANCES = (
    {"id": "demo-inst-1", "label": "demo-web", "plan": "vc2-1c-2gb",
     "cpu_recent_percent": 2.0},
)
_DEMO_SIZES = (
    {"id": "vc2-1c-2gb", "price_per_month": 12.0},
    {"id": "vc2-1c-1gb", "price_per_month": 6.0},
)
_DEMO_VOLUMES = (
    {"id": "demo-vol-1", "label": "demo-data", "size_gb": 10,
     "monthly_price": 1.0, "attached_to": None},
)


def _as_list(payload, *keys):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in keys:
            val = payload.get(key)
            if isinstance(val, list):
                return val
    return []


def _fetch(client, names, path, *keys):
    """Duck-typed read: try method names, then get(path).json()."""
    for name in names:
        meth = getattr(client, name, None)
        if callable(meth):
            return _as_list(meth(), *keys)
    getter = getattr(client, "get", None)
    if callable(getter):
        return _as_list(getter(path).json(), *keys)
    raise AttributeError("client has no Vultr read method for %s" % path)


def _price(size):
    for key in ("price_per_month", "monthly_cost", "monthly_price", "price"):
        try:
            return float(size.get(key))
        except (TypeError, ValueError):
            continue
    return 0.0


def _cpu(inst):
    for key in ("cpu_recent_percent", "cpu_percent", "cpu", "recent_cpu"):
        try:
            return float(inst.get(key))
        except (TypeError, ValueError):
            continue
    return 100.0


def _plan(inst):
    for key in ("plan", "size", "size_slug", "plan_slug"):
        if inst.get(key):
            return str(inst.get(key))
    return ""


def _volume_cost(vol):
    for key in ("monthly_price", "monthly_cost", "cost"):
        try:
            return float(vol.get(key))
        except (TypeError, ValueError):
            continue
    try:
        return float(vol.get("size_gb", 0)) * VOLUME_GB_MONTH_RATE
    except (TypeError, ValueError):
        return 0.0


def _attached(vol):
    return vol.get("attached_to", vol.get("instance_id"))


def _cheaper(sizes, price):
    cheaper = [s for s in sizes if _price(s) < price]
    if not cheaper:
        return None
    return min(cheaper, key=_price)


def estimate_cost(vultr_client=None, demo=False):
    """Estimate current vs simulated monthly cost. Never raises, never logs keys."""
    use_demo = bool(demo) or vultr_client is None
    instances, sizes, volumes = [], [], []
    if not use_demo:
        try:
            instances = _fetch(vultr_client, ("list_instances", "get_instances"),
                               "/v2/instances", "instances")
            sizes = _fetch(vultr_client, ("list_sizes", "get_sizes"),
                           "/v2/sizes", "sizes")
            volumes = _fetch(vultr_client, ("list_volumes", "get_volumes"),
                             "/v2/volumes", "volumes")
        except Exception:
            use_demo = True
    if use_demo:
        instances = [dict(i) for i in _DEMO_INSTANCES]
        sizes = [dict(s) for s in _DEMO_SIZES]
        volumes = [dict(v) for v in _DEMO_VOLUMES]

    price_by_id = {str(s.get("id")): _price(s) for s in sizes}
    current = 0.0
    simulated = 0.0
    commands = []
    for inst in instances:
        price = price_by_id.get(_plan(inst), 0.0)
        current += price
        if _cpu(inst) < 5.0:
            target = _cheaper(sizes, price)
            if target is not None:
                simulated += _price(target)
                commands.append("downgrade %s (%s) to %s ($%.2f/mo)" % (
                    inst.get("id", "?"), _plan(inst),
                    target.get("id"), _price(target)))
            else:
                simulated += price
        else:
            simulated += price
    for vol in volumes:
        cost = _volume_cost(vol)
        current += cost
        if _attached(vol) in (None, "", []):
            commands.append("delete unattached volume %s ($%.2f/mo)" % (
                vol.get("id", "?"), cost))
        else:
            simulated += cost

    current = round(current, 2)
    simulated = round(simulated, 2)
    saved = round(current - simulated, 2)
    return {
        "current": current,
        "simulated": simulated,
        "saved": saved,
        "co2_kg": round(max(saved, 0.0) * CO2_KG_PER_DOLLAR, 4),
        "downgrade_cmd": "; ".join(commands),
        "demo": use_demo,
    }


class LiveVultrClient:
    """Read-only Vultr v2 client (GET only). Key held in memory, never logged."""

    BASE = "https://api.vultr.com/v2"

    def __init__(self, api_key=None, timeout_s=10):
        self._api_key = api_key if api_key is not None else os.environ.get("VULTR_API_KEY", "")
        self._timeout_s = timeout_s

    def _get(self, path):
        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx is not installed")
        resp = httpx.get(self.BASE + path,
                         headers={"Authorization": "Bearer " + self._api_key},
                         timeout=self._timeout_s)
        resp.raise_for_status()
        return resp

    def list_instances(self):
        return _as_list(self._get("/instances").json(), "instances")

    def list_sizes(self):
        return _as_list(self._get("/sizes").json(), "sizes")

    def list_volumes(self):
        return _as_list(self._get("/volumes").json(), "volumes")
