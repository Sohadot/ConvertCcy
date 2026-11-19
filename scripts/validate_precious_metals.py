#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_precious_metals.py — SEO-A4.4 gate for precious-metal pair pages and hubs.

Cohort comes from the policy router (generate.pair_semantic_treatment ==
"precious_metal"), never from a code list. Fails closed unless:

  classification  XAU, XAG, XPT, XPD resolve as precious_metal with converter
                  valuation_only, page role precious_metal_reference, reference
                  rate expected, specialized hub indexability; every pair with a
                  metal side is precious_metal unless standards / historical govern
  pair pages      data-mode="metal"; no FX rate state, converter, rate runtime, table
                  rows or generic A3 "no reference rate" wording; no converter / FX
                  wording in title, og, twitter or WebPage; metadata equals the
                  resolver; no WebApplication; FAQ visible == FAQPage JSON-LD; no
                  ordinary market boilerplate; the banner value type equals
                  metal_reference.value_view(); any numeric value is labelled and shows
                  sources and timestamps, otherwise no figure appears outside cited
                  claims; unit convention shown; hub linked; robots follow policy and
                  sitemap membership agrees; single self-canonical; generator output
  hubs            index,follow, self-canonical, in sitemap, "ISO 4217 Reference" title
                  ("Price" only when a source is activated), WebPage + FAQPage with FAQ
                  parity, no WebApplication, ISO designation shown, all pair links kept
  snapshot        metal_reference.validate_metal_snapshot passes

Run: python3 scripts/validate_precious_metals.py
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
import metal_reference as mr  # noqa: E402
import validate_historical_instruments as vh  # noqa: E402

LD_RE = re.compile(r'(?s)<script type="application/ld\+json">\n(.*?)\n</script>')
VIS_RE = re.compile(r'(?s)<div class="faq-q"[^>]*>(.*?)</div>\s*<div class="faq-a">(.*?)</div>')
HUB_FAQ_RE = re.compile(r'<div class="hub-faq"><h3>([^<]*)</h3><p>([^<]*)</p></div>')
CLAIM_RE = re.compile(r"<span data-claim>([^<]*)</span>")
VALUE_RE = re.compile(r'<span data-value-type="([a-z_]+)">([^<]*)</span>')
LOC_RE = re.compile(r"<loc>https://convertccy\.com/([^<]*)</loc>")
FORBIDDEN = ('data-rate=', '>LIVE', 'SNAPSHOT ·', 'Reference snapshot as of', 'id="from-input"', 'data-amount=',
             g.RATE_SCRIPT_SRC, "Live reference value", "shows the latest available reference exchange rate",
             "No reference rate available", "No current reference rate is available", ">Currency Converter<")
CONVERTER_WORDS = ("Converter", "Convert ", "currency converter", "foreign exchange rate", "bank exchange rate",
                   "live currency exchange", "conversion table")


def meta(page, attr, name):
    m = re.search(rf'<meta {attr}="{re.escape(name)}" content="([^"]*)">', page)
    return html.unescape(m.group(1)) if m else None


def cited_texts(sides):
    out = set()
    for m in sides:
        out.add(m["iso_designation"]["text"])
        out.add(m["troy_ounce_definition"]["text"])
        out |= {c["text"] for c in m["claims"]} | {c["text"] for c in m["licensing_claims"]}
    return out


