#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEO-A4.5 — institutional-unit reference layer (XDR, CLF, UYW, XUA, XSU)."""

from __future__ import annotations

import copy
import html
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import generate as g  # noqa: E402
import institutional_reference as ir  # noqa: E402
import instrument_policy as ip  # noqa: E402
import validate_institutional_units as vi  # noqa: E402

BASELINE = "8a6a6436bd8b15b447446a436f70f6dc5b7dc75c"
FX = g.load_rate_snapshot()
CUR = g.load_currencies()
CONTENT = g.load_content_blocks()
PROFILES = g.load_pair_profiles()
POL = g.instrument_policy_layer()
LD_RE = re.compile(r'(?s)<script type="application/ld\+json">\n(.*?)\n</script>')
LOCS = set(re.findall(r"<loc>https://convertccy\.com/([^<]*)</loc>", (REPO / "sitemap.xml").read_text(encoding="utf-8")))


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def at_baseline(rel):
    out = subprocess.run(["git", "show", f"{BASELINE}:{rel}"], cwd=REPO, capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else None


def licensed_snapshot(license_state="redistribution_permitted", values=None, captured="2026-11-18T13:00:00Z"):
    """Synthetic, NOT committed: XDR activated with a licence that permits publication."""
    s = copy.deepcopy(ir.load_institutional_snapshot())
    s["activation_state"] = "source_activated"
    s["captured_at"] = captured
    s["instruments"]["XDR"]["value_decision"] = "issuer_value_activated"
    s["instruments"]["XDR"]["source_id"] = "test_licensed"
    s["sources"].append({"id": "test_licensed", "name": "Test Licensed SDR Feed", "authority": "test", "url": "https://example.test",
                         "role": "issuer", "codes": ["XDR"], "license_state": license_state,
                         "license_basis": "synthetic test licence", "license_evidence": None})
    s["values"] = values if values is not None else [{
        "instrument_code": "XDR", "instrument_name": "IMF Special Drawing Right", "instrument_type": "special_instrument",
        "issuer": "International Monetary Fund", "valuation_type": "basket_valuation", "value": "1.300000",
        "denomination_currency": "USD", "valuation_date": "2026-11-18", "source_timestamp": "2026-11-18T12:00:00Z",
        "retrieved_at": "2026-11-18T12:30:00Z", "methodology_id": "imf_sdr_basket_valuation", "source_id": "test_licensed",
        "license_state": license_state, "freshness_state": "current", "derived": False, "derivation_method": None,
        "provenance_id": "test-1"}]
    return s


def view(F, T, snap, fx=FX):
    return ir.value_view(F, T, snap, fx, g.format_rate_value)


def faq_pairs(t):
    blocks = [json.loads(b) for b in LD_RE.findall(t)]
    faq = next(b for b in blocks if b.get("@type") == "FAQPage")
    ld = [(e["name"], e["acceptedAnswer"]["text"]) for e in faq["mainEntity"]]
    vis = [(html.unescape(q), html.unescape(a)) for q, a in vi.VIS_RE.findall(t)]
    return ld, vis


class ClassificationTest(unittest.TestCase):
    def test_A_xdr_special_instrument(self):
        r = POL.resolve("XDR")
        self.assertEqual((r["instrument_type"], r["page_role"], r["converter_behavior"]),
                         ("special_instrument", "supranational_instrument_dossier", "valuation_only"))
        iv = POL.institutional_view("XDR")
        self.assertEqual((iv["issuer_display"], iv["pair_role"], iv["valuation_type"]),
                         ("International Monetary Fund", "supranational_valuation_reference", "basket_valuation"))

    def test_B_clf_indexed_unit(self):
        iv = POL.institutional_view("CLF")
        self.assertEqual((iv["instrument_type"], iv["pair_role"], iv["valuation_type"], iv["issuer_display"]),
                         ("unit_of_account", "indexed_unit_reference", "indexed_unit_value", "Banco Central de Chile"))

    def test_C_uyw_statutory_publisher(self):
        iv = POL.institutional_view("UYW")
        self.assertEqual((iv["instrument_type"], iv["pair_role"], iv["issuer_type"]),
                         ("unit_of_account", "indexed_unit_reference", "national_statistical_authority"))
        self.assertIn("Instituto Nacional de Estadística", iv["issuer_display"])
        self.assertTrue(any("19.608" in c["text"] for c in iv["claims"]))

    def test_D_xua_regional_with_sdr_relationship(self):
        iv = POL.institutional_view("XUA")
        self.assertEqual((iv["instrument_type"], iv["related_unit"], iv["valuation_type"], iv["value_decision"]),
                         ("regional_unit", "XDR", "institutional_parity", "reference_layer_only"))

    def test_E_xsu_status_is_evidence_driven(self):
        iv = POL.institutional_view("XSU")
        self.assertEqual((iv["activity_status"], iv["decision_label"], iv["issuer_display"]),
                         ("status_unresolved", "STATUS UNRESOLVED", None))
        self.assertEqual(iv["activity_claims"], [])
        self.assertTrue(iv["reported_indicators"])
        self.assertNotEqual(iv["classification_confidence"], "high")
        doc = ip.load_raw()
        bad = copy.deepcopy(doc)  # an unresolved unit may not claim activity from a press source
        bad["institutional_units_reference"]["units"]["XSU"]["activity_claims"] = list(
            bad["institutional_units_reference"]["units"]["XSU"]["reported_indicators"])
        self.assertTrue(any("unresolved status cannot carry activity claims" in e for e in ip.validate(bad)))
        bad = copy.deepcopy(doc)  # press sources cannot back issuer statements
        bad["institutional_units_reference"]["units"]["XSU"]["claims"].append(
            bad["institutional_units_reference"]["units"]["XSU"]["reported_indicators"][0])
        self.assertTrue(any("primary sources only" in e for e in ip.validate(bad)))
        t = read("pages/xsu-to-usd.html")
        self.assertIn('data-activity-status="status_unresolved"', t)
        self.assertNotIn("Status: active", t)


class PairSemanticsTest(unittest.TestCase):
    def test_F_xdr_usd_not_a_converter(self):
        self.assertEqual(g.pair_semantic_treatment("XDR", "USD", FX), "institutional_unit")
        self.assertIsNotNone(g.static_pair_rate("XDR", "USD", FX))  # provider value preserved in the raw snapshot ...
        t = read("pages/xdr-to-usd.html")                            # ... but never rendered
        for bad in ("Converter", "data-rate=", "WebApplication", g.RATE_SCRIPT_SRC, "SNAPSHOT ·", "Reference rate vs bank rate"):
            self.assertNotIn(bad, t)
        self.assertIn("<title>XDR to USD — IMF SDR Valuation Reference | ConvertCCY</title>", t)
        self.assertIn('data-pair-role="supranational_valuation_reference"', t)
        self.assertIn("IMF REFERENCE ONLY", t)

    def test_G_clf_clp_indexed_semantics(self):
        t = read("pages/clf-to-clp.html")
        self.assertIn("Unidad de Fomento Indexed Value Reference", t)
        self.assertIn('data-pair-role="indexed_unit_reference"', t)
        self.assertIn("not a floating exchange rate", t)
        self.assertNotIn("Converter", t)

    def test_H_xua_xdr_relationship(self):
        self.assertEqual(g.institutional_pair_role("XUA", "XDR"), "institutional_relative_reference")
        t = read("pages/xua-to-xdr.html")
        self.assertIn("<title>XUA / XDR — AfDB Unit of Account Reference | ConvertCCY</title>", t)
        self.assertIn("does not convert it into a standing numeric parity", t)
        self.assertNotRegex(t, r"1 XUA = 1")

    def test_I_xdr_xts_stays_standards(self):
        self.assertEqual(g.pair_semantic_treatment("XDR", "XTS", FX), "standards_special")
        base = at_baseline("pages/xdr-to-xts.html")
        if base is None:
            self.skipTest("baseline commit not available")
        self.assertEqual(read("pages/xdr-to-xts.html"), base)

    def test_J_xdr_bgn_stays_historical(self):
        self.assertEqual(g.pair_semantic_treatment("XDR", "BGN", FX), "historical")
        base = at_baseline("pages/xdr-to-bgn.html")
        if base is None:
            self.skipTest("baseline commit not available")
        self.assertEqual(read("pages/xdr-to-bgn.html"), base)

    def test_K_xau_xdr_metal_precedence(self):
        self.assertEqual(g.pair_semantic_treatment("XAU", "XDR", FX), "precious_metal")
        self.assertIn("XDR is an institutional unit whose valuation source is not activated", read("pages/xau-to-xdr.html"))
        base = at_baseline("pages/xau-to-xdr.html")
        if base is not None:
            self.assertEqual(read("pages/xau-to-xdr.html"), base)

    def test_X_router_is_policy_driven(self):
        original = g._POLICY_LAYER
        try:
            doc = copy.deepcopy(ip.load_raw())
            doc["instruments"]["CLF"]["instrument_type"] = "fiat_currency"
            g._POLICY_LAYER = ip.InstrumentPolicy(doc, validate_doc=False)
            self.assertEqual(g.pair_semantic_treatment("CLF", "USD", FX), "ordinary_fx")
            doc2 = copy.deepcopy(ip.load_raw())
            doc2["instruments"]["KPW"]["instrument_type"] = "unit_of_account"
            g._POLICY_LAYER = ip.InstrumentPolicy(doc2, validate_doc=False)
            self.assertEqual(g.pair_semantic_treatment("KPW", "USD", FX), "institutional_unit")
        finally:
            g._POLICY_LAYER = original


class ValueModelTest(unittest.TestCase):
    def test_L_no_value_without_provenance(self):
        snap = ir.load_institutional_snapshot()
        self.assertEqual(snap["values"], [])
        for F, T in (("XDR", "USD"), ("CLF", "CLP"), ("UYW", "UYU"), ("XUA", "XDR"), ("XSU", "USD")):
            self.assertEqual(view(F, T, snap)["value_type"], "unavailable")
        s = licensed_snapshot()
        del s["values"][0]["provenance_id"]
        self.assertTrue(ir.validate_institutional_snapshot(s))
        s = licensed_snapshot()
        s["values"][0]["methodology_id"] = None
        self.assertTrue(ir.validate_institutional_snapshot(s, ip.load_raw()))
        self.assertEqual(view("XDR", "USD", s)["value_type"], "unavailable")

    def test_M_license_unclear_cannot_render(self):
        s = licensed_snapshot(license_state="license_unclear")
        self.assertTrue(any("may not be published" in e for e in ir.validate_institutional_snapshot(s)))
        self.assertEqual(view("XDR", "USD", s)["value_type"], "unavailable")
        self.assertEqual(view("XDR", "USD", licensed_snapshot())["value_type"], "basket_valuation")

    def test_N_issuer_methodology_required(self):
        s = copy.deepcopy(ir.load_institutional_snapshot())
        s["instruments"]["CLF"]["methodology_id"] = None
        self.assertTrue(any("issuer methodology is required" in e for e in ir.validate_institutional_snapshot(s)))
        doc = copy.deepcopy(ip.load_raw())
        doc["institutional_units_reference"]["units"]["CLF"]["claims"] = []
        self.assertTrue(any("requires cited methodology claims" in e for e in ip.validate(doc)))

    def test_O_direct_vs_derived(self):
        s = licensed_snapshot()
        d = view("XDR", "USD", s)
        self.assertEqual((d["value_type"], d["derived"], d["value_text"]), ("basket_valuation", False, "1.300000"))
        inv = view("USD", "XDR", s)
        self.assertEqual((inv["value_type"], inv["derived"], inv["derivation_method"]),
                         ("derived_reference_value", True, "inverse_of_issuer_value"))
        x = view("XDR", "EUR", s)
        self.assertEqual((x["value_type"], x["derived"]), ("derived_reference_value", True))
        self.assertEqual((x["fx_timestamp"], x["issuer_timestamp"]), (FX["captured_at"], "2026-11-18T12:00:00Z"))
        self.assertEqual(view("XUA", "XDR", s)["value_type"], "unavailable")  # no stored parity value
        # derived precision never exceeds the weakest input
        self.assertLessEqual(len(re.sub(r"\D", "", x["value_text"]).lstrip("0")),
                             ir.sig_for(ir.published_uncertainty("1.300000") + ir.published_uncertainty(repr(FX["rates"]["EUR"]))))
        # rendered labels with an activated value
        tok = g.make_pair_tokens(PROFILES["XDR_EUR"], CUR)
        global_snap = g._INSTITUTIONAL_SNAPSHOT
        try:
            g._INSTITUTIONAL_SNAPSHOT = s
            region = g.institutional_rate_region_html(tok, FX)
            self.assertIn("DERIVED FROM INTERNATIONAL MONETARY FUND VALUATION", region)
            self.assertIn("FX timestamp:", region)
            self.assertIn("Direct issuer value", g.institutional_rate_region_html(g.make_pair_tokens(PROFILES["XDR_USD"], CUR), FX))
        finally:
            g._INSTITUTIONAL_SNAPSHOT = global_snap

    def test_P_dates_and_timestamps_required(self):
        for field, bad in (("valuation_date", "18/11/2026"), ("source_timestamp", None), ("retrieved_at", "2026-11-18")):
            s = licensed_snapshot()
            s["values"][0][field] = bad
            self.assertTrue(ir.validate_institutional_snapshot(s), field)
        s = copy.deepcopy(ir.load_institutional_snapshot())
        s["captured_at"] = "2026-11-18T00:00:00Z"   # no timestamp without values
        self.assertTrue(ir.validate_institutional_snapshot(s))
        # cadence-specific skew: an FX reference too far from the issuer date blocks derivation
        s = licensed_snapshot()
        fx = dict(FX, captured_at="2026-11-25T12:00:00Z")
        self.assertEqual(view("XDR", "EUR", s, fx)["value_type"], "unavailable")
        # stale issuer value is not shown
        self.assertEqual(view("XDR", "USD", licensed_snapshot(captured="2026-12-20T00:00:00Z"))["value_type"], "unavailable")

    def test_snapshot_rejects_bad_data(self):
        good = ir.load_institutional_snapshot()
        self.assertEqual(ir.validate_institutional_snapshot(good, ip.load_raw()), [])
        bad = copy.deepcopy(good)
        bad["values"] = [{"instrument_code": "CLF"}]
        self.assertTrue(ir.validate_institutional_snapshot(bad))
        s = licensed_snapshot()
        s["values"][0]["value"] = "-1"
        self.assertTrue(ir.validate_institutional_snapshot(s))
        s = licensed_snapshot()
        s["values"].append(dict(s["values"][0]))
        self.assertTrue(any("duplicate" in e for e in ir.validate_institutional_snapshot(s)))
        s = licensed_snapshot()
        s["values"][0]["derived"] = True
        self.assertTrue(ir.validate_institutional_snapshot(s))
        with self.assertRaises(ir.InstitutionalSnapshotError):
            json.loads('{"a": 1, "a": 2}', object_pairs_hook=ir._no_dupes)
        self.assertEqual(good["provider_values"]["XDR"]["classification"], "provider_value_secondary_only")
        self.assertEqual(good["provider_values"]["CLF"]["classification"], "provider_value_pending_issuer_comparison")


class SurfaceTest(unittest.TestCase):
    def test_Q_faq_schema_parity(self):
        for slug in ("xdr-to-usd", "usd-to-xdr", "clf-to-clp", "clf-to-usd", "uyw-to-uyu", "xua-to-xdr", "xsu-to-usd", "xdr-to-clf"):
            ld, vis = faq_pairs(read(f"pages/{slug}.html"))
            self.assertEqual(ld, vis, slug)
        hub = read("currencies/xdr.html")
        blocks = [json.loads(b) for b in LD_RE.findall(hub)]
        faq = next(b for b in blocks if b.get("@type") == "FAQPage")
        self.assertEqual([(e["name"], e["acceptedAnswer"]["text"]) for e in faq["mainEntity"]],
                         [(html.unescape(q), html.unescape(a)) for q, a in vi.HUB_FAQ_RE.findall(hub)])
        qs = [q for q, _ in faq_pairs(read("pages/xdr-to-usd.html"))[0]]
        for want in ("Is XDR a currency?", "Who issues the SDR?", "How is the SDR valued?",
                     "Is this XDR/USD value published directly by International Monetary Fund?", "What date does this reference use?"):
            self.assertIn(want, qs)

    def test_hubs_institution_aware(self):
        for code, word in (("xdr", "IMF Special Drawing Right"), ("clf", "Chile Unidad de Fomento"), ("uyw", "Unidad Previsional"),
                           ("xua", "African Development Bank Unit of Account"), ("xsu", "SUCRE")):
            t = read(f"currencies/{code}.html")
            title = re.search(r"<title>([^<]*)</title>", t).group(1)
            self.assertIn(word, title)
            self.assertNotIn("Currency Pairs", title)
            self.assertIn("Source governance", t)
            self.assertNotIn("WebApplication", t)


class FreezeTest(unittest.TestCase):
    def test_R_S_T_U_controls_byte_identical(self):
        for rel in ("pages/usd-to-eur.html", "pages/bgn-to-eur.html", "pages/usd-to-xts.html", "pages/xau-to-usd.html",
                    "currencies/usd.html", "currencies/bgn.html", "currencies/xau.html", "sitemap.xml",
                    "data/rate_snapshot.json", "data/metal_reference_snapshot.json"):
            base = at_baseline(rel)
            if base is None:
                self.skipTest("baseline commit not available")
            self.assertEqual(read(rel), base, rel)

    def test_V_targeted_regeneration_idempotent(self):
        for key in ("XDR_USD", "USD_XDR", "CLF_CLP", "UYW_UYU", "XUA_XDR", "XSU_USD", "XDR_CLF", "KPW_CLF"):
            prof = PROFILES[key]
            tok = g.make_pair_tokens(prof, CUR)
            t = read(f'pages/{prof["pair_slug"]}.html')
            again = g.apply_institutional_semantics(g.replace_static_rate_regions(t, prof, tok, FX), tok, CONTENT, FX)
            self.assertEqual(again, t, key)

    def test_W_validator_rejects_pre_sprint_converter_semantics(self):
        for key, slug in (("XDR_USD", "xdr-to-usd"), ("CLF_CLP", "clf-to-clp"), ("XSU_USD", "xsu-to-usd")):
            base = at_baseline(f"pages/{slug}.html")
            if base is None:
                self.skipTest("baseline commit not available")
            errs, _, _ = vi.check_pair(base, PROFILES[key], CUR, CONTENT, FX, POL, LOCS)
            self.assertTrue(errs, slug)
        self.assertIn("Converter", at_baseline("pages/xdr-to-usd.html"))
        self.assertIn('data-mode="snapshot"', at_baseline("pages/clf-to-clp.html"))

    def test_gates_pass(self):
        for script in ("validate_institutional_units.py", "validate_institutional_snapshot.py"):
            out = subprocess.run([sys.executable, str(REPO / "scripts" / script)], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
