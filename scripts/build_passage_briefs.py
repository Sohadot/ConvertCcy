#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_passage_briefs.py — generate governed Country Passage Briefs.

A Passage Brief is the published, source-mapped rules for one jurisdiction in a
portable, print-optimised one-page format (at-a-glance + traveler/business
checklists + official sources). It is NOT new knowledge and NOT gated: the same
facts are free on /rules/. The brief is a *format* — free to read, print-to-PDF
friendly — and the paid editions (business/compliance PDF, bundle, commercial
license) are an extension of the reference, never a tax on it.

Governance:
  - Briefs are built only from PUBLISHED entries (page_status == published).
  - Every figure is transcribed from the governed dataset and each source links
    to the official authority. Nothing is fabricated.
  - Each brief canonicalises to itself and links to its full /rules/ entry
    (the canonical reference) to keep roles distinct.

Inputs:  rules/passage-check.json (structured) + data/rules/<slug>.json (prose+sources)
Outputs: briefs/index.html + briefs/<slug>-passage-brief.html (one per published country)

Run: python3 scripts/build_passage_briefs.py
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PASSAGE = REPO / "rules" / "passage-check.json"
RULES_DIR = REPO / "data" / "rules"
OUT_DIR = REPO / "briefs"
BASE_URL = "https://convertccy.com"


def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


