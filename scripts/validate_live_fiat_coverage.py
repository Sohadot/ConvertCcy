#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_live_fiat_coverage.py — SEO-A4.6A gate for live-fiat coverage pair pages and hubs.

Cohort comes from the policy router (generate.pair_semantic_treatment ==
"live_fiat_coverage"), whose membership is data/live_fiat_reference_snapshot.json
under the scope rule. Fails closed unless:

  cohort       every pair with a covered side is live_fiat_coverage unless standards /
               historical / precious-metal / institutional precedence governs; no
               live_fiat_coverage pair lacks a covered side; no cohort pair has a
               provider FX value; no code with a provider value is covered (A4.6B
               codes such as CUP, IRR, MMK, SYP, TMT, VES stay outside)
  pair pages   data-mode="live_fiat"; no FX rate state, converter, rate runtime, table
               rows, A3 "no reference rate" wording or ordinary market boilerplate;
               title/og/twitter/WebPage equal the resolver and carry no converter / FX
               wording; WebPage + BreadcrumbList + FAQPage only (no WebApplication);
               visible FAQ == FAQPage JSON-LD; banner availability, rate regime and
               value type equal the governed state; every claim is registry-cited; no
               rate figure while no value is activated; an activated value shows its
               source, regime, valuation date and DIRECT / DERIVED labelling; covered
               hubs (and a transitional code's operative-code hub) linked; robots follow
               policy and sitemap membership agrees; single self-canonical; page equals
               the generator output (idempotent rewrite)
  hubs         index,follow, self-canonical, in sitemap, "Reference" title (never
               "Currency Pairs" or "Converter"), WebPage + FAQPage with FAQ parity, no
               WebApplication, identity claims, availability, rate regime, provenance
               and limitations shown, all pair links kept, generator output
  snapshot     live_fiat_reference.validate_live_fiat_snapshot passes

Run: python3 scripts/validate_live_fiat_coverage.py
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
import validate_historical_instruments as vh  # noqa: E402

LD_RE = re.compile(r'(?s)<script type="application/ld\+json">\n(.*?)\n</script>')
VIS_RE = re.compile(r'(?s)<div class="faq-q"[^>]*>(.*?)</div>\s*<div class="faq-a">(.*?)</div>')
HUB_FAQ_RE = re.compile(r'<div class="hub-faq"><h3>([^<]*)</h3><p>([^<]*)</p></div>')
CLAIM_RE = re.compile(r"<span data-claim>([^<]*)</span>")
VALUE_RE = re.compile(r'<span data-value-type="([a-z_]+)">([^<]*)</span>')
LOC_RE = re.compile(r"<loc>https://convertccy\.com/([^<]*)</loc>")
ROOT_RE = re.compile(r'<div class="rate-banner" id="rate-root"[^>]*>')
RATE_FIGURE_RE = re.compile(r"=\s*\d|\b\d+(?:[.,]\d+)*\s+[A-Z]{3}\b|\b\d+(?:[.,]\d+)*\s*(?i:won|bol[ií]var)")
RATE_QUESTION_RE = re.compile(r"How much is 1 [A-Z]{3} in [A-Z]{3}\?")
FORBIDDEN = ('data-rate=', '>LIVE', 'SNAPSHOT ·', 'Reference snapshot as of', 'id="from-input"', 'data-amount=',
             g.RATE_SCRIPT_SRC, "Live reference value", "shows the latest available reference exchange rate",
             "No reference rate available", "No current reference rate is available", ">Currency Converter<",
             ">NO RATE<", 'data-mode="unsupported"', "Reference rate vs bank rate", "What moves currencies",
             "What an exchange rate means")
CONVERTER_WORDS = ("Converter", "Convert ", "currency converter", "foreign exchange rate", "bank exchange rate",
                   "live currency exchange", "conversion table", "Currency Pairs")


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
    return None


def check_pair(page, profile, currencies, content, fx, sitemap_locs):
    errs = []
    tokens = g.make_pair_tokens(profile, currencies)
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    rel = f'pages/{profile["pair_slug"]}.html'
    if 'data-mode="live_fiat"' not in page:
        return ["not in live_fiat mode"], None
    for f in FORBIDDEN:
        if f in page:
            errs.append(f"forbidden marker {f!r}")
    brand = content.get("site_copy", {}).get("brand_name", g.SITE_NAME)
    md = g.live_fiat_pair_metadata(tokens, brand, fx)
    blocks = []
    for blk in LD_RE.findall(page):
        try:
            blocks.append(json.loads(blk))
        except ValueError:
            errs.append("malformed JSON-LD")
    if '"WebApplication"' in page:
        errs.append("WebApplication node present")
    graph_types = [n.get("@type") for x in blocks for n in x.get("@graph", [])]
    top_types = sorted(x.get("@type") for x in blocks if x.get("@type"))
    if graph_types != ["WebPage"] or top_types != ["BreadcrumbList", "FAQPage"]:
        errs.append(f"structured data must be WebPage + BreadcrumbList + FAQPage, got {graph_types} {top_types}")
    wp = [n for x in blocks for n in x.get("@graph", []) if n.get("@type") == "WebPage"]
    title = html.unescape(re.search(r"<title>([^<]*)</title>", page).group(1))
    if wp:
        for label, val, want in (("title", title, md["title"]), ("og:title", meta(page, "property", "og:title"), md["title"]),
                                 ("twitter:title", meta(page, "name", "twitter:title"), md["title"]),
                                 ("WebPage name", wp[0].get("name"), md["title"]),
                                 ("description", meta(page, "name", "description"), md["description"]),
                                 ("og:description", meta(page, "property", "og:description"), md["description"]),
                                 ("twitter:description", meta(page, "name", "twitter:description"), md["description"]),
                                 ("WebPage description", wp[0].get("description"), md["description"])):
            if val != want:
                errs.append(f"{label} drifts from the live-fiat metadata resolver")
            if val and any(w.lower() in val.lower() for w in CONVERTER_WORDS):
                errs.append(f"{label} uses converter / FX wording: {val!r}")
    faqs = [x for x in blocks if x.get("@type") == "FAQPage"]
    if len(faqs) == 1:
        ld = [(e["name"], e["acceptedAnswer"]["text"]) for e in faqs[0]["mainEntity"]]
        if ld != [(html.unescape(q), html.unescape(a)) for q, a in VIS_RE.findall(page)]:
            errs.append("visible FAQ != FAQPage JSON-LD")
    sentences, headings = vh.ordinary_boilerplate(profile, tokens, content)
    for x in sentences:
        if g.esc(x) in page:
            errs.append(f"ordinary market boilerplate present: {x[:50]!r}")
    for h in headings:
        if f'<div class="sec-title">{g.esc(h)}</div>' in page:
            errs.append(f"ordinary section heading present: {h!r}")
    if f"{F} / {T} Exchange Rate</div>" in page:
        errs.append("overview heading claims an exchange rate")
    robots = meta(page, "name", "robots")
    if robots != g.pair_robots(F, T):
        errs.append(f"robots {robots!r} != policy {g.pair_robots(F, T)!r}")
    if (rel in sitemap_locs) != (robots == g.INDEXABLE_ROBOTS):
        errs.append("sitemap membership disagrees with robots")
    if re.findall(r'<link rel="canonical" href="([^"]+)">', page) != [f"{g.BASE_URL}/{rel}"]:
        errs.append("canonical is not a single self-canonical")
    sides = [g.live_fiat_view(c) for c in (F, T) if g.is_live_fiat(c)]
    root = ROOT_RE.search(page)
    root_s = root.group(0) if root else ""
    want_avail = " ".join(dict.fromkeys(s["availability_status"] for s in sides))
    want_regime = " ".join(dict.fromkeys(s["rate_regime"] for s in sides))
    if f'data-availability="{want_avail}"' not in root_s or f'data-rate-regime="{want_regime}"' not in root_s:
        errs.append("banner availability / rate regime differ from the governed state")
    for s in sides:
        if f'href="{g.currency_hub_href(s["code"])}"' not in page:
            errs.append(f"no link to the {s['code']} hub")
        if f'data-live-fiat-code="{s["code"]}" data-availability="{s["availability_status"]}"' not in page:
            errs.append(f"{s['code']}: coverage block missing or availability wrong")
        if s.get("operative_code") and f'href="{g.currency_hub_href(s["operative_code"])}"' not in page:
            errs.append(f"{s['code']}: operative code {s['operative_code']} not linked")
    cited = {c["text"] for s in sides for k in ("identity_claims", "coverage_claims", "reported_indicators") for c in s[k]}
    for text in CLAIM_RE.findall(page):
        if html.unescape(text) not in cited:
            errs.append(f"uncited claim {text!r}")
    view = g.live_fiat_value(F, T, fx)
    if f'data-value-type="{view["value_type"]}"' not in root_s:
        errs.append(f"banner value type != governed {view['value_type']!r}")
    ov = page.index(g._OVERVIEW_START)
    faq0 = page.index('<div class="sec-title">FAQ</div>')
    surfaces = (vh.region(page, g.STATIC_RATE_START, g.STATIC_RATE_END)
                + vh.region(page, g.STATIC_TABLE_START, g.STATIC_TABLE_END) + page[ov: page.index("\n  </section>", ov)]
                + page[faq0: page.index("</section>", faq0)])
    if view["value_type"] == "unavailable":
        if VALUE_RE.search(surfaces):
            errs.append("value element rendered although no governed value exists")
        attribution_free = re.sub(r'<a href="https?://[^"]*">[^<]*</a>', " ", CLAIM_RE.sub(" ", surfaces))
        stripped = RATE_QUESTION_RE.sub(" ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", attribution_free)))
        m = RATE_FIGURE_RE.search(stripped)
        if m:
            errs.append(f"rate figure {m.group(0)!r} rendered while no governed value is activated")
    else:
        for need in ("Source:", "valuation date:", "rate regime:"):
            if need not in surfaces:
                errs.append(f"numeric value without visible {need!r}")
        if view["derived"] and "DERIVED FROM" not in surfaces:
            errs.append("derived value not labelled DERIVED FROM")
        if view.get("fx_source") and ("FX source:" not in surfaces or "FX timestamp:" not in surfaces):
            errs.append("derived value without FX source and FX timestamp")
    expected = g.replace_static_rate_regions(page, profile, tokens, fx)
    expected = g.apply_live_fiat_semantics(expected, tokens, content, fx)
    if expected != page:
        errs.append("page differs from generator output (run: python3 generate.py --live-fiat-coverage-only)")
    return errs, view["value_type"]


