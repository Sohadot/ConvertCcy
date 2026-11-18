#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_institutional_units.py — SEO-A4.5 gate for institutional-unit pair pages and hubs.

Cohort comes from the policy router (generate.pair_semantic_treatment ==
"institutional_unit"), never from a code list. Fails closed unless:

  classification  every unit_of_account / regional_unit / special_instrument code has a
                  registry-cited institutional_units_reference entry (instrument_policy);
                  converter valuation_only; a pair with an institutional side is
                  institutional_unit unless standards / historical / precious-metal govern
  pair pages      data-mode="institutional"; no FX rate state, converter, rate runtime,
                  table rows, A3 "no reference rate" wording or ordinary market
                  boilerplate; title/og/twitter/WebPage equal the resolver and carry no
                  converter / FX wording; no WebApplication; FAQ visible == FAQPage
                  JSON-LD; the pair role and banner value type equal the governed state;
                  every claim is registry-cited; no figure outside cited claims while no
                  value is activated; an activated value shows issuer, valuation date,
                  methodology and DIRECT / DERIVED labelling (with FX source and date when
                  derived); an unresolved-status unit is never called active; hub linked;
                  robots follow policy and sitemap membership agrees; single
                  self-canonical; generator output (idempotent rewrite)
  hubs            index,follow, self-canonical, in sitemap, institution-aware "Reference"
                  title (never "Currency Pairs"), WebPage + FAQPage with FAQ parity, no
                  WebApplication, ISO designation, issuer, status, decision label and
                  source governance shown, all pair links kept, generator output
  snapshot        institutional_reference.validate_institutional_snapshot passes

Run: python3 scripts/validate_institutional_units.py
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
import institutional_reference as ir  # noqa: E402
import instrument_policy as ip  # noqa: E402
import validate_historical_instruments as vh  # noqa: E402

LD_RE = re.compile(r'(?s)<script type="application/ld\+json">\n(.*?)\n</script>')
VIS_RE = re.compile(r'(?s)<div class="faq-q"[^>]*>(.*?)</div>\s*<div class="faq-a">(.*?)</div>')
HUB_FAQ_RE = re.compile(r'<div class="hub-faq"><h3>([^<]*)</h3><p>([^<]*)</p></div>')
CLAIM_RE = re.compile(r"<span data-claim>([^<]*)</span>")
VALUE_RE = re.compile(r'<span data-value-type="([a-z_]+)">([^<]*)</span>')
LOC_RE = re.compile(r"<loc>https://convertccy\.com/([^<]*)</loc>")
ROLE_RE = re.compile(r'id="rate-root"[^>]*data-pair-role="([a-z_]+)"')
FORBIDDEN = ('data-rate=', '>LIVE', 'SNAPSHOT ·', 'Reference snapshot as of', 'id="from-input"', 'data-amount=',
             g.RATE_SCRIPT_SRC, "Live reference value", "shows the latest available reference exchange rate",
             "No reference rate available", "No current reference rate is available", ">Currency Converter<",
             "Reference rate vs bank rate", "What moves currencies", "What an exchange rate means")
CONVERTER_WORDS = ("Converter", "Convert ", "currency converter", "foreign exchange rate", "bank exchange rate",
                   "live currency exchange", "conversion table", "Currency Pairs")
EXPECTED_TYPES = {"XDR": "special_instrument", "CLF": "unit_of_account", "UYW": "unit_of_account",
                  "XUA": "regional_unit", "XSU": "regional_unit"}


def meta(page, attr, name):
    m = re.search(rf'<meta {attr}="{re.escape(name)}" content="([^"]*)">', page)
    return html.unescape(m.group(1)) if m else None


def cited_texts(sides):
    out = set()
    for s in sides:
        out.add(s["iso_designation"]["text"])
        for k in ("claims", "activity_claims", "reported_indicators", "licensing_claims"):
            out |= {c["text"] for c in s[k]}
    return out


