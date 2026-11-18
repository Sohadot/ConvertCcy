#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
metal_reference.py — SEO-A4.4 precious-metal value model and licensing gate.

data/metal_reference_snapshot.json is the ONLY place a metal price may come
from. It is separate from the ordinary FX snapshot (data/rate_snapshot.json),
which is never modified for metals. Architecture (Option C): benchmark
provenance (who administers a price, under which licence) is recorded per
source; a numeric quote may only be rendered when its source's license_state
permits publication, it carries a timestamp, unit and counter-currency, and it
is fresh relative to the snapshot's own capture time (deterministic builds).

Value types rendered by value_view():
  benchmark_reference | market_reference   direct quote (metal -> its quote currency)
  derived_cross_value                      quote x FX cross (both sources + timestamps shown)
  derived_inverse                          1 / (metal value): currency -> metal quantity
  derived_metal_ratio                      metal A value / metal B value, same counter-currency
  unavailable                              no publishable value (the current state)
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parent
METAL_SNAPSHOT_FILE = REPO / "data" / "metal_reference_snapshot.json"

LICENSE_STATES = ("redistribution_permitted", "attribution_required", "display_only",
                  "derived_use_only", "license_unclear", "not_usable")
PUBLISHABLE_LICENSES = ("redistribution_permitted", "attribution_required")
QUOTE_TYPES = ("benchmark_reference", "market_reference")
VALUE_TYPES = QUOTE_TYPES + ("derived_cross_value", "derived_inverse", "derived_metal_ratio", "unavailable")
FRESHNESS_STATES = ("current", "recent", "stale", "historical_snapshot", "unavailable")
SOURCE_ROLES = ("benchmark", "market_data_provider", "fx_provider", "market_body")
METAL_CODES = ("XAU", "XAG", "XPT", "XPD")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
QUOTE_FIELDS = ("metal_code", "metal_name", "unit", "counter_currency", "value", "valuation_type", "source_id",
                "source_timestamp", "retrieved_at", "license_state", "provenance_id", "derived")


class MetalSnapshotError(ValueError):
    pass


def _no_dupes(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise MetalSnapshotError(f"duplicate key {k!r}")
        out[k] = v
    return out


def load_metal_snapshot(path: Path = METAL_SNAPSHOT_FILE) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_no_dupes)


