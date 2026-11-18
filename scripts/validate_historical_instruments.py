#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_historical_instruments.py — SEO-A4.2 gate for historical / legacy pages.

Cohort comes from the policy layer (instrument_policy.resolve_pair ->
converter_behavior == "archival_only"), never from a code list. For every pair
page in that cohort it fails closed unless:

  - the page is in data-mode="historical" and carries no current-rate state:
    no data-rate, no LIVE / SNAPSHOT badge, no "Reference snapshot as of",
    no converter inputs, no conversion-table rows, no /assets/js/pair-rate.js
  - no ordinary current-FX FAQ claim ("shows the latest available reference
    exchange rate")
  - every rendered figure sits inside a labelled element: data-value-type
    (must equal a VERIFIED fixed conversion from historical_view) or data-claim
    (must equal a registry-cited claim); no other digits in the rate/table regions
  - no snapshot-derived cross rate or inverse for the pair appears anywhere on
    the page (blocks provider aliasing such as ZWL priced as ZWG)
  - all JSON-LD parses; exactly one FAQPage; visible FAQ == FAQPage JSON-LD;
    no WebApplication node
  - rate regions, FAQ regions and WebPage JSON-LD equal the generator output
Non-historical pages must not be in historical mode and keep WebApplication.
Hubs of historical/legacy codes must carry the historical/legacy label.

Run: python3 scripts/validate_historical_instruments.py
"""

from __future__ import annotations

import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import generate as g  # noqa: E402

LD_RE = re.compile(r'(?s)<script type="application/ld\+json">\n(.*?)\n</script>')
VIS_RE = re.compile(r'(?s)<div class="faq-q"[^>]*>(.*?)</div>\s*<div class="faq-a">(.*?)</div>')
VALUE_RE = re.compile(r'<span data-value-type="([a-z_]+)">([^<]*)</span>')
CLAIM_RE = re.compile(r"<span data-claim>([^<]*)</span>")
FALSE_CLAIM = "shows the latest available reference exchange rate"
FORBIDDEN = ('data-rate=', '>LIVE', 'SNAPSHOT ·', 'Reference snapshot as of', 'id="from-input"',
             'data-amount=', g.RATE_SCRIPT_SRC, "Live reference value")


def region(page: str, start: str, end: str) -> str:
    return page[page.index(start): page.index(end) + len(end)]


def check_page(page: str, profile, currencies, content, snap, pol):
    errs = []
    a, b = profile["from_code"], profile["to_code"]
    tokens = g.make_pair_tokens(profile, currencies)
    if 'data-mode="historical"' not in page:
        return ["not in historical mode"]
    for f in FORBIDDEN:
        if f in page:
            errs.append(f"forbidden current-rate marker {f!r}")
    if FALSE_CLAIM in page:
        errs.append("ordinary current-FX FAQ claim present")
    verified = {hv["code"]: hv for hv in (pol.historical_view(c) for c in (a, b) if pol.is_historical(c))}
    statements = {hv["fixed_conversion"]["statement"] for hv in verified.values() if hv["fixed_conversion"]}
    claims = {c["text"] for hv in verified.values() for c in hv["claims"]}
    surfaces = region(page, g.STATIC_RATE_START, g.STATIC_RATE_END) + region(page, g.STATIC_TABLE_START, g.STATIC_TABLE_END)
    for kind, text in VALUE_RE.findall(surfaces):
        if kind not in g.HISTORICAL_VALUE_LABELS or html.unescape(text) not in statements:
            errs.append(f"unverified or unlabelled value {text!r} ({kind})")
    for text in CLAIM_RE.findall(surfaces):
        if html.unescape(text) not in claims:
            errs.append(f"claim not in registry-cited set: {text!r}")
    stripped = CLAIM_RE.sub(" ", VALUE_RE.sub(" ", surfaces))
    stripped = re.sub(r"(?s)<[^>]+>", " ", stripped)
    if re.search(r"\d", html.unescape(stripped)):
        errs.append("unlabelled numeric value in historical rate/table region")
    sr = g.static_pair_rate(a, b, snap)
    if sr is not None:
        # what readers and parsers receive: visible text (tags/attributes, CSS and
        # inline JS removed) plus JSON-LD bodies
        body = re.sub(r"(?is)<(style|script)\b[^>]*>.*?</\1>", " ", page)
        received = html.unescape(re.sub(r"(?s)<[^>]+>", " ", body)) + " " + " ".join(LD_RE.findall(page))
        cited_figures = {n for st in statements for n in re.findall(r"[\d][\d,.]*", st)}
        for v in (sr["rate"], sr["inverse"]):
            s = g.format_rate_value(v, sr["sig"])
            if s in cited_figures:
                continue  # the provider cross equals a verified figure (e.g. SLL/SLE 1,000)
            if re.search(r"(?<![\d.,])" + re.escape(s) + r"(?![\d,]|\.\d)", received):
                errs.append(f"snapshot-derived value {s} rendered on a historical page")
    blocks = []
    for blk in LD_RE.findall(page):
        try:
            blocks.append(json.loads(blk))
        except ValueError:
            errs.append("malformed JSON-LD")
    faqs = [x for x in blocks if x.get("@type") == "FAQPage"]
    if len(faqs) != 1:
        errs.append(f"{len(faqs)} FAQPage blocks")
    else:
        ld = [(e["name"], e["acceptedAnswer"]["text"]) for e in faqs[0]["mainEntity"]]
        vis = [(html.unescape(q), html.unescape(x)) for q, x in VIS_RE.findall(page)]
        if ld != vis:
            errs.append("visible FAQ != FAQPage JSON-LD")
    for x in blocks:
        if any(n.get("@type") == "WebApplication" for n in x.get("@graph", [])):
            errs.append("WebApplication node on an archival page")
    items = g.rate_aware_faq_items(g.build_faq_items(profile, content, tokens), tokens, snap, currencies)
    expected = g.replace_static_rate_regions(page, profile, tokens, snap)
    expected = g.replace_faq_regions(expected, items)
    expected = g.replace_webpage_jsonld(expected, tokens, items, True)
    if expected != page:
        errs.append("historical regions differ from generator output (run: python3 generate.py --historical-instruments-only)")
    return errs


def main() -> int:
    snap = g.load_rate_snapshot()
    pol = g.instrument_policy_layer()
    currencies = g.load_currencies()
    content = g.load_content_blocks()
    profiles = g.load_pair_profiles()
    counts = Counter()
    failures = []
    for profile in profiles.values():
        a, b = profile["from_code"], profile["to_code"]
        if a == b or a not in currencies or b not in currencies:
            continue
        page = (g.PAGES_DIR / f'{profile["pair_slug"]}.html').read_text(encoding="utf-8")
        t = g.pair_rate_treatment(a, b, snap)
        counts[t] += 1
        if t == "historical":
            errs = check_page(page, profile, currencies, content, snap, pol)
            vt = re.search(r'id="rate-root"[^>]*data-value-type="([a-z_]+)"', page)
            counts["historical:" + (vt.group(1) if vt else "?")] += 1
        else:
            errs = []
            if 'data-mode="historical"' in page:
                errs.append("non-historical pair rendered in historical mode")
            if '"@type": "WebApplication"' not in page:
                errs.append("ordinary pair lost its WebApplication node")
        if errs:
            failures.append((profile["pair_slug"], errs))
    gov = g.load_governed_currency_map()
    for code in currencies:
        if pol.is_historical(code):
            hub = (REPO / "currencies" / f"{code.lower()}.html").read_text(encoding="utf-8")
            if hub != g.build_currency_hub_page(code, currencies, gov) or "fiat currency" in hub:
                failures.append((f"hub {code}", ["hub not regenerated with historical/legacy label"]))
            counts["historical_hubs"] += 1
    print("cohort: " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if failures:
        print(f"FAIL: {len(failures)} pages")
        for slug, errs in failures[:25]:
            print(f"  - {slug}: {errs[:3]}")
        return 1
    print("PASS: historical and legacy instrument pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
