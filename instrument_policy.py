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
        want = {"unit_of_account": "national_monetary_authority", "regional_unit": "regional_institution",
                "special_instrument": "supranational_institution"}[t]
        if r["issuer_type"] != want:
            e.append(f"{t} requires issuer_type {want}")
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
            return "provider_rate_pending_issuer_source"
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
