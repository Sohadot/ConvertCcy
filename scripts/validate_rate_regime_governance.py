#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_rate_regime_governance.py — SEO-A4.6B gate for rate-regime-governed pair pages and hubs.

Cohort comes from the policy router (generate.pair_semantic_treatment ==
"rate_regime_governed"), whose membership is rate_regime_governance in
data/live_fiat_reference_snapshot.json. Fails closed unless:

  model        live_fiat_reference.validate_rate_regime passes; no governed code is an
               A4.6A (live-fiat coverage) code; every governed code has a provider value
  cohort       every pair with a governed side is rate_regime_governed unless standards /
               historical / metal / institutional / live-fiat precedence governs; no
               rate_regime_governed pair lacks a governed side
  every page   the rate-regime card is present with the pair's mode and one block per
               governed side carrying its effective provider policy; every regime of that
               side is listed with its evidence state and no issuer/market figure;
               every claim in the card is source-cited; title/og/twitter/WebPage equal the
               resolver; visible FAQ == FAQPage JSON-LD; robots follow policy and sitemap
               membership agrees; single self-canonical; page equals generator output
  converter    A3 snapshot converter, rate runtime and WebApplication present (only when
               every governed side permits conversion)
  comparison   data-mode="rate_regime", value labelled provider comparison only and equal
               to the snapshot derivation; no converter, rate runtime, table rows or
               WebApplication
  none         no number for the pair at all (rate, inverse or table), no converter,
               rate runtime or WebApplication
  hubs         generator output, index,follow, self-canonical, in sitemap, regimes,
               provider use, provenance and FAQ (with JSON-LD parity), no WebApplication,
               all pair links kept, converter headings only where conversion is allowed

