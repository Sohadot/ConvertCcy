#!/usr/bin/env python3
"""
ConvertCCY — Global FX Rules Reference Layer
=============================================
generate_rules.py v1.2.1

Static HTML generator with strict lifecycle separation:
- `rules/` (site root) holds only pages with page_status=`published`
- `preview/rules/<status>/` holds verified / needs_hardening / secondary_review
- `data/generated/rules_manifest.json` records what was emitted and where

All inputs must pass `validate_rules.py` with 0 errors and 0 warnings before render.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

try:
    import rules_schema as rs
    from validate_rules import validate_file, ValidationResult
except Exception as exc:  # pragma: no cover
    print(f"ERROR: could not import rules modules: {exc}", file=sys.stderr)
    sys.exit(2)


# ─────────────────────────────────────────────────────────────────────────────
# Layers (presentation separation)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LayerPaths:
    public_rules: Path
    preview_rules: Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def html_escape(text: Any) -> str:
    return html.escape(str(text), quote=True)


def page_stem(slug: str) -> str:
    return f"{slug}-foreign-currency-rules"


def filename_for_slug(slug: str) -> str:
    return f"{page_stem(slug)}.html"


def public_url(slug: str) -> str:
    return f"https://convertccy.com/rules/{filename_for_slug(slug)}"


def robots_meta(status: str) -> str:
    if status == rs.PageStatus.PUBLISHED.value:
        return "index,follow"
    # Preview / staging surfaces must not leak into indexing
    return "noindex,nofollow"


# ─────────────────────────────────────────────────────────────────────────────
# Presentation assets (single-file layering: kept as named sections)
# ─────────────────────────────────────────────────────────────────────────────

GTM_HEAD = """<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);})(window,document,'script','dataLayer','GTM-TWVB524B');</script>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-2HS37BH07J"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-2HS37BH07J');</script>"""

GTM_NOSCRIPT = """<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-TWVB524B" height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>"""

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500'
    '&family=Sora:wght@300;400;600;700;800&display=swap" rel="stylesheet">'
)

SHARED_NAV = """<nav>
  <a class="logo" href="/">convert<span>ccy</span>.com</a>
  <div class="nav-links">
    <a href="/">Home</a>
    <a href="/currencies.html">Currencies</a>
    <a href="/articles/">Articles</a>
    <a href="/rules/">FX Rules</a>
    <a href="/framework.html">Framework</a>
    <a href="/manifesto.html">Manifesto</a>
    <a href="/about.html">About</a>
  </div>
</nav>"""

SHARED_FOOTER = """<footer>
  <p>&copy; 2026 <a href="/">convertccy.com</a> — Currency conversion and exchange-rate reference for informational comparison.</p>
  <p style="margin-top:.55rem">
    <a href="/about.html">About</a> &nbsp;&middot;&nbsp;
    <a href="/currencies.html">Currencies</a> &nbsp;&middot;&nbsp;
    <a href="/articles/">Articles</a> &nbsp;&middot;&nbsp;
    <a href="/rules/">FX Rules</a> &nbsp;&middot;&nbsp;
    <a href="/framework.html">Framework</a> &nbsp;&middot;&nbsp;
    <a href="/manifesto.html">Manifesto</a> &nbsp;&middot;&nbsp;
    <a href="/contact.html">Contact</a> &nbsp;&middot;&nbsp;
    <a href="/privacy.html">Privacy Policy</a>
  </p>
</footer>"""

