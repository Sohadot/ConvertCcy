#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEO-A4.4 — precious-metals reference layer."""

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
import instrument_policy as ip  # noqa: E402
import metal_reference as mr  # noqa: E402
import validate_precious_metals as vp  # noqa: E402

BASELINE = "4612f2282a83f81c7cec9b371a4edba2bcba42d0"
FX = g.load_rate_snapshot()
CUR = g.load_currencies()
CONTENT = g.load_content_blocks()
PROFILES = g.load_pair_profiles()
POL = g.instrument_policy_layer()
LD_RE = re.compile(r'(?s)<script type="application/ld\+json">\n(.*?)\n</script>')


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def at_baseline(rel):
    out = subprocess.run(["git", "show", f"{BASELINE}:{rel}"], cwd=REPO, capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else None


def licensed_snapshot(quotes=None, license_state="redistribution_permitted", captured="2026-11-18T12:00:00Z"):
    """Synthetic, NOT committed: a snapshot whose source licence permits publication."""
    s = copy.deepcopy(mr.load_metal_snapshot())
    s["activation_state"] = "source_activated"
    s["captured_at"] = captured
    s["sources"].append({"id": "test_licensed", "name": "Test Licensed Metals Feed", "administrator": "test",
                         "role": "market_data_provider", "metals": ["XAU", "XAG", "XPT", "XPD"],
                         "license_state": license_state, "license_basis": "synthetic test licence", "license_evidence": None})
    s["quotes"] = quotes if quotes is not None else [
        {"metal_code": "XAU", "metal_name": "Gold", "unit": "troy ounce", "counter_currency": "USD", "value": "2500.50",
         "valuation_type": "market_reference", "source_id": "test_licensed", "source_timestamp": "2026-11-18T10:00:00Z",
         "retrieved_at": "2026-11-18T10:05:00Z", "license_state": license_state, "provenance_id": "t1", "derived": False},
        {"metal_code": "XAG", "metal_name": "Silver", "unit": "troy ounce", "counter_currency": "USD", "value": "31.25",
         "valuation_type": "market_reference", "source_id": "test_licensed", "source_timestamp": "2026-11-18T10:00:00Z",
         "retrieved_at": "2026-11-18T10:05:00Z", "license_state": license_state, "provenance_id": "t2", "derived": False}]
    return s


def view(F, T, snap):
    return mr.value_view(F, T, snap, FX, g.format_rate_value)


class ClassificationTest(unittest.TestCase):
    def test_A_codes_resolve_as_precious_metal(self):
        for c in ("XAU", "XAG", "XPT", "XPD"):
            r = POL.resolve(c)
            self.assertEqual((r["instrument_type"], r["converter_behavior"], r["page_role"]),
                             ("precious_metal", "valuation_only", "precious_metal_reference"))
            self.assertTrue(r["reference_rate_expected"])
            self.assertEqual(r["hub_indexability"], "index_with_specialized_reference_role")
            self.assertNotIn(c, FX["rates"])

    def test_J_unit_semantics(self):
        mv = POL.metal_view("XAU")
        self.assertEqual(mv["iso_designation"]["text"], "Gold")
        self.assertIn("states no unit", mv["unit_convention"])
        self.assertIn("3.110 348 E+01", mv["troy_ounce_definition"]["text"])
        self.assertFalse(mv["gram_conversion_published"])
        self.assertIn(g.esc(mv["unit_convention"]), read("pages/xau-to-usd.html"))


class PairSemanticsTest(unittest.TestCase):
    def test_B_xau_usd_metal_semantics(self):
        t = read("pages/xau-to-usd.html")
        self.assertIn('data-mode="metal"', t)
        self.assertIn("<title>XAU to USD Gold Valuation Reference | ConvertCCY</title>", t)
        self.assertIn("<h1>Gold (XAU) Valuation in <em>US Dollar (USD)</em></h1>", t)
        for bad in ("Converter", "data-rate=", g.RATE_SCRIPT_SRC, "No reference rate available", '"@type": "WebApplication"'):
            self.assertNotIn(bad, t)

    def test_C_usd_xau_inverse_semantics(self):
        t = read("pages/usd-to-xau.html")
        self.assertIn("US Dollar (USD) Valuation in <em>Gold (XAU)</em>", t)
        v = view("USD", "XAU", licensed_snapshot())
        self.assertEqual(v["value_type"], "derived_inverse")
        self.assertTrue(v["derived"])

    def test_D_xau_xag_relative_value(self):
        t = read("pages/xau-to-xag.html")
        self.assertIn("XAU / XAG Gold-Silver Ratio Reference", t)
        self.assertIn("Relative Metal Value Reference", t)
        v = view("XAU", "XAG", licensed_snapshot())
        self.assertEqual(v["value_type"], "derived_metal_ratio")

    def test_E_no_value_without_governed_source(self):
        snap = mr.load_metal_snapshot()
        self.assertEqual(snap["activation_state"], "reference_layer_only")
        self.assertEqual(snap["quotes"], [])
        for F, T in (("XAU", "USD"), ("USD", "XAU"), ("XAU", "XAG"), ("XPD", "JPY")):
            self.assertEqual(g.metal_value(F, T, FX)["value_type"], "unavailable")
        self.assertIn("Reference pricing source not yet activated", read("pages/xpt-to-usd.html"))

    def test_F_licence_unclear_cannot_render(self):
        for state in ("license_unclear", "display_only", "not_usable", "derived_use_only"):
            snap = licensed_snapshot(license_state=state)
            self.assertEqual(view("XAU", "USD", snap)["value_type"], "unavailable", state)
            self.assertTrue(any("may not be published" in e for e in mr.validate_metal_snapshot(snap)), state)

    def test_G_I_provenance_and_timestamps_required(self):
        snap = licensed_snapshot()
        snap["quotes"][0]["source_timestamp"] = "yesterday"
        self.assertTrue(any("source_timestamp" in e for e in mr.validate_metal_snapshot(snap)))
        snap = licensed_snapshot()
        snap["quotes"][0]["provenance_id"] = ""
        self.assertTrue(any("provenance_id" in e for e in mr.validate_metal_snapshot(snap)))
        snap = licensed_snapshot()
        del snap["quotes"][0]["unit"]
        self.assertTrue(any("missing" in e for e in mr.validate_metal_snapshot(snap)))
        snap = licensed_snapshot()
        snap["quotes"][0]["value"] = 2500.5
        self.assertTrue(any("decimal string" in e for e in mr.validate_metal_snapshot(snap)))
        stale = licensed_snapshot(captured="2026-11-25T12:00:00Z")
        self.assertEqual(view("XAU", "USD", stale)["value_type"], "unavailable")

    def test_H_direct_vs_derived_labels(self):
        snap = licensed_snapshot()
        direct = view("XAU", "USD", snap)
        self.assertEqual((direct["value_type"], direct["derived"], direct["value_text"]), ("market_reference", False, "2,500.50"))
        cross = view("XAU", "EUR", snap)
        self.assertEqual((cross["value_type"], cross["derived"]), ("derived_cross_value", True))
        self.assertEqual(len(cross["sources"]), 2)
        self.assertEqual(len(cross["timestamps"]), 2)
        skewed = licensed_snapshot()
        for q in skewed["quotes"]:
            q["source_timestamp"] = "2026-11-17T08:00:00Z"   # > 24 h from the FX capture
        skewed["captured_at"] = "2026-11-17T12:00:00Z"
        self.assertEqual(view("XAU", "EUR", skewed)["value_type"], "unavailable")
        original = g._METAL_SNAPSHOT
        try:
            g._METAL_SNAPSHOT = snap
            tok = g.make_pair_tokens(PROFILES["XAU_EUR"], CUR)
            html_ = g.metal_rate_region_html(tok, FX)
            self.assertIn('data-value-type="derived_cross_value"', html_)
            self.assertIn(">DERIVED · AS OF", html_)
            self.assertIn("sources:", html_)
            self.assertIn("timestamps:", html_)
            self.assertIn("XAU to EUR Gold Reference Price", g.metal_pair_metadata(tok, "ConvertCCY", FX)["title"])
        finally:
            g._METAL_SNAPSHOT = original

    def test_K_faq_parity(self):
        for slug in ("xau-to-usd", "usd-to-xag", "xau-to-xag", "xpd-to-xdr"):
            t = read(f"pages/{slug}.html")
            faq = next(json.loads(b) for b in LD_RE.findall(t) if '"FAQPage"' in b)
            self.assertEqual([(e["name"], e["acceptedAnswer"]["text"]) for e in faq["mainEntity"]],
                             [(html.unescape(q), html.unescape(a)) for q, a in vp.VIS_RE.findall(t)])
        hub = read("currencies/xau.html")
        faq = next(json.loads(b) for b in LD_RE.findall(hub) if '"FAQPage"' in b)
        self.assertEqual([(e["name"], e["acceptedAnswer"]["text"]) for e in faq["mainEntity"]],
                         [(html.unescape(q), html.unescape(a)) for q, a in vp.HUB_FAQ_RE.findall(hub)])

    def test_hub_semantics(self):
        t = read("currencies/xau.html")
        self.assertIn("<title>XAU — Gold / ISO 4217 Reference | ConvertCCY</title>", t)
        self.assertNotIn("Price", re.search(r"<title>([^<]*)", t).group(1))
        self.assertIn('data-pricing-activation="reference_layer_only"', t)
        self.assertEqual(len(re.findall(r'href="/pages/[a-z]{3}-to-[a-z]{3}\.html"', t)), 338)


class PrecedenceTest(unittest.TestCase):
    def test_L_xau_xts_standards(self):
        self.assertEqual(g.pair_semantic_treatment("XAU", "XTS", FX), "standards_special")
        self.assertEqual(read("pages/xau-to-xts.html"), at_baseline("pages/xau-to-xts.html"))

    def test_M_xau_bgn_historical(self):
        self.assertEqual(g.pair_semantic_treatment("XAU", "BGN", FX), "historical")
        self.assertEqual(g.pair_semantic_treatment("BGN", "XAU", FX), "historical")
        self.assertEqual(read("pages/xau-to-bgn.html"), at_baseline("pages/xau-to-bgn.html"))

    def test_N_xau_xdr_no_fabricated_value(self):
        self.assertEqual(g.pair_semantic_treatment("XAU", "XDR", FX), "precious_metal")
        self.assertEqual(view("XAU", "XDR", licensed_snapshot())["value_type"] != "unavailable", "XDR" in FX["rates"])
        t = read("pages/xau-to-xdr.html")
        self.assertIn("XDR is an institutional unit whose valuation source is not activated", t)
        self.assertIn('data-value-type="unavailable"', t)

    def test_T_router_policy_driven(self):
        original = g._POLICY_LAYER
        try:
            doc = copy.deepcopy(ip.load_raw())
            doc["instruments"]["XPT"]["instrument_type"] = "fiat_currency"
            g._POLICY_LAYER = ip.InstrumentPolicy(doc, validate_doc=False)
            self.assertNotEqual(g.pair_semantic_treatment("XPT", "USD", FX), "precious_metal")
            doc2 = copy.deepcopy(ip.load_raw())
            doc2["instruments"]["KPW"]["instrument_type"] = "precious_metal"
            g._POLICY_LAYER = ip.InstrumentPolicy(doc2, validate_doc=False)
            self.assertEqual(g.pair_semantic_treatment("KPW", "USD", FX), "precious_metal")
        finally:
            g._POLICY_LAYER = original


class FreezeTest(unittest.TestCase):
    def test_O_P_Q_controls_byte_identical(self):
        for rel in ("pages/usd-to-eur.html", "pages/bgn-to-eur.html", "pages/usd-to-xts.html", "pages/clf-to-usd.html",
                    "currencies/usd.html", "sitemap.xml"):
            base = at_baseline(rel)
            if base is None:
                self.skipTest("baseline commit not available")
            self.assertEqual(read(rel), base, rel)

    def test_R_idempotent(self):
        for key in ("XAU_USD", "USD_XAU", "XAU_XAG", "XPD_XDR", "KPW_XAG"):
            prof = PROFILES[key]
            tok = g.make_pair_tokens(prof, CUR)
            t = read(f'pages/{prof["pair_slug"]}.html')
            again = g.apply_metal_semantics(g.replace_static_rate_regions(t, prof, tok, FX), tok, CONTENT, FX)
            self.assertEqual(again, t, key)

    def test_S_validator_rejects_converter_metal_page(self):
        base = at_baseline("pages/xau-to-usd.html")
        if base is None:
            self.skipTest("baseline commit not available")
        self.assertIn("Converter", base)
        locs = set(re.findall(r"<loc>https://convertccy\.com/([^<]*)</loc>", read("sitemap.xml")))
        errs, _ = vp.check_pair(base, PROFILES["XAU_USD"], CUR, CONTENT, FX, POL, locs)
        self.assertTrue(errs)

    def test_snapshot_validator_rejects_bad_data(self):
        good = mr.load_metal_snapshot()
        self.assertEqual(mr.validate_metal_snapshot(good, ip.load_raw()), [])
        bad = copy.deepcopy(good)
        bad["quotes"] = [{"metal_code": "XAU"}]
        self.assertTrue(mr.validate_metal_snapshot(bad))
        with self.assertRaises(mr.MetalSnapshotError):
            json.loads('{"a": 1, "a": 2}', object_pairs_hook=mr._no_dupes)

    def test_gates_pass(self):
        for script in ("validate_precious_metals.py", "validate_metal_snapshot.py"):
            out = subprocess.run([sys.executable, str(REPO / "scripts" / script)], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