def check_pair(page, profile, currencies, content, fx, pol, sitemap_locs):
    errs = []
    tokens = g.make_pair_tokens(profile, currencies)
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    rel = f'pages/{profile["pair_slug"]}.html'
    if 'data-mode="metal"' not in page:
        return ["not in metal mode"], None
    for f in FORBIDDEN:
        if f in page:
            errs.append(f"forbidden marker {f!r}")
    brand = content.get("site_copy", {}).get("brand_name", g.SITE_NAME)
    md = g.metal_pair_metadata(tokens, brand, fx)
    blocks = []
    for blk in LD_RE.findall(page):
        try:
            blocks.append(json.loads(blk))
        except ValueError:
            errs.append("malformed JSON-LD")
    if any(n.get("@type") == "WebApplication" for x in blocks for n in x.get("@graph", [])):
        errs.append("WebApplication node present")
    wp = [n for x in blocks for n in x.get("@graph", []) if n.get("@type") == "WebPage"]
    title = html.unescape(re.search(r"<title>([^<]*)</title>", page).group(1))
    if len(wp) != 1:
        errs.append("expected exactly one WebPage node")
    else:
        for label, val, want in (("title", title, md["title"]), ("og:title", meta(page, "property", "og:title"), md["title"]),
                                 ("twitter:title", meta(page, "name", "twitter:title"), md["title"]),
                                 ("WebPage name", wp[0].get("name"), md["title"]),
                                 ("description", meta(page, "name", "description"), md["description"]),
                                 ("og:description", meta(page, "property", "og:description"), md["description"]),
                                 ("twitter:description", meta(page, "name", "twitter:description"), md["description"]),
                                 ("WebPage description", wp[0].get("description"), md["description"])):
            if val != want:
                errs.append(f"{label} drifts from the metal metadata resolver")
            if val and any(w.lower() in val.lower() for w in CONVERTER_WORDS):
                errs.append(f"{label} uses converter / FX wording: {val!r}")
    faqs = [x for x in blocks if x.get("@type") == "FAQPage"]
    if len(faqs) != 1:
        errs.append(f"{len(faqs)} FAQPage blocks")
    else:
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
    sides = [pol.metal_view(c) for c in (F, T) if pol.is_precious_metal(c)]
    for m in sides:
        if f'href="{g.currency_hub_href(m["code"])}"' not in page:
            errs.append(f"no link to the {m['code']} hub")
        if g.esc(m["unit_convention"]) not in page:
            errs.append("unit convention not shown")
    cited = cited_texts(sides)
    for text in CLAIM_RE.findall(page):
        if html.unescape(text) not in cited:
            errs.append(f"uncited claim {text!r}")
    view = g.metal_value(F, T, fx)
    vt = re.search(r'id="rate-root"[^>]*data-value-type="([a-z_]+)"', page)
    if not vt or vt.group(1) != view["value_type"]:
        errs.append(f"banner value type {vt.group(1) if vt else None!r} != governed {view['value_type']!r}")
    ov = page.index(g._OVERVIEW_START)
    surfaces = (vh.region(page, g.STATIC_RATE_START, g.STATIC_RATE_END)
                + vh.region(page, g.STATIC_TABLE_START, g.STATIC_TABLE_END) + page[ov: page.index("\n  </section>", ov)])
    if view["value_type"] == "unavailable":
        if VALUE_RE.search(surfaces):
            errs.append("value element rendered although no governed value exists")
        attribution_free = re.sub(r'<a href="https?://[^"]*">[^<]*</a>', " ", CLAIM_RE.sub(" ", surfaces))  # source names
        stripped = html.unescape(re.sub(r"(?s)<[^>]+>", " ", attribution_free)).replace("ISO 4217", "ISO")
        if re.search(r"\d", stripped):
            errs.append("figure outside a cited claim while no metal value is activated")
    else:
        if "sources:" not in surfaces or "timestamps:" not in surfaces:
            errs.append("numeric metal value without visible sources and timestamps")
        if view["derived"] and ">DERIVED" not in surfaces:
            errs.append("derived value not labelled DERIVED")
    expected = g.replace_static_rate_regions(page, profile, tokens, fx)
    expected = g.apply_metal_semantics(expected, tokens, content, fx)
    if expected != page:
        errs.append("page differs from generator output (run: python3 generate.py --precious-metals-only)")
    return errs, view["value_type"]


