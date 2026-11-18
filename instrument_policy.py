#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
instrument_policy.py — SEO-A4.1 instrument classification and treatment policy.

Single access layer over data/instrument_classification.json (the authoritative
taxonomy). Generators and validators ask this module, never the raw file:

    what kind of instrument is this?        resolve(code)["instrument_type"]
    what page should be rendered?           resolve(code)["page_role"]
    which sources are acceptable?           resolve(code)["source_policy"]
    should it behave like a converter?      resolve(code)["converter_behavior"]
    how should a pair page be treated?      resolve_pair(a, b)

data/currencies.json stays the identity layer (names, symbols, numeric codes).
Its legacy `instrument_type` label is reconciled here: any departure from
`legacy_type_mapping` must carry an explicit `reclassification_reason`.

CLI:
    python3 instrument_policy.py --write-matrix   # rebuild the derived matrix
    python3 instrument_policy.py --check          # validate + matrix drift check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent
CLASSIFICATION_FILE = REPO / "data" / "instrument_classification.json"
CURRENCIES_FILE = REPO / "data" / "currencies.json"
SNAPSHOT_FILE = REPO / "data" / "rate_snapshot.json"
MATRIX_FILE = REPO / "data" / "generated" / "instrument_policy_matrix.json"

EXPECTED_CODE_COUNT = 170
CONVERTER_ORDER = ["standard", "caveated", "valuation_only", "archival_only", "none"]

# Hard anchors the taxonomy may never contradict (SEO-A4.1 §13).
ANCHORS = {
    "XTS": {"test_code"},
    "XXX": {"no_currency"},
    "XAU": {"precious_metal"}, "XAG": {"precious_metal"},
    "XPT": {"precious_metal"}, "XPD": {"precious_metal"},
    "XUA": {"unit_of_account", "regional_unit", "special_instrument"},
    "XSU": {"unit_of_account", "regional_unit", "special_instrument"},
    "UYW": {"unit_of_account", "regional_unit", "special_instrument"},
    "CUC": {"historical_currency", "legacy_transition"},
    "SVC": {"historical_currency", "legacy_transition"},
    "KPW": {"fiat_currency", "restricted_fiat_currency"},
    "VED": {"fiat_currency", "restricted_fiat_currency"},
}

REQUIRED_FIELDS = {
    "instrument_type": "enum", "instrument_status": "enum", "circulation_status": "enum",
    "legal_tender_status": "enum", "convertibility_status": "enum", "issuer_type": "enum",
    "issuer_name": "str_or_null", "jurisdiction_scope": "enum",
    "market_pricing_expected": "bool", "reference_rate_expected": "bool",
    "historical": "bool", "active": "bool", "classification_confidence": "enum",
    "evidence": "enum_list", "review_flags": "enum_list", "successor_code": "str_or_null",
    "documented_conversion": "obj_or_null", "reclassification_reason": "str_or_null",
    "notes": "str_or_null",
}

TYPE_POLICY_FIELDS = ("definition", "page_role", "converter_behavior", "rate_policy",
                      "source_policy", "hub_indexability", "pair_indexability", "commercial_role")


class ClassificationError(ValueError):
    pass


