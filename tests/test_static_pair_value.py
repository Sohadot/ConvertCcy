#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEO-A3 — static pair reference values with progressive enhancement.

Covers the sprint's required assertions:
  A  supported pair has a numeric static rate in HTML
  B  supported pair shows the exact snapshot date
  C  supported pair has static conversion-table values
  D  inverse rate is mathematically consistent
  E  unsupported pair carries no fake numeric rate
  F  unsupported pair carries a truthful unsupported message
  G  JS keeps the static value when the live fetch fails (browser test;
     skipped when node/playwright are unavailable)
  H  --static-rates-only changes only the marked regions
  I  SEO-A2 graph assertions still hold
  J  the pre-existing passage-text drift line is untouched
  K  precision formatter handles normal / tiny / huge rates
  L  snapshot validator rejects malformed data
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from decimal import Decimal
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import generate as g  # noqa: E402

SNAP = g.load_rate_snapshot()
CUR = g.load_currencies()
PROFILES = g.load_pair_profiles()
DRIFT_LINE = "governed declaration threshold and exchange-control posture"


def page(slug: str) -> str:
    return (g.PAGES_DIR / f"{slug}.html").read_text(encoding="utf-8")


def region(text: str, start: str, end: str) -> str:
    return text[text.index(start): text.index(end) + len(end)]


class SupportedPairStaticHtmlTest(unittest.TestCase):
    def setUp(self):
        self.html = page("usd-to-eur")
        self.sr = g.static_pair_rate("USD", "EUR", SNAP)
        self.rate_s = g.format_rate_value(self.sr["rate"], self.sr["sig"])

    def test_A_numeric_rate_in_static_html(self):
        self.assertIn(f'<div class="rate-main" id="live-rate">1 USD = {self.rate_s} EUR</div>', self.html)
        self.assertRegex(self.rate_s, r"^[0-9][0-9,]*(\.[0-9]+)?$")
        self.assertNotIn("Loading…", self.html)
        self.assertNotIn("Fetching rate…", self.html)

    def test_B_exact_snapshot_date(self):
        self.assertIn(f"SNAPSHOT · {SNAP['as_of']}", self.html)
        self.assertIn(f"Reference snapshot as of {SNAP['as_of']}", self.html)
        self.assertIn(f'data-asof="{SNAP["as_of"]}"', self.html)
        self.assertIn(f"source: {SNAP['source']}", self.html)

    def test_C_static_table_values(self):
        tbl = region(self.html, g.STATIC_TABLE_START, g.STATIC_TABLE_END)
        rows = re.findall(r'<tr data-amount="(\d+)"><td>([^<]+)</td><td>([^<]+)</td></tr>', tbl)
        self.assertEqual([int(a) for a, _, _ in rows], PROFILES["USD_EUR"]["static_amounts"])
        for a, left, right in rows:
            self.assertEqual(right, f'{g.format_rate_value(int(a) * self.sr["rate"], self.sr["sig"])} EUR')
            self.assertEqual(left, f"{int(a):,} USD")
        self.assertIn('<th scope="col">USD</th>', tbl)

    def test_D_inverse_consistent(self):
        for a, b in [("USD", "EUR"), ("USD", "IRR"), ("KWD", "VND"), ("JPY", "GBP"), ("CLF", "IDR")]:
            sr = g.static_pair_rate(a, b, SNAP)
            sig = sr["sig"]
            rate_d = Decimal(g.format_rate_value(sr["rate"], sig).replace(",", ""))
            inv_d = Decimal(g.format_rate_value(sr["inverse"], sig).replace(",", ""))
            self.assertAlmostEqual(float(rate_d * inv_d), 1.0, delta=2 * 10 ** (1 - sig))
            rev = g.static_pair_rate(b, a, SNAP)
            self.assertEqual(g.format_rate_value(rev["rate"], rev["sig"]), g.format_rate_value(sr["inverse"], sig))
        self.assertIn(f'1 EUR = <span id="inverse-rate">{g.format_rate_value(self.sr["inverse"], self.sr["sig"])}</span> USD', self.html)


