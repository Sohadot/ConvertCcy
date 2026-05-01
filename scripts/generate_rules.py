"""
ConvertCCY — Global FX Rules Reference Layer
=============================================
generate_rules.py — Static HTML generator for /rules/ layer.
Only generates pages for countries with page_status in PUBLISHABLE_STATUSES
that have passed validate_rules.py.
"""

import json
import html
import re
import sys
from pathlib import Path
from datetime import date

from validate_rules import validate_country_file
from rules_schema import PageStatus, STANDARD_DISCLAIMER

PUBLISHABLE_STATUSES = {PageStatus.PUBLISHED.value, PageStatus.VERIFIED.value}

RULES_DATA_DIR   = Path("data/rules")
RULES_OUTPUT_DIR = Path("rules")
RULES_INDEX_FILE = Path("data/rules_index.json")


# ── Safe escape helper ────────────────────────────────────────────────────────

def e(text: str) -> str:
    """HTML-escape any string before insertion into template."""
    return html.escape(str(text), quote=True)


# ── Slug → page path ──────────────────────────────────────────────────────────

def page_filename(slug: str) -> str:
    return f"{slug}-foreign-currency-rules.html"


def page_url(slug: str) -> str:
    return f"https://convertccy.com/rules/{page_filename(slug)}"


def get_source_authorities(data: dict) -> list:
    """Accept source_authorities and the official_sources alias used by rule data."""
    return data.get("source_authorities") or data.get("official_sources") or []


# ── Nav HTML (shared) ─────────────────────────────────────────────────────────

NAV_HTML = """<nav>
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

GTM_HEAD = """<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);})(window,document,'script','dataLayer','GTM-TWVB524B');</script>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-2HS37BH07J"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-2HS37BH07J');</script>"""

GTM_NOSCRIPT = """<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-TWVB524B" height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>"""

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
@media(max-width:680px){nav{padding:.8rem 1rem}}"""

FOOTER_HTML = """<footer>
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

FONTS = '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Sora:wght@300;400;600;700;800&display=swap" rel="stylesheet">'


# ── Country page generator ────────────────────────────────────────────────────

