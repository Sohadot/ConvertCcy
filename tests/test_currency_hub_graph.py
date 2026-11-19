#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEO-A2 — currency hubs + deterministic related-pair graph.

Locks in:
  * related-pair selection is deterministic, bounded and free of reverse-only
    2-cycles across the full 170-currency pair space (in-memory graph);
  * each currency hub links all FROM and TO pairs and self-canonicalises;
  * build_pair_page and the navigation-only patch emit the same nav region;
  * the additive sitemap merge never rewrites an existing entry;
  * the committed tree satisfies the graph gate (assertions A–K).
"""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
from collections import defaultdict, deque
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import generate  # noqa: E402
import validate_pair_link_graph as gate  # noqa: E402


def _silent(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


class _Data:
    currencies = _silent(generate.load_currencies)
    content = _silent(generate.load_content_blocks)
    profiles = _silent(generate.load_pair_profiles)
    codes = generate.site_currency_order(currencies.keys())
    importance = generate.build_pair_importance_index(profiles)


class RelatedPairSelectionTest(unittest.TestCase):
    def test_bounded_unique_reverse_first_and_deterministic(self):
        for a, b in [("USD", "EUR"), ("TZS", "MWK"), ("XAU", "XTS"), ("AED", "AFN"), ("ZWL", "AED")]:
            sel = generate.select_related_pairs(a, b, _Data.codes, _Data.importance)
            self.assertEqual(len(sel), generate.RELATED_PAIR_LIMIT)
            self.assertEqual(sel[0], (b, a))
            self.assertEqual(len(set(sel)), len(sel))
            self.assertNotIn((a, b), sel)
            for x, y in sel:
                self.assertNotEqual(x, y)
                self.assertIn(x, _Data.currencies)
                self.assertIn(y, _Data.currencies)
            self.assertEqual(sel, generate.select_related_pairs(a, b, list(reversed(_Data.codes)), _Data.importance))

    def test_full_in_memory_graph_has_no_isolated_cycles_and_depth_3(self):
        codes = sorted(_Data.codes)
        pairs = [(a, b) for a in codes for b in codes if a != b]
        self.assertEqual(len(pairs), 28730)
        inbound = defaultdict(set)
        for a, b in pairs:
            for t in generate.select_related_pairs(a, b, _Data.codes, _Data.importance):
                inbound[t].add((a, b))
        two_cycles = sum(1 for a, b in pairs if inbound[(a, b)] <= {(b, a)} and inbound[(b, a)] <= {(a, b)})
        self.assertEqual(two_cycles, 0)
        self.assertGreaterEqual(min(len(inbound[p]) for p in pairs), 4)
        # home -> currencies.html -> hub -> pair : every pair is linked by both of its hubs
        hub_links = {c: {(c, o) for o in codes if o != c} | {(o, c) for o in codes if o != c} for c in codes}
        depth = {}
        q = deque()
        for c in codes:
            for p in hub_links[c]:
                if p not in depth:
                    depth[p] = 3
                    q.append(p)
        self.assertEqual(len(depth), len(pairs))
        self.assertEqual(max(depth.values()), 3)


class CurrencyHubPageTest(unittest.TestCase):
    def test_hub_links_all_from_and_to_pairs(self):
        gov = generate.load_governed_currency_map()
        for code in ("USD", "EUR", "TZS", "XTS"):
            html = generate.build_currency_hub_page(code, _Data.currencies, gov)
            self.assertIn(f'<link rel="canonical" href="https://convertccy.com/currencies/{code.lower()}.html">', html)
            self.assertIn('<meta name="robots" content="index,follow">', html)
            hrefs = set(gate.anchors(html))
            for o in _Data.codes:
                if o == code:
                    continue
                self.assertIn(generate.pair_href(code, o), hrefs)
                self.assertIn(generate.pair_href(o, code), hrefs)
            self.assertIn("/currencies.html", hrefs)

    def test_hub_titles_unique(self):
        titles = {
            generate.build_currency_hub_page(c, _Data.currencies).split("<title>")[1].split("</title>")[0]
            for c in _Data.codes
        }
        self.assertEqual(len(titles), len(_Data.codes))

    def test_currencies_index_links_every_hub(self):
        html = generate.build_currencies_page(_Data.currencies, _Data.content)
        for c in _Data.codes:
            self.assertIn(f'href="{generate.currency_hub_href(c)}"', html)


class PairNavigationRegionTest(unittest.TestCase):
    def test_full_render_and_patch_agree(self):
        prof = _Data.profiles["TZS_MWK"]
        gov = generate.load_governed_currency_map()
        full = generate.build_pair_page(prof, _Data.currencies, _Data.content, _Data.codes, gov, _Data.importance)
        nav = generate.pair_navigation_html("TZS", "MWK", _Data.codes, _Data.importance)
        self.assertEqual(full.count(nav), 1)
        self.assertEqual(generate.replace_pair_navigation(full, nav), full)
        self.assertIn('href="/currencies/tzs.html"', nav)
        self.assertIn('href="/currencies/mwk.html"', nav)

    def test_patch_leaves_everything_outside_region(self):
        page = (generate.PAGES_DIR / "usd-to-eur.html").read_text(encoding="utf-8")
        patched = generate.replace_pair_navigation(page, "  <!--NAV-->")
        start = page.index(generate.PAIR_NAV_START_MARKER)
        end = page.index(generate.PAIR_NAV_END_MARKER)
        self.assertEqual(patched, page[:start] + "  <!--NAV-->" + page[end:])

    def test_patch_refuses_unknown_template(self):
        with self.assertRaises(ValueError):
            generate.replace_pair_navigation("<html>no nav</html>", "x")


class SitemapHubMembershipTest(unittest.TestCase):
    """SEO-A5.1 replaced the additive monolithic-sitemap merge with derived semantic sitemaps.
    The A2 guarantees it protected still hold: the committed sitemaps list every generator URL
    (no hub or pair missing, nothing extra), and every hub sits in the currency-hubs child."""

    def test_committed_sitemaps_complete_and_exact(self):
        locs = generate.read_sitemap_locs(REPO)
        self.assertEqual(len(locs), len(set(locs)))
        self.assertEqual(set(locs), {u for u, _ in generate.sitemap_entries(_Data.profiles)})

    def test_every_hub_in_hub_sitemap(self):
        hubs = (REPO / "sitemaps" / "currency-hubs.xml").read_text(encoding="utf-8")
        for code in ("usd", "eur", "xts", "kpw"):
            self.assertIn(f"<loc>https://convertccy.com/currencies/{code}.html</loc>", hubs)
        self.assertEqual(hubs.count("<loc>"), len(list((REPO / "currencies").glob("*.html"))))


class CommittedGraphGateTest(unittest.TestCase):
    """Assertions A–K against the committed HTML tree."""

    @classmethod
    def setUpClass(cls):
        cls.r = gate.analyse(REPO)

    def test_gate_passes(self):
        self.assertEqual(gate.check(self.r), [])

    def test_headline_numbers(self):
        r = self.r
        self.assertEqual(r["pair_pages"], 28730)          # A
        self.assertEqual(r["reachable"], 28730)           # B
        self.assertEqual(r["unreachable"], 0)             # C
        self.assertEqual(r["sitemap_only"], 0)            # D
        self.assertEqual(r["isolated_2_cycles"], 0)       # E
        self.assertEqual(r["no_nonpair_inbound"], 0)      # F
        self.assertLessEqual(r["depth_max"], 3)           # G
        self.assertEqual(r["hub_errors"], [])             # H, I
        self.assertEqual(r["broken_links"], {})           # J
        self.assertLessEqual(r["related_max"], gate.MAX_RELATED)


if __name__ == "__main__":
    unittest.main()
