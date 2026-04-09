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
from typing import Dict, List, Any, Tuple

# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------

BASE_URL = "https://convertccy.com"
SITE_NAME = "ConvertCCY"
GTM_ID = "GTM-TWVB524B"
OG_IMAGE = f"{BASE_URL}/assets/images/og-default.png"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PAIR_PARTS_DIR = DATA_DIR / "pair_profiles_parts"
PAGES_DIR = BASE_DIR / "pages"

CURRENCIES_FILE = DATA_DIR / "currencies.json"
CONTENT_FILE = DATA_DIR / "content_blocks.json"

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
        "FROM_DESC": from_cur.get("short_description", ""),
        "TO_DESC": to_cur.get("short_description", ""),
        "FROM_COUNTRY": from_cur.get("country", ""),
        "TO_COUNTRY": to_cur.get("country", ""),
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

def build_pair_page(profile: Dict[str, Any], currencies: Dict[str, Dict[str, Any]], content: Dict[str, Any], all_codes: List[str]) -> str:
    tokens = make_pair_tokens(profile, currencies)

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
<script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);}})(window,document,'script','dataLayer','{GTM_ID}');</script>
<!-- End Google Tag Manager -->

<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{esc(canonical)}">
<link rel="icon" href="/favicon.ico" type="image/x-icon">

<meta property="og:type" content="website">
<meta property="og:site_name" content="{esc(brand)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:image" content="{OG_IMAGE}">

<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(description)}">
<meta name="twitter:image" content="{OG_IMAGE}">

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
<link rel="preload" href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Sora:wght@300;400;600;700&display=swap" as="style" onload="this.onload=null;this.rel='stylesheet'">
<noscript><link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Sora:wght@300;400;600;700&display=swap" rel="stylesheet"></noscript>
<link rel="stylesheet" href="/assets/pair.css">
</head>
<body>
<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={GTM_ID}" height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
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
    <div class="rate-badge">REFERENCE</div>
  </div>

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
const AMOUNTS = [1,5,10,20,50,100,200,500,1000,5000];

async function init() {{
  try {{
    const res = await fetch('https://api.exchangerate-api.com/v4/latest/' + FROM);
    if (!res.ok) throw new Error('API error');
    const data = await res.json();
    rate = data.rates[TO];
    if (!rate || isNaN(rate)) throw new Error('Rate not found');
  }} catch (e) {{
    document.getElementById('live-rate').textContent = 'Rate unavailable';
    document.getElementById('live-rate-num').textContent = '—';
    document.getElementById('rate-info').textContent = 'Live rate could not be loaded. Please try refreshing.';
    return;
  }}

  document.getElementById('live-rate').textContent = `1 ${{FROM}} = ${{rate.toFixed(4)}} ${{TO}}`;
  document.getElementById('live-rate-num').textContent = rate.toFixed(4);

  convertFrom();
  buildTable();
}}

function convertFrom() {{
  if (!rate) return;
  const a = parseFloat(document.getElementById('from-input').value) || 0;
  const b = a * rate;
  document.getElementById('to-input').value = b.toFixed(4);
  document.getElementById('main-result').textContent = `${{a.toLocaleString()}} ${{FROM}} = ${{b.toLocaleString('en-US', {{maximumFractionDigits:4}})}} ${{TO}}`;
  document.getElementById('rate-info').textContent = `Reference rate: 1 ${{FROM}} = ${{rate.toFixed(4)}} ${{TO}}`;
}}

function convertTo() {{
  if (!rate) return;
  const b = parseFloat(document.getElementById('to-input').value) || 0;
  const a = b / rate;
  document.getElementById('from-input').value = a.toFixed(4);
  document.getElementById('main-result').textContent = `${{b.toLocaleString()}} ${{TO}} = ${{a.toLocaleString('en-US', {{maximumFractionDigits:4}})}} ${{FROM}}`;
  document.getElementById('rate-info').textContent = `Reference rate: 1 ${{TO}} = ${{(1/rate).toFixed(4)}} ${{FROM}}`;
}}