SHARED_CSS = """*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#f7f7f5;--surface:#fff;--surface-2:#fcfcfa;--border:#e8e8e4;
  --text:#111110;--muted:#888884;
  --accent:#1a6b3c;--accent-light:#e8f5ee;--accent-border:#c4dfd0;
  --accent2:#f0a500;--accent2-light:#fef8e7;
  --shadow:0 6px 20px rgba(17,17,16,.05);
  --mono:'DM Mono',monospace;--sans:'Sora',sans-serif
}
html{scroll-behavior:smooth}
body{font-family:var(--sans);background:var(--bg);color:var(--text);line-height:1.78;font-size:17px}
a{color:inherit}
nav{position:sticky;top:0;z-index:100;background:rgba(247,247,245,.92);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);padding:0 2rem;display:flex;align-items:center;justify-content:space-between;min-height:58px;gap:1rem;flex-wrap:wrap}
.logo{font-family:var(--mono);font-size:1.05rem;font-weight:500;color:var(--text);text-decoration:none}
.logo span{color:var(--accent)}
.nav-links{display:flex;align-items:center;gap:1.2rem;flex-wrap:wrap}
.nav-links a{font-size:.82rem;color:var(--muted);text-decoration:none;transition:color .18s}
.nav-links a:hover{color:var(--text)}
footer{border-top:1px solid var(--border);text-align:center;padding:2rem;margin-top:3rem;font-size:.78rem;color:var(--muted);font-family:var(--mono)}
footer a{color:var(--muted);text-decoration:none}
footer a:hover{color:var(--text)}
@media(max-width:680px){nav{padding:.8rem 1rem}}
.preview-banner{background:#111110;color:#f7f7f5;border-radius:12px;padding:.75rem 1rem;margin:1rem 0 1.5rem;font-family:var(--mono);font-size:.72rem;line-height:1.55}
.preview-banner strong{color:#fef8e7}
.page-wrap{max-width:860px;margin:0 auto;padding:3.5rem 2rem 5rem}
.breadcrumb{font-family:var(--mono);font-size:.72rem;color:var(--muted);margin-bottom:2rem;display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}
.breadcrumb a{color:var(--muted);text-decoration:none}
.breadcrumb a:hover{color:var(--accent)}
.breadcrumb span{opacity:.4}
.hero-tag{display:inline-block;background:var(--accent-light);color:var(--accent);font-family:var(--mono);font-size:.72rem;padding:4px 14px;border-radius:100px;margin-bottom:1.2rem;border:1px solid var(--accent-border)}
h1{font-size:clamp(1.9rem,4vw,2.8rem);font-weight:800;letter-spacing:-1.2px;line-height:1.1;margin-bottom:1rem}
h1 em{font-style:normal;color:var(--accent)}
.meta-strip{display:flex;gap:1.5rem;flex-wrap:wrap;font-family:var(--mono);font-size:.72rem;color:var(--muted);padding:1rem 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border);margin:1.5rem 0 2.5rem}
.meta-strip strong{color:var(--text)}
h2{font-size:1.1rem;font-weight:700;color:var(--text);margin:2.5rem 0 1rem;letter-spacing:-.02em}
.rule-section{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1rem 1.2rem;margin-bottom:.75rem;box-shadow:var(--shadow)}
.rule-label{font-family:var(--mono);font-size:.68rem;text-transform:uppercase;letter-spacing:.14em;color:var(--accent);margin-bottom:.4rem}
.rule-text{color:#2a2a28;font-size:.93rem;line-height:1.75}
.overview-box{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1.15rem 1.3rem;margin:1.2rem 0 2rem;color:#2a2a28;font-size:.95rem;line-height:1.78;box-shadow:var(--shadow)}
.summary-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin:1.5rem 0}
.summary-box{border-radius:14px;padding:1.1rem 1.2rem}
.summary-box.traveler{background:var(--accent-light);border:1px solid var(--accent-border)}
.summary-box.business{background:var(--accent2-light);border:1px solid #f5d97a}
.summary-box .box-label{font-family:var(--mono);font-size:.66rem;letter-spacing:.16em;text-transform:uppercase;margin-bottom:.4rem}
.summary-box.traveler .box-label{color:var(--accent)}
.summary-box.business .box-label{color:#a07000}
.summary-box p{font-size:.9rem;line-height:1.72;color:#1e4f2f}
.summary-box.business p{color:#5a4000}
.sources-section{margin-top:2.5rem;padding-top:1.5rem;border-top:1px solid var(--border)}
.sources-label{font-family:var(--mono);font-size:.7rem;text-transform:uppercase;letter-spacing:.15em;color:var(--muted);margin-bottom:.8rem}
.source-link{display:flex;justify-content:space-between;align-items:center;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:.75rem 1rem;text-decoration:none;color:var(--text);margin-bottom:.5rem;font-size:.88rem;transition:border-color .15s}
.source-link:hover{border-color:var(--accent-border)}
.source-label{font-weight:600}
.source-type{font-family:var(--mono);font-size:.68rem;color:var(--muted)}
.disclaimer-box{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1rem 1.2rem;margin-top:2.5rem;color:var(--muted);font-size:.83rem;line-height:1.65}
.disclaimer-box strong{color:var(--muted)}
.reviewed-note{font-family:var(--mono);font-size:.72rem;color:var(--muted);margin-top:1rem;text-align:right}
@media(max-width:640px){
  .page-wrap{padding:2.5rem 1rem 4rem}
  h1{font-size:1.7rem}
  .summary-grid{grid-template-columns:1fr}
}"""


