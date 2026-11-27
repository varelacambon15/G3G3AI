"""Uso de tokens y coste estimado.

Los precios son ORIENTATIVOS (dólares por millón de tokens, entrada/salida) y cambian con el tiempo: se pueden
sobrescribir en Ajustes → «Precios por modelo» con líneas «modelo = entrada, salida». Los modelos locales cuestan 0.
Si un modelo de API no tiene precio, se cuentan sus tokens pero no se estima el coste.
"""
from __future__ import annotations

import re
import time

# (patrón del nombre del modelo, entrada, salida) por millón de tokens. El primero que coincide gana.
DEFAULT_PRICES: list[tuple[str, float, float]] = [
    (r"claude.*haiku", 1.0, 5.0),
    (r"claude.*sonnet", 3.0, 15.0),
    (r"claude.*opus", 5.0, 25.0),
    (r"deepseek.*(reasoner|r1)", 0.55, 2.19),
    (r"deepseek", 0.27, 1.10),
    (r"gpt-?4o-?mini|gpt-?4\.1-?(mini|nano)|gpt-?5-?(mini|nano)", 0.25, 1.0),
    (r"gpt-?5|gpt-?4\.1|gpt-?4o", 2.0, 8.0),
    (r"gemini.*flash", 0.30, 2.5),
    (r"gemini.*pro", 1.25, 10.0),
]


def parse_prices(lines) -> dict[str, tuple[float, float]]:
    """«modelo = entrada, salida» (una por línea) → {modelo: (entrada, salida)}."""
    out = {}
    for ln in lines or []:
        m = re.match(r"\s*(.+?)\s*=\s*([\d.]+)\s*[,;/ ]\s*([\d.]+)\s*$", str(ln))
        if m:
            out[m.group(1).lower()] = (float(m.group(2)), float(m.group(3)))
    return out


KNOWN_PRICES: dict[tuple[str, str], tuple[float, float]] = {}   # los que publica el proveedor en su lista de modelos


def price_for(cfg, provider: str, model: str) -> tuple[float, float] | None:
    if provider in ("local", "ollama") or not model:
        return (0.0, 0.0)
    name = model.lower()
    custom = parse_prices(cfg["model_prices"])
    for key, pr in custom.items():
        if key in name:
            return pr
    if (provider, model) in KNOWN_PRICES:
        return KNOWN_PRICES[(provider, model)]
    for pat, pin, pout in DEFAULT_PRICES:
        if re.search(pat, name):
            return (pin, pout)
    return None


def cost_of(cfg, provider: str, model: str, tin: int, tout: int) -> float | None:
    pr = price_for(cfg, provider, model)
    if pr is None:
        return None
    return (tin * pr[0] + tout * pr[1]) / 1_000_000


def month_start(now: float | None = None) -> float:
    t = time.localtime(now or time.time())
    return time.mktime((t.tm_year, t.tm_mon, 1, 0, 0, 0, 0, 0, -1))


def summary(db, cfg, since: float | None = None) -> dict:
    """Totales desde `since` (por defecto, este mes): por modelo y total."""
    since = month_start() if since is None else since
    rows = db.assistant_usage(since)
    models: dict[str, dict] = {}
    for r in rows:
        u = (r["meta"] or {}).get("usage")
        if not u:
            continue
        key = f"{r['meta'].get('provider', '?')} · {r['meta'].get('model', '?')}"
        m = models.setdefault(key, {"input": 0, "output": 0, "cost": 0.0, "unpriced": False, "calls": 0,
                                    "allowance": 0.0, "list_cost": 0.0, "provider": r["meta"].get("provider")})
        m["allowance"] += u.get("allowance") or 0
        m["list_cost"] += u.get("list_cost") or 0
        m["input"] += u.get("in", 0)
        m["output"] += u.get("out", 0)
        m["calls"] += 1
        if u.get("cost") is None:
            m["unpriced"] = True
        else:
            m["cost"] += u["cost"]
    total = {"input": sum(m["input"] for m in models.values()), "output": sum(m["output"] for m in models.values()),
             "cost": sum(m["cost"] for m in models.values()),
             "allowance": sum(m["allowance"] for m in models.values()),
             "list_cost": sum(m["list_cost"] for m in models.values())}
    by_provider: dict[str, dict] = {}
    for m in models.values():
        b = by_provider.setdefault(m["provider"] or "?", {"cost": 0.0, "allowance": 0.0, "list_cost": 0.0, "calls": 0})
        for k in ("cost", "allowance", "list_cost", "calls"):
            b[k] += m[k]
    limit = float(cfg["monthly_budget_usd"] or 0)
    return {"since": since, "models": models, "total": total, "providers": by_provider, "budget": limit,
            "budget_pct": round(100 * total["cost"] / limit) if limit else None}