class UnsupportedPairStaticHtmlTest(unittest.TestCase):
    def test_E_no_fake_numeric_rate(self):
        for slug in ("kpw-to-usd", "eur-to-ved", "ved-to-kpw"):   # XTS/XXX, metals, institutional units (A4.5): own tests
            html = page(slug)
            rate = region(html, g.STATIC_RATE_START, g.STATIC_RATE_END)
            tbl = region(html, g.STATIC_TABLE_START, g.STATIC_TABLE_END)
            self.assertIn('data-mode="unsupported"', rate)
            self.assertNotIn("data-rate=", rate)
            self.assertNotRegex(rate, r"= [0-9]")
            self.assertNotIn('id="from-input"', rate)  # no operational-looking converter
            self.assertNotRegex(tbl, r"<td>[0-9][0-9,.]* [A-Z]{3}</td>")
            self.assertNotIn("Loading…", html)

    def test_F_truthful_unsupported_message(self):
        html = page("kpw-to-ved")
        self.assertIn("No current reference rate is available for this pair in the ConvertCCY snapshot", html)
        self.assertIn(g.UNSUPPORTED_CODE_REASONS["KPW"], html)
        self.assertIn(g.UNSUPPORTED_CODE_REASONS["VED"], html)
        self.assertIn(">NO RATE<", html)

    def test_every_missing_code_is_classified(self):
        missing = {c for c in CUR if c not in SNAP["rates"]}
        self.assertTrue(missing)
        self.assertEqual(missing - set(g.UNSUPPORTED_CODE_REASONS), set())

    def test_counts(self):
        sup = sum(1 for p in PROFILES.values() if g.static_pair_rate(p["from_code"], p["to_code"], SNAP))
        self.assertEqual(sup + (len(PROFILES) - sup), 28730)
        self.assertEqual(len(PROFILES) - sup, 4238)


class PrecisionPolicyTest(unittest.TestCase):
    def test_K_formatter(self):
        cases = {
            (0.909, 3): "0.909",
            (1.1001, 3): "1.10",
            (9.9996, 3): "10.0",            # carry into a new leading digit
            (0.00099996, 3): "0.00100",
            (0.5, 3): "0.500",
            (1816886.22, 6): "1,816,890",   # huge: grouped, no exponent
            (18168862200.0, 6): "18,168,900,000",
            (5.50392e-7, 6): "0.000000550392",  # tiny: plain decimal
            (1.23456789e-9, 6): "0.00000000123457",
            (1000, 3): "1,000",
        }
        for (v, s), want in cases.items():
            self.assertEqual(g.format_rate_value(v, s), want, (v, s))
        for v in (1e-12, 3.3e-8, 0.123, 7.0, 12345.678, 9.87e10):
            out = g.format_rate_value(v, 6)
            self.assertNotIn("e", out.lower())
            self.assertNotIn("E", out)

    def test_K_significant_digit_rule(self):
        # 2-decimal / 3-sig-digit source precision → sig from summed leg uncertainty, clamped 3..6
        self.assertEqual(g.static_pair_rate("USD", "EUR", {"base": "USD", "as_of": "x", "source": "s",
                                                           "rates": {"USD": 1, "EUR": 0.874}})["sig"], 3)
        self.assertEqual(g.static_pair_rate("USD", "IRR", {"base": "USD", "as_of": "x", "source": "s",
                                                           "rates": {"USD": 1, "IRR": 1198016.03}})["sig"], 6)
        self.assertEqual(g.significant_digits_for(0.0), 6)
        self.assertEqual(g.significant_digits_for(0.5), 3)

    def test_K_js_formatter_matches_python(self):
        js = (REPO / "assets" / "js" / "pair-rate.js").read_text(encoding="utf-8")
        self.assertIn("SIG_MIN = 3, SIG_MAX = 6", js)
        self.assertEqual((g.RATE_SIG_MIN, g.RATE_SIG_MAX), (3, 6))


