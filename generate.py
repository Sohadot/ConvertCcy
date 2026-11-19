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


def _git_run(repo_root: Path, args: List[str]):
    import subprocess
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def build_git_content_lastmod_index(
    repo_root: Path,
    *,
    today: Optional[str] = None,
    git_runner=None,
) -> Tuple[Dict[str, str], Set[str], Optional[str], float]:
    """Build path → content-change date maps from repository history.

    Returns:
      history_dates: tracked path (posix, repo-relative) → YYYY-MM-DD of the
        newest commit that materially changed that path
      dirty_paths: modified or untracked paths (posix) whose content is changing
        in this working tree
      today_iso: UTC date used for dirty/untracked paths (None if clock not set
        and no dirty paths need it)
      elapsed_seconds: wall time spent building the maps

    Does NOT use filesystem mtime. If Git history cannot be read, history_dates
    is empty and callers must omit <lastmod> rather than fabricate dates.
    """
    import time as _time

    t0 = _time.perf_counter()
    today_iso = today if today is not None else iso_today()
    runner = git_runner or (lambda args: _git_run(repo_root, args))

    history_dates: Dict[str, str] = {}
    dirty_paths: Set[str] = set()

    log = runner(["log", "--pretty=format:%cI", "--name-only", "--diff-filter=ACMR"])
    if log.returncode != 0:
        # No trustworthy Git history — omit lastmod rather than invent dates.
        return {}, set(), today_iso, _time.perf_counter() - t0

    current_date: Optional[str] = None
    for raw_line in log.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "T" in line and len(line) >= 10 and line[0:4].isdigit():
            # Committer ISO timestamp → calendar date in that timestamp's zone
            # prefix (YYYY-MM-DD). Prefer the date component only.
            current_date = line[:10]
            continue
        if current_date is None:
            continue
        path = line.replace("\\", "/")
        # Newest commit first: keep the first date seen per path.
        if path not in history_dates:
            history_dates[path] = current_date

    status = runner(["status", "--porcelain", "-uall"])
    if status.returncode == 0:
        for raw_line in status.stdout.splitlines():
            if len(raw_line) < 4:
                continue
            entry = raw_line[3:].strip()
            if " -> " in entry:
                entry = entry.split(" -> ", 1)[1].strip()
            entry = entry.strip('"').replace("\\", "/")
            if entry:
                dirty_paths.add(entry)

    return history_dates, dirty_paths, today_iso, _time.perf_counter() - t0


def resolve_content_lastmod(
    rel_path: str,
    history_dates: Dict[str, str],
    dirty_paths: Set[str],
    today_iso: Optional[str],
) -> Optional[str]:
    """Return YYYY-MM-DD for a repo-relative path, or None to omit <lastmod>."""
    path = rel_path.replace("\\", "/")
    if path in dirty_paths:
        return today_iso
    return history_dates.get(path)


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

def faq_items_html(faq_items: List[Dict[str, str]]) -> str:
    out = ""
    for item in faq_items:
        out += f"""
        <div class="faq-item">
          <div class="faq-q" onclick="this.parentElement.classList.toggle('open')">{esc(item["q"])}</div>
          <div class="faq-a">{esc(item["a"])}</div>
        </div>
        """
    return out


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

def pair_webpage_jsonld(tokens: Dict[str, str], faq_items: List[Dict[str, str]], archival: Any = False) -> str:
    graph = [
        {
            "@type": "WebPage",
            "name": pair_metadata(tokens, archival)["schema_name"],
            "url": f'{BASE_URL}/pages/{tokens["PAIR_SLUG"]}.html',
            "description": pair_metadata(tokens, archival)["schema_description"]
        },
        {
            "@type": "WebApplication",
            "name": f'{tokens["FROM_CODE"]} to {tokens["TO_CODE"]} Currency Converter',
            "applicationCategory": "FinanceApplication",
            "operatingSystem": "Web",
            "url": f'{BASE_URL}/pages/{tokens["PAIR_SLUG"]}.html'
        }
    ]
    if archival == "rate_regime_governed":
        # SEO-A4.6B: keep WebApplication only where the page still converts amounts.
        if rate_regime_pair(tokens["FROM_CODE"], tokens["TO_CODE"])["mode"] != "converter":
            graph = graph[:1]
    elif archival:
        # SEO-A4.2: no operational converter exists for a historical/legacy pair,
        # so the WebApplication node would misdescribe the page.
        graph = graph[:1]
    return json.dumps({
        "@context": "https://schema.org",
        "@graph": graph
    }, ensure_ascii=False, indent=2)

# -----------------------------------------------------------------------------
# INTERNAL LINK GRAPH (SEO-A2)
# -----------------------------------------------------------------------------
#
# Crawl path for every pair page (all plain <a href>, no JS navigation):
#
#   index.html -> currencies.html -> /currencies/<code>.html -> /pages/<a>-to-<b>.html
#
# Each currency hub links all 169 pairs FROM that currency and all 169 pairs
# TO it, so every pair page has exactly two non-pair (hub) inbound links and
# sits at depth <= 3 from the homepage. Pair pages additionally carry a
# bounded, deterministic related-pairs block (RELATED_PAIR_LIMIT links) built
# from four sources — reverse pair, alphabetical "ring" neighbours on both
# sides (spreads inbound links evenly across all pairs), and importance-ranked
# alternatives from the profile `importance_score` — plus links to both hubs.

RELATED_PAIR_LIMIT = 12
RELATED_IMPORTANCE_PER_SIDE = 3


def currency_hub_href(code: str) -> str:
    return f"/currencies/{code.lower()}.html"


def pair_href(from_code: str, to_code: str) -> str:
    return f"/pages/{from_code.lower()}-to-{to_code.lower()}.html"


def popularity_rank(code: str) -> int:
    try:
        return DEFAULT_POPULAR_CODES.index(code)
    except ValueError:
        return len(DEFAULT_POPULAR_CODES)


def site_currency_order(codes) -> List[str]:
    """Popular-first, then alphabetical (the order used across the site)."""
    return sorted(codes, key=lambda x: (x not in DEFAULT_POPULAR_CODES, x))


def build_pair_importance_index(pair_profiles: Dict[str, Dict[str, Any]]) -> Dict[Tuple[str, str], int]:
    out: Dict[Tuple[str, str], int] = {}
    for p in pair_profiles.values():
        try:
            out[(p["from_code"], p["to_code"])] = int(p.get("importance_score") or 0)
        except (TypeError, ValueError):
            out[(p["from_code"], p["to_code"])] = 0
    return out


def select_related_pairs(
    from_code: str,
    to_code: str,
    all_codes: List[str],
    importance: Optional[Dict[Tuple[str, str], int]] = None,
    limit: int = RELATED_PAIR_LIMIT,
) -> List[Tuple[str, str]]:
    """Deterministic, bounded related-pair selection for one directed pair.

    Order of preference (duplicates and self-pairs skipped):
      1. reverse pair (B -> A)
      2. same-base ring:  A -> next/prev of B in alphabetical order
      3. same-quote ring: next/prev of A -> B in alphabetical order
      4. same-base importance: top A -> X by importance_score
      5. same-quote importance: top X -> B by importance_score
      6. widen the rings (distance 2, 3, ...) until `limit` is reached

    The rings guarantee every pair receives links from its four alphabetical
    neighbours, which removes reverse-pair-only 2-cycles without depending on
    popularity. Importance ties break on DEFAULT_POPULAR_CODES order, then code.
    No randomness: identical input always yields identical output.
    """
    importance = importance or {}
    codes = sorted(set(all_codes))
    A, B = from_code, to_code
    out: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = {(A, B)}

    def add(pair: Tuple[str, str]) -> None:
        a, b = pair
        if a == b or pair in seen or a not in codes or b not in codes:
            return
        if len(out) >= limit:
            return
        seen.add(pair)
        out.append(pair)

    quotes = [c for c in codes if c != A]   # possible B for base A
    bases = [c for c in codes if c != B]    # possible A for quote B
    qi = quotes.index(B) if B in quotes else 0
    bi = bases.index(A) if A in bases else 0

    def ring(d: int) -> List[Tuple[str, str]]:
        return [
            (A, quotes[(qi + d) % len(quotes)]),
            (A, quotes[(qi - d) % len(quotes)]),
            (bases[(bi + d) % len(bases)], B),
            (bases[(bi - d) % len(bases)], B),
        ]

    add((B, A))
    for pair in ring(1):
        add(pair)

    def rank_key(score_pair: Tuple[str, str], other: str):
        return (-importance.get(score_pair, 0), popularity_rank(other), other)

    from_side = sorted((c for c in quotes if c != B), key=lambda c: rank_key((A, c), c))
    to_side = sorted((c for c in bases if c != A), key=lambda c: rank_key((c, B), c))
    for c in from_side[:RELATED_IMPORTANCE_PER_SIDE]:
        add((A, c))
    for c in to_side[:RELATED_IMPORTANCE_PER_SIDE]:
        add((c, B))

    d = 2
    while len(out) < limit and d <= len(codes):
        for pair in ring(d):
            add(pair)
        d += 1
    return out


def related_pairs_html(
    from_code: str,
    to_code: str,
    all_codes: List[str],
    importance: Optional[Dict[Tuple[str, str], int]] = None,
    limit: int = RELATED_PAIR_LIMIT,
) -> str:
    cards = []
    for a, b in select_related_pairs(from_code, to_code, all_codes, importance, limit):
        cards.append(
            f'<a class="related-card" href="{pair_href(a, b)}"><span>{esc(a)} → {esc(b)}</span><small>→</small></a>'
        )
    return "\n".join(cards)


PAIR_NAV_START_MARKER = '  <section class="section">\n    <div class="sec-title">Related Pairs</div>'
PAIR_NAV_END_MARKER = "\n</div>\n\n<footer>"


def pair_navigation_html(
    from_code: str,
    to_code: str,
    all_codes: List[str],
    importance: Optional[Dict[Tuple[str, str], int]] = None,
) -> str:
    """The pair page's navigation region (related pairs + currency hubs).

    This is the ONLY region a navigation-only refresh rewrites in an existing
    pair page; it starts at PAIR_NAV_START_MARKER and ends right before
    PAIR_NAV_END_MARKER. Reuses existing CSS classes (no <head> change).
    """
    related_html = related_pairs_html(from_code, to_code, all_codes, importance)
    hubs_html = "\n".join(
        f'<a class="related-card" href="{currency_hub_href(c)}"><span>All {esc(c)} pairs</span><small>→</small></a>'
        for c in (from_code, to_code)
    )
    return f"""  <section class="section">
    <div class="sec-title">Related Pairs</div>
    <div class="related-grid">
      {related_html}
    </div>
  </section>

  <section class="section">
    <div class="sec-title">Currency Hubs</div>
    <div class="related-grid">
      {hubs_html}
    </div>
  </section>"""


def replace_pair_navigation(page_html: str, new_nav: str) -> str:
    """Swap only the navigation region of an already-published pair page.

    Raises ValueError if the region cannot be located exactly once, so a
    template mismatch never silently rewrites anything else.
    """
    if page_html.count(PAIR_NAV_START_MARKER) != 1 or page_html.count(PAIR_NAV_END_MARKER) != 1:
        raise ValueError("pair navigation region not found exactly once")
    start = page_html.index(PAIR_NAV_START_MARKER)
    end = page_html.index(PAIR_NAV_END_MARKER)
    if end <= start:
        raise ValueError("pair navigation region markers out of order")
    return page_html[:start] + new_nav + page_html[end:]

# -----------------------------------------------------------------------------
# STATIC PAIR VALUE (SEO-A3)
# -----------------------------------------------------------------------------
#
# Architecture: ONE shared numeric source (data/rate_snapshot.json, byte-identical
# public copy at rates/snapshot.json, built by scripts/build_rate_snapshot.py).
# Pair pages carry values DERIVED from it inside three marked regions:
#
#   <!-- STATIC-RATE:START -->        rate banner, freshness/source note, converter
#   <!-- STATIC-RATE-TABLE:START -->  static conversion table
#   <!-- RATE-SCRIPT:START -->        <script src="/assets/js/pair-rate.js">
#
# `generate.py --static-rates-only` rewrites only those regions (fail-closed on
# missing/duplicated markers). The snapshot JSON can be refreshed on its own
# (2 files); pages then upgrade client-side to the newer snapshot, and the
# baked HTML values are refreshed on a governed cadence, never implicitly.
# Runtime logic lives in ONE shared file, so JS changes never touch pair HTML.

RATE_SNAPSHOT_FILE = DATA_DIR / "rate_snapshot.json"
PUBLIC_RATE_SNAPSHOT_FILE = BASE_DIR / "rates" / "snapshot.json"
RATE_SCRIPT_SRC = "/assets/js/pair-rate.js"
RATE_SIG_MIN = 3
RATE_SIG_MAX = 6
DEFAULT_STATIC_AMOUNTS = [1, 5, 10, 20, 50, 100, 500, 1000, 10000]

STATIC_RATE_START = "  <!-- STATIC-RATE:START -->"
STATIC_RATE_END = "  <!-- STATIC-RATE:END -->"
STATIC_TABLE_START = "    <!-- STATIC-RATE-TABLE:START -->"
STATIC_TABLE_END = "    <!-- STATIC-RATE-TABLE:END -->"
RATE_SCRIPT_START = "<!-- RATE-SCRIPT:START -->"
RATE_SCRIPT_END = "<!-- RATE-SCRIPT:END -->"

# Pre-SEO-A3 layout anchors, used once to migrate legacy pages into markers.
_LEGACY_RATE_START = '  <div class="rate-banner">\n'
_LEGACY_RATE_END = '\n\n  <section class="section">\n    <div class="sec-title">Pair Overview</div>'
_LEGACY_TABLE_START = '    <div class="card" style="padding:0;overflow:hidden">\n      <div class="table-wrap">'
_LEGACY_TABLE_END = '\n  </section>\n\n  <section class="section">\n    <div class="sec-title">FAQ</div>'
_LEGACY_SCRIPT_START = "<script>\nconst FROM = '"
_LEGACY_SCRIPT_END = "init();\n</script>"

# Codes with no rate in the snapshot source, classified (SEO-A3 §15). Indexability
# is NOT changed here; the classification only drives a truthful static message.
UNSUPPORTED_CODE_REASONS = {
    "XTS": "XTS is the ISO 4217 code reserved for testing; it has no exchange rate",
    "XXX": "XXX is the ISO 4217 code for transactions where no currency is involved; it has no exchange rate",
    "XAU": "XAU (gold, troy ounce) is a precious-metal code that the snapshot source does not price",
    "XAG": "XAG (silver, troy ounce) is a precious-metal code that the snapshot source does not price",
    "XPD": "XPD (palladium, troy ounce) is a precious-metal code that the snapshot source does not price",
    "XPT": "XPT (platinum, troy ounce) is a precious-metal code that the snapshot source does not price",
    "XSU": "XSU (SUCRE) is a regional unit of account that the snapshot source does not publish",
    "XUA": "XUA (ADB Unit of Account) is a unit of account that the snapshot source does not publish",
    "UYW": "UYW (Uruguayan nominal wage index unit) is a unit of account that the snapshot source does not publish",
    "CUC": "CUC (Cuban convertible peso) is a legacy/transition code that the snapshot source does not publish",
    "SVC": "SVC (Salvadoran colón) is a legacy/transition code that the snapshot source does not publish",
    "KPW": "KPW (North Korean won) is a valid currency that the snapshot source does not publish",
    "VED": "VED (Venezuelan digital bolívar) is a valid currency that the snapshot source does not publish",
}


class RateSnapshotError(ValueError):
    pass


def _reject_duplicate_keys(pairs):
    seen = {}
    for k, v in pairs:
        if k in seen:
            raise RateSnapshotError(f"duplicate key in snapshot: {k!r}")
        seen[k] = v
    return seen