def expected_treatment(pol, a, b):
    beh = pol.resolve_pair(a, b)["converter_behavior"]
    if beh == "none":
        return "standards_special"
    if beh == "archival_only":
        return "historical"
    if pol.is_precious_metal(a) or pol.is_precious_metal(b):
        return "precious_metal"
    return "institutional_unit"


def check_pair(page, profile, currencies, content, fx, pol, sitemap_locs):
    errs = []
    tokens = g.make_pair_tokens(profile, currencies)
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    rel = f'pages/{profile["pair_slug"]}.html'
    if 'data-mode="institutional"' not in page:
        return ["not in institutional mode"], None, None
    for f in FORBIDDEN:
        if f in page:
            errs.append(f"forbidden marker {f!r}")
    brand = content.get("site_copy", {}).get("brand_name", g.SITE_NAME)
    md = g.institutional_pair_metadata(tokens, brand, fx)
    blocks = []
    for blk in LD_RE.findall(page):
        try:
            blocks.append(json.loads(blk))
        except ValueError:
            errs.append("malformed JSON-LD")
    if any(n.get("@type") == "WebApplication" for x in blocks for n in x.get("@graph", [])) or '"WebApplication"' in page:
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
                errs.append(f"{label} drifts from the institutional metadata resolver")
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
    sides = [pol.institutional_view(c) for c in (F, T) if pol.is_institutional_unit(c)]
    for s in sides:
        if f'href="{g.currency_hub_href(s["code"])}"' not in page:
            errs.append(f"no link to the {s['code']} hub")
        if s["activity_status"] == "status_unresolved":
            if f'data-activity-status="status_unresolved"' not in page:
                errs.append(f"{s['code']}: unresolved status not shown")
            if re.search(rf"{s['code']}[^.<]{{0,40}}\b(is|remains) (an )?active\b", page):
                errs.append(f"{s['code']}: page asserts activity although status is unresolved")
    role = ROLE_RE.search(page)
    if not role or role.group(1) != g.institutional_pair_role(F, T):
        errs.append(f"pair role {role.group(1) if role else None!r} != governed {g.institutional_pair_role(F, T)!r}")
    cited = cited_texts(sides)
    for text in CLAIM_RE.findall(page):
        if html.unescape(text) not in cited:
            errs.append(f"uncited claim {text!r}")
    view = g.institutional_value(F, T, fx)
    vt = re.search(r'id="rate-root"[^>]*data-value-type="([a-z_]+)"', page)
    if not vt or vt.group(1) != view["value_type"]:
        errs.append(f"banner value type {vt.group(1) if vt else None!r} != governed {view['value_type']!r}")
    ov = page.index(g._OVERVIEW_START)
    surfaces = (vh.region(page, g.STATIC_RATE_START, g.STATIC_RATE_END)
                + vh.region(page, g.STATIC_TABLE_START, g.STATIC_TABLE_END) + page[ov: page.index("\n  </section>", ov)])
    if view["value_type"] == "unavailable":
        if VALUE_RE.search(surfaces):
            errs.append("value element rendered although no governed value exists")
        attribution_free = re.sub(r'<a href="https?://[^"]*">[^<]*</a>', " ", CLAIM_RE.sub(" ", surfaces))
        stripped = html.unescape(re.sub(r"(?s)<[^>]+>", " ", attribution_free)).replace("ISO 4217", "ISO")
        if re.search(r"\d", stripped):
            errs.append("figure outside a cited claim while no institutional value is activated")
    else:
        for need in ("Issuer source:", "valuation date:", "methodology:"):
            if need not in surfaces:
                errs.append(f"numeric institutional value without visible {need!r}")
        if view["derived"]:
            if "DERIVED FROM" not in surfaces or ">DERIVED" not in surfaces:
                errs.append("derived value not labelled DERIVED FROM ... VALUATION")
            if view.get("fx_source") and ("FX source:" not in surfaces or "FX timestamp:" not in surfaces):
                errs.append("derived value without FX source and FX timestamp")
        elif "Direct issuer value" not in surfaces:
            errs.append("direct issuer value not labelled direct")
    expected = g.replace_static_rate_regions(page, profile, tokens, fx)
    expected = g.apply_institutional_semantics(expected, tokens, content, fx)
    if expected != page:
        errs.append("page differs from generator output (run: python3 generate.py --institutional-units-only)")
    return errs, view["value_type"], role.group(1) if role else None