class SnapshotValidatorTest(unittest.TestCase):
    def test_L_current_snapshot_valid(self):
        self.assertEqual(g.validate_rate_snapshot_data(SNAP), [])
        self.assertEqual(g.RATE_SNAPSHOT_FILE.read_bytes(), g.PUBLIC_RATE_SNAPSHOT_FILE.read_bytes())

    def test_L_malformed_rejected(self):
        bad_cases = []
        for mutate in (
            lambda s: s["rates"].__setitem__("EUR", -1),
            lambda s: s["rates"].__setitem__("EUR", 0),
            lambda s: s["rates"].__setitem__("EUR", "0.9"),
            lambda s: s["rates"].__setitem__("EUR", True),
            lambda s: s["rates"].__setitem__("eur", 0.9),
            lambda s: s["rates"].__setitem__("USD", 2),
            lambda s: s.__setitem__("as_of", "18/11/2026"),
            lambda s: s.__setitem__("captured_at", "yesterday"),
            lambda s: s.__setitem__("count", 1),
            lambda s: s.__setitem__("type", "other"),
            lambda s: s.__setitem__("source", ""),
            lambda s: s.__setitem__("rates", {}),
        ):
            s = copy.deepcopy(SNAP)
            mutate(s)
            bad_cases.append(g.validate_rate_snapshot_data(s))
        for errs in bad_cases:
            self.assertTrue(errs)
        with self.assertRaises(g.RateSnapshotError):
            g.parse_rate_snapshot('{"rates": {"EUR": 1, "EUR": 2}}')
        with self.assertRaises(g.RateSnapshotError):
            g.parse_rate_snapshot("{not json")


class TargetedUpdateTest(unittest.TestCase):
    def test_H_only_marked_regions_change(self):
        prof = PROFILES["TZS_MWK"]
        tok = g.make_pair_tokens(prof, CUR)
        html = page("tzs-to-mwk")
        other = copy.deepcopy(SNAP)
        other["as_of"] = "2099-01-01"
        other["rates"]["TZS"] = other["rates"]["TZS"] * 1.5
        new = g.replace_static_rate_regions(html, prof, tok, other)
        self.assertNotEqual(new, html)

        def mask(t):
            for s, e in ((g.STATIC_RATE_START, g.STATIC_RATE_END),
                         (g.STATIC_TABLE_START, g.STATIC_TABLE_END),
                         (g.RATE_SCRIPT_START, g.RATE_SCRIPT_END)):
                t = t[: t.index(s)] + "\0" + t[t.index(e) + len(e):]
            return t
        self.assertEqual(mask(new), mask(html))
        self.assertIn("SNAPSHOT · 2099-01-01", new)
        self.assertEqual(g.replace_static_rate_regions(html, prof, tok, SNAP), html)  # idempotent

    def test_H_fail_closed(self):
        prof = PROFILES["TZS_MWK"]
        tok = g.make_pair_tokens(prof, CUR)
        html = page("tzs-to-mwk")
        for broken in (html.replace(g.STATIC_RATE_END, "", 1),
                       html + g.STATIC_TABLE_START,
                       html.replace(g.RATE_SCRIPT_START, "", 1)):
            with self.assertRaises(ValueError):
                g.replace_static_rate_regions(broken, prof, tok, SNAP)

    def test_full_render_equals_committed_except_known_drift(self):
        cur_order = g.site_currency_order(CUR)
        gov = g.load_governed_currency_map()
        imp = g.build_pair_importance_index(PROFILES)
        ct = g.load_content_blocks()
        for key in ("USD_EUR", "XAU_XTS", "CHF_USD", "NGN_PKR"):
            prof = PROFILES[key]
            full = g.build_pair_page(prof, CUR, ct, cur_order, gov, imp, SNAP).split("\n")
            committed = page(prof["pair_slug"]).split("\n")
            diff = [i for i, (x, y) in enumerate(zip(committed, full)) if x != y]
            self.assertEqual(len(full), len(committed))
            self.assertLessEqual(len(diff), 1, key)
            for i in diff:
                self.assertIn(DRIFT_LINE, committed[i])

    def test_J_drift_line_preserved(self):
        self.assertIn(DRIFT_LINE, page("usd-to-eur"))
        self.assertIn(DRIFT_LINE, page("xau-to-xts"))
        self.assertNotIn(DRIFT_LINE, page("chf-to-usd"))  # the 338 CHF pages were already current


