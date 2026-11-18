#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEO-A4.3 — XTS / XXX standards reference & pair consolidation."""

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
import validate_standards_special_codes as vs  # noqa: E402

BASELINE = "c8fbdd50368f8ae335573c8824e7835746a8451d"
SNAP = g.load_rate_snapshot()
CUR = g.load_currencies()
CONTENT = g.load_content_blocks()
PROFILES = g.load_pair_profiles()
LD_RE = re.compile(r'(?s)<script type="application/ld\+json">\n(.*?)\n</script>')


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def at_baseline(rel):
    out = subprocess.run(["git", "show", f"{BASELINE}:{rel}"], cwd=REPO, capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else None


def robots(t):
    return re.search(r'<meta name="robots" content="([^"]*)">', t).group(1)


def blocks(t):
    return [json.loads(b) for b in LD_RE.findall(t)]


def has_webapp(t):
    return any(n.get("@type") == "WebApplication" for x in blocks(t) for n in x.get("@graph", []))


COHORT = [p for p in PROFILES.values() if "XTS" in (p["from_code"], p["to_code"]) or "XXX" in (p["from_code"], p["to_code"])]


class HubTest(unittest.TestCase):
    def test_A_xts_hub_is_testing_code(self):
        t = read("currencies/xts.html")
        self.assertIn("<title>XTS — ISO 4217 Test Code Reference | ConvertCCY</title>", t)
        self.assertIn("Codes specifically reserved for testing purposes", t)
        self.assertIn('data-instrument-type="test_code"', t)
        self.assertEqual(robots(t), "index,follow")

    def test_B_xxx_hub_is_no_currency_code(self):
        t = read("currencies/xxx.html")
        self.assertIn("<title>XXX — ISO 4217 No-Currency Code Reference | ConvertCCY</title>", t)
        self.assertIn("The codes assigned for transactions where no currency is involved", t)
        self.assertIn('data-instrument-type="no_currency"', t)
        self.assertIn("does not mean an amount of zero", t)

    def test_hub_keeps_all_pair_links_and_no_converter_wording(self):
        t = read("currencies/xts.html")
        self.assertEqual(len(re.findall(r'href="/pages/[a-z]{3}-to-[a-z]{3}\.html"', t)), 338)
        self.assertNotIn("<h2>Convert", t)
        self.assertNotIn("Currency Pairs", t)


class PairPageTest(unittest.TestCase):
    def test_C_D_no_rate(self):
        for slug in ("usd-to-xts", "usd-to-xxx", "xts-to-usd", "xxx-to-eur"):
            t = read(f"pages/{slug}.html")
            self.assertIn('data-mode="standards"', t)
            self.assertIn("No exchange-rate relationship", t)
            for bad in ("data-rate=", g.RATE_SCRIPT_SRC, 'id="from-input"', "data-amount=", "SNAPSHOT ·", ">LIVE"):
                self.assertNotIn(bad, t, (slug, bad))

    def test_E_F_no_webapplication(self):
        for slug in ("usd-to-xts", "usd-to-xxx"):
            self.assertFalse(has_webapp(read(f"pages/{slug}.html")))

    def test_G_metadata_semantics(self):
        t = read("pages/usd-to-xts.html")
        self.assertIn("<title>USD / XTS — Test Code Reference | ConvertCCY</title>", t)
        self.assertIn("<h1>USD / XTS <em>Test Code Reference</em></h1>", t)
        self.assertIn("<title>USD / XXX — No-Currency Code Reference | ConvertCCY</title>", read("pages/usd-to-xxx.html"))
        for p in COHORT[:40]:
            t = read(f'pages/{p["pair_slug"]}.html')
            self.assertNotIn("Converter", re.search(r"<title>([^<]*)", t).group(1))
            self.assertNotIn("Convert ", re.search(r'name="description" content="([^"]*)', t).group(1))

    def test_H_faq_parity(self):
        for slug in ("usd-to-xts", "xxx-to-eur", "xts-to-xxx"):
            t = read(f"pages/{slug}.html")
            faq = next(x for x in blocks(t) if x.get("@type") == "FAQPage")
            ld = [(e["name"], e["acceptedAnswer"]["text"]) for e in faq["mainEntity"]]
            vis = [(html.unescape(q), html.unescape(a)) for q, a in vs.VIS_RE.findall(t)]
            self.assertEqual(ld, vis)
        for code in ("xts", "xxx"):
            t = read(f"currencies/{code}.html")
            faq = next(x for x in blocks(t) if x.get("@type") == "FAQPage")
            self.assertEqual([(e["name"], e["acceptedAnswer"]["text"]) for e in faq["mainEntity"]],
                             [(html.unescape(q), html.unescape(a)) for q, a in vs.HUB_FAQ_RE.findall(t)])

    def test_I_robots_policy(self):
        self.assertEqual(len(COHORT), 674)
        for p in COHORT:
            self.assertEqual(robots(read(f'pages/{p["pair_slug"]}.html')), "noindex,follow")
            self.assertEqual(g.pair_robots(p["from_code"], p["to_code"]), "noindex,follow")
        self.assertEqual(robots(read("pages/usd-to-eur.html")), g.INDEXABLE_ROBOTS)

    def test_K_canonical_self(self):
        for slug in ("usd-to-xts", "xxx-to-eur"):
            t = read(f"pages/{slug}.html")
            self.assertEqual(re.findall(r'<link rel="canonical" href="([^"]+)">', t),
                             [f"https://convertccy.com/pages/{slug}.html"])
        for line in read("_redirects").splitlines():      # no consolidation redirects
            if line.strip() and not line.startswith("#"):
                self.assertNotRegex(line.split()[0].lower(), r"(xts|xxx)")


class SitemapTest(unittest.TestCase):
    def test_J_sitemap_matches_policy(self):
        sm = read("sitemap.xml")
        locs = re.findall(r"<loc>([^<]+)</loc>", sm)
        self.assertEqual(len(locs), 28308)
        for p in COHORT:
            self.assertNotIn(f'https://convertccy.com/pages/{p["pair_slug"]}.html</loc>', sm)
        for code in ("xts", "xxx"):
            self.assertIn(f"https://convertccy.com/currencies/{code}.html</loc>", sm)
        urls = {u for u, _ in g.sitemap_entries(PROFILES)}
        self.assertNotIn("https://convertccy.com/pages/usd-to-xts.html", urls)
        self.assertIn("https://convertccy.com/pages/usd-to-eur.html", urls)
        xml, removed, refreshed = g.apply_sitemap_policy(sm, PROFILES, history_dates={}, dirty_paths=set(), today="2026-01-01")
        self.assertEqual((xml, removed, refreshed), (sm, [], []))  # current sitemap already conforms


class FreezeTest(unittest.TestCase):
    def test_L_M_controls_byte_identical(self):
        for rel in ("pages/usd-to-eur.html", "pages/bgn-to-eur.html",           # xau-to-usd moved to A4.4 metals
                    "currencies/usd.html", "currencies/bgn.html"):          # clf-to-usd moved to A4.5 institutional units
            base = at_baseline(rel)
            if base is None:
                self.skipTest("baseline commit not available")
            self.assertEqual(read(rel), base, rel)

    def test_N_idempotent(self):
        for key in ("USD_XTS", "XXX_EUR", "XTS_XXX", "BGN_XTS"):
            prof = PROFILES[key]
            tok = g.make_pair_tokens(prof, CUR)
            t = read(f'pages/{prof["pair_slug"]}.html')
            again = g.apply_standards_semantics(g.replace_static_rate_regions(t, prof, tok, SNAP), tok, CONTENT)
            self.assertEqual(again, t, key)

    def test_O_graph_valid(self):
        import validate_pair_link_graph as gate
        r = gate.analyse(REPO)
        self.assertEqual(gate.check(r), [])
        self.assertEqual(r["reachable"], 28730)
        self.assertLessEqual(r["depth_max"], 3)

    def test_P_policy_controls_treatment(self):
        original = g._POLICY_LAYER
        try:
            doc = copy.deepcopy(ip.load_raw())
            doc["instruments"]["XTS"]["instrument_type"] = "fiat_currency"
            g._POLICY_LAYER = ip.InstrumentPolicy(doc, validate_doc=False)
            self.assertNotEqual(g.pair_semantic_treatment("USD", "XTS", SNAP), "standards_special")
            doc2 = copy.deepcopy(ip.load_raw())
            doc2["instruments"]["KPW"]["instrument_type"] = "test_code"
            g._POLICY_LAYER = ip.InstrumentPolicy(doc2, validate_doc=False)
            self.assertEqual(g.pair_semantic_treatment("USD", "KPW", SNAP), "standards_special")
        finally:
            g._POLICY_LAYER = original
        self.assertEqual(g.pair_semantic_treatment("USD", "XTS", SNAP), "standards_special")
        self.assertEqual(g.pair_semantic_treatment("USD", "EUR", SNAP), "ordinary_fx")
        self.assertEqual(g.pair_semantic_treatment("BGN", "USD", SNAP), "historical")
        self.assertEqual(g.pair_semantic_treatment("KPW", "USD", SNAP), "unsupported_specialized")
        self.assertEqual(g.pair_semantic_treatment("XAU", "USD", SNAP), "precious_metal")

    def test_registry_citations_enforced(self):
        doc = copy.deepcopy(ip.load_raw())
        doc["standards_reference"]["XTS"]["iso_designation"]["text"] = "Codes for testing"
        self.assertTrue(any("verbatim" in e for e in ip.validate(doc)))
        doc2 = copy.deepcopy(ip.load_raw())
        doc2["standards_reference"]["XXX"]["claims"][0]["text"] = "XXX has the ISO 4217 numeric code 998."
        self.assertTrue(any("not in the cited source statements" in e for e in ip.validate(doc2)))

    def test_validator_rejects_pre_sprint_page(self):
        base = at_baseline("pages/usd-to-xts.html")
        if base is None:
            self.skipTest("baseline commit not available")
        errs = vs.check_pair(base, PROFILES["USD_XTS"], CUR, CONTENT, SNAP, g.instrument_policy_layer(), set())
        self.assertTrue(errs)

    def test_gate_passes(self):
        out = subprocess.run([sys.executable, str(REPO / "scripts" / "validate_standards_special_codes.py")],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
