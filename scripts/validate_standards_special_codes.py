#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_standards_special_codes.py — SEO-A4.3 gate for ISO 4217 test / no-currency
codes (XTS, XXX) and their consolidated pair pages.

Cohort comes from the policy layer (generate.pair_semantic_treatment ==
"standards_special"), never from a code list. Fails closed unless:

  classification  XTS = test_code, XXX = no_currency; the deployed pair policy is
                  noindex_follow_consolidated_reference; hubs stay indexable
  pair pages      data-mode="standards"; no rate, converter, rate runtime, table rows,
                  LIVE/SNAPSHOT state or ordinary-FX FAQ claim; no ordinary market
                  boilerplate or headings; no "Converter" in title / og / twitter /
                  WebPage name; descriptions are not consumer-converter wording; all
                  metadata equals the resolver; no WebApplication; FAQ visible ==
                  FAQPage JSON-LD; robots == "noindex,follow" from policy; exactly one
                  self-canonical; no meta refresh and no _redirects rule; links to the
                  authoritative hub; claim spans are registry-cited; page equals the
                  generator output
  sitemap         no cohort URL in sitemap.xml; no sitemap URL points to a noindex page;
                  both hubs listed
  hubs            index,follow, self-canonical, standards title (no "Currency Pairs"),
                  WebPage + FAQPage JSON-LD (FAQ parity), no WebApplication, every pair
                  link kept, generator output

Run: python3 scripts/validate_standards_special_codes.py
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
import validate_historical_instruments as vh  # noqa: E402

LD_RE = re.compile(r'(?s)<script type="application/ld\+json">\n(.*?)\n</script>')
VIS_RE = re.compile(r'(?s)<div class="faq-q"[^>]*>(.*?)</div>\s*<div class="faq-a">(.*?)</div>')
HUB_FAQ_RE = re.compile(r'<div class="hub-faq"><h3>([^<]*)</h3><p>([^<]*)</p></div>')
CLAIM_RE = re.compile(r"<span data-claim>([^<]*)</span>")
LOC_RE = re.compile(r"<loc>https://convertccy\.com/([^<]*)</loc>")
FORBIDDEN = ('data-rate=', '>LIVE', 'SNAPSHOT ·', 'Reference snapshot as of', 'id="from-input"', 'data-amount=',
             g.RATE_SCRIPT_SRC, "Live reference value", "shows the latest available reference exchange rate",
             'http-equiv="refresh"')
NOINDEX = "noindex,follow"


def meta(page, attr, name):
    m = re.search(rf'<meta {attr}="{re.escape(name)}" content="([^"]*)">', page)
    return html.unescape(m.group(1)) if m else None


def check_pair(page, profile, currencies, content, snap, pol, redirects):
    errs = []
    tokens = g.make_pair_tokens(profile, currencies)
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    rel = f'pages/{profile["pair_slug"]}.html'
    if 'data-mode="standards"' not in page:
        return ["not in standards mode"]
    for f in FORBIDDEN:
        if f in page:
            errs.append(f"forbidden marker {f!r}")
    rp = pol.resolve_pair(F, T)
    if rp["pair_indexability"] != "noindex_follow_consolidated_reference":
        errs.append(f"policy pair_indexability is {rp['pair_indexability']}")
    if meta(page, "name", "robots") != NOINDEX or g.pair_robots(F, T) != NOINDEX:
        errs.append(f"robots {meta(page, 'name', 'robots')!r} != {NOINDEX!r}")
    canon = re.findall(r'<link rel="canonical" href="([^"]+)">', page)
    if canon != [f"{g.BASE_URL}/{rel}"]:
        errs.append(f"canonical {canon!r} is not a single self-canonical")
    if f"/{rel}" in redirects or f"/{rel[:-5]}" in redirects:
        errs.append("redirect rule exists for a consolidated page")
    brand = content.get("site_copy", {}).get("brand_name", g.SITE_NAME)
    md = g.standards_pair_metadata(tokens, brand)
    title = html.unescape(re.search(r"<title>([^<]*)</title>", page).group(1))
    blocks = []
    for blk in LD_RE.findall(page):
        try:
            blocks.append(json.loads(blk))
        except ValueError:
            errs.append("malformed JSON-LD")
    wp = [n for x in blocks for n in x.get("@graph", []) if n.get("@type") == "WebPage"]
    if any(n.get("@type") == "WebApplication" for x in blocks for n in x.get("@graph", [])):
        errs.append("WebApplication node present")
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
                errs.append(f"{label} drifts from the standards metadata resolver")
            if val and ("Converter" in val or val.startswith("Convert ") or "conversion table" in val.lower()):
                errs.append(f"{label} uses converter wording")
    faqs = [x for x in blocks if x.get("@type") == "FAQPage"]
    if len(faqs) != 1:
        errs.append(f"{len(faqs)} FAQPage blocks")
    else:
        ld = [(e["name"], e["acceptedAnswer"]["text"]) for e in faqs[0]["mainEntity"]]
        vis = [(html.unescape(q), html.unescape(a)) for q, a in VIS_RE.findall(page)]
        if ld != vis:
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
    sides = [pol.standards_view(c) for c in (F, T) if pol.is_standards_special(c)]
    cited = {sv["iso_designation"]["text"] for sv in sides} | {c["text"] for sv in sides for c in sv["claims"]}
    for text in CLAIM_RE.findall(page):
        if html.unescape(text) not in cited:
            errs.append(f"uncited claim {text!r}")
    for sv in sides:
        if f'href="{g.currency_hub_href(sv["code"])}"' not in page:
            errs.append(f"no link to the authoritative {sv['code']} hub")
    ov = page.index(g._OVERVIEW_START)
    surfaces = (vh.region(page, g.STATIC_RATE_START, g.STATIC_RATE_END)
                + vh.region(page, g.STATIC_TABLE_START, g.STATIC_TABLE_END) + page[ov: page.index("\n  </section>", ov)])
    stripped = html.unescape(re.sub(r"(?s)<[^>]+>", " ", CLAIM_RE.sub(" ", surfaces))).replace("ISO 4217", "ISO")
    if re.search(r"\d", stripped):
        errs.append("figure outside a cited claim in standards surfaces")
    expected = g.replace_static_rate_regions(page, profile, tokens, snap)
    expected = g.apply_standards_semantics(expected, tokens, content)
    if expected != page:
        errs.append("page differs from generator output (run: python3 generate.py --standards-special-only)")
    return errs