def build_country_page_html(data: Dict[str, Any], *, layer: str, rel_path: str) -> str:
    slug = data["country_slug"]
    country = html_escape(data["country_name"])
    currency_c = html_escape(data["currency_code"])
    currency_n = html_escape(data["currency_name"])
    region = html_escape(data["region"])
    iso2 = html_escape(data["iso2"])
    iso3 = html_escape(data["iso3"])
    last_rev = html_escape(data["last_reviewed"])
    status = data["page_status"]
    disclaimer = html_escape(data.get("disclaimer", ""))
    overview = html_escape(data.get("country_overview", ""))

    canonical = public_url(slug)
    robots = robots_meta(status)

    summary = data.get("summary", {})
    summary_t = html_escape(summary.get("traveler", ""))
    summary_b = html_escape(summary.get("business", ""))

    rules = data.get("rules", {})

    def rule(key: str, label: str) -> str:
        text = html_escape(rules.get(key, ""))
        return f"""
    <div class="rule-section">
      <div class="rule-label">{html_escape(label)}</div>
      <div class="rule-text">{text}</div>
    </div>"""

    sources_html = ""
    for src in data.get("source_authorities", []):
        if not isinstance(src, dict):
            continue
        src_label = html_escape(src.get("label", ""))
        src_url = html_escape(src.get("url", ""))
        src_type = html_escape(src.get("type", ""))
        tier = html_escape(src.get("tier", ""))
        sources_html += f"""
      <a class="source-link" href="{src_url}" target="_blank" rel="noopener noreferrer nofollow">
        <span class="source-label">{src_label}</span>
        <span class="source-type">{src_type} · {tier}</span>
      </a>"""

    preview_banner = ""
    if layer == "preview":
        preview_banner = f"""
  <div class="preview-banner">
    <strong>Preview layer ({html_escape(status)}).</strong>
    This page is generated for internal review and is <strong>not indexed</strong>.
    Public URLs under <code>/rules/</code> exist only for <code>published</code> entries.
    Path: <code>{html_escape(rel_path)}</code>
  </div>"""

    schema_json = json.dumps(
        {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "WebPage",
                    "name": f"Foreign Currency Rules — {data['country_name']} | ConvertCCY",
                    "url": canonical,
                    "description": (
                        f"Reference-grade foreign currency rules for {data['country_name']}: "
                        "declaration thresholds, exchange controls, resident and non-resident rules, "
                        "and official sources."
                    ),
                    "dateModified": data["last_reviewed"],
                    "isPartOf": {"@type": "WebSite", "name": "ConvertCCY", "url": "https://convertccy.com/"},
                    "publisher": {"@type": "Organization", "name": "ConvertCCY", "url": "https://convertccy.com/"},
                    "about": {"@type": "Country", "name": data["country_name"]},
                },
                {
                    "@type": "BreadcrumbList",
                    "itemListElement": [
                        {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://convertccy.com/"},
                        {"@type": "ListItem", "position": 2, "name": "FX Rules", "item": "https://convertccy.com/rules/"},
                        {"@type": "ListItem", "position": 3, "name": f"{data['country_name']} FX Rules"},
                    ],
                },
            ]
        },
        indent=2,
        ensure_ascii=False,
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{GTM_HEAD}
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Foreign Currency Rules — {country} ({currency_c}) | ConvertCCY</title>
<meta name="description" content="Reference-grade foreign currency rules for {country}: cash declaration limits, exchange controls, resident and non-resident rules, and official sources.">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{html_escape(canonical)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="ConvertCCY">
<meta property="og:title" content="Foreign Currency Rules — {country} | ConvertCCY">
<meta property="og:description" content="Reference-grade FX rules for {country}: declaration thresholds, exchange controls, and official sources.">
<meta property="og:url" content="{html_escape(canonical)}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{country} Foreign Currency Rules | ConvertCCY">
<meta name="twitter:description" content="Cash declaration limits, exchange controls, and FX rules for {country}.">
{FONTS}
<style>{SHARED_CSS}</style>
<script type="application/ld+json">
{schema_json}
</script>
</head>
<body>
{GTM_NOSCRIPT}
{SHARED_NAV}
<div class="page-wrap">
  <nav class="breadcrumb" aria-label="Breadcrumb">
    <a href="/">Home</a><span>/</span>
    <a href="/rules/">FX Rules</a><span>/</span>
    <span>{country}</span>
  </nav>
{preview_banner}
  <div class="hero-tag">Foreign Currency Rules · {region}</div>
  <h1>{country}:<br><em>Foreign Currency Rules</em></h1>

  <div class="meta-strip">
    <span><strong>Currency:</strong> {currency_c} — {currency_n}</span>
    <span><strong>ISO:</strong> {iso2} / {iso3}</span>
    <span><strong>Last reviewed:</strong> {last_rev}</span>
    <span><strong>Lifecycle:</strong> {html_escape(status)}</span>
    <span><strong>Indexing:</strong> {html_escape('allowed' if data.get('indexing_allowed') is True else 'blocked')}</span>
  </div>

  <h2>Country Overview</h2>
  <div class="overview-box">{overview}</div>

  <h2>Rules at a Glance</h2>
  {rule("bring_foreign_currency_in", "Bringing foreign currency into the country")}
  {rule("take_foreign_currency_out", "Taking foreign currency out of the country")}
  {rule("cash_declaration_threshold", "Cash declaration threshold")}
  {rule("resident_holding_rules", "Rules for residents holding foreign currency")}
  {rule("non_resident_rules", "Rules for non-residents")}
  {rule("business_invoicing_settlement", "Business invoicing and settlement in foreign currency")}
  {rule("exchange_controls", "Exchange controls and approval requirements")}
  {rule("banking_conversion_practicality", "Banking and conversion practicality")}

  <h2>Practical Summaries</h2>
  <div class="summary-grid">
    <div class="summary-box traveler">
      <div class="box-label">Traveler summary</div>
      <p>{summary_t}</p>
    </div>
    <div class="summary-box business">
      <div class="box-label">Business summary</div>
      <p>{summary_b}</p>
    </div>
  </div>

  <div class="sources-section">
    <div class="sources-label">Authority sources (with tier)</div>
    {sources_html}
  </div>

  <div class="disclaimer-box">
    <strong>Disclaimer:</strong> {disclaimer}
  </div>

  <div class="reviewed-note">Last reviewed: {last_rev} · ConvertCCY Reference Layer</div>
</div>
{SHARED_FOOTER}
</body>
</html>"""


def build_public_index_html(published: Sequence[Dict[str, Any]]) -> str:
    count = len(published)
    cards = ""
    for c in sorted(published, key=lambda x: x["country_name"]):
        fn = filename_for_slug(c["country_slug"])
        cards += f"""
      <a class="country-card" href="/rules/{fn}">
        <div class="card-top">
          <span class="card-cur">{html_escape(c['currency_code'])}</span>
          <span class="card-region">{html_escape(c['region'])}</span>
        </div>
        <div class="card-name">{html_escape(c['country_name'])}</div>
        <div class="card-link">View rules →</div>
      </a>"""

    schema = json.dumps(
        {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "CollectionPage",
                    "name": "Foreign Currency Rules by Country",
                    "url": "https://convertccy.com/rules/",
                    "description": (
                        "Reference-grade foreign currency rules by country: declaration thresholds, "
                        "exchange controls, resident and non-resident rules, and official sources."
                    ),
                    "numberOfItems": count,
                    "publisher": {"@type": "Organization", "name": "ConvertCCY", "url": "https://convertccy.com/"},
                },
                {
                    "@type": "BreadcrumbList",
                    "itemListElement": [
                        {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://convertccy.com/"},
                        {"@type": "ListItem", "position": 2, "name": "FX Rules"},
                    ],
                },
            ]
        },
        indent=2,
    )

    # Reuse the same metric layout as before, but keep CSS minimal by extending SHARED_CSS inline.
    index_css = SHARED_CSS + """
.page-wrap{max-width:1080px;margin:0 auto;padding:4rem 2rem 5rem}
.hero{margin-bottom:2.5rem}
.metric-row{display:flex;gap:1rem;flex-wrap:wrap;margin:1.8rem 0 2.5rem}
.metric{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1rem 1.2rem;box-shadow:var(--shadow);flex:1;min-width:140px}
.metric-k{font-size:1.4rem;font-weight:800;letter-spacing:-.04em;margin-bottom:.2rem}
.metric-l{font-family:var(--mono);font-size:.68rem;text-transform:uppercase;letter-spacing:.14em;color:var(--muted)}
.section-label{font-family:var(--mono);font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:1.5px;margin-bottom:1.2rem}
.country-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:.85rem;margin-top:1rem}
.country-card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1.1rem 1.1rem;text-decoration:none;color:var(--text);transition:border-color .15s,transform .15s;box-shadow:var(--shadow)}
.country-card:hover{border-color:var(--accent-border);transform:translateY(-1px)}
.card-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:.4rem}
.card-cur{font-family:var(--mono);font-size:.85rem;font-weight:600;color:var(--accent)}
.card-region{font-family:var(--mono);font-size:.6rem;color:var(--muted);text-align:right;max-width:90px;line-height:1.3}
.card-name{font-size:.95rem;font-weight:700;margin-bottom:.5rem;letter-spacing:-.02em}
.card-link{font-family:var(--mono);font-size:.72rem;color:var(--accent)}
.posture-note{margin-top:3rem;background:var(--accent-light);border:1px solid var(--accent-border);border-radius:14px;padding:1.1rem 1.3rem;color:var(--accent);font-size:.88rem;line-height:1.65}
@media(max-width:680px){.page-wrap{padding:3rem 1rem 4rem}}
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{GTM_HEAD}
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Foreign Currency Rules by Country — FX Controls & Declaration Reference | ConvertCCY</title>
<meta name="description" content="Reference-grade foreign currency rules by country: cash declaration thresholds, exchange controls, resident and non-resident rules, and verified official sources.">
<meta name="robots" content="index,follow">
<link rel="canonical" href="https://convertccy.com/rules/">
{FONTS}
<style>{index_css}</style>
<script type="application/ld+json">
{schema}
</script>
</head>
<body>
{GTM_NOSCRIPT}
{SHARED_NAV}
<div class="page-wrap">
  <nav class="breadcrumb" aria-label="Breadcrumb">
    <a href="/">Home</a><span>/</span><span>FX Rules</span>
  </nav>
  <section class="hero">
    <div class="hero-tag">Public sovereign layer · {count} Countries</div>
    <h1>Foreign Currency Rules<br><em>by Country</em></h1>
    <p class="hero-lead">This index lists only entries explicitly marked <strong>published</strong> in the sovereign reference dataset.</p>
  </section>
  <div class="metric-row">
    <div class="metric"><div class="metric-k">{count}</div><div class="metric-l">Published countries</div></div>
    <div class="metric"><div class="metric-k">Indexed</div><div class="metric-l">Public /rules/</div></div>
  </div>
  <div class="section-label">Published Countries</div>
  <div class="country-grid">
    {cards}
  </div>
  <div class="posture-note">
    <strong>Deployment note.</strong> Preview drafts live under <code>/preview/rules/&lt;status&gt;/</code> and carry <code>noindex</code>.
  </div>