def parse_rate_snapshot(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise RateSnapshotError(f"snapshot is not valid JSON: {exc}") from exc


def validate_rate_snapshot_data(snap: Any) -> List[str]:
    """Return a list of schema/data errors (empty = valid)."""
    errs: List[str] = []
    if not isinstance(snap, dict):
        return ["snapshot root must be an object"]
    if snap.get("type") != "reference_rate_snapshot":
        errs.append("type must be 'reference_rate_snapshot'")
    base = snap.get("base")
    if not (isinstance(base, str) and re.fullmatch(r"[A-Z]{3}", base)):
        errs.append("base must be a 3-letter uppercase code")
    as_of = snap.get("as_of")
    try:
        datetime.strptime(str(as_of), "%Y-%m-%d")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(as_of)):
            raise ValueError
    except ValueError:
        errs.append(f"as_of must be YYYY-MM-DD, got {as_of!r}")
    cap = snap.get("captured_at")
    if not (isinstance(cap, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", cap)):
        errs.append("captured_at must be an ISO-8601 UTC timestamp (YYYY-MM-DDTHH:MM:SSZ)")
    if not (isinstance(snap.get("source"), str) and snap["source"].strip()):
        errs.append("source must be a non-empty string")
    rates = snap.get("rates")
    if not isinstance(rates, dict) or not rates:
        errs.append("rates must be a non-empty object")
        return errs
    for code, val in rates.items():
        if not (isinstance(code, str) and re.fullmatch(r"[A-Z]{3}", code)):
            errs.append(f"malformed currency code {code!r}")
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            errs.append(f"{code}: rate must be numeric, got {val!r}")
        elif not (val == val and val not in (float("inf"), float("-inf"))):
            errs.append(f"{code}: rate must be finite")
        elif val <= 0:
            errs.append(f"{code}: rate must be positive, got {val!r}")
    if isinstance(base, str) and rates.get(base) != 1:
        errs.append(f"base currency {base} must have rate exactly 1")
    if snap.get("count") != len(rates):
        errs.append(f"count {snap.get('count')!r} != number of rates {len(rates)}")
    return errs


_SNAPSHOT_CACHE: Dict[str, Dict[str, Any]] = {}


def load_rate_snapshot(path: Path = RATE_SNAPSHOT_FILE) -> Dict[str, Any]:
    """Load and validate the snapshot; raises RateSnapshotError on bad data."""
    key = str(path)
    if key not in _SNAPSHOT_CACHE:
        snap = parse_rate_snapshot(Path(path).read_text(encoding="utf-8"))
        errs = validate_rate_snapshot_data(snap)
        if errs:
            raise RateSnapshotError("invalid rate snapshot: " + "; ".join(errs[:5]))
        _SNAPSHOT_CACHE[key] = snap
    return _SNAPSHOT_CACHE[key]


# ---- precision policy -------------------------------------------------------
#
# The source publishes each USD-based rate with 2 decimal places or 3
# significant digits, whichever is finer (JSON drops trailing zeros, so
# 0.310 arrives as 0.31). A leg's relative uncertainty is therefore
# half a unit of its last published digit; the base leg (exactly 1) has none.
# A cross rate's uncertainty is the sum of its two legs, and it is shown with
#     sig = clamp(floor(-log10(u_from + u_to)), 3, 6)
# significant digits, rounded half-up, in plain decimal notation with thousands
# separators (never scientific notation). Table values (amount x rate) and the
# inverse (1 / rate) use the same sig, so no row claims more precision than
# the rate itself.

def leg_relative_uncertainty(value: float, base_value: bool = False) -> float:
    if base_value:
        return 0.0
    from decimal import Decimal
    exp = Decimal(repr(float(value))).adjusted()
    last_digit_exp = min(-2, exp - 2)
    return 0.5 * (10.0 ** last_digit_exp) / float(value)


def significant_digits_for(uncertainty: float) -> int:
    import math
    if uncertainty <= 0:
        return RATE_SIG_MAX
    return max(RATE_SIG_MIN, min(RATE_SIG_MAX, int(math.floor(-math.log10(uncertainty)))))


def format_rate_value(value: float, sig: int) -> str:
    """Round to `sig` significant digits (half-up); plain decimal with grouping."""
    from decimal import Decimal, ROUND_HALF_UP
    d = Decimal(repr(float(value)))
    if d <= 0:
        raise ValueError("format_rate_value requires a positive value")
    exp = d.adjusted()
    r = d.quantize(Decimal(1).scaleb(exp - sig + 1), rounding=ROUND_HALF_UP)
    if r.adjusted() != exp:  # rounding carried into a new leading digit (9.995 -> 10.0)
        exp = r.adjusted()
        r = d.quantize(Decimal(1).scaleb(exp - sig + 1), rounding=ROUND_HALF_UP)
    if r.as_tuple().exponent >= 0:
        return f"{int(r):,}"
    return f"{r:,f}"


def format_amount(amount: Any) -> str:
    return f"{int(amount):,}" if float(amount) == int(amount) else f"{amount:,}"


def static_pair_rate(from_code: str, to_code: str, snapshot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Derive the static cross rate; None when either side has no snapshot rate."""
    rates = snapshot["rates"]
    base = snapshot["base"]
    rf, rt = rates.get(from_code), rates.get(to_code)
    if not rf or not rt:
        return None
    rate = float(rt) / float(rf)
    u = leg_relative_uncertainty(rf, from_code == base) + leg_relative_uncertainty(rt, to_code == base)
    sig = significant_digits_for(u)
    return {
        "rate": rate,
        "inverse": 1.0 / rate,
        "sig": sig,
        "as_of": snapshot["as_of"],
        "source": snapshot["source"],
    }


def unsupported_reason(from_code: str, to_code: str, snapshot: Dict[str, Any]) -> str:
    bits = []
    for c in (from_code, to_code):
        if c not in snapshot["rates"]:
            bits.append(UNSUPPORTED_CODE_REASONS.get(c, f"{c} is not published by the snapshot source"))
    return "; ".join(dict.fromkeys(bits))


def static_rate_region_html(profile: Dict[str, Any], tokens: Dict[str, str], snapshot: Dict[str, Any],
                            force_ordinary: bool = False) -> str:
    """Rate banner + freshness/source note + converter (between STATIC-RATE markers)."""
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    treatment = "snapshot" if force_ordinary else pair_rate_treatment(F, T, snapshot)
    if treatment == "rate_regime_governed":
        return regime_rate_region_html(profile, tokens, snapshot)
    if treatment == "standards_special":
        return standards_rate_region_html(tokens)
    if treatment == "precious_metal":
        return metal_rate_region_html(tokens, snapshot)
    if treatment == "institutional_unit":
        return institutional_rate_region_html(tokens, snapshot)
    if treatment == "live_fiat_coverage":
        return live_fiat_rate_region_html(tokens, snapshot)
    if treatment == "historical":
        return historical_rate_region_html(tokens, snapshot)
    rev_href = f'/pages/{T.lower()}-to-{F.lower()}.html'
    sr = static_pair_rate(F, T, snapshot)
    if sr is None:
        reason = unsupported_reason(F, T, snapshot)
        return f"""{STATIC_RATE_START}
  <div class="rate-banner" id="rate-root" data-from="{esc(F)}" data-to="{esc(T)}" data-mode="unsupported">
    <div>
      <div class="rate-main" id="live-rate">No reference rate available</div>
      <div class="rate-sub" id="rate-sub">{esc(F)} → {esc(T)} is not covered by the ConvertCCY reference snapshot</div>
    </div>
    <div class="rate-badge off" id="rate-badge">NO RATE</div>
  </div>
  <p class="rate-note" id="rate-source">No current reference rate is available for this pair in the ConvertCCY snapshot: {esc(reason)}. No value is shown rather than an estimate.</p>

  <div class="card">
    <div class="card-title">Currency Converter</div>
    <p class="result-info">Conversion is not available for {esc(F)} → {esc(T)} because no reference rate exists for this pair. <a href="{rev_href}">Open the reverse pair</a> or use the related pairs and currency hubs below.</p>
  </div>
{STATIC_RATE_END}"""

    sig = sr["sig"]
    rate_s = format_rate_value(sr["rate"], sig)
    inv_s = format_rate_value(sr["inverse"], sig)
    as_of = esc(sr["as_of"])
    source = esc(sr["source"])
    quick = "\n".join(
        f'      <button class="quick-btn" type="button" onclick="setAmt({a})">{format_amount(a)}</button>'
        for a in (1, 5, 10, 50, 100, 500, 1000)
    )
    return f"""{STATIC_RATE_START}
  <div class="rate-banner" id="rate-root" data-from="{esc(F)}" data-to="{esc(T)}" data-mode="snapshot" data-rate="{sr['rate']!r}" data-sig="{sig}" data-asof="{as_of}">
    <div>
      <div class="rate-main" id="live-rate">1 {esc(F)} = {rate_s} {esc(T)}</div>
      <div class="rate-sub" id="rate-sub">1 {esc(T)} = <span id="inverse-rate">{inv_s}</span> {esc(F)}</div>
    </div>
    <div class="rate-badge snap" id="rate-badge">SNAPSHOT · {as_of}</div>
  </div>
  <p class="rate-note" id="rate-source">Reference snapshot as of {as_of} · source: {source} (USD-based reference rates, cross-calculated by ConvertCCY). Indicative only — not a live or dealing rate; providers apply their own spread and fees. When the live source responds, this page switches to the live reference value and labels it as live.</p>

  <div class="card">
    <div class="card-title">Currency Converter</div>
    <div class="conv-row">
      <div class="field">
        <label for="from-input">{esc(F)} Amount</label>
        <input type="number" id="from-input" value="1" min="0" inputmode="decimal">
      </div>
      <a class="swap-btn" href="{rev_href}" title="Open reverse pair" aria-label="Open {esc(T)} to {esc(F)}" style="text-decoration:none">⇄</a>
      <div class="field">
        <label for="to-input">{esc(T)} Result</label>
        <input type="number" id="to-input" value="{format_rate_value(sr['rate'], sig).replace(',', '')}" min="0" inputmode="decimal">
      </div>
    </div>
    <div class="result-row">
      <span class="result-val" id="main-result">1 {esc(F)} = {rate_s} {esc(T)}</span>
      <span class="result-info" id="rate-info">Reference snapshot as of {as_of}</span>
    </div>
    <div class="quick-grid">
{quick}
    </div>
    <noscript><p class="result-info" style="margin-top:.8rem">Custom amounts need JavaScript; the conversion table below lists fixed amounts at the snapshot rate.</p></noscript>
  </div>
{STATIC_RATE_END}"""


def static_table_region_html(profile: Dict[str, Any], tokens: Dict[str, str], snapshot: Dict[str, Any],
                             force_ordinary: bool = False) -> str:
    """Static conversion table card (between STATIC-RATE-TABLE markers)."""
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    treatment = "snapshot" if force_ordinary else pair_rate_treatment(F, T, snapshot)
    if treatment == "rate_regime_governed":
        return regime_table_region_html(profile, tokens, snapshot)
    if treatment == "standards_special":
        return standards_table_region_html(tokens)
    if treatment == "precious_metal":
        return metal_table_region_html(tokens, snapshot)
    if treatment == "institutional_unit":
        return institutional_table_region_html(tokens, snapshot)
    if treatment == "live_fiat_coverage":
        return live_fiat_table_region_html(tokens, snapshot)
    if treatment == "historical":
        return historical_table_region_html(tokens, snapshot)
    amounts = profile.get("static_amounts") or DEFAULT_STATIC_AMOUNTS
    sr = static_pair_rate(F, T, snapshot)
    if sr is None:
        body = f'            <tr><td colspan="2">No conversion table: no reference rate is available for {esc(F)} → {esc(T)}.</td></tr>'
        label = f"{F} to {T} conversion table (no reference rate available)"
        foot = ""
    else:
        sig = sr["sig"]
        body = "\n".join(
            f'            <tr data-amount="{a}"><td>{format_amount(a)} {esc(F)}</td><td>{format_rate_value(a * sr["rate"], sig)} {esc(T)}</td></tr>'
            for a in amounts
        )
        label = f"{F} to {T} conversion table, reference snapshot as of {sr['as_of']}"
        foot = f'\n      <p class="result-info" id="table-source" style="padding:.7rem 1rem">Reference snapshot as of {esc(sr["as_of"])} · source: {esc(sr["source"])}</p>'
    return f"""{STATIC_TABLE_START}
    <div class="card" style="padding:0;overflow:hidden">
      <div class="table-wrap">
        <table aria-label="{esc(label)}">
          <thead>
            <tr>
              <th scope="col">{esc(F)}</th>
              <th scope="col">{esc(T)}</th>
            </tr>
          </thead>
          <tbody id="conv-table">
{body}
          </tbody>
        </table>
      </div>{foot}
    </div>
{STATIC_TABLE_END}"""


def rate_script_region_html(from_code: Optional[str] = None, to_code: Optional[str] = None,
                            snapshot: Optional[Dict[str, Any]] = None) -> str:
    """Rate script tag. Historical/legacy pairs get NO script: their values must
    never enter the live/snapshot converter lifecycle (SEO-A4.2)."""
    if from_code and to_code and pair_rate_treatment(from_code, to_code, snapshot) in SPECIAL_TREATMENTS:
        return f"{RATE_SCRIPT_START}\n{RATE_SCRIPT_END}"
    if from_code and to_code and pair_rate_treatment(from_code, to_code, snapshot) == "rate_regime_governed" \
            and rate_regime_pair(from_code, to_code, snapshot)["mode"] != "converter":
        return f"{RATE_SCRIPT_START}\n{RATE_SCRIPT_END}"   # SEO-A4.6B: no runtime without a converter
    return f'{RATE_SCRIPT_START}\n<script src="{RATE_SCRIPT_SRC}" defer></script>\n{RATE_SCRIPT_END}'


def _replace_region(page: str, start: str, end: str, new: str,
                    legacy_start: str, legacy_end: str, legacy_end_inclusive: bool, label: str) -> str:
    """Replace one marked region; migrate a legacy page exactly once. Fail closed."""
    ns, ne = page.count(start), page.count(end)
    if ns or ne:
        if ns != 1 or ne != 1:
            raise ValueError(f"{label}: markers found {ns}/{ne} times (need exactly 1/1)")
        i = page.index(start)
        j = page.index(end) + len(end)
        if j <= i:
            raise ValueError(f"{label}: markers out of order")
        return page[:i] + new + page[j:]
    ls, le = page.count(legacy_start), page.count(legacy_end)
    if ls != 1 or le != 1:
        raise ValueError(f"{label}: no markers and legacy layout not found exactly once ({ls}/{le})")
    i = page.index(legacy_start)
    j = page.index(legacy_end)
    if legacy_end_inclusive:
        j += len(legacy_end)
    if j <= i:
        raise ValueError(f"{label}: legacy anchors out of order")
    return page[:i] + new + page[j:]


def replace_static_rate_regions(page: str, profile: Dict[str, Any], tokens: Dict[str, str],
                                snapshot: Dict[str, Any]) -> str:
    page = _replace_region(page, STATIC_RATE_START, STATIC_RATE_END,
                           static_rate_region_html(profile, tokens, snapshot),
                           _LEGACY_RATE_START, _LEGACY_RATE_END, False, "STATIC-RATE")
    page = _replace_region(page, STATIC_TABLE_START, STATIC_TABLE_END,
                           static_table_region_html(profile, tokens, snapshot),
                           _LEGACY_TABLE_START, _LEGACY_TABLE_END, False, "STATIC-RATE-TABLE")
    page = _replace_region(page, RATE_SCRIPT_START, RATE_SCRIPT_END,
                           rate_script_region_html(tokens["FROM_CODE"], tokens["TO_CODE"], snapshot),
                           _LEGACY_SCRIPT_START, _LEGACY_SCRIPT_END, True, "RATE-SCRIPT")
    return page


# ---- SEO-A4.2: historical & legacy instruments ------------------------------
#
# Treatment is decided ONLY by the A4.1 policy layer (instrument_policy.py):
# a pair whose most restrictive converter behaviour is "archival_only" (a
# historical_currency or legacy_transition side, not overridden by XTS/XXX) is
# rendered as a historical reference. Such pages never carry a LIVE/SNAPSHOT
# state, a data-rate, the pair-rate.js runtime or a current-rate table. Only
# registry-cited facts from instrument_policy.historical_view() are rendered.
# Value types: historical_fixed_conversion | redenomination | fixed_legal_parity
# (successor pair with a verified fixed relationship) or archival_unavailable.
# Decision A4.2: no successor-derived present-day values (see docs).

_POLICY_LAYER = None


def instrument_policy_layer():
    global _POLICY_LAYER
    if _POLICY_LAYER is None:
        import instrument_policy
        _POLICY_LAYER = instrument_policy.InstrumentPolicy()
    return _POLICY_LAYER


def pair_semantic_treatment(from_code: str, to_code: str, snapshot: Optional[Dict[str, Any]] = None) -> str:
    """SEO-A4.3 semantic-treatment router — the single decision point.

    'standards_special'      a side is an ISO 4217 test/no-currency code (converter behaviour none)
    'historical'             a side is historical/legacy (archival_only), unless the above governs
    'precious_metal'         a side is a precious metal (XAU/XAG/XPT/XPD), unless the above govern
    'institutional_unit'     a side is an institutional unit (XDR/CLF/UYW/XUA/XSU), unless the above govern
                             (SEO-A4.5; a provider FX value for the unit never makes the pair ordinary FX)
    'live_fiat_coverage'     a side is an active fiat code the FX provider does not publish and that
                             data/live_fiat_reference_snapshot.json governs (SEO-A4.6A: KPW, VED), unless
                             the above govern; the scope rule bars any code that has a provider value
    'rate_regime_governed'   a side is a provider-valued live fiat code whose rate regime is governed by
                             rate_regime_governance in the same snapshot (SEO-A4.6B: CUP, IRR, MMK, SYP,
                             TMT, VES), unless the above govern; the provider value is kept, its use is
                             decided by the effective provider policy (converter / comparison / none)
    'ordinary_fx'            snapshot-covered pair rendered by the A3 rate logic
    'unsupported_specialized' no rate source yet (metals, units, restricted fiat, …)
    Policy (instrument_policy.resolve_pair) decides first; snapshot coverage only
    distinguishes the last two.
    """
    behaviour = instrument_policy_layer().resolve_pair(from_code, to_code)["converter_behavior"]
    if behaviour == "none":
        return "standards_special"
    if behaviour == "archival_only":
        return "historical"
    pol = instrument_policy_layer()
    if pol.is_precious_metal(from_code) or pol.is_precious_metal(to_code):
        return "precious_metal"
    if pol.is_institutional_unit(from_code) or pol.is_institutional_unit(to_code):
        return "institutional_unit"
    if is_live_fiat(from_code) or is_live_fiat(to_code):
        return "live_fiat_coverage"
    if is_rate_regime_governed(from_code) or is_rate_regime_governed(to_code):
        return "rate_regime_governed"
    snapshot = snapshot if snapshot is not None else load_rate_snapshot()
    return "ordinary_fx" if static_pair_rate(from_code, to_code, snapshot) is not None else "unsupported_specialized"


_RATE_TREATMENT = {"ordinary_fx": "snapshot", "unsupported_specialized": "unsupported",
                   "historical": "historical", "standards_special": "standards_special",
                   "precious_metal": "precious_metal", "institutional_unit": "institutional_unit",
                   "live_fiat_coverage": "live_fiat_coverage", "rate_regime_governed": "rate_regime_governed"}


def pair_rate_treatment(from_code: str, to_code: str, snapshot: Optional[Dict[str, Any]] = None) -> str:
    """'snapshot' | 'unsupported' | 'historical' | 'standards_special' (derived from the router)."""
    return _RATE_TREATMENT[pair_semantic_treatment(from_code, to_code, snapshot)]


SPECIAL_TREATMENTS = ("historical", "standards_special", "precious_metal", "institutional_unit", "live_fiat_coverage")


HISTORICAL_VALUE_LABELS = {
    "historical_fixed_conversion": ("FIXED CONVERSION", "Historical fixed conversion — not a current market rate"),
    "redenomination": ("REDENOMINATION", "Redenomination ratio — not a market rate"),
    "fixed_legal_parity": ("FIXED PARITY", "Fixed official parity — not a floating market quote"),
}


def _historical_sides(F: str, T: str) -> List[Dict[str, Any]]:
    pol = instrument_policy_layer()
    return [pol.historical_view(c) for c in (F, T) if pol.is_historical(c)]


def _pair_fixed_conversion(F: str, T: str) -> Optional[Dict[str, Any]]:
    """The verified fixed relationship when the pair is (historical code, its successor)."""
    for hv in _historical_sides(F, T):
        other = T if hv["code"] == F else F
        if hv["successor_code"] == other and hv["fixed_conversion"]:
            return hv["fixed_conversion"]
    return None


def _status_phrase(hv: Dict[str, Any]) -> str:
    bits = [hv["instrument_status"]]
    bits.append({"legal_tender": "de jure legal tender", "not_legal_tender": "no longer legal tender",
                 "unknown": "legal-tender end date not verified"}.get(hv["legal_tender_status"], ""))
    if hv["circulation_status"] == "not_circulating":
        bits.append("not in circulation")
    return " · ".join(b for b in bits if b)


def _source_links(sources: List[Dict[str, str]]) -> str:
    return ", ".join(f'<a href="{esc(s["url"])}">{esc(s["authority"])}</a>' for s in sources)


def provider_observation(code: str, snapshot: Dict[str, Any]) -> Optional[str]:
    """Provenance sentence when the rate provider still publishes a value for a
    historical/legacy code. The value itself is never rendered."""
    rates = snapshot["rates"]
    if code not in rates:
        return None
    hv = instrument_policy_layer().historical_view(code)
    succ = hv["successor_code"]
    note = f"The rate provider still publishes a value under the {code} code"
    fc = hv["fixed_conversion"]
    v = float(rates[code])
    explained = False
    if fc and succ in rates:
        # code units per 1 successor, from the verified fixed conversion
        bu, qu = float(fc["base_units"].replace(",", "")), float(fc["quote_units"].replace(",", ""))
        per_succ = qu / bu if fc["base_code"] == succ else bu / qu
        expected = float(rates[succ]) * per_succ
        if abs(v - expected) <= 0.005 * expected:  # within the source's ~3-significant-digit precision
            note += f" that matches the verified fixed conversion applied to the {succ} rate, i.e. it is derived from {succ} rather than from an independent {code} market"
            explained = True
    if not explained and succ in rates and v == float(rates[succ]):
        note += f" that is identical to its {succ} value (an alias of the successor's pricing, with no verified one-to-one conversion behind it)"
    return note + f". ConvertCCY does not present it as a current {code} market rate."


def _side_block(hv: Dict[str, Any]) -> str:
    succ = hv["successor_code"]
    if succ and hv["successor_in_site"]:
        succ_html = f'<a href="{currency_hub_href(succ)}">{esc(succ)} — {esc(hv["successor_name"] or succ)}</a>'
    elif succ:
        succ_html = f"{esc(succ)} (not yet covered by ConvertCCY)"
    else:
        succ_html = "none recorded"
    lines = [f'<div class="pj-line">Status: {esc(_status_phrase(hv))}</div>',
             f'<div class="pj-line">Successor: {succ_html}</div>']
    fc = hv["fixed_conversion"]
    if fc:
        label = HISTORICAL_VALUE_LABELS[fc["kind"]][0].capitalize()
        lines.append(f'<div class="pj-line">{esc(label)}: <span data-value-type="{fc["kind"]}">{esc(fc["statement"])}</span>'
                     f' <span class="pj-muted">— {_source_links(fc["sources"])}</span></div>')
    for c in hv["claims"]:
        lines.append(f'<div class="pj-line"><span data-claim>{esc(c["text"])}</span>'
                     f' <span class="pj-muted">— {_source_links(c["sources"])}</span></div>')
    if hv["unverified_note"]:
        lines.append(f'<div class="pj-line pj-muted">{esc(hv["unverified_note"])}</div>')
    body = "\n          ".join(lines)
    return f"""
        <div class="pj-block pj-plain" data-historical-code="{esc(hv["code"])}">
          <div class="pj-head"><span class="pj-badge">{esc(hv["status_label"])}</span> {esc(hv["code"])} — {esc(hv["name"])}</div>
          {body}
        </div>"""


def _successor_pair_links(F: str, T: str) -> List[Tuple[str, str]]:
    pol = instrument_policy_layer()
    out = []
    for hv in _historical_sides(F, T):
        succ = hv["successor_code"]
        if not (succ and hv["successor_in_site"]):
            continue
        a, b = (succ, T) if hv["code"] == F else (F, succ)
        if a != b and not pol.is_historical(a) and not pol.is_historical(b) and (a, b) not in out:
            out.append((a, b))
    return out


def historical_rate_region_html(tokens: Dict[str, str], snapshot: Dict[str, Any]) -> str:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    sides = _historical_sides(F, T)
    fc = _pair_fixed_conversion(F, T)
    if fc:
        badge, sub = HISTORICAL_VALUE_LABELS[fc["kind"]]
        value_type = fc["kind"]
        main = f'<span data-value-type="{fc["kind"]}">{esc(fc["statement"])}</span>'
        note = (f'{esc(sub)}, published by {_source_links(fc["sources"])}. '
                f'It describes the fixed relationship between {esc(F)} and {esc(T)}; it is not a live or snapshot exchange rate.')
    else:
        badge = " / ".join(dict.fromkeys(hv["status_label"] for hv in sides))
        value_type = "archival_unavailable"
        main = "No current market rate"
        sub = "; ".join(f'{hv["code"]} is a {"historical currency" if hv["status_label"] == "HISTORICAL" else "legacy currency code"}'
                        + (f' (successor {hv["successor_code"]})' if hv["successor_code"] else "") for hv in sides)
        note = (f"ConvertCCY does not show a current {esc(F)}/{esc(T)} market rate because "
                + esc(" and ".join(hv["code"] for hv in sides))
                + (" is" if len(sides) == 1 else " are") + " no longer a current traded currency.")
    observations = [o for o in (provider_observation(hv["code"], snapshot) for hv in sides) if o]
    obs_html = "".join(f" {esc(o)}" for o in observations)
    links = _successor_pair_links(F, T)
    links_html = ""
    if links and not fc:
        links_html = '\n    <p class="result-info">Current values: ' + " · ".join(
            f'<a href="{pair_href(a, b)}">{esc(a)} → {esc(b)}</a>' for a, b in links) + "</p>"
    blocks = "".join(_side_block(hv) for hv in sides)
    return f"""{STATIC_RATE_START}
  <div class="rate-banner" id="rate-root" data-from="{esc(F)}" data-to="{esc(T)}" data-mode="historical" data-value-type="{value_type}">
    <div>
      <div class="rate-main" id="live-rate">{main}</div>
      <div class="rate-sub" id="rate-sub">{esc(sub)}</div>
    </div>
    <div class="rate-badge snap" id="rate-badge">{esc(badge)}</div>
  </div>
  <p class="rate-note" id="rate-source">{note}{obs_html}</p>

  <div class="card">
    <div class="card-title">Historical &amp; Legacy Currency Reference</div>
    <div class="pj-grid">{blocks}
    </div>{links_html}
  </div>
{STATIC_RATE_END}"""


def historical_table_region_html(tokens: Dict[str, str], snapshot: Dict[str, Any]) -> str:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    fc = _pair_fixed_conversion(F, T)
    codes = " and ".join(hv["code"] for hv in _historical_sides(F, T))
    extra = (f' The fixed relationship is <span data-value-type="{fc["kind"]}">{esc(fc["statement"])}</span>.' if fc else "")
    return f"""{STATIC_TABLE_START}
    <div class="card">
      <p class="result-info" id="table-source">No current-rate conversion table: {esc(codes)} {"is" if " and " not in codes else "are"} not a current traded currency.{extra}</p>
    </div>
{STATIC_TABLE_END}"""


def historical_faq_items(tokens: Dict[str, str], snapshot: Dict[str, Any]) -> List[Dict[str, str]]:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    hv = _historical_sides(F, T)[0]
    H, succ = hv["code"], hv["successor_code"]
    succ_label = f'{hv["successor_name"]} ({succ})' if hv["successor_name"] else succ
    items = []
    if hv["status_label"] == "HISTORICAL":
        a1 = f"No. {H} ({hv['name']}) is a withdrawn currency and is no longer legal tender."
    elif hv["legal_tender_status"] == "legal_tender":
        a1 = f"{H} ({hv['name']}) is a legacy currency code: it remains de jure legal tender but is not in circulation."
    else:
        a1 = f"{H} ({hv['name']}) is a legacy currency code that has been superseded and is not in circulation."
    if succ:
        a1 += f" Its successor is {succ_label}."
    if hv["unverified_note"] and hv["status_label"] == "LEGACY":
        a1 += " " + hv["unverified_note"]
    items.append({"q": f"Is {H} still a current currency?", "a": a1})
    if succ:
        a2 = f"{succ_label} is the successor of {H}."
        if hv["claims"]:
            a2 += " " + " ".join(c["text"] for c in hv["claims"])
        items.append({"q": f"What replaced {H}?", "a": a2})
    fc = hv["fixed_conversion"]
    if fc:
        q = {"historical_fixed_conversion": f"What was the fixed {H}/{succ} conversion?",
             "redenomination": f"What is the {H}/{succ} redenomination ratio?",
             "fixed_legal_parity": f"What is the fixed {H}/{succ} parity?"}[fc["kind"]]
        auth = ", ".join(s["authority"] for s in fc["sources"])
        items.append({"q": q, "a": f"{fc['statement']}, as published by {auth}. "
                                  f"{HISTORICAL_VALUE_LABELS[fc['kind']][1]}."})
    obs = provider_observation(H, snapshot)
    a4 = (f"{H} is {'a withdrawn' if hv['status_label'] == 'HISTORICAL' else 'a superseded'} currency, so ConvertCCY "
          f"does not treat it as a current traded currency or show a live or snapshot {F}/{T} rate.")
    if obs:
        a4 += " " + obs
    items.append({"q": f"Why does ConvertCCY not show a live {F}/{T} market rate?", "a": a4})
    return items


# ---- SEO-A4.2.1: historical metadata & page semantics -------------------------
#
# ONE resolver (pair_metadata) feeds <title>, meta description, og/twitter
# copies and the WebPage JSON-LD name/description. Ordinary pairs get the
# pre-existing strings byte-for-byte. Historical pairs get wording derived from
# the same semantic state as the visible page (value type + historical sides).
# apply_historical_semantics() is the single body/head rewrite used by both the
# full build and `--historical-instruments-only`.

HISTORICAL_TITLE_SUFFIX = {
    "historical_fixed_conversion": "Historical Fixed Conversion",
    "redenomination": "Redenomination Reference",
    "fixed_legal_parity": "Fixed Parity Reference",
}
HISTORICAL_OVERVIEW_HEADING = {
    "historical_fixed_conversion": "Historical Reference",
    "redenomination": "Redenomination Reference",
    "fixed_legal_parity": "Fixed Parity Reference",
}
HISTORICAL_TABLE_HEADING = {
    "historical_fixed_conversion": "Historical Fixed Conversion",
    "redenomination": "Redenomination",
    "fixed_legal_parity": "Fixed Parity",
    "archival_unavailable": "Historical Conversion Status",
}
HISTORICAL_RELATION_NOUN = {
    "historical_fixed_conversion": "verified fixed conversion",
    "redenomination": "verified redenomination ratio",
    "fixed_legal_parity": "verified fixed parity",
}


def historical_semantic_state(tokens: Dict[str, str]) -> Dict[str, Any]:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    sides = _historical_sides(F, T)
    fc = _pair_fixed_conversion(F, T)
    value_type = fc["kind"] if fc else "archival_unavailable"
    status_word = "Historical" if any(hv["status_label"] == "HISTORICAL" for hv in sides) else "Legacy"
    return {"sides": sides, "fixed": fc, "value_type": value_type, "status_word": status_word}


def pair_metadata(tokens: Dict[str, str], archival: Any = False, brand: str = SITE_NAME) -> Dict[str, str]:
    """Single source for title / description / WebPage schema name & description."""
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    if archival == "standards_special":
        return standards_pair_metadata(tokens, brand)
    if archival == "precious_metal":
        return metal_pair_metadata(tokens, brand)
    if archival == "institutional_unit":
        return institutional_pair_metadata(tokens, brand)
    if archival == "live_fiat_coverage":
        return live_fiat_pair_metadata(tokens, brand)
    if archival == "rate_regime_governed":
        return rate_regime_pair_metadata(tokens, brand)
    if not archival:
        return {
            "title": f"{F} to {T} Converter | {brand}",
            "description": f'Convert {tokens["FROM_NAME"]} to {tokens["TO_NAME"]} with a clear reference exchange-rate page, conversion table, FAQ, and currency context.',
            "schema_name": f"{F} to {T} Converter | {SITE_NAME}",
            "schema_description": f'Convert {tokens["FROM_NAME"]} to {tokens["TO_NAME"]} using a clear reference exchange-rate page.',
        }
    st = historical_semantic_state(tokens)
    vt, fc, sides = st["value_type"], st["fixed"], st["sides"]
    pair_names = f'{tokens["FROM_NAME"]} ({F}) and {tokens["TO_NAME"]} ({T})'
    if fc:
        title = f"{F} to {T} {HISTORICAL_TITLE_SUFFIX[vt]} | {brand}"
        description = (f"{st['status_word']} reference for {pair_names}, including the "
                       f"{HISTORICAL_RELATION_NOUN[vt]} {fc['statement']} and its official source. "
                       f"No current market rate is presented.")
    else:
        title = f"{F} to {T} {st['status_word']} Currency Reference | {brand}"
        hist = " or ".join(hv["code"] for hv in sides)
        description = (f"{st['status_word']} reference for {tokens['FROM_NAME']} ({F}) against {tokens['TO_NAME']} ({T}), "
                       f"including successor information, verified transition facts and source provenance. "
                       f"No current {hist} market rate is presented.")
    return {"title": title, "description": description, "schema_name": title, "schema_description": description}


def _historical_side_sentence(hv: Dict[str, Any]) -> str:
    succ = hv["successor_code"]
    succ_label = f'{hv["successor_name"]} ({succ})' if hv["successor_name"] else succ
    if hv["status_label"] == "HISTORICAL":
        s = f"{hv['name']} ({hv['code']}) is a withdrawn currency and is no longer legal tender."
    elif hv["legal_tender_status"] == "legal_tender":
        s = f"{hv['name']} ({hv['code']}) is a legacy currency code: it remains de jure legal tender but is not in circulation."
    else:
        s = f"{hv['name']} ({hv['code']}) is a legacy currency code that has been superseded and is not in circulation."
    if succ:
        s += f" Its successor is {succ_label}."
    return s


def historical_overview_html(tokens: Dict[str, str]) -> str:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    st = historical_semantic_state(tokens)
    vt, fc = st["value_type"], st["fixed"]
    heading = HISTORICAL_OVERVIEW_HEADING.get(vt, f"{st['status_word']} Currency Reference")
    paras = [esc(_historical_side_sentence(hv)) for hv in st["sides"]]
    if fc:
        paras.append(f'The {esc(HISTORICAL_RELATION_NOUN[vt])} between {esc(F)} and {esc(T)} is '
                     f'<span data-value-type="{vt}">{esc(fc["statement"])}</span>. It records how the units relate; '
                     f'it is not a current market rate.')
    else:
        paras.append(f"No verified fixed relationship links {esc(F)} and {esc(T)} directly, so ConvertCCY does not "
                     f"present a current {esc(F)}/{esc(T)} value.")
    paras.append("This page is a reference for status, successor relationship and source provenance; the official "
                 "sources are cited in the reference card above.")
    body = "\n".join(f"    <p>{p}</p>" for p in paras)
    return f"""  <section class="section">
    <div class="sec-title">Pair Overview</div>
    <div class="sec-h2">{esc(F)} / {esc(T)} {esc(heading)}</div>
{body}
  </section>"""


HISTORICAL_EDUCATION_HTML = """  <section class="section">
    <div class="sec-title">Reading a Historical Currency Reference</div>
    <div class="card">
      <p>A withdrawn or superseded currency has no current market rate. Where an official fixed conversion, redenomination ratio or parity exists, ConvertCCY shows it with its source: it describes how the old unit relates to its successor, not what the old unit trades for today.</p>
      <p>For current values, use the pairs of the successor currency.</p>
    </div>
  </section>
"""

_META_PATTERNS = (
    (re.compile(r"<title>[^<]*</title>"), "<title>{title}</title>"),
    (re.compile(r'<meta name="description" content="[^"]*">'), '<meta name="description" content="{description}">'),
    (re.compile(r'<meta property="og:title" content="[^"]*">'), '<meta property="og:title" content="{title}">'),
    (re.compile(r'<meta property="og:description" content="[^"]*">'), '<meta property="og:description" content="{description}">'),
    (re.compile(r'<meta name="twitter:title" content="[^"]*">'), '<meta name="twitter:title" content="{title}">'),
    (re.compile(r'<meta name="twitter:description" content="[^"]*">'), '<meta name="twitter:description" content="{description}">'),
)
_SUBTITLE_RE = re.compile(r'<p class="pair-subtitle">[^<]*</p>')
_MACRO_RE = re.compile(r'\n    <p class="pj-macro">[^<]*</p>')
_OVERVIEW_START = '  <section class="section">\n    <div class="sec-title">Pair Overview</div>'
_PASSAGE_START = '<section class="section pj-section">'


def apply_historical_semantics(page: str, tokens: Dict[str, str], content: Dict[str, Any]) -> str:
    """Rewrite historical metadata and page semantics. Idempotent; fails closed."""
    brand = content.get("site_copy", {}).get("brand_name", SITE_NAME)
    meta = pair_metadata(tokens, True, brand)
    st = historical_semantic_state(tokens)
    for rx, tpl in _META_PATTERNS:
        if len(rx.findall(page)) != 1:
            raise ValueError(f"historical metadata: {rx.pattern} not found exactly once")
        page = rx.sub(lambda _m: tpl.format(title=esc(meta["title"]), description=esc(meta["description"])), page)
    if len(_SUBTITLE_RE.findall(page)) != 1:
        raise ValueError("historical subtitle anchor not found exactly once")
    page = _SUBTITLE_RE.sub(lambda _m: f'<p class="pair-subtitle">{esc(st["status_word"])} currency reference</p>', page)
    if page.count(_OVERVIEW_START) != 1 or page.count(_PASSAGE_START) != 1 or page.count(STATIC_TABLE_START) != 1:
        raise ValueError("historical body anchors not found exactly once")
    i = page.index(_OVERVIEW_START)
    j = page.index("\n  </section>", i) + len("\n  </section>")
    page = page[:i] + historical_overview_html(tokens) + page[j:]
    page = _MACRO_RE.sub("", page)   # market-context line; the rest of the passage section is untouched
    p = page.index(_PASSAGE_START)
    edu_start = page.index("\n  </section>", p) + len("\n  </section>")
    table_start = page.rindex('\n  <section class="section">\n', 0, page.index(STATIC_TABLE_START))
    page = page[:edu_start] + "\n" + HISTORICAL_EDUCATION_HTML + page[table_start:]
    t0 = page.rindex('\n  <section class="section">\n', 0, page.index(STATIC_TABLE_START)) + 1
    t1 = page.index(STATIC_TABLE_START)
    heading = HISTORICAL_TABLE_HEADING[st["value_type"]]
    page = page[:t0] + f'  <section class="section">\n    <div class="sec-title">{esc(heading)}</div>\n' + page[t1:]
    return page


# ---- SEO-A4.3: ISO 4217 standards-special codes (XTS, XXX) -------------------
#
# Pairs whose policy converter behaviour is "none" (instrument types test_code /
# no_currency) are contextual standards references: no rate, no converter, no
# rate runtime, no WebApplication. Robots follow the deployed policy value
# (noindex_follow_consolidated_reference -> "noindex,follow"); canonical stays
# self-referential; URLs are kept (no redirects). The /currencies/<code>.html
# hub is the authoritative, indexable reference. Facts come only from
# instrument_policy.standards_view() (registry-cited); wording varies by
# instrument type, never by code name.

ROBOTS_BY_PAIR_INDEXABILITY = {"noindex_follow_consolidated_reference": "noindex,follow"}
INDEXABLE_ROBOTS = "index,follow,max-image-preview:large"

STANDARDS_FAQ = {
    "test_code": [
        ("Is {S} a real currency?", "No. In the ISO 4217 code list maintained by SIX, {S} is listed as “{designation}”. {not_this}"),
        ("What is {S} used for?", "{why_exists} {implementation}"),
        ("Does {S} have an exchange rate?", "{no_rate}"),
    ],
    "no_currency": [
        ("Is {S} a currency?", "No. In the ISO 4217 code list maintained by SIX, {S} is listed as “{designation}”. {not_this}"),
        ("What does {S} mean in ISO 4217?", "{what} {implementation}"),
        ("Can {S} be converted into another currency?", "{no_rate}"),
    ],
}


def _standards_sides(F: str, T: str) -> List[Dict[str, Any]]:
    pol = instrument_policy_layer()
    return [pol.standards_view(c) for c in (F, T) if pol.is_standards_special(c)]


def _standards_role(sides: List[Dict[str, Any]]) -> str:
    return sides[0]["title_role"] if len(sides) == 1 else "ISO 4217 Special Codes Reference"


def standards_pair_metadata(tokens: Dict[str, str], brand: str = SITE_NAME) -> Dict[str, str]:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    sides = _standards_sides(F, T)
    title = f"{F} / {T} — {_standards_role(sides)} | {brand}"
    reasons = " and ".join(f'{sv["code"]} is the {sv["code_role"]} (“{sv["iso_designation"]["text"]}”)' for sv in sides)
    description = (f"Reference explaining why {F}/{T} has no exchange rate: {reasons}, not a currency. "
                   f"See the {' and '.join(sv['code'] for sv in sides)} standards reference.")
    return {"title": title, "description": description, "schema_name": title, "schema_description": description}


def _standards_block(sv: Dict[str, Any]) -> str:
    links = ", ".join(f'<a href="{esc(s["url"])}">{esc(s["authority"])}</a>' for s in sv["iso_designation"]["sources"])
    lines = [f'<div class="pj-line">ISO 4217 designation: <span data-claim>{esc(sv["iso_designation"]["text"])}</span>'
             f' <span class="pj-muted">— {links}</span></div>']
    for c in sv["claims"]:
        lines.append(f'<div class="pj-line"><span data-claim>{esc(c["text"])}</span> <span class="pj-muted">— '
                     + ", ".join(f'<a href="{esc(s["url"])}">{esc(s["authority"])}</a>' for s in c["sources"]) + "</span></div>")
    lines.append(f'<div class="pj-line">{esc(sv["explanations"]["no_rate"])}</div>')
    lines.append(f'<div class="pj-line">Authoritative reference: <a href="{currency_hub_href(sv["code"])}">'
                 f'{esc(sv["code"])} standards reference →</a></div>')
    body = "\n          ".join(lines)
    return f"""
        <div class="pj-block pj-plain" data-standards-code="{esc(sv["code"])}">
          <div class="pj-head"><span class="pj-badge">{esc(sv["badge"])}</span> {esc(sv["code"])} — {esc(sv["name"])}</div>
          {body}
        </div>"""


def standards_rate_region_html(tokens: Dict[str, str]) -> str:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    sides = _standards_sides(F, T)
    badge = " / ".join(sv["badge"] for sv in sides)
    sub = "; ".join(f'{sv["code"]} is the {sv["code_role"]} — not a currency' for sv in sides)
    hubs = " and ".join(f'<a href="{currency_hub_href(sv["code"])}">{esc(sv["code"])} standards reference</a>' for sv in sides)
    return f"""{STATIC_RATE_START}
  <div class="rate-banner" id="rate-root" data-from="{esc(F)}" data-to="{esc(T)}" data-mode="standards" data-value-type="no_exchange_relationship">
    <div>
      <div class="rate-main" id="live-rate">No exchange-rate relationship</div>
      <div class="rate-sub" id="rate-sub">{esc(sub)}</div>
    </div>
    <div class="rate-badge snap" id="rate-badge">{esc(badge)}</div>
  </div>
  <p class="rate-note" id="rate-source">{esc(F)} / {esc(T)} is not a valid exchange-rate relationship, so ConvertCCY shows no rate and offers no conversion. Authoritative explanation: {hubs}.</p>

  <div class="card">
    <div class="card-title">ISO 4217 Standards Reference</div>
    <div class="pj-grid">{"".join(_standards_block(sv) for sv in sides)}
    </div>
  </div>
{STATIC_RATE_END}"""


def standards_table_region_html(tokens: Dict[str, str]) -> str:
    sides = _standards_sides(tokens["FROM_CODE"], tokens["TO_CODE"])
    why = " ".join(sv["explanations"]["no_rate"] for sv in sides)
    return f"""{STATIC_TABLE_START}
    <div class="card">
      <p class="result-info" id="table-source">No conversion table: {esc(why)}</p>
    </div>
{STATIC_TABLE_END}"""


def _standards_faq_core(sv: Dict[str, Any]) -> List[Dict[str, str]]:
    ex = sv["explanations"]
    fill = {"S": sv["code"], "designation": sv["iso_designation"]["text"], **ex}
    return [{"q": q.format(**fill), "a": a.format(**fill)} for q, a in STANDARDS_FAQ[sv["instrument_type"]]]


def standards_faq_items(tokens: Dict[str, str]) -> List[Dict[str, str]]:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    sv = _standards_sides(F, T)[0]
    items = _standards_faq_core(sv)
    items.append({"q": f"Why does this {F}/{T} page exist?",
                  "a": (f"ConvertCCY covers every code in its ISO 4217 set, so a {F}/{T} page exists for completeness. "
                        f"It is a contextual reference only and is not indexed; the authoritative explanation is the "
                        f"{sv['code']} standards reference.")})
    return items


def standards_overview_html(tokens: Dict[str, str]) -> str:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    pol = instrument_policy_layer()
    sides = _standards_sides(F, T)
    paras = [f'{esc(sv["code"])} ({esc(sv["name"])}) is the {esc(sv["code_role"])}: {esc(sv["explanations"]["what"])}'
             for sv in sides]
    for other in (F, T):
        if not pol.is_standards_special(other):
            paras.append(f'{esc(other)} ({esc(pol.resolve(other)["name"])}) is a separate code; see its '
                         f'<a href="{currency_hub_href(other)}">{esc(other)} reference</a> for its own pairs.')
    paras.append(f"This page is a contextual reference: the {' and '.join(esc(sv['code']) for sv in sides)} "
                 f"standards reference is authoritative, and this page is not indexed.")
    body = "\n".join(f"    <p>{p}</p>" for p in paras)
    return f"""  <section class="section">
    <div class="sec-title">Pair Overview</div>
    <div class="sec-h2">{esc(F)} / {esc(T)} Standards Reference</div>
{body}
  </section>"""


STANDARDS_EDUCATION_HTML = """  <section class="section">
    <div class="sec-title">Reading an ISO 4217 Special Code</div>
    <div class="card">
      <p>ISO 4217 includes a few codes that are not currencies. A testing code and a no-currency code are standards markers: they denote no money, so no exchange rate, conversion or market price exists for them.</p>
      <p>The authoritative explanation of each code is on its standards reference page.</p>
    </div>
  </section>
"""

_ROBOTS_RE = re.compile(r'<meta name="robots" content="[^"]*">')
_H1_RE = re.compile(r"(?s)<h1>.*?</h1>")


def pair_robots(from_code: str, to_code: str) -> str:
    return ROBOTS_BY_PAIR_INDEXABILITY.get(instrument_policy_layer().resolve_pair(from_code, to_code)["pair_indexability"],
                                           INDEXABLE_ROBOTS)


def apply_standards_semantics(page: str, tokens: Dict[str, str], content: Dict[str, Any]) -> str:
    """Rewrite standards-special pair metadata, robots and page semantics. Idempotent; fails closed."""
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    brand = content.get("site_copy", {}).get("brand_name", SITE_NAME)
    meta = standards_pair_metadata(tokens, brand)
    sides = _standards_sides(F, T)
    for rx, tpl in _META_PATTERNS:
        if len(rx.findall(page)) != 1:
            raise ValueError(f"standards metadata: {rx.pattern} not found exactly once")
        page = rx.sub(lambda _m: tpl.format(title=esc(meta["title"]), description=esc(meta["description"])), page)
    for rx, new, label in ((_ROBOTS_RE, f'<meta name="robots" content="{pair_robots(F, T)}">', "robots"),
                           (_H1_RE, f"<h1>{esc(F)} / {esc(T)} <em>{esc(_standards_role(sides))}</em></h1>", "h1"),
                           (_SUBTITLE_RE, '<p class="pair-subtitle">ISO 4217 standards reference</p>', "subtitle")):
        if len(rx.findall(page)) != 1:
            raise ValueError(f"standards {label} anchor not found exactly once")
        page = rx.sub(lambda _m, v=new: v, page)
    if page.count(_OVERVIEW_START) != 1 or page.count(_PASSAGE_START) != 1 or page.count(STATIC_TABLE_START) != 1:
        raise ValueError("standards body anchors not found exactly once")
    i = page.index(_OVERVIEW_START)
    j = page.index("\n  </section>", i) + len("\n  </section>")
    page = page[:i] + standards_overview_html(tokens) + page[j:]
    page = _MACRO_RE.sub("", page)
    p = page.index(_PASSAGE_START)
    edu_start = page.index("\n  </section>", p) + len("\n  </section>")
    table_start = page.rindex('\n  <section class="section">\n', 0, page.index(STATIC_TABLE_START))
    page = page[:edu_start] + "\n" + STANDARDS_EDUCATION_HTML + page[table_start:]
    t0 = page.rindex('\n  <section class="section">\n', 0, page.index(STATIC_TABLE_START)) + 1
    t1 = page.index(STATIC_TABLE_START)
    page = page[:t0] + '  <section class="section">\n    <div class="sec-title">Conversion Status</div>\n' + page[t1:]
    items = standards_faq_items(tokens)
    page = replace_faq_regions(page, items)
    return replace_webpage_jsonld(page, tokens, items, "standards_special")


# ---- SEO-A4.4: precious metals (XAU, XAG, XPT, XPD) ---------------------------
#
# Pairs with a precious-metal side (unless standards/historical govern) are metal
# valuation references, never ordinary FX converters. Facts come only from
# instrument_policy.metal_view() (registry-cited). Any numeric value comes only
# from metal_reference.value_view(), which reads data/metal_reference_snapshot.json
# and refuses unless licence, provenance, timestamp, freshness and skew rules pass.
# Current state: reference_layer_only -> every value is "unavailable".

_METAL_SNAPSHOT = None


def metal_snapshot() -> Dict[str, Any]:
    global _METAL_SNAPSHOT
    if _METAL_SNAPSHOT is None:
        import metal_reference
        _METAL_SNAPSHOT = metal_reference.load_metal_snapshot()
    return _METAL_SNAPSHOT


def _metal_sides(F: str, T: str) -> List[Dict[str, Any]]:
    pol = instrument_policy_layer()
    return [pol.metal_view(c) for c in (F, T) if pol.is_precious_metal(c)]


def metal_value(F: str, T: str, fx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    import metal_reference
    fx = fx if fx is not None else load_rate_snapshot()
    return metal_reference.value_view(F, T, metal_snapshot(), fx, format_rate_value)


METAL_VALUE_BADGE = {"benchmark_reference": "BENCHMARK", "market_reference": "MARKET REFERENCE",
                     "derived_cross_value": "DERIVED", "derived_inverse": "DERIVED", "derived_metal_ratio": "DERIVED"}


def _metal_pair_shape(F: str, T: str) -> str:
    sides = _metal_sides(F, T)
    return "ratio" if len(sides) == 2 else ("metal_from" if sides[0]["code"] == F else "metal_to")


def _cur_name(code: str) -> str:
    return instrument_policy_layer().resolve(code)["name"]


def metal_pair_metadata(tokens: Dict[str, str], brand: str = SITE_NAME, fx: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    sides = _metal_sides(F, T)
    shape = _metal_pair_shape(F, T)
    active = metal_value(F, T, fx)["value_type"] != "unavailable"
    if shape == "ratio":
        a, b = sides[0]["metal_name"], sides[1]["metal_name"]
        title = f"{F} / {T} {a}-{b} Ratio Reference | {brand}"
        description = (f"Reference for the {a.lower()}-to-{b.lower()} relative value: ISO 4217 identity of both metals, "
                       f"ratio methodology and pricing status. "
                       + ("A derived ratio is shown with its sources and timestamps." if active else "No ratio is currently published."))
    else:
        m = sides[0]
        role = "Reference Price" if active else "Valuation Reference"
        title = f"{F} to {T} {m['metal_name']} {role} | {brand}"
        if shape == "metal_from":
            subject = f"the value of {m['metal_name'].lower()} ({F}) in {_cur_name(T)} ({T})"
        else:
            subject = f"the value of {_cur_name(F)} ({F}) expressed in {m['metal_name'].lower()} ({T})"
        description = (f"Reference for {subject}: ISO 4217 identity, unit convention, pricing provenance and licensing status. "
                       + ("Values are labelled with source, timestamp and direct or derived type."
                          if active else f"No licensed {m['metal_name'].lower()} price is currently published."))
    return {"title": title, "description": description, "schema_name": title, "schema_description": description}


def _metal_h1(F: str, T: str) -> Tuple[str, str]:
    sides = _metal_sides(F, T)
    shape = _metal_pair_shape(F, T)
    if shape == "ratio":
        return f"{sides[0]['metal_name']} / {sides[1]['metal_name']}", "Relative Value Reference"
    if shape == "metal_from":
        return f"{sides[0]['metal_name']} ({F}) Valuation in", f"{_cur_name(T)} ({T})"
    return f"{_cur_name(F)} ({F}) Valuation in", f"{sides[0]['metal_name']} ({T})"


def _cited_line(claim: Dict[str, Any], prefix: str = "") -> str:
    links = ", ".join(f'<a href="{esc(s["url"])}">{esc(s["authority"])}</a>' for s in claim["sources"])
    return (f'<div class="pj-line">{esc(prefix)}<span data-claim>{esc(claim["text"])}</span>'
            f' <span class="pj-muted">— {links}</span></div>')


def _metal_block(mv: Dict[str, Any]) -> str:
    lines = [_cited_line(mv["iso_designation"], "ISO 4217 designation: ")]
    lines += [_cited_line(c) for c in mv["claims"]]
    lines.append(f'<div class="pj-line">Unit: {esc(mv["unit_convention"])}</div>')
    lines.append(_cited_line(mv["troy_ounce_definition"]))
    lines.append(f'<div class="pj-line">Pricing: {esc(mv["pricing_reason"])}</div>')
    lines += [_cited_line(c) for c in mv["licensing_claims"]]
    lines.append(f'<div class="pj-line">Authoritative reference: <a href="{currency_hub_href(mv["code"])}">'
                 f'{esc(mv["code"])} — {esc(mv["metal_name"])} reference →</a></div>')
    body = "\n          ".join(lines)
    return f"""
        <div class="pj-block pj-plain" data-metal-code="{esc(mv["code"])}">
          <div class="pj-head"><span class="pj-badge">PRECIOUS METAL</span> {esc(mv["code"])} — {esc(mv["metal_name"])}</div>
          {body}
        </div>"""


def _other_side_note(F: str, T: str) -> str:
    pol = instrument_policy_layer()
    for c in (F, T):
        if not pol.is_precious_metal(c) and pol.resolve(c)["converter_behavior"] == "valuation_only":
            return (f" {c} is an institutional unit whose valuation source is not activated, so no {F}/{T} value "
                    f"can be derived until both sides have governed sources.")
    return ""


def metal_rate_region_html(tokens: Dict[str, str], fx: Optional[Dict[str, Any]] = None) -> str:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    sides = _metal_sides(F, T)
    v = metal_value(F, T, fx)
    vt = v["value_type"]
    hubs = " and ".join(f'<a href="{currency_hub_href(m["code"])}">{esc(m["code"])} reference</a>' for m in sides)
    sub = "; ".join(f'{m["code"]} is the ISO 4217 code for {m["metal_name"].lower()} — a metal, not a currency' for m in sides)
    if vt == "unavailable":
        main = "Reference pricing source not yet activated"
        badge = "METAL REFERENCE"
        note = (f"{esc(sides[0]['pricing_reason'])}{esc(_other_side_note(F, T))} Benchmark and source provenance: {hubs}.")
    else:
        lhs = f"1 {F}" if vt != "derived_metal_ratio" else f"{F} / {T}"
        main = f'<span data-value-type="{vt}">{esc(lhs)} = {esc(v["value_text"])}' + ("" if vt == "derived_metal_ratio" else f" {esc(T)}") + "</span>"
        badge = METAL_VALUE_BADGE[vt] + " · AS OF " + esc(v["timestamps"][0][:10])
        note = (f"{'Derived' if v['derived'] else 'Direct'} value · sources: {esc(', '.join(v['sources']))} · "
                f"timestamps: {esc(', '.join(v['timestamps']))}. A reference value, not a dealer buy or sell price.")
    return f"""{STATIC_RATE_START}
  <div class="rate-banner" id="rate-root" data-from="{esc(F)}" data-to="{esc(T)}" data-mode="metal" data-value-type="{vt}">
    <div>
      <div class="rate-main" id="live-rate">{main}</div>
      <div class="rate-sub" id="rate-sub">{esc(sub)}</div>
    </div>
    <div class="rate-badge snap" id="rate-badge">{badge}</div>
  </div>
  <p class="rate-note" id="rate-source">{note}</p>

  <div class="card">
    <div class="card-title">Precious-Metal Reference</div>
    <div class="pj-grid">{"".join(_metal_block(m) for m in sides)}
    </div>
  </div>
{STATIC_RATE_END}"""


def metal_table_region_html(tokens: Dict[str, str], fx: Optional[Dict[str, Any]] = None) -> str:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    v = metal_value(F, T, fx)
    if v["value_type"] == "unavailable":
        text = "No valuation table: no licensed precious-metal pricing source is activated."
    else:
        text = (f"No valuation table: the reference value above applies to one {F} unit only; "
                f"dealer, retail and premium-inclusive prices differ.")
    return f"""{STATIC_TABLE_START}
    <div class="card">
      <p class="result-info" id="table-source">{esc(text)}</p>
    </div>
{STATIC_TABLE_END}"""


def metal_faq_items(tokens: Dict[str, str], fx: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    m = _metal_sides(F, T)[0]
    M = m["code"]
    ex = m["explanations"]
    shape = _metal_pair_shape(F, T)
    v = metal_value(F, T, fx)
    unavailable = v["value_type"] == "unavailable"
    items = [
        {"q": f"What does {M} mean?", "a": f"ISO 4217 lists {M} as “{m['iso_designation']['text']}”. {ex['what']}"},
        {"q": f"Is {M} a currency?", "a": f"No. {ex['not_this']}"},
        {"q": f"What unit does {M} represent?", "a": f"{m['unit_convention']} {m['troy_ounce_definition']['text']}"},
    ]
    q4 = f"How is the {F}/{T} ratio determined?" if shape == "ratio" else f"How is this {F}/{T} value determined?"
    if unavailable:
        a4 = f"{m['pricing_reason']} {m['licensing_claims'][1]['text']} {ex['derived']}{_other_side_note(F, T)}"
        a5 = ("No value is published yet. When a licensed source is activated, a value quoted directly by the source "
              "is labelled as a benchmark or market reference, and any other currency, inverse or ratio value is labelled as derived.")
        a7 = ("None yet: no value is published. An activated value shows its source timestamp, a derived value also shows "
              "the FX timestamp, and values older than the freshness limit are not shown.")
    else:
        a4 = (f"The value is {'derived' if v['derived'] else 'quoted directly'} from {', '.join(v['sources'])}. {ex['derived']}")
        a5 = f"It is {'a derived value' if v['derived'] else 'a direct ' + METAL_VALUE_BADGE[v['value_type']].lower() + ' value'}."
        a7 = f"Source timestamps: {', '.join(v['timestamps'])}."
    items += [{"q": q4, "a": a4.strip()},
              {"q": "Is this a direct benchmark or a derived value?", "a": a5},
              {"q": "Why may a metal value differ from a dealer quote?", "a": ex["benchmark_vs_dealer"]},
              {"q": "What timestamp does this reference use?", "a": a7}]
    return items


def metal_overview_html(tokens: Dict[str, str]) -> str:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    pol = instrument_policy_layer()
    sides = _metal_sides(F, T)
    shape = _metal_pair_shape(F, T)
    heading = "Relative Metal Value Reference" if shape == "ratio" else "Metal Valuation Reference"
    paras = [esc(f"{m['explanations']['what']} {m['explanations']['not_this']}") for m in sides]
    if shape == "ratio":
        paras.append(esc(f"A {sides[0]['metal_name'].lower()}-to-{sides[1]['metal_name'].lower()} ratio compares two metal "
                         f"values in the same currency and unit at aligned timestamps; it is not an exchange rate."))
    else:
        other = T if shape == "metal_from" else F
        paras.append(f'{esc(other)} ({esc(pol.resolve(other)["name"])}) is the counter-currency; see its '
                     f'<a href="{currency_hub_href(other)}">{esc(other)} reference</a> for its own pairs.'
                     + esc(_other_side_note(F, T)))
    paras.append(esc(sides[0]["pricing_reason"]))
    body = "\n".join(f"    <p>{p}</p>" for p in paras)
    return f"""  <section class="section">
    <div class="sec-title">Pair Overview</div>
    <div class="sec-h2">{esc(F)} / {esc(T)} {esc(heading)}</div>
{body}
  </section>"""


def metal_education_html(tokens: Dict[str, str]) -> str:
    ex = _metal_sides(tokens["FROM_CODE"], tokens["TO_CODE"])[0]["explanations"]
    return f"""  <section class="section">
    <div class="sec-title">Reading a Precious-Metal Reference</div>
    <div class="card">
      <p>{esc(ex["benchmark_vs_dealer"])}</p>
      <p>{esc(ex["derived"])}</p>
    </div>
  </section>
"""


def apply_metal_semantics(page: str, tokens: Dict[str, str], content: Dict[str, Any],
                          fx: Optional[Dict[str, Any]] = None) -> str:
    """Rewrite precious-metal pair metadata and page semantics. Idempotent; fails closed."""
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    brand = content.get("site_copy", {}).get("brand_name", SITE_NAME)
    meta = metal_pair_metadata(tokens, brand, fx)
    left, right = _metal_h1(F, T)
    for rx, tpl in _META_PATTERNS:
        if len(rx.findall(page)) != 1:
            raise ValueError(f"metal metadata: {rx.pattern} not found exactly once")
        page = rx.sub(lambda _m: tpl.format(title=esc(meta["title"]), description=esc(meta["description"])), page)
    for rx, new, label in ((_ROBOTS_RE, f'<meta name="robots" content="{pair_robots(F, T)}">', "robots"),
                           (_H1_RE, f"<h1>{esc(left)} <em>{esc(right)}</em></h1>", "h1"),
                           (_SUBTITLE_RE, '<p class="pair-subtitle">Precious-metal reference</p>', "subtitle")):
        if len(rx.findall(page)) != 1:
            raise ValueError(f"metal {label} anchor not found exactly once")
        page = rx.sub(lambda _m, v=new: v, page)
    if page.count(_OVERVIEW_START) != 1 or page.count(_PASSAGE_START) != 1 or page.count(STATIC_TABLE_START) != 1:
        raise ValueError("metal body anchors not found exactly once")
    i = page.index(_OVERVIEW_START)
    j = page.index("\n  </section>", i) + len("\n  </section>")
    page = page[:i] + metal_overview_html(tokens) + page[j:]
    page = _MACRO_RE.sub("", page)
    p = page.index(_PASSAGE_START)
    edu_start = page.index("\n  </section>", p) + len("\n  </section>")
    table_start = page.rindex('\n  <section class="section">\n', 0, page.index(STATIC_TABLE_START))
    page = page[:edu_start] + "\n" + metal_education_html(tokens) + page[table_start:]
    t0 = page.rindex('\n  <section class="section">\n', 0, page.index(STATIC_TABLE_START)) + 1
    t1 = page.index(STATIC_TABLE_START)
    page = page[:t0] + '  <section class="section">\n    <div class="sec-title">Metal Valuation Status</div>\n' + page[t1:]
    items = metal_faq_items(tokens, fx)
    page = replace_faq_regions(page, items)
    return replace_webpage_jsonld(page, tokens, items, "precious_metal")


# ---- SEO-A4.5: institutional units (XDR, CLF, UYW, XUA, XSU) ----------------
#
# Pairs with an institutional-unit side (instrument types special_instrument,
# unit_of_account, regional_unit), unless standards / historical / precious-metal
# treatment governs, are institutional valuation references — never ordinary FX
# converters, even where the raw FX snapshot carries a provider value (that value
# is classified secondary-only and is not rendered). Facts come only from
# instrument_policy.institutional_view() (registry-cited). Any numeric value comes
# only from institutional_reference.value_view(), which reads
# data/institutional_reference_snapshot.json and refuses unless licence,
# provenance, methodology, dates, cadence freshness and FX-skew rules all pass.
# Current state: reference_layer_only -> every value is "unavailable".

_INSTITUTIONAL_SNAPSHOT = None


def institutional_snapshot() -> Dict[str, Any]:
    global _INSTITUTIONAL_SNAPSHOT
    if _INSTITUTIONAL_SNAPSHOT is None:
        import institutional_reference
        _INSTITUTIONAL_SNAPSHOT = institutional_reference.load_institutional_snapshot()
    return _INSTITUTIONAL_SNAPSHOT


def _institutional_sides(F: str, T: str) -> List[Dict[str, Any]]:
    pol = instrument_policy_layer()
    return [pol.institutional_view(c) for c in (F, T) if pol.is_institutional_unit(c)]


def institutional_value(F: str, T: str, fx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    import institutional_reference
    fx = fx if fx is not None else load_rate_snapshot()
    return institutional_reference.value_view(F, T, institutional_snapshot(), fx, format_rate_value)


INSTITUTIONAL_VALUE_BADGE = {"issuer_published_valuation": "ISSUER VALUATION", "indexed_unit_value": "OFFICIAL INDEXED VALUE",
                             "basket_valuation": "ISSUER BASKET VALUATION", "derived_reference_value": "DERIVED"}


def _code_article(code: str) -> str:
    """'an XDR' / 'a CLF': the article follows the spoken first letter of the code."""
    return "an" if code[:1] in "AEFHILMNORSX" else "a"


def institutional_pair_role(F: str, T: str) -> str:
    sides = _institutional_sides(F, T)
    return "institutional_relative_reference" if len(sides) == 2 else sides[0]["pair_role"]


def _institutional_governing(F: str, T: str) -> Dict[str, Any]:
    """The side whose identity names the page: the unit that declares a relationship
    to the other (XUA -> XDR), else the from-side unit."""
    sides = _institutional_sides(F, T)
    if len(sides) == 2:
        for s in sides:
            if s["related_unit"] in (F, T):
                return s
    return sides[0]


def institutional_pair_metadata(tokens: Dict[str, str], brand: str = SITE_NAME,
                                fx: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    sides = _institutional_sides(F, T)
    role = institutional_pair_role(F, T)
    active = institutional_value(F, T, fx)["value_type"] != "unavailable"
    g = _institutional_governing(F, T)
    if role == "institutional_relative_reference":
        if g["related_unit"] in (F, T):
            title = f"{F} / {T} — {g['title_role']} | {brand}"
        else:
            title = f"{F} / {T} — Institutional Units Relative Reference | {brand}"
        description = (f"Institutional reference for {sides[0]['display_name']} ({sides[0]['code']}) and "
                       f"{sides[1]['display_name']} ({sides[1]['code']}): issuers, classification, valuation methodology, "
                       f"the relationship between the two units and source provenance. No market exchange rate exists for this pair.")
    else:
        title = f"{F} to {T} — {g['title_role']} | {brand}"
        other = T if g["code"] == F else F
        description = (f"Institutional reference for the {g['display_name']} ({g['code']}) against {_cur_name(other)} ({other}): "
                       + (f"issuer {g['issuer_display']}, " if g["issuer_display"] else "issuer unresolved, ")
                       + "classification, valuation methodology, status and source provenance. "
                       + ("Values are labelled with issuer, dates and direct or derived type." if active
                          else "No issuer value is currently published on ConvertCCY."))
    return {"title": title, "description": description, "schema_name": title, "schema_description": description}


def _institutional_h1(F: str, T: str) -> Tuple[str, str]:
    sides = _institutional_sides(F, T)
    if len(sides) == 2:
        return f"{sides[0]['display_name']} ({F}) / {sides[1]['display_name']} ({T})", "Institutional Relative Reference"
    u = sides[0]
    if u["code"] == F:
        return f"{u['display_name']} ({F})", f"{u['h1_role']} in {_cur_name(T)} ({T})"
    return f"{_cur_name(F)} ({F})", f"Expressed in {u['display_name']} ({T})"


def _institutional_block(iv: Dict[str, Any]) -> str:
    lines = [_cited_line(iv["iso_designation"], "ISO 4217 designation: ")]
    issuer = iv["issuer_display"] or "unresolved — no current issuer publication verified"
    lines.append(f'<div class="pj-line">Instrument type: {esc(iv["classification_label"])} · Issuer: {esc(issuer)}</div>')
    status = "unresolved" if iv["activity_status"] == "status_unresolved" else iv["activity_status"].replace("_", " ")
    lines.append(f'<div class="pj-line" data-activity-status="{esc(iv["activity_status"])}">Status: {esc(status)}</div>')
    lines += [_cited_line(c) for c in iv["activity_claims"]]
    lines += [_cited_line(c, "Reported (secondary source): ") for c in iv["reported_indicators"]]
    lines += [_cited_line(c) for c in iv["claims"]]
    lines.append(f'<div class="pj-line">Valuation: {esc(iv["explanations"]["value_status"])}</div>')
    lines += [_cited_line(c) for c in iv["licensing_claims"]]
    lines.append(f'<div class="pj-line">Authoritative reference: <a href="{currency_hub_href(iv["code"])}">'
                 f'{esc(iv["code"])} — {esc(iv["display_name"])} reference →</a></div>')
    body = "\n          ".join(lines)
    return f"""
        <div class="pj-block pj-plain" data-institutional-code="{esc(iv["code"])}" data-value-decision="{esc(iv["value_decision"])}">
          <div class="pj-head"><span class="pj-badge">INSTITUTIONAL UNIT</span> {esc(iv["code"])} — {esc(iv["display_name"])}</div>
          {body}
        </div>"""


def _institutional_relation_note(F: str, T: str) -> str:
    sides = _institutional_sides(F, T)
    if len(sides) != 2:
        return ""
    for s in sides:
        if s["related_unit"] in (F, T):
            return f" {s['explanations']['valuation']}"
    return (f" Both {F} and {T} are institutional units with their own issuers; no issuer defines a relationship "
            f"between them, so no {F}/{T} value is shown.")


def institutional_rate_region_html(tokens: Dict[str, str], fx: Optional[Dict[str, Any]] = None) -> str:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    sides = _institutional_sides(F, T)
    role = institutional_pair_role(F, T)
    v = institutional_value(F, T, fx)
    vt = v["value_type"]
    hubs = " and ".join(f'<a href="{currency_hub_href(s["code"])}">{esc(s["code"])} reference</a>' for s in sides)
    sub = "; ".join(f'{s["code"]} is the {s["display_name"]} — an institutional unit, not a circulating currency' for s in sides)
    if vt == "unavailable":
        main = "No issuer value published here"
        badge = " · ".join(dict.fromkeys(s["decision_label"] for s in sides))
        note = (" ".join(dict.fromkeys(s["explanations"]["value_status"] for s in sides))
                + _institutional_relation_note(F, T) + f" Issuer, methodology and source provenance: ")
        note_html = f"{esc(note)}{hubs}."
    else:
        main = f'<span data-value-type="{vt}">1 {esc(F)} = {esc(v["value_text"])} {esc(T)}</span>'
        badge = INSTITUTIONAL_VALUE_BADGE[vt] + " · " + esc(v["valuation_date"])
        if v["derived"]:
            lead = f"DERIVED FROM {v['issuer'].upper()} VALUATION — not a direct issuer quote."
        else:
            lead = f"Direct issuer value published by {v['issuer']}."
        parts = [lead, f"Issuer source: {v['issuer_source']}", f"valuation date: {v['valuation_date']}",
                 f"methodology: {v['methodology_id']}"]
        if v.get("fx_source"):
            parts += [f"FX source: {v['fx_source']}", f"FX timestamp: {v['fx_timestamp']}"]
        if v["derivation_method"]:
            parts.append(f"derivation: {v['derivation_method']}")
        note_html = esc(" · ".join(parts) + ".")
    return f"""{STATIC_RATE_START}
  <div class="rate-banner" id="rate-root" data-from="{esc(F)}" data-to="{esc(T)}" data-mode="institutional" data-value-type="{vt}" data-pair-role="{esc(role)}">
    <div>
      <div class="rate-main" id="live-rate">{main}</div>
      <div class="rate-sub" id="rate-sub">{esc(sub)}</div>
    </div>
    <div class="rate-badge snap" id="rate-badge">{esc(badge) if vt == "unavailable" else badge}</div>
  </div>
  <p class="rate-note" id="rate-source">{note_html}</p>

  <div class="card">
    <div class="card-title">Institutional Unit Reference</div>
    <div class="pj-grid">{"".join(_institutional_block(s) for s in sides)}
    </div>
  </div>
{STATIC_RATE_END}"""


def institutional_table_region_html(tokens: Dict[str, str], fx: Optional[Dict[str, Any]] = None) -> str:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    v = institutional_value(F, T, fx)
    if v["value_type"] == "unavailable":
        text = "No valuation table: no licensed issuer valuation is activated for this institutional pair."
    else:
        text = f"No conversion table: the institutional value above applies to one {F} unit on its valuation date only."
    return f"""{STATIC_TABLE_START}
    <div class="card">
      <p class="result-info" id="table-source">{esc(text)}</p>
    </div>
{STATIC_TABLE_END}"""


def institutional_faq_items(tokens: Dict[str, str], fx: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    sides = _institutional_sides(F, T)
    v = institutional_value(F, T, fx)
    items: List[Dict[str, str]] = []
    for s in sides:
        for f in s["faq"]:
            if f["q"] not in {i["q"] for i in items}:
                items.append(dict(f))
    issuers = " or ".join(dict.fromkeys(s["issuer_display"] or f"an issuer of {s['code']}" for s in sides))
    if v["value_type"] == "unavailable":
        a_direct = (f"No {F}/{T} value is shown. " + " ".join(dict.fromkeys(s["explanations"]["value_status"] for s in sides))
                    + " When an issuer value is activated, a value in the unit's own denomination is labelled as a direct issuer value "
                      "and any other currency or inverse value is labelled as derived from the issuer valuation.")
        a_date = ("None: no value is published, so no valuation date applies. An activated value shows the issuer valuation date "
                  "and, if derived, the FX reference date as well.")
    else:
        a_direct = (f"No — it is derived from the {v['issuer']} valuation and an FX reference ({v['derivation_method']})."
                    if v["derived"] else f"Yes — it is the direct value published by {v['issuer']}.")
        a_date = f"Issuer valuation date {v['valuation_date']}" + (f"; FX timestamp {v['fx_timestamp']}." if v.get("fx_timestamp") else ".")
    items += [{"q": f"Is this {F}/{T} value published directly by {issuers}?", "a": a_direct},
              {"q": "What date does this reference use?", "a": a_date}]
    return items


def institutional_overview_html(tokens: Dict[str, str]) -> str:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    pol = instrument_policy_layer()
    sides = _institutional_sides(F, T)
    role = institutional_pair_role(F, T)
    heading = {"supranational_valuation_reference": "Supranational Valuation Reference",
               "indexed_unit_reference": "Indexed Unit Reference",
               "institutional_valuation_reference": "Institutional Valuation Reference",
               "institutional_relative_reference": "Institutional Relative Reference"}[role]
    paras = [esc(f"{s['explanations']['what']} {s['explanations']['not_this']}") for s in sides]
    if len(sides) == 1:
        other = T if sides[0]["code"] == F else F
        paras.append(f'{esc(other)} ({esc(pol.resolve(other)["name"])}) is the counter-currency; see its '
                     f'<a href="{currency_hub_href(other)}">{esc(other)} reference</a> for its own pairs.')
        paras.append(esc(sides[0]["explanations"]["valuation"]))
    else:
        paras.append(esc(_institutional_relation_note(F, T).strip()))
    body = "\n".join(f"    <p>{p}</p>" for p in paras)
    return f"""  <section class="section">
    <div class="sec-title">Pair Overview</div>
    <div class="sec-h2">{esc(F)} / {esc(T)} {esc(heading)}</div>
{body}
  </section>"""


INSTITUTIONAL_EDUCATION_HTML = """  <section class="section">
    <div class="sec-title">Reading an Institutional-Unit Reference</div>
    <div class="card">
      <p>An institutional unit is defined and valued by an institution — through a currency basket, an official index or an institutional rule — rather than priced by a foreign-exchange market. Its governing value is the one its issuer publishes, on the issuer's own schedule.</p>
      <p>A value shown in the unit's own denomination is a direct issuer value. A value in any other currency, or an inverse value, is derived from the issuer valuation and a separate FX reference; both dates are shown, and it is not an issuer quote.</p>
    </div>
  </section>
"""


def apply_institutional_semantics(page: str, tokens: Dict[str, str], content: Dict[str, Any],
                                  fx: Optional[Dict[str, Any]] = None) -> str:
    """Rewrite institutional-unit pair metadata and page semantics. Idempotent; fails closed."""
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    brand = content.get("site_copy", {}).get("brand_name", SITE_NAME)
    meta = institutional_pair_metadata(tokens, brand, fx)
    left, right = _institutional_h1(F, T)
    for rx, tpl in _META_PATTERNS:
        if len(rx.findall(page)) != 1:
            raise ValueError(f"institutional metadata: {rx.pattern} not found exactly once")
        page = rx.sub(lambda _m: tpl.format(title=esc(meta["title"]), description=esc(meta["description"])), page)
    for rx, new, label in ((_ROBOTS_RE, f'<meta name="robots" content="{pair_robots(F, T)}">', "robots"),
                           (_H1_RE, f"<h1>{esc(left)} <em>{esc(right)}</em></h1>", "h1"),
                           (_SUBTITLE_RE, '<p class="pair-subtitle">Institutional-unit reference</p>', "subtitle")):
        if len(rx.findall(page)) != 1:
            raise ValueError(f"institutional {label} anchor not found exactly once")
        page = rx.sub(lambda _m, v=new: v, page)
    if page.count(_OVERVIEW_START) != 1 or page.count(_PASSAGE_START) != 1 or page.count(STATIC_TABLE_START) != 1:
        raise ValueError("institutional body anchors not found exactly once")
    i = page.index(_OVERVIEW_START)
    j = page.index("\n  </section>", i) + len("\n  </section>")
    page = page[:i] + institutional_overview_html(tokens) + page[j:]
    page = _MACRO_RE.sub("", page)
    p = page.index(_PASSAGE_START)
    edu_start = page.index("\n  </section>", p) + len("\n  </section>")
    table_start = page.rindex('\n  <section class="section">\n', 0, page.index(STATIC_TABLE_START))
    page = page[:edu_start] + "\n" + INSTITUTIONAL_EDUCATION_HTML + page[table_start:]
    t0 = page.rindex('\n  <section class="section">\n', 0, page.index(STATIC_TABLE_START)) + 1
    t1 = page.index(STATIC_TABLE_START)
    page = page[:t0] + '  <section class="section">\n    <div class="sec-title">Institutional Valuation Status</div>\n' + page[t1:]
    items = institutional_faq_items(tokens, fx)
    page = replace_faq_regions(page, items)
    return replace_webpage_jsonld(page, tokens, items, "institutional_unit")


# ---- SEO-A4.6A: residual live-fiat coverage (KPW, VED) ----------------------
#
# Active fiat codes that the FX reference provider does not publish, and that no
# higher-precedence policy layer governs, are rendered as live-fiat coverage
# references instead of the generic A3 "unsupported" template. Membership comes
# ONLY from data/live_fiat_reference_snapshot.json, whose validator enforces the
# scope rule (active fiat, no provider value) — so a code with a provider value
# (CUP, IRR, MMK, SYP, TMT, VES, …) can never be captured here. Facts are
# registry-cited; any numeric value comes only from live_fiat_reference.value_view(),
# which refuses unless regime, source tier, licence, dates, provenance and
# freshness all pass. Current state: reference_layer_only -> "unavailable".

_LIVE_FIAT_SNAPSHOT = None


def live_fiat_snapshot() -> Dict[str, Any]:
    global _LIVE_FIAT_SNAPSHOT
    if _LIVE_FIAT_SNAPSHOT is None:
        import live_fiat_reference
        _LIVE_FIAT_SNAPSHOT = live_fiat_reference.load_live_fiat_snapshot()
    return _LIVE_FIAT_SNAPSHOT


def is_live_fiat(code: str) -> bool:
    return code in live_fiat_snapshot().get("currencies", {})


def live_fiat_view(code: str) -> Dict[str, Any]:
    """Governed coverage view for one covered code, with claim sources resolved."""
    snap = live_fiat_snapshot()
    srcs = {s["id"]: s for s in snap["sources"]}
    c = dict(snap["currencies"][code])

    def cite(cl):
        s = srcs[cl["source"]]
        return {"text": cl["text"], "sources": [{"url": s["url"], "authority": s["authority"]}]}
    for k in ("identity_claims", "coverage_claims", "reported_indicators"):
        c[k] = [cite(x) for x in c[k]]
    c["code"] = code
    c["role_label"] = LIVE_FIAT_ROLE_LABELS[c["instrument_role"]]
    c["sources_resolved"] = [srcs[i] for i in dict.fromkeys(
        x["source"] for k in ("identity_claims", "coverage_claims", "reported_indicators")
        for x in snap["currencies"][code][k])]
    return c


LIVE_FIAT_ROLE_LABELS = {"active_restricted_fiat": "Active restricted fiat currency",
                         "active_fiat": "Active fiat currency",
                         "transitional_iso_code": "Transitional ISO 4217 code"}
LIVE_FIAT_AVAILABILITY_LABELS = {
    "live_verified": "governed value available",
    "live_caveated": "governed value available with caveats",
    "official_source_unresolved": "no governed value — official source unresolved",
    "provider_regime_unresolved": "no governed value — provider rate regime unresolved",
    "license_unresolved": "no governed value — publication licence unresolved",
    "no_governed_value_available": "no governed value available",
    "code_role_under_review": "no governed value — code role under review"}
LIVE_FIAT_REGIME_LABELS = {"official_reference": "official reference rate", "market_reference": "market reference rate",
                           "multiple_regimes_verified": "multiple verified rate regimes", "unresolved": "unresolved",
                           "not_applicable": "not applicable (no independent rate)"}
LIVE_FIAT_VALUE_BADGE = {"official_reference": "OFFICIAL REFERENCE", "market_reference": "MARKET REFERENCE",
                         "derived_reference_value": "DERIVED"}


def _live_fiat_sides(F: str, T: str) -> List[Dict[str, Any]]:
    return [live_fiat_view(c) for c in (F, T) if is_live_fiat(c)]


def live_fiat_value(F: str, T: str, fx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    import live_fiat_reference
    fx = fx if fx is not None else load_rate_snapshot()
    return live_fiat_reference.value_view(F, T, live_fiat_snapshot(), fx, format_rate_value)


def _live_fiat_role_word(sides: List[Dict[str, Any]]) -> str:
    if all(s["instrument_role"] == "transitional_iso_code" for s in sides):
        return "Code-Status Reference"
    return "Coverage Reference"


def live_fiat_pair_metadata(tokens: Dict[str, str], brand: str = SITE_NAME,
                            fx: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    sides = _live_fiat_sides(F, T)
    active = live_fiat_value(F, T, fx)["value_type"] != "unavailable"
    if len(sides) == 2:
        title = f"{F} / {T} — Live-Fiat Coverage Reference | {brand}"
        description = (f"Coverage reference for {sides[0]['display_name']} ({F}) and {sides[1]['display_name']} ({T}): "
                       f"ISO identity, code role, rate-regime state, source coverage and provenance. "
                       f"Neither code is published by the FX reference provider, so no {F}/{T} value exists.")
    else:
        s = sides[0]
        other = T if s["code"] == F else F
        title = f"{F} to {T} — {s['display_name']} {_live_fiat_role_word(sides)} | {brand}"
        description = (f"Reference for the {s['display_name']} ({s['code']}) against {_cur_name(other)} ({other}): "
                       f"ISO identity, {'code role' if s['instrument_role'] == 'transitional_iso_code' else 'currency status'}, "
                       "rate-regime state, source coverage and provenance. "
                       + ("Values are labelled with source, regime and date." if active
                          else f"No governed {s['code']} value is currently published on ConvertCCY."))
    return {"title": title, "description": description, "schema_name": title, "schema_description": description}


def _live_fiat_h1(F: str, T: str) -> Tuple[str, str]:
    sides = _live_fiat_sides(F, T)
    if len(sides) == 2:
        return f"{sides[0]['display_name']} ({F}) / {sides[1]['display_name']} ({T})", "Live-Fiat Coverage Reference"
    s = sides[0]
    if s["code"] == F:
        return f"{s['display_name']} ({F})", f"{_live_fiat_role_word(sides)} in {_cur_name(T)} ({T})"
    return f"{_cur_name(F)} ({F})", f"Against {s['display_name']} ({T})"


def _live_fiat_block(lv: Dict[str, Any]) -> str:
    lines = [_cited_line(c, "ISO 4217: ") for c in lv["identity_claims"]]
    issuer = lv["issuer_or_authority"] or "not stated — no issuer publication located"
    lines.append(f'<div class="pj-line">Role: {esc(lv["role_label"])} · Issuer or authority: {esc(issuer)}</div>')
    if lv.get("operative_code"):
        op = lv["operative_code"]
        lines.append(f'<div class="pj-line" data-operative-code="{esc(op)}">Operative code per ISO 4217: '
                     f'<a href="{currency_hub_href(op)}">{esc(op)} — {esc(_cur_name(op))} reference →</a> '
                     f'(no value is copied from {esc(op)} to {esc(lv["code"])})</div>')
    lines.append(f'<div class="pj-line" data-availability="{esc(lv["availability_status"])}">Availability: '
                 f'{esc(LIVE_FIAT_AVAILABILITY_LABELS[lv["availability_status"]])}</div>')
    lines.append(f'<div class="pj-line" data-rate-regime="{esc(lv["rate_regime"])}">Rate regime: '
                 f'{esc(LIVE_FIAT_REGIME_LABELS[lv["rate_regime"]])}</div>')
    lines += [_cited_line(c, "Provider coverage: ") for c in lv["coverage_claims"]]
    lines += [_cited_line(c, "Reported (secondary source): ") for c in lv["reported_indicators"]]
    lines.append(f'<div class="pj-line">Next activation condition: {esc(lv["explanations"]["activation"])}</div>')
    lines.append(f'<div class="pj-line">Authoritative reference: <a href="{currency_hub_href(lv["code"])}">'
                 f'{esc(lv["code"])} — {esc(lv["display_name"])} reference →</a></div>')
    body = "\n          ".join(lines)
    return f"""
        <div class="pj-block pj-plain" data-live-fiat-code="{esc(lv["code"])}" data-availability="{esc(lv["availability_status"])}">
          <div class="pj-head"><span class="pj-badge">{esc(lv["role_label"].upper())}</span> {esc(lv["code"])} — {esc(lv["display_name"])}</div>
          {body}
        </div>"""


def live_fiat_rate_region_html(tokens: Dict[str, str], fx: Optional[Dict[str, Any]] = None) -> str:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    sides = _live_fiat_sides(F, T)
    v = live_fiat_value(F, T, fx)
    vt = v["value_type"]
    hubs = " and ".join(f'<a href="{currency_hub_href(s["code"])}">{esc(s["code"])} reference</a>' for s in sides)
    sub = "; ".join(f'{s["code"]} is {"an" if s["role_label"][0].lower() in "aeiou" else "a"} {s["role_label"][0].lower() + s["role_label"][1:]} — '
                    f'{LIVE_FIAT_AVAILABILITY_LABELS[s["availability_status"]]}' for s in sides)
    avail = " ".join(dict.fromkeys(s["availability_status"] for s in sides))
    regime = " ".join(dict.fromkeys(s["rate_regime"] for s in sides))
    if vt == "unavailable":
        main = "No governed value published"
        badge = esc(" · ".join(dict.fromkeys(s["decision_label"] for s in sides)))
        note = " ".join(dict.fromkeys(s["explanations"]["value_status"] for s in sides))
        if len(sides) == 2:
            note += f" Neither {F} nor {T} is published by the FX reference provider, so no {F}/{T} cross exists."
        note_html = f"{esc(note)} Identity, rate regime and source provenance: {hubs}."
    else:
        main = f'<span data-value-type="{vt}">1 {esc(F)} = {esc(v["value_text"])} {esc(T)}</span>'
        badge = LIVE_FIAT_VALUE_BADGE[vt] + " · " + esc(v["valuation_date"])
        lead = (f"DERIVED FROM {LIVE_FIAT_REGIME_LABELS[v['rate_regime']].upper()} — not a direct source quote."
                if v["derived"] else f"Direct {LIVE_FIAT_REGIME_LABELS[v['rate_regime']]} published by {v['source']}.")
        parts = [lead, f"Source: {v['source']}", f"valuation date: {v['valuation_date']}",
                 f"rate regime: {LIVE_FIAT_REGIME_LABELS[v['rate_regime']]}"]
        if v.get("fx_source"):
            parts += [f"FX source: {v['fx_source']}", f"FX timestamp: {v['fx_timestamp']}"]
        if v["derivation_method"]:
            parts.append(f"derivation: {v['derivation_method']}")
        note_html = esc(" · ".join(parts) + ".")
    return f"""{STATIC_RATE_START}
  <div class="rate-banner" id="rate-root" data-from="{esc(F)}" data-to="{esc(T)}" data-mode="live_fiat" data-value-type="{vt}" data-availability="{esc(avail)}" data-rate-regime="{esc(regime)}">
    <div>
      <div class="rate-main" id="live-rate">{main}</div>
      <div class="rate-sub" id="rate-sub">{esc(sub)}</div>
    </div>
    <div class="rate-badge snap" id="rate-badge">{badge}</div>
  </div>
  <p class="rate-note" id="rate-source">{note_html}</p>

  <div class="card">
    <div class="card-title">Live-Fiat Coverage Reference</div>
    <div class="pj-grid">{"".join(_live_fiat_block(s) for s in sides)}
    </div>
  </div>
{STATIC_RATE_END}"""


def live_fiat_table_region_html(tokens: Dict[str, str], fx: Optional[Dict[str, Any]] = None) -> str:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    v = live_fiat_value(F, T, fx)
    if v["value_type"] == "unavailable":
        codes = " or ".join(s["code"] for s in _live_fiat_sides(F, T))
        text = f"No conversion table: no governed {codes} value is published, so no amounts are converted."
    else:
        text = f"No conversion table: the value above applies to one {F} unit on its valuation date and rate regime only."
    return f"""{STATIC_TABLE_START}
    <div class="card">
      <p class="result-info" id="table-source">{esc(text)}</p>
    </div>
{STATIC_TABLE_END}"""


def live_fiat_faq_items(tokens: Dict[str, str], fx: Optional[Dict[str, Any]] = None) -> List[Dict[str, str]]:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    sides = _live_fiat_sides(F, T)
    v = live_fiat_value(F, T, fx)
    if v["value_type"] == "unavailable":
        a_rate = (f"ConvertCCY publishes no governed {F}/{T} value. "
                  + " ".join(dict.fromkeys(s["explanations"]["value_status"] for s in sides))
                  + " No number is shown rather than an estimate.")
    else:
        a_rate = (f"1 {F} = {v['value_text']} {T} ({LIVE_FIAT_REGIME_LABELS[v['rate_regime']]}, "
                  f"{'derived' if v['derived'] else 'direct'}, valuation date {v['valuation_date']}, source {v['source']}).")
    items: List[Dict[str, str]] = [{"q": f"How much is 1 {F} in {T}?", "a": a_rate}]
    for s in sides:
        for f in s["faq"]:
            if f["q"] not in {i["q"] for i in items}:
                items.append(dict(f))
    items.append({"q": "Does a missing value mean the currency is not real?",
                  "a": "No. A missing value means no governed source with an identified rate regime, a valuation date "
                       "and publication rights is available to ConvertCCY. It says nothing against the validity of the "
                       "currency or code, and it does not mean that no market exists."})
    return items


def live_fiat_overview_html(tokens: Dict[str, str]) -> str:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    sides = _live_fiat_sides(F, T)
    paras = [esc(f"{s['explanations']['what']} {s['explanations']['regime']}") for s in sides]
    if len(sides) == 1:
        other = T if sides[0]["code"] == F else F
        paras.append(f'{esc(other)} ({esc(_cur_name(other))}) is the counter-currency; see its '
                     f'<a href="{currency_hub_href(other)}">{esc(other)} reference</a> for its own pairs.')
    body = "\n".join(f"    <p>{p}</p>" for p in paras)
    return f"""  <section class="section">
    <div class="sec-title">Pair Overview</div>
    <div class="sec-h2">{esc(F)} / {esc(T)} {esc(_live_fiat_role_word(sides))}</div>
{body}
  </section>"""


LIVE_FIAT_EDUCATION_HTML = """  <section class="section">
    <div class="sec-title">Reading a Live-Fiat Coverage Reference</div>
    <div class="card">
      <p>A coverage reference describes a real currency or currency code for which ConvertCCY has no governed value: what the code is, whether a governed value exists, why it does or does not, which rate regime applies and where the evidence comes from.</p>
      <p>No governed value is not the same as no currency, and the absence of a value from ConvertCCY's FX provider is not the same as the absence of a market. A value is shown only when its source identifies the rate regime, carries a valuation date, is current and permits publication.</p>
    </div>
  </section>
"""


def apply_live_fiat_semantics(page: str, tokens: Dict[str, str], content: Dict[str, Any],
                              fx: Optional[Dict[str, Any]] = None) -> str:
    """Rewrite live-fiat pair metadata and page semantics. Idempotent; fails closed."""
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    brand = content.get("site_copy", {}).get("brand_name", SITE_NAME)
    meta = live_fiat_pair_metadata(tokens, brand, fx)
    left, right = _live_fiat_h1(F, T)
    sides = _live_fiat_sides(F, T)
    subtitle = ("ISO 4217 code-status reference" if all(s["instrument_role"] == "transitional_iso_code" for s in sides)
                else "Live-fiat coverage reference")
    for rx, tpl in _META_PATTERNS:
        if len(rx.findall(page)) != 1:
            raise ValueError(f"live-fiat metadata: {rx.pattern} not found exactly once")
        page = rx.sub(lambda _m: tpl.format(title=esc(meta["title"]), description=esc(meta["description"])), page)
    for rx, new, label in ((_ROBOTS_RE, f'<meta name="robots" content="{pair_robots(F, T)}">', "robots"),
                           (_H1_RE, f"<h1>{esc(left)} <em>{esc(right)}</em></h1>", "h1"),
                           (_SUBTITLE_RE, f'<p class="pair-subtitle">{subtitle}</p>', "subtitle")):
        if len(rx.findall(page)) != 1:
            raise ValueError(f"live-fiat {label} anchor not found exactly once")
        page = rx.sub(lambda _m, v=new: v, page)
    if page.count(_OVERVIEW_START) != 1 or page.count(_PASSAGE_START) != 1 or page.count(STATIC_TABLE_START) != 1:
        raise ValueError("live-fiat body anchors not found exactly once")
    i = page.index(_OVERVIEW_START)
    j = page.index("\n  </section>", i) + len("\n  </section>")
    page = page[:i] + live_fiat_overview_html(tokens) + page[j:]
    page = _MACRO_RE.sub("", page)
    p = page.index(_PASSAGE_START)
    edu_start = page.index("\n  </section>", p) + len("\n  </section>")
    table_start = page.rindex('\n  <section class="section">\n', 0, page.index(STATIC_TABLE_START))
    page = page[:edu_start] + "\n" + LIVE_FIAT_EDUCATION_HTML + page[table_start:]
    t0 = page.rindex('\n  <section class="section">\n', 0, page.index(STATIC_TABLE_START)) + 1
    t1 = page.index(STATIC_TABLE_START)
    page = page[:t0] + '  <section class="section">\n    <div class="sec-title">Value Coverage Status</div>\n' + page[t1:]
    items = live_fiat_faq_items(tokens, fx)
    page = replace_faq_regions(page, items)
    return replace_webpage_jsonld(page, tokens, items, "live_fiat_coverage")


# ---- SEO-A4.6B: rate-regime governance (CUP, IRR, MMK, SYP, TMT, VES) --------
#
# Active fiat codes that DO have a provider value, but whose rate regime needs
# explicit governance, route to "rate_regime_governed" after every other policy
# layer. Membership and decisions come ONLY from rate_regime_governance in
# data/live_fiat_reference_snapshot.json (scope rule: provider value present, not
# an A4.6A code). The provider value itself is unchanged; the effective provider
# policy decides how it is used (live_fiat_reference.pair_regime_view):
#   converter   every governed side permits it: the ordinary A3 converter is kept,
#               plus a regime card stating what the provider value matches
#   comparison  provider value shown, labelled "comparison only", no converter
#   none        no number (provider regime unresolved / conflicting)
# Issuer and market figures are never rendered while their licence is unclear.

REGIME_TYPE_LABELS = {
    "single_official_reference": "single official reference rate",
    "fixed_official_reference": "fixed official reference rate",
    "multi_segment_official": "several official rate segments, plus an informal market",
    "official_reference_plus_market_trading": "official reference rate plus a materially different official market trading rate",
    "official_reference_plus_parallel_market": "official rate plus a reported parallel market",
    "market_reference_only": "market reference only",
    "provider_regime_unresolved": "provider regime unresolved",
    "official_source_unresolved": "official source unresolved"}
EVIDENCE_LABELS = {"issuer_verified": "verified on the issuer's site", "secondary_reported": "reported by a secondary source",
                   "unverified_copy": "seen only on an unverified copy of the issuer's site", "unresolved": "not verified"}
POLICY_LABELS = {"secondary_provider_value": "provider snapshot used for conversion, labelled with its regime match",
                 "governed_primary": "governed issuer value",
                 "comparison_only": "provider snapshot shown for comparison only — no converter",
                 "suppressed": "provider value not shown", "unresolved": "provider value not shown"}
REGIME_VALUE_WITHHELD = {"license_unclear": "value not republished (reuse terms unclear)",
                         "not_usable": "value not republished (not a usable value source)",
                         "display_only": "value not republished (display-only terms)",
                         "derived_use_only": "value not republished (derived use only)"}
REVERIFY_NOTES = {"regime_match_not_reverified": "The regime match was audited for an earlier provider snapshot and has not been re-verified for this one.",
                  "provider_value_drifted_since_audit": "The provider value has moved materially since the regime audit, so its regime match no longer holds.",
                  "provider_value_missing": "The provider no longer publishes a value."}


def is_rate_regime_governed(code: str) -> bool:
    return code in live_fiat_snapshot().get("rate_regime_governance", {}).get("currencies", {})


def rate_regime_view(code: str) -> Dict[str, Any]:
    snap = live_fiat_snapshot()
    srcs = {s["id"]: s for s in snap["sources"]}
    c = dict(snap["rate_regime_governance"]["currencies"][code])

    def cite(cl):
        s = srcs[cl["source"]]
        return {"text": cl["text"], "sources": [{"url": s["url"], "authority": s["authority"]}],
                "secondary": s["source_tier"] in ("secondary_press", "secondary_analysis", "market_aggregator")}
    for k in ("identity_claims", "coverage_claims", "regime_claims"):
        c[k] = [cite(x) for x in c[k]]
    c["code"] = code
    c["regimes_resolved"] = [dict(r, source=srcs[r["source_id"]]) for r in c["regimes"]]
    c["sources_resolved"] = [srcs[i] for i in dict.fromkeys(
        [x["source"] for k in ("identity_claims", "coverage_claims", "regime_claims") for x in snap["rate_regime_governance"]["currencies"][code][k]]
        + [r["source_id"] for r in c["regimes"]])]
    return c


def rate_regime_pair(F: str, T: str, fx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    import live_fiat_reference
    fx = fx if fx is not None else load_rate_snapshot()
    return live_fiat_reference.pair_regime_view(F, T, live_fiat_snapshot(), fx)


def _regime_sides(F: str, T: str) -> List[Dict[str, Any]]:
    return [rate_regime_view(c) for c in (F, T) if is_rate_regime_governed(c)]


def _regime_block(rv: Dict[str, Any], eff: Dict[str, Any], fx: Dict[str, Any]) -> str:
    lines = [_cited_line(c, "ISO 4217: ") for c in rv["identity_claims"]]
    state = {"accessible": "issuer site accessible", "unavailable": "issuer site not reachable during the audit",
             "unverified": "no authoritative copy of the issuer's site verified"}.get(rv["issuer_source_state"], rv["issuer_source_state"])
    lines.append(f'<div class="pj-line">Issuer or authority: {esc(rv["issuer_or_authority"])} ({esc(state)})</div>')
    lines.append(f'<div class="pj-line" data-regime-type="{esc(rv["regime_type"])}">Rate regime: '
                 f'{esc(REGIME_TYPE_LABELS[rv["regime_type"]])}</div>')
    for r in rv["regimes_resolved"]:
        when = f" · valuation date {r['valuation_date']}" if r["valuation_date"] else ""
        val = (REGIME_VALUE_WITHHELD.get(r["license_state"], "value not republished") if r["value"] is None
               else f"{r['value']} ({r['unit']})")
        lines.append(f'<div class="pj-line" data-regime-id="{esc(r["regime_id"])}" data-evidence="{esc(r["evidence_state"])}">'
                     f'{esc(r["regime_label"])} — {esc(EVIDENCE_LABELS[r["evidence_state"]])}{esc(when)} · {esc(val)} · '
                     f'<a href="{esc(r["source"]["url"])}">{esc(r["source"]["authority"])}</a></div>')
    lines += [_cited_line(c, "Reported (secondary source): " if c["secondary"] else "") for c in rv["regime_claims"]]
    lines += [_cited_line(c, "Provider coverage: ") for c in rv["coverage_claims"]]
    prov = rv["provider"]
    lines.append(f'<div class="pj-line" data-provider-policy="{esc(eff["policy"])}">Provider snapshot '
                 f'({esc(fx.get("source", ""))}, as of {esc(fx.get("as_of", ""))}): {esc(rv["explanations"]["provider"])} '
                 f'Policy: {esc(POLICY_LABELS[eff["policy"]])}.'
                 + (f' {esc(REVERIFY_NOTES[eff["reason"]])}' if eff.get("reason") else "")
                 + f' Regime audit: {esc(prov["provider_as_of"])} ({esc(prov["match_basis"])}).</div>')
    lines.append(f'<div class="pj-line">{esc(rv["explanations"]["official"])} {esc(rv["explanations"]["claims_scope"])}</div>')
    lines.append(f'<div class="pj-line">Authoritative reference: <a href="{currency_hub_href(rv["code"])}">'
                 f'{esc(rv["code"])} — {esc(rv["display_name"])} rate-regime reference →</a></div>')
    body = "\n          ".join(lines)
    return f"""
        <div class="pj-block pj-plain" data-rate-regime-code="{esc(rv["code"])}" data-provider-policy="{esc(eff["policy"])}">
          <div class="pj-head"><span class="pj-badge">RATE REGIME</span> {esc(rv["code"])} — {esc(rv["display_name"])}</div>
          {body}
        </div>"""


def _regime_card(F: str, T: str, fx: Dict[str, Any]) -> str:
    view = rate_regime_pair(F, T, fx)
    blocks = "".join(_regime_block(rate_regime_view(c), view["effective"][c], fx) for c in view["sides"])
    return f"""
  <div class="card" data-rate-regime-card="{esc(view["mode"])}">
    <div class="card-title">Rate-Regime Governance</div>
    <div class="pj-grid">{blocks}
    </div>
  </div>
"""


def _regime_reason(F: str, T: str, fx: Dict[str, Any]) -> str:
    view = rate_regime_pair(F, T, fx)
    parts = []
    for c in view["sides"]:
        rv = rate_regime_view(c)
        e = view["effective"][c]
        if e["policy"] in ("comparison_only", "suppressed", "unresolved"):
            parts.append(rv["decision_reason"] if not e.get("reason") else f"{rv['decision_reason']} {REVERIFY_NOTES[e['reason']]}")
    return " ".join(dict.fromkeys(parts))


def regime_rate_region_html(profile: Dict[str, Any], tokens: Dict[str, str], snapshot: Dict[str, Any]) -> str:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    view = rate_regime_pair(F, T, snapshot)
    card = _regime_card(F, T, snapshot)
    if view["mode"] == "converter":
        base = static_rate_region_html(profile, tokens, snapshot, force_ordinary=True)
        return base.replace(f"\n{STATIC_RATE_END}", card + STATIC_RATE_END)
    sides = view["sides"]
    if view["mode"] == "comparison":
        sr = static_pair_rate(F, T, snapshot)
        main = (f'<span data-value-type="provider_comparison">1 {esc(F)} = {format_rate_value(sr["rate"], sr["sig"])} {esc(T)}</span>')
        badge = f"PROVIDER SNAPSHOT · COMPARISON ONLY · {esc(sr['as_of'])}"
        sub = f"Not a conversion rate — {', '.join(sides)}: several materially different rates exist or the provider value's regime is not the one most users face"
        note = (f"Provider snapshot as of {sr['as_of']} · source: {sr['source']}. Shown for comparison only and not attributed to any "
                f"official rate. {_regime_reason(F, T, snapshot)}")
        vt = "provider_comparison"
    else:
        main = "No rate shown"
        badge = "PROVIDER REGIME UNRESOLVED"
        sub = f"{F} → {T}: the provider value's rate regime is unresolved"
        note = f"No number is shown rather than an unattributed value. {_regime_reason(F, T, snapshot)}"
        vt = "unavailable"
    return f"""{STATIC_RATE_START}
  <div class="rate-banner" id="rate-root" data-from="{esc(F)}" data-to="{esc(T)}" data-mode="rate_regime" data-value-type="{vt}" data-regime-mode="{esc(view["mode"])}">
    <div>
      <div class="rate-main" id="live-rate">{main}</div>
      <div class="rate-sub" id="rate-sub">{esc(sub)}</div>
    </div>
    <div class="rate-badge snap" id="rate-badge">{badge}</div>
  </div>
  <p class="rate-note" id="rate-source">{esc(note)}</p>
{card}{STATIC_RATE_END}"""


def regime_table_region_html(profile: Dict[str, Any], tokens: Dict[str, str], snapshot: Dict[str, Any]) -> str:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    view = rate_regime_pair(F, T, snapshot)
    if view["mode"] == "converter":
        return static_table_region_html(profile, tokens, snapshot, force_ordinary=True)
    text = (f"No conversion table: the {F}/{T} provider value is shown above for comparison only." if view["mode"] == "comparison"
            else f"No conversion table: no {F}/{T} rate is shown while the provider value's regime is unresolved.")
    return f"""{STATIC_TABLE_START}
    <div class="card">
      <p class="result-info" id="table-source">{esc(text)}</p>
    </div>
{STATIC_TABLE_END}"""


def rate_regime_faq_items(items: List[Dict[str, str]], tokens: Dict[str, str], snapshot: Dict[str, Any]) -> List[Dict[str, str]]:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    view = rate_regime_pair(F, T, snapshot)
    sides = _regime_sides(F, T)
    sr = static_pair_rate(F, T, snapshot)
    prov = " ".join(dict.fromkeys(s["explanations"]["provider"] for s in sides))
    if view["mode"] == "converter":
        a1 = (f"This page converts {tokens['FROM_NAME']} to {tokens['TO_NAME']} with a provider reference snapshot "
              f"(as of {sr['as_of']}), labelled with its rate regime. {prov}")
    elif view["mode"] == "comparison":
        a1 = (f"ConvertCCY shows a provider snapshot of 1 {F} = {format_rate_value(sr['rate'], sr['sig'])} {T} (as of {sr['as_of']}) "
              f"for comparison only, not as a conversion rate. {_regime_reason(F, T, snapshot)}")
    else:
        a1 = f"ConvertCCY does not show a {F}/{T} rate. {_regime_reason(F, T, snapshot)}"
    out = [{"q": replace_tokens(FAQ_Q_RATE, tokens), "a": a1}]
    for s in sides:
        for f in s["faq"]:
            if f["q"] not in {i["q"] for i in out}:
                out.append(dict(f))
    if view["mode"] == "converter":
        out += [i for i in items[1:] if i["q"] not in {o["q"] for o in out}]
    return out


def rate_regime_pair_metadata(tokens: Dict[str, str], brand: str = SITE_NAME,
                              fx: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    view = rate_regime_pair(F, T, fx)
    codes = " and ".join(view["sides"])
    if view["mode"] == "converter":
        title = f"{F} to {T} Converter | {brand}"
        description = (f"Convert {tokens['FROM_NAME']} to {tokens['TO_NAME']} with a provider reference snapshot labelled with "
                       f"its rate regime: which {codes} rates exist, who publishes them and what the provider value matches.")
    else:
        title = f"{F} to {T} — Exchange-Rate Regime Reference | {brand}"
        description = (f"Rate-regime reference for {tokens['FROM_NAME']} and {tokens['TO_NAME']}: which {codes} exchange rates exist, "
                       "who publishes them, how the provider value compares and why no converter is offered.")
    return {"title": title, "description": description, "schema_name": title, "schema_description": description}


def rate_regime_overview_html(tokens: Dict[str, str], fx: Dict[str, Any]) -> str:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    paras = [esc(f"{s['explanations']['what']} {s['explanations']['provider']} {s['explanations']['claims_scope']}")
             for s in _regime_sides(F, T)]
    for other in (F, T):
        if not is_rate_regime_governed(other):
            paras.append(f'{esc(other)} ({esc(_cur_name(other))}) is the counter-currency; see its '
                         f'<a href="{currency_hub_href(other)}">{esc(other)} reference</a> for its own pairs.')
    body = "\n".join(f"    <p>{p}</p>" for p in paras)
    return f"""  <section class="section">
    <div class="sec-title">Pair Overview</div>
    <div class="sec-h2">{esc(F)} / {esc(T)} Rate Regimes</div>
{body}
  </section>"""


def apply_rate_regime_semantics(page: str, profile: Dict[str, Any], tokens: Dict[str, str], content: Dict[str, Any],
                                fx: Optional[Dict[str, Any]] = None) -> str:
    """Rewrite metadata, overview, FAQ and JSON-LD of a rate-regime-governed pair. Idempotent; fails closed."""
    fx = fx if fx is not None else load_rate_snapshot()
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    brand = content.get("site_copy", {}).get("brand_name", SITE_NAME)
    view = rate_regime_pair(F, T, fx)
    meta = rate_regime_pair_metadata(tokens, brand, fx)
    for rx, tpl in _META_PATTERNS:
        if len(rx.findall(page)) != 1:
            raise ValueError(f"rate-regime metadata: {rx.pattern} not found exactly once")
        page = rx.sub(lambda _m: tpl.format(title=esc(meta["title"]), description=esc(meta["description"])), page)
    if page.count(_OVERVIEW_START) != 1 or page.count(STATIC_TABLE_START) != 1:
        raise ValueError("rate-regime body anchors not found exactly once")
    if view["mode"] != "converter":
        for rx, new, label in ((_H1_RE, f"<h1>{esc(_cur_name(F))} ({esc(F)}) / {esc(_cur_name(T))} ({esc(T)}) "
                                        f"<em>Exchange-Rate Regime Reference</em></h1>", "h1"),
                               (_SUBTITLE_RE, '<p class="pair-subtitle">Rate-regime reference</p>', "subtitle")):
            if len(rx.findall(page)) != 1:
                raise ValueError(f"rate-regime {label} anchor not found exactly once")
            page = rx.sub(lambda _m, v=new: v, page)
    i = page.index(_OVERVIEW_START)
    j = page.index("\n  </section>", i) + len("\n  </section>")
    page = page[:i] + rate_regime_overview_html(tokens, fx) + page[j:]
    if view["mode"] != "converter":
        t0 = page.rindex('\n  <section class="section">\n', 0, page.index(STATIC_TABLE_START)) + 1
        t1 = page.index(STATIC_TABLE_START)
        page = page[:t0] + '  <section class="section">\n    <div class="sec-title">Value Coverage Status</div>\n' + page[t1:]
    items = rate_regime_faq_items(build_faq_items(profile, content, tokens), tokens, fx)
    page = replace_faq_regions(page, items)
    return replace_webpage_jsonld(page, tokens, items, "rate_regime_governed")



WEBPAGE_JSONLD_START = '<script type="application/ld+json">\n{\n  "@context": "https://schema.org",\n  "@graph": ['


def replace_webpage_jsonld(page: str, tokens: Dict[str, str], faq_items: List[Dict[str, str]], archival: Any) -> str:
    if page.count(WEBPAGE_JSONLD_START) != 1:
        raise ValueError(f"WebPage JSON-LD: anchor found {page.count(WEBPAGE_JSONLD_START)} times (need exactly 1)")
    i = page.index(WEBPAGE_JSONLD_START) + len('<script type="application/ld+json">\n')
    j = page.index("\n</script>", i)
    return page[:i] + pair_webpage_jsonld(tokens, faq_items, archival) + page[j:]


def refresh_historical_instruments(
    currencies: Dict[str, Dict[str, Any]],
    content: Dict[str, Any],
    pair_profiles: Dict[str, Dict[str, Any]],
) -> Tuple[int, int, int]:
    """SEO-A4.2: rewrite ONLY pages whose pair resolves to historical treatment
    (rate regions, FAQ regions, WebPage JSON-LD) plus the hubs of historical/legacy
    codes. Cohort comes from the policy layer, never a code list."""
    snapshot = load_rate_snapshot()
    pol = instrument_policy_layer()
    changed = unchanged = 0
    for profile in pair_profiles.values():
        a, b = profile["from_code"], profile["to_code"]
        if a == b or a not in currencies or b not in currencies:
            continue
        if pair_rate_treatment(a, b, snapshot) != "historical":
            continue
        tokens = make_pair_tokens(profile, currencies)
        path = PAGES_DIR / f'{profile["pair_slug"]}.html'
        old = path.read_text(encoding="utf-8")
        items = rate_aware_faq_items(build_faq_items(profile, content, tokens), tokens, snapshot, currencies)
        new = replace_static_rate_regions(old, profile, tokens, snapshot)
        new = replace_faq_regions(new, items)
        new = replace_webpage_jsonld(new, tokens, items, True)
        new = apply_historical_semantics(new, tokens, content)
        if new != old:
            write_text(path, new)
            changed += 1
        else:
            unchanged += 1
    gov_map = load_governed_currency_map()
    hubs = 0
    for code in currencies:
        if pol.is_historical(code):
            path = BASE_DIR / currency_hub_href(code).lstrip("/")
            html_doc = build_currency_hub_page(code, currencies, gov_map)
            if not path.exists() or path.read_text(encoding="utf-8") != html_doc:
                write_text(path, html_doc)
                hubs += 1
    print(f"Historical instruments: {changed} pair pages changed, {unchanged} unchanged, {hubs} hubs changed")
    return changed, unchanged, hubs


def refresh_standards_special(
    currencies: Dict[str, Dict[str, Any]],
    content: Dict[str, Any],
    pair_profiles: Dict[str, Dict[str, Any]],
) -> Tuple[int, int, int, int]:
    """SEO-A4.3: rewrite ONLY pairs whose policy treatment is standards_special,
    the hubs of ISO 4217 test/no-currency codes, and the sitemap entries the
    deployed robots policy requires. Cohort comes from the policy layer."""
    snapshot = load_rate_snapshot()
    pol = instrument_policy_layer()
    changed = unchanged = 0
    for profile in pair_profiles.values():
        a, b = profile["from_code"], profile["to_code"]
        if a == b or a not in currencies or b not in currencies:
            continue
        if pair_rate_treatment(a, b, snapshot) != "standards_special":
            continue
        tokens = make_pair_tokens(profile, currencies)
        path = PAGES_DIR / f'{profile["pair_slug"]}.html'
        old = path.read_text(encoding="utf-8")
        new = replace_static_rate_regions(old, profile, tokens, snapshot)
        new = apply_standards_semantics(new, tokens, content)
        if new != old:
            write_text(path, new)
            changed += 1
        else:
            unchanged += 1
    gov_map = load_governed_currency_map()
    hubs = 0
    hub_paths: Set[str] = set()
    for code in currencies:
        if pol.is_standards_special(code):
            rel = currency_hub_href(code).lstrip("/")
            path = BASE_DIR / rel
            html_doc = build_currency_hub_page(code, currencies, gov_map)
            if not path.exists() or path.read_text(encoding="utf-8") != html_doc:
                write_text(path, html_doc)
                hubs += 1
                hub_paths.add(rel)
    sitemap_path = BASE_DIR / "sitemap.xml"
    old_xml = sitemap_path.read_text(encoding="utf-8")
    xml, removed, refreshed = apply_sitemap_policy(old_xml, pair_profiles, refresh_paths=hub_paths)
    if xml != old_xml:
        write_text(sitemap_path, xml)
    print(f"Standards special: {changed} pair pages changed, {unchanged} unchanged, {hubs} hubs changed; "
          f"sitemap: {len(removed)} noindex URLs removed, {len(refreshed)} lastmods refreshed")
    return changed, unchanged, hubs, len(removed)


def refresh_precious_metals(
    currencies: Dict[str, Dict[str, Any]],
    content: Dict[str, Any],
    pair_profiles: Dict[str, Dict[str, Any]],
) -> Tuple[int, int, int]:
    """SEO-A4.4: rewrite ONLY pairs whose policy treatment is precious_metal and the
    hubs of precious-metal codes. Cohort comes from the policy layer."""
    snapshot = load_rate_snapshot()
    pol = instrument_policy_layer()
    changed = unchanged = 0
    for profile in pair_profiles.values():
        a, b = profile["from_code"], profile["to_code"]
        if a == b or a not in currencies or b not in currencies:
            continue
        if pair_rate_treatment(a, b, snapshot) != "precious_metal":
            continue
        tokens = make_pair_tokens(profile, currencies)
        path = PAGES_DIR / f'{profile["pair_slug"]}.html'
        old = path.read_text(encoding="utf-8")
        new = replace_static_rate_regions(old, profile, tokens, snapshot)
        new = apply_metal_semantics(new, tokens, content, snapshot)
        if new != old:
            write_text(path, new)
            changed += 1
        else:
            unchanged += 1
    gov_map = load_governed_currency_map()
    hubs = 0
    for code in currencies:
        if pol.is_precious_metal(code):
            path = BASE_DIR / currency_hub_href(code).lstrip("/")
            html_doc = build_currency_hub_page(code, currencies, gov_map)
            if not path.exists() or path.read_text(encoding="utf-8") != html_doc:
                write_text(path, html_doc)
                hubs += 1
    print(f"Precious metals: {changed} pair pages changed, {unchanged} unchanged, {hubs} hubs changed")
    return changed, unchanged, hubs


def refresh_institutional_units(
    currencies: Dict[str, Dict[str, Any]],
    content: Dict[str, Any],
    pair_profiles: Dict[str, Dict[str, Any]],
) -> Tuple[int, int, int]:
    """SEO-A4.5: rewrite ONLY pairs whose policy treatment is institutional_unit and the
    hubs of institutional-unit codes. Cohort comes from the policy layer. Robots stay
    indexable for every institutional class, so the sitemap is unchanged."""
    snapshot = load_rate_snapshot()
    pol = instrument_policy_layer()
    changed = unchanged = 0
    for profile in pair_profiles.values():
        a, b = profile["from_code"], profile["to_code"]
        if a == b or a not in currencies or b not in currencies:
            continue
        if pair_rate_treatment(a, b, snapshot) != "institutional_unit":
            continue
        tokens = make_pair_tokens(profile, currencies)
        path = PAGES_DIR / f'{profile["pair_slug"]}.html'
        old = path.read_text(encoding="utf-8")
        new = replace_static_rate_regions(old, profile, tokens, snapshot)
        new = apply_institutional_semantics(new, tokens, content, snapshot)
        if new != old:
            write_text(path, new)
            changed += 1
        else:
            unchanged += 1
    gov_map = load_governed_currency_map()
    hubs = 0
    for code in currencies:
        if pol.is_institutional_unit(code):
            path = BASE_DIR / currency_hub_href(code).lstrip("/")
            html_doc = build_currency_hub_page(code, currencies, gov_map)
            if not path.exists() or path.read_text(encoding="utf-8") != html_doc:
                write_text(path, html_doc)
                hubs += 1
    print(f"Institutional units: {changed} pair pages changed, {unchanged} unchanged, {hubs} hubs changed")
    return changed, unchanged, hubs


def refresh_live_fiat_coverage(
    currencies: Dict[str, Dict[str, Any]],
    content: Dict[str, Any],
    pair_profiles: Dict[str, Dict[str, Any]],
) -> Tuple[int, int, int]:
    """SEO-A4.6A: rewrite ONLY pairs whose policy treatment is live_fiat_coverage and the
    hubs of covered codes. Cohort comes from the router (governed snapshot + policy
    precedence), never a slug list. Robots stay as resolved by policy (indexable), so
    the sitemap is unchanged."""
    snapshot = load_rate_snapshot()
    changed = unchanged = 0
    for profile in pair_profiles.values():
        a, b = profile["from_code"], profile["to_code"]
        if a == b or a not in currencies or b not in currencies:
            continue
        if pair_rate_treatment(a, b, snapshot) != "live_fiat_coverage":
            continue
        tokens = make_pair_tokens(profile, currencies)
        path = PAGES_DIR / f'{profile["pair_slug"]}.html'
        old = path.read_text(encoding="utf-8")
        new = replace_static_rate_regions(old, profile, tokens, snapshot)
        new = apply_live_fiat_semantics(new, tokens, content, snapshot)
        if new != old:
            write_text(path, new)
            changed += 1
        else:
            unchanged += 1
    gov_map = load_governed_currency_map()
    hubs = 0
    for code in currencies:
        if is_live_fiat(code):
            path = BASE_DIR / currency_hub_href(code).lstrip("/")
            html_doc = build_currency_hub_page(code, currencies, gov_map)
            if not path.exists() or path.read_text(encoding="utf-8") != html_doc:
                write_text(path, html_doc)
                hubs += 1
    print(f"Live-fiat coverage: {changed} pair pages changed, {unchanged} unchanged, {hubs} hubs changed")
    return changed, unchanged, hubs


def refresh_rate_regime_governance(
    currencies: Dict[str, Dict[str, Any]],
    content: Dict[str, Any],
    pair_profiles: Dict[str, Dict[str, Any]],
) -> Tuple[int, int, int]:
    """SEO-A4.6B: rewrite ONLY pairs whose policy treatment is rate_regime_governed and the
    hubs of governed codes. Cohort comes from the router (governed snapshot + precedence).
    Robots, canonicals and the sitemap are unchanged (all classes stay indexable)."""
    snapshot = load_rate_snapshot()
    changed = unchanged = 0
    for profile in pair_profiles.values():
        a, b = profile["from_code"], profile["to_code"]
        if a == b or a not in currencies or b not in currencies:
            continue
        if pair_rate_treatment(a, b, snapshot) != "rate_regime_governed":
            continue
        tokens = make_pair_tokens(profile, currencies)
        path = PAGES_DIR / f'{profile["pair_slug"]}.html'
        old = path.read_text(encoding="utf-8")
        new = replace_static_rate_regions(old, profile, tokens, snapshot)
        new = apply_rate_regime_semantics(new, profile, tokens, content, snapshot)
        if new != old:
            write_text(path, new)
            changed += 1
        else:
            unchanged += 1
    gov_map = load_governed_currency_map()
    hubs = 0
    for code in currencies:
        if is_rate_regime_governed(code):
            path = BASE_DIR / currency_hub_href(code).lstrip("/")
            html_doc = build_currency_hub_page(code, currencies, gov_map)
            if not path.exists() or path.read_text(encoding="utf-8") != html_doc:
                write_text(path, html_doc)
                hubs += 1
    print(f"Rate-regime governance: {changed} pair pages changed, {unchanged} unchanged, {hubs} hubs changed")
    return changed, unchanged, hubs


# ---- SEO-A3.1: rate-aware FAQ truthfulness ----------------------------------
#
# Support status comes ONLY from static_pair_rate() (the validated snapshot).
# Supported pairs keep the default FAQ byte-for-byte. Unsupported pairs:
#   * FAQ "How much is 1 A in B?"  -> states that no reference rate exists
#   * FAQ "Why does the A/B rate change?" and "What affects the value of A
#     against B?" -> corrected ONLY when a side is a code that by definition
#     has no exchange value (instrument_type test_code / no_currency, i.e.
#     XTS, XXX). For metals, units of account, legacy codes and unpublished
#     currencies those generic answers remain true of the real instrument.
#   * "Is this the same as a bank rate?" is generic and true; unchanged.

FAQ_Q_RATE = "How much is 1 {FROM_CODE} in {TO_CODE}?"
FAQ_Q_CHANGE = "Why does the {FROM_CODE}/{TO_CODE} rate change?"
FAQ_Q_VALUE = "What affects the value of {FROM_CODE} against {TO_CODE}?"
NO_EXCHANGE_VALUE_TYPES = {"test_code", "no_currency"}


def rate_aware_faq_items(items: List[Dict[str, str]], tokens: Dict[str, str],
                         snapshot: Dict[str, Any], currencies: Dict[str, Dict[str, Any]]) -> List[Dict[str, str]]:
    F, T = tokens["FROM_CODE"], tokens["TO_CODE"]
    treatment = pair_rate_treatment(F, T, snapshot)
    if treatment == "standards_special":
        return standards_faq_items(tokens)
    if treatment == "precious_metal":
        return metal_faq_items(tokens, snapshot)
    if treatment == "institutional_unit":
        return institutional_faq_items(tokens, snapshot)
    if treatment == "live_fiat_coverage":
        return live_fiat_faq_items(tokens, snapshot)
    if treatment == "rate_regime_governed":
        return rate_regime_faq_items(items, tokens, snapshot)
    if treatment == "historical":
        return historical_faq_items(tokens, snapshot)
    if static_pair_rate(F, T, snapshot) is not None:
        return items
    reason = unsupported_reason(F, T, snapshot)
    policy = instrument_policy_layer()
    no_value = [c for c in (F, T) if policy.resolve(c)["instrument_type"] in NO_EXCHANGE_VALUE_TYPES]
    no_value_text = "; ".join(UNSUPPORTED_CODE_REASONS.get(c, f"{c} has no exchange value") for c in no_value)
    q_rate = replace_tokens(FAQ_Q_RATE, tokens)
    q_change = replace_tokens(FAQ_Q_CHANGE, tokens)
    q_value = replace_tokens(FAQ_Q_VALUE, tokens)
    out = []
    for item in items:
        q, a = item["q"], item["a"]
        if q == q_rate:
            a = (f"ConvertCCY does not currently have a reference rate for {F} to {T} in its "
                 f"reference snapshot: {reason}. No conversion value is shown rather than an estimate.")
        elif no_value and q == q_change:
            a = f"There is no {F}/{T} exchange rate that moves over time: {no_value_text}."
        elif no_value and q == q_value:
            a = f"No market factor sets a value of {F} against {T}: {no_value_text}."
        out.append({"q": q, "a": a})
    return out


FAQ_VISIBLE_START = '    <div class="sec-title">FAQ</div>\n    <div class="card">\n      '
FAQ_VISIBLE_END = '\n    </div>\n  </section>'
FAQ_JSONLD_START = '<script type="application/ld+json">\n{\n  "@context": "https://schema.org",\n  "@type": "FAQPage",'
FAQ_JSONLD_END = '\n</script>'


def replace_faq_regions(page: str, items: List[Dict[str, str]]) -> str:
    """Rewrite ONLY the visible FAQ list and the FAQPage JSON-LD body. Fail closed."""
    for anchor, label in ((FAQ_VISIBLE_START, "visible FAQ"), (FAQ_JSONLD_START, "FAQPage JSON-LD")):
        if page.count(anchor) != 1:
            raise ValueError(f"{label}: anchor found {page.count(anchor)} times (need exactly 1)")
    i = page.index(FAQ_VISIBLE_START) + len(FAQ_VISIBLE_START)
    j = page.index(FAQ_VISIBLE_END, i)
    page = page[:i] + faq_items_html(items) + page[j:]
    i = page.index(FAQ_JSONLD_START) + len('<script type="application/ld+json">\n')
    j = page.index(FAQ_JSONLD_END, i)
    return page[:i] + faq_jsonld(items) + page[j:]


def refresh_faq_truthfulness(
    currencies: Dict[str, Dict[str, Any]],
    content: Dict[str, Any],
    pair_profiles: Dict[str, Dict[str, Any]],
) -> Tuple[int, int]:
    """SEO-A3.1: rewrite ONLY the FAQ regions, from rate-aware FAQ items."""
    snapshot = load_rate_snapshot()
    changed = unchanged = 0
    for profile in pair_profiles.values():
        a, b = profile["from_code"], profile["to_code"]
        if a == b or a not in currencies or b not in currencies:
            continue
        tokens = make_pair_tokens(profile, currencies)
        items = rate_aware_faq_items(build_faq_items(profile, content, tokens), tokens, snapshot, currencies)
        path = PAGES_DIR / f'{profile["pair_slug"]}.html'
        old = path.read_text(encoding="utf-8")
        new = replace_faq_regions(old, items)
        if new != old:
            write_text(path, new)
            changed += 1
        else:
            unchanged += 1
    print(f"FAQ truthfulness: {changed} pair pages changed, {unchanged} unchanged")
    return changed, unchanged


# -----------------------------------------------------------------------------
# HTML TEMPLATES
# -----------------------------------------------------------------------------

def pair_surface_threshold_body(gov_entry: Dict[str, Any]) -> str:
    """Compact threshold/regime line for pair pages.

    Prefer an optional governed ``pair_surface_summary`` from Passage Check when
    present (mixed declaration / permit / carriage regimes). Otherwise keep the
    legacy numeric join used by ordinary single-threshold jurisdictions:

        declaration at <currency> <value>[ / …]
    """
    summary = str(gov_entry.get("pair_surface_summary") or "").strip()
    if summary:
        return summary
    thresholds = gov_entry.get("thresholds") or []
    if thresholds:
        return "declaration at " + " / ".join(thresholds)
    return ""


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
        decl = c.get("declaration", {}) or {}
        border = c.get("border_cash") or {}
        # Precedence: typed border_cash.pair_surface_summary >
        # legacy declaration.pair_surface_summary > numeric fallback.
        pair_summary = str(border.get("pair_surface_summary") or "").strip()
        if not pair_summary:
            pair_summary = str(decl.get("pair_surface_summary") or "").strip()
        thresholds = decl.get("thresholds", [])
        gov.setdefault(code, []).append({
            "country_name": c.get("country_name", ""),
            "country_slug": c.get("country_slug", ""),
            "rules_page": c.get("rules_page", ""),
            "last_reviewed": c.get("last_reviewed", ""),
            "exch_label": c.get("exchange_controls", {}).get("label", ""),
            "exch_posture": c.get("exchange_controls", {}).get("posture", ""),
            "pair_surface_summary": pair_summary,
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
    either a governed jurisdiction block (border-cash controls, exchange-control
    profile, links to the source-mapped rules page + ontology + Passage Check) when
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
            # Governed: render transcribed border-cash / exchange profile + source links.
            links = " · ".join(
                f'<a href="{esc(g["rules_page"])}">{esc(g["country_name"])} rules →</a>'
                for g in govs if g.get("rules_page")
            )
            thresh_bits = []
            for g in govs:
                body = pair_surface_threshold_body(g)
                if body:
                    thresh_bits.append(
                        f'<strong>{esc(g["country_name"])}:</strong> '
                        + esc(body)
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
    <p>A conversion is a jurisdictional event, not only an arithmetic one. Where ConvertCCY has a published jurisdiction entry associated with a currency, the governed border-cash controls and exchange-control profile are shown below with links to the source-mapped rules entry. Figures are reference-grade; verify against the linked official sources before you travel.</p>
    {macro_html}
    <div class="pj-grid">
      {from_html}
      {to_html}
    </div>
    {corridor}
  </section>"""


def _build_pair_page_base(profile: Dict[str, Any], currencies: Dict[str, Dict[str, Any]], content: Dict[str, Any], all_codes: List[str], gov_map: Dict[str, List[Dict[str, Any]]] = None, importance: Optional[Dict[Tuple[str, str], int]] = None, snapshot: Optional[Dict[str, Any]] = None) -> str:
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
    snapshot = snapshot if snapshot is not None else load_rate_snapshot()
    faq_items = rate_aware_faq_items(build_faq_items(profile, content, tokens), tokens, snapshot, currencies)

    canonical = f'{BASE_URL}/pages/{tokens["PAIR_SLUG"]}.html'
    _treatment = pair_rate_treatment(tokens["FROM_CODE"], tokens["TO_CODE"], snapshot)
    _meta = pair_metadata(tokens, _treatment if _treatment in SPECIAL_TREATMENTS else False, brand)
    title = _meta["title"]
    description = _meta["description"]
    navigation_html = pair_navigation_html(profile["from_code"], profile["to_code"], all_codes, importance)
    static_rate_html = static_rate_region_html(profile, tokens, snapshot)
    static_table_html = static_table_region_html(profile, tokens, snapshot)
    rate_script_html = rate_script_region_html(tokens["FROM_CODE"], tokens["TO_CODE"], snapshot)
    archival = _treatment if _treatment in SPECIAL_TREATMENTS else False
    passage_section = build_currency_passage_section(profile, currencies, tokens, gov_map)

    faq_block_html = faq_items_html(faq_items)

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
{pair_webpage_jsonld(tokens, faq_items, archival)}
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

{static_rate_html}

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
{static_table_html}
  </section>

  <section class="section">
    <div class="sec-title">FAQ</div>
    <div class="card">
      {faq_block_html}
    </div>
  </section>

{navigation_html}
</div>

<footer>
  <p>© 2026 <a href="/">{esc(brand)}</a> — {esc(content.get("footer_copy", {}).get("line_1", "Reference exchange-rate content for informational comparison."))}</p>
  <p style="margin-top:.55rem">{esc(content.get("footer_copy", {}).get("line_2", ""))}</p>
</footer>

{rate_script_html}

</body>
</html>
"""

def build_pair_page(profile: Dict[str, Any], currencies: Dict[str, Dict[str, Any]], content: Dict[str, Any], all_codes: List[str], gov_map: Dict[str, List[Dict[str, Any]]] = None, importance: Optional[Dict[Tuple[str, str], int]] = None, snapshot: Optional[Dict[str, Any]] = None) -> str:
    snapshot = snapshot if snapshot is not None else load_rate_snapshot()
    page = _build_pair_page_base(profile, currencies, content, all_codes, gov_map, importance, snapshot)
    tokens = make_pair_tokens(profile, currencies)
    treatment = pair_rate_treatment(tokens["FROM_CODE"], tokens["TO_CODE"], snapshot)
    if treatment == "historical":
        page = apply_historical_semantics(page, tokens, content)
    elif treatment == "standards_special":
        page = apply_standards_semantics(page, tokens, content)
    elif treatment == "precious_metal":
        page = apply_metal_semantics(page, tokens, content, snapshot)
    elif treatment == "institutional_unit":
        page = apply_institutional_semantics(page, tokens, content, snapshot)
    elif treatment == "live_fiat_coverage":
        page = apply_live_fiat_semantics(page, tokens, content, snapshot)
    elif treatment == "rate_regime_governed":
        page = apply_rate_regime_semantics(page, profile, tokens, content, snapshot)
    return page


def build_currencies_page(currencies: Dict[str, Dict[str, Any]], content: Dict[str, Any]) -> str:
    brand = content.get("site_copy", {}).get("brand_name", SITE_NAME)
    title = f"Global Currencies Index | {brand}"
    description = "Browse major world currencies and explore exchange-rate relationships across the global financial system."

    all_codes = sorted(currencies.keys(), key=lambda x: (x not in DEFAULT_POPULAR_CODES, x))
    cards = []

    pair_total = 2 * (len(all_codes) - 1)
    for code in all_codes:
        cur = currencies[code]
        samples = choose_pair_samples(all_codes, code, limit=3)
        links = "\n".join(
            f'<a href="/pages/{code.lower()}-to-{s.lower()}.html">{esc(code)} → {esc(s)}</a>'
            for s in samples
        )
        hub = currency_hub_href(code)

        cards.append(f"""
        <div class="currency-card">
          <div class="currency-code"><a href="{hub}">{esc(code)}</a></div>
          <div class="currency-name">{esc(cur.get("name", code))}</div>
          <div class="pair-links">{links}</div>
          <a class="hub-link" href="{hub}">All {pair_total} {esc(code)} pairs →</a>
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
.currency-code a{{color:inherit;text-decoration:none}}
.currency-code a:hover{{color:#1a6b3c}}
.hub-link{{display:inline-block;margin-top:8px;font-size:13px;font-weight:600;color:#1a6b3c;text-decoration:none}}
.hub-link:hover{{text-decoration:underline}}
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

INSTRUMENT_TYPE_LABELS = {
    "fiat_currency": "national fiat currency",
    "regional_currency": "regional (multi-country) currency",
    "unit_of_account": "unit of account",
    "legacy_or_transition": "legacy or transition currency code",
    "precious_metal": "precious-metal code (troy ounce)",
    "test_code": "ISO 4217 testing code",
    "no_currency": "ISO 4217 code for transactions without a currency",
}


def build_currency_hub_page(
    code: str,
    currencies: Dict[str, Dict[str, Any]],
    gov_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> str:
    """Navigation hub for one currency: every directed pair from and to it.

    Navigation architecture, not a landing page: identity line from
    currencies.json, links to already-published rules entries (if any), and
    two plain-HTML link lists. No generated prose, no JS navigation.
    """
    gov_map = gov_map or {}
    cur = currencies[code]
    name = cur.get("name", code)
    others = [c for c in site_currency_order(currencies.keys()) if c != code]
    canonical = f"{BASE_URL}{currency_hub_href(code)}"
    title = f"{name} ({code}) Currency Pairs | {SITE_NAME}"
    description = (
        f"All {2 * len(others)} {SITE_NAME} reference pages involving the {name} ({code}): "
        f"convert {code} to {len(others)} currencies and {len(others)} currencies to {code}."
    )

    kind = INSTRUMENT_TYPE_LABELS.get(cur.get("instrument_type", ""), "")
    pol = instrument_policy_layer()
    if pol.is_precious_metal(code):
        kind = "precious-metal code"   # SEO-A4.4: ISO 4217 states no unit; the unit is not asserted here
    if pol.is_institutional_unit(code):
        kind = pol.institutional_view(code)["classification_label"].lower()   # SEO-A4.5: A4.1 taxonomy, not the legacy label
    if is_live_fiat(code):
        kind = live_fiat_view(code)["role_label"][0].lower() + live_fiat_view(code)["role_label"][1:]   # SEO-A4.6A: governed coverage role, not the legacy label
    if pol.is_historical(code):
        hv = pol.historical_view(code)
        kind = ("historical currency" if hv["instrument_type"] == "historical_currency" else "legacy currency code") + \
            (f" (successor {hv['successor_code']})" if hv["successor_code"] else "")
    ident = f"ISO 4217 code {esc(code)}"
    sym = cur.get("symbol", "")
    if sym and sym.upper() != code.upper():
        ident += f" · symbol {esc(sym)}"
    if kind:
        ident += f" · {esc(kind)}"

    rules_links = " · ".join(
        f'<a href="{esc(g["rules_page"])}">{esc(g["country_name"])} foreign-currency rules →</a>'
        for g in gov_map.get(code, []) if g.get("rules_page")
    )
    rules_html = f'\n  <p class="hub-rules">Published jurisdiction entries: {rules_links}</p>' if rules_links else ""
    from_heading = f"Convert {esc(code)} to another currency"
    to_heading = f"Convert another currency to {esc(code)}"
    if pol.is_historical(code):
        # SEO-A4.2.1: historical/legacy hubs are reference indexes, not converter indexes.
        hv = pol.historical_view(code)
        word = "Historical" if hv["instrument_type"] == "historical_currency" else "Legacy"
        state = "withdrawn" if hv["instrument_type"] == "historical_currency" else "superseded"
        succ = hv["successor_code"]
        succ_name = hv["successor_name"] or succ
        title = f"{name} ({code}) {word} Currency Reference | {SITE_NAME}"
        description = (
            f"Reference index for the {state} {name} ({code})"
            + (f", its {succ_name} ({succ}) successor relationship" if succ else "")
            + f", verified historical facts and {2 * len(others)} archived pair references."
        )
        succ_html = (f'<a href="{currency_hub_href(succ)}">{esc(succ)} — {esc(succ_name)}</a>' if succ and hv["successor_in_site"]
                     else (f"{esc(succ)} (not yet covered by ConvertCCY)" if succ else "none recorded"))
        fixed = hv["fixed_conversion"]
        fixed_html = (f' · {esc(HISTORICAL_VALUE_LABELS[fixed["kind"]][0].capitalize())}: '
                      f'<span data-value-type="{fixed["kind"]}">{esc(fixed["statement"])}</span>' if fixed else "")
        rules_html += (f'\n  <p class="hub-rules">{word} currency · {esc(_status_phrase(hv))} · successor {succ_html}{fixed_html}. '
                       f'The pair references below are archival: none presents a current {esc(code)} market rate.</p>')
        from_heading = f"Archived {esc(code)} pair references"
        to_heading = f"Archived pair references into {esc(code)}"
    standards_html = ""
    extra_jsonld = ""
    h1_text = f"{esc(name)} ({esc(code)})"
    if pol.is_standards_special(code):
        # SEO-A4.3: authoritative, indexable ISO 4217 standards reference for this code.
        sv = pol.standards_view(code)
        ex = sv["explanations"]
        role = sv["code_role"]
        role_title = " ".join(w if (w.isupper() or w[0].isdigit()) else "-".join(x.capitalize() for x in w.split("-"))
                              for w in role.split())
        title = f"{code} — ISO 4217 {sv['title_role']} | {SITE_NAME}"
        description = (f"Standards reference for {code}: the {role} (“{sv['iso_designation']['text']}”). "
                       f"What it means, why it has no exchange rate, implementation notes and ISO 4217 provenance.")
        h1_text = f"{esc(code)} — {esc(role_title)}"
        def src(sources):
            return ", ".join(f'<a href="{esc(x["url"])}">{esc(x["authority"])}</a>' for x in sources)
        faq = _standards_faq_core(sv) + [{
            "q": f"Why does ConvertCCY list {code} pair pages?",
            "a": (f"ConvertCCY covers every code in its ISO 4217 set, so pair pages exist for completeness. They are "
                  f"contextual references that are not indexed; this page is the authoritative {code} reference.")}]
        faq_html = "".join(f'\n    <div class="hub-faq"><h3>{esc(i["q"])}</h3><p>{esc(i["a"])}</p></div>' for i in faq)
        claims = "".join(f'\n      <li><span data-claim>{esc(c["text"])}</span> — {src(c["sources"])}</li>' for c in sv["claims"])
        sections = [
            (f"What {esc(code)} means", f'<p>ISO 4217 designation: <span data-claim>“{esc(sv["iso_designation"]["text"])}”</span> — '
                                         f'{src(sv["iso_designation"]["sources"])}.</p>\n    <p>{esc(ex["what"])}</p>'),
            (f"Why {esc(code)} exists", f"<p>{esc(ex['why_exists'])}</p>"),
            (f"Why {esc(code)} has no exchange rate", f"<p>{esc(ex['no_rate'])}</p>"),
            (f"{esc(code)} vs real currencies", f"<p>{esc(ex['not_this'])}</p>"),
            ("Implementation considerations", f"<p>{esc(ex['implementation'])}</p>"),
            ("Source and standards provenance", f"<ul class=\"hub-sources\">{claims}\n    </ul>"),
            (f"{esc(code)} FAQ", faq_html.lstrip("\n")),
        ]
        standards_html = "".join(f"\n\n  <section class=\"hub-std\">\n    <h2>{h}</h2>\n    {b}\n  </section>" for h, b in sections)
        status = (f'\n  <p class="hub-rules" data-instrument-type="{esc(sv["instrument_type"])}" data-converter="none" '
                  f'data-rate-eligible="false" data-pair-indexability="{esc(sv["pair_indexability"])}">'
                  f"Standards code · not a currency · no exchange rate · no conversion.</p>")
        rules_html += status
        from_heading = f"Standards reference examples: {esc(code)} with other codes"
        to_heading = f"Standards reference examples: other codes with {esc(code)}"
        webpage = json.dumps({"@context": "https://schema.org", "@type": "WebPage", "name": title,
                              "url": canonical, "description": description}, ensure_ascii=False, indent=2)
        faq_ld = json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": i["q"], "acceptedAnswer": {"@type": "Answer", "text": i["a"]}} for i in faq]},
            ensure_ascii=False, indent=2)
        extra_jsonld = (f'\n\n<script type="application/ld+json">\n{webpage}\n</script>'
                        f'\n\n<script type="application/ld+json">\n{faq_ld}\n</script>')
    elif pol.is_precious_metal(code):
        # SEO-A4.4: authoritative precious-metal reference (no price until a licensed source is activated).
        mv = pol.metal_view(code)
        ex = mv["explanations"]
        metal = mv["metal_name"]
        priced = mv["activation_state"] == "source_activated"
        title = f"{code} — {metal} {'Price & ' if priced else '/ '}ISO 4217 Reference | {SITE_NAME}"
        description = (f"Reference for {code}, the ISO 4217 code for {metal.lower()}: unit convention, pricing methodology, "
                       f"benchmark licensing status and the benchmark-versus-dealer distinction."
                       + ("" if priced else f" No licensed {metal.lower()} price is currently published."))
        h1_text = f"{esc(code)} — {esc(metal)}"

        def cl(c):
            return (f'<li><span data-claim>{esc(c["text"])}</span> — '
                    + ", ".join(f'<a href="{esc(x["url"])}">{esc(x["authority"])}</a>' for x in c["sources"]) + "</li>")
        faq = [
            {"q": f"What does {code} mean?", "a": f"ISO 4217 lists {code} as “{mv['iso_designation']['text']}”. {ex['what']}"},
            {"q": f"Is {code} a currency?", "a": f"No. {ex['not_this']}"},
            {"q": f"What unit does {code} represent?", "a": f"{mv['unit_convention']} {mv['troy_ounce_definition']['text']}"},
            {"q": f"Does ConvertCCY publish a {metal.lower()} price?",
             "a": f"{mv['pricing_reason']} {mv['licensing_claims'][1]['text']}" if not priced else "Yes, with source, timestamp and value type."},
            {"q": f"Why may a {metal.lower()} reference value differ from a dealer quote?", "a": ex["benchmark_vs_dealer"]},
        ]
        faq_html = "".join(f'\n    <div class="hub-faq"><h3>{esc(i["q"])}</h3><p>{esc(i["a"])}</p></div>' for i in faq)
        sections = [
            (f"What {esc(code)} means", f"<ul class=\"hub-sources\">{chr(10)}      {cl(mv['iso_designation']).replace('<li>', '<li>ISO 4217 designation: ', 1)}{''.join(chr(10) + '      ' + cl(c) for c in mv['claims'])}\n    </ul>\n    <p>{esc(ex['what'])}</p>"),
            ("Unit semantics", f"<p>{esc(mv['unit_convention'])}</p>\n    <ul class=\"hub-sources\">\n      {cl(mv['troy_ounce_definition'])}\n    </ul>"),
            ("Pricing status and methodology",
             f"<p>{esc(mv['pricing_reason'])}</p>\n    <ul class=\"hub-sources\">{''.join(chr(10) + '      ' + cl(c) for c in mv['licensing_claims'])}\n    </ul>\n    <p>{esc(ex['derived'])}</p>"),
            ("Benchmark versus dealer prices", f"<p>{esc(ex['benchmark_vs_dealer'])}</p>"),
            (f"What {esc(code)} is not", f"<p>{esc(ex['not_this'])}</p>"),
            (f"{esc(code)} FAQ", faq_html.lstrip("\n")),
        ]
        standards_html = "".join(f"\n\n  <section class=\"hub-std\">\n    <h2>{h}</h2>\n    {b}\n  </section>" for h, b in sections)
        rules_html += (f'\n  <p class="hub-rules" data-instrument-type="precious_metal" data-converter="valuation_only" '
                       f'data-rate-eligible="true" data-pricing-activation="{esc(mv["activation_state"])}" '
                       f'data-pair-indexability="{esc(mv["pair_indexability"])}">'
                       f"Precious metal · not a currency · {'licensed reference pricing' if priced else 'no licensed price published'}.</p>")
        from_heading = f"Metal valuation references: {esc(code)} with other codes"
        to_heading = f"Metal valuation references: other codes with {esc(code)}"
        webpage = json.dumps({"@context": "https://schema.org", "@type": "WebPage", "name": title,
                              "url": canonical, "description": description}, ensure_ascii=False, indent=2)
        faq_ld = json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": i["q"], "acceptedAnswer": {"@type": "Answer", "text": i["a"]}} for i in faq]},
            ensure_ascii=False, indent=2)
        extra_jsonld = (f'\n\n<script type="application/ld+json">\n{webpage}\n</script>'
                        f'\n\n<script type="application/ld+json">\n{faq_ld}\n</script>')

    elif pol.is_institutional_unit(code):
        # SEO-A4.5: authoritative institutional-unit reference (no value until a licensed issuer source is activated).
        iv = pol.institutional_view(code)
        ex = iv["explanations"]
        title = f"{code} — {iv['display_name']} Reference | {SITE_NAME}"
        description = (f"Institutional reference for {code}, the {iv['display_name']}: "
                       + (f"issuer {iv['issuer_display']}, " if iv["issuer_display"] else "issuer unresolved, ")
                       + "classification, status, purpose, valuation methodology and source provenance. "
                       + ("No issuer value is currently published on ConvertCCY." if iv["value_decision"] != "issuer_value_activated" else ""))
        description = description.strip()
        h1_text = f"{esc(code)} — {esc(iv['display_name'])}"

        def cl(c, prefix=""):
            return (f'<li>{esc(prefix)}<span data-claim>{esc(c["text"])}</span> — '
                    + ", ".join(f'<a href="{esc(x["url"])}">{esc(x["authority"])}</a>' for x in c["sources"]) + "</li>")

        def ul(items):
            return '<ul class="hub-sources">' + "".join(chr(10) + "      " + x for x in items) + "\n    </ul>"
        status = "unresolved" if iv["activity_status"] == "status_unresolved" else iv["activity_status"].replace("_", " ")
        issuer = iv["issuer_display"] or "unresolved — no current issuer publication verified"
        sg = iv["source_governance"]
        gov_rows = "".join(f"\n      <li>{esc(k.replace('_', ' ').capitalize())}: {esc(v)}</li>" for k, v in sg.items())
        faq = list(iv["faq"]) + [{
            "q": f"Does ConvertCCY publish {_code_article(code)} {code} value?",
            "a": f"{ex['value_status']} {ex['valuation']}"}]
        faq_html = "".join(f'\n    <div class="hub-faq"><h3>{esc(i["q"])}</h3><p>{esc(i["a"])}</p></div>' for i in faq)
        related = ""
        if iv["related_unit"]:
            ru = pol.institutional_view(iv["related_unit"])
            related = (f'\n    <p>Related institutional unit: <a href="{currency_hub_href(ru["code"])}">{esc(ru["code"])} — '
                       f'{esc(ru["display_name"])} reference</a>.</p>')
        sections = [
            ("Institutional identity",
             ul([cl(iv["iso_designation"], "ISO 4217 designation: ")])
             + f"\n    <p>Instrument type: {esc(iv['classification_label'])} (A4.1 class <code>{esc(iv['instrument_type'])}</code>) · "
               f"Issuer: {esc(issuer)} · Status: <span data-activity-status=\"{esc(iv['activity_status'])}\">{esc(status)}</span></p>"),
            ("Purpose and role", f"<p>{esc(ex['what'])}</p>\n    <p>{esc(ex['not_this'])}</p>{related}"),
            ("Definition and valuation methodology", ul([cl(c) for c in iv["claims"]])),
            ("Current status", ul([cl(c) for c in iv["activity_claims"]] + [cl(c, "Reported (secondary source): ") for c in iv["reported_indicators"]])
             if (iv["activity_claims"] or iv["reported_indicators"]) else f"<p>{esc(ex['value_status'])}</p>"),
            ("Valuation state",
             f'<p><span class="hub-decision">{esc(iv["decision_label"])}</span> · {esc(ex["value_status"])}</p>\n    <p>{esc(ex["valuation"])}</p>'
             + (("\n    " + ul([cl(c) for c in iv["licensing_claims"]])) if iv["licensing_claims"] else "")),
            ("Source governance", f'<ul class="hub-sources">{gov_rows}\n    </ul>'),
            (f"{esc(code)} FAQ", faq_html.lstrip("\n")),
        ]
        standards_html = "".join(f"\n\n  <section class=\"hub-std\">\n    <h2>{h}</h2>\n    {b}\n  </section>" for h, b in sections)
        rules_html += (f'\n  <p class="hub-rules" data-instrument-type="{esc(iv["instrument_type"])}" data-converter="valuation_only" '
                       f'data-value-decision="{esc(iv["value_decision"])}" data-activity-status="{esc(iv["activity_status"])}" '
                       f'data-pair-indexability="{esc(iv["pair_indexability"])}">'
                       f"Institutional unit · not a circulating currency · {esc(iv['decision_label'].lower())}.</p>")
        from_heading = f"Institutional valuation references: {esc(code)} with other codes"
        to_heading = f"Institutional valuation references: other codes with {esc(code)}"
        webpage = json.dumps({"@context": "https://schema.org", "@type": "WebPage", "name": title,
                              "url": canonical, "description": description}, ensure_ascii=False, indent=2)
        faq_ld = json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": i["q"], "acceptedAnswer": {"@type": "Answer", "text": i["a"]}} for i in faq]},
            ensure_ascii=False, indent=2)
        extra_jsonld = (f'\n\n<script type="application/ld+json">\n{webpage}\n</script>'
                        f'\n\n<script type="application/ld+json">\n{faq_ld}\n</script>')

    elif is_live_fiat(code):
        # SEO-A4.6A: live-fiat coverage reference (no value until a governed source is activated).
        lv = live_fiat_view(code)
        ex = lv["explanations"]
        word = "Code-Status Reference" if lv["instrument_role"] == "transitional_iso_code" else "Coverage Reference"
        title = f"{code} — {lv['display_name']} {word} | {SITE_NAME}"
        description = (f"Reference for {code}, the {lv['display_name']}: ISO identity, "
                       + ("code role, " if lv["instrument_role"] == "transitional_iso_code" else "currency status, ")
                       + f"rate-regime state, source coverage and provenance. "
                       + (f"No governed {code} value is currently published on ConvertCCY."
                          if lv["availability_status"] not in ("live_verified", "live_caveated") else ""))
        description = description.strip()
        h1_text = f"{esc(code)} — {esc(lv['display_name'])}"

        def cl(c, prefix=""):
            return (f'<li>{esc(prefix)}<span data-claim>{esc(c["text"])}</span> — '
                    + ", ".join(f'<a href="{esc(x["url"])}">{esc(x["authority"])}</a>' for x in c["sources"]) + "</li>")

        def ul(items):
            return '<ul class="hub-sources">' + "".join(chr(10) + "      " + x for x in items) + "\n    </ul>"
        issuer = lv["issuer_or_authority"] or "not stated — no issuer publication located"
        operative = ""
        if lv.get("operative_code"):
            op = lv["operative_code"]
            operative = (f'\n    <p data-operative-code="{esc(op)}">Operative code per ISO 4217: <a href="{currency_hub_href(op)}">'
                         f'{esc(op)} — {esc(_cur_name(op))} reference</a>. No value is copied from {esc(op)} to {esc(code)}.</p>')
        prov_rows = "".join(
            f'\n      <li><a href="{esc(s["url"])}">{esc(s["title"])}</a> — {esc(s["authority"])} · tier: {esc(s["source_tier"].replace("_", " "))}'
            f' · accessed {esc(s["accessed"])}</li>' for s in lv["sources_resolved"])
        faq = list(lv["faq"])
        faq_html = "".join(f'\n    <div class="hub-faq"><h3>{esc(i["q"])}</h3><p>{esc(i["a"])}</p></div>' for i in faq)
        sections = [
            ("Identity", ul([cl(c, "ISO 4217: ") for c in lv["identity_claims"]])
             + f"\n    <p>Role: {esc(lv['role_label'])} · Issuer or authority: {esc(issuer)}</p>{operative}"),
            ("Status and role", f"<p>{esc(ex['what'])}</p>"),
            ("Source coverage", ul([cl(c) for c in lv["coverage_claims"]]
                                   + [cl(c, "Reported (secondary source): ") for c in lv["reported_indicators"]])),
            ("Availability and rate regime",
             f'<p><span class="hub-decision" data-availability="{esc(lv["availability_status"])}">{esc(lv["decision_label"])}</span>'
             f' · {esc(ex["value_status"])}</p>\n    <p data-rate-regime="{esc(lv["rate_regime"])}">{esc(ex["regime"])}</p>'),
            ("Provenance", f'<ul class="hub-sources">{prov_rows}\n    </ul>'),
            ("Current limitations", f"<p>{esc(ex['activation'])}</p>"),
            (f"{esc(code)} FAQ", faq_html.lstrip("\n")),
        ]
        standards_html = "".join(f"\n\n  <section class=\"hub-std\">\n    <h2>{h}</h2>\n    {b}\n  </section>" for h, b in sections)
        rules_html += (f'\n  <p class="hub-rules" data-live-fiat-role="{esc(lv["instrument_role"])}" data-converter="none" '
                       f'data-availability="{esc(lv["availability_status"])}" data-rate-regime="{esc(lv["rate_regime"])}">'
                       f"{esc(lv['role_label'])} · {esc(LIVE_FIAT_AVAILABILITY_LABELS[lv['availability_status']])}.</p>")
        from_heading = f"Coverage references: {esc(code)} with other currencies"
        to_heading = f"Coverage references: other currencies with {esc(code)}"
        webpage = json.dumps({"@context": "https://schema.org", "@type": "WebPage", "name": title,
                              "url": canonical, "description": description}, ensure_ascii=False, indent=2)
        faq_ld = json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": i["q"], "acceptedAnswer": {"@type": "Answer", "text": i["a"]}} for i in faq]},
            ensure_ascii=False, indent=2)
        extra_jsonld = (f'\n\n<script type="application/ld+json">\n{webpage}\n</script>'
                        f'\n\n<script type="application/ld+json">\n{faq_ld}\n</script>')

    elif is_rate_regime_governed(code):
        # SEO-A4.6B: rate-regime reference hub (identity, regimes, provider comparison, provenance).
        rv = rate_regime_view(code)
        ex = rv["explanations"]
        import live_fiat_reference as _lfr
        eff = _lfr.effective_provider_policy(code, live_fiat_snapshot(), load_rate_snapshot())
        converter = eff["policy"] in ("secondary_provider_value", "governed_primary")
        if not converter:
            title = f"{code} — {rv['display_name']} Exchange-Rate Regime Reference | {SITE_NAME}"
        description = (f"{rv['display_name']} ({code}): which exchange rates exist ({REGIME_TYPE_LABELS[rv['regime_type']]}), "
                       f"who publishes them, how the provider value compares and how ConvertCCY uses it: {POLICY_LABELS[eff['policy']]}.")

        def cl(c, prefix=""):
            return (f'<li>{esc(prefix)}<span data-claim>{esc(c["text"])}</span> — '
                    + ", ".join(f'<a href="{esc(x["url"])}">{esc(x["authority"])}</a>' for x in c["sources"]) + "</li>")

        def ul(items):
            return '<ul class="hub-sources">' + "".join(chr(10) + "      " + x for x in items) + "\n    </ul>"
        reg_rows = "".join(
            f'\n      <li data-regime-id="{esc(r["regime_id"])}" data-evidence="{esc(r["evidence_state"])}">{esc(r["regime_label"])} — '
            f'{esc(EVIDENCE_LABELS[r["evidence_state"]])}'
            + (f" · valuation date {esc(r['valuation_date'])}" if r["valuation_date"] else "")
            + f" · {esc(REGIME_VALUE_WITHHELD.get(r['license_state'], 'value not republished'))}</li>" for r in rv["regimes_resolved"])
        prov_rows = "".join(
            f'\n      <li><a href="{esc(s["url"])}">{esc(s["title"])}</a> — {esc(s["authority"])} · tier: {esc(s["source_tier"].replace("_", " "))}'
            f' · {"accessible" if s["access_state"] == "accessible" else "not reachable"} on {esc(s["accessed"])}</li>' for s in rv["sources_resolved"])
        faq = list(rv["faq"])
        faq_html = "".join(f'\n    <div class="hub-faq"><h3>{esc(i["q"])}</h3><p>{esc(i["a"])}</p></div>' for i in faq)
        sections = [
            ("Identity", ul([cl(c, "ISO 4217: ") for c in rv["identity_claims"]])
             + f"\n    <p>Issuer or authority: {esc(rv['issuer_or_authority'])}</p>"),
            ("Rate regimes",
             f'<p data-regime-type="{esc(rv["regime_type"])}">{esc(ex["what"])}</p>\n    <ul class="hub-sources">{reg_rows}\n    </ul>'
             + ("\n    " + ul([cl(c, "Reported (secondary source): " if c["secondary"] else "") for c in rv["regime_claims"]])
                if rv["regime_claims"] else "")),
            ("Provider value and how it is used",
             f'<p><span class="hub-decision" data-provider-policy="{esc(eff["policy"])}">{esc(POLICY_LABELS[eff["policy"]].upper())}</span>'
             f' · {esc(ex["provider"])}</p>\n    <p>{esc(rv["decision_reason"])}</p>\n    ' + ul([cl(c) for c in rv["coverage_claims"]])),
            ("Provenance", f'<ul class="hub-sources">{prov_rows}\n    </ul>'),
            ("Current limitations", f"<p>{esc(ex['official'])} {esc(ex['claims_scope'])}</p>"),
            (f"{esc(code)} FAQ", faq_html.lstrip("\n")),
        ]
        standards_html = "".join(f"\n\n  <section class=\"hub-std\">\n    <h2>{h}</h2>\n    {b}\n  </section>" for h, b in sections)
        rules_html += (f'\n  <p class="hub-rules" data-rate-regime="{esc(rv["regime_type"])}" '
                       f'data-converter="{"provider_snapshot" if converter else "none"}" data-provider-policy="{esc(eff["policy"])}">'
                       f"Rate regime: {esc(REGIME_TYPE_LABELS[rv['regime_type']])} · {esc(POLICY_LABELS[eff['policy']])}.</p>")
        if not converter:
            from_heading = f"Rate-regime references: {esc(code)} with other currencies"
            to_heading = f"Rate-regime references: other currencies with {esc(code)}"
        webpage = json.dumps({"@context": "https://schema.org", "@type": "WebPage", "name": title,
                              "url": canonical, "description": description}, ensure_ascii=False, indent=2)
        faq_ld = json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": i["q"], "acceptedAnswer": {"@type": "Answer", "text": i["a"]}} for i in faq]},
            ensure_ascii=False, indent=2)
        extra_jsonld = (f'\n\n<script type="application/ld+json">\n{webpage}\n</script>'
                        f'\n\n<script type="application/ld+json">\n{faq_ld}\n</script>')

    def item(a: str, b: str, label_code: str) -> str:
        other_name = currencies.get(label_code, {}).get("name", label_code)
        return (
            f'<li><a href="{pair_href(a, b)}">{esc(a)} → {esc(b)}</a>'
            f' <span>{esc(other_name)}</span></li>'
        )

    from_items = "\n".join(item(code, o, o) for o in others)
    to_items = "\n".join(item(o, code, o) for o in others)

    breadcrumb = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{BASE_URL}/"},
            {"@type": "ListItem", "position": 2, "name": "Currencies", "item": f"{BASE_URL}/currencies.html"},
            {"@type": "ListItem", "position": 3, "name": f"{code}", "item": canonical},
        ],
    }, ensure_ascii=False, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{canonical}">

<meta property="og:type" content="website">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{canonical}">

<script type="application/ld+json">
{breadcrumb}
</script>{extra_jsonld}

<style>
body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f7f7f5;color:#111;line-height:1.7;margin:0}}
.container{{max-width:1100px;margin:auto;padding:50px 20px 70px}}
nav{{border-bottom:1px solid #e8e8e4;padding:18px 20px;background:#fff}}
nav a{{color:#111;text-decoration:none;margin-right:16px}}
.breadcrumb{{font-size:13px;color:#777;margin-bottom:18px}}
.breadcrumb a{{color:#777;text-decoration:none}}
h1{{font-size:38px;margin:0 0 8px}}
.hub-ident{{color:#555;margin:0 0 6px}}
.hub-rules{{font-size:14px;margin:0 0 6px}}
.hub-rules a{{color:#1a6b3c;text-decoration:none}}
h2{{margin-top:44px;font-size:22px}}
.pair-list{{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:6px 16px}}
.pair-list li{{font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.pair-list a{{color:#1a6b3c;text-decoration:none;font-weight:600}}
.pair-list a:hover{{text-decoration:underline}}
.pair-list span{{color:#777}}
footer{{border-top:1px solid #e8e8e4;padding:30px;text-align:center;margin-top:80px;color:#777;font-size:14px}}
footer a{{color:#777}}
</style>
</head>
<body>
<nav><a href="/">{SITE_NAME}</a><a href="/currencies.html">Currencies</a></nav>
<div class="container">
  <div class="breadcrumb"><a href="/">Home</a> › <a href="/currencies.html">Currencies</a> › {esc(code)}</div>
  <h1>{h1_text}</h1>
  <p class="hub-ident">{ident}</p>{rules_html}{standards_html}

  <section>
    <h2>{from_heading}</h2>
    <ul class="pair-list">
{from_items}
    </ul>
  </section>

  <section>
    <h2>{to_heading}</h2>
    <ul class="pair-list">
{to_items}
    </ul>
  </section>
</div>
<footer>
  <p>© 2026 {SITE_NAME} — <a href="/currencies.html">All currencies</a></p>
</footer>
</body>
</html>
"""


def generate_currency_hubs(currencies: Dict[str, Dict[str, Any]]) -> int:
    gov_map = load_governed_currency_map()
    for code in currencies:
        write_text(BASE_DIR / currency_hub_href(code).lstrip("/"), build_currency_hub_page(code, currencies, gov_map))
    print(f"Generated {len(currencies)} currency hub pages")
    return len(currencies)


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

def sitemap_entries(pair_profiles: Dict[str, Dict[str, Any]]) -> List[Tuple[str, str]]:
    """Ordered (url, repo-relative path) list for the search sitemap."""
    # (url, repo-relative posix path used for lastmod resolution)
    entries: List[Tuple[str, str]] = [(f"{BASE_URL}/", "index.html")]

    # Static + authority pages (only those present on disk).
    authority_pages = STATIC_CORE_PAGES + [
        "governance.html",
        "standard.html",
        "passage-check.html",
        "passage-briefs.html",
        "licensing.html",
        "api.html",
    ]
    seen_pages = set()
    for page in authority_pages:
        if page == "index.html" or page in seen_pages:
            continue
        if file_exists(page):
            entries.append((f"{BASE_URL}/{page}", page.replace("\\", "/")))
            seen_pages.add(page)

    # SEO-A2 currency hubs (/currencies/<code>.html) — the pair crawl path.
    hubs_dir = BASE_DIR / "currencies"
    if hubs_dir.is_dir():
        for f in sorted(hubs_dir.glob("*.html")):
            entries.append((f"{BASE_URL}/currencies/{f.name}", f"currencies/{f.name}"))

    # Directory hubs + their contents (hub index first, then children, sorted).
    def add_dir(dir_name: str, child_glob: str, index_name: str = "index.html"):
        d = BASE_DIR / dir_name
        if not (d / index_name).exists():
            return
        entries.append((f"{BASE_URL}/{dir_name}/", f"{dir_name}/{index_name}"))
        for f in sorted(d.glob(child_glob)):
            if f.name == index_name:
                continue
            # Human HTML only under these hubs. Never emit raw JSON siblings.
            if f.suffix.lower() != ".html":
                continue
            entries.append((f"{BASE_URL}/{dir_name}/{f.name}", f"{dir_name}/{f.name}"))

    add_dir("ontology", "*.html")
    add_dir("articles", "*.html")
    add_dir("briefs", "*.html")
    # Published sovereign layer only: the country rules files, never /preview/.
    add_dir("rules", "*-foreign-currency-rules.html")
    # Static Agent Interface hub (P7A) — human HTML hub only (api/index.html → /api/).
    # Raw api/v1/*.json and llms.txt are intentionally excluded from the search sitemap.
    add_dir("api", "*.html")

    for profile in sorted(pair_profiles.values(), key=lambda p: p["pair_slug"]):
        if not pair_in_search_sitemap(profile["from_code"], profile["to_code"]):
            continue  # SEO-A4.3: noindex pages never belong in the search sitemap
        slug = profile["pair_slug"]
        entries.append((f"{BASE_URL}/pages/{slug}.html", f"pages/{slug}.html"))
    return entries


def pair_in_search_sitemap(from_code: str, to_code: str) -> bool:
    """Only pairs whose deployed policy keeps them indexable are sitemap entries."""
    return pair_robots(from_code, to_code) == INDEXABLE_ROBOTS


def apply_sitemap_policy(
    existing_xml: str,
    pair_profiles: Dict[str, Dict[str, Any]],
    *,
    refresh_paths: Optional[Set[str]] = None,
    history_dates: Optional[Dict[str, str]] = None,
    dirty_paths: Optional[Set[str]] = None,
    today: Optional[str] = None,
) -> Tuple[str, List[str], List[str]]:
    """Remove pair URLs that policy excludes (noindex), refresh lastmod only for
    `refresh_paths` (regenerated files), add missing URLs; every other entry is
    kept byte-for-byte. Returns (xml, removed_urls, refreshed_urls)."""
    if history_dates is None or dirty_paths is None:
        history_dates, dirty_paths, today_iso, _ = build_git_content_lastmod_index(BASE_DIR, today=today)
    else:
        today_iso = today if today is not None else iso_today()
    excluded = {f"{BASE_URL}/pages/{p['pair_slug']}.html" for p in pair_profiles.values()
                if p["from_code"] != p["to_code"] and not pair_in_search_sitemap(p["from_code"], p["to_code"])}
    removed: List[str] = []
    refreshed: List[str] = []
    refresh_urls = {f"{BASE_URL}/{r}": r for r in (refresh_paths or set())}

    def edit(m):
        loc = m.group(1)
        if loc in excluded:
            removed.append(loc)
            return ""
        if loc in refresh_urls:
            lastmod = resolve_content_lastmod(refresh_urls[loc], history_dates or {}, dirty_paths or set(), today_iso)
            block = f"  <url>\n    <loc>{loc}</loc>\n" + (f"    <lastmod>{lastmod}</lastmod>\n" if lastmod else "") + "  </url>\n"
            if block != m.group(0):
                refreshed.append(loc)
            return block
        return m.group(0)

    pruned = _SITEMAP_URL_BLOCK_RE.sub(edit, existing_xml)
    xml, _added = merge_sitemap_additively(pruned, pair_profiles, history_dates=history_dates,
                                           dirty_paths=dirty_paths, today=today_iso)
    return xml, removed, refreshed


def build_sitemap(
    pair_profiles: Dict[str, Dict[str, Any]],
    *,
    history_dates: Optional[Dict[str, str]] = None,
    dirty_paths: Optional[Set[str]] = None,
    today: Optional[str] = None,
    lastmod_index_builder=None,
) -> str:
    """Complete, generator-authoritative SEARCH sitemap.

    Includes, in crawl-priority order: home; static/authority pages; the
    intelligence layer; articles; published /rules/ (never /preview/); human
    API HTML hubs; and all pair pages. Only files that exist on disk are
    emitted.

    SEO-A1:
    - <lastmod> is a trustworthy content-change date (Git history), not the
      sitemap build day. Untrusted dates are omitted, never fabricated.
    - Raw machine-readable api/v1/*.json and llms.txt remain public files but
      are NOT advertised in the search sitemap. Human /api.html and /api/ stay.
    """
    entries = sitemap_entries(pair_profiles)

    if history_dates is None or dirty_paths is None:
        builder = lastmod_index_builder or build_git_content_lastmod_index
        history_dates, dirty_paths, today_iso, elapsed = builder(BASE_DIR, today=today)
        print(f"Sitemap lastmod index: {len(history_dates)} paths from Git history in {elapsed:.2f}s")
    else:
        today_iso = today if today is not None else iso_today()

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    seen_locs: Set[str] = set()
    for url, rel_path in entries:
        if url in seen_locs:
            continue
        seen_locs.add(url)
        lines.append("  <url>")
        lines.append(f"    <loc>{url}</loc>")
        lastmod = resolve_content_lastmod(rel_path, history_dates or {}, dirty_paths or set(), today_iso)
        if lastmod:
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
    importance = build_pair_importance_index(pair_profiles)
    snapshot = load_rate_snapshot()
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

        html_doc = build_pair_page(profile, currencies, content, all_codes, gov_map, importance, snapshot)
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
    generate_currency_hubs(currencies)
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

_SITEMAP_URL_BLOCK_RE = re.compile(
    r"  <url>\n    <loc>([^<]+)</loc>\n(?:    <lastmod>[^<]*</lastmod>\n)?  </url>\n"
)


def merge_sitemap_additively(
    existing_xml: str,
    pair_profiles: Dict[str, Dict[str, Any]],
    *,
    history_dates: Optional[Dict[str, str]] = None,
    dirty_paths: Optional[Set[str]] = None,
    today: Optional[str] = None,
) -> Tuple[str, List[str]]:
    """Add newly required sitemap URLs without touching existing entries.

    Every <url> block already in `existing_xml` is kept byte-for-byte (same
    loc, same lastmod). URLs that sitemap_entries() now requires but the file
    lacks are inserted at their generator-order position with a lastmod from
    the normal resolve_content_lastmod() rules. Raises ValueError if the
    existing file holds a URL the generator no longer emits, or if relative
    order would change — membership and order of existing URLs are frozen.
    """
    head = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    tail = "</urlset>"
    if not existing_xml.startswith(head) or not existing_xml.rstrip("\n").endswith(tail):
        raise ValueError("unexpected sitemap envelope")
    body = existing_xml[len(head):existing_xml.rstrip("\n").rindex(tail)]
    blocks: Dict[str, str] = {}
    order: List[str] = []
    pos = 0
    for m in _SITEMAP_URL_BLOCK_RE.finditer(body):
        if m.start() != pos:
            raise ValueError("unparseable content in existing sitemap")
        blocks[m.group(1)] = m.group(0)
        order.append(m.group(1))
        pos = m.end()
    if pos != len(body):
        raise ValueError("unparseable trailing content in existing sitemap")

    entries = sitemap_entries(pair_profiles)
    wanted = [u for u, _ in entries]
    missing_from_generator = set(order) - set(wanted)
    if missing_from_generator:
        raise ValueError(f"existing sitemap URLs no longer generated: {sorted(missing_from_generator)[:5]}")
    kept_in_order = [u for u in wanted if u in blocks]
    if kept_in_order != order:
        raise ValueError("existing sitemap URL order differs from generator order")

    if history_dates is None or dirty_paths is None:
        history_dates, dirty_paths, today_iso, _ = build_git_content_lastmod_index(BASE_DIR, today=today)
    else:
        today_iso = today if today is not None else iso_today()

    out = [head]
    added: List[str] = []
    seen: Set[str] = set()
    for url, rel_path in entries:
        if url in seen:
            continue
        seen.add(url)
        if url in blocks:
            out.append(blocks[url])
            continue
        lastmod = resolve_content_lastmod(rel_path, history_dates or {}, dirty_paths or set(), today_iso)
        block = f"  <url>\n    <loc>{url}</loc>\n"
        if lastmod:
            block += f"    <lastmod>{lastmod}</lastmod>\n"
        out.append(block + "  </url>\n")
        added.append(url)
    out.append(tail)
    return "".join(out), added


def refresh_pair_navigation(
    currencies: Dict[str, Dict[str, Any]],
    pair_profiles: Dict[str, Dict[str, Any]],
) -> Tuple[int, int]:
    """Rewrite ONLY the navigation region of each existing pair page.

    Everything outside PAIR_NAV_START_MARKER..PAIR_NAV_END_MARKER (title,
    metadata, prose, passage section, FAQ, rate script) is left byte-for-byte
    as published. Returns (changed, unchanged).
    """
    all_codes = site_currency_order(currencies.keys())
    importance = build_pair_importance_index(pair_profiles)
    changed = unchanged = 0
    for profile in pair_profiles.values():
        a, b = profile["from_code"], profile["to_code"]
        if a == b or a not in currencies or b not in currencies:
            continue
        path = PAGES_DIR / f'{profile["pair_slug"]}.html'
        old = path.read_text(encoding="utf-8")
        new = replace_pair_navigation(old, pair_navigation_html(a, b, all_codes, importance))
        if new != old:
            write_text(path, new)
            changed += 1
        else:
            unchanged += 1
    print(f"Navigation refreshed on {changed} pair pages ({unchanged} already current)")
    return changed, unchanged


def refresh_static_rates(
    currencies: Dict[str, Dict[str, Any]],
    pair_profiles: Dict[str, Dict[str, Any]],
) -> Tuple[int, int]:
    """SEO-A3: rewrite ONLY the marked static-rate regions of existing pair pages.

    Reads the validated snapshot (data/rate_snapshot.json), recomputes each
    page's STATIC-RATE / STATIC-RATE-TABLE / RATE-SCRIPT regions, and writes a
    page only if a region actually changed. Everything outside the markers
    (prose, metadata, passage section, FAQ, navigation) is left byte-for-byte.
    Fails closed (ValueError) on missing or duplicated markers.
    """
    snapshot = load_rate_snapshot()
    changed = unchanged = 0
    for profile in pair_profiles.values():
        a, b = profile["from_code"], profile["to_code"]
        if a == b or a not in currencies or b not in currencies:
            continue
        path = PAGES_DIR / f'{profile["pair_slug"]}.html'
        old = path.read_text(encoding="utf-8")
        new = replace_static_rate_regions(old, profile, make_pair_tokens(profile, currencies), snapshot)
        if new != old:
            write_text(path, new)
            changed += 1
        else:
            unchanged += 1
    print(f"Static rates (snapshot as_of {snapshot['as_of']}): {changed} pair pages changed, {unchanged} unchanged")
    return changed, unchanged


def run_navigation_only(
    currencies: Dict[str, Dict[str, Any]],
    content: Dict[str, Any],
    pair_profiles: Dict[str, Dict[str, Any]],
) -> None:
    """SEO-A2 navigation-only build: hubs, currencies.html, pair nav regions,
    and additive sitemap entries. Never re-renders pair-page prose."""
    write_text(BASE_DIR / "currencies.html", build_currencies_page(currencies, content))
    generate_currency_hubs(currencies)
    refresh_pair_navigation(currencies, pair_profiles)
    sitemap_path = BASE_DIR / "sitemap.xml"
    xml, added = merge_sitemap_additively(sitemap_path.read_text(encoding="utf-8"), pair_profiles)
    write_text(sitemap_path, xml)
    print(f"Sitemap: added {len(added)} URLs; existing entries unchanged")


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
    parser.add_argument(
        "--navigation-only",
        action="store_true",
        help=(
            "SEO-A2: regenerate currencies.html and the /currencies/ hubs, rewrite "
            "ONLY the navigation region of existing pair pages, and add missing "
            "sitemap URLs without touching existing entries. Pair-page prose, "
            "metadata and scripts are left byte-for-byte as published."
        ),
    )
    parser.add_argument(
        "--static-rates-only",
        action="store_true",
        help=(
            "SEO-A3: rewrite ONLY the marked static-rate regions (rate banner, "
            "converter, conversion table, rate script tag) of existing pair pages "
            "from the validated data/rate_snapshot.json. Pair prose, metadata, "
            "navigation, support pages and sitemap.xml are left untouched."
        ),
    )
    parser.add_argument(
        "--faq-only",
        action="store_true",
        help=(
            "SEO-A3.1: rewrite ONLY the visible FAQ list and FAQPage JSON-LD of "
            "existing pair pages from the rate-aware FAQ items. Everything else "
            "is left byte-for-byte."
        ),
    )
    parser.add_argument(
        "--precious-metals-only",
        action="store_true",
        help=(
            "SEO-A4.4: rewrite only pairs whose policy treatment is precious_metal and the "
            "precious-metal hubs. Sitemap and robots are unchanged (class stays indexable)."
        ),
    )
    parser.add_argument(
        "--institutional-units-only",
        action="store_true",
        help=(
            "SEO-A4.5: rewrite only pairs whose policy treatment is institutional_unit "
            "(XDR/CLF/UYW/XUA/XSU, unless standards/historical/metal precedence governs) and "
            "the institutional-unit hubs. Sitemap and robots are unchanged (classes stay indexable)."
        ),
    )
    parser.add_argument(
        "--live-fiat-coverage-only",
        action="store_true",
        help=(
            "SEO-A4.6A: rewrite only pairs whose policy treatment is live_fiat_coverage "
            "(active fiat codes the FX provider does not publish, governed by "
            "data/live_fiat_reference_snapshot.json) and their hubs. Sitemap and robots unchanged."
        ),
    )
    parser.add_argument(
        "--rate-regime-governance-only",
        action="store_true",
        help=(
            "SEO-A4.6B: rewrite only pairs whose policy treatment is rate_regime_governed "
            "(provider-valued live fiat codes governed by rate_regime_governance in "
            "data/live_fiat_reference_snapshot.json) and their hubs. Sitemap and robots unchanged."
        ),
    )
    parser.add_argument(
        "--standards-special-only",
        action="store_true",
        help=(
            "SEO-A4.3: rewrite only pairs whose policy treatment is standards_special "
            "(ISO 4217 test/no-currency codes), their hubs, and the sitemap entries the "
            "deployed noindex policy requires."
        ),
    )
    parser.add_argument(
        "--historical-instruments-only",
        action="store_true",
        help=(
            "SEO-A4.2: rewrite only pair pages whose pair resolves (via instrument_policy) "
            "to historical/legacy treatment — rate regions, FAQ regions and WebPage JSON-LD — "
            "plus the hubs of historical/legacy codes. Everything else is untouched."
        ),
    )
    args = parser.parse_args()
    only_currencies = parse_only_currencies(args.only_currency)
    modes = (args.navigation_only, args.static_rates_only, args.faq_only, args.historical_instruments_only,
             args.standards_special_only, args.precious_metals_only, args.institutional_units_only,
             args.live_fiat_coverage_only, args.rate_regime_governance_only, only_currencies)
    if sum(bool(x) for x in modes) > 1:
        parser.error("generation modes (--navigation-only, --static-rates-only, --faq-only, --*-only, --only-currency) are mutually exclusive")

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

    if args.rate_regime_governance_only:
        refresh_rate_regime_governance(currencies, content, pair_profiles)
        print("\nRate-regime-governance-only build complete. Sitemap unchanged.")
        return

    if args.live_fiat_coverage_only:
        refresh_live_fiat_coverage(currencies, content, pair_profiles)
        print("\nLive-fiat-coverage-only build complete. Sitemap unchanged.")
        return

    if args.institutional_units_only:
        refresh_institutional_units(currencies, content, pair_profiles)
        print("\nInstitutional-units-only build complete. Sitemap unchanged.")
        return

    if args.precious_metals_only:
        refresh_precious_metals(currencies, content, pair_profiles)
        print("\nPrecious-metals-only build complete. Sitemap unchanged.")
        return

    if args.standards_special_only:
        refresh_standards_special(currencies, content, pair_profiles)
        print("\nStandards-special-only build complete.")
        return

    if args.historical_instruments_only:
        refresh_historical_instruments(currencies, content, pair_profiles)
        print("\nHistorical-instruments-only build complete. Sitemap unchanged.")
        return

    if args.faq_only:
        refresh_faq_truthfulness(currencies, content, pair_profiles)
        print("\nFAQ-only build complete. Support pages and sitemap.xml unchanged.")
        return

    if args.static_rates_only:
        refresh_static_rates(currencies, pair_profiles)
        print("\nStatic-rates-only build complete. Support pages and sitemap.xml unchanged.")
        return

    if args.navigation_only:
        run_navigation_only(currencies, content, pair_profiles)
        print("\nNavigation-only build complete.")
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