def check_hub(code, currencies, gov, pol, sitemap_locs):
    errs = []
    rel = f"currencies/{code.lower()}.html"
    page = (REPO / rel).read_text(encoding="utf-8")
    mv = pol.metal_view(code)
    if page != g.build_currency_hub_page(code, currencies, gov):
        errs.append("hub differs from generator output")
    if meta(page, "name", "robots") != "index,follow" or rel not in sitemap_locs:
        errs.append("hub must be index,follow and listed in the sitemap")
    if re.findall(r'<link rel="canonical" href="([^"]+)">', page) != [f"{g.BASE_URL}/{rel}"]:
        errs.append("hub canonical is not self")
    t = re.search(r"<title>([^<]*)</title>", page).group(1)
    if "ISO 4217 Reference" not in t or "Currency Pairs" in t or "Converter" in t:
        errs.append(f"hub title lacks metal reference semantics: {t!r}")
    if "Price" in t and mv["activation_state"] != "source_activated":
        errs.append("hub title says Price although no source is activated")
    if mv["iso_designation"]["text"] not in page or g.esc(mv["unit_convention"]) not in page:
        errs.append("hub lacks the cited ISO designation or unit semantics")
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
        if o == code:
            continue
        if f'href="{g.pair_href(code, o)}"' not in page or f'href="{g.pair_href(o, code)}"' not in page:
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
    metals = sorted(c for c in currencies if pol.is_precious_metal(c))
    if metals != ["XAG", "XAU", "XPD", "XPT"]:
        failures.append(("classification", [f"precious-metal codes are {metals}"]))
    for c in metals:
        r = pol.resolve(c)
        want = ("valuation_only", "precious_metal_reference", True, "index_with_specialized_reference_role")
        if (r["converter_behavior"], r["page_role"], r["reference_rate_expected"], r["hub_indexability"]) != want:
            failures.append((c, [f"policy mismatch {r['converter_behavior'], r['page_role'], r['reference_rate_expected'], r['hub_indexability']}"]))
    snap_errs = mr.validate_metal_snapshot(mr.load_metal_snapshot(), ip.load_raw())
    if snap_errs:
        failures.append(("metal snapshot", snap_errs[:5]))
    sitemap_locs = set(u[len(g.BASE_URL) + 1:] for u in g.read_sitemap_locs(REPO))   # SEO-A5.1: index + child sitemaps
    counts = Counter()
    for profile in profiles.values():
        a, b = profile["from_code"], profile["to_code"]
        if a == b:
            continue
        t = g.pair_semantic_treatment(a, b, fx)
        involves = a in metals or b in metals
        rel = f'pages/{profile["pair_slug"]}.html'
        if involves:
            counts["metal_involving"] += 1
            beh = pol.resolve_pair(a, b)["converter_behavior"]
            expected_t = "standards_special" if beh == "none" else ("historical" if beh == "archival_only" else "precious_metal")
            if t != expected_t:
                failures.append((rel, [f"router precedence: {t} != {expected_t}"]))
            counts[f"governed_by_{t}"] += 1
        elif t == "precious_metal":
            failures.append((rel, ["precious_metal treatment without a metal side"]))
        if t != "precious_metal":
            continue
        page = (REPO / rel).read_text(encoding="utf-8")
        errs, vt = check_pair(page, profile, currencies, content, fx, pol, sitemap_locs)
        counts[f"value_{vt}"] += 1
        if errs:
            failures.append((rel, errs))
    for c in metals:
        errs = check_hub(c, currencies, gov, pol, sitemap_locs)
        if errs:
            failures.append((f"hub {c}", errs))
        counts["metal_hubs"] += 1
    print("precious metals: " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if failures:
        print(f"FAIL: {len(failures)}")
        for name, errs in failures[:25]:
            print(f"  - {name}: {errs[:3]}")
        return 1
    print("PASS: precious-metal pair pages, hubs and snapshot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