class RateGateTest(unittest.TestCase):
    def test_gate_passes(self):
        out = subprocess.run([sys.executable, str(REPO / "scripts" / "validate_rate_snapshot.py")],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


class GraphRegressionTest(unittest.TestCase):
    def test_I_seo_a2_graph_unchanged(self):
        import validate_pair_link_graph as gate
        r = gate.analyse(REPO)
        self.assertEqual(gate.check(r), [])
        self.assertEqual(r["pair_pages"], 28730)
        self.assertEqual(r["reachable"], 28730)
        self.assertLessEqual(r["depth_max"], 3)
        self.assertEqual(r["isolated_2_cycles"], 0)


def _have_playwright() -> bool:
    if shutil.which("node") is None:
        return False
    probe = subprocess.run(["node", "-e", "require('playwright')"], capture_output=True)
    return probe.returncode == 0


@unittest.skipUnless(_have_playwright(), "node + playwright not available")
class BrowserLifecycleTest(unittest.TestCase):
    """G — progressive enhancement lifecycle in a real browser."""

    @classmethod
    def setUpClass(cls):
        class _Quiet(SimpleHTTPRequestHandler):
            def log_message(self, *args, **kwargs):
                pass

        handler = partial(_Quiet, directory=str(REPO))
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cases = [[0.909, 3], [1816886.22, 6], [5.50392e-7, 6], [9.9996, 3], [0.5, 3], [12345.678, 4]]
        cls.cases = cases
        out = subprocess.run(
            ["node", str(REPO / "tests" / "js" / "pair_rate_lifecycle.js"), f"http://127.0.0.1:{port}", json.dumps(cases)],
            capture_output=True, text=True, timeout=180,
        )
        cls.res = json.loads(out.stdout.strip().splitlines()[-1])

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_no_error(self):
        self.assertNotIn("error", self.res)

    def test_G_static_value_kept_when_live_fails(self):
        r = self.res["liveFail"]
        sr = g.static_pair_rate("USD", "EUR", SNAP)
        want = f"1 USD = {g.format_rate_value(sr['rate'], sr['sig'])} EUR"
        self.assertEqual(r["main"], want)
        self.assertEqual(r["badge"], f"SNAPSHOT · {SNAP['as_of']}")
        self.assertEqual(len(r["rows"]), 9)
        for seen in r["seen"]:
            self.assertNotIn("Loading", seen)
            self.assertNotIn("unavailable", seen.lower())

    def test_js_disabled_shows_static_answer(self):
        r = self.res["nojs"]
        self.assertTrue(r["main"].startswith("1 USD = "))
        self.assertEqual(len(r["rows"]), 9)
        self.assertIn(SNAP["as_of"], r["note"])

    def test_live_value_replaces_and_is_labelled_live(self):
        r = self.res["liveOk"]
        self.assertEqual(r["main"], "1 USD = 0.950 EUR")
        self.assertEqual(r["badge"], "LIVE · 2099-01-02")
        self.assertIn("Live reference value", r["note"])
        self.assertEqual(r["rows"][0], ["1 USD", "0.950 EUR"])

    def test_newer_snapshot_upgrades(self):
        r = self.res["newerSnap"]
        self.assertEqual(r["main"], "1 USD = 0.500 EUR")
        self.assertEqual(r["badge"], "SNAPSHOT · 2099-01-01")

    def test_unsupported_stays_truthful(self):
        for key in ("unsupported", "unsupportedNoJs"):
            r = self.res[key]
            self.assertEqual(r["main"], "No reference rate available")
            self.assertEqual(r["badge"], "NO RATE")
            self.assertEqual(len(r["rows"]), 1)

    def test_K_js_formatter_parity(self):
        self.assertEqual(self.res["liveFail"]["fmt"], [g.format_rate_value(v, s) for v, s in self.cases])


if __name__ == "__main__":
    unittest.main()
