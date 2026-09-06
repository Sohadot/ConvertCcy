#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ConvertCCY - Strategic SEO Generator
Builds pair pages, currencies index, trust pages, and sitemap
from:
- data/currencies.json
- data/content_blocks.json
- data/pair_profiles_parts/*.json
"""

from __future__ import annotations

import json
import hashlib
import html
import os
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Tuple, Optional, Set

# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------

BASE_URL = "https://convertccy.com"
SITE_NAME = "ConvertCCY"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PAIR_PARTS_DIR = DATA_DIR / "pair_profiles_parts"
PAGES_DIR = BASE_DIR / "pages"

CURRENCIES_FILE = DATA_DIR / "currencies.json"
CONTENT_FILE = DATA_DIR / "content_blocks.json"
# Governed Passage Check dataset (built by scripts/build_passage_check.py from the
# published, source-mapped rules layer). Used to enrich pair pages with governed
# jurisdiction data. Optional: if absent, pair pages still build (no governed block).
PASSAGE_FILE = BASE_DIR / "rules" / "passage-check.json"

STATIC_CORE_PAGES = [
    "index.html",
    "about.html",
    "contact.html",
    "privacy.html",
    "currencies.html",
    "methodology.html",
    "disclaimer.html",
    "manifesto.html",
    "framework.html",
]

DEFAULT_POPULAR_CODES = [
    "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY",
    "AED", "SAR", "KWD", "QAR", "EGP", "MAD", "INR", "MXN",
    "BRL", "SGD", "HKD", "TRY", "ZAR"
]

# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------

def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)

def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")

def iso_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()

def hash_index(key: str, size: int) -> int:
    if size <= 0:
        return 0
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return int(digest, 16) % size

def choose_by_hash(options: List[str], key: str, fallback: str = "") -> str:
    if not options:
        return fallback
    return options[hash_index(key, len(options))]

def choose_pair_samples(all_codes: List[str], base_code: str, limit: int = 6) -> List[str]:
    out = []
    for code in all_codes:
        if code != base_code:
            out.append(code)
        if len(out) >= limit:
            break
    return out

def replace_tokens(text: str, tokens: Dict[str, str]) -> str:
    for k, v in tokens.items():
        text = text.replace("{" + k + "}", str(v))
    return text

def file_exists(name: str) -> bool:
    return (BASE_DIR / name).exists()

# -----------------------------------------------------------------------------
# LOAD CURRENCIES
# -----------------------------------------------------------------------------

def normalize_currency_entry(raw: Any) -> Dict[str, Any]:
    """
    Supports:
    - {"code":"USD","name":"US Dollar","symbol":"$","flag":"🇺🇸"}
    - {"currency_code":"USD","currency_name":"US Dollar"}
    - ["USD","US Dollar","🇺🇸"]
    """
    if isinstance(raw, dict):
        code = raw.get("code") or raw.get("currency_code") or raw.get("id")
        name = raw.get("name") or raw.get("currency_name") or raw.get("title") or code
        symbol = raw.get("symbol", "")
        flag = raw.get("flag", "")
        country = raw.get("country", "")
        return {
            "code": str(code).upper(),
            "name": str(name),
            "symbol": str(symbol),
            "flag": str(flag),
            "country": str(country),
        }

    if isinstance(raw, list) and len(raw) >= 2:
        code = str(raw[0]).upper()
        name = str(raw[1])
        flag = str(raw[2]) if len(raw) > 2 else ""
        return {
            "code": code,
            "name": name,
            "symbol": "",
            "flag": flag,
            "country": "",
        }

    raise ValueError(f"Unsupported currency format: {raw!r}")

def load_currencies() -> Dict[str, Dict[str, Any]]:
    data = load_json(CURRENCIES_FILE)

    if isinstance(data, dict) and "currencies" in data:
        raw_items = data["currencies"]

        # حالة currencies كـ dict
        if isinstance(raw_items, dict):
            currencies = {}
            for code, raw in raw_items.items():
                if not isinstance(raw, dict):
                    continue

                currencies[str(code).upper()] = {
                    "code": str(raw.get("code", code)).upper(),
                    "name": str(
                        raw.get("display_name")
                        or raw.get("iso_name")
                        or raw.get("name")
                        or code
                    ),
                    "symbol": str(raw.get("symbol", "")),
                    "flag": str(raw.get("flag", "")),
                    "country": str(raw.get("country", "")),
                    "slug": str(raw.get("slug", slugify(str(code)))),
                    "aliases": raw.get("aliases", []),
                    "instrument_type": str(raw.get("instrument_type", "")),
                    "visibility_tier": str(raw.get("visibility_tier", "")),
                    "is_regional": bool(raw.get("is_regional", False)),
                    "is_special_unit": bool(raw.get("is_special_unit", False)),
                    "short_description": str(raw.get("short_description", "")),
                }
            return currencies

        # حالة currencies كـ list
        elif isinstance(raw_items, list):
            currencies = {}
            for item in raw_items:
                c = normalize_currency_entry(item)
                if c["code"]:
                    currencies[c["code"]] = c
            return currencies

    elif isinstance(data, list):
        currencies = {}
        for item in data:
            c = normalize_currency_entry(item)
            if c["code"]:
                currencies[c["code"]] = c
        return currencies

    raise ValueError("currencies.json format is not supported")

    return currencies

# -----------------------------------------------------------------------------
# LOAD CONTENT BLOCKS
# -----------------------------------------------------------------------------

def load_content_blocks() -> Dict[str, Any]:
    return load_json(CONTENT_FILE)

# -----------------------------------------------------------------------------
# LOAD PAIR PROFILES
# -----------------------------------------------------------------------------

def infer_pair_fields(pair_key: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Supports many shapes:
    - key: USD_EUR
    - key: usd-to-eur
    - dict already has from_code / to_code
    """
    profile = dict(raw)

    from_code = profile.get("from_code")
    to_code = profile.get("to_code")

    if not from_code or not to_code:
        key = pair_key.strip()

        if "_" in key:
            parts = key.split("_", 1)
            from_code, to_code = parts[0], parts[1]
        elif "-to-" in key:
            parts = key.split("-to-", 1)
            from_code, to_code = parts[0], parts[1]

    if not from_code or not to_code:
        raise ValueError(f"Could not infer pair codes for profile key: {pair_key}")

    from_code = str(from_code).upper()
    to_code = str(to_code).upper()

    slug = profile.get("pair_slug") or f"{from_code.lower()}-to-{to_code.lower()}"

    category_flags = []
    for field in ("categories", "tags", "flags"):
        v = profile.get(field)
        if isinstance(v, list):
            category_flags.extend([str(x) for x in v])

    if profile.get("is_major_major"):
        category_flags.append("major_major")
    if profile.get("is_remittance"):
        category_flags.append("remittance")
    if profile.get("is_commodity_sensitive"):
        category_flags.append("commodity_sensitive")
    if profile.get("is_safe_haven_linked"):
        category_flags.append("safe_haven_linked")

    profile["from_code"] = from_code
    profile["to_code"] = to_code
    profile["pair_slug"] = slug
    profile["pair_key"] = f"{from_code}_{to_code}"
    profile["category_flags"] = list(dict.fromkeys(category_flags))
    return profile

def load_pair_profiles() -> Dict[str, Dict[str, Any]]:
    if not PAIR_PARTS_DIR.exists():
        raise FileNotFoundError(f"Missing folder: {PAIR_PARTS_DIR}")

    merged: Dict[str, Dict[str, Any]] = {}

    json_files = sorted(PAIR_PARTS_DIR.glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"No JSON files found in {PAIR_PARTS_DIR}")

    for file_path in json_files:
        data = load_json(file_path)

        if isinstance(data, dict) and "pair_profiles" in data:
            raw_profiles = data["pair_profiles"]
        elif isinstance(data, dict):
            raw_profiles = data
        else:
            raise ValueError(f"Unsupported pair profile structure in {file_path.name}")

        for k, v in raw_profiles.items():
            if not isinstance(v, dict):
                continue
            profile = infer_pair_fields(k, v)
            merged[profile["pair_key"]] = profile

    return merged

# -----------------------------------------------------------------------------
# PAGE CONTENT ENGINE
# -----------------------------------------------------------------------------

def make_pair_tokens(profile: Dict[str, Any], currencies: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    from_code = profile["from_code"]
    to_code = profile["to_code"]

    from_cur = currencies.get(from_code, {"name": from_code, "flag": ""})
    to_cur = currencies.get(to_code, {"name": to_code, "flag": ""})

    return {
        "FROM_CODE": from_code,
        "TO_CODE": to_code,
        "FROM_NAME": from_cur.get("name", from_code),
        "TO_NAME": to_cur.get("name", to_code),
        "FROM_FLAG": from_cur.get("flag", ""),
        "TO_FLAG": to_cur.get("flag", ""),
        "PAIR_SLUG": profile["pair_slug"],
    }

def build_pair_intro(profile: Dict[str, Any], content: Dict[str, Any], tokens: Dict[str, str]) -> str:
    templates = content.get("pair_page_templates", {}).get("intro_templates", [])
    chosen = choose_by_hash(templates, profile["pair_key"], fallback="The exchange rate between these two currencies helps users compare relative value across markets.")
    return replace_tokens(chosen, tokens)

def build_from_currency_para(profile: Dict[str, Any], content: Dict[str, Any], tokens: Dict[str, str]) -> str:
    templates = content.get("pair_page_templates", {}).get("from_currency_templates", [])
    chosen = choose_by_hash(templates, profile["pair_key"] + "_from", fallback=f'{tokens["FROM_NAME"]} is part of its own monetary and economic environment.')
    return replace_tokens(chosen, tokens)

def build_to_currency_para(profile: Dict[str, Any], content: Dict[str, Any], tokens: Dict[str, str]) -> str:
    templates = content.get("pair_page_templates", {}).get("to_currency_templates", [])
    chosen = choose_by_hash(templates, profile["pair_key"] + "_to", fallback=f'{tokens["TO_NAME"]} responds to its own regional and monetary conditions.')
    return replace_tokens(chosen, tokens)

def build_relationship_para(profile: Dict[str, Any], content: Dict[str, Any], tokens: Dict[str, str]) -> str:
    templates = content.get("pair_page_templates", {}).get("relationship_templates", [])
    chosen = choose_by_hash(templates, profile["pair_key"] + "_rel", fallback="This currency pair can be useful for both practical conversion and broader exchange-rate understanding.")
    return replace_tokens(chosen, tokens)

def build_driver_intro(profile: Dict[str, Any], content: Dict[str, Any]) -> str:
    templates = content.get("pair_page_templates", {}).get("driver_intro_templates", [])
    return choose_by_hash(templates, profile["pair_key"] + "_drv", fallback="Several economic factors can influence this rate over time.")

def build_table_intro(profile: Dict[str, Any], content: Dict[str, Any]) -> str:
    templates = content.get("pair_page_templates", {}).get("table_intro_templates", [])
    return choose_by_hash(templates, profile["pair_key"] + "_tbl", fallback="The table below provides quick sample conversions.")

def build_faq_items(profile: Dict[str, Any], content: Dict[str, Any], tokens: Dict[str, str]) -> List[Dict[str, str]]:
    faq_items = []

    defaults = content.get("faq_defaults", [])
    for item in defaults:
        q = replace_tokens(item.get("q", ""), tokens)
        a = replace_tokens(item.get("a", ""), tokens)
        if q and a:
            faq_items.append({"q": q, "a": a})

    extra_map = content.get("faq_extras", {})
    for flag in profile.get("category_flags", []):
        extra_items = extra_map.get(flag, [])
        for item in extra_items:
            q = replace_tokens(item.get("q", ""), tokens)
            a = replace_tokens(item.get("a", ""), tokens)
            if q and a:
                faq_items.append({"q": q, "a": a})

    # limit to keep pages clean
    return faq_items[:6]

def faq_jsonld(faq_items: List[Dict[str, str]]) -> str:
    entities = []
    for item in faq_items:
        entities.append({
            "@type": "Question",
            "name": item["q"],
            "acceptedAnswer": {
                "@type": "Answer",
                "text": item["a"]
            }
        })
    return json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": entities
    }, ensure_ascii=False, indent=2)

def pair_breadcrumb_jsonld(tokens: Dict[str, str]) -> str:
    return json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{BASE_URL}/"},
            {"@type": "ListItem", "position": 2, "name": "Currencies", "item": f"{BASE_URL}/currencies.html"},
            {"@type": "ListItem", "position": 3, "name": f'{tokens["FROM_CODE"]} to {tokens["TO_CODE"]}', "item": f'{BASE_URL}/pages/{tokens["PAIR_SLUG"]}.html'}
        ]
    }, ensure_ascii=False, indent=2)

def pair_webpage_jsonld(tokens: Dict[str, str], faq_items: List[Dict[str, str]]) -> str:
    graph = [
        {
            "@type": "WebPage",
            "name": f'{tokens["FROM_CODE"]} to {tokens["TO_CODE"]} Converter | {SITE_NAME}',
            "url": f'{BASE_URL}/pages/{tokens["PAIR_SLUG"]}.html',
            "description": f'Convert {tokens["FROM_NAME"]} to {tokens["TO_NAME"]} using a clear reference exchange-rate page.'
        },
        {
            "@type": "WebApplication",
            "name": f'{tokens["FROM_CODE"]} to {tokens["TO_CODE"]} Currency Converter',
            "applicationCategory": "FinanceApplication",
            "operatingSystem": "Web",
            "url": f'{BASE_URL}/pages/{tokens["PAIR_SLUG"]}.html'
        }
    ]
    return json.dumps({
        "@context": "https://schema.org",
        "@graph": graph
    }, ensure_ascii=False, indent=2)

def related_pairs_html(from_code: str, to_code: str, all_codes: List[str], limit: int = 8) -> str:
    related = []
    related.append((to_code, from_code))

    for code in all_codes:
        if code not in {from_code, to_code}:
            related.append((from_code, code))
        if len(related) >= limit:
            break

    cards = []
    for a, b in related[:limit]:
        href = f"/pages/{a.lower()}-to-{b.lower()}.html"
        cards.append(
            f'<a class="related-card" href="{href}"><span>{esc(a)} → {esc(b)}</span><small>→</small></a>'
        )
    return "\n".join(cards)

# -----------------------------------------------------------------------------
# HTML TEMPLATES
# -----------------------------------------------------------------------------

def load_governed_currency_map() -> Dict[str, List[Dict[str, Any]]]:
    """Map currency_code -> list of governed jurisdiction records, transcribed from
    the published Passage Check dataset (rules/passage-check.json). A currency may
    map to more than one published country (e.g. EUR -> France, Germany).

    Returns {} if the dataset is absent so the pair build never breaks. Every value
    here is evidence-bound: it originates in a source-mapped published rules entry,
    and each rendered block links back to that entry.
    """
    if not PASSAGE_FILE.exists():
        return {}
    try:
        data = load_json(PASSAGE_FILE)
    except Exception:
        return {}
    gov: Dict[str, List[Dict[str, Any]]] = {}
    for c in data.get("countries", []):
        code = str(c.get("currency_code", "")).upper()
        if not code:
            continue
        thresholds = c.get("declaration", {}).get("thresholds", [])
        gov.setdefault(code, []).append({
            "country_name": c.get("country_name", ""),
            "country_slug": c.get("country_slug", ""),
            "rules_page": c.get("rules_page", ""),
            "last_reviewed": c.get("last_reviewed", ""),
            "exch_label": c.get("exchange_controls", {}).get("label", ""),
            "thresholds": [
                f'{t.get("currency","")} {int(t.get("value",0)):,}'.strip()
                for t in thresholds if t.get("value")
            ],
        })
    return gov


def build_currency_passage_section(profile: Dict[str, Any],
                                   currencies: Dict[str, Dict[str, Any]],
                                   tokens: Dict[str, str],
                                   gov_map: Dict[str, List[Dict[str, Any]]]) -> str:
    """Per-pair, evidence-bound enrichment. For each of the two currencies it shows
    either a governed jurisdiction block (declaration threshold, exchange-control
    posture, links to the source-mapped rules page + ontology + Passage Check) when
    the currency's country is published in the sovereign layer, or an honest factual
    identity block otherwise. This is the R1 mitigation: unique, governed, internally
    linked intelligence that no template clone carries — never fabricated.
    """
    from_code = profile["from_code"]
    to_code = profile["to_code"]

    def currency_block(code: str) -> str:
        cur = currencies.get(code, {})
        name = cur.get("name", code)
        govs = gov_map.get(code, [])
        if govs:
            # Governed: render transcribed thresholds + posture + source links.
            links = " · ".join(
                f'<a href="{esc(g["rules_page"])}">{esc(g["country_name"])} rules →</a>'
                for g in govs if g.get("rules_page")
            )
            thresh_bits = []
            for g in govs:
                if g.get("thresholds"):
                    thresh_bits.append(
                        f'<strong>{esc(g["country_name"])}:</strong> declaration at '
                        + esc(" / ".join(g["thresholds"]))
                        + (f' · <span class="pj-muted">{esc(g["exch_label"])}</span>' if g.get("exch_label") else "")
                    )
            thresh_html = "".join(f'<div class="pj-line">{b}</div>' for b in thresh_bits)
            return f"""
        <div class="pj-block pj-gov">
          <div class="pj-head"><span class="pj-badge">Governed</span> {esc(code)} — {esc(name)}</div>
          {thresh_html}
          <div class="pj-links">{links}</div>
          <div class="pj-cls"><a href="/ontology/declaration-regimes.html">Declaration Regimes</a> · <a href="/ontology/exchange-controls.html">Exchange Controls</a></div>
        </div>"""
        # Not governed: honest, factual identity only. No jurisdictional claims.
        symbol = cur.get("symbol", "")
        ident_bits = []
        if symbol and symbol.upper() != code.upper():
            ident_bits.append(f'symbol {esc(symbol)}')
        ident_bits.append(f'ISO 4217 code {esc(code)}')
        ident = ", ".join(ident_bits)
        return f"""
        <div class="pj-block pj-plain">
          <div class="pj-head">{esc(code)} — {esc(name)}</div>
          <div class="pj-line pj-muted">{ident}. No governed foreign-currency-rules entry for a published jurisdiction associated with this currency exists yet — nothing is shown here, to avoid unsourced claims.</div>
        </div>"""

    from_html = currency_block(from_code)
    to_html = currency_block(to_code)

    from_govs = gov_map.get(from_code, [])
    to_govs = gov_map.get(to_code, [])

    # A currency pair is NOT automatically a travel corridor. A pre-filled Passage
    # Check deep-link is only honest when BOTH currencies map to exactly one
    # published jurisdiction. If either currency maps to several (e.g. EUR ->
    # France, Germany), we must not pick one to stand in for the whole currency —
    # we link generically and let the user choose the exact route.
    fs = from_govs[0]["country_slug"] if len(from_govs) == 1 else ""
    ts = to_govs[0]["country_slug"] if len(to_govs) == 1 else ""
    if fs and ts:
        q = f"?from={esc(fs)}&amp;to={esc(ts)}"
        corridor = (
            f'<p class="pj-corridor">Both currencies map to a single published jurisdiction. '
            f'<a href="/passage-check.html{q}">Run this {esc(from_code)} → {esc(to_code)} corridor in Passage Check →</a></p>'
        )
    elif from_govs and to_govs:
        corridor = (
            '<p class="pj-corridor">Published jurisdictional entries exist for both currencies, '
            'but at least one currency maps to multiple jurisdictions. '
            '<a href="/passage-check.html">Open Passage Check and choose the exact origin and destination →</a></p>'
        )
    else:
        corridor = (
            '<p class="pj-corridor">See how a conversion is a jurisdictional event — '
            '<a href="/passage-check.html">open Passage Check →</a></p>'
        )

    macro = esc(profile.get("macro_context", "")).strip()
    macro_html = f'<p class="pj-macro">{macro}</p>' if macro else ""

    return f"""
  <section class="section pj-section">
    <div class="sec-title">Currency Passage &amp; Jurisdiction Rules</div>
    <div class="sec-h2">Moving {esc(tokens["FROM_CODE"])} and {esc(tokens["TO_CODE"])} across borders</div>
    <p>A conversion is a jurisdictional event, not only an arithmetic one. Where ConvertCCY has a published jurisdiction entry associated with a currency, the governed declaration threshold and exchange-control posture are shown below with links to the source-mapped rules entry. Figures are reference-grade; verify against the linked official sources before you travel.</p>
    {macro_html}
    <div class="pj-grid">
      {from_html}
      {to_html}
    </div>
    {corridor}
  </section>"""


def build_pair_page(profile: Dict[str, Any], currencies: Dict[str, Dict[str, Any]], content: Dict[str, Any], all_codes: List[str], gov_map: Dict[str, List[Dict[str, Any]]] = None) -> str:
    tokens = make_pair_tokens(profile, currencies)
    gov_map = gov_map or {}

    brand = content.get("site_copy", {}).get("brand_name", SITE_NAME)
    tagline = content.get("site_copy", {}).get("tagline", "Currency conversion, done right.")
    trust_statement = content.get("site_copy", {}).get(
        "trust_statement",
        "Reference exchange-rate content for informational comparison."
    )

    intro = build_pair_intro(profile, content, tokens)
    from_para = build_from_currency_para(profile, content, tokens)
    to_para = build_to_currency_para(profile, content, tokens)
    rel_para = build_relationship_para(profile, content, tokens)
    driver_intro = build_driver_intro(profile, content)
    table_intro = build_table_intro(profile, content)

    educational = content.get("educational_blocks", {})
    mid_market = content.get("pair_page_templates", {}).get("mid_market_section", {})
    faq_items = build_faq_items(profile, content, tokens)

    canonical = f'{BASE_URL}/pages/{tokens["PAIR_SLUG"]}.html'
    title = f'{tokens["FROM_CODE"]} to {tokens["TO_CODE"]} Converter | {brand}'
    description = f'Convert {tokens["FROM_NAME"]} to {tokens["TO_NAME"]} with a clear reference exchange-rate page, conversion table, FAQ, and currency context.'
    related_html = related_pairs_html(profile["from_code"], profile["to_code"], all_codes)
    passage_section = build_currency_passage_section(profile, currencies, tokens, gov_map)

    faq_block_html = ""
    for item in faq_items:
        faq_block_html += f"""
        <div class="faq-item">
          <div class="faq-q" onclick="this.parentElement.classList.toggle('open')">{esc(item["q"])}</div>
          <div class="faq-a">{esc(item["a"])}</div>
        </div>
        """

    exchange_heading = educational.get("exchange_rate_explained", {}).get("heading", "What an exchange rate means")
    exchange_paras = educational.get("exchange_rate_explained", {}).get("paragraphs", [])
    market_heading = educational.get("market_drivers_explained", {}).get("heading", "What moves currencies")
    market_paras = educational.get("market_drivers_explained", {}).get("paragraphs", [])

    mid_heading = mid_market.get("heading", "Reference rate vs bank rate")
    mid_paras = mid_market.get("paragraphs", [])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<!-- Google Tag Manager -->
<script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':
new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
}})(window,document,'script','dataLayer','GTM-TWVB524B');</script>
<!-- End Google Tag Manager -->

<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-2HS37BH07J"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', 'G-2HS37BH07J');
</script>

<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{esc(canonical)}">

<meta property="og:type" content="website">
<meta property="og:site_name" content="{esc(brand)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canonical)}">

<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(description)}">

<script type="application/ld+json">
{pair_webpage_jsonld(tokens, faq_items)}
</script>

<script type="application/ld+json">
{pair_breadcrumb_jsonld(tokens)}
</script>

<script type="application/ld+json">
{faq_jsonld(faq_items)}
</script>

<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Sora:wght@300;400;600;700&display=swap" rel="stylesheet">

<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#f7f7f5;--surface:#fff;--border:#e8e8e4;--text:#111110;--muted:#888884;--accent:#1a6b3c;--accent-light:#e8f5ee;--mono:'DM Mono',monospace;--sans:'Sora',sans-serif}}
body{{font-family:var(--sans);background:var(--bg);color:var(--text);min-height:100vh;line-height:1.7}}
nav{{position:sticky;top:0;z-index:100;background:rgba(247,247,245,.92);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);padding:0 2rem;display:flex;align-items:center;justify-content:space-between;min-height:58px;gap:1rem;flex-wrap:wrap}}
.logo{{font-family:var(--mono);font-size:1.1rem;font-weight:500;color:var(--text);text-decoration:none}}
.logo span{{color:var(--accent)}}
.nav-links{{display:flex;gap:1.2rem;flex-wrap:wrap}}
.nav-links a{{font-size:.82rem;color:var(--muted);text-decoration:none}}
.nav-links a:hover{{color:var(--text)}}
.page-wrap{{max-width:860px;margin:0 auto;padding:3rem 2rem}}
.breadcrumb{{font-family:var(--mono);font-size:.75rem;color:var(--muted);margin-bottom:1.4rem}}
.breadcrumb a{{color:var(--muted);text-decoration:none}}
.breadcrumb a:hover{{color:var(--accent)}}
.pair-hero{{margin-bottom:2rem}}
.pair-flags{{font-size:2.2rem;margin-bottom:.75rem}}
.pair-hero h1{{font-size:clamp(1.9rem,4vw,2.8rem);font-weight:700;letter-spacing:-1.5px;line-height:1.1}}
.pair-hero h1 em{{font-style:normal;color:var(--accent)}}
.pair-subtitle{{font-size:.92rem;color:var(--muted);margin-top:.6rem}}
.rate-banner{{background:var(--text);color:#fff;border-radius:16px;padding:1.4rem 1.7rem;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:1rem;margin-bottom:1.5rem}}
.rate-main{{font-family:var(--mono);font-size:1.9rem;font-weight:500}}
.rate-sub{{font-size:.78rem;opacity:.7;font-family:var(--mono);margin-top:4px}}
.rate-badge{{background:var(--accent);color:#fff;font-family:var(--mono);font-size:.72rem;padding:4px 12px;border-radius:100px;white-space:nowrap}}
.rate-badge.snap{{background:#a07000}}
.rate-badge.off{{background:#8a2c2c}}
.rate-note{{font-size:.76rem;color:var(--muted);margin:-.8rem 0 1.5rem;line-height:1.5}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:18px;padding:1.7rem;margin-bottom:1.5rem;box-shadow:0 2px 20px rgba(0,0,0,.04)}}
.card-title{{font-size:.72rem;font-family:var(--mono);color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:1rem}}
.conv-row{{display:grid;grid-template-columns:1fr auto 1fr;gap:1rem;align-items:end}}
.field label{{display:block;font-size:.72rem;font-family:var(--mono);color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:.5rem}}
.field input{{width:100%;padding:.9rem 1rem;border:1.5px solid var(--border);border-radius:12px;font-family:var(--mono);font-size:1.15rem;font-weight:500;background:var(--bg);color:var(--text);outline:none;transition:border-color .2s}}
.field input:focus{{border-color:var(--accent);background:#fff}}
.swap-btn{{width:40px;height:40px;border-radius:50%;border:1.5px solid var(--border);background:var(--bg);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:1rem;transition:all .2s;color:var(--muted);align-self:center}}
.swap-btn:hover{{background:var(--accent);color:#fff;border-color:var(--accent);transform:rotate(180deg)}}
.result-row{{margin-top:1.2rem;background:var(--accent-light);border:1.5px solid #c4dfd0;border-radius:12px;padding:1rem 1.2rem;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.5rem}}
.result-val{{font-family:var(--mono);font-size:1.35rem;font-weight:500;color:var(--accent)}}
.result-info{{font-size:.78rem;color:var(--muted);font-family:var(--mono)}}
.quick-grid{{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:1rem}}
.quick-btn{{padding:6px 14px;border:1px solid var(--border);border-radius:8px;background:var(--bg);font-family:var(--mono);font-size:.8rem;cursor:pointer;color:var(--muted);transition:all .2s}}
.quick-btn:hover{{border-color:var(--accent);color:var(--accent);background:var(--accent-light)}}
.section{{margin-bottom:2rem}}
.sec-title{{font-size:.72rem;font-family:var(--mono);color:var(--muted);text-transform:uppercase;letter-spacing:1.4px;margin-bottom:.9rem}}
.sec-h2{{font-size:1.15rem;font-weight:700;letter-spacing:-.4px;margin-bottom:.6rem}}
.section p{{font-size:.92rem;color:var(--muted);margin-bottom:.95rem}}
.table-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:.88rem}}
thead th{{text-align:left;padding:.6rem 1rem;font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:1px;border-bottom:1px solid var(--border)}}
tbody tr{{border-bottom:1px solid var(--border)}}
tbody tr:hover{{background:var(--accent-light)}}
tbody td{{padding:.8rem 1rem}}
tbody td:last-child{{color:var(--accent);font-weight:500}}
.faq-item{{border-bottom:1px solid var(--border);padding:1.1rem 0}}
.faq-q{{font-weight:600;font-size:.94rem;margin-bottom:.5rem;cursor:pointer;display:flex;justify-content:space-between;align-items:center}}
.faq-q::after{{content:'+';font-family:var(--mono);color:var(--muted);font-size:1.2rem;transition:transform .2s}}
.faq-item.open .faq-q::after{{transform:rotate(45deg)}}
.faq-a{{font-size:.88rem;color:var(--muted);display:none}}
.faq-item.open .faq-a{{display:block}}
.related-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:.75rem}}
.related-card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:.9rem 1.1rem;text-decoration:none;color:var(--text);display:flex;justify-content:space-between;align-items:center;transition:all .2s}}
.related-card:hover{{border-color:var(--accent);transform:translateY(-2px)}}
.related-card span{{font-family:var(--mono);font-size:.85rem;font-weight:500}}
.related-card small{{font-family:var(--mono);font-size:.75rem;color:var(--muted)}}
footer{{border-top:1px solid var(--border);text-align:center;padding:2rem;margin-top:3rem;font-size:.78rem;color:var(--muted);font-family:var(--mono)}}
footer a{{color:var(--muted);text-decoration:none}}
footer a:hover{{color:var(--text)}}
.pj-section .sec-h2{{margin-bottom:.6rem}}
.pj-macro{{font-size:.9rem;color:var(--muted);margin-bottom:1rem}}
.pj-grid{{display:grid;grid-template-columns:1fr 1fr;gap:.9rem;margin:1rem 0}}
.pj-block{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1.1rem 1.2rem}}
.pj-gov{{border-color:#c4dfd0;background:var(--accent-light)}}
.pj-head{{font-weight:600;font-size:.92rem;margin-bottom:.5rem;display:flex;align-items:center;gap:.5rem;flex-wrap:wrap}}
.pj-badge{{font-family:var(--mono);font-size:.62rem;letter-spacing:.06em;text-transform:uppercase;color:#fff;background:var(--accent);border-radius:6px;padding:2px 7px}}
.pj-line{{font-size:.85rem;color:var(--text);line-height:1.6;margin-bottom:.35rem}}
.pj-muted{{color:var(--muted)}}
.pj-links{{font-family:var(--mono);font-size:.78rem;margin-top:.5rem}}
.pj-links a,.pj-cls a{{color:var(--accent);text-decoration:none}}
.pj-links a:hover,.pj-cls a:hover{{text-decoration:underline}}
.pj-cls{{font-family:var(--mono);font-size:.72rem;margin-top:.4rem;color:var(--muted)}}
.pj-corridor{{font-size:.88rem;margin-top:.4rem}}
.pj-corridor a{{color:var(--accent);text-decoration:none;font-weight:500}}
.pj-corridor a:hover{{text-decoration:underline}}
@media(max-width:640px){{.conv-row{{grid-template-columns:1fr}}.swap-btn{{width:100%;height:36px;border-radius:10px}}nav{{padding:1rem}}.page-wrap{{padding:2rem 1rem}}.pj-grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-TWVB524B"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
<!-- End Google Tag Manager (noscript) -->

<nav>
  <a class="logo" href="/">convert<span>ccy</span>.com</a>
  <div class="nav-links">
    <a href="/">Home</a>
    <a href="/currencies.html">Currencies</a>
    <a href="/about.html">About</a>
    <a href="/contact.html">Contact</a>
  </div>
</nav>

<div class="page-wrap">
  <div class="breadcrumb">
    <a href="/">Home</a> › <a href="/currencies.html">Currencies</a> › {esc(tokens["FROM_CODE"])} to {esc(tokens["TO_CODE"])}
  </div>

  <div class="pair-hero">
    <div class="pair-flags">{esc(tokens["FROM_FLAG"])} → {esc(tokens["TO_FLAG"])}</div>
    <h1>{esc(tokens["FROM_NAME"])} to <em>{esc(tokens["TO_NAME"])}</em></h1>
    <p class="pair-subtitle">{esc(tagline)}</p>
  </div>

  <div class="rate-banner">
    <div>
      <div class="rate-main" id="live-rate">Loading…</div>
      <div class="rate-sub">1 {esc(tokens["FROM_CODE"])} = <span id="live-rate-num">—</span> {esc(tokens["TO_CODE"])}</div>
    </div>
    <div class="rate-badge" id="rate-badge">REFERENCE</div>
  </div>
  <p class="rate-note">Indicative reference rate — live when available, otherwise a dated reference snapshot. Not a dealing rate; providers apply their own spread and fees.</p>

  <div class="card">
    <div class="card-title">Currency Converter</div>
    <div class="conv-row">
      <div class="field">
        <label>{esc(tokens["FROM_CODE"])} Amount</label>
        <input type="number" id="from-input" value="1" min="0">
      </div>
      <button class="swap-btn" onclick="swapPair()" title="Open reverse pair">⇄</button>
      <div class="field">
        <label>{esc(tokens["TO_CODE"])} Result</label>
        <input type="number" id="to-input" placeholder="0.00">
      </div>
    </div>
    <div class="result-row">
      <span class="result-val" id="main-result">—</span>
      <span class="result-info" id="rate-info">Fetching rate…</span>
    </div>
    <div class="quick-grid">
      <button class="quick-btn" onclick="setAmt(1)">1</button>
      <button class="quick-btn" onclick="setAmt(5)">5</button>
      <button class="quick-btn" onclick="setAmt(10)">10</button>
      <button class="quick-btn" onclick="setAmt(50)">50</button>
      <button class="quick-btn" onclick="setAmt(100)">100</button>
      <button class="quick-btn" onclick="setAmt(500)">500</button>
      <button class="quick-btn" onclick="setAmt(1000)">1,000</button>
    </div>
  </div>

  <section class="section">
    <div class="sec-title">Pair Overview</div>
    <div class="sec-h2">{esc(tokens["FROM_CODE"])} / {esc(tokens["TO_CODE"])} Exchange Rate</div>
    <p>{esc(intro)}</p>
    <p>{esc(from_para)}</p>
    <p>{esc(to_para)}</p>
    <p>{esc(rel_para)}</p>
  </section>
{passage_section}
  <section class="section">
    <div class="sec-title">{esc(exchange_heading)}</div>
    <div class="card">
      {"".join(f"<p>{esc(p)}</p>" for p in exchange_paras)}
    </div>
  </section>

  <section class="section">
    <div class="sec-title">{esc(mid_heading)}</div>
    <div class="card">
      {"".join(f"<p>{esc(p)}</p>" for p in mid_paras)}
      <p>{esc(trust_statement)}</p>
    </div>
  </section>

  <section class="section">
    <div class="sec-title">{esc(market_heading)}</div>
    <div class="card">
      <p>{esc(driver_intro)}</p>
      {"".join(f"<p>{esc(p)}</p>" for p in market_paras)}
    </div>
  </section>

  <section class="section">
    <div class="sec-title">Conversion Table</div>
    <p>{esc(table_intro)}</p>
    <div class="card" style="padding:0;overflow:hidden">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{esc(tokens["FROM_CODE"])}</th>
              <th>{esc(tokens["TO_CODE"])}</th>
            </tr>
          </thead>
          <tbody id="conv-table"></tbody>
        </table>
      </div>
    </div>
  </section>

  <section class="section">
    <div class="sec-title">FAQ</div>
    <div class="card">
      {faq_block_html}
    </div>
  </section>

  <section class="section">
    <div class="sec-title">Related Pairs</div>
    <div class="related-grid">
      {related_html}
    </div>
  </section>
</div>

<footer>
  <p>© 2026 <a href="/">{esc(brand)}</a> — {esc(content.get("footer_copy", {}).get("line_1", "Reference exchange-rate content for informational comparison."))}</p>
  <p style="margin-top:.55rem">{esc(content.get("footer_copy", {}).get("line_2", ""))}</p>
</footer>

<script>
const FROM = '{tokens["FROM_CODE"]}';
const TO = '{tokens["TO_CODE"]}';
let rate = null;
let rateMode = '';      // 'live' | 'snapshot' | 'unavailable'
let snapDate = '';
const AMOUNTS = [1,5,10,20,50,100,200,500,1000,5000];

async function getLiveRate() {{
  // Time-box the live call: a hanging free endpoint is the most common failure,
  // so we abort after 3.5s and fall back to the dated snapshot rather than stall.
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 3500);
  try {{
    const res = await fetch('https://api.exchangerate-api.com/v4/latest/' + FROM, {{signal: ctrl.signal}});
    if (!res.ok) throw new Error('live http');
    const data = await res.json();
    const r = data && data.rates && data.rates[TO];
    if (typeof r !== 'number' || !isFinite(r) || r <= 0) throw new Error('live rate missing');
    return r;
  }} finally {{ clearTimeout(t); }}
}}

// Fallback: same-origin dated reference snapshot (see /rates/snapshot.json).
// Never presented as live; always labelled with its capture date.
async function getSnapshotRate() {{
  const res = await fetch('/rates/snapshot.json', {{cache: 'no-cache'}});
  if (!res.ok) throw new Error('snapshot http');
  const s = await res.json();
  snapDate = s.as_of || '';
  const rf = s.rates && s.rates[FROM], rt = s.rates && s.rates[TO];
  if (!rf || !rt) throw new Error('snapshot pair missing');
  return rt / rf;
}}

async function init() {{
  try {{
    rate = await getLiveRate(); rateMode = 'live';
  }} catch (e) {{
    try {{ rate = await getSnapshotRate(); rateMode = 'snapshot'; }}
    catch (e2) {{ rate = null; rateMode = 'unavailable'; }}
  }}
  renderRate();
  convertFrom();
  buildTable();
}}

function renderRate() {{
  const main = document.getElementById('live-rate');
  const num = document.getElementById('live-rate-num');
  const badge = document.getElementById('rate-badge');
  if (rateMode === 'unavailable' || rate === null) {{
    main.textContent = 'Rate unavailable right now';
    num.textContent = '—';
    badge.textContent = 'UNAVAILABLE'; badge.className = 'rate-badge off';
    return;
  }}
  main.textContent = `1 ${{FROM}} = ${{rate.toFixed(4)}} ${{TO}}`;
  num.textContent = rate.toFixed(4);
  if (rateMode === 'snapshot') {{
    badge.textContent = snapDate ? `SNAPSHOT · ${{snapDate}}` : 'SNAPSHOT';
    badge.className = 'rate-badge snap';
    badge.title = 'Live source unavailable — showing a dated reference snapshot, not a live rate';
  }} else {{
    badge.textContent = 'REFERENCE'; badge.className = 'rate-badge';
  }}
}}

function rateContext() {{
  if (rateMode === 'snapshot') return ` · reference snapshot as of ${{snapDate || 'recent capture'}}, not live`;
  return '';
}}

function convertFrom() {{
  if (!rate) {{
    document.getElementById('main-result').textContent = '—';
    document.getElementById('rate-info').textContent = 'Live rate unavailable and no snapshot for this pair.';
    return;
  }}
  const a = parseFloat(document.getElementById('from-input').value) || 0;
  const b = a * rate;
  document.getElementById('to-input').value = b.toFixed(4);
  document.getElementById('main-result').textContent = `${{a.toLocaleString()}} ${{FROM}} = ${{b.toLocaleString('en-US', {{maximumFractionDigits:4}})}} ${{TO}}`;
  document.getElementById('rate-info').textContent = `Reference rate: 1 ${{FROM}} = ${{rate.toFixed(4)}} ${{TO}}${{rateContext()}}`;
}}

function convertTo() {{
  if (!rate) return;
  const b = parseFloat(document.getElementById('to-input').value) || 0;
  const a = b / rate;
  document.getElementById('from-input').value = a.toFixed(4);
  document.getElementById('main-result').textContent = `${{b.toLocaleString()}} ${{TO}} = ${{a.toLocaleString('en-US', {{maximumFractionDigits:4}})}} ${{FROM}}`;
  document.getElementById('rate-info').textContent = `Reference rate: 1 ${{TO}} = ${{(1/rate).toFixed(4)}} ${{FROM}}${{rateContext()}}`;
}}

function setAmt(n) {{
  document.getElementById('from-input').value = n;
  convertFrom();
}}

function buildTable() {{
  const tbody = document.getElementById('conv-table');
  if (!rate) {{ tbody.innerHTML = `<tr><td colspan="2">Conversion table unavailable — no live rate or snapshot for this pair right now.</td></tr>`; return; }}
  tbody.innerHTML = AMOUNTS.map(a => {{
    const b = (a * rate).toLocaleString('en-US', {{minimumFractionDigits:2, maximumFractionDigits:2}});
    return `<tr><td>${{a.toLocaleString()}} ${{FROM}}</td><td>${{b}} ${{TO}}</td></tr>`;
  }}).join('');
}}

function swapPair() {{
  window.location.href = `/pages/${{TO.toLowerCase()}}-to-${{FROM.toLowerCase()}}.html`;
}}

document.getElementById('from-input').addEventListener('input', convertFrom);
document.getElementById('to-input').addEventListener('input', convertTo);

init();
</script>

</body>
</html>
"""

def build_currencies_page(currencies: Dict[str, Dict[str, Any]], content: Dict[str, Any]) -> str:
    brand = content.get("site_copy", {}).get("brand_name", SITE_NAME)
    title = f"Global Currencies Index | {brand}"
    description = "Browse major world currencies and explore exchange-rate relationships across the global financial system."

    all_codes = sorted(currencies.keys(), key=lambda x: (x not in DEFAULT_POPULAR_CODES, x))
    cards = []

    for code in all_codes:
        cur = currencies[code]
        samples = choose_pair_samples(all_codes, code, limit=3)
        links = "\n".join(
            f'<a href="/pages/{code.lower()}-to-{s.lower()}.html">{esc(code)} → {esc(s)}</a>'
            for s in samples
        )

        cards.append(f"""
        <div class="currency-card">
          <div class="currency-code">{esc(code)}</div>
          <div class="currency-name">{esc(cur.get("name", code))}</div>
          <div class="pair-links">{links}</div>
        </div>
        """)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{BASE_URL}/currencies.html">

<meta property="og:type" content="website">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{BASE_URL}/currencies.html">

<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f7f7f5;color:#111;line-height:1.7;margin:0}}
.container{{max-width:1100px;margin:auto;padding:70px 20px}}
nav{{border-bottom:1px solid #e8e8e4;padding:18px 20px;background:#fff}}
h1{{font-size:42px;margin-bottom:10px}}
p.lead{{color:#555;margin-bottom:40px}}
h2{{margin-top:50px;font-size:24px}}
.currency-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}}
.currency-card{{background:#fff;border:1px solid #e8e8e4;border-radius:12px;padding:16px;transition:.2s}}
.currency-card:hover{{border-color:#1a6b3c;transform:translateY(-2px)}}
.currency-code{{font-weight:700;font-size:18px}}
.currency-name{{font-size:14px;color:#666;margin-bottom:10px}}
.pair-links a{{display:block;font-size:13px;margin:4px 0;color:#1a6b3c;text-decoration:none}}
.pair-links a:hover{{text-decoration:underline}}
.section{{margin-top:60px}}
footer{{border-top:1px solid #e8e8e4;padding:30px;text-align:center;margin-top:80px;color:#777;font-size:14px}}
</style>
</head>
<body>
<nav><a href="/">{esc(brand)}</a></nav>
<div class="container">
  <h1>Global Currency Index</h1>
  <p class="lead">Explore major world currencies and navigate exchange-rate relationships across the global financial system.</p>

  <div class="currency-grid">
    {''.join(cards)}
  </div>

  <div class="section">
    <h2>Understanding Global Currency Relationships</h2>
    <p>Currencies represent monetary systems shaped by domestic policy, inflation, growth expectations, trade flows, and market confidence.</p>
    <p>ConvertCCY organizes thousands of exchange-rate relationships into a navigable reference layer so users can move from a currency to related pairs quickly.</p>
  </div>
</div>
<footer>
  <p>© 2026 {esc(brand)}</p>
</footer>
</body>
</html>
"""

def simple_page(title: str, description: str, body_html: str, canonical_path: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{BASE_URL}/{canonical_path}">
<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f7f7f5;color:#111;line-height:1.7;margin:0}}
.container{{max-width:900px;margin:auto;padding:70px 20px}}
nav{{border-bottom:1px solid #e8e8e4;padding:18px 20px;background:#fff}}
h1{{font-size:40px;margin-bottom:18px}}
h2{{margin-top:40px;font-size:24px}}
p{{margin:16px 0;color:#444}}
footer{{border-top:1px solid #e8e8e4;padding:30px;text-align:center;margin-top:60px;color:#777;font-size:14px}}
a{{color:#1a6b3c;text-decoration:none}}
</style>
</head>
<body>
<nav><a href="/">{SITE_NAME}</a></nav>
<div class="container">
{body_html}
</div>
<footer>© 2026 {SITE_NAME}</footer>
</body>
</html>
"""

def build_methodology_page(content: Dict[str, Any]) -> str:
    section = content.get("trust_pages", {}).get("methodology", {})
    title = section.get("title", "Methodology")
    paragraphs = "".join(f"<p>{esc(p)}</p>" for p in section.get("paragraphs", []))
    body = f"<h1>{esc(title)}</h1>{paragraphs}"
    return simple_page(f"{title} | {SITE_NAME}", "Methodology behind ConvertCCY reference-rate content.", body, "methodology.html")

def build_disclaimer_page(content: Dict[str, Any]) -> str:
    section = content.get("trust_pages", {}).get("disclaimer", {})
    title = section.get("title", "Disclaimer")
    paragraphs = "".join(f"<p>{esc(p)}</p>" for p in section.get("paragraphs", []))
    body = f"<h1>{esc(title)}</h1>{paragraphs}"
    return simple_page(f"{title} | {SITE_NAME}", "Important informational disclaimer for ConvertCCY.", body, "disclaimer.html")

def build_manifesto_page(content: Dict[str, Any]) -> str:
    brand = content.get("site_copy", {}).get("brand_name", SITE_NAME)
    mission = content.get("site_copy", {}).get("long_mission", "")
    body = f"""
    <h1>The ConvertCCY Manifesto</h1>
    <p>{esc(mission)}</p>
    <h2>Clarity First</h2>
    <p>Currency conversion should not be hidden behind clutter, ambiguity, or avoidable friction.</p>
    <h2>Reference Over Noise</h2>
    <p>{esc(content.get("site_copy", {}).get("trust_statement", ""))}</p>
    <h2>A Map of the Monetary World</h2>
    <p>ConvertCCY is structured to become a reference graph of global currency relationships through thousands of connected pair pages.</p>
    """
    return simple_page(f"The ConvertCCY Manifesto | {brand}", "The philosophy behind ConvertCCY’s reference-first approach.", body, "manifesto.html")

def build_framework_page(content: Dict[str, Any]) -> str:
    body = """
    <h1>ConvertCCY Framework</h1>
    <h2>Currency Pair Graph</h2>
    <p>The platform is structured as a network of pair pages connecting currencies across the global monetary system.</p>
    <h2>Reference Exchange Rates</h2>
    <p>Pages are built to highlight relative value for informational comparison rather than to quote guaranteed retail execution prices.</p>
    <h2>Educational Layer</h2>
    <p>Each page combines conversion functionality with explanatory content, FAQs, and internal links.</p>
    <h2>Scalable SEO Architecture</h2>
    <p>The site architecture supports thousands of discoverable pair pages, trust pages, and navigational hubs.</p>
    """
    return simple_page("ConvertCCY Framework", "The structural framework behind ConvertCCY’s currency knowledge system.", body, "framework.html")

# -----------------------------------------------------------------------------
# SITEMAP
# -----------------------------------------------------------------------------

def build_sitemap(pair_profiles: Dict[str, Dict[str, Any]]) -> str:
    """Complete, generator-authoritative sitemap. Includes, in crawl-priority order:
    home; static/authority pages; the intelligence layer (governance, CRIS standard,
    ontology hub + class pages, Passage Check); articles; the PUBLISHED sovereign
    rules layer (only /rules/ — preview/RC entries live under /preview/ and are never
    listed); and all pair pages. Only files that exist on disk are emitted, so the
    sitemap can never reference a page that was not built. Previously the rules and
    article URLs were hand-merged into the sitemap after generation; they are now
    produced here so the sitemap stays complete on every build."""
    lastmod = iso_today()
    urls = [f"{BASE_URL}/"]

    # Static + authority pages (only those present on disk).
    authority_pages = STATIC_CORE_PAGES + ["governance.html", "standard.html", "passage-check.html", "passage-briefs.html", "licensing.html", "api.html"]
    seen_pages = set()
    for page in authority_pages:
        if page == "index.html" or page in seen_pages:
            continue
        if file_exists(page):
            urls.append(f"{BASE_URL}/{page}")
            seen_pages.add(page)

    # Directory hubs + their contents (hub index first, then children, sorted).
    def add_dir(dir_name: str, child_glob: str, index_name: str = "index.html"):
        d = BASE_DIR / dir_name
        if not (d / index_name).exists():
            return
        urls.append(f"{BASE_URL}/{dir_name}/")
        for f in sorted(d.glob(child_glob)):
            if f.name == index_name:
                continue
            urls.append(f"{BASE_URL}/{dir_name}/{f.name}")

    add_dir("ontology", "*.html")
    add_dir("articles", "*.html")
    add_dir("briefs", "*.html")
    # Published sovereign layer only: the country rules files, never /preview/.
    add_dir("rules", "*-foreign-currency-rules.html")
    # Static Agent Interface hub (P7A) — generated hub page, no other HTML children.
    add_dir("api", "*.html")

    # Static Agent Interface JSON routes (P7A). These are static, read-only files
    # generated by scripts/build_static_agent_interface.py from published data
    # only — never /preview/. Only files present on disk are ever listed.
    api_v1_dir = BASE_DIR / "api" / "v1"
    if (api_v1_dir / "index.json").exists():
        urls.append(f"{BASE_URL}/api/v1/index.json")
    if (api_v1_dir / "rules-index.json").exists():
        urls.append(f"{BASE_URL}/api/v1/rules-index.json")
    if (api_v1_dir / "passage-check.json").exists():
        urls.append(f"{BASE_URL}/api/v1/passage-check.json")
    for f in sorted((api_v1_dir / "rules").glob("*.json")) if (api_v1_dir / "rules").exists() else []:
        urls.append(f"{BASE_URL}/api/v1/rules/{f.name}")
    if file_exists("llms.txt"):
        urls.append(f"{BASE_URL}/llms.txt")

    for profile in sorted(pair_profiles.values(), key=lambda p: p["pair_slug"]):
        urls.append(f'{BASE_URL}/pages/{profile["pair_slug"]}.html')

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']

    for url in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{url}</loc>")
        lines.append(f"    <lastmod>{lastmod}</lastmod>")
        lines.append("  </url>")

    lines.append("</urlset>")
    return "\n".join(lines)

# -----------------------------------------------------------------------------
# BUILD
# -----------------------------------------------------------------------------

def generate_pair_pages(currencies: Dict[str, Dict[str, Any]], content: Dict[str, Any], pair_profiles: Dict[str, Dict[str, Any]], only_currencies: Optional[Set[str]] = None) -> int:
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    all_codes = sorted(currencies.keys(), key=lambda x: (x not in DEFAULT_POPULAR_CODES, x))
    gov_map = load_governed_currency_map()
    if gov_map:
        print(f"Governed currency enrichment active for: {', '.join(sorted(gov_map.keys()))}")
    else:
        print("Governed currency enrichment: passage-check.json absent — pair pages build without governed blocks")

    if only_currencies:
        print(f"Scoped regeneration: only pair pages involving {', '.join(sorted(only_currencies))}")

    count = 0
    skipped = 0
    out_of_scope = 0

    for pair_key, profile in pair_profiles.items():
        from_code = profile["from_code"]
        to_code = profile["to_code"]

        if from_code == to_code:
            skipped += 1
            continue

        if from_code not in currencies or to_code not in currencies:
            skipped += 1
            continue

        # Scoped run: only regenerate pages where one side matches a requested
        # currency. build_pair_page is deterministic per-profile, so the subset
        # output is byte-identical to the same pages in a full build.
        if only_currencies and from_code not in only_currencies and to_code not in only_currencies:
            out_of_scope += 1
            continue

        html_doc = build_pair_page(profile, currencies, content, all_codes, gov_map)
        out_path = PAGES_DIR / f'{profile["pair_slug"]}.html'
        write_text(out_path, html_doc)
        count += 1

    print(f"Generated {count} pair pages")
    if skipped:
        print(f"Skipped {skipped} invalid or incomplete profiles")
    if only_currencies:
        print(f"Left {out_of_scope} out-of-scope pair pages untouched")
    return count

MANUALLY_MANAGED_BUILDERS = [
    ("methodology.html", build_methodology_page),
    ("manifesto.html", build_manifesto_page),
    ("framework.html", build_framework_page),
]

def generate_support_pages(currencies: Dict[str, Dict[str, Any]], content: Dict[str, Any]) -> None:
    write_text(BASE_DIR / "currencies.html", build_currencies_page(currencies, content))
    write_text(BASE_DIR / "disclaimer.html", build_disclaimer_page(content))

    for name, builder in MANUALLY_MANAGED_BUILDERS:
        path = BASE_DIR / name
        if path.exists():
            print(f"Skipped {name} — manually managed, file exists")
            continue

        write_text(path, builder(content))
        print(f"Generated {name} (first time only — now manually managed)")

def generate_sitemap(pair_profiles: Dict[str, Dict[str, Any]]) -> None:
    write_text(BASE_DIR / "sitemap.xml", build_sitemap(pair_profiles))
    print("Generated sitemap.xml")

def parse_only_currencies(values: Optional[List[str]]) -> Optional[Set[str]]:
    if not values:
        return None
    codes: Set[str] = set()
    for item in values:
        for c in str(item).split(","):
            c = c.strip().upper()
            if c:
                codes.add(c)
    return codes or None


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate ConvertCCY pair pages and supporting surfaces"
    )
    parser.add_argument(
        "--only-currency",
        action="append",
        default=None,
        metavar="CODE",
        help=(
            "Regenerate only pair pages where the FROM or TO currency matches CODE "
            "(repeatable, or comma-separated). Scopes the run to those pair pages; "
            "support pages and sitemap.xml are left untouched. Omit for a full build. "
            "Deterministic: the scoped output is byte-identical to the same pages in "
            "a full build."
        ),
    )
    args = parser.parse_args()
    only_currencies = parse_only_currencies(args.only_currency)

    if not CURRENCIES_FILE.exists():
        raise FileNotFoundError(f"Missing file: {CURRENCIES_FILE}")

    if not CONTENT_FILE.exists():
        raise FileNotFoundError(f"Missing file: {CONTENT_FILE}")

    currencies = load_currencies()
    content = load_content_blocks()
    pair_profiles = load_pair_profiles()

    print(f"Loaded {len(currencies)} currencies")
    print(f"Loaded {len(pair_profiles)} pair profiles")

    if only_currencies:
        unknown = sorted(c for c in only_currencies if c not in currencies)
        if unknown:
            print(f"Warning: requested currency code(s) not in currencies.json: {', '.join(unknown)}")
        generate_pair_pages(currencies, content, pair_profiles, only_currencies=only_currencies)
        print(
            f"\nScoped build complete for {', '.join(sorted(only_currencies))}. "
            "Support pages and sitemap.xml intentionally left unchanged "
            "(pair-page URLs are stable, so the sitemap does not move)."
        )
        return

    generate_pair_pages(currencies, content, pair_profiles)
    generate_support_pages(currencies, content)
    generate_sitemap(pair_profiles)

    print("\nBuild complete.")
    print("Next steps:")
    print("1) Review the generated files")
    print("2) Commit changes in GitHub Desktop")
    print("3) Push to origin")

if __name__ == "__main__":
    main()
