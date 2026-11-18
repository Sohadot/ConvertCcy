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
            return "rate_shown_contrary_to_policy"
        if expected and covered and p["rate_policy"] == "official_reference_with_regime_caveat":
            return "rate_shown_without_regime_caveat"
        if expected and covered and p["rate_policy"] == "issuer_published_valuation":
            return "provider_rate_pending_issuer_source"
        return "conformant"

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
