#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEO-A4.2 — historical & legacy currency semantics."""

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

SNAP = g.load_rate_snapshot()
CUR = g.load_currencies()
CONTENT = g.load_content_blocks()
PROFILES = g.load_pair_profiles()
LD_RE = re.compile(r'(?s)<script type="application/ld\+json">\n(.*?)\n</script>')
VIS_RE = re.compile(r'(?s)<div class="faq-q"[^>]*>(.*?)</div>\s*<div class="faq-a">(.*?)</div>')


def page(slug):
    return (g.PAGES_DIR / f"{slug}.html").read_text(encoding="utf-8")


def rate_region(t):
    return t[t.index(g.STATIC_RATE_START): t.index(g.STATIC_RATE_END)]


def faq_ld(t):
    faqs = [x for x in (json.loads(b) for b in LD_RE.findall(t)) if x.get("@type") == "FAQPage"]
    assert len(faqs) == 1
    return [(e["name"], e["acceptedAnswer"]["text"]) for e in faqs[0]["mainEntity"]]


NO_CURRENT = ("data-rate=", ">LIVE", "SNAPSHOT ·", "Reference snapshot as of", g.RATE_SCRIPT_SRC, 'id="from-input"')


class HistoricalRenderingTest(unittest.TestCase):
    def assertNoCurrentRate(self, t):
        for s in NO_CURRENT:
            self.assertNotIn(s, t)
        self.assertIn('data-mode="historical"', t)

    def test_A_bgn_no_current_semantics(self):
        for slug in ("bgn-to-usd", "bgn-to-eur", "usd-to-bgn"):
            self.assertNoCurrentRate(page(slug))
        self.assertIn("No current market rate", rate_region(page("bgn-to-usd")))

    def test_B_hrk_fixed_conversion(self):
        r = rate_region(page("hrk-to-eur"))
        self.assertIn('<span data-value-type="historical_fixed_conversion">EUR 1 = HRK 7.53450</span>', r)
        self.assertIn("FIXED CONVERSION", r)
        self.assertIn("not a current market rate", r)

    def test_C_ang_provider_quote_not_current(self):
        t = page("ang-to-usd")
        self.assertNoCurrentRate(t)
        sr = g.static_pair_rate("ANG", "USD", SNAP)
        self.assertIsNotNone(sr)  # provider still publishes ANG …
        self.assertNotIn(g.format_rate_value(sr["rate"], sr["sig"]) + " USD", t)  # … but it is not rendered
        self.assertIn("does not present it as a current ANG market rate", t)

    def test_D_zwl_alias_blocked(self):
        self.assertEqual(SNAP["rates"]["ZWL"], SNAP["rates"]["ZWG"])  # the alias exists in source data
        t = page("zwl-to-usd")
        self.assertNoCurrentRate(t)
        sr = g.static_pair_rate("ZWL", "USD", SNAP)
        for v in (sr["rate"], sr["inverse"]):
            self.assertNotIn(g.format_rate_value(v, sr["sig"]), re.sub(r"(?is)<style.*?</style>", "", t))
        self.assertIn("alias of the successor", t)
        self.assertNotIn("data-value-type=\"historical_fixed_conversion\"", t)

    def test_E_sll_redenomination_without_overstating(self):
        r = rate_region(page("sll-to-sle"))
        self.assertIn('<span data-value-type="redenomination">SLE 1 = SLL 1,000</span>', r)
        self.assertIn("legal-tender end date not verified", r)
        self.assertNotIn("no longer legal tender", r)

    def test_F_cuc_24(self):
        self.assertIn('<span data-value-type="historical_fixed_conversion">CUC 1 = CUP 24</span>', rate_region(page("cuc-to-cup")))

    def test_G_svc_parity(self):
        r = rate_region(page("svc-to-usd"))
        self.assertIn('<span data-value-type="fixed_legal_parity">USD 1 = SVC 8.75</span>', r)
        self.assertIn("FIXED PARITY", r)
        self.assertIn("de jure legal tender", r)


