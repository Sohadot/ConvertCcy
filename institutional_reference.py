#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
institutional_reference.py — SEO-A4.5 institutional-unit value model and licensing gate.

data/institutional_reference_snapshot.json is the ONLY place a numeric value for an
institutional unit (XDR, CLF, UYW, XUA, XSU) may come from. It is separate from the
ordinary FX snapshot (data/rate_snapshot.json, never modified here) and from the
metal snapshot (data/metal_reference_snapshot.json). Provider FX values for XDR/CLF
stay in the raw FX snapshot and are classified here as secondary only.

A stored value is a direct issuer valuation (issuer_published_valuation,
indexed_unit_value or basket_valuation) of 1 unit in its denomination currency.
It may be rendered only when its source's license_state permits publication, it
carries a valuation date, source timestamp and retrieval time, a methodology and a
provenance id, and it is fresh under the instrument's own cadence policy (never a
universal FX TTL). Values are never stored derived: derived_reference_value is
computed at render time from a governed issuer value and a governed FX reference,
with both dates shown, within the instrument's own timestamp-skew limit.

value_view(from, to) returns value_type:
  issuer_published_valuation | indexed_unit_value | basket_valuation   direct (unit -> its denomination)
  derived_reference_value                                              inverse or FX cross of a direct value
  unavailable                                                          no publishable value (current state)
institutional_parity is recorded as a relationship type only; it never yields a
numeric value unless the issuer publishes one as a stored value.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parent
INSTITUTIONAL_SNAPSHOT_FILE = REPO / "data" / "institutional_reference_snapshot.json"

LICENSE_STATES = ("redistribution_permitted", "attribution_required", "derived_use_only", "display_only",
                  "license_unclear", "not_usable")
PUBLISHABLE_LICENSES = ("redistribution_permitted", "attribution_required")
DIRECT_TYPES = ("issuer_published_valuation", "indexed_unit_value", "basket_valuation")
VALUE_TYPES = DIRECT_TYPES + ("derived_reference_value", "institutional_parity", "unavailable")
VALUE_DECISIONS = ("issuer_value_activated", "issuer_methodology_only", "reference_layer_only")
FRESHNESS_STATES = ("current", "recent", "stale", "unavailable")
CADENCES = ("daily_business", "daily_published_by_period", "follows_related_unit", "unresolved")
SOURCE_ROLES = ("issuer", "statutory_publisher", "official_republisher", "fx_provider")
PROVIDER_CLASSES = ("provider_value_secondary_only", "provider_value_pending_issuer_comparison")
INSTITUTIONAL_CODES = ("XDR", "CLF", "UYW", "XUA", "XSU")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALUE_FIELDS = ("instrument_code", "instrument_name", "instrument_type", "issuer", "valuation_type", "value",
                "denomination_currency", "valuation_date", "source_timestamp", "retrieved_at", "methodology_id",
                "source_id", "license_state", "freshness_state", "derived", "derivation_method", "provenance_id")
INSTRUMENT_FIELDS = ("value_decision", "valuation_type", "denomination_currency", "methodology_id", "source_id",
                     "freshness_policy_id", "precision_policy")


class InstitutionalSnapshotError(ValueError):
    pass


def _no_dupes(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise InstitutionalSnapshotError(f"duplicate key {k!r}")
        out[k] = v
    return out


def load_institutional_snapshot(path: Path = INSTITUTIONAL_SNAPSHOT_FILE) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_no_dupes)