def _no_dupes(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ClassificationError(f"duplicate key {k!r}")
        out[k] = v
    return out


def _load(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_no_dupes)


def load_raw(path: Path = CLASSIFICATION_FILE) -> Dict[str, Any]:
    return _load(path)


def _currencies() -> Dict[str, Any]:
    return _load(CURRENCIES_FILE)["currencies"]


def _snapshot_codes() -> set:
    try:
        return set(_load(SNAPSHOT_FILE)["rates"])
    except FileNotFoundError:
        return set()


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def validate(doc: Dict[str, Any], currencies: Optional[Dict[str, Any]] = None,
             snapshot_codes: Optional[set] = None) -> List[str]:
    """Return every rule violation (empty list = valid). Fails closed."""
    errs: List[str] = []
    currencies = currencies if currencies is not None else _currencies()
    snapshot_codes = snapshot_codes if snapshot_codes is not None else _snapshot_codes()

    for key in ("meta", "enums", "indexability_order", "legacy_type_mapping", "type_policies", "instruments"):
        if key not in doc:
            errs.append(f"missing top-level key {key!r}")
    if errs:
        return errs
    enums = doc["enums"]
    types = enums.get("instrument_type", [])
    pols = doc["type_policies"]
    inst = doc["instruments"]

    # enums for policy-level fields
    if sorted(doc["indexability_order"]) != sorted(enums.get("indexability", [])):
        errs.append("indexability_order must list every indexability value exactly once")
    if set(pols) != set(types):
        errs.append(f"type_policies keys {sorted(pols)} != instrument_type enum {sorted(types)}")
    for t, p in pols.items():
        for f in TYPE_POLICY_FIELDS:
            if f not in p or p[f] in (None, "", []):
                errs.append(f"type_policies.{t}: missing {f}")
        if p.get("page_role") not in enums.get("page_role", []):
            errs.append(f"type_policies.{t}: page_role {p.get('page_role')!r} not in enum")
        if p.get("converter_behavior") not in enums.get("converter_behavior", []):
            errs.append(f"type_policies.{t}: converter_behavior invalid")
        if p.get("rate_policy") not in enums.get("rate_policy", []):
            errs.append(f"type_policies.{t}: rate_policy invalid")
        for f in ("hub_indexability", "pair_indexability"):
            if p.get(f) not in enums.get("indexability", []):
                errs.append(f"type_policies.{t}: {f} {p.get(f)!r} invalid")
        for s in p.get("source_policy") or []:
            if s not in enums.get("source_class", []):
                errs.append(f"type_policies.{t}: source class {s!r} not in enum")
        for r in p.get("commercial_role") or []:
            if r not in enums.get("commercial_role", []):
                errs.append(f"type_policies.{t}: commercial role {r!r} not in enum")
    no_auto_noindex = {"precious_metal", "historical_currency", "unit_of_account", "regional_unit",
                       "special_instrument", "fiat_currency", "restricted_fiat_currency", "legacy_transition"}
    for t in no_auto_noindex & set(pols):
        for f in ("hub_indexability", "pair_indexability"):
            if pols[t].get(f) == "candidate_for_noindex":
                errs.append(f"type_policies.{t}: {f} must not default to candidate_for_noindex")

    # code coverage
    codes = set(inst)
    cur_codes = {c.upper() for c in currencies}
    if len(inst) != EXPECTED_CODE_COUNT:
        errs.append(f"expected {EXPECTED_CODE_COUNT} classified codes, found {len(inst)}")
    if codes != cur_codes:
        errs.append(f"code set mismatch: missing={sorted(cur_codes - codes)} extra={sorted(codes - cur_codes)}")

    mapping = doc["legacy_type_mapping"]
    for code, r in inst.items():
        where = f"instruments.{code}"
        for f, kind in REQUIRED_FIELDS.items():
            if f not in r:
                errs.append(f"{where}: missing field {f}")
                continue
            v = r[f]
            if kind == "enum" and v not in enums.get(f, []):
                errs.append(f"{where}: {f}={v!r} not in enum")
            elif kind == "bool" and not isinstance(v, bool):
                errs.append(f"{where}: {f} must be boolean")
            elif kind == "str_or_null" and not (v is None or (isinstance(v, str) and v.strip())):
                errs.append(f"{where}: {f} must be a non-empty string or null")
            elif kind == "obj_or_null" and not (v is None or isinstance(v, dict)):
                errs.append(f"{where}: {f} must be an object or null")
            elif kind == "enum_list":
                if not isinstance(v, list) or len(set(v)) != len(v) or any(x not in enums.get(f, []) for x in v):
                    errs.append(f"{where}: {f} must be a duplicate-free list of enum values")
        extra = set(r) - set(REQUIRED_FIELDS)
        if extra:
            errs.append(f"{where}: unknown fields {sorted(extra)}")
        if any(f not in r for f in REQUIRED_FIELDS):
            continue
        t = r["instrument_type"]
        errs.extend(f"{where}: {m}" for m in _combination_errors(code, r, cur_codes))
        if not r["evidence"]:
            errs.append(f"{where}: evidence must not be empty")
        # snapshot evidence must match reality (re-review forced on coverage change)
        if "repo_rate_snapshot_quote" in r["evidence"] and code not in snapshot_codes:
            errs.append(f"{where}: claims a snapshot quote but the snapshot has none")
        if "repo_rate_snapshot_no_quote" in r["evidence"] and code in snapshot_codes:
            errs.append(f"{where}: claims no snapshot quote but the snapshot has one")
        if ("repo_rate_snapshot_quote" in r["evidence"]) == ("repo_rate_snapshot_no_quote" in r["evidence"]):
            errs.append(f"{where}: evidence must state exactly one of repo_rate_snapshot_quote / _no_quote")
        # reconcile with the legacy identity-layer label
        legacy = currencies.get(code, {}).get("instrument_type")
        if legacy not in mapping:
            errs.append(f"{where}: legacy instrument_type {legacy!r} has no mapping")
        elif mapping[legacy] != t and not r["reclassification_reason"]:
            errs.append(f"{where}: reclassified {legacy} -> {t} without reclassification_reason")
        elif mapping[legacy] == t and r["reclassification_reason"] and legacy == t:
            errs.append(f"{where}: reclassification_reason set but type is unchanged")
        if code in ANCHORS and t not in ANCHORS[code]:
            errs.append(f"{where}: anchored code must be one of {sorted(ANCHORS[code])}, got {t}")
        if r["classification_confidence"] != "high" and not r["notes"]:
            errs.append(f"{where}: non-high confidence requires notes explaining the uncertainty")
    errs.extend(_historical_reference_errors(doc))
    errs.extend(_standards_reference_errors(doc))
    errs.extend(_metals_reference_errors(doc))
    errs.extend(_institutional_reference_errors(doc))
    return errs


INSTITUTIONAL_TYPES = ("unit_of_account", "regional_unit", "special_instrument")
INSTITUTIONAL_EXPLANATION_KEYS = ("what", "not_this", "valuation", "value_status")
INSTITUTIONAL_GOVERNANCE_KEYS = ("official_valuation_source", "methodology", "update_frequency", "publication_schedule",
                                 "unit_definition", "reference_basket", "historical_continuity", "redistribution")
INSTITUTIONAL_UNIT_KEYS = ("display_name", "short_name", "classification_label", "issuer_display", "issuer_role", "pair_role",
                           "title_role", "h1_role", "activity_status", "valuation_type", "value_decision", "decision_label",
                           "related_unit", "iso_designation", "activity_claims", "reported_indicators", "claims",
                           "licensing_claims", "explanations", "source_governance", "faq")
# Which value decision each label may carry (A4.5 §48-§51).
INSTITUTIONAL_DECISION_LABELS = {
    "issuer_value_activated": ("IMF VALUE ACTIVATED", "OFFICIAL CLF VALUE ACTIVATED", "OFFICIAL UYW VALUE ACTIVATED",
                               "XUA VALUATION ACTIVATED"),
    "issuer_methodology_only": ("IMF REFERENCE ONLY", "METHODOLOGY ONLY", "REFERENCE ONLY"),
    "reference_layer_only": ("SDR-RELATIONSHIP REFERENCE ONLY", "STATUS UNRESOLVED", "REFERENCE ONLY"),
}


def _source_tier(doc: Dict[str, Any], cite: Dict[str, Any]) -> Optional[str]:
    entries = doc.get("verification_sources", {}).get(cite.get("source"), [])
    i = cite.get("index")
    return entries[i].get("source_tier", "primary") if isinstance(i, int) and 0 <= i < len(entries) else None


def _institutional_reference_errors(doc: Dict[str, Any]) -> List[str]:
    """SEO-A4.5: institutional-unit facts are registry-cited; status and valuation decisions are explicit."""
    import re as _re
    inst = doc.get("instruments", {})
    codes = {c for c, r in inst.items() if r.get("instrument_type") in INSTITUTIONAL_TYPES}
    ir = doc.get("institutional_units_reference")
    if ir is None:
        return ["missing institutional_units_reference section"] if codes else []
    errs: List[str] = []
    units = ir.get("units") or {}
    if set(units) != codes:
        errs.append(f"institutional_units_reference.units {sorted(units)} != institutional codes {sorted(codes)}")
    for code, u in units.items():
        w = f"institutional_units_reference.units.{code}"
        r = inst.get(code, {})
        if set(u) != set(INSTITUTIONAL_UNIT_KEYS):
            errs.append(f"{w}: keys must be exactly {sorted(INSTITUTIONAL_UNIT_KEYS)} (diff {sorted(set(u) ^ set(INSTITUTIONAL_UNIT_KEYS))})")
            continue
        for k in ("display_name", "short_name", "classification_label", "title_role", "h1_role", "decision_label"):
            if not isinstance(u[k], str) or not u[k].strip():
                errs.append(f"{w}: {k} required")
        if u["pair_role"] not in ir.get("pair_roles", []) or u["pair_role"] == "institutional_relative_reference":
            errs.append(f"{w}: pair_role invalid")
        if u["activity_status"] not in ir.get("activity_statuses", []):
            errs.append(f"{w}: activity_status invalid")
        if u["valuation_type"] not in ir.get("valuation_types", []) or u["valuation_type"] == "derived_reference_value":
            errs.append(f"{w}: valuation_type must be a stored (non-derived) valuation type")
        if u["value_decision"] not in ir.get("value_decisions", []):
            errs.append(f"{w}: value_decision invalid")
        elif u["decision_label"] not in INSTITUTIONAL_DECISION_LABELS[u["value_decision"]]:
            errs.append(f"{w}: decision_label {u['decision_label']!r} contradicts value_decision {u['value_decision']}")
        if u["related_unit"] is not None and u["related_unit"] not in units:
            errs.append(f"{w}: related_unit must be another institutional code")
        # issuer: shown only when the record names one and status is not unresolved
        if u["issuer_display"] != r.get("issuer_name"):
            errs.append(f"{w}: issuer_display must equal the instrument record issuer_name")
        if u["activity_status"] == "status_unresolved":
            if u["activity_claims"]:
                errs.append(f"{w}: an unresolved status cannot carry activity claims")
            if u["value_decision"] != "reference_layer_only" or u["valuation_type"] != "unavailable":
                errs.append(f"{w}: an unresolved status allows only reference_layer_only / unavailable")
            if r.get("classification_confidence") == "high":
                errs.append(f"{w}: an unresolved status cannot carry high classification confidence")
        elif u["activity_status"] == "active" and not u["activity_claims"]:
            errs.append(f"{w}: an active status needs at least one cited activity claim")
        if u["value_decision"] == "issuer_methodology_only" and not u["claims"]:
            errs.append(f"{w}: issuer_methodology_only requires cited methodology claims")
        errs.extend(_cited_claim_errors(doc, f"{w}.iso_designation", u["iso_designation"], verbatim=True))
        for group in ("activity_claims", "claims", "licensing_claims", "reported_indicators"):
            for k, cl in enumerate(u[group] or []):
                errs.extend(_cited_claim_errors(doc, f"{w}.{group}[{k}]", cl))
                tiers = {_source_tier(doc, c) for c in cl.get("cites") or []}
                if group == "reported_indicators":
                    if tiers != {"secondary_press"}:
                        errs.append(f"{w}.reported_indicators[{k}]: must cite secondary_press sources only")
                    if "report" not in cl.get("text", ""):
                        errs.append(f"{w}.reported_indicators[{k}]: must be worded as a report")
                elif tiers != {"primary"}:
                    errs.append(f"{w}.{group}[{k}]: issuer statements must cite primary sources only")
        ex = u["explanations"] or {}
        if set(ex) != set(INSTITUTIONAL_EXPLANATION_KEYS):
            errs.append(f"{w}: explanations must define exactly {list(INSTITUTIONAL_EXPLANATION_KEYS)}")
        for k, v in ex.items():
            if not v or _re.search(r"\d", v.replace("ISO 4217", "ISO")):
                errs.append(f"{w}.explanations.{k}: must be figure-free policy wording")
        if _re.search(r"\bcirculat(es|ing) (currency|money)\b", " ".join(ex.values()).replace("not a circulating", "")):
            errs.append(f"{w}: explanations must not describe the unit as circulating money")
        sg = u["source_governance"] or {}
        if set(sg) != set(INSTITUTIONAL_GOVERNANCE_KEYS) or any(not isinstance(v, str) or not v for v in sg.values()):
            errs.append(f"{w}: source_governance must define {list(INSTITUTIONAL_GOVERNANCE_KEYS)} as non-empty strings")
        groups = {"claim": u["claims"], "activity": u["activity_claims"], "reported": u["reported_indicators"],
                  "licensing": u["licensing_claims"]}
        qs = [f.get("q") for f in u["faq"] or []]
        if not qs or len(set(qs)) != len(qs):
            errs.append(f"{w}: faq must be a non-empty list of distinct questions")
        for k, f in enumerate(u["faq"] or []):
            parts = f.get("a") or []
            if not parts:
                errs.append(f"{w}.faq[{k}]: answer parts required")
            for part in parts:
                kind, _, ref = str(part).partition(":")
                if kind == "ex":
                    ok = ref in ex
                elif kind in groups:
                    ok = ref.isdigit() and int(ref) < len(groups[kind])
                else:
                    ok = False
                if not ok:
                    errs.append(f"{w}.faq[{k}]: answer part {part!r} does not resolve to governed content")
    return errs


METAL_TYPE = "precious_metal"
METAL_ACTIVATION_STATES = ("reference_layer_only", "source_activated")
METAL_EXPLANATION_KEYS = ("what", "not_this", "benchmark_vs_dealer", "derived")


def _cited_claim_errors(doc: Dict[str, Any], where: str, claim: Dict[str, Any], verbatim: bool = False) -> List[str]:
    import re as _re
    sups = [_cited_supports(doc, c) for c in (claim or {}).get("cites") or []]
    if not (claim or {}).get("text") or not sups or any(x is None for x in sups):
        return [f"{where}: needs text and resolvable registry citations"]
    cited = " ".join(sups)
    errs = []
    if verbatim and claim["text"] not in cited:
        errs.append(f"{where}: must quote the cited statement verbatim")
    for num in _re.findall(r"\d[\d,./-]*\d|\d", claim["text"].replace("ISO 4217", "ISO")):
        if num.replace(",", "") not in cited.replace(",", ""):
            errs.append(f"{where}: figure {num!r} is not in the cited source statements")
    return errs


def _metals_reference_errors(doc: Dict[str, Any]) -> List[str]:
    """SEO-A4.4: metal facts are registry-cited; pricing activation is explicit."""
    import re as _re
    inst = doc.get("instruments", {})
    codes = {c for c, r in inst.items() if r.get("instrument_type") == METAL_TYPE}
    pm = doc.get("precious_metals_reference")
    if pm is None:
        return ["missing precious_metals_reference section"] if codes else []
    errs: List[str] = []
    metals = pm.get("metals") or {}
    if set(metals) != codes:
        errs.append(f"precious_metals_reference.metals {sorted(metals)} != precious_metal codes {sorted(codes)}")
    for code, m in metals.items():
        w = f"precious_metals_reference.metals.{code}"
        if not m.get("metal_name"):
            errs.append(f"{w}: missing metal_name")
        errs.extend(_cited_claim_errors(doc, f"{w}.iso_designation", m.get("iso_designation"), verbatim=True))
        for k, cl in enumerate(m.get("claims") or []):
            errs.extend(_cited_claim_errors(doc, f"{w}.claims[{k}]", cl))
    unit = pm.get("unit") or {}
    if unit.get("iso_unit_stated") is not False:
        errs.append("precious_metals_reference.unit: ISO 4217 states no unit; iso_unit_stated must be false")
    if not unit.get("convention_text") or _re.search(r"\d", unit.get("convention_text", "").replace("ISO 4217", "ISO")):
        errs.append("precious_metals_reference.unit.convention_text must be figure-free policy wording")
    errs.extend(_cited_claim_errors(doc, "precious_metals_reference.unit.troy_ounce_definition", unit.get("troy_ounce_definition")))
    if unit.get("gram_conversion_published") not in (True, False):
        errs.append("precious_metals_reference.unit.gram_conversion_published must be boolean")
    pricing = pm.get("pricing") or {}
    if pricing.get("activation_state") not in METAL_ACTIVATION_STATES:
        errs.append(f"precious_metals_reference.pricing.activation_state must be one of {METAL_ACTIVATION_STATES}")
    if not pricing.get("reason_text") or _re.search(r"\d", pricing.get("reason_text", "")):
        errs.append("precious_metals_reference.pricing.reason_text must be figure-free policy wording")
    for k, cl in enumerate(pricing.get("licensing_claims") or []):
        errs.extend(_cited_claim_errors(doc, f"precious_metals_reference.pricing.licensing_claims[{k}]", cl))
    if not pricing.get("licensing_claims"):
        errs.append("precious_metals_reference.pricing: licensing_claims required")
    ex = pm.get("explanations") or {}
    if set(ex) != set(METAL_EXPLANATION_KEYS):
        errs.append(f"precious_metals_reference.explanations must define exactly {list(METAL_EXPLANATION_KEYS)}")
    for k, v in ex.items():
        if not v or _re.search(r"\d", v.replace("ISO 4217", "ISO")):
            errs.append(f"precious_metals_reference.explanations.{k}: must be figure-free policy wording")
    return errs


STANDARDS_TYPES = ("test_code", "no_currency")
STANDARDS_EXPLANATION_KEYS = ("what", "why_exists", "not_this", "no_rate", "implementation", "pair_role")


def _standards_reference_errors(doc: Dict[str, Any]) -> List[str]:
    """SEO-A4.3: XTS/XXX public facts must be registry-cited; explanations carry no figures."""
    import re as _re
    errs: List[str] = []
    inst = doc.get("instruments", {})
    codes = {c for c, r in inst.items() if r.get("instrument_type") in STANDARDS_TYPES}
    sr = doc.get("standards_reference")
    if sr is None:
        return ["missing standards_reference section"] if codes else []
    if set(sr) != codes:
        errs.append(f"standards_reference codes {sorted(sr)} != test/no-currency codes {sorted(codes)}")
    for code, e in sr.items():
        where = f"standards_reference.{code}"
        for k in ("code_role", "badge", "title_role", "iso_designation", "claims", "explanations"):
            if not e.get(k):
                errs.append(f"{where}: missing {k}")
        entries = [e.get("iso_designation") or {}] + list(e.get("claims") or [])
        for k, claim in enumerate(entries):
            sups = [_cited_supports(doc, c) for c in claim.get("cites") or []]
            if not claim.get("text") or not sups or any(x is None for x in sups):
                errs.append(f"{where}[{k}]: needs text and resolvable registry citations")
                continue
            cited = " ".join(sups)
            if k == 0 and claim["text"] not in cited:
                errs.append(f"{where}: ISO designation must quote the cited statement verbatim")
            # the standard's own name is not a figure
            for num in _re.findall(r"\d[\d,./-]*\d|\d", claim["text"].replace("ISO 4217", "ISO")):
                if num.replace(",", "") not in cited.replace(",", ""):
                    errs.append(f"{where}[{k}]: figure {num!r} is not in the cited source statements")
        ex = e.get("explanations") or {}
        if set(ex) != set(STANDARDS_EXPLANATION_KEYS):
            errs.append(f"{where}: explanations must define exactly {list(STANDARDS_EXPLANATION_KEYS)}")
        for k, v in ex.items():
            if not v or _re.search(r"\d", v.replace("ISO 4217", "ISO")):
                errs.append(f"{where}.explanations.{k}: must be non-empty policy wording without figures")
    return errs


HISTORICAL_TYPES = ("historical_currency", "legacy_transition")


def _cited_supports(doc: Dict[str, Any], cite: Dict[str, Any]) -> Optional[str]:
    """Return the cited 'supports' string if the citation resolves exactly, else None."""
    reg = doc.get("verification_sources", {})
    entries = reg.get(cite.get("source"), [])
    i = cite.get("index")
    if not isinstance(i, int) or not (0 <= i < len(entries)):
        return None
    entry = entries[i]
    if not entry.get("url") or not entry.get("authority"):
        return None
    sup = cite.get("supports")
    return sup if sup in (entry.get("supports") or []) else None


def _historical_reference_errors(doc: Dict[str, Any]) -> List[str]:
    """SEO-A4.2: public historical facts must be registry-cited, verified and consistent."""
    import re as _re
    errs: List[str] = []
    hr = doc.get("historical_reference")
    inst = doc.get("instruments", {})
    hist_codes = {c for c, r in inst.items() if r.get("instrument_type") in HISTORICAL_TYPES}
    if hr is None:
        return ["missing historical_reference section"] if hist_codes else []
    if set(hr) != hist_codes:
        errs.append(f"historical_reference codes {sorted(hr)} != historical/legacy codes {sorted(hist_codes)}")
    kinds = doc.get("enums", {}).get("fixed_conversion_kind", [])
    for code, h in hr.items():
        where = f"historical_reference.{code}"
        r = inst.get(code, {})
        extra = set(h) - {"claims", "fixed_conversion", "unverified_note"}
        if extra:
            errs.append(f"{where}: unknown fields {sorted(extra)}")
        for k, claim in enumerate(h.get("claims") or []):
            cites = claim.get("cites") or []
            sups = [_cited_supports(doc, c) for c in cites]
            if not claim.get("text") or not cites or any(s is None for s in sups):
                errs.append(f"{where}.claims[{k}]: every claim needs text and resolvable registry citations")
                continue
            cited = " ".join(sups)
            for num in _re.findall(r"\d[\d,./-]*\d|\d", claim["text"]):
                if num.replace(",", "") not in cited.replace(",", ""):
                    errs.append(f"{where}.claims[{k}]: figure {num!r} is not in the cited source statements")
        fc = h.get("fixed_conversion")
        dc = r.get("documented_conversion")
        if fc is not None:
            if fc.get("kind") not in kinds:
                errs.append(f"{where}: fixed_conversion.kind invalid")
            pair = {fc.get("base_code"), fc.get("quote_code")}
            if pair != {code, r.get("successor_code")}:
                errs.append(f"{where}: fixed conversion must relate {code} and its successor {r.get('successor_code')}")
            sups = [_cited_supports(doc, c) for c in fc.get("cites") or []]
            if not sups or any(s is None for s in sups):
                errs.append(f"{where}: fixed conversion needs resolvable registry citations")
            else:
                cited = " ".join(sups).replace(",", "")
                for f in ("base_units", "quote_units"):
                    v = str(fc.get(f, "")).replace(",", "")
                    if v != "1" and v not in cited:  # a unit amount is implicit in "per X" wording
                        errs.append(f"{where}: fixed conversion {f}={fc.get(f)!r} not in the cited statement")
            if not dc or dc.get("verification_status") != "verified":
                errs.append(f"{where}: fixed conversion requires a verified documented_conversion")
            else:
                want = dc.get("units_per_successor") or dc.get("successor_units_per_code")
                have = fc["quote_units"] if fc.get("base_code") == r.get("successor_code") else fc["base_units"]
                other = fc["quote_units"] if fc.get("base_code") == code else None
                if dc.get("successor_units_per_code"):
                    have = other
                if str(want).replace(",", "") != str(have).replace(",", ""):
                    errs.append(f"{where}: fixed conversion figure disagrees with documented_conversion ({have} vs {want})")
    return errs


def _combination_errors(code: str, r: Dict[str, Any], site_codes: set) -> List[str]:
    e: List[str] = []
    t = r["instrument_type"]
    if r["active"] != (r["instrument_status"] == "active"):
        e.append("active must be true iff instrument_status == 'active'")
    if r["historical"] == r["active"]:
        e.append("historical must be the negation of active")
    if t in ("fiat_currency", "restricted_fiat_currency"):
        if not r["active"]:
            e.append(f"{t} must be active")
        if r["legal_tender_status"] not in ("legal_tender", "unknown"):
            e.append(f"{t} must be legal tender (or unknown)")
        if r["circulation_status"] not in ("circulating", "unknown"):
            e.append(f"{t} must be circulating (or unknown)")
        if r["issuer_type"] not in ("national_monetary_authority", "currency_union_authority"):
            e.append(f"{t} needs a monetary-authority issuer_type")
        if not r["reference_rate_expected"]:
            e.append(f"{t} must expect a reference rate")
    if t == "fiat_currency" and r["convertibility_status"] == "non_convertible":
        e.append("a non_convertible fiat currency must be classified restricted_fiat_currency")
    if t == "restricted_fiat_currency" and r["convertibility_status"] not in ("restricted", "non_convertible"):
        e.append("restricted_fiat_currency requires convertibility restricted or non_convertible")
    if t == "precious_metal":
        if (r["issuer_type"], r["jurisdiction_scope"]) != ("no_issuer", "global_commodity"):
            e.append("precious_metal requires issuer_type no_issuer and jurisdiction_scope global_commodity")
        if r["legal_tender_status"] != "not_applicable" or not r["market_pricing_expected"] or not r["active"]:
            e.append("precious_metal must be active, market-priced and not legal tender")
    if t in ("unit_of_account", "regional_unit", "special_instrument"):
        if r["circulation_status"] != "not_circulating" or r["legal_tender_status"] != "not_legal_tender":
            e.append(f"{t} must be non-circulating and not legal tender")
        if r["market_pricing_expected"]:
            e.append(f"{t} is valued by its issuer, not market-priced")
        # SEO-A4.5: a statutory unit may be administered by a national statistical authority (UYW / INE).
        want = {"unit_of_account": ("national_monetary_authority", "national_statistical_authority"),
                "regional_unit": ("regional_institution",),
                "special_instrument": ("supranational_institution",)}[t]
        if r["issuer_type"] not in want:
            e.append(f"{t} requires issuer_type {' or '.join(want)}")
    if t in ("historical_currency", "legacy_transition"):
        want_status = "withdrawn" if t == "historical_currency" else "superseded"
        if r["instrument_status"] != want_status or r["active"]:
            e.append(f"{t} requires instrument_status {want_status} and active=false")
        if r["reference_rate_expected"] or r["market_pricing_expected"]:
            e.append(f"{t} must not expect a live/market reference rate")
        if not r["successor_code"]:
            e.append(f"{t} requires successor_code")
        if t == "historical_currency" and r["legal_tender_status"] != "not_legal_tender":
            e.append("historical_currency must not be legal tender")
    if t in ("test_code", "no_currency"):
        if r["reference_rate_expected"] or r["market_pricing_expected"]:
            e.append(f"{t} never has a rate")
        if r["issuer_type"] != "not_applicable" or r["legal_tender_status"] != "not_applicable":
            e.append(f"{t} has no issuer and no legal-tender status")
    succ = r["successor_code"]
    if succ and t not in ("historical_currency", "legacy_transition"):
        e.append("successor_code is only valid for historical/legacy instruments")
    if succ and succ not in site_codes and "successor_not_in_site_set" not in r["review_flags"]:
        e.append(f"successor {succ} is not in the site set and is not flagged successor_not_in_site_set")
    dc = r["documented_conversion"]
    if dc is not None:
        if dc.get("to") != succ:
            e.append("documented_conversion.to must equal successor_code")
        if dc.get("verification_status") not in ("requires_source_verification", "verified"):
            e.append("documented_conversion.verification_status invalid")
    return e


# --------------------------------------------------------------------------
# resolution (the access layer generators use)
# --------------------------------------------------------------------------

class InstrumentPolicy:
    def __init__(self, doc: Optional[Dict[str, Any]] = None, *, validate_doc: bool = True,
                 currencies: Optional[Dict[str, Any]] = None, snapshot_codes: Optional[set] = None):
        self.doc = doc if doc is not None else load_raw()
        self.currencies = currencies if currencies is not None else _currencies()
        self.snapshot_codes = snapshot_codes if snapshot_codes is not None else _snapshot_codes()
        if validate_doc:
            errs = validate(self.doc, self.currencies, self.snapshot_codes)
            if errs:
                raise ClassificationError(f"{len(errs)} classification errors, e.g. {errs[:3]}")
        self._order = self.doc["indexability_order"]

    def codes(self) -> List[str]:
        return sorted(self.doc["instruments"])

    def resolve(self, code: str) -> Dict[str, Any]:
        code = code.upper()
        if code not in self.doc["instruments"]:
            raise KeyError(f"unclassified code {code!r}")
        r = self.doc["instruments"][code]
        p = self.doc["type_policies"][r["instrument_type"]]
        covered = code in self.snapshot_codes
        return {
            "code": code,
            "name": self.currencies.get(code, {}).get("display_name", code),
            "instrument_type": r["instrument_type"],
            "page_role": p["page_role"],
            "converter_behavior": p["converter_behavior"],
            "rate_policy": p["rate_policy"],
            "source_policy": list(p["source_policy"]),
            "hub_indexability": p["hub_indexability"],
            "pair_indexability": p["pair_indexability"],
            "commercial_role": list(p["commercial_role"]),
            "reference_rate_expected": r["reference_rate_expected"],
            "current_rate_coverage": covered,
            "active": r["active"],
            "classification_confidence": r["classification_confidence"],
            "review_flags": list(r["review_flags"]),
            "policy_conformance": self._conformance(r, p, covered),
        }

    @staticmethod
    def _conformance(r: Dict[str, Any], p: Dict[str, Any], covered: bool) -> str:
        expected = r["reference_rate_expected"]
        if expected and not covered:
            return "rate_source_missing"
        if not expected and covered:
            if r["instrument_type"] in HISTORICAL_TYPES:
                # SEO-A4.2: the provider observation is preserved in the snapshot, but
                # pages render the historical reference instead of a current rate.
                return "provider_value_present_but_policy_disallows_live_use"
            return "rate_shown_contrary_to_policy"
        if expected and covered and p["rate_policy"] == "official_reference_with_regime_caveat":
            return "rate_shown_without_regime_caveat"
        if expected and covered and p["rate_policy"] == "issuer_published_valuation":
            # SEO-A4.5: the provider value stays in the raw FX snapshot but is never rendered as the
            # governing value; issuer comparison state lives in data/institutional_reference_snapshot.json.
            return "provider_value_secondary_only"
        return "conformant"

    def is_historical(self, code: str) -> bool:
        return self.resolve(code)["instrument_type"] in HISTORICAL_TYPES

    def historical_view(self, code: str) -> Dict[str, Any]:
        """Render-ready, verified-only facts for a historical/legacy code (SEO-A4.2).

        Only registry-cited claims are returned; a fixed conversion is returned
        only when its documented_conversion is verified. Status and successor come
        from the classification record.
        """
        code = code.upper()
        r = self.doc["instruments"][code]
        if r["instrument_type"] not in HISTORICAL_TYPES:
            raise ValueError(f"{code} is not a historical or legacy instrument")
        h = self.doc.get("historical_reference", {}).get(code, {})
        reg = self.doc.get("verification_sources", {})

        def sources(cites):
            out = []
            for c in cites:
                if _cited_supports(self.doc, c) is None:
                    raise ClassificationError(f"{code}: unresolvable citation {c}")
                e = reg[c["source"]][c["index"]]
                item = {"authority": e["authority"], "url": e["url"]}
                if item not in out:
                    out.append(item)
            return out

        claims = [{"text": c["text"], "sources": sources(c["cites"])} for c in h.get("claims") or []]
        fc = h.get("fixed_conversion")
        dc = r.get("documented_conversion") or {}
        fixed = None
        if fc and dc.get("verification_status") == "verified":
            fixed = {
                "kind": fc["kind"],
                "statement": f'{fc["base_code"]} {fc["base_units"]} = {fc["quote_code"]} {fc["quote_units"]}',
                "base_code": fc["base_code"], "base_units": fc["base_units"],
                "quote_code": fc["quote_code"], "quote_units": fc["quote_units"],
                "sources": sources(fc["cites"]),
            }
        succ = r["successor_code"]
        return {
            "code": code,
            "name": self.currencies.get(code, {}).get("display_name", code),
            "instrument_type": r["instrument_type"],
            "status_label": "HISTORICAL" if r["instrument_type"] == "historical_currency" else "LEGACY",
            "instrument_status": r["instrument_status"],
            "legal_tender_status": r["legal_tender_status"],
            "circulation_status": r["circulation_status"],
            "successor_code": succ,
            "successor_name": self.currencies.get(succ, {}).get("display_name") if succ else None,
            "successor_in_site": bool(succ and succ in self.currencies),
            "issuer_name": r["issuer_name"],
            "claims": claims,
            "fixed_conversion": fixed,
            "unverified_note": h.get("unverified_note"),
        }

    def is_standards_special(self, code: str) -> bool:
        return self.resolve(code)["instrument_type"] in STANDARDS_TYPES

    def standards_view(self, code: str) -> Dict[str, Any]:
        """Render-ready, registry-cited facts for an ISO 4217 special code (SEO-A4.3)."""
        code = code.upper()
        r = self.doc["instruments"][code]
        if r["instrument_type"] not in STANDARDS_TYPES:
            raise ValueError(f"{code} is not an ISO 4217 test/no-currency code")
        e = self.doc["standards_reference"][code]
        reg = self.doc.get("verification_sources", {})

        def sources(cites):
            out = []
            for c in cites:
                if _cited_supports(self.doc, c) is None:
                    raise ClassificationError(f"{code}: unresolvable citation {c}")
                ent = reg[c["source"]][c["index"]]
                item = {"authority": ent["authority"], "url": ent["url"]}
                if item not in out:
                    out.append(item)
            return out

        return {
            "code": code,
            "name": self.currencies.get(code, {}).get("display_name", code),
            "instrument_type": r["instrument_type"],
            "code_role": e["code_role"],
            "badge": e["badge"],
            "title_role": e["title_role"],
            "iso_designation": {"text": e["iso_designation"]["text"], "sources": sources(e["iso_designation"]["cites"])},
            "claims": [{"text": c["text"], "sources": sources(c["cites"])} for c in e["claims"]],
            "explanations": dict(e["explanations"]),
            "pair_indexability": self.doc["type_policies"][r["instrument_type"]]["pair_indexability"],
            "hub_indexability": self.doc["type_policies"][r["instrument_type"]]["hub_indexability"],
        }

    def is_precious_metal(self, code: str) -> bool:
        return self.resolve(code)["instrument_type"] == METAL_TYPE

    def metal_view(self, code: str) -> Dict[str, Any]:
        """Render-ready, registry-cited facts for a precious-metal code (SEO-A4.4)."""
        code = code.upper()
        if not self.is_precious_metal(code):
            raise ValueError(f"{code} is not a precious-metal code")
        pm = self.doc["precious_metals_reference"]
        m = pm["metals"][code]
        reg = self.doc.get("verification_sources", {})

        def cited(claim):
            out = []
            for c in claim["cites"]:
                if _cited_supports(self.doc, c) is None:
                    raise ClassificationError(f"{code}: unresolvable citation {c}")
                ent = reg[c["source"]][c["index"]]
                item = {"authority": ent["authority"], "url": ent["url"]}
                if item not in out:
                    out.append(item)
            return {"text": claim["text"], "sources": out}

        fill = {"S": code, "metal": m["metal_name"].lower()}
        return {
            "code": code,
            "metal_name": m["metal_name"],
            "name": self.currencies.get(code, {}).get("display_name", code),
            "instrument_type": METAL_TYPE,
            "iso_designation": cited(m["iso_designation"]),
            "claims": [cited(c) for c in m["claims"]],
            "unit_convention": pm["unit"]["convention_text"],
            "troy_ounce_definition": cited(pm["unit"]["troy_ounce_definition"]),
            "gram_conversion_published": pm["unit"]["gram_conversion_published"],
            "activation_state": pm["pricing"]["activation_state"],
            "pricing_reason": pm["pricing"]["reason_text"],
            "licensing_claims": [cited(c) for c in pm["pricing"]["licensing_claims"]],
            "explanations": {k: v.format(**fill) for k, v in pm["explanations"].items()},
            "pair_indexability": self.doc["type_policies"][METAL_TYPE]["pair_indexability"],
            "hub_indexability": self.doc["type_policies"][METAL_TYPE]["hub_indexability"],
        }

    def is_institutional_unit(self, code: str) -> bool:
        return self.resolve(code)["instrument_type"] in INSTITUTIONAL_TYPES

    def institutional_view(self, code: str) -> Dict[str, Any]:
        """Render-ready, registry-cited facts for an institutional unit (SEO-A4.5)."""
        code = code.upper()
        if not self.is_institutional_unit(code):
            raise ValueError(f"{code} is not an institutional unit")
        u = self.doc["institutional_units_reference"]["units"][code]
        r = self.doc["instruments"][code]
        reg = self.doc.get("verification_sources", {})

        def cited(claim):
            out = []
            for c in claim["cites"]:
                if _cited_supports(self.doc, c) is None:
                    raise ClassificationError(f"{code}: unresolvable citation {c}")
                ent = reg[c["source"]][c["index"]]
                item = {"authority": ent["authority"], "url": ent["url"]}
                if item not in out:
                    out.append(item)
            return {"text": claim["text"], "sources": out}

        groups = {"claim": [cited(c) for c in u["claims"]],
                  "activity": [cited(c) for c in u["activity_claims"]],
                  "reported": [cited(c) for c in u["reported_indicators"]],
                  "licensing": [cited(c) for c in u["licensing_claims"]]}
        ex = dict(u["explanations"])

        def answer(parts):
            out = []
            for part in parts:
                kind, _, ref = part.partition(":")
                out.append(ex[ref] if kind == "ex" else groups[kind][int(ref)]["text"])
            return " ".join(out)

        policy = self.doc["type_policies"][r["instrument_type"]]
        return {
            "code": code,
            "name": self.currencies.get(code, {}).get("display_name", code),
            "instrument_type": r["instrument_type"],
            "classification_confidence": r["classification_confidence"],
            "issuer_type": r["issuer_type"],
            **{k: u[k] for k in ("display_name", "short_name", "classification_label", "issuer_display", "issuer_role",
                                 "pair_role", "title_role", "h1_role", "activity_status", "valuation_type",
                                 "value_decision", "decision_label", "related_unit")},
            "source_governance": dict(u["source_governance"]),
            "iso_designation": cited(u["iso_designation"]),
            "claims": groups["claim"],
            "activity_claims": groups["activity"],
            "reported_indicators": groups["reported"],
            "licensing_claims": groups["licensing"],
            "explanations": ex,
            "faq": [{"q": f["q"], "a": answer(f["a"])} for f in u["faq"]],
            "pair_indexability": policy["pair_indexability"],
            "hub_indexability": policy["hub_indexability"],
        }

    def is_ordinary_converter(self, code: str) -> bool:
        return self.resolve(code)["converter_behavior"] == "standard"

    def resolve_pair(self, from_code: str, to_code: str) -> Dict[str, Any]:
        a, b = self.resolve(from_code), self.resolve(to_code)
        pair_idx = max((a["pair_indexability"], b["pair_indexability"]), key=self._order.index)
        conv = max((a["converter_behavior"], b["converter_behavior"]), key=CONVERTER_ORDER.index)
        driver = a if CONVERTER_ORDER.index(a["converter_behavior"]) >= CONVERTER_ORDER.index(b["converter_behavior"]) else b
        return {
            "pair": f"{a['code']}_{b['code']}",
            "pair_indexability": pair_idx,
            "converter_behavior": conv,
            "governing_side": driver["code"],
            "governing_page_role": driver["page_role"],
            "reference_rate_expected": a["reference_rate_expected"] and b["reference_rate_expected"],
            "current_rate_coverage": a["current_rate_coverage"] and b["current_rate_coverage"],
        }

    # ---------------------------------------------------------------- matrix
    def build_matrix(self) -> Dict[str, Any]:
        codes = self.codes()
        resolved = {c: self.resolve(c) for c in codes}
        by_type: Dict[str, List[str]] = {}
        for c in codes:
            by_type.setdefault(resolved[c]["instrument_type"], []).append(c)
        pair_idx: Dict[str, int] = {}
        pair_conv: Dict[str, int] = {}
        for a in codes:
            for b in codes:
                if a == b:
                    continue
                rp = self.resolve_pair(a, b)
                pair_idx[rp["pair_indexability"]] = pair_idx.get(rp["pair_indexability"], 0) + 1
                pair_conv[rp["converter_behavior"]] = pair_conv.get(rp["converter_behavior"], 0) + 1
        conformance: Dict[str, List[str]] = {}
        for c in codes:
            conformance.setdefault(resolved[c]["policy_conformance"], []).append(c)
        return {
            "provenance": {
                "generated_by": "instrument_policy.py --write-matrix",
                "source": "data/instrument_classification.json",
                "joined_with": ["data/currencies.json (names)", "data/rate_snapshot.json (coverage only)"],
                "taxonomy_version": self.doc["meta"]["taxonomy_version"],
                "note": "Derived artifact. Never hand-edit; rebuild and commit.",
            },
            "type_matrix": {
                t: {k: self.doc["type_policies"][t][k] for k in TYPE_POLICY_FIELDS if k != "definition"}
                | {"codes": by_type.get(t, []), "count": len(by_type.get(t, []))}
                for t in self.doc["enums"]["instrument_type"]
            },
            "code_matrix": {c: {k: v for k, v in resolved[c].items() if k != "code"} for c in codes},
            "pair_cohorts": {
                "total_directed_pairs": sum(pair_idx.values()),
                "by_pair_indexability": dict(sorted(pair_idx.items())),
                "by_converter_behavior": dict(sorted(pair_conv.items())),
            },
            "policy_conformance": {k: v for k, v in sorted(conformance.items())},
        }


def matrix_text(policy: Optional[InstrumentPolicy] = None) -> str:
    policy = policy or InstrumentPolicy()
    return json.dumps(policy.build_matrix(), ensure_ascii=False, indent=1) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Instrument classification policy layer")
    ap.add_argument("--write-matrix", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    doc = load_raw()
    errs = validate(doc)
    if errs:
        print(f"FAIL: {len(errs)} classification errors")
        for e in errs[:50]:
            print(f"  - {e}")
        return 1
    text = matrix_text(InstrumentPolicy(doc, validate_doc=False))
    if args.write_matrix:
        MATRIX_FILE.parent.mkdir(parents=True, exist_ok=True)
        MATRIX_FILE.write_text(text, encoding="utf-8")
        print(f"Wrote {MATRIX_FILE.relative_to(REPO)}")
    if args.check:
        if not MATRIX_FILE.exists() or MATRIX_FILE.read_text(encoding="utf-8") != text:
            print("FAIL: data/generated/instrument_policy_matrix.json is stale — run: python3 instrument_policy.py --write-matrix")
            return 1
        print("PASS: classification valid and policy matrix current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