function setAmt(n) {{
  document.getElementById('from-input').value = n;
  convertFrom();
}}

function buildTable() {{
  const tbody = document.getElementById('conv-table');
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
    lastmod = iso_today()

    # (url, priority, changefreq)
    entries: List[Tuple[str, str, str]] = [
        (f"{BASE_URL}/", "1.0", "daily"),
    ]

    for page in STATIC_CORE_PAGES:
        if file_exists(page) and page != "index.html":
            entries.append((f"{BASE_URL}/{page}", "0.8", "monthly"))

    for profile in sorted(pair_profiles.values(), key=lambda p: p["pair_slug"]):
        slug = profile["pair_slug"]
        from_code = profile.get("from_code", "")
        # higher priority for popular pairs
        is_popular = from_code in DEFAULT_POPULAR_CODES
        priority = "0.7" if is_popular else "0.4"
        entries.append((f"{BASE_URL}/pages/{slug}.html", priority, "daily"))

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']

    for url, priority, changefreq in entries:
        lines.append("  <url>")
        lines.append(f"    <loc>{url}</loc>")
        lines.append(f"    <lastmod>{lastmod}</lastmod>")
        lines.append(f"    <changefreq>{changefreq}</changefreq>")
        lines.append(f"    <priority>{priority}</priority>")
        lines.append("  </url>")

    lines.append("</urlset>")
    return "\n".join(lines)

# -----------------------------------------------------------------------------
# BUILD
# -----------------------------------------------------------------------------

def generate_pair_pages(currencies: Dict[str, Dict[str, Any]], content: Dict[str, Any], pair_profiles: Dict[str, Dict[str, Any]]) -> int:
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    all_codes = sorted(currencies.keys(), key=lambda x: (x not in DEFAULT_POPULAR_CODES, x))

    count = 0
    skipped = 0

    for pair_key, profile in pair_profiles.items():
        from_code = profile["from_code"]
        to_code = profile["to_code"]

        if from_code == to_code:
            skipped += 1
            continue

        if from_code not in currencies or to_code not in currencies:
            skipped += 1
            continue

        html_doc = build_pair_page(profile, currencies, content, all_codes)
        out_path = PAGES_DIR / f'{profile["pair_slug"]}.html'
        write_text(out_path, html_doc)
        count += 1

    print(f"Generated {count} pair pages")
    if skipped:
        print(f"Skipped {skipped} invalid or incomplete profiles")
    return count

def generate_support_pages(currencies: Dict[str, Dict[str, Any]], content: Dict[str, Any]) -> None:
    write_text(BASE_DIR / "currencies.html", build_currencies_page(currencies, content))
    write_text(BASE_DIR / "methodology.html", build_methodology_page(content))
    write_text(BASE_DIR / "disclaimer.html", build_disclaimer_page(content))
    write_text(BASE_DIR / "manifesto.html", build_manifesto_page(content))
    write_text(BASE_DIR / "framework.html", build_framework_page(content))
    print("Generated currencies.html, methodology.html, disclaimer.html, manifesto.html, framework.html")

def generate_sitemap(pair_profiles: Dict[str, Dict[str, Any]]) -> None:
    write_text(BASE_DIR / "sitemap.xml", build_sitemap(pair_profiles))
    print("Generated sitemap.xml")

def main():
    if not CURRENCIES_FILE.exists():
        raise FileNotFoundError(f"Missing file: {CURRENCIES_FILE}")

    if not CONTENT_FILE.exists():
        raise FileNotFoundError(f"Missing file: {CONTENT_FILE}")

    currencies = load_currencies()
    content = load_content_blocks()
    pair_profiles = load_pair_profiles()

    print(f"Loaded {len(currencies)} currencies")
    print(f"Loaded {len(pair_profiles)} pair profiles")

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