def check_hub(code, currencies, gov, sitemap_locs):
    errs = []
    rel = f"currencies/{code.lower()}.html"
    page = (REPO / rel).read_text(encoding="utf-8")
    lv = g.live_fiat_view(code)
    if page != g.build_currency_hub_page(code, currencies, gov):
        errs.append("hub differs from generator output")
    if meta(page, "name", "robots") != "index,follow" or rel not in sitemap_locs:
        errs.append("hub must be index,follow and listed in the sitemap")
    if re.findall(r'<link rel="canonical" href="([^"]+)">', page) != [f"{g.BASE_URL}/{rel}"]:
        errs.append("hub canonical is not self")
    t = html.unescape(re.search(r"<title>([^<]*)</title>", page).group(1))
    if "Reference" not in t or lv["display_name"] not in t or any(w in t for w in ("Currency Pairs", "Converter")):
        errs.append(f"hub title lacks reference semantics: {t!r}")
    needs = [g.esc(c["text"]) for c in lv["identity_claims"] + lv["coverage_claims"] + lv["reported_indicators"]]
    needs += [g.esc(lv["decision_label"]), f'data-availability="{lv["availability_status"]}"',
              f'data-rate-regime="{lv["rate_regime"]}"', "<h2>Provenance</h2>", "<h2>Current limitations</h2>"]
    if lv.get("operative_code"):
        needs.append(f'href="{g.currency_hub_href(lv["operative_code"])}"')
    for need in needs:
        if need not in page:
            errs.append(f"hub lacks {need[:60]!r}")
    blocks = [json.loads(b) for b in LD_RE.findall(page)]
    types = [x.get("@type") for x in blocks]
    if "WebPage" not in types or "FAQPage" not in types or "WebApplication" in page:
        errs.append(f"hub structured data wrong: {types}")
    faq = next((x for x in blocks if x.get("@type") == "FAQPage"), None)
    if faq and [(e["name"], e["acceptedAnswer"]["text"]) for e in faq["mainEntity"]] != \
            [(html.unescape(q), html.unescape(a)) for q, a in HUB_FAQ_RE.findall(page)]:
        errs.append("hub visible FAQ != FAQPage JSON-LD")
    if "<h2>Convert" in page:
        errs.append("hub headings use converter wording")
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
    failures = []
    snap = lf.load_live_fiat_snapshot()
    snap_errs = lf.validate_live_fiat_snapshot(snap, ip.load_raw(), fx)
    if snap_errs:
        failures.append(("live-fiat snapshot", snap_errs[:5]))
    covered = set(lf.covered_codes(snap))
    leaked = sorted(c for c in covered if c in fx["rates"])
    if leaked:
        failures.append(("scope", [f"codes with a provider value are covered: {leaked}"]))
    sitemap_locs = set(LOC_RE.findall((REPO / "sitemap.xml").read_text(encoding="utf-8")))
    counts = Counter()
    for profile in profiles.values():
        a, b = profile["from_code"], profile["to_code"]
        if a == b:
            continue
        t = g.pair_semantic_treatment(a, b, fx)
        rel = f'pages/{profile["pair_slug"]}.html'
        counts[f"treatment_{t}"] += 1
        involves = a in covered or b in covered
        if involves:
            want = higher_precedence(pol, a, b) or "live_fiat_coverage"
            if t != want:
                failures.append((rel, [f"router precedence: {t} != {want}"]))
            counts[f"involving_governed_by_{t}"] += 1
        elif t == "live_fiat_coverage":
            failures.append((rel, ["live_fiat_coverage treatment without a covered side"]))
        if t != "live_fiat_coverage":
            continue
        if g.static_pair_rate(a, b, fx) is not None:
            failures.append((rel, ["cohort pair has a provider FX value (A4.6B scope)"]))
        for c in covered:
            if c in (a, b):
                counts[f"code_{c}"] += 1
        if a in covered and b in covered:
            counts["both_covered"] += 1
        page = (REPO / rel).read_text(encoding="utf-8")
        errs, vt = check_pair(page, profile, currencies, content, fx, sitemap_locs)
        counts[f"value_{vt}"] += 1
        if errs:
            failures.append((rel, errs))
    for c in sorted(covered):
        errs = check_hub(c, currencies, gov, sitemap_locs)
        if errs:
            failures.append((f"hub {c}", errs))
        counts["live_fiat_hubs"] += 1
    print("live-fiat coverage: " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if failures:
        print(f"FAIL: {len(failures)}")
        for name, errs in failures[:25]:
            print(f"  - {name}: {errs[:3]}")
        return 1
    print("PASS: live-fiat coverage pair pages, hubs and snapshot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