</div>
{SHARED_FOOTER}
</body>
</html>"""


def build_preview_index_html(status: str, items: Sequence[Dict[str, Any]]) -> str:
    count = len(items)
    cards = ""
    for c in sorted(items, key=lambda x: x["country_name"]):
        fn = filename_for_slug(c["country_slug"])
        cards += f"""
      <a class="country-card" href="./{fn}">
        <div class="card-top">
          <span class="card-cur">{html_escape(c['currency_code'])}</span>
          <span class="card-region">{html_escape(c['region'])}</span>
        </div>
        <div class="card-name">{html_escape(c['country_name'])}</div>
        <div class="card-link">Open preview →</div>
      </a>"""

    index_css = SHARED_CSS + """
.page-wrap{max-width:1080px;margin:0 auto;padding:3.5rem 2rem 5rem}
.country-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:.85rem;margin-top:1rem}
.country-card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1.1rem 1.1rem;text-decoration:none;color:var(--text);transition:border-color .15s,transform .15s;box-shadow:var(--shadow)}
.country-card:hover{border-color:var(--accent-border);transform:translateY(-1px)}
.card-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:.4rem}
.card-cur{font-family:var(--mono);font-size:.85rem;font-weight:600;color:var(--accent)}
.card-region{font-family:var(--mono);font-size:.6rem;color:var(--muted);text-align:right;max-width:90px;line-height:1.3}
.card-name{font-size:.95rem;font-weight:700;margin-bottom:.5rem;letter-spacing:-.02em}
.card-link{font-family:var(--mono);font-size:.72rem;color:var(--accent)}
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{GTM_HEAD}
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Preview FX Rules — {html_escape(status)} | ConvertCCY</title>
<meta name="robots" content="noindex,nofollow">
{FONTS}
<style>{index_css}</style>
</head>
<body>
{GTM_NOSCRIPT}
{SHARED_NAV}
<div class="page-wrap">
  <div class="preview-banner">
    <strong>Preview index ({html_escape(status)}).</strong> {count} entr{"y" if count == 1 else "ies"} · not indexed · not sovereign-public until published.
  </div>
  <h1>Preview: {html_escape(status)}</h1>
  <div class="country-grid">
    {cards}
  </div>