def check_hub(code, currencies, gov, pol, sitemap_locs):
    errs = []
    rel = f"currencies/{code.lower()}.html"
    page = (REPO / rel).read_text(encoding="utf-8")
    iv = pol.institutional_view(code)
    if page != g.build_currency_hub_page(code, currencies, gov):
        errs.append("hub differs from generator output")
    if meta(page, "name", "robots") != "index,follow" or rel not in sitemap_locs:
        errs.append("hub must be index,follow and listed in the sitemap")
    if re.findall(r'<link rel="canonical" href="([^"]+)">', page) != [f"{g.BASE_URL}/{rel}"]:
        errs.append("hub canonical is not self")
    t = html.unescape(re.search(r"<title>([^<]*)</title>", page).group(1))
    if "Reference" not in t or iv["display_name"] not in t or any(w in t for w in ("Currency Pairs", "Converter")):
        errs.append(f"hub title lacks institutional reference semantics: {t!r}")
    for need in (iv["iso_designation"]["text"], g.esc(iv["decision_label"]), "Source governance",
                 f'data-activity-status="{iv["activity_status"]}"', g.esc(iv["issuer_display"] or "unresolved")):
        if need not in page:
            errs.append(f"hub lacks {need!r}")
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
    units = sorted(c for c in currencies if pol.is_institutional_unit(c))
    if {c: pol.resolve(c)["instrument_type"] for c in units} != EXPECTED_TYPES:
        failures.append(("classification", [f"institutional codes are {units}"]))
    for c in units:
        r = pol.resolve(c)
        if r["converter_behavior"] != "valuation_only" or r["hub_indexability"] != "index_with_specialized_reference_role":
            failures.append((c, [f"policy mismatch {r['converter_behavior']}, {r['hub_indexability']}"]))
    snap_errs = ir.validate_institutional_snapshot(ir.load_institutional_snapshot(), ip.load_raw())
    if snap_errs:
        failures.append(("institutional snapshot", snap_errs[:5]))
    sitemap_locs = set(LOC_RE.findall((REPO / "sitemap.xml").read_text(encoding="utf-8")))
    counts = Counter()
    for profile in profiles.values():
        a, b = profile["from_code"], profile["to_code"]
        if a == b:
            continue
        t = g.pair_semantic_treatment(a, b, fx)
        involves = a in units or b in units
        rel = f'pages/{profile["pair_slug"]}.html'
        if involves:
            counts["institutional_involving"] += 1
            want = expected_treatment(pol, a, b)
            if t != want:
                failures.append((rel, [f"router precedence: {t} != {want}"]))
            counts[f"governed_by_{t}"] += 1
            for c in (a, b):
                if c in units:
                    counts[f"code_{c}"] += 1
        elif t == "institutional_unit":
            failures.append((rel, ["institutional_unit treatment without an institutional side"]))
        if t != "institutional_unit":
            continue
        page = (REPO / rel).read_text(encoding="utf-8")
        errs, vt, role = check_pair(page, profile, currencies, content, fx, pol, sitemap_locs)
        counts[f"value_{vt}"] += 1
        counts[f"role_{role}"] += 1
        if errs:
            failures.append((rel, errs))
    for c in units:
        errs = check_hub(c, currencies, gov, pol, sitemap_locs)
        if errs:
            failures.append((f"hub {c}", errs))
        counts["institutional_hubs"] += 1
    print("institutional units: " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if failures:
        print(f"FAIL: {len(failures)}")
        for name, errs in failures[:25]:
            print(f"  - {name}: {errs[:3]}")
        return 1
    print("PASS: institutional-unit pair pages, hubs and snapshot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
