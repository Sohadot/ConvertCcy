#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEO-A4.2.1 — historical metadata & page-semantics consistency."""

from __future__ import annotations

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
import validate_historical_instruments as vh  # noqa: E402

SNAP = g.load_rate_snapshot()
CUR = g.load_currencies()
CONTENT = g.load_content_blocks()
PROFILES = g.load_pair_profiles()


def page(slug):
    return (g.PAGES_DIR / f"{slug}.html").read_text(encoding="utf-8")


def hub(code):
    return (REPO / "currencies" / f"{code}.html").read_text(encoding="utf-8")


def title(t):
    return html.unescape(re.search(r"<title>([^<]*)</title>", t).group(1))


def description(t):
    return html.unescape(re.search(r'<meta name="description" content="([^"]*)">', t).group(1))


def webpage(t):
    for blk in vh.LD_RE.findall(t):
        for n in json.loads(blk).get("@graph", []):
            if n.get("@type") == "WebPage":
                return n
    raise AssertionError("no WebPage node")


class PairMetadataTest(unittest.TestCase):
    def test_A_bgn_eur_title(self):
        t = page("bgn-to-eur")
        self.assertNotIn("Converter", title(t))
        self.assertEqual(title(t), "BGN to EUR Historical Fixed Conversion | ConvertCCY")

    def test_B_bgn_eur_description(self):
        d = description(page("bgn-to-eur"))
        self.assertTrue(d.startswith("Historical reference for Bulgarian Lev (BGN) and Euro (EUR)"))
        self.assertIn("verified fixed conversion EUR 1 = BGN 1.95583", d)
        self.assertNotIn("conversion table", d.lower())

    def test_C_bgn_eur_schema_name(self):
        wp = webpage(page("bgn-to-eur"))
        self.assertNotIn("Converter", wp["name"])
        self.assertFalse(wp["description"].startswith("Convert"))

    def test_N_html_and_schema_share_semantic_type(self):
        for slug in ("bgn-to-eur", "bgn-to-usd", "zwl-to-usd", "sll-to-sle", "svc-to-usd", "cuc-to-cup", "eur-to-hrk"):
            t = page(slug)
            wp = webpage(t)
            self.assertEqual(title(t), wp["name"], slug)
            self.assertEqual(description(t), wp["description"], slug)
            a, b = slug.upper().split("-TO-")
            meta = g.pair_metadata(g.make_pair_tokens(PROFILES[f"{a}_{b}"], CUR), True)
            self.assertEqual((meta["title"], meta["description"]), (wp["name"], wp["description"]))
            for tag in ("og:title", "twitter:title"):
                self.assertIn(f'content="{g.esc(meta["title"])}"', t)


class PairSemanticsTest(unittest.TestCase):
    def test_D_zwl_usd_no_market_overview(self):
        t = page("zwl-to-usd")
        sentences, _ = vh.ordinary_boilerplate(PROFILES["ZWL_USD"], g.make_pair_tokens(PROFILES["ZWL_USD"], CUR), CONTENT)
        for s in sentences:
            self.assertNotIn(g.esc(s), t)
        self.assertNotIn("as market conditions evolve", t)
        self.assertIn("ZWL / USD Historical Currency Reference", t)

    def test_E_sll_sle_redenomination(self):
        t = page("sll-to-sle")
        self.assertIn("SLL to SLE Redenomination Reference", title(t))
        self.assertIn("SLL / SLE Redenomination Reference", t)
        self.assertIn('<div class="sec-title">Redenomination</div>', t)
        self.assertIn("verified redenomination ratio SLE 1 = SLL 1,000", description(t))

    def test_F_cuc_cup_fixed_conversion(self):
        t = page("cuc-to-cup")
        self.assertIn("Historical Fixed Conversion", title(t))
        self.assertIn('<div class="sec-title">Historical Fixed Conversion</div>', t)

    def test_G_svc_usd_parity(self):
        t = page("svc-to-usd")
        self.assertIn("SVC to USD Fixed Parity Reference", title(t))
        self.assertIn('<div class="sec-title">Fixed Parity</div>', t)
        self.assertIn("Legacy reference for", description(t))

    def test_H_no_ordinary_conversion_table_heading(self):
        for slug in ("bgn-to-usd", "hrk-to-eur", "zwl-to-usd"):
            self.assertNotIn('<div class="sec-title">Conversion Table</div>', page(slug))
        self.assertIn('<div class="sec-title">Historical Conversion Status</div>', page("bgn-to-usd"))

    def test_I_no_market_boilerplate_sections(self):
        for slug in ("bgn-to-usd", "ang-to-usd", "svc-to-eur"):
            t = page(slug)
            for h in ("What moves currencies", "What an exchange rate means", "Reference rate vs bank rate"):
                self.assertNotIn(f'<div class="sec-title">{h}</div>', t)
            self.assertNotIn('<p class="pj-macro">', t)
            self.assertIn("Reading a Historical Currency Reference", t)

    def test_O_no_a3_runtime(self):
        for slug in ("bgn-to-eur", "zwl-to-usd", "sll-to-sle"):
            t = page(slug)
            self.assertNotIn(g.RATE_SCRIPT_SRC, t)
            self.assertNotIn("data-rate=", t)
            self.assertNotIn('"@type": "WebApplication"', t)