</div>
{SHARED_FOOTER}
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Manifest builder
# ─────────────────────────────────────────────────────────────────────────────


def manifest_entry(status: str, data: Dict[str, Any], output_html: Path, site_root: Path) -> Dict[str, Any]:
    slug = data["country_slug"]
    rel = output_html.relative_to(site_root).as_posix()
    eligible = status == rs.PageStatus.PUBLISHED.value and data.get("indexing_allowed") is True

    entry: Dict[str, Any] = {
        "status": status,
        "country_slug": slug,
        "country_name": data.get("country_name"),
        "output_html": rel,
        "sitemap_eligible": bool(eligible),
    }
    if status == rs.PageStatus.PUBLISHED.value:
        entry["public_url"] = public_url(slug)
    return entry


def build_manifest_payload(
    *,
    site_root: Path,
    grouped: Dict[str, List[Tuple[Dict[str, Any], Path]]],
    skipped: List[Dict[str, Any]],
) -> Dict[str, Any]:
    published_entries: List[Dict[str, Any]] = []
    verified_entries: List[Dict[str, Any]] = []
    needs_hardening_entries: List[Dict[str, Any]] = []
    secondary_review_entries: List[Dict[str, Any]] = []
    skipped_entries: List[Dict[str, Any]] = []
    validation_failed_entries: List[Dict[str, Any]] = []

    for item in skipped:
        if item.get("status") == "skipped_validation_failed":
            validation_failed_entries.append(item)
        else:
            skipped_entries.append(item)

    for status, items in grouped.items():
        for data, out_path in items:
            payload = manifest_entry(status, data, out_path, site_root)
            if status == rs.PageStatus.PUBLISHED.value:
                published_entries.append(payload)
            elif status == rs.PageStatus.VERIFIED.value:
                verified_entries.append(payload)
            elif status == rs.PageStatus.NEEDS_HARDENING.value:
                needs_hardening_entries.append(payload)
            elif status == rs.PageStatus.SECONDARY_REVIEW.value:
                secondary_review_entries.append(payload)

    counts = {
        "published": len(published_entries),
        "verified": len(verified_entries),
        "needs_hardening": len(needs_hardening_entries),
        "secondary_review": len(secondary_review_entries),
        "skipped": len(skipped_entries),
        "validation_failed": len(validation_failed_entries),
    }

    return {
        "generated_at": utc_now_iso(),
        "base_url": "https://convertccy.com/",
        "schema_version_target": rs.SCHEMA_VERSION_CURRENT,
        "counts": counts,
        "published_entries": sorted(published_entries, key=lambda e: e.get("country_slug", "")),
        "verified_entries": sorted(verified_entries, key=lambda e: e.get("country_slug", "")),
        "needs_hardening_entries": sorted(needs_hardening_entries, key=lambda e: e.get("country_slug", "")),
        "secondary_review_entries": sorted(secondary_review_entries, key=lambda e: e.get("country_slug", "")),
        "skipped_entries": skipped_entries,
        "validation_failed_entries": validation_failed_entries,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────────


def select_files(data_dir: Path, only: Optional[Sequence[str]]) -> List[Path]:
    if only:
        out: List[Path] = []
        for stem in only:
            p = data_dir / f"{stem}.json"
            if p.exists():
                out.append(p)
            else:
                print(f"[WARN] --only slug not found: {stem}")
        return sorted(set(out))
    return sorted(data_dir.glob("*.json"))


def validate_or_skip(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[ValidationResult]]:
    vr = validate_file(path)
    if vr.ok:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            bad = ValidationResult(path=path)
            bad.error(f"JSON read failed after validation: {exc}")
            return None, bad
        if not isinstance(data, dict):
            bad = ValidationResult(path=path)
            bad.error("Top-level JSON must be an object")
            return None, bad
        return data, vr

    print(f"[FAIL] {path.name}: {len(vr.errors)} error(s), {len(vr.warnings)} warning(s)")
    for err in vr.errors:
        print(f"    {err}")
    for warn in vr.warnings:
        print(f"    {warn}")
    return None, vr


def wipe_dir_contents(dir_path: Path) -> None:
    if not dir_path.exists():
        return
    for child in dir_path.iterdir():
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            wipe_dir_contents(child)
            child.rmdir()


def ensure_clean_output_dirs(layers: LayerPaths) -> None:
    layers.public_rules.mkdir(parents=True, exist_ok=True)
    layers.preview_rules.mkdir(parents=True, exist_ok=True)

    # Public layer: keep only published outputs
    for p in layers.public_rules.glob("*.html"):
        p.unlink()

    # Preview layer: reset per status subfolders we use
    for status in (
        rs.PageStatus.VERIFIED.value,
        rs.PageStatus.NEEDS_HARDENING.value,
        rs.PageStatus.SECONDARY_REVIEW.value,
    ):
        d = layers.preview_rules / status
        wipe_dir_contents(d)


def render_country(
    data: Dict[str, Any],
    *,
    layers: LayerPaths,
    site_root: Path,
) -> Tuple[str, Path]:
    status = data["page_status"]
    slug = data["country_slug"]

    if status == rs.PageStatus.PUBLISHED.value:
        out = layers.public_rules / filename_for_slug(slug)
        rel = out.relative_to(site_root).as_posix()
        html_text = build_country_page_html(data, layer="public", rel_path=rel)
        out.write_text(html_text, encoding="utf-8")
        return status, out

    if status in {
        rs.PageStatus.VERIFIED.value,
        rs.PageStatus.NEEDS_HARDENING.value,
        rs.PageStatus.SECONDARY_REVIEW.value,
    }:
        out_dir = layers.preview_rules / status
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / filename_for_slug(slug)
        rel = out.relative_to(site_root).as_posix()
        html_text = build_country_page_html(data, layer="preview", rel_path=rel)
        out.write_text(html_text, encoding="utf-8")
        return status, out

    raise ValueError(f"Unsupported page_status for rendering: {status}")


def build_rules(
    *,
    site_root: Path,
    data_dir: Path,
    layers: LayerPaths,
    only: Optional[Sequence[str]],
    dry_run: bool,
) -> int:
    files = select_files(data_dir, only)
    if not files:
        print("No input files found.")
        return 2

    validated: List[Tuple[Path, Dict[str, Any]]] = []
    skipped: List[Dict[str, Any]] = []
    failures = 0

    for path in files:
        data, vr = validate_or_skip(path)
        if data is None or vr is None:
            failures += 1
            skipped.append(
                {
                    "status": "skipped_validation_failed",
                    "country_slug": path.stem,
                    "reason": "validation_failed",
                }
            )
            continue
        status = data.get("page_status")
        if status in {rs.PageStatus.NEEDS_REVIEW.value, rs.PageStatus.BLOCKED.value}:
            skipped.append(
                {
                    "status": status,
                    "country_slug": data.get("country_slug", path.stem),
                    "reason": "non_renderable_status",
                }
            )
            continue
        validated.append((path, data))

    print(
        f"Validated OK: {len(validated)} | "
        f"Skipped: {len(skipped)} | "
        f"Failed validation: {failures}"
    )

    if dry_run:
        print("[DRY RUN] No HTML written.")
        return 0 if failures == 0 else 1

    ensure_clean_output_dirs(layers)

    grouped: Dict[str, List[Tuple[Dict[str, Any], Path]]] = {
        rs.PageStatus.PUBLISHED.value: [],
        rs.PageStatus.VERIFIED.value: [],
        rs.PageStatus.NEEDS_HARDENING.value: [],
        rs.PageStatus.SECONDARY_REVIEW.value: [],
    }

    for path, data in validated:
        try:
            status, out_path = render_country(data, layers=layers, site_root=site_root)
            grouped[status].append((data, out_path))
            print(f"[OK] {status}: {out_path.relative_to(site_root).as_posix()}")
        except Exception as exc:
            failures += 1
            print(f"[FAIL] render {path.name}: {exc}")
            skipped.append(
                {
                    "status": data.get("page_status"),
                    "country_slug": data.get("country_slug", path.stem),
                    "reason": f"render_error:{exc}",
                }
            )

    published_payload = [data for data, _ in grouped[rs.PageStatus.PUBLISHED.value]]
    (layers.public_rules / "index.html").write_text(build_public_index_html(published_payload), encoding="utf-8")
    print(f"[OK] public index: {(layers.public_rules / 'index.html').relative_to(site_root).as_posix()}")

    for status in (
        rs.PageStatus.VERIFIED.value,
        rs.PageStatus.NEEDS_HARDENING.value,
        rs.PageStatus.SECONDARY_REVIEW.value,
    ):
        items = [data for data, _ in grouped[status]]
        idx = layers.preview_rules / status / "index.html"
        idx.parent.mkdir(parents=True, exist_ok=True)
        idx.write_text(build_preview_index_html(status, items), encoding="utf-8")
        print(f"[OK] preview index: {idx.relative_to(site_root).as_posix()}")

    manifest_path = site_root / "data" / "generated" / "rules_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest_payload(site_root=site_root, grouped=grouped, skipped=skipped)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[OK] manifest: {manifest_path.relative_to(site_root).as_posix()}")

    # Optional compatibility index for older tooling
    legacy_index = site_root / "data" / "rules_index.json"
    legacy_index.write_text(
        json.dumps(
            [
                {
                    "country_name": d["country_name"],
                    "country_slug": d["country_slug"],
                    "iso2": d["iso2"],
                    "currency_code": d["currency_code"],
                    "region": d["region"],
                    "page_status": d["page_status"],
                    "last_reviewed": d.get("last_reviewed", ""),
                    "url": f"/rules/{filename_for_slug(d['country_slug'])}"
                    if d.get("page_status") == rs.PageStatus.PUBLISHED.value
                    else f"/preview/rules/{d['page_status']}/{filename_for_slug(d['country_slug'])}",
                }
                for d in sorted((data for _, data in validated), key=lambda x: x["country_name"])
            ],
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"[OK] legacy index: {legacy_index.relative_to(site_root).as_posix()}")

    return 0 if failures == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="ConvertCCY rules HTML generator v1.2.1")
    parser.add_argument("--site-root", default=".", help="Repository root")
    parser.add_argument("--data-dir", default="data/rules", help="Input JSON directory")
    parser.add_argument(
        "--public-dir",
        default="rules",
        help="Published sovereign HTML output directory (site-root relative)",
    )
    parser.add_argument("--preview-dir", default="preview/rules", help="Preview output root directory")
    parser.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Optional list of country_slug values to render (without .json)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate only; do not write HTML")
    args = parser.parse_args()

    site_root = Path(args.site_root).resolve()
    data_dir = (site_root / args.data_dir).resolve()
    layers = LayerPaths(
        public_rules=(site_root / args.public_dir).resolve(),
        preview_rules=(site_root / args.preview_dir).resolve(),
    )

    if not data_dir.exists():
        print(f"ERROR: data dir missing: {data_dir}", file=sys.stderr)
        return 2

    return build_rules(
        site_root=site_root,
        data_dir=data_dir,
        layers=layers,
        only=args.only,
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    raise SystemExit(main())
