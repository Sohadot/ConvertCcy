#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEO-A4.6B — rate-regime governance for provider-valued live fiat (CUP, IRR, MMK, SYP, TMT, VES).

Locks in:
  * source model: single official (VES/SYP), official + parallel (TMT), official + market
    trading (MMK), multiple official segments (CUP), provider regime unresolved (IRR), and a
    synthetic fixed official reference
  * provider comparison: official match within tolerance, divergence, date skew, stale /
    drifted provider values (policy downgrade), unresolved provider regime (no number)
  * licensing: a verified, licensed, activated value may be stored and rendered; unclear or
    not-usable sources block it
  * rendering: labels, no unlabeled number, converter only where allowed, FAQ / JSON-LD parity
  * router: A4.2–A4.6A precedence unchanged, KPW/VED stay A4.6A, other ordinary codes unchanged
  * idempotence, generator parity and semantic freeze of controls and A4.6A surfaces
"""

from __future__ import annotations

import contextlib
import copy
import html
import io
import json
import re
import sys
import unittest
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import generate as g  # noqa: E402
import instrument_policy as ip  # noqa: E402
import live_fiat_reference as lf  # noqa: E402

FX = g.load_rate_snapshot()
CUR = g.load_currencies()
CONTENT = g.load_content_blocks()
PROFILES = g.load_pair_profiles()
SNAP = lf.load_live_fiat_snapshot()
CLASS = ip.load_raw()
SIX = ("CUP", "IRR", "MMK", "SYP", "TMT", "VES")
LD_RE = re.compile(r'(?s)<script type="application/ld\+json">\n(.*?)\n</script>')
VIS_RE = re.compile(r'(?s)<div class="faq-q"[^>]*>(.*?)</div>\s*<div class="faq-a">(.*?)</div>')
DRIFT_OLD = "the governed declaration threshold and exchange-control posture"
DRIFT_NEW = "the governed border-cash controls and exchange-control profile"


def page(slug):
    return (REPO / "pages" / f"{slug}.html").read_text(encoding="utf-8")


def errs(s, fx=FX):
    return lf.validate_rate_regime(s, CLASS, fx)


def rr(s, code):
    return s["rate_regime_governance"]["currencies"][code]


class _Swap:
    def __init__(self, snap):
        self.snap = snap

    def __enter__(self):
        self.orig = g._LIVE_FIAT_SNAPSHOT
        g._LIVE_FIAT_SNAPSHOT = self.snap
        return self.snap

    def __exit__(self, *exc):
        g._LIVE_FIAT_SNAPSHOT = self.orig


def governance_disabled():
    return _Swap(dict(SNAP, rate_regime_governance={"currencies": {}}))


def routed():
    out = {}
    for prof in PROFILES.values():
        a, b = prof["from_code"], prof["to_code"]
        if a != b:
            out[(a, b)] = g.pair_semantic_treatment(a, b, FX)
    return out


ROUTED = routed()


class SourceModelTest(unittest.TestCase):
    def test_committed_model_valid(self):
        self.assertEqual(errs(SNAP), [])
        self.assertEqual(lf.validate_live_fiat_snapshot(SNAP, CLASS, FX), [])
        self.assertEqual(lf.regime_codes(SNAP), sorted(SIX))

    def test_decisions(self):
        want = {"CUP": ("multi_segment_official", "comparison_only"), "IRR": ("official_source_unresolved", "suppressed"),
                "MMK": ("official_reference_plus_market_trading", "comparison_only"),
                "SYP": ("single_official_reference", "secondary_provider_value"),
                "TMT": ("official_reference_plus_parallel_market", "secondary_provider_value"),
                "VES": ("single_official_reference", "secondary_provider_value")}
        for c, (rt, pol) in want.items():
            self.assertEqual((rr(SNAP, c)["regime_type"], rr(SNAP, c)["provider_policy"]), (rt, pol), c)

    def test_no_issuer_or_market_figure_stored(self):
        for c in SIX:
            for r in rr(SNAP, c)["regimes"]:
                self.assertIsNone(r["value"], (c, r["regime_id"]))
                self.assertTrue(r["value_withheld_reason"])

    def test_multi_regime_requires_every_regime(self):
        s = copy.deepcopy(SNAP)
        rr(s, "MMK")["regimes"] = rr(s, "MMK")["regimes"][:1]
        rr(s, "MMK")["provider"]["comparisons"] = rr(s, "MMK")["provider"]["comparisons"][:1]
        self.assertTrue(any("must expose every relevant regime" in e for e in errs(s)))

    def test_fixed_official_reference_supported(self):
        s = copy.deepcopy(SNAP)
        t = rr(s, "TMT")
        t["regime_type"] = "fixed_official_reference"
        t["regimes"] = [r for r in t["regimes"] if r["regime_id"] == "cbt_official"]
        self.assertEqual(errs(s), [])

    def test_unresolved_provider_regime_shows_no_number(self):
        s = copy.deepcopy(SNAP)
        rr(s, "IRR")["provider_policy"] = "comparison_only"
        self.assertTrue(any("unresolved / conflicting provider regime may not show a number" in e for e in errs(s)))

    def test_scope_rule(self):
        s = copy.deepcopy(SNAP)
        s["rate_regime_governance"]["currencies"]["KPW"] = dict(copy.deepcopy(rr(s, "TMT")), currency_code="KPW")
        e = errs(s)
        self.assertTrue(any("also governed by live-fiat coverage" in x for x in e))
        self.assertTrue(any("no provider value" in x for x in e))
        s2 = copy.deepcopy(SNAP)
        rr(s2, "CUP")["review_flags"] = []
        self.assertTrue(any("review_flags disagree" in x for x in errs(s2)))

    def test_secondary_claims_name_the_reporter(self):
        s = copy.deepcopy(SNAP)
        rr(s, "TMT")["regime_claims"][1]["text"] = "A parallel rate coexists with the official rate."
        self.assertTrue(any("must name its source" in x for x in errs(s)))


class ProviderComparisonTest(unittest.TestCase):
    def test_official_match_within_tolerance(self):
        self.assertEqual(rr(SNAP, "MMK")["provider"]["provider_regime_match"], "provider_matches_official_within_tolerance")
        s = copy.deepcopy(SNAP)
        rr(s, "TMT")["provider"]["comparisons"][0]["pct_difference"] = "+0.9"
        self.assertTrue(any("official match needs" in x for x in errs(s)))

    def test_divergence_blocks_converter(self):
        s = copy.deepcopy(SNAP)
        rr(s, "TMT")["provider"]["provider_regime_match"] = "provider_closer_to_market"
        self.assertTrue(any("may power a converter only when it matches an official regime" in x for x in errs(s)))
        s2 = copy.deepcopy(SNAP)
        rr(s2, "MMK")["provider_policy"] = "secondary_provider_value"
        self.assertTrue(any("multiple official regimes" in x for x in errs(s2)))

    def test_date_skew_blocks_match(self):
        s = copy.deepcopy(SNAP)
        rr(s, "TMT")["provider"]["comparisons"][0]["valuation_date_difference_days"] = 3
        self.assertTrue(any("official match needs" in x for x in errs(s)))

    def test_stale_provider_downgrades(self):
        fx = dict(FX, as_of="2026-11-30")
        self.assertEqual(lf.effective_provider_policy("TMT", SNAP, fx)["policy"], "comparison_only")
        self.assertEqual(lf.effective_provider_policy("TMT", SNAP, fx)["reason"], "regime_match_not_reverified")
        self.assertEqual(lf.effective_provider_policy("TMT", SNAP, FX)["policy"], "secondary_provider_value")

    def test_drifted_provider_downgrades(self):
        rates = dict(FX["rates"], TMT=FX["rates"]["TMT"] * 1.03, MMK=FX["rates"]["MMK"] * 1.03)
        fx = dict(FX, rates=rates)
        self.assertEqual(lf.effective_provider_policy("TMT", SNAP, fx)["policy"], "comparison_only")
        self.assertEqual(lf.effective_provider_policy("MMK", SNAP, fx)["policy"], "suppressed")
        self.assertEqual(lf.effective_provider_policy("IRR", SNAP, fx)["policy"], "suppressed")

    def test_pair_modes_combine_fail_closed(self):
        mode = lambda a, b: lf.pair_regime_view(a, b, SNAP, FX)["mode"]   # noqa: E731
        self.assertEqual(mode("TMT", "USD"), "converter")
        self.assertEqual(mode("TMT", "VES"), "converter")
        self.assertEqual(mode("MMK", "TMT"), "comparison")
        self.assertEqual(mode("CUP", "IRR"), "none")
        self.assertEqual(mode("USD", "IRR"), "none")


class LicensingTest(unittest.TestCase):
    def activated(self, lic="redistribution_permitted", rid="cbm_reference", evidence=None):
        s = copy.deepcopy(SNAP)
        s["activation_state"] = "source_activated"
        s["captured_at"] = FX["captured_at"]
        for src in s["sources"]:
            if src["id"] == "cbm_fxrate":
                src["license_state"] = lic
        r = next(x for x in rr(s, "MMK")["regimes"] if x["regime_id"] == rid)
        r.update(value="2100.00", license_state=lic, activation_state="source_activated")
        if evidence:
            r["evidence_state"] = evidence
        return s

    def test_verified_and_permitted_renders(self):
        s = self.activated()
        self.assertEqual(errs(s), [])
        with _Swap(s):
            html_ = g._regime_block(g.rate_regime_view("MMK"), lf.effective_provider_policy("MMK", s, FX), FX)
            self.assertIn("2100.00 (MMK per USD)", html_)

    def test_licence_unclear_blocks_value(self):
        self.assertTrue(any("stores a value without a verified, licensed, activated source" in e
                            for e in errs(self.activated(lic="license_unclear"))))

    def test_not_usable_market_source_blocks_value(self):
        s = copy.deepcopy(SNAP)
        r = next(x for x in rr(s, "IRR")["regimes"] if x["regime_id"] == "tehran_free_market")
        r["value"] = "2711000"
        self.assertTrue(any("stores a value without" in e for e in errs(s)))


class FreshnessTest(unittest.TestCase):
    def test_regime_policies_exist(self):
        for c in SIX:
            for r in rr(SNAP, c)["regimes"]:
                self.assertIn(r["freshness_policy"], SNAP["freshness_policies"])

    def test_fresh_vs_stale_official_value(self):
        pol = SNAP["freshness_policies"]["official_daily"]
        self.assertEqual(lf.freshness("2026-11-18T08:00:00Z", "2026-11-18T12:00:00Z", pol), "current")
        self.assertEqual(lf.freshness("2026-11-10T08:00:00Z", "2026-11-18T12:00:00Z", pol), "stale")
        self.assertEqual(lf.freshness("2026-11-18T08:00:00Z", "2026-11-18T12:00:00Z", SNAP["freshness_policies"]["market_daily"]), "current")

    def test_audit_comparison_dates(self):
        for c in SIX:
            for x in rr(SNAP, c)["provider"]["comparisons"]:
                d = x.get("valuation_date_difference_days")
                self.assertTrue(d is None or abs(d) <= 1, (c, x))


class RenderingTest(unittest.TestCase):
    def ld(self, t):
        return [json.loads(b) for b in LD_RE.findall(t)]

    def faq_parity(self, t):
        faq = next(x for x in self.ld(t) if x.get("@type") == "FAQPage")
        self.assertEqual([(e["name"], e["acceptedAnswer"]["text"]) for e in faq["mainEntity"]],
                         [(html.unescape(q), html.unescape(a)) for q, a in VIS_RE.findall(t)])

    def test_converter_mode(self):
        t = page("usd-to-tmt")
        self.assertIn('data-rate-regime-card="converter"', t)
        self.assertIn('data-mode="snapshot"', t)
        self.assertIn(g.RATE_SCRIPT_SRC, t)
        self.assertIn("It is a provider snapshot, not a CBT publication.", t)
        self.assertEqual([n["@type"] for x in self.ld(t) for n in x.get("@graph", [])], ["WebPage", "WebApplication"])
        self.assertNotIn("shows the latest available reference exchange rate", t)
        self.faq_parity(t)

    def test_comparison_mode(self):
        t = page("mmk-to-usd")
        sr = g.static_pair_rate("MMK", "USD", FX)
        self.assertIn(f'<span data-value-type="provider_comparison">1 MMK = {g.format_rate_value(sr["rate"], sr["sig"])} USD</span>', t)
        self.assertIn("PROVIDER SNAPSHOT · COMPARISON ONLY", t)
        for f in ('id="from-input"', "data-rate=", g.RATE_SCRIPT_SRC, "WebApplication", "data-amount="):
            self.assertNotIn(f, t)
        self.assertIn("Exchange-Rate Regime Reference", re.search(r"<title>[^<]*</title>", t).group(0))
        self.faq_parity(t)

    def test_no_number_mode(self):
        t = page("irr-to-usd")
        sr = g.static_pair_rate("IRR", "USD", FX)
        text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", t))
        for s in (g.format_rate_value(sr["rate"], sr["sig"]), g.format_rate_value(sr["inverse"], sr["sig"])):
            self.assertNotRegex(text, r"(?<![\d.,])" + re.escape(s) + r"(?![\d,]|\.\d)")
        self.assertIn("PROVIDER REGIME UNRESOLVED", t)
        self.assertNotIn("WebApplication", t)
        self.faq_parity(t)

    def test_provider_never_called_official(self):
        for slug in ("usd-to-tmt", "ves-to-usd", "syp-to-eur", "cup-to-usd", "mmk-to-usd"):
            t = html.unescape(re.sub(r"(?s)<[^>]+>", " ", page(slug)))
            self.assertNotRegex(t, r"provider (value|snapshot)[^.]{0,40}\bis the official rate\b")

    def test_every_regime_listed_without_figures(self):
        t = page("cup-to-usd")
        for r in rr(SNAP, "CUP")["regimes"]:
            self.assertIn(f'data-regime-id="{r["regime_id"]}"', t)
        self.assertNotRegex(t, r"\b(120|762|865) CUP\b")

    def test_hubs(self):
        for c in SIX:
            t = (REPO / "currencies" / f"{c.lower()}.html").read_text(encoding="utf-8")
            self.assertEqual(t, g.build_currency_hub_page(c, CUR, g.load_governed_currency_map()))
            self.assertIn("<h2>Rate regimes</h2>", t)
            self.assertNotIn("WebApplication", t)
        for c in ("CUP", "IRR", "MMK"):
            t = (REPO / "currencies" / f"{c.lower()}.html").read_text(encoding="utf-8")
            self.assertNotIn("<h2>Convert", t)
            self.assertIn("Exchange-Rate Regime Reference", re.search(r"<title>[^<]*</title>", t).group(0))
        self.assertIn("<h2>Convert TMT", (REPO / "currencies" / "tmt.html").read_text(encoding="utf-8"))


class RouterTest(unittest.TestCase):
    def test_cohort(self):
        cohort = [k for k, t in ROUTED.items() if t == "rate_regime_governed"]
        self.assertEqual(len(cohort), 1758)
        for c in SIX:
            self.assertEqual(sum(1 for k in cohort if c in k), 298, c)
        modes = Counter(lf.pair_regime_view(a, b, SNAP, FX)["mode"] for a, b in cohort)
        self.assertEqual(modes, Counter({"converter": 870, "comparison": 590, "none": 298}))
        for a, b in cohort:
            self.assertIsNotNone(g.static_pair_rate(a, b, FX))

    def test_precedence(self):
        for c in SIX:
            for other, want in (("XTS", "standards_special"), ("BGN", "historical"), ("XAU", "precious_metal"),
                                ("XDR", "institutional_unit"), ("KPW", "live_fiat_coverage"), ("VED", "live_fiat_coverage")):
                self.assertEqual(g.pair_semantic_treatment(c, other, FX), want, (c, other))
                self.assertEqual(g.pair_semantic_treatment(other, c, FX), want, (other, c))
        self.assertEqual(g.pair_semantic_treatment("KPW", "USD", FX), "live_fiat_coverage")
        self.assertEqual(g.pair_semantic_treatment("VED", "EUR", FX), "live_fiat_coverage")

    def test_only_governed_pairs_moved(self):
        with governance_disabled():
            base = routed()
        moved = {k for k in ROUTED if ROUTED[k] != base[k]}
        self.assertEqual(moved, {k for k, t in ROUTED.items() if t == "rate_regime_governed"})
        self.assertEqual({base[k] for k in moved}, {"ordinary_fx"})

    def test_rate_script_follows_mode(self):
        self.assertIn(g.RATE_SCRIPT_SRC, g.rate_script_region_html("TMT", "USD", FX))
        self.assertNotIn(g.RATE_SCRIPT_SRC, g.rate_script_region_html("MMK", "USD", FX))
        self.assertNotIn(g.RATE_SCRIPT_SRC, g.rate_script_region_html("IRR", "USD", FX))


class IdempotenceAndFreezeTest(unittest.TestCase):
    def test_second_targeted_run_changes_nothing(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(g.refresh_rate_regime_governance(CUR, CONTENT, PROFILES), (0, 1758, 0))

    def test_full_build_parity(self):
        codes = sorted(CUR.keys(), key=lambda x: (x not in g.DEFAULT_POPULAR_CODES, x))
        gov, imp = g.load_governed_currency_map(), g.build_pair_importance_index(PROFILES)
        for key in ("TMT_USD", "MMK_USD", "IRR_EUR", "CUP_TMT", "VES_SYP", "USD_CUP"):
            full = g.build_pair_page(PROFILES[key], CUR, CONTENT, codes, gov, imp, FX)
            disk = page(PROFILES[key]["pair_slug"])
            self.assertTrue(full == disk or full.replace(DRIFT_NEW, DRIFT_OLD) == disk, key)

    def test_controls_and_a46a_unaffected(self):
        codes = sorted(CUR.keys(), key=lambda x: (x not in g.DEFAULT_POPULAR_CODES, x))
        gov, imp = g.load_governed_currency_map(), g.build_pair_importance_index(PROFILES)
        keys = ("USD_EUR", "GBP_USD", "JPY_USD", "BGN_EUR", "USD_XTS", "XAU_USD", "XDR_USD", "CLF_USD",
                "KPW_USD", "USD_VED", "KPW_CUP", "VED_VES")
        hub_codes = ("USD", "KPW", "VED", "XDR", "EUR")
        with_layer = {k: g.build_pair_page(PROFILES[k], CUR, CONTENT, codes, gov, imp, FX) for k in keys}
        with_hubs = {c: g.build_currency_hub_page(c, CUR, gov) for c in hub_codes}
        with governance_disabled():
            for k in keys:
                self.assertEqual(with_layer[k], g.build_pair_page(PROFILES[k], CUR, CONTENT, codes, gov, imp, FX), k)
            for c in hub_codes:
                self.assertEqual(with_hubs[c], g.build_currency_hub_page(c, CUR, gov), c)
        for c in hub_codes:
            self.assertEqual(with_hubs[c], (REPO / "currencies" / f"{c.lower()}.html").read_text(encoding="utf-8"), c)

    def test_sitemap_and_robots_unchanged(self):
        locs = set(u[len(g.BASE_URL) + 1:] for u in g.read_sitemap_locs(REPO))   # SEO-A5.1: index + children
        for (a, b), t in ROUTED.items():
            if t == "rate_regime_governed":
                self.assertEqual(g.pair_robots(a, b), g.INDEXABLE_ROBOTS)
                self.assertIn(f"pages/{a.lower()}-to-{b.lower()}.html", locs)

    def test_gate_passes(self):
        import validate_rate_regime_governance as gate
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gate.main(), 0)


if __name__ == "__main__":
    unittest.main()