class HubSemanticsTest(unittest.TestCase):
    def test_J_bgn_hub_title(self):
        self.assertEqual(title(hub("bgn")), "Bulgarian Lev (BGN) Historical Currency Reference | ConvertCCY")
        self.assertIn("Legacy Currency Reference", title(hub("svc")))

    def test_K_bgn_hub_description(self):
        d = description(hub("bgn"))
        self.assertNotIn("convert BGN to 169 currencies", d)
        self.assertIn("withdrawn Bulgarian Lev (BGN)", d)
        self.assertNotIn("<h2>Convert BGN", hub("bgn"))
        self.assertIn("none presents a current BGN market rate", hub("bgn"))

    def test_ordinary_hub_unchanged_wording(self):
        self.assertEqual(title(hub("usd")), "US Dollar (USD) Currency Pairs | ConvertCCY")


class FreezeAndIdempotenceTest(unittest.TestCase):
    def test_L_usd_eur_matches_committed_control(self):
        base = subprocess.run(["git", "show", "34c919fc4b7e22b54da548215042f7279742ece1:pages/usd-to-eur.html"],
                              cwd=REPO, capture_output=True, text=True)
        if base.returncode != 0:
            self.skipTest("baseline commit not available in this checkout")
        self.assertEqual(page("usd-to-eur"), base.stdout)

    def test_ordinary_metadata_unchanged(self):
        meta = g.pair_metadata(g.make_pair_tokens(PROFILES["USD_EUR"], CUR), False)
        self.assertEqual(meta["title"], "USD to EUR Converter | ConvertCCY")
        self.assertTrue(meta["description"].startswith("Convert US Dollar to Euro"))

    def test_M_targeted_regeneration_idempotent(self):
        for key in ("BGN_EUR", "ZWL_USD", "SLL_SLE", "SVC_EUR"):
            prof = PROFILES[key]
            tok = g.make_pair_tokens(prof, CUR)
            t = page(prof["pair_slug"])
            self.assertEqual(g.apply_historical_semantics(t, tok, CONTENT), t, key)

    def test_semantics_rewrite_fails_closed(self):
        tok = g.make_pair_tokens(PROFILES["BGN_USD"], CUR)
        with self.assertRaises(ValueError):
            g.apply_historical_semantics(page("bgn-to-usd").replace("<title>", "<title>x</title><title>", 1), tok, CONTENT)

    def test_validator_rejects_pre_patch_page(self):
        old = subprocess.run(["git", "show", "e2a3b6a306cc936bab3883aeaa2bbc28948fef6d:pages/bgn-to-eur.html"],
                             cwd=REPO, capture_output=True, text=True)
        if old.returncode != 0:
            self.skipTest("pre-patch commit not available in this checkout")
        blocks = [json.loads(b) for b in vh.LD_RE.findall(old.stdout)]
        errs = vh.semantic_errors(old.stdout, PROFILES["BGN_EUR"], g.make_pair_tokens(PROFILES["BGN_EUR"], CUR), CONTENT, blocks)
        self.assertTrue(any("converter semantics" in e for e in errs))
        self.assertTrue(any("boilerplate" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