STYLE = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#f7f7f5;--surface:#fff;--surface-2:#fcfcfa;--border:#e8e8e4;--text:#111110;--muted:#888884;--accent:#1a6b3c;--accent-light:#e8f5ee;--accent-border:#c4dfd0;--amber:#a07000;--amber-light:#fef8e7;--shadow:0 8px 24px rgba(17,17,16,.05);--mono:'DM Mono',monospace;--sans:'Sora',sans-serif}
html{scroll-behavior:smooth}
body{font-family:var(--sans);background:var(--bg);color:var(--text);line-height:1.7;font-size:16px}
nav{position:sticky;top:0;z-index:100;background:rgba(247,247,245,.92);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);padding:0 2rem;display:flex;align-items:center;justify-content:space-between;min-height:58px;gap:1rem;flex-wrap:wrap}
.logo{font-family:var(--mono);font-size:1.05rem;font-weight:500;color:var(--text);text-decoration:none}
.logo span{color:var(--accent)}
.nav-links{display:flex;align-items:center;gap:1.1rem;flex-wrap:wrap}
.nav-links a{font-size:.82rem;color:var(--muted);text-decoration:none}
.nav-links a:hover{color:var(--text)}
.wrap{max-width:820px;margin:0 auto;padding:2.6rem 2rem 5rem}
.breadcrumb{font-family:var(--mono);font-size:.72rem;color:var(--muted);margin-bottom:1.6rem}
.breadcrumb a{color:var(--muted);text-decoration:none}
.breadcrumb a:hover{color:var(--accent)}
.brief-tag{display:inline-block;background:var(--accent-light);color:var(--accent);font-family:var(--mono);font-size:.72rem;padding:4px 12px;border-radius:100px;border:1px solid var(--accent-border);margin-bottom:1rem}
h1{font-size:clamp(1.8rem,4vw,2.6rem);font-weight:800;letter-spacing:-1.2px;line-height:1.08;margin-bottom:.5rem}
.sub{font-family:var(--mono);font-size:.82rem;color:var(--muted);margin-bottom:.4rem}
.meta-row{font-family:var(--mono);font-size:.74rem;color:var(--muted);display:flex;gap:.8rem;flex-wrap:wrap;margin:.6rem 0 1.4rem}
.meta-row .ev{color:var(--accent)}
.glance{display:grid;grid-template-columns:1fr 1fr;gap:.8rem;margin:1.4rem 0}
.gcard{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1rem 1.15rem;box-shadow:var(--shadow)}
.gcard .k{font-family:var(--mono);font-size:.64rem;text-transform:uppercase;letter-spacing:.12em;color:var(--accent);margin-bottom:.35rem}
.gcard .v{font-size:.92rem;line-height:1.5}
h2{font-size:1.12rem;font-weight:800;letter-spacing:-.02em;margin:2rem 0 .7rem}
.sec-kicker{font-family:var(--mono);font-size:.66rem;text-transform:uppercase;letter-spacing:.14em;color:var(--accent);margin-top:2rem}
p{color:#2a2a28;line-height:1.75;margin-bottom:.9rem;font-size:.95rem}
.check{list-style:none;margin:.6rem 0 1rem}
.check li{position:relative;padding-left:1.5rem;margin-bottom:.6rem;font-size:.93rem;line-height:1.6;color:#2a2a28}
.check li::before{content:'✓';position:absolute;left:0;color:var(--accent);font-weight:700}
.srcbox{background:var(--surface-2);border:1px solid var(--border);border-radius:12px;padding:1rem 1.2rem;margin:1.2rem 0}
.srcbox .k{font-family:var(--mono);font-size:.64rem;text-transform:uppercase;letter-spacing:.12em;color:var(--accent);margin-bottom:.5rem}
.srcbox ul{list-style:none}
.srcbox li{font-size:.82rem;margin-bottom:.4rem;line-height:1.45}
.srcbox a{color:var(--accent);text-decoration:none;word-break:break-word}
.srcbox a:hover{text-decoration:underline}
.callout{background:var(--accent-light);border:1px solid var(--accent-border);border-radius:12px;padding:1rem 1.2rem;margin:1.4rem 0;font-size:.88rem;color:#1e4f2f;line-height:1.6}
.callout a{color:var(--accent);font-weight:600;text-decoration:none}
.disc{font-size:.8rem;color:var(--muted);line-height:1.6;margin-top:1.6rem;padding-top:1rem;border-top:1px solid var(--border)}
.actions{display:flex;gap:.6rem;flex-wrap:wrap;margin:1.4rem 0}
.btn{font-family:var(--mono);font-size:.8rem;text-decoration:none;padding:.6rem 1rem;border-radius:10px;border:1px solid var(--accent-border);color:var(--accent);background:var(--accent-light)}
.btn:hover{background:#dcefe4}
.btn.print{border-color:var(--border);color:var(--text);background:var(--surface);cursor:pointer}
footer{border-top:1px solid var(--border);text-align:center;padding:2rem;margin-top:3rem;font-size:.76rem;color:var(--muted);font-family:var(--mono)}
footer a{color:var(--muted);text-decoration:none}
footer a:hover{color:var(--text)}
@media(max-width:640px){.glance{grid-template-columns:1fr}.wrap{padding:2rem 1rem 4rem}nav{padding:.8rem 1rem}}
@media print{
  nav,footer,.actions,.brief-tag{display:none!important}
  body{background:#fff;font-size:11.5pt}
  .wrap{max-width:none;padding:0}
  .gcard,.srcbox,.callout{box-shadow:none;break-inside:avoid}
  a{color:#111!important;text-decoration:none}
  .srcbox a{text-decoration:underline}
}
"""

GTM_HEAD = (
    "<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':new Date().getTime(),"
    "event:'gtm.js'});var f=d.getElementsByTagName(s)[0],j=d.createElement(s),dl=l!='dataLayer'?"
    "'&l='+l:'';j.async=true;j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;"
    "f.parentNode.insertBefore(j,f);})(window,document,'script','dataLayer','GTM-TWVB524B');</script>\n"
    "<script async src=\"https://www.googletagmanager.com/gtag/js?id=G-2HS37BH07J\"></script>\n"
    "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
    "gtag('js',new Date());gtag('config','G-2HS37BH07J');</script>"
)

NAV = (
    '<nav>\n  <a href="/" class="logo">convert<span>ccy</span></a>\n'
    '  <div class="nav-links">\n'
    '    <a href="/">Home</a>\n    <a href="/rules/">Rules</a>\n'
    '    <a href="/ontology/">Ontology</a>\n    <a href="/passage-check.html">Passage Check</a>\n'
    '    <a href="/briefs/">Briefs</a>\n    <a href="/governance.html">Governance</a>\n'
    '  </div>\n</nav>'
)

FOOTER = (
    '<footer>\n  <p>© 2026 ConvertCCY. <a href="/rules/">Rules</a> • '
    '<a href="/briefs/">Passage Briefs</a> • <a href="/passage-briefs.html">About Briefs</a> • '
    '<a href="/licensing.html">Licensing</a> • <a href="/governance.html">Governance</a> • '
    '<a href="/disclaimer.html">Disclaimer</a></p>\n</footer>'
)


def brief_jsonld(name: str, url: str, desc: str) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": name,
        "url": url,
        "isAccessibleForFree": True,
        "publisher": {"@type": "Organization", "name": "ConvertCCY", "url": BASE_URL},
        "description": desc,
    }
    return json.dumps(data, ensure_ascii=False)


def render_brief(pc: dict, rules: dict) -> str:
    name = pc["country_name"]
    slug = pc["country_slug"]
    ccy = pc["currency_code"]
    ccy_name = pc.get("currency_name", ccy)
    reviewed = pc.get("last_reviewed", "")
    url = f'{BASE_URL}/briefs/{slug}-passage-brief.html'
    rules_page = f'/rules/{slug}-foreign-currency-rules.html'

    # At-a-glance threshold lines (governed, transcribed).
    th = pc["declaration"]["thresholds"]
    th_html = "<br>".join(
        f'{esc(t["currency"])} {int(t["value"]):,} <span style="color:var(--muted)">({esc(t["scope"])})</span>'
        for t in th
    )
    exch = pc["exchange_controls"]["label"]

    r = rules.get("rules", {})
    summ = rules.get("summary", {})

    def rule(field):
        return esc(r.get(field, "")).strip()

    traveler = esc(summ.get("traveler", "")).strip()
    business = esc(summ.get("business", "")).strip()

    # Source authorities (official links).
    src_items = ""
    for s in rules.get("source_authorities", []):
        lbl = esc(s.get("label", ""))
        u = esc(s.get("url", ""))
        tier = esc(s.get("tier", ""))
        if u:
            src_items += f'<li><a href="{u}" target="_blank" rel="noopener">{lbl}</a>{f" · {tier}" if tier else ""}</li>'

    desc = (f'Governed Country Passage Brief for {name}: declaration threshold, exchange-control posture, '
            f'traveler and business checklists, and official sources — free to read, print-to-PDF ready.')
    title = f'{name} Currency Passage Brief | ConvertCCY'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{GTM_HEAD}
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{esc(url)}">
<meta property="og:type" content="article">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(url)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Sora:wght@300;400;600;700;800&display=swap" rel="stylesheet">
<script type="application/ld+json">
{brief_jsonld(title, url, desc)}
</script>
<style>{STYLE}</style>
</head>
<body>
{NAV}
<div class="wrap">
  <div class="breadcrumb"><a href="/">Home</a> / <a href="/briefs/">Passage Briefs</a> / {esc(name)}</div>
  <span class="brief-tag">Country Passage Brief · Governed reference</span>
  <h1>{esc(name)} — Currency Passage Brief</h1>
  <div class="sub">{esc(ccy)} · {esc(ccy_name)} · {esc(pc.get("region",""))}</div>
  <div class="meta-row">
    <span>Last reviewed: {esc(reviewed)}</span>
    <span class="ev">Evidence: {esc(rules.get("evidence_tier","official_verified"))}</span>
    <span>Free to read · print-to-PDF ready</span>
  </div>

  <div class="glance">
    <div class="gcard"><div class="k">Declaration threshold</div><div class="v">{th_html}</div></div>
    <div class="gcard"><div class="k">Exchange controls</div><div class="v">{esc(exch)}</div></div>
  </div>

  <div class="actions">
    <button class="btn print" onclick="window.print()">Print / Save as PDF</button>
    <a class="btn" href="/passage-check.html?from={esc(slug)}">Open in Passage Check →</a>
    <a class="btn" href="{esc(rules_page)}">Full rules entry →</a>
  </div>

  <div class="sec-kicker">For travellers</div>
  <h2>Carrying cash in or out</h2>
  <p>{traveler}</p>
  <ul class="check">
    <li><strong>Bringing currency in:</strong> {rule("bring_foreign_currency_in")}</li>
    <li><strong>Taking currency out:</strong> {rule("take_foreign_currency_out")}</li>
    <li><strong>Declaration:</strong> {rule("cash_declaration_threshold")}</li>
  </ul>

  <div class="sec-kicker">Residency</div>
  <h2>Resident vs non-resident</h2>
  <ul class="check">
    <li><strong>Residents:</strong> {rule("resident_holding_rules")}</li>
    <li><strong>Non-residents:</strong> {rule("non_resident_rules")}</li>
  </ul>

  <div class="sec-kicker">For business</div>
  <h2>Invoicing, settlement &amp; conversion</h2>
  <p>{business}</p>
  <ul class="check">
    <li><strong>Invoicing &amp; settlement:</strong> {rule("business_invoicing_settlement")}</li>
    <li><strong>Exchange controls:</strong> {rule("exchange_controls")}</li>
    <li><strong>Banking &amp; conversion:</strong> {rule("banking_conversion_practicality")}</li>
  </ul>

  <div class="srcbox">
    <div class="k">Official sources</div>
    <ul>{src_items}</ul>
  </div>

  <div class="callout">
    This brief is a portable format of a free, public reference. The full source-mapped entry — with per-field source mapping — is at <a href="{esc(rules_page)}">the {esc(name)} rules page</a>. Need business/compliance editions, a bundled PDF pack, or a commercial-use licence? See <a href="/passage-briefs.html">Passage Briefs</a> and <a href="/licensing.html">Licensing</a>.
  </div>

  <div class="disc">{esc(rules.get("disclaimer",""))}</div>
  <div class="disc">Governed by ConvertCCY under CRIS v1.0. Figures are reference-grade and transcribed from the official sources above; verify against them before you travel or transact. This brief is not legal, tax, or customs advice.</div>
</div>
{FOOTER}
</body>
</html>
"""


def render_index(briefs: list[dict]) -> str:
    url = f'{BASE_URL}/briefs/'
    cards = ""
    for b in briefs:
        cards += (
            f'<a class="gcard" style="text-decoration:none;color:inherit;display:block" '
            f'href="/briefs/{esc(b["slug"])}-passage-brief.html">'
            f'<div class="k">{esc(b["ccy"])} · reviewed {esc(b["reviewed"])}</div>'
            f'<div class="v" style="font-weight:700;font-size:1rem">{esc(b["name"])}</div>'
            f'<div class="v" style="color:var(--muted);font-size:.82rem">{esc(b["threshold_summary"])}</div></a>'
        )
    desc = ("Governed Country Passage Briefs — portable, print-ready summaries of each published jurisdiction's "
            "currency-passage rules, built from source-mapped official data. Free to read.")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{GTM_HEAD}
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Country Passage Briefs | ConvertCCY</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{esc(url)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Sora:wght@300;400;600;700;800&display=swap" rel="stylesheet">
<style>{STYLE}
.glance{{grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}}
.gcard{{transition:border-color .18s}} .gcard:hover{{border-color:var(--accent)}}
</style>
</head>
<body>
{NAV}
<div class="wrap">
  <div class="breadcrumb"><a href="/">Home</a> / <span>Passage Briefs</span></div>
  <span class="brief-tag">Governed · Free to read</span>
  <h1>Country Passage Briefs</h1>
  <p>Each brief is the published, source-mapped currency-passage rules for one jurisdiction in a portable, print-ready one-page format: declaration threshold at a glance, traveler and business checklists, and links to the official sources. Same governed facts as the <a href="/rules/">rules layer</a> — in a form you can carry.</p>
  <div class="glance">
    {cards}
  </div>
  <div class="callout">
    Briefs are free to read and print. Paid editions — a business/compliance edition, bundled multi-jurisdiction PDF packs, and a commercial-use licence — are an extension of the same reference. See <a href="/passage-briefs.html">about Passage Briefs</a> and <a href="/licensing.html">Licensing</a>.
  </div>
</div>
{FOOTER}
</body>
</html>
"""


def main() -> None:
    if not PASSAGE.exists():
        raise SystemExit("Missing rules/passage-check.json — run scripts/build_passage_check.py first")
    pc_all = json.loads(PASSAGE.read_text())["countries"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    briefs_meta = []
    for pc in sorted(pc_all, key=lambda c: c["country_name"]):
        slug = pc["country_slug"]
        rules_file = RULES_DIR / f"{slug}.json"
        if not rules_file.exists():
            print(f"  skip {slug}: no data/rules/{slug}.json")
            continue
        rules = json.loads(rules_file.read_text())
        if rules.get("page_status") != "published":
            print(f"  skip {slug}: not published ({rules.get('page_status')})")
            continue
        (OUT_DIR / f"{slug}-passage-brief.html").write_text(render_brief(pc, rules))
        th = pc["declaration"]["thresholds"]
        briefs_meta.append({
            "slug": slug,
            "name": pc["country_name"],
            "ccy": pc["currency_code"],
            "reviewed": pc.get("last_reviewed", ""),
            "threshold_summary": " / ".join(f'{t["currency"]} {int(t["value"]):,}' for t in th),
        })

    (OUT_DIR / "index.html").write_text(render_index(briefs_meta))
    print(f"Wrote briefs/index.html + {len(briefs_meta)} briefs:")
    for b in briefs_meta:
        print(f"  {b['name']:24s} {b['ccy']}  {b['threshold_summary']}")


if __name__ == "__main__":
    main()
