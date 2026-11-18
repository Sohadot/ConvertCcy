#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEO-A4.1 — instrument classification and treatment-policy layer."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import instrument_policy as ip  # noqa: E402

DOC = ip.load_raw()
POLICY = ip.InstrumentPolicy(DOC)
CURRENCIES = json.loads((REPO / "data" / "currencies.json").read_text(encoding="utf-8"))["currencies"]


def mutated(fn):
    d = copy.deepcopy(DOC)
    fn(d)
    return ip.validate(d)


class CoverageTest(unittest.TestCase):
    def test_A_every_code_classified(self):
        self.assertEqual(len(DOC["instruments"]), 170)
        self.assertEqual(set(DOC["instruments"]), set(CURRENCIES))
        self.assertEqual(ip.validate(DOC), [])

    def test_B_no_duplicate_classification(self):
        text = (REPO / "data" / "instrument_classification.json").read_text(encoding="utf-8")
        dup = text.replace('"instruments": {', '"instruments": {\n  "XTS": {},', 1)
        with self.assertRaises(ip.ClassificationError):
            json.loads(dup, object_pairs_hook=ip._no_dupes)
        types = [r["instrument_type"] for r in DOC["instruments"].values()]
        self.assertTrue(all(isinstance(t, str) for t in types))  # exactly one primary type each

    def test_C_enums_valid(self):
        enums = DOC["enums"]
        for code, r in DOC["instruments"].items():
            for f in ("instrument_type", "instrument_status", "circulation_status", "legal_tender_status",
                      "convertibility_status", "issuer_type", "jurisdiction_scope", "classification_confidence"):
                self.assertIn(r[f], enums[f], (code, f))
        for t, p in DOC["type_policies"].items():
            self.assertIn(p["page_role"], enums["page_role"])
            self.assertTrue(set(p["source_policy"]) <= set(enums["source_class"]))
            self.assertTrue(set(p["commercial_role"]) <= set(enums["commercial_role"]))
            self.assertTrue(p["commercial_role"] and p["source_policy"])


class AnchorTest(unittest.TestCase):
    def t(self, code):
        return POLICY.resolve(code)["instrument_type"]

    def test_D_xts(self):
        self.assertEqual(self.t("XTS"), "test_code")
        self.assertEqual(POLICY.resolve("XTS")["page_role"], "iso_standards_reference")

    def test_E_xxx(self):
        self.assertEqual(self.t("XXX"), "no_currency")
        self.assertEqual(POLICY.resolve("XXX")["page_role"], "iso_semantics_reference")

    def test_F_metals(self):
        for c in ("XAU", "XAG", "XPT", "XPD"):
            self.assertEqual(self.t(c), "precious_metal")
            self.assertEqual(POLICY.resolve(c)["rate_policy"], "dedicated_metal_benchmark_required")

    def test_G_units_not_fiat(self):
        for c in ("XUA", "XSU", "UYW"):
            self.assertNotIn(self.t(c), ("fiat_currency", "restricted_fiat_currency"))
            self.assertFalse(POLICY.is_ordinary_converter(c))

    def test_H_cuc_svc_historical_or_legacy(self):
        self.assertEqual(self.t("CUC"), "historical_currency")
        self.assertEqual(self.t("SVC"), "legacy_transition")
        for c in ("CUC", "SVC"):
            self.assertFalse(POLICY.resolve(c)["reference_rate_expected"])

    def test_I_kpw_ved_real_currencies(self):
        self.assertEqual(self.t("KPW"), "restricted_fiat_currency")
        self.assertEqual(self.t("VED"), "fiat_currency")
        for c in ("KPW", "VED"):
            r = POLICY.resolve(c)
            self.assertTrue(r["reference_rate_expected"])
            self.assertTrue(r["active"])
            self.assertEqual(r["policy_conformance"], "rate_source_missing")

    def test_special_set_wider_than_unsupported_set(self):
        # ANG, BGN, HRK, ZWL, SLL have provider quotes but are not ordinary fiat
        for c in ("ANG", "BGN", "HRK", "ZWL", "SLL"):
            r = POLICY.resolve(c)
            self.assertNotEqual(r["instrument_type"], "fiat_currency")
            self.assertEqual(r["policy_conformance"], "provider_value_present_but_policy_disallows_live_use")


