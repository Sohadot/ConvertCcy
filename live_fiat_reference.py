#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
live_fiat_reference.py — SEO-A4.6A live-fiat coverage model and value gate.

data/live_fiat_reference_snapshot.json governs active fiat codes that the FX
reference provider does not publish (the residual unsupported cohort after
A4.2–A4.5: currently KPW and VED). It is separate from data/rate_snapshot.json
(never modified here), from the metal snapshot and from the institutional snapshot.

Scope rule (fail-closed, enforced by validate()): a covered code must be an active
fiat_currency / restricted_fiat_currency in data/instrument_classification.json
and must have NO value in data/rate_snapshot.json. A code with a provider value
(e.g. CUP, IRR, MMK, SYP, TMT, VES) can therefore never enter this layer; regime
governance for those codes is A4.6B.

A numeric value may render only when every gate passes:
  1. snapshot activation_state is source_activated;
  2. the code's availability_status is live_verified or live_caveated;
  3. the value's rate_regime is identified (official_reference | market_reference)
     and agrees with the code's rate_regime;
  4. the source tier is authoritative for that regime (official: issuer or
     official republisher; market: licensed market data or issuer) — never
     secondary press, a standards registry or the generic FX provider;
  5. the source licence permits publication and matches the value's licence;
  6. valuation date, source timestamp, retrieval time and provenance id are present
     and retrieval is not before the source timestamp;
  7. the value is current or recent under its freshness policy.
Otherwise value_view() returns value_type "unavailable" (the current state).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parent
LIVE_FIAT_SNAPSHOT_FILE = REPO / "data" / "live_fiat_reference_snapshot.json"

PUBLISHABLE_LICENSES = ("redistribution_permitted", "attribution_required")
ACTIVATION_STATES = ("reference_layer_only", "source_activated")
LIVE_AVAILABILITY = ("live_verified", "live_caveated")
VALUE_REGIMES = ("official_reference", "market_reference")
REGIME_SOURCE_TIERS = {"official_reference": ("issuer", "official_republisher"),
                       "market_reference": ("licensed_market_data", "issuer")}
ELIGIBLE_INSTRUMENT_TYPES = ("fiat_currency", "restricted_fiat_currency")
VALUE_TYPES = VALUE_REGIMES + ("derived_reference_value", "unavailable")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CURRENCY_FIELDS = ("currency_code", "display_name", "issuer_or_authority", "issuer_source_state", "instrument_role",
                   "rate_regime", "availability_status", "decision_label", "classification_confidence", "review_flags",
                   "provider_value", "provider_regime_status", "official_reference_value", "market_reference_value",
                   "value_source", "freshness_policy", "license_state", "identity_claims", "coverage_claims",
                   "reported_indicators", "explanations", "decision_reason", "faq")
EXPLANATION_KEYS = ("what", "value_status", "regime", "activation")
VALUE_FIELDS = ("currency_code", "quote_currency", "rate_regime", "value", "valuation_date", "source_id",
                "source_timestamp", "retrieved_at", "license_state", "freshness_policy", "provenance_id", "derived")
SOURCE_FIELDS = ("id", "title", "url", "authority", "source_tier", "accessed", "access_state", "license_state", "role")
UNAVAILABLE = {"value_type": "unavailable", "derived": None}


def _no_dupes(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError(f"duplicate key {k!r}")
        out[k] = v
    return out


def load_live_fiat_snapshot(path: Path = LIVE_FIAT_SNAPSHOT_FILE) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_dupes)


