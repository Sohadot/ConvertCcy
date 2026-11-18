#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEO-A3.1 — unsupported-pair FAQ and FAQPage JSON-LD truthfulness."""

from __future__ import annotations

import html
import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import generate as g  # noqa: E402

SNAP = g.load_rate_snapshot()
CUR = g.load_currencies()
CONTENT = g.load_content_blocks()
PROFILES = g.load_pair_profiles()
FALSE_CLAIM = "shows the latest available reference exchange rate"
SUPPORTED_A1 = "This page shows the latest available reference exchange rate for converting {FROM_NAME} to {TO_NAME}."
LD_RE = re.compile(r'(?s)<script type="application/ld\+json">\n(.*?)\n</script>')
VIS_RE = re.compile(r'(?s)<div class="faq-q"[^>]*>(.*?)</div>\s*<div class="faq-a">(.*?)</div>')
DRIFT_LINE = "governed declaration threshold and exchange-control posture"


def page(slug):
    return (g.PAGES_DIR / f"{slug}.html").read_text(encoding="utf-8")


def faq_ld(text):
    blocks = [json.loads(b) for b in LD_RE.findall(text)]   # G: every block parses
    faqs = [b for b in blocks if b.get("@type") == "FAQPage"]
    assert len(faqs) == 1, len(faqs)
    return [(e["name"], e["acceptedAnswer"]["text"]) for e in faqs[0]["mainEntity"]]


def faq_visible(text):
    return [(html.unescape(q), html.unescape(a)) for q, a in VIS_RE.findall(text)]


def expected_items(key):
    prof = PROFILES[key]
    tok = g.make_pair_tokens(prof, CUR)
    return g.rate_aware_faq_items(g.build_faq_items(prof, CONTENT, tok), tok, SNAP, CUR)


class FaqTruthfulnessTest(unittest.TestCase):
    def test_A_supported_keeps_supported_statement(self):
        want = g.replace_tokens(SUPPORTED_A1, g.make_pair_tokens(PROFILES["USD_EUR"], CUR))
        t = page("usd-to-eur")
        self.assertEqual(faq_ld(t)[0][1], want)
        self.assertEqual(faq_visible(t)[0][1], want)

    def test_B_unsupported_has_no_false_claim(self):
        self.assertNotIn(FALSE_CLAIM, page("xau-to-xts"))

    def test_C_unsupported_truthful_answer(self):
        # SEO-A4.3: XTS/XXX pairs are standards pages now; XAU->USD stays the unsupported example
        a1 = faq_ld(page("xau-to-usd"))[0][1]
        self.assertTrue(a1.startswith("ConvertCCY does not currently have a reference rate for XAU to USD"))
        self.assertIn("No conversion value is shown rather than an estimate.", a1)
        self.assertIn(g.UNSUPPORTED_CODE_REASONS["XAU"], a1)
        for word in ("latest", "current rate", "live", "market rate is"):
            self.assertNotIn(word, a1)

    def test_C_no_exchange_value_codes_use_standards_faq(self):
        # SEO-A4.3 supersedes the A3.1 Q2/Q4 patch: XTS/XXX pairs carry the standards FAQ
        items = dict(faq_ld(page("xau-to-xts")))
        self.assertIn("Is XTS a real currency?", items)
        self.assertIn("Does XTS have an exchange rate?", items)
        self.assertNotIn("Is this the same as a bank rate?", items)
        self.assertNotIn("How much is 1 XAU in XTS?", items)
        # unsupported but real instrument (KPW): Q2/Q4 keep the default generic wording
        kpw = dict(faq_ld(page("kpw-to-usd")))
        self.assertEqual(kpw["Why does the KPW/USD rate change?"], CONTENT["faq_defaults"][1]["a"])

    def test_D_visible_equals_jsonld(self):
        for slug in ("xau-to-xts", "usd-to-xxx", "kpw-to-usd", "usd-to-eur", "eur-to-ved"):
            t = page(slug)
            self.assertEqual(faq_visible(t), faq_ld(t), slug)

    def test_E_F_G_full_cohort(self):
        bad = {"unsupported_false": 0, "supported_missing": 0, "mismatch": 0, "drift": 0}
        for key, prof in PROFILES.items():
            t = page(prof["pair_slug"])
            ld = faq_ld(t)
            if ld != faq_visible(t):
                bad["mismatch"] += 1
            if g.pair_rate_treatment(prof["from_code"], prof["to_code"], SNAP) != "snapshot":
                if FALSE_CLAIM in t:
                    bad["unsupported_false"] += 1
            elif FALSE_CLAIM not in ld[0][1]:
                bad["supported_missing"] += 1
            if [(i["q"], i["a"]) for i in expected_items(key)] != ld:
                bad["drift"] += 1
        self.assertEqual(bad, {"unsupported_false": 0, "supported_missing": 0, "mismatch": 0, "drift": 0})

    def test_supported_items_untouched_by_rate_awareness(self):
        prof = PROFILES["USD_EUR"]
        tok = g.make_pair_tokens(prof, CUR)
        base = g.build_faq_items(prof, CONTENT, tok)
        self.assertIs(g.rate_aware_faq_items(base, tok, SNAP, CUR), base)

    def test_H_rate_regions_unchanged_and_faq_update_targeted(self):
        for key in ("XAU_XTS", "USD_EUR", "KPW_USD"):
            prof = PROFILES[key]
            t = page(prof["pair_slug"])
            self.assertEqual(g.replace_static_rate_regions(t, prof, g.make_pair_tokens(prof, CUR), SNAP), t)
            self.assertEqual(g.replace_faq_regions(t, expected_items(key)), t)  # idempotent

    def test_H_faq_replace_fails_closed(self):
        t = page("xau-to-xts")
        with self.assertRaises(ValueError):
            g.replace_faq_regions(t.replace('<div class="sec-title">FAQ</div>', "", 1), expected_items("XAU_XTS"))
        with self.assertRaises(ValueError):
            g.replace_faq_regions(t + g.FAQ_JSONLD_START, expected_items("XAU_XTS"))

    def test_I_graph_unchanged(self):
        import validate_pair_link_graph as gate
        self.assertEqual(gate.check(gate.analyse(REPO)), [])

    def test_J_drift_line_untouched(self):
        self.assertIn(DRIFT_LINE, page("xau-to-xts"))
        self.assertIn(DRIFT_LINE, page("usd-to-eur"))


if __name__ == "__main__":
    unittest.main()