class ResolutionTest(unittest.TestCase):
    def test_J_deterministic(self):
        a = ip.matrix_text(ip.InstrumentPolicy(DOC))
        b = ip.matrix_text(ip.InstrumentPolicy(copy.deepcopy(DOC)))
        self.assertEqual(a, b)
        self.assertEqual(ip.MATRIX_FILE.read_text(encoding="utf-8"), a)
        self.assertEqual(POLICY.resolve_pair("USD", "XTS"), POLICY.resolve_pair("USD", "XTS"))

    def test_J_pair_resolution_most_restrictive(self):
        self.assertEqual(POLICY.resolve_pair("USD", "EUR")["pair_indexability"], "index")
        self.assertEqual(POLICY.resolve_pair("USD", "XAU")["pair_indexability"], "index_with_specialized_reference_role")
        self.assertEqual(POLICY.resolve_pair("XAU", "XTS")["pair_indexability"], "candidate_for_consolidation")
        p = POLICY.resolve_pair("HRK", "USD")
        self.assertEqual((p["converter_behavior"], p["governing_side"]), ("archival_only", "HRK"))
        cohorts = json.loads(ip.MATRIX_FILE.read_text())["pair_cohorts"]
        self.assertEqual(cohorts["total_directed_pairs"], 28730)
        self.assertNotIn("candidate_for_noindex", cohorts["by_pair_indexability"])

    def test_L_generator_access_layer(self):
        cases = {"USD": ("fx_converter_reference", "standard"), "KPW": ("restricted_currency_reference", "caveated"),
                 "XAU": ("precious_metal_reference", "valuation_only"), "CLF": ("institutional_unit_dossier", "valuation_only"),
                 "XDR": ("supranational_instrument_dossier", "valuation_only"), "HRK": ("historical_currency_dossier", "archival_only"),
                 "SVC": ("legacy_currency_dossier", "archival_only"), "XTS": ("iso_standards_reference", "none"),
                 "XXX": ("iso_semantics_reference", "none"), "EUR": ("fx_converter_reference", "standard")}
        for code, (role, conv) in cases.items():
            r = POLICY.resolve(code)
            self.assertEqual((r["page_role"], r["converter_behavior"]), (role, conv), code)
        self.assertTrue(POLICY.is_ordinary_converter("usd"))
        with self.assertRaises(KeyError):
            POLICY.resolve("ZZZ")


class InvalidCombinationTest(unittest.TestCase):
    def assertInvalid(self, fn, needle):
        errs = mutated(fn)
        self.assertTrue(any(needle in e for e in errs), errs[:5])

    def test_K_invalid_combinations_fail(self):
        I = "instruments"
        self.assertInvalid(lambda d: d[I]["XTS"].__setitem__("instrument_type", "fiat_currency"), "anchored code")
        self.assertInvalid(lambda d: d[I]["XAU"].__setitem__("instrument_type", "unit_of_account"), "anchored code")
        self.assertInvalid(lambda d: d[I]["USD"].__setitem__("convertibility_status", "non_convertible"), "restricted_fiat_currency")
        self.assertInvalid(lambda d: d[I]["HRK"].__setitem__("active", True), "active must be true iff")
        self.assertInvalid(lambda d: d[I]["HRK"].__setitem__("successor_code", None), "requires successor_code")
        self.assertInvalid(lambda d: d[I]["XTS"].__setitem__("reference_rate_expected", True), "never has a rate")
        self.assertInvalid(lambda d: d[I]["USD"].__setitem__("instrument_type", "space_money"), "not in enum")
        self.assertInvalid(lambda d: d[I]["BGN"].__setitem__("reclassification_reason", None), "without reclassification_reason")
        self.assertInvalid(lambda d: d[I].pop("USD"), "expected 170")
        self.assertInvalid(lambda d: d[I]["USD"].__setitem__("evidence", ["repo_rate_snapshot_no_quote"]), "snapshot has one")
        self.assertInvalid(lambda d: d["type_policies"]["precious_metal"].__setitem__("pair_indexability", "candidate_for_noindex"),
                           "must not default to candidate_for_noindex")
        self.assertInvalid(lambda d: d[I]["CLF"].__setitem__("market_pricing_expected", True), "valued by its issuer")
        self.assertInvalid(lambda d: d[I]["ZWL"].__setitem__("review_flags", []), "successor_not_in_site_set")
        self.assertInvalid(lambda d: d[I]["USD"].__setitem__("surprise", 1), "unknown fields")
        with self.assertRaises(ip.ClassificationError):
            bad = copy.deepcopy(DOC)
            bad["instruments"]["XXX"]["instrument_type"] = "fiat_currency"
            ip.InstrumentPolicy(bad)


class GateTest(unittest.TestCase):
    def test_validator_script_passes(self):
        out = subprocess.run([sys.executable, str(REPO / "scripts" / "validate_instrument_classification.py")],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