Run: python3 scripts/validate_rate_regime_governance.py
"""

from __future__ import annotations

import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (REPO, REPO / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import generate as g  # noqa: E402
import instrument_policy as ip  # noqa: E402
import live_fiat_reference as lf  # noqa: E402

LD_RE = re.compile(r'(?s)<script type="application/ld\+json">\n(.*?)\n</script>')
VIS_RE = re.compile(r'(?s)<div class="faq-q"[^>]*>(.*?)</div>\s*<div class="faq-a">(.*?)</div>')
HUB_FAQ_RE = re.compile(r'<div class="hub-faq"><h3>([^<]*)</h3><p>([^<]*)</p></div>')
CLAIM_RE = re.compile(r"<span data-claim>([^<]*)</span>")
LOC_RE = re.compile(r"<loc>https://convertccy\.com/([^<]*)</loc>")
CARD_RE = re.compile(r'(?s)<div class="card" data-rate-regime-card="([a-z]+)">(.*?)\n  </div>\n')


def meta(page, attr, name):
    m = re.search(rf'<meta {attr}="{re.escape(name)}" content="([^"]*)">', page)
    return html.unescape(m.group(1)) if m else None


def higher_precedence(pol, a, b):
    beh = pol.resolve_pair(a, b)["converter_behavior"]
    if beh == "none":
        return "standards_special"
    if beh == "archival_only":
        return "historical"
    if pol.is_precious_metal(a) or pol.is_precious_metal(b):
        return "precious_metal"
    if pol.is_institutional_unit(a) or pol.is_institutional_unit(b):
        return "institutional_unit"
    if g.is_live_fiat(a) or g.is_live_fiat(b):
        return "live_fiat_coverage"
    return None


def check_pair(page, profile, currencies, content, fx, sitemap_locs):
    errs = []
    tokens = g.make_pair_tokens(profile, currencies)
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    rel = f'pages/{profile["pair_slug"]}.html'
    view = g.rate_regime_pair(F, T, fx)
    mode = view["mode"]
    card = CARD_RE.search(page)
    if not card or card.group(1) != mode:
        return [f"rate-regime card missing or mode != {mode}"], mode
    body = card.group(2)
    for c in view["sides"]:
        rv = g.rate_regime_view(c)
        eff = view["effective"][c]
        if f'data-rate-regime-code="{c}" data-provider-policy="{eff["policy"]}"' not in body:
            errs.append(f"{c}: regime block missing or wrong provider policy")
        for r in rv["regimes"]:
            if f'data-regime-id="{r["regime_id"]}" data-evidence="{r["evidence_state"]}"' not in body:
                errs.append(f"{c}: regime {r['regime_id']} not exposed")
            if r["value"] is None and r["license_state"] in ("license_unclear", "not_usable") and \
                    "value not republished" not in body:
                errs.append(f"{c}: withheld regime value not declared")
    cited_all = {x["text"] for c in view["sides"] for k in ("identity_claims", "coverage_claims", "regime_claims")
                 for x in g.rate_regime_view(c)[k]}
    for text in CLAIM_RE.findall(body):
        if html.unescape(text) not in cited_all:
            errs.append(f"uncited claim {text[:60]!r}")
    brand = content.get("site_copy", {}).get("brand_name", g.SITE_NAME)
    md = g.rate_regime_pair_metadata(tokens, brand, fx)
    blocks = []
    for blk in LD_RE.findall(page):
        try:
            blocks.append(json.loads(blk))
        except ValueError:
            errs.append("malformed JSON-LD")
    graph_types = [n.get("@type") for x in blocks for n in x.get("@graph", [])]
    want_graph = ["WebPage", "WebApplication"] if mode == "converter" else ["WebPage"]
    if graph_types != want_graph:
        errs.append(f"structured data {graph_types} != {want_graph} for mode {mode}")
    wp = [n for x in blocks for n in x.get("@graph", []) if n.get("@type") == "WebPage"]
    title = html.unescape(re.search(r"<title>([^<]*)</title>", page).group(1))
    if wp:
        for label, val, want in (("title", title, md["title"]), ("og:title", meta(page, "property", "og:title"), md["title"]),
                                 ("WebPage name", wp[0].get("name"), md["title"]),
                                 ("description", meta(page, "name", "description"), md["description"]),
                                 ("WebPage description", wp[0].get("description"), md["description"])):
            if val != want:
                errs.append(f"{label} drifts from the rate-regime metadata resolver")
    faqs = [x for x in blocks if x.get("@type") == "FAQPage"]
    if len(faqs) != 1:
        errs.append(f"{len(faqs)} FAQPage blocks")
    else:
        ld = [(e["name"], e["acceptedAnswer"]["text"]) for e in faqs[0]["mainEntity"]]
        if ld != [(html.unescape(q), html.unescape(a)) for q, a in VIS_RE.findall(page)]:
            errs.append("visible FAQ != FAQPage JSON-LD")
    robots = meta(page, "name", "robots")
    if robots != g.pair_robots(F, T):
        errs.append(f"robots {robots!r} != policy")
    if (rel in sitemap_locs) != (robots == g.INDEXABLE_ROBOTS):
        errs.append("sitemap membership disagrees with robots")
    if re.findall(r'<link rel="canonical" href="([^"]+)">', page) != [f"{g.BASE_URL}/{rel}"]:
        errs.append("canonical is not a single self-canonical")
    sr = g.static_pair_rate(F, T, fx)
    rate_s = g.format_rate_value(sr["rate"], sr["sig"])
    inv_s = g.format_rate_value(sr["inverse"], sr["sig"])
    has_runtime = g.RATE_SCRIPT_SRC in page
    if mode == "converter":
        if 'data-mode="snapshot"' not in page or "data-rate=" not in page or 'id="from-input"' not in page or not has_runtime:
            errs.append("converter mode without the A3 converter, snapshot state and runtime")
    else:
        for f in ('id="from-input"', "data-rate=", "data-amount=", ">Currency Converter<", 'data-mode="snapshot"'):
            if f in page:
                errs.append(f"converter / FX state {f!r} on a {mode} page")
        if has_runtime:
            errs.append(f"rate runtime on a {mode} page")
        if 'data-mode="rate_regime"' not in page:
            errs.append("rate_regime mode banner missing")
    if mode == "comparison":
        want = f'<span data-value-type="provider_comparison">1 {F} = {rate_s} {T}</span>'
        if want not in page or "COMPARISON ONLY" not in page:
            errs.append("comparison value missing, unlabelled or not the snapshot derivation")
    if mode == "none":
        text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", page))
        for s in (rate_s, inv_s):
            if re.search(r"(?<![\d.,])" + re.escape(s) + r"(?![\d,]|\.\d)", text):
                errs.append(f"provider number {s} rendered although the provider regime is unresolved")
        if 'data-value-type="unavailable"' not in page:
            errs.append("no-number page lacks value type unavailable")
    expected = g.replace_static_rate_regions(page, profile, tokens, fx)
    expected = g.apply_rate_regime_semantics(expected, profile, tokens, content, fx)
    if expected != page:
        errs.append("page differs from generator output (run: python3 generate.py --rate-regime-governance-only)")
    return errs, mode


def check_hub(code, currencies, gov, sitemap_locs, snap, fx):
    errs = []
    rel = f"currencies/{code.lower()}.html"
    page = (REPO / rel).read_text(encoding="utf-8")
    rv = g.rate_regime_view(code)
    eff = lf.effective_provider_policy(code, snap, fx)
    if page != g.build_currency_hub_page(code, currencies, gov):
        errs.append("hub differs from generator output")
    if meta(page, "name", "robots") != "index,follow" or rel not in sitemap_locs:
        errs.append("hub must be index,follow and listed in the sitemap")
    if re.findall(r'<link rel="canonical" href="([^"]+)">', page) != [f"{g.BASE_URL}/{rel}"]:
        errs.append("hub canonical is not self")
    for r in rv["regimes"]:
        if f'data-regime-id="{r["regime_id"]}" data-evidence="{r["evidence_state"]}"' not in page:
            errs.append(f"hub lacks regime {r['regime_id']}")
    for need in ("<h2>Rate regimes</h2>", "<h2>Provenance</h2>", "<h2>Provider value and how it is used</h2>",
                 f'data-provider-policy="{eff["policy"]}"', g.esc(rv["decision_reason"])):
        if need not in page:
            errs.append(f"hub lacks {need[:50]!r}")
    blocks = [json.loads(b) for b in LD_RE.findall(page)]
    types = [x.get("@type") for x in blocks]
    if "WebPage" not in types or "FAQPage" not in types or "WebApplication" in page:
        errs.append(f"hub structured data wrong: {types}")
    faq = next((x for x in blocks if x.get("@type") == "FAQPage"), None)
    if faq and [(e["name"], e["acceptedAnswer"]["text"]) for e in faq["mainEntity"]] != \
            [(html.unescape(q), html.unescape(a)) for q, a in HUB_FAQ_RE.findall(page)]:
        errs.append("hub visible FAQ != FAQPage JSON-LD")
    converter = eff["policy"] in ("secondary_provider_value", "governed_primary")
    if not converter and ("<h2>Convert" in page or "Currency Pairs" in page):
        errs.append("hub uses converter wording although conversion is not allowed")
    for o in currencies:
        if o != code and (f'href="{g.pair_href(code, o)}"' not in page or f'href="{g.pair_href(o, code)}"' not in page):
            errs.append(f"hub lost a pair link with {o}")
            break
    return errs


def main() -> int:
    fx = g.load_rate_snapshot()
    pol = g.instrument_policy_layer()
    currencies = g.load_currencies()
    content = g.load_content_blocks()
    profiles = g.load_pair_profiles()
    gov = g.load_governed_currency_map()
    snap = lf.load_live_fiat_snapshot()
    failures = []
    errs = lf.validate_rate_regime(snap, ip.load_raw(), fx)
    if errs:
        failures.append(("rate-regime model", errs[:5]))
    governed = set(lf.regime_codes(snap))
    overlap = governed & set(lf.covered_codes(snap))
    if overlap:
        failures.append(("scope", [f"codes in both A4.6A and A4.6B: {sorted(overlap)}"]))
    missing = sorted(c for c in governed if c not in fx["rates"])
    if missing:
        failures.append(("scope", [f"governed codes without a provider value: {missing}"]))
    sitemap_locs = set(u[len(g.BASE_URL) + 1:] for u in g.read_sitemap_locs(REPO))   # SEO-A5.1: index + child sitemaps
    counts = Counter()
    for profile in profiles.values():
        a, b = profile["from_code"], profile["to_code"]
        if a == b:
            continue
        t = g.pair_semantic_treatment(a, b, fx)
        counts[f"treatment_{t}"] += 1
        rel = f'pages/{profile["pair_slug"]}.html'
        if a in governed or b in governed:
            want = higher_precedence(pol, a, b) or "rate_regime_governed"
            if t != want:
                failures.append((rel, [f"router precedence: {t} != {want}"]))
        elif t == "rate_regime_governed":
            failures.append((rel, ["rate_regime_governed without a governed side"]))
        if t != "rate_regime_governed":
            continue
        for c in governed:
            if c in (a, b):
                counts[f"code_{c}"] += 1
        page = (REPO / rel).read_text(encoding="utf-8")
        errs, mode = check_pair(page, profile, currencies, content, fx, sitemap_locs)
        counts[f"mode_{mode}"] += 1
        if errs:
            failures.append((rel, errs))
    for c in sorted(governed):
        errs = check_hub(c, currencies, gov, sitemap_locs, snap, fx)
        if errs:
            failures.append((f"hub {c}", errs))
        counts["governed_hubs"] += 1
    print("rate-regime governance: " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if failures:
        print(f"FAIL: {len(failures)}")
        for name, errs in failures[:25]:
            print(f"  - {name}: {errs[:3]}")
        return 1
    print("PASS: rate-regime-governed pair pages, hubs and model")
    return 0


if __name__ == "__main__":
    sys.exit(main())