def _ts(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def validate_metal_snapshot(snap: Any, classification: Optional[Dict[str, Any]] = None) -> List[str]:
    """Return every schema / licensing / provenance violation. Fails closed."""
    errs: List[str] = []
    if not isinstance(snap, dict):
        return ["metal snapshot root must be an object"]
    if snap.get("type") != "metal_reference_snapshot":
        errs.append("type must be 'metal_reference_snapshot'")
    state = snap.get("activation_state")
    if state not in ("reference_layer_only", "source_activated"):
        errs.append("activation_state must be reference_layer_only or source_activated")
    if classification is not None:
        want = classification.get("precious_metals_reference", {}).get("pricing", {}).get("activation_state")
        if want != state:
            errs.append(f"activation_state {state!r} disagrees with the classification ({want!r})")
    fp = snap.get("freshness_policy") or {}
    for k in ("current_max_hours", "recent_max_hours"):
        if not isinstance(fp.get(k), (int, float)) or isinstance(fp.get(k), bool) or fp.get(k) <= 0:
            errs.append(f"freshness_policy.{k} must be a positive number")
    if fp.get("current_max_hours", 0) > fp.get("recent_max_hours", 0):
        errs.append("freshness_policy: current_max_hours must not exceed recent_max_hours")
    dp = snap.get("derivation_policy") or {}
    if not isinstance(dp.get("max_timestamp_skew_hours"), (int, float)) or dp.get("max_timestamp_skew_hours", 0) <= 0:
        errs.append("derivation_policy.max_timestamp_skew_hours must be a positive number")
    sources = snap.get("sources")
    if not isinstance(sources, list) or not sources:
        errs.append("sources must be a non-empty list")
        sources = []
    by_id: Dict[str, Dict[str, Any]] = {}
    reg = (classification or {}).get("verification_sources", {})
    for s in sources:
        sid = s.get("id")
        if not sid or sid in by_id:
            errs.append(f"source id missing or duplicated: {sid!r}")
            continue
        by_id[sid] = s
        if s.get("license_state") not in LICENSE_STATES:
            errs.append(f"source {sid}: license_state {s.get('license_state')!r} invalid")
        if s.get("role") not in SOURCE_ROLES:
            errs.append(f"source {sid}: role invalid")
        if not s.get("name") or not s.get("license_basis"):
            errs.append(f"source {sid}: name and license_basis required")
        for m in s.get("metals") or []:
            if m not in METAL_CODES:
                errs.append(f"source {sid}: unknown metal {m!r}")
        ev = s.get("license_evidence")
        if ev is not None and classification is not None:
            entries = reg.get(ev.get("source"), [])
            i = ev.get("index")
            if not (isinstance(i, int) and 0 <= i < len(entries) and ev.get("supports") in entries[i].get("supports", [])):
                errs.append(f"source {sid}: license_evidence does not resolve to the verification registry")
    quotes = snap.get("quotes")
    if not isinstance(quotes, list):
        errs.append("quotes must be a list")
        quotes = []
    if state == "reference_layer_only" and quotes:
        errs.append("reference_layer_only snapshot must not carry quotes")
    if state == "source_activated" and not quotes:
        errs.append("source_activated snapshot must carry quotes")
    cap = snap.get("captured_at")
    if quotes and not (isinstance(cap, str) and TS_RE.match(cap)):
        errs.append("captured_at must be YYYY-MM-DDTHH:MM:SSZ when quotes exist")
    seen = set()
    for k, q in enumerate(quotes):
        w = f"quotes[{k}]"
        if not isinstance(q, dict):
            errs.append(f"{w}: must be an object")
            continue
        missing = [f for f in QUOTE_FIELDS if f not in q]
        extra = set(q) - set(QUOTE_FIELDS)
        if missing or extra:
            errs.append(f"{w}: missing {missing} / unknown {sorted(extra)}")
            continue
        if q["metal_code"] not in METAL_CODES:
            errs.append(f"{w}: metal_code invalid")
        if not re.fullmatch(r"[A-Z]{3}", str(q["counter_currency"])) or q["counter_currency"] in METAL_CODES:
            errs.append(f"{w}: counter_currency must be a non-metal ISO code")
        if q["valuation_type"] not in QUOTE_TYPES:
            errs.append(f"{w}: valuation_type must be one of {QUOTE_TYPES}")
        if q["derived"] is not False:
            errs.append(f"{w}: stored quotes are direct; derived values are computed, never stored")
        if not q["unit"] or not q["provenance_id"]:
            errs.append(f"{w}: unit and provenance_id required")
        try:
            v = Decimal(str(q["value"]))
            if not isinstance(q["value"], str) or v <= 0:
                raise ValueError
        except Exception:
            errs.append(f"{w}: value must be a positive decimal string")
        for f in ("source_timestamp", "retrieved_at"):
            if not (isinstance(q[f], str) and TS_RE.match(q[f])):
                errs.append(f"{w}: {f} must be YYYY-MM-DDTHH:MM:SSZ")
        src = by_id.get(q["source_id"])
        if src is None:
            errs.append(f"{w}: unknown source_id {q['source_id']!r}")
        else:
            if q["license_state"] != src.get("license_state"):
                errs.append(f"{w}: license_state differs from its source")
            if src.get("license_state") not in PUBLISHABLE_LICENSES:
                errs.append(f"{w}: source {q['source_id']} is {src.get('license_state')}; quote may not be published")
            if q["metal_code"] not in (src.get("metals") or []):
                errs.append(f"{w}: source does not cover {q['metal_code']}")
        key = (q["metal_code"], q["counter_currency"], q["source_id"])
        if key in seen:
            errs.append(f"{w}: duplicate quote for {key}")
        seen.add(key)
    return errs


# ---------------------------------------------------------------------------
# precision (mirrors the A3 rule: never more digits than the weakest input)
# ---------------------------------------------------------------------------

def published_uncertainty(value: str) -> float:
    """Half a unit of the last published decimal place, relative to the value."""
    d = Decimal(value)
    return 0.5 * float(Decimal(1).scaleb(d.as_tuple().exponent)) / float(d)


def sig_for(u: float) -> int:
    if u <= 0:
        return 6
    return max(3, min(6, int(math.floor(-math.log10(u)))))


def format_published(value: str) -> str:
    """A direct quote is shown exactly as published (grouping only, no re-rounding)."""
    return f"{Decimal(value):,f}"


def freshness(source_ts: str, captured_at: str, policy: Dict[str, Any]) -> str:
    age_h = (_ts(captured_at) - _ts(source_ts)).total_seconds() / 3600.0
    if age_h < 0:
        return "unavailable"
    if age_h <= policy["current_max_hours"]:
        return "current"
    if age_h <= policy["recent_max_hours"]:
        return "recent"
    return "stale"


def usable_quote(snap: Dict[str, Any], metal: str) -> Optional[Dict[str, Any]]:
    """The publishable, non-stale direct quote for a metal (deterministic choice)."""
    if snap.get("activation_state") != "source_activated":
        return None
    srcs = {s["id"]: s for s in snap.get("sources", [])}
    cands = []
    for q in snap.get("quotes", []):
        if q["metal_code"] != metal:
            continue
        src = srcs.get(q["source_id"])
        if not src or src.get("license_state") not in PUBLISHABLE_LICENSES or q["license_state"] != src["license_state"]:
            continue
        state = freshness(q["source_timestamp"], snap["captured_at"], snap["freshness_policy"])
        if state in ("current", "recent"):
            cands.append((0 if q["valuation_type"] == "benchmark_reference" else 1, q["counter_currency"], q, state, src))
    if not cands:
        return None
    _, _, q, state, src = sorted(cands, key=lambda x: (x[0], x[1]))[0]
    return {"quote": q, "freshness": state, "source": src}


def value_view(from_code: str, to_code: str, snap: Dict[str, Any], fx: Dict[str, Any],
               format_value) -> Dict[str, Any]:
    """Resolve what may be shown for a metal pair. Returns value_type 'unavailable' unless
    every provenance, licence, freshness and skew rule is satisfied."""
    unavailable = {"value_type": "unavailable"}
    fm, tm = from_code in METAL_CODES, to_code in METAL_CODES
    max_skew = snap.get("derivation_policy", {}).get("max_timestamp_skew_hours", 0)

    def in_currency(metal: str, currency: str):
        u = usable_quote(snap, metal)
        if not u:
            return None
        q = u["quote"]
        base = {"metal_source": u["source"]["name"], "metal_timestamp": q["source_timestamp"],
                "freshness": u["freshness"], "unit": q["unit"], "quote_currency": q["counter_currency"]}
        if q["counter_currency"] == currency:
            return dict(base, value=float(q["value"]), u=published_uncertainty(q["value"]),
                        value_type=q["valuation_type"], derived=False, published=q["value"])
        rates = fx.get("rates", {})
        c0 = q["counter_currency"]
        if c0 not in rates or currency not in rates or not fx.get("captured_at"):
            return None
        skew_h = abs((_ts(fx["captured_at"]) - _ts(q["source_timestamp"])).total_seconds()) / 3600.0
        if skew_h > max_skew:
            return None
        fx_u = sum(published_uncertainty(repr(float(rates[c]))) if rates[c] != 1 else 0.0 for c in (c0, currency))
        return dict(base, value=float(q["value"]) * float(rates[currency]) / float(rates[c0]),
                    u=published_uncertainty(q["value"]) + fx_u, value_type="derived_cross_value", derived=True,
                    fx_source=fx.get("source"), fx_timestamp=fx["captured_at"])

    if fm and tm:
        a, b = usable_quote(snap, from_code), usable_quote(snap, to_code)
        if not a or not b or a["quote"]["counter_currency"] != b["quote"]["counter_currency"]:
            return unavailable
        if a["quote"]["unit"] != b["quote"]["unit"]:
            return unavailable
        skew_h = abs((_ts(a["quote"]["source_timestamp"]) - _ts(b["quote"]["source_timestamp"])).total_seconds()) / 3600.0
        if skew_h > max_skew:
            return unavailable
        ratio = float(a["quote"]["value"]) / float(b["quote"]["value"])
        u = published_uncertainty(a["quote"]["value"]) + published_uncertainty(b["quote"]["value"])
        return {"value_type": "derived_metal_ratio", "derived": True, "value_text": format_value(ratio, sig_for(u)),
                "sources": [a["source"]["name"], b["source"]["name"]],
                "timestamps": [a["quote"]["source_timestamp"], b["quote"]["source_timestamp"]]}
    metal, other = (from_code, to_code) if fm else (to_code, from_code)
    v = in_currency(metal, other)
    if not v:
        return unavailable
    value = v["value"] if fm else 1.0 / v["value"]
    vt = v["value_type"] if fm else "derived_inverse"
    direct = fm and not v["derived"]
    text = format_published(v["published"]) if direct else format_value(value, sig_for(v["u"]))
    out = {"value_type": vt, "derived": v["derived"] or not fm, "value_text": text,
           "unit": v["unit"], "sources": [v["metal_source"]] + ([v["fx_source"]] if v.get("fx_source") else []),
           "timestamps": [v["metal_timestamp"]] + ([v["fx_timestamp"]] if v.get("fx_timestamp") else []),
           "freshness": v["freshness"]}
    return out