def generate_country_page(data: dict) -> str:
    slug         = e(data["country_slug"])
    country      = e(data["country_name"])
    currency_c   = e(data["currency_code"])
    currency_n   = e(data["currency_name"])
    region       = e(data["region"])
    iso2         = e(data["iso2"])
    last_rev     = e(data["last_reviewed"])
    disclaimer   = e(data.get("disclaimer", STANDARD_DISCLAIMER))
    url          = page_url(data["country_slug"])
    filename     = page_filename(data["country_slug"])
    overview     = e(data.get("country_overview", ""))

    summary_t    = e(data["summary"]["traveler"])
    summary_b    = e(data["summary"]["business"])

    rules        = data["rules"]
    sources      = get_source_authorities(data)

    def rule(key: str, label: str) -> str:
        text = e(rules.get(key, ""))
        return f"""
    <div class="rule-section">
      <div class="rule-label">{label}</div>
      <div class="rule-text">{text}</div>
    </div>"""

    sources_html = ""
    for src in sources:
        src_label = e(src.get("label", ""))
        src_url   = e(src.get("url", ""))
        src_type  = e(src.get("type", ""))
        sources_html += f"""
      <a class="source-link" href="{src_url}" target="_blank" rel="noopener noreferrer nofollow">
        <span class="source-label">{src_label}</span>
        <span class="source-type">{src_type}</span>
      </a>"""

    schema_json = json.dumps({
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "name": f"Foreign Currency Rules — {data['country_name']} | ConvertCCY",
                "url": url,
                "description": f"Reference-grade foreign currency rules for {data['country_name']}: declaration thresholds, exchange controls, resident and non-resident rules, and official sources.",
                "dateModified": data["last_reviewed"],
                "isPartOf": {"@type": "WebSite", "name": "ConvertCCY", "url": "https://convertccy.com/"},
                "publisher": {"@type": "Organization", "name": "ConvertCCY", "url": "https://convertccy.com/"},
                "about": {"@type": "Country", "name": data["country_name"]}
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://convertccy.com/"},
                    {"@type": "ListItem", "position": 2, "name": "FX Rules", "item": "https://convertccy.com/rules/"},
                    {"@type": "ListItem", "position": 3, "name": f"{data['country_name']} FX Rules"}
                ]
            }
        ]
    }, indent=2, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{GTM_HEAD}
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Foreign Currency Rules — {country} ({currency_c}) | ConvertCCY</title>
<meta name="description" content="Reference-grade foreign currency rules for {country}: cash declaration limits, exchange controls, resident and non-resident rules, and verified official sources.">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{url}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="ConvertCCY">
<meta property="og:title" content="Foreign Currency Rules — {country} | ConvertCCY">
<meta property="og:description" content="Reference-grade FX rules for {country}: declaration thresholds, exchange controls, and official sources.">
<meta property="og:url" content="{url}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{country} Foreign Currency Rules | ConvertCCY">
<meta name="twitter:description" content="Cash declaration limits, exchange controls, and FX rules for {country}.">
{FONTS}
<style>
{SHARED_CSS}
.page-wrap{{max-width:860px;margin:0 auto;padding:3.5rem 2rem 5rem}}
.breadcrumb{{font-family:var(--mono);font-size:.72rem;color:var(--muted);margin-bottom:2rem;display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}}
.breadcrumb a{{color:var(--muted);text-decoration:none}}
.breadcrumb a:hover{{color:var(--accent)}}
.breadcrumb span{{opacity:.4}}
.hero-tag{{display:inline-block;background:var(--accent-light);color:var(--accent);font-family:var(--mono);font-size:.72rem;padding:4px 14px;border-radius:100px;margin-bottom:1.2rem;border:1px solid var(--accent-border)}}
h1{{font-size:clamp(1.9rem,4vw,2.8rem);font-weight:800;letter-spacing:-1.2px;line-height:1.1;margin-bottom:1rem}}
h1 em{{font-style:normal;color:var(--accent)}}
.meta-strip{{display:flex;gap:1.5rem;flex-wrap:wrap;font-family:var(--mono);font-size:.72rem;color:var(--muted);padding:1rem 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border);margin:1.5rem 0 2.5rem}}
.meta-strip strong{{color:var(--text)}}
h2{{font-size:1.1rem;font-weight:700;color:var(--text);margin:2.5rem 0 1rem;letter-spacing:-.02em}}
.rule-section{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1rem 1.2rem;margin-bottom:.75rem;box-shadow:var(--shadow)}}
.rule-label{{font-family:var(--mono);font-size:.68rem;text-transform:uppercase;letter-spacing:.14em;color:var(--accent);margin-bottom:.4rem}}
.rule-text{{color:#2a2a28;font-size:.93rem;line-height:1.75}}
.overview-box{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1.15rem 1.3rem;margin:1.2rem 0 2rem;color:#2a2a28;font-size:.95rem;line-height:1.78;box-shadow:var(--shadow)}}
.summary-grid{{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin:1.5rem 0}}
.summary-box{{border-radius:14px;padding:1.1rem 1.2rem}}
.summary-box.traveler{{background:var(--accent-light);border:1px solid var(--accent-border)}}
.summary-box.business{{background:var(--accent2-light);border:1px solid #f5d97a}}
.summary-box .box-label{{font-family:var(--mono);font-size:.66rem;letter-spacing:.16em;text-transform:uppercase;margin-bottom:.4rem}}
.summary-box.traveler .box-label{{color:var(--accent)}}
.summary-box.business .box-label{{color:#a07000}}
.summary-box p{{font-size:.9rem;line-height:1.72;color:#1e4f2f}}
.summary-box.business p{{color:#5a4000}}
.sources-section{{margin-top:2.5rem;padding-top:1.5rem;border-top:1px solid var(--border)}}
.sources-label{{font-family:var(--mono);font-size:.7rem;text-transform:uppercase;letter-spacing:.15em;color:var(--muted);margin-bottom:.8rem}}
.source-link{{display:flex;justify-content:space-between;align-items:center;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:.75rem 1rem;text-decoration:none;color:var(--text);margin-bottom:.5rem;font-size:.88rem;transition:border-color .15s}}
.source-link:hover{{border-color:var(--accent-border)}}
.source-label{{font-weight:600}}
.source-type{{font-family:var(--mono);font-size:.68rem;color:var(--muted)}}
.disclaimer-box{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1rem 1.2rem;margin-top:2.5rem;color:var(--muted);font-size:.83rem;line-height:1.65}}
.disclaimer-box strong{{color:var(--muted)}}
.reviewed-note{{font-family:var(--mono);font-size:.72rem;color:var(--muted);margin-top:1rem;text-align:right}}
@media(max-width:640px){{
  .page-wrap{{padding:2.5rem 1rem 4rem}}
  h1{{font-size:1.7rem}}
  .summary-grid{{grid-template-columns:1fr}}
}}
</style>
<script type="application/ld+json">
{schema_json}
</script>
</head>
<body>
{GTM_NOSCRIPT}
{NAV_HTML}
<div class="page-wrap">
  <nav class="breadcrumb" aria-label="Breadcrumb">
    <a href="/">Home</a><span>/</span>
    <a href="/rules/">FX Rules</a><span>/</span>
    <span>{country}</span>
  </nav>

  <div class="hero-tag">Foreign Currency Rules · {region}</div>
  <h1>{country}:<br><em>Foreign Currency Rules</em></h1>

  <div class="meta-strip">
    <span><strong>Currency:</strong> {currency_c} — {currency_n}</span>
    <span><strong>ISO:</strong> {iso2} / {data['iso3']}</span>
    <span><strong>Last reviewed:</strong> {last_rev}</span>
    <span><strong>Status:</strong> Reference · Informational</span>
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
    <div class="sources-label">Official authority sources</div>
    {sources_html}
  </div>

  <div class="disclaimer-box">
    <strong>Disclaimer:</strong> {disclaimer}
  </div>

  <div class="reviewed-note">Last reviewed: {last_rev} · ConvertCCY Reference Layer</div>
</div>
{FOOTER_HTML}
</body>
</html>"""


# ── Index page generator ──────────────────────────────────────────────────────

def generate_rules_index(published_countries: list[dict]) -> str:
    count = len(published_countries)

    cards_html = ""
    for c in sorted(published_countries, key=lambda x: x["country_name"]):
        slug    = e(c["country_slug"])
        country = e(c["country_name"])
        cur     = e(c["currency_code"])
        region  = e(c["region"])
        fn      = page_filename(c["country_slug"])
        cards_html += f"""
      <a class="country-card" href="/rules/{fn}">
        <div class="card-top">
          <span class="card-cur">{cur}</span>
          <span class="card-region">{region}</span>
        </div>
        <div class="card-name">{country}</div>
        <div class="card-link">View rules →</div>
      </a>"""

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
<meta property="og:type" content="website">
<meta property="og:site_name" content="ConvertCCY">
<meta property="og:title" content="Foreign Currency Rules by Country | ConvertCCY">
<meta property="og:description" content="Reference-grade FX rules by country: declaration thresholds, exchange controls, and official sources.">
<meta property="og:url" content="https://convertccy.com/rules/">
<meta name="twitter:card" content="summary">
{FONTS}
<style>
{SHARED_CSS}
.page-wrap{{max-width:1080px;margin:0 auto;padding:4rem 2rem 5rem}}
.breadcrumb{{font-family:var(--mono);font-size:.72rem;color:var(--muted);margin-bottom:2rem;display:flex;gap:.45rem;align-items:center;flex-wrap:wrap}}
.breadcrumb a{{color:var(--muted);text-decoration:none}}
.breadcrumb a:hover{{color:var(--accent)}}
.breadcrumb span{{opacity:.45}}
.hero{{margin-bottom:2.5rem}}
.hero-tag{{display:inline-block;background:var(--accent-light);color:var(--accent);font-family:var(--mono);font-size:.74rem;padding:4px 14px;border-radius:100px;margin-bottom:1.1rem;border:1px solid var(--accent-border)}}
h1{{font-size:clamp(2rem,4vw,3rem);font-weight:800;letter-spacing:-1.8px;line-height:1.04;margin-bottom:1rem}}
h1 em{{font-style:normal;color:var(--accent)}}
.hero-lead{{color:#2e2e2b;font-size:1rem;max-width:760px;margin-bottom:.8rem;line-height:1.72}}
.hero-sub{{color:var(--muted);font-size:.9rem;max-width:700px}}
.metric-row{{display:flex;gap:1rem;flex-wrap:wrap;margin:1.8rem 0 2.5rem}}
.metric{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1rem 1.2rem;box-shadow:var(--shadow);flex:1;min-width:140px}}
.metric-k{{font-size:1.4rem;font-weight:800;letter-spacing:-.04em;margin-bottom:.2rem}}
.metric-l{{font-family:var(--mono);font-size:.68rem;text-transform:uppercase;letter-spacing:.14em;color:var(--muted)}}
.section-label{{font-family:var(--mono);font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:1.5px;margin-bottom:1.2rem}}
.country-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:.85rem;margin-top:1rem}}
.country-card{{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1.1rem 1.1rem;text-decoration:none;color:var(--text);transition:border-color .15s,transform .15s;box-shadow:var(--shadow)}}
.country-card:hover{{border-color:var(--accent-border);transform:translateY(-1px)}}
.card-top{{display:flex;justify-content:space-between;align-items:center;margin-bottom:.4rem}}
.card-cur{{font-family:var(--mono);font-size:.85rem;font-weight:600;color:var(--accent)}}
.card-region{{font-family:var(--mono);font-size:.6rem;color:var(--muted);text-align:right;max-width:90px;line-height:1.3}}
.card-name{{font-size:.95rem;font-weight:700;margin-bottom:.5rem;letter-spacing:-.02em}}
.card-link{{font-family:var(--mono);font-size:.72rem;color:var(--accent)}}
.posture-note{{margin-top:3rem;background:var(--accent-light);border:1px solid var(--accent-border);border-radius:14px;padding:1.1rem 1.3rem;color:var(--accent);font-size:.88rem;line-height:1.65}}
@media(max-width:680px){{.page-wrap{{padding:3rem 1rem 4rem}}h1{{font-size:1.9rem}}}}
</style>
<script type="application/ld+json">
{json.dumps({
    "@context": "https://schema.org",
    "@graph": [
        {
            "@type": "CollectionPage",
            "name": "Foreign Currency Rules by Country",
            "url": "https://convertccy.com/rules/",
            "description": "Reference-grade foreign currency rules by country: declaration thresholds, exchange controls, resident and non-resident rules, and official sources.",
            "numberOfItems": count,
            "publisher": {"@type": "Organization", "name": "ConvertCCY", "url": "https://convertccy.com/"}
        },
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://convertccy.com/"},
                {"@type": "ListItem", "position": 2, "name": "FX Rules"}
            ]
        }
    ]
}, indent=2)}
</script>
</head>
<body>
{GTM_NOSCRIPT}
{NAV_HTML}
<div class="page-wrap">
  <nav class="breadcrumb" aria-label="Breadcrumb">
    <a href="/">Home</a><span>/</span><span>FX Rules</span>
  </nav>
  <section class="hero">
    <div class="hero-tag">Global Reference Layer · {count} Countries</div>
    <h1>Foreign Currency Rules<br><em>by Country</em></h1>
    <p class="hero-lead">Reference-grade coverage of foreign currency rules across {count} countries: cash declaration thresholds, exchange controls, resident and non-resident rules, business settlement, and verified official sources.</p>
    <p class="hero-sub">Each page is built from a structured template, verified against official sources, and reviewed for accuracy. This is informational reference — not legal or financial advice.</p>
  </section>
  <div class="metric-row">
    <div class="metric"><div class="metric-k">{count}</div><div class="metric-l">Countries covered</div></div>
    <div class="metric"><div class="metric-k">Verified</div><div class="metric-l">Source-backed</div></div>
    <div class="metric"><div class="metric-k">Structured</div><div class="metric-l">Uniform template</div></div>
    <div class="metric"><div class="metric-k">Reference</div><div class="metric-l">Not legal advice</div></div>
  </div>
  <div class="section-label">Published Countries</div>
  <div class="country-grid">
    {cards_html}
  </div>
  <div class="posture-note">
    <strong>Reference standard.</strong> Each country page follows a uniform structured template with verified official sources and a last-reviewed date. Foreign currency rules change — always verify current rules with the relevant official authority before making financial or travel decisions.
  </div>
</div>
{FOOTER_HTML}
</body>
</html>"""


# ── Sitemap fragment generator ────────────────────────────────────────────────

def generate_sitemap_entries(published_countries: list[dict], today: str) -> str:
    lines = [f"""  <url>
    <loc>https://convertccy.com/rules/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>"""]
    for c in published_countries:
        fn = page_filename(c["country_slug"])
        lines.append(f"""  <url>
    <loc>https://convertccy.com/rules/{fn}</loc>
    <lastmod>{c.get('last_reviewed', today)}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.65</priority>
  </url>""")
    return "\n".join(lines)


# ── rules_index.json ──────────────────────────────────────────────────────────

def generate_rules_index_json(all_countries: list[dict]) -> list[dict]:
    return [
        {
            "country_name":  c["country_name"],
            "country_slug":  c["country_slug"],
            "iso2":          c["iso2"],
            "currency_code": c["currency_code"],
            "region":        c["region"],
            "page_status":   c["page_status"],
            "last_reviewed": c.get("last_reviewed", ""),
            "url":           f"/rules/{page_filename(c['country_slug'])}"
        }
        for c in sorted(all_countries, key=lambda x: x["country_name"])
    ]


# ── Master build function ─────────────────────────────────────────────────────

def build_rules_layer(
    data_dir:   str = "data/rules",
    output_dir: str = "rules",
    dry_run:    bool = False
) -> dict:

    data_path   = Path(data_dir)
    output_path = Path(output_dir)
    today       = date.today().isoformat()

    if not data_path.exists():
        print(f"Data directory not found: {data_dir}")
        return {}

    files = sorted(data_path.glob("*.json"))
    print(f"Found {len(files)} country files in {data_dir}")

    all_countries      = []
    published_countries = []
    skipped_draft      = []
    failed_validation  = []

    for f in files:
        # Validate first
        result = validate_country_file(f)
        if not result.passed:
            print(f"[FAIL] {f.stem}: {len(result.errors)} validation errors")
            for err in result.errors:
                print(f"  {err}")
            failed_validation.append(f.stem)
            continue

        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        all_countries.append(data)

        if data.get("page_status") not in PUBLISHABLE_STATUSES:
            print(f"[SKIP] {data['country_name']} — status: {data['page_status']}")
            skipped_draft.append(data["country_name"])
            continue

        published_countries.append(data)

    print(f"\nPublishable: {len(published_countries)} | "
          f"Draft/skipped: {len(skipped_draft)} | "
          f"Failed validation: {len(failed_validation)}")

    if dry_run:
        print("[DRY RUN] No files written.")
        return {
            "published": len(published_countries),
            "skipped":   len(skipped_draft),
            "failed":    len(failed_validation),
        }

    if not published_countries:
        print("No publishable countries — nothing to generate.")
        return {}

    # Create output directory
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate country pages
    for data in published_countries:
        html_content = generate_country_page(data)
        fn = page_filename(data["country_slug"])
        out = output_path / fn
        out.write_text(html_content, encoding="utf-8")
        print(f"[OK] Generated: rules/{fn}")

    # Generate index page
    index_html = generate_rules_index(published_countries)
    (output_path / "index.html").write_text(index_html, encoding="utf-8")
    print(f"[OK] Generated: rules/index.html ({len(published_countries)} countries)")

    # Generate sitemap fragment
    sitemap_fragment = generate_sitemap_entries(published_countries, today)
    (output_path / "_sitemap_rules_fragment.xml").write_text(
        sitemap_fragment, encoding="utf-8"
    )
    print(f"[OK] Generated: rules/_sitemap_rules_fragment.xml")

    # Generate rules_index.json
    index_json = generate_rules_index_json(all_countries)
    Path("data/rules_index.json").write_text(
        json.dumps(index_json, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"[OK] Generated: data/rules_index.json ({len(all_countries)} countries)")

    return {
        "published": len(published_countries),
        "skipped":   len(skipped_draft),
        "failed":    len(failed_validation),
    }


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ConvertCCY Rules Layer Generator")
    parser.add_argument("--data-dir",   default="data/rules",  help="Input JSON directory")
    parser.add_argument("--output-dir", default="rules",       help="Output HTML directory")
    parser.add_argument("--dry-run",    action="store_true",   help="Validate only, no output")
    args = parser.parse_args()

    result = build_rules_layer(args.data_dir, args.output_dir, args.dry_run)
    print(f"\nBuild complete: {result}")