def _ts(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def covered_codes(snap: Dict[str, Any]) -> List[str]:
    return sorted(snap.get("currencies", {}))


# ---------------------------------------------------------------------------
# validation (fail-closed)
# ---------------------------------------------------------------------------

def validate_live_fiat_snapshot(snap: Any, classification: Optional[Dict[str, Any]] = None,
                                fx: Optional[Dict[str, Any]] = None) -> List[str]:
    errs: List[str] = []
    if not isinstance(snap, dict):
        return ["snapshot is not an object"]
    if snap.get("type") != "live_fiat_reference_snapshot" or snap.get("schema_version") != 1:
        errs.append("type/schema_version must be live_fiat_reference_snapshot / 1")
    enums = snap.get("enums", {})
    for k in ("availability_status", "rate_regime", "instrument_role", "provider_regime_status", "source_tier",
              "access_state", "license_state"):
        if not isinstance(enums.get(k), list) or not enums[k]:
            errs.append(f"enums.{k} missing")
    state = snap.get("activation_state")
    if state not in ACTIVATION_STATES:
        errs.append("activation_state must be reference_layer_only or source_activated")
    values = snap.get("values")
    if not isinstance(values, list):
        errs.append("values must be a list")
        values = []
    if state == "reference_layer_only":
        if values:
            errs.append("reference_layer_only carries no values")
        if snap.get("captured_at") is not None:
            errs.append("captured_at must be null while no value exists (no fabricated timestamp)")
    elif state == "source_activated":
        if not isinstance(snap.get("captured_at"), str) or not TS_RE.match(snap["captured_at"]):
            errs.append("source_activated requires captured_at (YYYY-MM-DDTHH:MM:SSZ)")
    policies = snap.get("freshness_policies", {})
    for pid, p in policies.items():
        for k in ("current_max_hours", "recent_max_hours", "max_fx_skew_hours"):
            if not isinstance(p.get(k), (int, float)) or p[k] <= 0:
                errs.append(f"freshness policy {pid}: {k} must be positive")
        if p.get("current_max_hours", 0) > p.get("recent_max_hours", 0):
            errs.append(f"freshness policy {pid}: current window exceeds recent window")

    srcs: Dict[str, Dict[str, Any]] = {}
    for s in snap.get("sources", []):
        miss = [f for f in SOURCE_FIELDS if f not in s]
        if miss:
            errs.append(f"source {s.get('id')}: missing {miss}")
            continue
        if s["id"] in srcs:
            errs.append(f"duplicate source id {s['id']}")
        srcs[s["id"]] = s
        if not str(s["url"]).startswith("https://"):
            errs.append(f"source {s['id']}: url must be https")
        if s["source_tier"] not in enums.get("source_tier", []):
            errs.append(f"source {s['id']}: unknown source_tier {s['source_tier']!r}")
        if s["access_state"] not in enums.get("access_state", []):
            errs.append(f"source {s['id']}: unknown access_state {s['access_state']!r}")
        if s["license_state"] is not None and s["license_state"] not in enums.get("license_state", []):
            errs.append(f"source {s['id']}: unknown license_state {s['license_state']!r}")
        if not DATE_RE.match(str(s["accessed"])):
            errs.append(f"source {s['id']}: accessed must be YYYY-MM-DD")
        if s["source_tier"] == "secondary_press" and s["license_state"] in PUBLISHABLE_LICENSES:
            errs.append(f"source {s['id']}: secondary press can never be a publishable value source")

    instruments = (classification or {}).get("instruments", {})
    fx_rates = (fx or {}).get("rates", {})
    for code, c in sorted(snap.get("currencies", {}).items()):
        p = f"{code}:"
        miss = [f for f in CURRENCY_FIELDS if f not in c]
        if miss:
            errs.append(f"{p} missing fields {miss}")
            continue
        if c["currency_code"] != code:
            errs.append(f"{p} currency_code mismatch")
        for k in ("availability_status", "rate_regime", "instrument_role", "provider_regime_status"):
            if c[k] not in enums.get(k, []):
                errs.append(f"{p} unknown {k} {c[k]!r}")
        # scope rule: an active fiat code with no provider value
        if classification is not None:
            ins = instruments.get(code)
            if not ins:
                errs.append(f"{p} not in instrument_classification.json")
            else:
                if ins["instrument_type"] not in ELIGIBLE_INSTRUMENT_TYPES or ins["instrument_status"] != "active":
                    errs.append(f"{p} out of scope: A4.1 type {ins['instrument_type']}/{ins['instrument_status']}")
                if c["classification_confidence"] != ins["classification_confidence"]:
                    errs.append(f"{p} classification_confidence disagrees with A4.1 ({ins['classification_confidence']!r})")
                if list(c["review_flags"]) != list(ins["review_flags"]):
                    errs.append(f"{p} review_flags disagree with A4.1 {ins['review_flags']!r}")
        if fx is not None and code in fx_rates:
            errs.append(f"{p} out of scope: the FX provider publishes a value (regime governance is A4.6B)")
        # provider fields: no provider value may be promoted
        if c["provider_value"] is not None and c["provider_regime_status"] != "provider_regime_identified":
            errs.append(f"{p} provider value recorded without an identified regime")
        if c["provider_value"] is None and c["provider_regime_status"] != "no_provider_value":
            errs.append(f"{p} provider_regime_status must be no_provider_value when no provider value exists")
        # claims cite resolvable sources; secondary press only as reported indicators
        for group in ("identity_claims", "coverage_claims", "reported_indicators"):
            for cl in c[group]:
                src = srcs.get(cl.get("source"))
                if not cl.get("text") or not src:
                    errs.append(f"{p} {group} claim without text or resolvable source")
                    continue
                if group == "reported_indicators" and src["source_tier"] != "secondary_press":
                    errs.append(f"{p} reported indicator must cite secondary press")
                if group != "reported_indicators" and src["source_tier"] == "secondary_press":
                    errs.append(f"{p} {group}: secondary press may support only reported indicators")
                if group == "identity_claims" and src["access_state"] != "accessible":
                    errs.append(f"{p} identity claim cites a source that was not accessible")
                if re.search(r"\d[\d,.]*\s*(won|KPW|VED|VES|bol)", cl["text"], re.I) and group == "reported_indicators":
                    errs.append(f"{p} reported indicator states a rate figure")
        if not c["identity_claims"]:
            errs.append(f"{p} no registry-cited identity claim")
        if not c["coverage_claims"]:
            errs.append(f"{p} no provider-coverage claim")
        ex = c["explanations"]
        if not isinstance(ex, dict) or any(not ex.get(k) for k in EXPLANATION_KEYS):
            errs.append(f"{p} explanations need {EXPLANATION_KEYS}")
        if not c["decision_label"] or not c["decision_reason"]:
            errs.append(f"{p} decision_label and decision_reason required")
        if not c["faq"] or any(not f.get("q") or not f.get("a") for f in c["faq"]):
            errs.append(f"{p} faq entries need q and a")
        if c["issuer_or_authority"] is None and c["issuer_source_state"] == "accessible":
            errs.append(f"{p} accessible issuer source without a named issuer")
        live = c["availability_status"] in LIVE_AVAILABILITY
        if live:
            if state != "source_activated":
                errs.append(f"{p} live availability requires source_activated")
            if c["rate_regime"] not in VALUE_REGIMES + ("multiple_regimes_verified",):
                errs.append(f"{p} live availability requires an identified rate regime")
            for k in ("value_source", "freshness_policy", "license_state"):
                if not c[k]:
                    errs.append(f"{p} live availability requires {k}")
            if c["freshness_policy"] and c["freshness_policy"] not in policies:
                errs.append(f"{p} unknown freshness_policy {c['freshness_policy']!r}")
            if c["value_source"] and c["value_source"] not in srcs:
                errs.append(f"{p} value_source does not resolve")
        else:
            for k in ("official_reference_value", "market_reference_value", "value_source", "freshness_policy",
                      "license_state"):
                if c[k] is not None:
                    errs.append(f"{p} {k} must be null while availability is {c['availability_status']}")
        if c["instrument_role"] == "transitional_iso_code":
            op = c.get("operative_code")
            if not op or (classification is not None and op not in instruments):
                errs.append(f"{p} transitional code needs a resolvable operative_code")

    for i, v in enumerate(values):
        p = f"values[{i}]:"
        miss = [f for f in VALUE_FIELDS if f not in v]
        if miss:
            errs.append(f"{p} missing {miss}")
            continue
        if v["currency_code"] not in snap.get("currencies", {}):
            errs.append(f"{p} value for an uncovered code")
        if v["derived"] is not False:
            errs.append(f"{p} stored values are never derived")
        if v["rate_regime"] not in VALUE_REGIMES:
            errs.append(f"{p} rate_regime must be one of {VALUE_REGIMES}")
        try:
            if Decimal(str(v["value"])) <= 0 or not isinstance(v["value"], str):
                errs.append(f"{p} value must be a positive decimal string")
        except InvalidOperation:
            errs.append(f"{p} value must be a decimal string")
        for k in ("source_timestamp", "retrieved_at"):
            if not TS_RE.match(str(v[k])):
                errs.append(f"{p} {k} must be YYYY-MM-DDTHH:MM:SSZ")
        if not DATE_RE.match(str(v["valuation_date"])):
            errs.append(f"{p} valuation_date must be YYYY-MM-DD")
        if TS_RE.match(str(v["source_timestamp"])) and TS_RE.match(str(v["retrieved_at"])) \
                and _ts(v["retrieved_at"]) < _ts(v["source_timestamp"]):
            errs.append(f"{p} retrieved_at precedes source_timestamp")
        src = srcs.get(v["source_id"])
        if not src:
            errs.append(f"{p} source does not resolve")
        else:
            if src["source_tier"] not in REGIME_SOURCE_TIERS.get(v["rate_regime"], ()):
                errs.append(f"{p} source tier {src['source_tier']} cannot support {v['rate_regime']}")
            if src["license_state"] not in PUBLISHABLE_LICENSES or v["license_state"] != src["license_state"]:
                errs.append(f"{p} licence does not permit publication or disagrees with its source")
        if v["freshness_policy"] not in policies:
            errs.append(f"{p} unknown freshness_policy")
        if not v["provenance_id"]:
            errs.append(f"{p} provenance_id required")
    return errs


# ---------------------------------------------------------------------------
# value gate
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
    age_h = (_ts(captured_at) - _ts(source_ts)).total_seconds() / 3600.0
    if age_h < 0:
        return "unavailable"
    if age_h <= policy["current_max_hours"]:
        return "current"
    if age_h <= policy["recent_max_hours"]:
        return "recent"
    return "stale"


def usable_value(snap: Dict[str, Any], code: str) -> Optional[Dict[str, Any]]:
    """The publishable, non-stale value for a covered code, or None (fail-closed)."""
    if snap.get("activation_state") != "source_activated" or not snap.get("captured_at"):
        return None
    cur = snap.get("currencies", {}).get(code)
    if not cur or cur.get("availability_status") not in LIVE_AVAILABILITY:
        return None
    srcs = {s["id"]: s for s in snap.get("sources", [])}
    policies = snap.get("freshness_policies", {})
    for v in sorted(snap.get("values", []), key=lambda x: (x.get("source_timestamp") or ""), reverse=True):
        if v.get("currency_code") != code or v.get("derived") is not False:
            continue
        regime = v.get("rate_regime")
        if regime not in VALUE_REGIMES or cur["rate_regime"] not in (regime, "multiple_regimes_verified"):
            continue
        src = srcs.get(v.get("source_id"))
        if not src or src.get("source_tier") not in REGIME_SOURCE_TIERS[regime]:
            continue
        if src.get("license_state") not in PUBLISHABLE_LICENSES or v.get("license_state") != src["license_state"]:
            continue
        if not v.get("provenance_id") or not v.get("valuation_date") or not v.get("source_timestamp") \
                or not v.get("retrieved_at") or not v.get("quote_currency"):
            continue
        if _ts(v["retrieved_at"]) < _ts(v["source_timestamp"]):
            continue
        policy = policies.get(v.get("freshness_policy"))
        if not policy:
            continue
        state = freshness(v["source_timestamp"], snap["captured_at"], policy)
        if state in ("current", "recent"):
            return {"value": v, "freshness": state, "source": src, "policy": policy}
    return None


def value_view(from_code: str, to_code: str, snap: Dict[str, Any], fx: Dict[str, Any], format_value) -> Dict[str, Any]:
    """What may be shown for a live-fiat pair: 'unavailable' unless every gate passes."""
    cov = snap.get("currencies", {})
    fc, tc = from_code in cov, to_code in cov
    if fc and tc:
        return dict(UNAVAILABLE)   # both sides uncovered by the provider: no governed cross exists
    if not (fc or tc):
        return dict(UNAVAILABLE)
    code, other = (from_code, to_code) if fc else (to_code, from_code)
    u = usable_value(snap, code)
    if not u:
        return dict(UNAVAILABLE)
    v = u["value"]
    quote = v["quote_currency"]
    base = {"rate_regime": v["rate_regime"], "source": u["source"]["authority"], "source_url": u["source"]["url"],
            "valuation_date": v["valuation_date"], "source_timestamp": v["source_timestamp"],
            "freshness": u["freshness"], "provenance_id": v["provenance_id"],
            "license_state": v["license_state"]}
    if other == quote and fc:
        return dict(base, value_type=v["rate_regime"], derived=False, derivation_method=None,
                    value_text=format_published(v["value"]))
    if other == quote:
        x = 1.0 / float(v["value"])
        return dict(base, value_type="derived_reference_value", derived=True, derivation_method="inverse",
                    value_text=format_value(x, sig_for(published_uncertainty(v["value"]))))
    rates = (fx or {}).get("rates", {})
    if quote not in rates or other not in rates or not (fx or {}).get("captured_at"):
        return dict(UNAVAILABLE)
    skew_h = abs((_ts(fx["captured_at"]) - _ts(v["source_timestamp"])).total_seconds()) / 3600.0
    if skew_h > u["policy"]["max_fx_skew_hours"]:
        return dict(UNAVAILABLE)
    fx_u = sum(published_uncertainty(repr(float(rates[c]))) if rates[c] != 1 else 0.0 for c in (quote, other))
    in_other = float(v["value"]) * float(rates[other]) / float(rates[quote])
    x = in_other if fc else 1.0 / in_other
    return dict(base, value_type="derived_reference_value", derived=True,
                derivation_method="value_times_fx_cross" if fc else "inverse_of_value_times_fx_cross",
                value_text=format_value(x, sig_for(published_uncertainty(v["value"]) + fx_u)),
                fx_source=fx.get("source"), fx_timestamp=fx["captured_at"])


# ===========================================================================
# SEO-A4.6B — rate-regime governance for provider-valued live fiat
# ===========================================================================
#
# rate_regime_governance in the same snapshot governs active fiat codes that DO have a
# provider value but whose rate regime needs explicit governance (CUP, IRR, MMK, SYP,
# TMT, VES). It never changes the provider value. It records the regimes that exist,
# how the provider value compares with them, and a provider policy:
#   governed_primary          a licensed, issuer-verified regime value powers the page (none yet)
#   secondary_provider_value  provider value powers the converter, labelled with its regime match
#   comparison_only           provider value shown labelled for comparison; no converter
#   suppressed                no number shown (provider regime unresolved / conflicting)
#   unresolved                no number shown pending evidence
# A provider value is trusted only while the FX snapshot is within provider_revalidation_days
# of the audited provider date and within provider_drift_tolerance_pct of the audited value;
# otherwise the policy is downgraded (secondary -> comparison_only; comparison_only ->
# suppressed on drift). Issuer and market figures are never stored while their licence is
# not publishable.

MULTI_REGIME_TYPES = ("multi_segment_official", "official_reference_plus_market_trading",
                      "official_reference_plus_parallel_market")
SECONDARY_TIERS = ("secondary_press", "secondary_analysis", "market_aggregator")
OFFICIAL_ENTRY_TYPES = ("official_reference", "fixed_official_segment", "floating_official_segment",
                        "official_market_trading")
NUMBERLESS_POLICIES = ("suppressed", "unresolved")
REGIME_CURRENCY_FIELDS = ("currency_code", "display_name", "issuer_or_authority", "issuer_source_state", "regime_type",
                          "availability_status", "regimes", "provider", "provider_policy", "decision_reason",
                          "classification_confidence", "review_flags", "identity_claims", "coverage_claims",
                          "regime_claims", "explanations", "faq")
REGIME_FIELDS = ("regime_id", "regime_type", "regime_label", "authority", "source_id", "evidence_state", "valuation_date",
                 "captured_at", "value", "value_withheld_reason", "unit", "freshness_policy", "license_state",
                 "activation_state", "confidence", "notes")
REGIME_EXPLANATION_KEYS = ("what", "provider", "official", "claims_scope")
EVIDENCE_TIERS = {"issuer_verified": ("issuer", "official_republisher"),
                  "secondary_reported": SECONDARY_TIERS,
                  "unverified_copy": ("unverified_official_copy",),
                  "unresolved": ("issuer", "official_republisher", "unverified_official_copy")}


def regime_section(snap: Dict[str, Any]) -> Dict[str, Any]:
    return snap.get("rate_regime_governance") or {}


def regime_codes(snap: Dict[str, Any]) -> List[str]:
    return sorted(regime_section(snap).get("currencies", {}))


def _pct(value: Any) -> Optional[float]:
    try:
        return float(str(value).replace("+", ""))
    except (TypeError, ValueError):
        return None


def validate_rate_regime(snap: Dict[str, Any], classification: Optional[Dict[str, Any]] = None,
                         fx: Optional[Dict[str, Any]] = None) -> List[str]:
    errs: List[str] = []
    sec = regime_section(snap)
    if not sec:
        return []
    enums = snap.get("enums", {})
    for k in ("regime_type", "regime_entry_type", "evidence_state", "provider_regime_match", "provider_policy"):
        if not enums.get(k):
            errs.append(f"enums.{k} missing")
    pol = sec.get("comparison_policy", {})
    for k in ("official_match_tolerance_pct", "material_divergence_pct", "provider_revalidation_days",
              "provider_drift_tolerance_pct", "max_match_date_gap_days"):
        if not isinstance(pol.get(k), (int, float)) or pol[k] <= 0:
            errs.append(f"comparison_policy.{k} must be positive")
    if not pol.get("rationale"):
        errs.append("comparison_policy.rationale required (tolerances must be justified)")
    if pol.get("official_match_tolerance_pct", 0) >= pol.get("material_divergence_pct", 0):
        errs.append("official match tolerance must be below the material-divergence threshold")
    tol = pol.get("official_match_tolerance_pct", 0)
    srcs = {s["id"]: s for s in snap.get("sources", [])}
    policies = snap.get("freshness_policies", {})
    instruments = (classification or {}).get("instruments", {})
    rates = (fx or {}).get("rates", {})
    for code, c in sorted(sec.get("currencies", {}).items()):
        p = f"{code}:"
        miss = [f for f in REGIME_CURRENCY_FIELDS if f not in c]
        if miss:
            errs.append(f"{p} missing fields {miss}")
            continue
        if c["currency_code"] != code:
            errs.append(f"{p} currency_code mismatch")
        if code in snap.get("currencies", {}):
            errs.append(f"{p} also governed by live-fiat coverage (A4.6A); a code belongs to one layer")
        if classification is not None:
            ins = instruments.get(code)
            if not ins:
                errs.append(f"{p} not in instrument_classification.json")
            else:
                if ins["instrument_type"] not in ELIGIBLE_INSTRUMENT_TYPES or ins["instrument_status"] != "active":
                    errs.append(f"{p} out of scope: A4.1 type {ins['instrument_type']}/{ins['instrument_status']}")
                if c["classification_confidence"] != ins["classification_confidence"]:
                    errs.append(f"{p} classification_confidence disagrees with A4.1")
                if list(c["review_flags"]) != list(ins["review_flags"]):
                    errs.append(f"{p} review_flags disagree with A4.1")
        if fx is not None and code not in rates:
            errs.append(f"{p} out of scope: no provider value (missing coverage belongs to A4.6A)")
        for k, enum in (("regime_type", "regime_type"), ("availability_status", "availability_status"),
                        ("provider_policy", "provider_policy")):
            if c[k] not in enums.get(enum, []):
                errs.append(f"{p} unknown {k} {c[k]!r}")
        regs = {r.get("regime_id"): r for r in c["regimes"]}
        if c["regime_type"] in MULTI_REGIME_TYPES and len(regs) < 2:
            errs.append(f"{p} {c['regime_type']} must expose every relevant regime (>= 2)")
        if c["regime_type"] in ("single_official_reference", "fixed_official_reference") and \
                sum(1 for r in regs.values() if r.get("regime_type") in OFFICIAL_ENTRY_TYPES) != 1:
            errs.append(f"{p} {c['regime_type']} must have exactly one official regime")
        for r in c["regimes"]:
            rp = f"{p} regime {r.get('regime_id')}:"
            rmiss = [f for f in REGIME_FIELDS if f not in r]
            if rmiss:
                errs.append(f"{rp} missing {rmiss}")
                continue
            if r["regime_type"] not in enums.get("regime_entry_type", []):
                errs.append(f"{rp} unknown regime_type {r['regime_type']!r}")
            if r["evidence_state"] not in enums.get("evidence_state", []):
                errs.append(f"{rp} unknown evidence_state")
            src = srcs.get(r["source_id"])
            if not src:
                errs.append(f"{rp} source does not resolve")
            elif src["source_tier"] not in EVIDENCE_TIERS.get(r["evidence_state"], ()):
                errs.append(f"{rp} evidence_state {r['evidence_state']} does not fit source tier {src['source_tier']}")
            elif r["evidence_state"] == "issuer_verified" and src["access_state"] != "accessible":
                errs.append(f"{rp} issuer_verified requires an accessible issuer source")
            if r["freshness_policy"] not in policies:
                errs.append(f"{rp} unknown freshness_policy")
            if r["license_state"] not in enums.get("license_state", []):
                errs.append(f"{rp} unknown license_state")
            if r["valuation_date"] is not None and not DATE_RE.match(str(r["valuation_date"])):
                errs.append(f"{rp} valuation_date must be YYYY-MM-DD or null")
            publishable = (r["license_state"] in PUBLISHABLE_LICENSES and r["evidence_state"] == "issuer_verified"
                           and r["activation_state"] == "source_activated" and snap.get("activation_state") == "source_activated")
            if r["value"] is not None and not publishable:
                errs.append(f"{rp} stores a value without a verified, licensed, activated source")
            if r["value"] is None and not r["value_withheld_reason"]:
                errs.append(f"{rp} null value needs value_withheld_reason")
            if r["value"] is not None and (not r["valuation_date"] or not r["captured_at"]):
                errs.append(f"{rp} numeric value without valuation date")
        prov = c["provider"]
        for k in ("provider_value", "provider_as_of", "provider_timestamp", "comparisons", "provider_regime_match",
                  "match_basis", "confidence"):
            if k not in prov:
                errs.append(f"{p} provider.{k} missing")
        match = prov.get("provider_regime_match")
        if match not in enums.get("provider_regime_match", []):
            errs.append(f"{p} unknown provider_regime_match {match!r}")
        if fx is not None and code in rates and prov.get("provider_as_of") == fx.get("as_of"):
            try:
                if Decimal(str(prov["provider_value"])) != Decimal(repr(float(rates[code]))):
                    errs.append(f"{p} recorded provider value differs from data/rate_snapshot.json for the same date")
            except InvalidOperation:
                errs.append(f"{p} provider_value must be a decimal string")
        comps = {x.get("regime_id"): x for x in prov.get("comparisons", [])}
        for rid in comps:
            if rid not in regs:
                errs.append(f"{p} comparison against unknown regime {rid!r}")

        gap = pol.get("max_match_date_gap_days", 0)

        def matched(types, evidence):
            # a match needs the same regime type and evidence, the tolerance, and a bounded
            # provider/source valuation-date gap (null only for undated fixed segments)
            return any(rid in regs and regs[rid]["regime_type"] in types and regs[rid]["evidence_state"] in evidence
                       and _pct(x.get("pct_difference")) is not None and abs(_pct(x["pct_difference"])) <= tol
                       and (x.get("valuation_date_difference_days") is None and regs[rid]["regime_type"] == "fixed_official_segment"
                            or isinstance(x.get("valuation_date_difference_days"), int)
                            and abs(x["valuation_date_difference_days"]) <= gap)
                       for rid, x in comps.items())
        if match == "provider_matches_official_within_tolerance" and \
                not matched(("official_reference",), ("issuer_verified",)):
            errs.append(f"{p} official match needs an issuer-verified official regime within tolerance")
        if match == "provider_matches_reported_official" and \
                not matched(("official_reference",), ("secondary_reported", "unverified_copy")):
            errs.append(f"{p} reported-official match needs a reported official regime within tolerance")
        if match == "provider_matches_reported_official_segment" and \
                not matched(("fixed_official_segment", "floating_official_segment"), ("secondary_reported", "issuer_verified")):
            errs.append(f"{p} segment match needs an official segment within tolerance")
        policy = c["provider_policy"]
        if policy == "secondary_provider_value":
            if match not in ("provider_matches_official_within_tolerance", "provider_matches_reported_official"):
                errs.append(f"{p} a provider value may power a converter only when it matches an official regime")
            if c["regime_type"] in ("multi_segment_official", "official_reference_plus_market_trading"):
                errs.append(f"{p} multiple official regimes: the provider value may not power a converter")
        if match in ("provider_regime_unresolved", "provider_conflicts_with_authoritative_source") and \
                policy not in NUMBERLESS_POLICIES:
            errs.append(f"{p} an unresolved / conflicting provider regime may not show a number")
        if policy == "governed_primary":
            if not any(r.get("value") is not None for r in c["regimes"]):
                errs.append(f"{p} governed_primary requires a published, licensed regime value")
        ex = c["explanations"]
        if not isinstance(ex, dict) or any(not ex.get(k) for k in REGIME_EXPLANATION_KEYS):
            errs.append(f"{p} explanations need {REGIME_EXPLANATION_KEYS}")
        for group in ("identity_claims", "coverage_claims", "regime_claims"):
            for cl in c[group]:
                src = srcs.get(cl.get("source"))
                if not cl.get("text") or not src:
                    errs.append(f"{p} {group} claim without text or resolvable source")
                    continue
                if src["access_state"] != "accessible":
                    errs.append(f"{p} {group} claim cites a source that was not accessible")
                if group != "regime_claims" and src["source_tier"] in SECONDARY_TIERS:
                    errs.append(f"{p} {group}: secondary sources may support only regime claims")
                if src["source_tier"] in SECONDARY_TIERS and not cl["text"].startswith(src["authority"].split(" (")[0]):
                    errs.append(f"{p} secondary claim must name its source ({src['authority']}) as the reporter")
        if not c["identity_claims"] or not c["coverage_claims"]:
            errs.append(f"{p} identity and provider-coverage claims required")
        if not c["faq"] or any(not f.get("q") or not f.get("a") for f in c["faq"]):
            errs.append(f"{p} faq entries need q and a")
        texts = " ".join([ex.get("provider", "")] + [f.get("a", "") for f in c["faq"]])
        if policy != "governed_primary" and re.search(r"provider[^.]*\bis the official rate\b", texts, re.I):
            errs.append(f"{p} provider value described as the official rate")
    return errs


def effective_provider_policy(code: str, snap: Dict[str, Any], fx: Dict[str, Any]) -> Dict[str, Any]:
    """The provider policy that applies to the current FX snapshot (deterministic, fail-closed)."""
    sec = regime_section(snap)
    c = sec["currencies"][code]
    policy = c["provider_policy"]
    out = {"policy": policy, "declared": policy, "reverified": True, "reason": None}
    if policy not in ("secondary_provider_value", "comparison_only"):
        return out
    cp = sec["comparison_policy"]
    rate = (fx or {}).get("rates", {}).get(code)
    if rate is None:
        return dict(out, policy="suppressed", reverified=False, reason="provider_value_missing")
    audited = float(c["provider"]["provider_value"])
    drift = abs(float(rate) - audited) / audited * 100.0
    try:
        age = (datetime.strptime(fx["as_of"], "%Y-%m-%d") - datetime.strptime(c["provider"]["provider_as_of"], "%Y-%m-%d")).days
    except (KeyError, ValueError):
        age = None
    if drift > cp["provider_drift_tolerance_pct"]:
        return dict(out, policy="suppressed" if policy == "comparison_only" else "comparison_only", reverified=False,
                    reason="provider_value_drifted_since_audit")
    if age is None or age < 0 or age > cp["provider_revalidation_days"]:
        return dict(out, policy="comparison_only", reverified=False, reason="regime_match_not_reverified")
    return out


def pair_regime_view(from_code: str, to_code: str, snap: Dict[str, Any], fx: Dict[str, Any]) -> Dict[str, Any]:
    """Combine the governed sides of a pair: a converter only when every governed side permits one;
    no number when any side forbids it; otherwise a labelled comparison value."""
    sec = regime_section(snap).get("currencies", {})
    sides = [c for c in (from_code, to_code) if c in sec]
    eff = {c: effective_provider_policy(c, snap, fx) for c in sides}
    pols = [e["policy"] for e in eff.values()]
    if any(p in NUMBERLESS_POLICIES for p in pols):
        mode = "none"
    elif pols and all(p in ("secondary_provider_value", "governed_primary") for p in pols):
        mode = "converter"
    else:
        mode = "comparison"
    return {"sides": sides, "effective": eff, "mode": mode}
