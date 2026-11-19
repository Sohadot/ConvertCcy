#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEO-A4.6A — residual unsupported live-fiat coverage (KPW, VED).

Locks in:
  * cohort: exactly 602 pairs route to live_fiat_coverage (KPW 302, VED 302, KPW<->VED 2);
    no published pair is unsupported_specialized any more
  * precedence: standards / historical / metal / institutional still win over live fiat
  * exclusion: CUP, IRR, MMK, SYP, TMT, VES (and every pair without a covered side) route
    exactly as they do with the layer disabled; the scope rule rejects any code that has
    a provider value
  * numeric fail-closed: a verified, licensable, fresh synthetic value renders; an
    unresolved licence, unresolved regime, stale value, missing provenance or a
    secondary-press / FX-provider source blocks it
  * structured data: WebPage + BreadcrumbList + FAQPage, no WebApplication, FAQ parity
  * idempotence and generator parity; semantic freeze of controls and shared artifacts
"""

from __future__ import annotations

import copy
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
import instrument_policy as ip  # noqa: E402
import live_fiat_reference as lf  # noqa: E402

FX = g.load_rate_snapshot()
CUR = g.load_currencies()
CONTENT = g.load_content_blocks()
PROFILES = g.load_pair_profiles()
SNAP = lf.load_live_fiat_snapshot()
CLASS = ip.load_raw()
LD_RE = re.compile(r'(?s)<script type="application/ld\+json">\n(.*?)\n</script>')
VIS_RE = re.compile(r'(?s)<div class="faq-q"[^>]*>(.*?)</div>\s*<div class="faq-a">(.*?)</div>')
A46B = ("CUP", "IRR", "MMK", "SYP", "TMT", "VES")
DRIFT_OLD = "the governed declaration threshold and exchange-control posture"
DRIFT_NEW = "the governed border-cash controls and exchange-control profile"


def page(slug):
    return (REPO / "pages" / f"{slug}.html").read_text(encoding="utf-8")


class _SnapshotSwap:
    """Temporarily replace the governed live-fiat snapshot seen by the generator."""

    def __init__(self, snap):
        self.snap = snap

    def __enter__(self):
        self.orig = g._LIVE_FIAT_SNAPSHOT
        g._LIVE_FIAT_SNAPSHOT = self.snap
        return self.snap

    def __exit__(self, *exc):
        g._LIVE_FIAT_SNAPSHOT = self.orig


def layer_disabled():
    # SEO-A4.6B: disable both live-fiat layers (A4.6A coverage and A4.6B rate-regime governance)
    # to recover the pre-layer baseline; otherwise KPW/VED pairs with a governed code fall through to A4.6B.
    return _SnapshotSwap(dict(SNAP, currencies={}, rate_regime_governance={"currencies": {}}))


def a46a_disabled():
    """Disable only the A4.6A coverage layer (A4.6B rate-regime governance stays active)."""
    return _SnapshotSwap(dict(SNAP, currencies={}))


def treatments(snapshot_ctx=None):
    out = {}
    for prof in PROFILES.values():
        a, b = prof["from_code"], prof["to_code"]
        if a != b:
            out[(a, b)] = g.pair_semantic_treatment(a, b, FX)
    return out


ROUTED = treatments()


class CohortTest(unittest.TestCase):
    def test_exact_cohort(self):
        cohort = [k for k, t in ROUTED.items() if t == "live_fiat_coverage"]
        self.assertEqual(len(cohort), 602)
        self.assertEqual(sum(1 for a, b in cohort if "KPW" in (a, b)), 302)
        self.assertEqual(sum(1 for a, b in cohort if "VED" in (a, b)), 302)
        self.assertEqual(sorted(k for k in cohort if set(k) == {"KPW", "VED"}), [("KPW", "VED"), ("VED", "KPW")])
        self.assertEqual(sum(1 for a, b in cohort if "KPW" in (a, b) and "VED" not in (a, b)), 300)
        self.assertEqual(sum(1 for a, b in cohort if "VED" in (a, b) and "KPW" not in (a, b)), 300)
        for a, b in cohort:
            self.assertIsNone(g.static_pair_rate(a, b, FX))
        self.assertNotIn("unsupported_specialized", set(ROUTED.values()))

    def test_cohort_comes_from_the_governed_snapshot(self):
        self.assertEqual(lf.covered_codes(SNAP), ["KPW", "VED"])
        with layer_disabled():
            before = treatments()
        moved = {k for k in ROUTED if ROUTED[k] != before[k] and ROUTED[k] == "live_fiat_coverage"}
        self.assertEqual(moved, {k for k, t in ROUTED.items() if t == "live_fiat_coverage"})
        self.assertEqual({before[k] for k in moved}, {"unsupported_specialized"})
        self.assertNotIn("unsupported_specialized", {ROUTED[k] for k in before if before[k] != "unsupported_specialized"})

    def test_totals_unchanged_elsewhere(self):
        from collections import Counter
        self.assertEqual(Counter(ROUTED.values()), Counter({
            "ordinary_fx": 20592, "historical": 2296, "institutional_unit": 1540, "precious_metal": 1268,
            "standards_special": 674, "live_fiat_coverage": 602, "rate_regime_governed": 1758}))   # A4.6B: 1,758 moved


class PrecedenceTest(unittest.TestCase):
    def test_higher_layers_win(self):
        for code in ("KPW", "VED"):
            for other, want in (("XTS", "standards_special"), ("XXX", "standards_special"), ("BGN", "historical"),
                                ("HRK", "historical"), ("XAU", "precious_metal"), ("XAG", "precious_metal"),
                                ("XDR", "institutional_unit"), ("CLF", "institutional_unit"), ("XSU", "institutional_unit")):
                self.assertEqual(g.pair_semantic_treatment(code, other, FX), want, (code, other))
                self.assertEqual(g.pair_semantic_treatment(other, code, FX), want, (other, code))
            self.assertEqual(g.pair_semantic_treatment(code, "USD", FX), "live_fiat_coverage")
            self.assertEqual(g.pair_semantic_treatment("CUP", code, FX), "live_fiat_coverage")

    def test_rate_treatment_and_special(self):
        self.assertEqual(g.pair_rate_treatment("KPW", "USD", FX), "live_fiat_coverage")
        self.assertIn("live_fiat_coverage", g.SPECIAL_TREATMENTS)
        self.assertEqual(g.rate_script_region_html("KPW", "USD", FX), f"{g.RATE_SCRIPT_START}\n{g.RATE_SCRIPT_END}")


class ExclusionTest(unittest.TestCase):
    def test_a46b_codes_route_as_baseline(self):
        with layer_disabled():
            base = treatments()
        for (a, b), t in ROUTED.items():
            if {"KPW", "VED"} & {a, b} or set(A46B) & {a, b}:
                continue
            self.assertEqual(t, base[(a, b)], (a, b))
        for code in A46B:
            # never A4.6A; since SEO-A4.6B these codes are rate-regime governed (their own layer)
            self.assertFalse(g.is_live_fiat(code))
            self.assertEqual(g.pair_semantic_treatment(code, "USD", FX), "rate_regime_governed")
            self.assertEqual(g.pair_semantic_treatment("EUR", code, FX), "rate_regime_governed")
            self.assertEqual(base[(code, "USD")], "ordinary_fx")

    def test_scope_rule_rejects_provider_valued_codes(self):
        for code in A46B + ("USD",):
            bad = copy.deepcopy(SNAP)
            entry = copy.deepcopy(SNAP["currencies"]["KPW"])
            entry.update(currency_code=code, classification_confidence=CLASS["instruments"][code]["classification_confidence"],
                         review_flags=CLASS["instruments"][code]["review_flags"])
            bad["currencies"][code] = entry
            errs = lf.validate_live_fiat_snapshot(bad, CLASS, FX)
            self.assertTrue(any("FX provider publishes a value" in e for e in errs), code)

    def test_scope_rule_rejects_non_fiat_and_a41_disagreement(self):
        bad = copy.deepcopy(SNAP)
        bad["currencies"]["XDR"] = dict(copy.deepcopy(SNAP["currencies"]["KPW"]), currency_code="XDR")
        self.assertTrue(any("out of scope: A4.1 type" in e for e in lf.validate_live_fiat_snapshot(bad, CLASS, FX)))
        bad2 = copy.deepcopy(SNAP)
        bad2["currencies"]["VED"]["review_flags"] = []
        self.assertTrue(any("review_flags disagree" in e for e in lf.validate_live_fiat_snapshot(bad2, CLASS, FX)))
        bad3 = copy.deepcopy(SNAP)
        bad3["currencies"]["KPW"]["classification_confidence"] = "low"
        self.assertTrue(any("classification_confidence disagrees" in e for e in lf.validate_live_fiat_snapshot(bad3, CLASS, FX)))

    def test_snapshot_valid_and_reference_only(self):
        self.assertEqual(lf.validate_live_fiat_snapshot(SNAP, CLASS, FX), [])
        self.assertEqual(SNAP["activation_state"], "reference_layer_only")
        self.assertEqual(SNAP["values"], [])
        self.assertIsNone(SNAP["captured_at"])
        bad = copy.deepcopy(SNAP)
        bad["captured_at"] = "2026-11-19T00:00:00Z"
        self.assertTrue(any("no fabricated timestamp" in e for e in lf.validate_live_fiat_snapshot(bad, CLASS, FX)))

    def test_provider_value_never_promoted(self):
        bad = copy.deepcopy(SNAP)
        bad["currencies"]["KPW"]["provider_value"] = "900"
        self.assertTrue(any("without an identified regime" in e for e in lf.validate_live_fiat_snapshot(bad, CLASS, FX)))

    def test_secondary_press_only_as_reported_indicator(self):
        bad = copy.deepcopy(SNAP)
        bad["currencies"]["KPW"]["identity_claims"].append({"text": "x", "source": "dailynk_market_rate_2026_04"})
        self.assertTrue(any("secondary press may support only reported indicators" in e
                            for e in lf.validate_live_fiat_snapshot(bad, CLASS, FX)))
        bad2 = copy.deepcopy(SNAP)
        bad2["currencies"]["KPW"]["reported_indicators"][0]["text"] = "Daily NK reports 70,100 won per dollar."
        self.assertTrue(any("states a rate figure" in e for e in lf.validate_live_fiat_snapshot(bad2, CLASS, FX)))


def activated(**over):
    """Synthetic activated snapshot for KPW (test fixture only — never committed data)."""
    s = copy.deepcopy(SNAP)
    s["activation_state"] = "source_activated"
    s["captured_at"] = FX["captured_at"]
    s["sources"].append({"id": "t_issuer", "title": "Test issuer", "url": "https://example.org/t", "authority": "Test Issuer",
                         "source_tier": over.pop("tier", "issuer"), "accessed": "2026-11-19", "access_state": "accessible",
                         "license_state": over.pop("source_license", "redistribution_permitted"), "role": "test"})
    k = s["currencies"]["KPW"]
    k.update(availability_status="live_verified", rate_regime=over.pop("regime", "official_reference"),
             value_source="t_issuer", freshness_policy="official_daily", license_state="redistribution_permitted",
             official_reference_value="0.0100")
    v = {"currency_code": "KPW", "quote_currency": "USD", "rate_regime": "official_reference", "value": "0.0100",
         "valuation_date": FX["captured_at"][:10], "source_id": "t_issuer", "source_timestamp": FX["captured_at"],
         "retrieved_at": FX["captured_at"], "license_state": "redistribution_permitted", "freshness_policy": "official_daily",
         "provenance_id": "t1", "derived": False}
    v.update(over)
    s["values"] = [v]
    return s


class NumericFailClosedTest(unittest.TestCase):
    def view(self, s, a="KPW", b="USD"):
        return lf.value_view(a, b, s, FX, g.format_rate_value)

    def test_verified_licensable_fresh_value_renders(self):
        s = activated()
        self.assertEqual(lf.validate_live_fiat_snapshot(s, CLASS, FX), [])
        d = self.view(s)
        self.assertEqual((d["value_type"], d["derived"], d["value_text"]), ("official_reference", False, "0.0100"))
        inv = self.view(s, "USD", "KPW")
        self.assertEqual((inv["value_type"], inv["derived"], inv["derivation_method"]), ("derived_reference_value", True, "inverse"))
        x = self.view(s, "KPW", "EUR")
        self.assertEqual((x["value_type"], x["derived"]), ("derived_reference_value", True))
        self.assertEqual(x["fx_timestamp"], FX["captured_at"])
        self.assertEqual(self.view(s, "KPW", "VED")["value_type"], "unavailable")   # both sides uncovered by the provider
        with _SnapshotSwap(s):
            tok = g.make_pair_tokens(PROFILES["KPW_USD"], CUR)
            region = g.live_fiat_rate_region_html(tok, FX)
            self.assertIn('data-value-type="official_reference">1 KPW = 0.0100 USD', region)
            self.assertIn("OFFICIAL REFERENCE · " + FX["captured_at"][:10], region)
            self.assertIn("Direct official reference rate published by Test Issuer", region)
            tok2 = g.make_pair_tokens(PROFILES["KPW_EUR"], CUR)
            self.assertIn("DERIVED FROM OFFICIAL REFERENCE RATE", g.live_fiat_rate_region_html(tok2, FX))
            self.assertIn("FX timestamp:", g.live_fiat_rate_region_html(tok2, FX))

    def test_licence_unresolved_blocks(self):
        s = activated(source_license="license_unclear", license_state="license_unclear")
        self.assertEqual(self.view(s)["value_type"], "unavailable")
        self.assertTrue(lf.validate_live_fiat_snapshot(s, CLASS, FX))

    def test_regime_unresolved_blocks(self):
        self.assertEqual(self.view(activated(regime="unresolved"))["value_type"], "unavailable")
        self.assertEqual(self.view(activated(rate_regime="market_reference"))["value_type"], "unavailable")

    def test_stale_blocks(self):
        s = activated(source_timestamp="2026-11-01T00:00:00Z", retrieved_at="2026-11-01T00:00:00Z")
        self.assertEqual(self.view(s)["value_type"], "unavailable")

    def test_missing_provenance_or_dates_block(self):
        for over in ({"provenance_id": ""}, {"valuation_date": ""}, {"retrieved_at": "2020-01-01T00:00:00Z"}):
            self.assertEqual(self.view(activated(**over))["value_type"], "unavailable", over)

    def test_unauthoritative_tiers_block(self):
        for tier in ("secondary_press", "fx_provider", "standards_registry"):
            self.assertEqual(self.view(activated(tier=tier))["value_type"], "unavailable", tier)

    def test_reference_layer_only_never_renders(self):
        s = activated()
        s["activation_state"] = "reference_layer_only"
        self.assertEqual(self.view(s)["value_type"], "unavailable")
        self.assertEqual(g.live_fiat_value("KPW", "USD", FX)["value_type"], "unavailable")


class PageSemanticsTest(unittest.TestCase):
    def test_structured_data_and_faq_parity(self):
        for slug in ("kpw-to-usd", "usd-to-kpw", "ved-to-eur", "kpw-to-ved", "cup-to-kpw"):
            t = page(slug)
            blocks = [json.loads(b) for b in LD_RE.findall(t)]
            self.assertNotIn("WebApplication", t)
            self.assertEqual([n["@type"] for x in blocks for n in x.get("@graph", [])], ["WebPage"])
            self.assertEqual(sorted(x["@type"] for x in blocks if "@type" in x), ["BreadcrumbList", "FAQPage"])
            faq = next(x for x in blocks if x.get("@type") == "FAQPage")
            import html as _h
            self.assertEqual([(e["name"], e["acceptedAnswer"]["text"]) for e in faq["mainEntity"]],
                             [(_h.unescape(q), _h.unescape(a)) for q, a in VIS_RE.findall(t)])

    def test_kpw_semantics(self):
        t = page("kpw-to-usd")
        self.assertIn("<title>KPW to USD — North Korean Won Coverage Reference | ConvertCCY</title>", t)
        self.assertIn('data-mode="live_fiat"', t)
        self.assertIn('data-availability="official_source_unresolved"', t)
        self.assertIn('data-rate-regime="unresolved"', t)
        self.assertIn("It is a real currency", t)
        self.assertNotIn("Converter", re.search(r"<title>[^<]*</title>", t).group(0))
        self.assertNotIn("data-rate=", t)
        self.assertNotIn(g.RATE_SCRIPT_SRC, t)
        self.assertNotIn(">NO RATE<", t)
        self.assertIn('<meta name="robots" content="index,follow,max-image-preview:large">', t)
        self.assertIn('<link rel="canonical" href="https://convertccy.com/pages/kpw-to-usd.html">', t)

    def test_ved_semantics_no_alias(self):
        t = page("ved-to-usd")
        self.assertIn("Code-Status Reference", t)
        self.assertIn('data-operative-code="VES"', t)
        self.assertIn('href="/currencies/ves.html"', t)
        self.assertIn("ConvertCCY does not treat VED as an alias of VES", t)
        ves = g.static_pair_rate("VES", "USD", FX)
        for s in (g.format_rate_value(ves["rate"], ves["sig"]), g.format_rate_value(ves["inverse"], ves["sig"])):
            self.assertNotIn(s, t)

    def test_hubs(self):
        for code, word in (("KPW", "Coverage Reference"), ("VED", "Code-Status Reference")):
            t = (REPO / "currencies" / f"{code.lower()}.html").read_text(encoding="utf-8")
            self.assertIn(word, re.search(r"<title>[^<]*</title>", t).group(0))
            self.assertNotIn("<h2>Convert", t)
            self.assertIn("<h2>Provenance</h2>", t)
            self.assertNotIn("WebApplication", t)
            self.assertEqual(t, g.build_currency_hub_page(code, CUR, g.load_governed_currency_map()))


class IdempotenceAndFreezeTest(unittest.TestCase):
    def test_second_targeted_run_changes_nothing(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            changed, unchanged, hubs = g.refresh_live_fiat_coverage(CUR, CONTENT, PROFILES)
        self.assertEqual((changed, unchanged, hubs), (0, 602, 0))

    def test_full_build_parity(self):
        codes = list(g.site_currency_order(CUR.keys()))
        gov, imp = g.load_governed_currency_map(), g.build_pair_importance_index(PROFILES)
        for key in ("KPW_USD", "USD_VED", "KPW_VED", "CUP_KPW", "VED_IRR"):
            full = g.build_pair_page(PROFILES[key], CUR, CONTENT, codes, gov, imp, FX)
            disk = page(PROFILES[key]["pair_slug"])
            self.assertTrue(full == disk or full.replace(DRIFT_NEW, DRIFT_OLD) == disk, key)

    def test_controls_unaffected_by_layer(self):
        codes = list(g.site_currency_order(CUR.keys()))
        gov, imp = g.load_governed_currency_map(), g.build_pair_importance_index(PROFILES)
        keys = ("USD_EUR", "BGN_EUR", "USD_XTS", "XAU_USD", "XDR_USD", "CLF_USD",
                "CUP_USD", "IRR_USD", "MMK_USD", "SYP_USD", "TMT_USD", "VES_USD", "USD_VES", "EUR_CUP")
        with_layer = {k: g.build_pair_page(PROFILES[k], CUR, CONTENT, codes, gov, imp, FX) for k in keys}
        with a46a_disabled():
            without = {k: g.build_pair_page(PROFILES[k], CUR, CONTENT, codes, gov, imp, FX) for k in keys}
            hubs_without = {c: g.build_currency_hub_page(c, CUR, gov) for c in ("USD", "VES", "CUP", "XDR")}
        for k in keys:
            self.assertEqual(with_layer[k], without[k], k)
            disk = page(PROFILES[k]["pair_slug"])
            self.assertTrue(with_layer[k] == disk or with_layer[k].replace(DRIFT_NEW, DRIFT_OLD) == disk, k)
        for c, h in hubs_without.items():
            self.assertEqual(h, g.build_currency_hub_page(c, CUR, gov), c)
            self.assertEqual(h, (REPO / "currencies" / f"{c.lower()}.html").read_text(encoding="utf-8"), c)

    def test_sitemap_membership_matches_indexability(self):
        locs = set(u[len(g.BASE_URL) + 1:] for u in g.read_sitemap_locs(REPO))   # SEO-A5.1: index + children
        for (a, b), t in ROUTED.items():
            if t == "live_fiat_coverage":
                self.assertEqual(g.pair_robots(a, b), g.INDEXABLE_ROBOTS)
                self.assertIn(f"pages/{a.lower()}-to-{b.lower()}.html", locs)
        self.assertIn("currencies/kpw.html", locs)
        self.assertIn("currencies/ved.html", locs)

    def test_gate_passes(self):
        import contextlib
        import io
        import validate_live_fiat_coverage as gate
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gate.main(), 0)


if __name__ == "__main__":
    unittest.main()