def _ts(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _resolves(reg: Dict[str, Any], ev: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(ev, dict):
        return False
    entries = reg.get(ev.get("source"), [])
    i = ev.get("index")
    return isinstance(i, int) and 0 <= i < len(entries) and ev.get("supports") in entries[i].get("supports", [])


def validate_institutional_snapshot(snap: Any, classification: Optional[Dict[str, Any]] = None) -> List[str]:
    """Return every schema / licensing / provenance / freshness violation. Fails closed."""
    errs: List[str] = []
    if not isinstance(snap, dict):
        return ["institutional snapshot root must be an object"]
    if snap.get("type") != "institutional_reference_snapshot":
        errs.append("type must be 'institutional_reference_snapshot'")
    state = snap.get("activation_state")
    if state not in ("reference_layer_only", "source_activated"):
        errs.append("activation_state must be reference_layer_only or source_activated")
    reg = (classification or {}).get("verification_sources", {})
    units = (classification or {}).get("institutional_units_reference", {}).get("units", {})

    policies = snap.get("freshness_policies")
    if not isinstance(policies, dict) or not policies:
        errs.append("freshness_policies must be a non-empty object")
        policies = {}
    for pid, p in policies.items():
        w = f"freshness_policies.{pid}"
        if p.get("cadence") not in CADENCES:
            errs.append(f"{w}: cadence must be one of {CADENCES}")
        if p.get("cadence") in ("daily_business", "daily_published_by_period"):
            for k in ("current_max_hours", "recent_max_hours", "max_fx_skew_hours"):
                v = p.get(k)
                if not isinstance(v, (int, float)) or isinstance(v, bool) or v <= 0:
                    errs.append(f"{w}.{k} must be a positive number")
            if (p.get("current_max_hours") or 0) > (p.get("recent_max_hours") or 0):
                errs.append(f"{w}: current_max_hours must not exceed recent_max_hours")
        elif any(k in p for k in ("current_max_hours", "recent_max_hours", "max_fx_skew_hours")):
            errs.append(f"{w}: a {p.get('cadence')} cadence publishes no own value and takes no age limits")
        if not p.get("basis"):
            errs.append(f"{w}: basis (why this cadence) required")

    methods = snap.get("methodologies")
    if not isinstance(methods, dict) or not methods:
        errs.append("methodologies must be a non-empty object")
        methods = {}
    for mid, m in methods.items():
        if not m.get("summary") or not m.get("evidence"):
            errs.append(f"methodologies.{mid}: summary and evidence required")
        elif classification is not None and not all(_resolves(reg, e) for e in m["evidence"]):
            errs.append(f"methodologies.{mid}: evidence does not resolve to the verification registry")

    sources = snap.get("sources")
    by_id: Dict[str, Dict[str, Any]] = {}
    if not isinstance(sources, list) or not sources:
        errs.append("sources must be a non-empty list")
        sources = []
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
        for k in ("name", "authority", "url", "license_basis"):
            if not s.get(k):
                errs.append(f"source {sid}: {k} required")
        for c in s.get("codes") or []:
            if c not in INSTITUTIONAL_CODES:
                errs.append(f"source {sid}: unknown code {c!r}")
        ev = s.get("license_evidence")
        if s.get("license_state") in PUBLISHABLE_LICENSES and ev is None:
            errs.append(f"source {sid}: a publishable licence needs license_evidence")
        if ev is not None and classification is not None and not _resolves(reg, ev):
            errs.append(f"source {sid}: license_evidence does not resolve to the verification registry")

    instruments = snap.get("instruments")
    if not isinstance(instruments, dict) or set(instruments) != set(INSTITUTIONAL_CODES):
        errs.append(f"instruments must define exactly {list(INSTITUTIONAL_CODES)}")
        instruments = instruments if isinstance(instruments, dict) else {}
    for code, ins in instruments.items():
        w = f"instruments.{code}"
        if set(ins) != set(INSTRUMENT_FIELDS):
            errs.append(f"{w}: fields must be exactly {list(INSTRUMENT_FIELDS)}")
            continue
        if ins["value_decision"] not in VALUE_DECISIONS:
            errs.append(f"{w}: value_decision invalid")
        if units and code in units:
            if ins["value_decision"] != units[code]["value_decision"]:
                errs.append(f"{w}: value_decision disagrees with the classification")
            if ins["valuation_type"] != units[code]["valuation_type"]:
                errs.append(f"{w}: valuation_type disagrees with the classification")
        if ins["valuation_type"] not in VALUE_TYPES or ins["valuation_type"] == "derived_reference_value":
            errs.append(f"{w}: valuation_type invalid")
        if ins["freshness_policy_id"] not in policies:
            errs.append(f"{w}: unknown freshness_policy_id")
        if ins["methodology_id"] is not None and ins["methodology_id"] not in methods:
            errs.append(f"{w}: unknown methodology_id")
        if ins["value_decision"] != "reference_layer_only" and ins["methodology_id"] is None:
            errs.append(f"{w}: issuer methodology is required unless reference_layer_only")
        if ins["source_id"] is not None and ins["source_id"] not in by_id:
            errs.append(f"{w}: unknown source_id")
        if ins["denomination_currency"] is not None and not re.fullmatch(r"[A-Z]{3}", str(ins["denomination_currency"])):
            errs.append(f"{w}: denomination_currency must be an ISO code or null")
        if ins["precision_policy"] not in ("source_precision", "not_applicable"):
            errs.append(f"{w}: precision_policy must be source_precision or not_applicable")

    values = snap.get("values")
    if not isinstance(values, list):
        errs.append("values must be a list")
        values = []
    if state == "reference_layer_only" and values:
        errs.append("reference_layer_only snapshot must not carry values")
    if state == "source_activated" and not values:
        errs.append("source_activated snapshot must carry values")
    cap = snap.get("captured_at")
    if values and not (isinstance(cap, str) and TS_RE.match(cap)):
        errs.append("captured_at must be YYYY-MM-DDTHH:MM:SSZ when values exist")
    if not values and cap is not None:
        errs.append("captured_at must be null when no values exist (no fabricated timestamp)")
    seen = set()
    for k, v in enumerate(values):
        w = f"values[{k}]"
        if not isinstance(v, dict):
            errs.append(f"{w}: must be an object")
            continue
        missing = [f for f in VALUE_FIELDS if f not in v]
        extra = set(v) - set(VALUE_FIELDS)
        if missing or extra:
            errs.append(f"{w}: missing {missing} / unknown {sorted(extra)}")
            continue
        code = v["instrument_code"]
        ins = instruments.get(code)
        if code not in INSTITUTIONAL_CODES or ins is None:
            errs.append(f"{w}: instrument_code invalid")
            continue
        if ins.get("value_decision") != "issuer_value_activated":
            errs.append(f"{w}: {code} value_decision is {ins.get('value_decision')}; no value may be stored")
        if v["valuation_type"] not in DIRECT_TYPES or v["valuation_type"] != ins.get("valuation_type"):
            errs.append(f"{w}: valuation_type must be the instrument's direct issuer type")
        if v["derived"] is not False or v["derivation_method"] is not None:
            errs.append(f"{w}: stored values are direct; derived values are computed, never stored")
        if v["denomination_currency"] != ins.get("denomination_currency"):
            errs.append(f"{w}: denomination_currency differs from the instrument policy")
        if v["methodology_id"] != ins.get("methodology_id") or v["source_id"] != ins.get("source_id"):
            errs.append(f"{w}: methodology_id/source_id differ from the instrument policy")
        if units and code in units and v["issuer"] != units[code]["issuer_display"]:
            errs.append(f"{w}: issuer differs from the classification")
        if not v["provenance_id"] or not v["instrument_name"]:
            errs.append(f"{w}: provenance_id and instrument_name required")
        if v["freshness_state"] not in FRESHNESS_STATES:
            errs.append(f"{w}: freshness_state invalid")
        try:
            d = Decimal(str(v["value"]))
            if not isinstance(v["value"], str) or d <= 0 or not d.is_finite():
                raise ValueError
        except Exception:
            errs.append(f"{w}: value must be a positive finite decimal string")
        if not (isinstance(v["valuation_date"], str) and DATE_RE.match(v["valuation_date"])):
            errs.append(f"{w}: valuation_date must be YYYY-MM-DD")
        for f in ("source_timestamp", "retrieved_at"):
            if not (isinstance(v[f], str) and TS_RE.match(v[f])):
                errs.append(f"{w}: {f} must be YYYY-MM-DDTHH:MM:SSZ")
        if all(isinstance(v[f], str) and TS_RE.match(v[f]) for f in ("source_timestamp", "retrieved_at")):
            if _ts(v["retrieved_at"]) < _ts(v["source_timestamp"]):
                errs.append(f"{w}: retrieved_at precedes source_timestamp")
        src = by_id.get(v["source_id"])
        if src is None:
            errs.append(f"{w}: unknown source_id")
        else:
            if v["license_state"] != src.get("license_state"):
                errs.append(f"{w}: license_state differs from its source")
            if src.get("license_state") not in PUBLISHABLE_LICENSES:
                errs.append(f"{w}: source {v['source_id']} is {src.get('license_state')}; value may not be published")
            if code not in (src.get("codes") or []):
                errs.append(f"{w}: source does not cover {code}")
        key = (code, v["denomination_currency"], v["source_id"])
        if key in seen:
            errs.append(f"{w}: duplicate value for {key}")
        seen.add(key)

    pv = snap.get("provider_values")
    if not isinstance(pv, dict):
        errs.append("provider_values must be an object")
        pv = {}
    for code, p in pv.items():
        w = f"provider_values.{code}"
        if code not in INSTITUTIONAL_CODES:
            errs.append(f"{w}: not an institutional code")
        if p.get("classification") not in PROVIDER_CLASSES:
            errs.append(f"{w}: classification must be one of {PROVIDER_CLASSES}")
        if p.get("rendered") is not False:
            errs.append(f"{w}: provider values are never rendered as the governing value")
        if not p.get("provider") or not p.get("comparison_state") or not p.get("comparison_date"):
            errs.append(f"{w}: provider, comparison_state and comparison_date required")
    return errs


# ---------------------------------------------------------------------------
# precision: a direct value keeps the issuer's published precision; a derived
# value never shows more digits than its weakest input supports.
# ---------------------------------------------------------------------------

def published_uncertainty(value: str) -> float:
    d = Decimal(value)
    return 0.5 * float(Decimal(1).scaleb(d.as_tuple().exponent)) / float(d)


def sig_for(u: float) -> int:
    import math
    if u <= 0:
        return 6
    return max(3, min(6, int(math.floor(-math.log10(u)))))


def format_published(value: str) -> str:
    return f"{Decimal(value):,f}"


def freshness(source_ts: str, captured_at: str, policy: Dict[str, Any]) -> str:
    if policy.get("cadence") not in ("daily_business", "daily_published_by_period"):
        return "unavailable"
    age_h = (_ts(captured_at) - _ts(source_ts)).total_seconds() / 3600.0
    if age_h < -policy.get("advance_publication_hours", 0):
        return "unavailable"
    if age_h <= policy["current_max_hours"]:
        return "current"
    if age_h <= policy["recent_max_hours"]:
        return "recent"
    return "stale"


def usable_value(snap: Dict[str, Any], code: str) -> Optional[Dict[str, Any]]:
    """The publishable, non-stale direct issuer value for a code (deterministic choice)."""
    if snap.get("activation_state") != "source_activated":
        return None
    ins = snap.get("instruments", {}).get(code)
    if not ins or ins.get("value_decision") != "issuer_value_activated":
        return None
    srcs = {s["id"]: s for s in snap.get("sources", [])}
    policy = snap.get("freshness_policies", {}).get(ins["freshness_policy_id"], {})
    for v in sorted(snap.get("values", []), key=lambda x: x["source_timestamp"], reverse=True):
        if v["instrument_code"] != code or v["derived"] is not False:
            continue
        src = srcs.get(v["source_id"])
        if not src or src.get("license_state") not in PUBLISHABLE_LICENSES or v["license_state"] != src["license_state"]:
            continue
        if not v.get("methodology_id") or not v.get("provenance_id") or not v.get("valuation_date"):
            continue
        state = freshness(v["source_timestamp"], snap["captured_at"], policy)
        if state in ("current", "recent"):
            return {"value": v, "freshness": state, "source": src, "policy": policy}
    return None


def value_view(from_code: str, to_code: str, snap: Dict[str, Any], fx: Dict[str, Any], format_value) -> Dict[str, Any]:
    """What may be shown for an institutional pair. 'unavailable' unless every provenance,
    licence, freshness and skew rule is satisfied for every input."""
    unavailable = {"value_type": "unavailable", "derived": None}
    fi, ti = from_code in INSTITUTIONAL_CODES, to_code in INSTITUTIONAL_CODES
    if fi and ti:
        return unavailable  # institutional-to-institutional: only a governed issuer parity could apply (none stored)
    unit, other = (from_code, to_code) if fi else (to_code, from_code)
    u = usable_value(snap, unit)
    if not u:
        return unavailable
    v = u["value"]
    denom = v["denomination_currency"]
    base = {"issuer": v["issuer"], "issuer_source": u["source"]["name"], "valuation_date": v["valuation_date"],
            "issuer_timestamp": v["source_timestamp"], "freshness": u["freshness"],
            "methodology_id": v["methodology_id"], "provenance_id": v["provenance_id"]}
    if other == denom and fi:
        return dict(base, value_type=v["valuation_type"], derived=False, derivation_method=None,
                    value_text=format_published(v["value"]))
    if other == denom:
        x = 1.0 / float(v["value"])
        return dict(base, value_type="derived_reference_value", derived=True, derivation_method="inverse_of_issuer_value",
                    value_text=format_value(x, sig_for(published_uncertainty(v["value"]))))
    rates = fx.get("rates", {})
    if denom not in rates or other not in rates or not fx.get("captured_at"):
        return unavailable
    skew_h = abs((_ts(fx["captured_at"]) - _ts(v["source_timestamp"])).total_seconds()) / 3600.0
    if skew_h > u["policy"].get("max_fx_skew_hours", 0):
        return unavailable
    fx_u = sum(published_uncertainty(repr(float(rates[c]))) if rates[c] != 1 else 0.0 for c in (denom, other))
    in_other = float(v["value"]) * float(rates[other]) / float(rates[denom])
    x = in_other if fi else 1.0 / in_other
    return dict(base, value_type="derived_reference_value", derived=True,
                derivation_method="issuer_value_times_fx_cross" if fi else "inverse_of_issuer_value_times_fx_cross",
                value_text=format_value(x, sig_for(published_uncertainty(v["value"]) + fx_u)),
                fx_source=fx.get("source"), fx_timestamp=fx["captured_at"])