class HistoricalFaqSchemaTest(unittest.TestCase):
    def test_H_no_current_rate_claim(self):
        for slug in ("bgn-to-usd", "hrk-to-eur", "zwl-to-usd", "svc-to-usd", "cuc-to-cup"):
            t = page(slug)
            self.assertNotIn("shows the latest available reference exchange rate", t)
            qs = [q for q, _ in faq_ld(t)]
            self.assertTrue(any(q.endswith("still a current currency?") for q in qs))
            self.assertTrue(any("not show a live" in q for q in qs))

    def test_I_visible_equals_jsonld_and_no_webapplication(self):
        for slug in ("bgn-to-usd", "hrk-to-eur", "sll-to-sle", "ang-to-usd"):
            t = page(slug)
            vis = [(html.unescape(q), html.unescape(a)) for q, a in VIS_RE.findall(t)]
            self.assertEqual(vis, faq_ld(t))
            self.assertNotIn('"@type": "WebApplication"', t)
        self.assertIn('"@type": "WebApplication"', page("usd-to-eur"))

    def test_J_control_page_unchanged_semantics(self):
        t = page("usd-to-eur")
        self.assertIn('data-mode="snapshot"', t)
        self.assertIn(g.RATE_SCRIPT_SRC, t)
        self.assertIn("shows the latest available reference exchange rate", t)
        self.assertEqual(g.pair_rate_treatment("USD", "EUR", SNAP), "snapshot")

    def test_K_no_live_enhancement_on_historical(self):
        self.assertEqual(g.rate_script_region_html("BGN", "USD", SNAP), f"{g.RATE_SCRIPT_START}\n{g.RATE_SCRIPT_END}")
        self.assertIn(g.RATE_SCRIPT_SRC, g.rate_script_region_html("USD", "EUR", SNAP))
        self.assertNotIn(g.RATE_SCRIPT_SRC, page("hrk-to-usd"))


class RegenerationGovernanceTest(unittest.TestCase):
    def test_L_targeted_regeneration_idempotent(self):
        for key in ("BGN_USD", "SLL_SLE", "ZWL_USD", "EUR_HRK"):
            prof = PROFILES[key]
            tok = g.make_pair_tokens(prof, CUR)
            t = page(prof["pair_slug"])
            items = g.rate_aware_faq_items(g.build_faq_items(prof, CONTENT, tok), tok, SNAP, CUR)
            again = g.replace_webpage_jsonld(g.replace_faq_regions(g.replace_static_rate_regions(t, prof, tok, SNAP), items), tok, items, True)
            self.assertEqual(again, t, key)

    def test_M_unverified_conversion_cannot_render(self):
        doc = copy.deepcopy(ip.load_raw())
        doc["instruments"]["HRK"]["documented_conversion"]["verification_status"] = "requires_source_verification"
        self.assertTrue(any("verified documented_conversion" in e for e in ip.validate(doc)))
        pol = ip.InstrumentPolicy(doc, validate_doc=False)
        self.assertIsNone(pol.historical_view("HRK")["fixed_conversion"])
        bad = copy.deepcopy(ip.load_raw())
        bad["historical_reference"]["BGN"]["claims"][0]["cites"][0]["supports"] = "Bulgaria adopted EUR on 2025-01-01"
        self.assertTrue(any("registry citations" in e for e in ip.validate(bad)))
        bad2 = copy.deepcopy(ip.load_raw())
        bad2["historical_reference"]["BGN"]["claims"][0]["text"] = "Bulgaria adopted the euro on 2027-01-01."
        self.assertTrue(any("not in the cited source statements" in e for e in ip.validate(bad2)))

    def test_N_policy_resolver_controls_branch(self):
        original = g._POLICY_LAYER
        try:
            doc = copy.deepcopy(ip.load_raw())
            doc["instruments"]["BGN"]["instrument_type"] = "fiat_currency"   # policy says fiat …
            g._POLICY_LAYER = ip.InstrumentPolicy(doc, validate_doc=False)
            self.assertEqual(CUR["BGN"]["instrument_type"], "fiat_currency")
            self.assertEqual(g.pair_rate_treatment("BGN", "USD", SNAP), "snapshot")
            doc2 = copy.deepcopy(ip.load_raw())
            cur2 = copy.deepcopy(CUR)
            cur2["HRK"]["instrument_type"] = "fiat_currency"                 # legacy label says fiat …
            g._POLICY_LAYER = ip.InstrumentPolicy(doc2, validate_doc=False)
            self.assertEqual(g.pair_rate_treatment("HRK", "USD", SNAP), "historical")  # … policy wins
        finally:
            g._POLICY_LAYER = original

    def test_cohort_comes_from_policy(self):
        pol = g.instrument_policy_layer()
        hist = {(p["from_code"], p["to_code"]) for p in PROFILES.values()
                if g.pair_rate_treatment(p["from_code"], p["to_code"], SNAP) == "historical"}
        self.assertEqual(len(hist), 2296)
        codes = {c for c in pol.codes() if pol.is_historical(c)}
        self.assertEqual(codes, {"ANG", "BGN", "CUC", "HRK", "SLL", "SVC", "ZWL"})
        self.assertEqual(g.pair_rate_treatment("XTS", "BGN", SNAP), "unsupported")  # XTS governs

    def test_gate_passes(self):
        out = subprocess.run([sys.executable, str(REPO / "scripts" / "validate_historical_instruments.py")],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