def check_hub(code, currencies, gov, pol, sitemap_locs):
    errs = []
    rel = f"currencies/{code.lower()}.html"
    page = (REPO / rel).read_text(encoding="utf-8")
    if page != g.build_currency_hub_page(code, currencies, gov):
        errs.append("hub differs from generator output")
    if meta(page, "name", "robots") != "index,follow":
        errs.append("hub is not index,follow")
    if re.findall(r'<link rel="canonical" href="([^"]+)">', page) != [f"{g.BASE_URL}/{rel}"]:
        errs.append("hub canonical is not self")
    if rel not in sitemap_locs:
        errs.append("hub missing from sitemap")
    t = re.search(r"<title>([^<]*)</title>", page).group(1)
    if "Currency Pairs" in t or "Converter" in t or "ISO 4217" not in t:
        errs.append(f"hub title lacks standards semantics: {t!r}")
    d = meta(page, "name", "description") or ""
    if f"convert {code.lower()}" in d.lower() or "currencies to" in d.lower():
        errs.append("hub description uses converter wording")
    sv = pol.standards_view(code)
    if sv["iso_designation"]["text"] not in html.unescape(page):
        errs.append("hub lacks the cited ISO 4217 designation")
    blocks = [json.loads(b) for b in LD_RE.findall(page)]
    types = [x.get("@type") for x in blocks]
    if "WebPage" not in types or "FAQPage" not in types or "WebApplication" in page:
        errs.append(f"hub structured data wrong: {types}")
    faq = next((x for x in blocks if x.get("@type") == "FAQPage"), None)
    if faq:
        ld = [(e["name"], e["acceptedAnswer"]["text"]) for e in faq["mainEntity"]]
        vis = [(html.unescape(q), html.unescape(a)) for q, a in HUB_FAQ_RE.findall(page)]
        if ld != vis:
            errs.append("hub visible FAQ != FAQPage JSON-LD")
    others = [c for c in currencies if c != code]
    for o in others:
        for a, b in ((code, o), (o, code)):
            if f'href="{g.pair_href(a, b)}"' not in page:
                errs.append(f"hub lost link to {a}->{b}")
                break
    return errs


def main() -> int:
    snap = g.load_rate_snapshot()
    pol = g.instrument_policy_layer()
    currencies = g.load_currencies()
    content = g.load_content_blocks()
    profiles = g.load_pair_profiles()
    gov = g.load_governed_currency_map()
    failures = []
    for code, want in (("XTS", "test_code"), ("XXX", "no_currency")):
        if pol.resolve(code)["instrument_type"] != want:
            failures.append((code, [f"must be classified {want}"]))
    special_codes = sorted(c for c in currencies if pol.is_standards_special(c))
    for c in special_codes:
        if pol.resolve(c)["hub_indexability"] == "noindex_follow_consolidated_reference":
            failures.append((c, ["hub must stay indexable"]))
    sitemap_text = (REPO / "sitemap.xml").read_text(encoding="utf-8")
    sitemap_locs = set(LOC_RE.findall(sitemap_text))
    redirects = set()
    rp = REPO / "_redirects"
    if rp.exists():
        for line in rp.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                redirects.add(line.split()[0])
    counts = Counter()
    for profile in profiles.values():
        a, b = profile["from_code"], profile["to_code"]
        if a == b:
            continue
        rel = f'pages/{profile["pair_slug"]}.html'
        page = (REPO / rel).read_text(encoding="utf-8")
        t = g.pair_semantic_treatment(a, b, snap)
        robots = meta(page, "name", "robots")
        if rel in sitemap_locs and "noindex" in (robots or ""):
            failures.append((rel, ["sitemap URL points to a noindex page"]))
        involves = a in special_codes or b in special_codes
        if involves != (t == "standards_special"):
            failures.append((rel, [f"cohort mismatch: treatment {t}"]))
        if t != "standards_special":
            if "noindex" in (robots or ""):
                failures.append((rel, ["non-standards pair is noindex"]))
            continue
        counts["pair_pages"] += 1
        for c in (a, b):
            if c in special_codes:
                counts[f"pages_with_{c}"] += 1
        if rel in sitemap_locs:
            failures.append((rel, ["noindex consolidated page listed in sitemap"]))
        errs = check_pair(page, profile, currencies, content, snap, pol, redirects)
        if errs:
            failures.append((rel, errs))
        counts["noindex_follow"] += robots == NOINDEX
    for c in special_codes:
        errs = check_hub(c, currencies, gov, pol, sitemap_locs)
        if errs:
            failures.append((f"hub {c}", errs))
        counts["indexable_hubs"] += 1
    counts["sitemap_urls"] = len(sitemap_locs)
    print("standards cohort: " + " ".join(f"{k}={v}" for k, v in sorted(counts.items()) if v or k == "noindex_follow"))
    if failures:
        print(f"FAIL: {len(failures)}")
        for name, errs in failures[:25]:
            print(f"  - {name}: {errs[:3]}")
        return 1
    print("PASS: ISO 4217 standards-special codes and consolidated pair pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
