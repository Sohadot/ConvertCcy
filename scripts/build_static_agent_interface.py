#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_static_agent_interface.py — generate the ConvertCCY Static Agent Interface (P7A).

This is NOT a dynamic API. There is no server, no API key, no authentication,
no billing, and no endpoint that executes a request. This script writes plain
JSON files to disk at build time; GitHub Pages serves them as static files,
exactly like rules/dataset.json and rules/passage-check.json already are.

Binding boundary (DECISION_LOG.md, Phase 11 — P7-0, binding):
  - No dynamic backend is ever added to convertccy.com.
  - No API keys, authentication, billing, checkout, or server-side processing
    of user input on this domain, ever.
  - Only static, read-only, agent-readable JSON generated from PUBLISHED,
    governed data may be exposed here. Never /preview/, never an unpublished
    jurisdiction, never an internal/RC entry.
  - Any future metered or authenticated API must be isolated off this domain
    (e.g. api.convertccy.com) and must not share this domain's origin,
    secrets, or trust.

Inputs (published governed data only):
  - rules/dataset.json        (public CC BY 4.0 dataset — already published-only)
  - rules/passage-check.json  (public Passage Check engine dataset)

Outputs:
  - api/v1/index.json          machine entry point
  - api/v1/rules-index.json    list of published jurisdictions
  - api/v1/rules/<slug>.json   one file per published jurisdiction
  - api/v1/passage-check.json  Static Agent Interface view of Passage Check
  - api/index.html             generated human hub page (lists the endpoints)

Drift guard: refuses to emit if rules/dataset.json and rules/passage-check.json
disagree on which jurisdictions are published, or if either source contains a
non-published entry. This script must never be the point where an unpublished
jurisdiction leaks into an agent-readable surface.

Run: python3 scripts/build_static_agent_interface.py
"""

from __future__ import annotations

import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATASET = REPO / "rules" / "dataset.json"
PASSAGE_CHECK = REPO / "rules" / "passage-check.json"

API_DIR = REPO / "api"
API_V1_DIR = API_DIR / "v1"
API_RULES_DIR = API_V1_DIR / "rules"

BASE_URL = "https://convertccy.com"
SCHEMA_VERSION = "1.0.0"

DISCLAIMER = (
    "This data is a governed reference, not legal, tax, customs, compliance, "
    "or financial advice. It does not predict, hedge, or guarantee any "
    "financial outcome. Verify time-sensitive figures against the official "
    "sources listed before acting."
)

USE_BOUNDARY = (
    "Static, read-only reference data only. Do not represent this interface "
    "as a dynamic API, as live data, or as covering any jurisdiction not "
    "listed in this file. A currency code is not the same as a jurisdiction: "
    "a shared currency (e.g. EUR) does not imply coverage of every country "
    "that uses it. Cite ConvertCCY and the official source(s) when using "
    "this data downstream."
)


def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def machine_contract(canonical_path: str, license_: str, attribution: str, extra: dict | None = None) -> dict:
    base = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "asset": "ConvertCCY",
        "interface_type": "static_agent_interface",
        "dynamic_api": False,
        "source_scope": "published_governed_data_only",
        "license": license_,
        "attribution": attribution,
        "disclaimer": DISCLAIMER,
        "use_boundary": USE_BOUNDARY,
        "canonical_url": f"{BASE_URL}{canonical_path}",
        "documentation": f"{BASE_URL}/api.html",
    }
    if extra:
        base.update(extra)
    return base


def load_sources():
    if not DATASET.exists():
        sys.exit(f"ERROR: {DATASET} not found. Run the rules generator first.")
    if not PASSAGE_CHECK.exists():
        sys.exit(f"ERROR: {PASSAGE_CHECK} not found. Run scripts/build_passage_check.py first.")

    dataset = json.loads(DATASET.read_text())
    passage = json.loads(PASSAGE_CHECK.read_text())

    dataset_countries = {c["country_slug"]: c for c in dataset["countries"]}
    passage_countries = {c["country_slug"]: c for c in passage["countries"]}

    errors = []
    for slug, c in dataset_countries.items():
        if c.get("page_status") != "published":
            errors.append(f"{slug}: present in rules/dataset.json with page_status={c.get('page_status')!r}, expected 'published'")
    for slug in dataset_countries:
        if slug not in passage_countries:
            errors.append(f"{slug}: published in dataset.json but missing from passage-check.json")
    for slug in passage_countries:
        if slug not in dataset_countries:
            errors.append(f"{slug}: present in passage-check.json but missing from published dataset.json")
    if errors:
        sys.exit("Static Agent Interface drift guard failed:\n  " + "\n  ".join(errors))

    return dataset, passage, dataset_countries, passage_countries


def build_rules_index(dataset: dict, dataset_countries: dict) -> dict:
    entries = []
    for slug, c in sorted(dataset_countries.items(), key=lambda kv: kv[1]["country_name"]):
        entries.append({
            "country_name": c["country_name"],
            "country_slug": slug,
            "iso2": c.get("iso2", ""),
            "iso3": c.get("iso3", ""),
            "region": c.get("region", ""),
            "currency_code": c.get("currency_code", ""),
            "currency_name": c.get("currency_name", ""),
            "last_reviewed": c.get("last_reviewed", ""),
            "rules_page": f"/rules/{slug}-foreign-currency-rules.html",
            "brief_page": f"/briefs/{slug}-passage-brief.html",
            "api_path": f"/api/v1/rules/{slug}.json",
        })

    payload = machine_contract(
        "/api/v1/rules-index.json",
        dataset.get("license", ""),
        dataset.get("attribution", ""),
        extra={
            "title": "ConvertCCY Published Jurisdictions Index",
            "source_dataset_generated_at": dataset.get("generated_at", ""),
            "count": len(entries),
            "coverage_note": (
                "Lists only jurisdictions that have passed ConvertCCY's published, "
                "source-mapped review gate. Absence from this list means not yet "
                "published — never infer coverage from a currency code."
            ),
            "countries": entries,
        },
    )
    return payload


def build_country_files(dataset: dict, dataset_countries: dict) -> list[dict]:
    written = []
    API_RULES_DIR.mkdir(parents=True, exist_ok=True)
    for slug, c in sorted(dataset_countries.items()):
        canonical_path = f"/api/v1/rules/{slug}.json"
        payload = machine_contract(
            canonical_path,
            dataset.get("license", ""),
            dataset.get("attribution", ""),
            extra={
                "country_name": c["country_name"],
                "country_slug": slug,
                "iso2": c.get("iso2", ""),
                "iso3": c.get("iso3", ""),
                "region": c.get("region", ""),
                "currency_code": c.get("currency_code", ""),
                "currency_name": c.get("currency_name", ""),
                "page_status": c.get("page_status", ""),
                "last_reviewed": c.get("last_reviewed", ""),
                "evidence_tier": c.get("evidence_tier", ""),
                "rules_page": f"/rules/{slug}-foreign-currency-rules.html",
                "brief_page": f"/briefs/{slug}-passage-brief.html",
                "country_overview": c.get("country_overview", ""),
                "summary": c.get("summary", {}),
                "rules": c.get("rules", {}),
                "source_authorities": c.get("source_authorities", []),
                "disclaimer_notice": c.get("disclaimer", ""),
            },
        )
        out_path = API_RULES_DIR / f"{slug}.json"
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
        written.append({"slug": slug, "path": out_path})
    return written


def build_passage_check_view(passage: dict, dataset: dict) -> dict:
    payload = machine_contract(
        "/api/v1/passage-check.json",
        passage.get("license", dataset.get("license", "")),
        passage.get("attribution", dataset.get("attribution", "")),
        extra={
            "title": "ConvertCCY Passage Check — Static Agent Interface view",
            "engine": passage.get("engine", ""),
            "engine_version": passage.get("version", ""),
            "built_from": passage.get("built_from", ""),
            "source_dataset_generated_at": passage.get("source_dataset_generated_at", ""),
            "engine_notice": passage.get("notice", ""),
            "count": passage.get("count", 0),
            "countries": passage.get("countries", []),
        },
    )
    return payload


def build_index(dataset: dict, rules_index: dict, passage_view: dict) -> dict:
    payload = machine_contract(
        "/api/v1/index.json",
        dataset.get("license", ""),
        dataset.get("attribution", ""),
        extra={
            "title": "ConvertCCY Static Agent Interface — machine entry point",
            "description": (
                "Static, read-only, agent-readable JSON generated from ConvertCCY's "
                "published, source-mapped governed data. There is no server behind "
                "these routes: they are files, refreshed on publication, served "
                "exactly like any other static asset on this domain."
            ),
            "not_an_api_notice": (
                "This is not a dynamic API. It is a static data interface. There is "
                "no endpoint that executes a request, no API key, no authentication, "
                "and no billing. Any future metered or authenticated API will be "
                "isolated off this domain (see /api.html)."
            ),
            "published_jurisdictions_count": rules_index["count"],
            "endpoints": {
                "rules_index": {
                    "path": "/api/v1/rules-index.json",
                    "description": "Index of all published jurisdictions with links to their per-country file.",
                },
                "rules_country": {
                    "path_pattern": "/api/v1/rules/<country-slug>.json",
                    "description": "Full governed rules entry for one published jurisdiction.",
                    "available_slugs": [c["country_slug"] for c in rules_index["countries"]],
                },
                "passage_check": {
                    "path": "/api/v1/passage-check.json",
                    "description": "Passage Check engine dataset: declaration thresholds and exchange-control posture, transcribed from governed data.",
                },
            },
            "human_documentation": "/api.html",
            "llms_txt": "/llms.txt",
        },
    )
    return payload


NAV = """<nav>
  <a href="/" class="logo">convert<span>ccy</span></a>
  <div class="nav-links">
    <a href="/">Home</a>
    <a href="/rules/">Rules</a>
    <a href="/rules/dataset.json">Dataset</a>
    <a href="/api.html">Agent Interface</a>
    <a href="/licensing.html">Licensing</a>
    <a href="/governance.html">Governance</a>
  </div>
</nav>"""

FOOTER = """<footer>
  <p>&copy; 2026 ConvertCCY. <a href="/rules/dataset.json">Open Dataset</a> &bull; <a href="/api.html">Static Agent Interface</a> &bull; <a href="/licensing.html">Licensing</a> &bull; <a href="/governance.html">Governance</a> &bull; <a href="/disclaimer.html">Disclaimer</a></p>
</footer>"""

STYLE = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#f7f7f5;--surface:#fff;--surface-2:#fcfcfa;--border:#e8e8e4;--text:#111110;--muted:#888884;--accent:#1a6b3c;--accent-light:#e8f5ee;--accent-border:#c4dfd0;--amber:#a07000;--amber-light:#fef8e7;--amber-border:#f5d97a;--shadow:0 8px 24px rgba(17,17,16,.05);--mono:'DM Mono',monospace;--sans:'Sora',sans-serif}
html{scroll-behavior:smooth}
body{font-family:var(--sans);background:var(--bg);color:var(--text);line-height:1.78;font-size:17px}
nav{position:sticky;top:0;z-index:100;background:rgba(247,247,245,.92);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);padding:0 2rem;display:flex;align-items:center;justify-content:space-between;min-height:58px;gap:1rem;flex-wrap:wrap}
.logo{font-family:var(--mono);font-size:1.05rem;font-weight:500;color:var(--text);text-decoration:none}
.logo span{color:var(--accent)}
.nav-links{display:flex;align-items:center;gap:1.2rem;flex-wrap:wrap}
.nav-links a{font-size:.82rem;color:var(--muted);text-decoration:none;transition:color .18s}
.nav-links a:hover{color:var(--text)}
.page-wrap{max-width:1000px;margin:0 auto;padding:4rem 2rem 6rem}
.breadcrumb{font-family:var(--mono);font-size:.72rem;color:var(--muted);margin-bottom:2rem}
.breadcrumb a{color:var(--muted);text-decoration:none}
.breadcrumb a:hover{color:var(--accent)}
.hero-tag{display:inline-block;background:var(--accent-light);color:var(--accent);font-family:var(--mono);font-size:.74rem;padding:4px 14px;border-radius:100px;margin-bottom:1.2rem;border:1px solid var(--accent-border)}
h1{font-size:clamp(2rem,4.6vw,3rem);font-weight:800;letter-spacing:-2px;line-height:1.06;margin-bottom:1.1rem}
h1 em{font-style:normal;color:var(--accent)}
.hero-lead{font-size:1.05rem;color:#2e2e2b;max-width:760px;line-height:1.75}
.section-divider{border:none;border-top:1px solid var(--border);margin:3rem 0}
.section-kicker{font-family:var(--mono);font-size:.7rem;text-transform:uppercase;letter-spacing:.16em;color:var(--accent);margin-bottom:.5rem}
h2{font-size:1.4rem;font-weight:800;letter-spacing:-.03em;margin-bottom:.9rem;line-height:1.15}
p{color:#2a2a28;line-height:1.8;margin-bottom:1.1rem}
strong{color:var(--text);font-weight:600}
.endpoints{display:grid;gap:1rem;margin:1.5rem 0}
.ep{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:1.2rem 1.4rem;box-shadow:var(--shadow)}
.ep .path{font-family:var(--mono);font-size:.92rem;color:var(--accent);word-break:break-all}
.ep .desc{color:var(--muted);font-size:.88rem;margin-top:.3rem}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.8rem;margin:1.5rem 0}
.gcard{display:block;text-decoration:none;color:inherit;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1rem 1.2rem;transition:border-color .18s}
.gcard:hover{border-color:var(--accent)}
.gcard .k{font-family:var(--mono);font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}
.gcard .v{font-weight:700;font-size:.98rem;margin-top:.2rem}
.box-accent{background:var(--accent-light);border:1px solid var(--accent-border);border-radius:16px;padding:1.3rem 1.5rem;margin:2rem 0}
.box-accent .box-label{font-family:var(--mono);font-size:.66rem;letter-spacing:.18em;color:var(--accent);text-transform:uppercase;margin-bottom:.5rem;display:block}
.box-accent p{color:#1e4f2f;margin:0;font-size:.93rem;line-height:1.72}
footer{border-top:1px solid var(--border);text-align:center;padding:2rem;margin-top:3rem;font-size:.78rem;color:var(--muted);font-family:var(--mono)}
footer a{color:var(--muted);text-decoration:none}
footer a:hover{color:var(--text)}
@media(max-width:640px){nav{padding:.8rem 1rem}.page-wrap{padding:2.5rem 1rem 4rem}h1{font-size:1.8rem}}
"""


def render_api_index_html(rules_index: dict) -> str:
    cards = ""
    for c in rules_index["countries"]:
        cards += (
            f'<a class="gcard" href="{esc(c["api_path"])}">'
            f'<div class="k">{esc(c["currency_code"])} &middot; reviewed {esc(c["last_reviewed"])}</div>'
            f'<div class="v">{esc(c["country_name"])}</div></a>'
        )

    desc = ("Machine entry point for the ConvertCCY Static Agent Interface — static, "
            "read-only JSON generated from published, source-mapped governed data. "
            "Not a dynamic API: no server, no keys, no authentication, no billing.")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Static Agent Interface — Endpoints | ConvertCCY</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="{BASE_URL}/api/">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Sora:wght@300;400;600;700;800&display=swap" rel="stylesheet">
<style>{STYLE}</style>
</head>
<body>
{NAV}
<div class="page-wrap">
  <div class="breadcrumb"><a href="/">Home</a> / <a href="/api.html">Agent Interface</a> / <span>Endpoints</span></div>
  <span class="hero-tag">Static &middot; Read-only &middot; No auth</span>
  <h1>Static Agent Interface <em>Endpoints</em></h1>
  <p class="hero-lead">This page is generated. It lists the current static JSON routes and the {esc(rules_index["count"])} published jurisdictions they cover. Start at <code>/api/v1/index.json</code> if you are a script or agent.</p>

  <hr class="section-divider">

  <section>
    <div class="section-kicker">Machine Entry Point</div>
    <h2>Core endpoints</h2>
    <div class="endpoints">
      <div class="ep"><div class="path">/api/v1/index.json</div><div class="desc">Entry point: endpoint map, published-jurisdiction count, links to documentation.</div></div>
      <div class="ep"><div class="path">/api/v1/rules-index.json</div><div class="desc">Index of all published jurisdictions with links to each per-country file.</div></div>
      <div class="ep"><div class="path">/api/v1/rules/&lt;country-slug&gt;.json</div><div class="desc">Full governed rules entry for one published jurisdiction (see list below).</div></div>
      <div class="ep"><div class="path">/api/v1/passage-check.json</div><div class="desc">Passage Check engine dataset: transcribed declaration thresholds and exchange-control posture.</div></div>
    </div>
  </section>

  <hr class="section-divider">

  <section>
    <div class="section-kicker">Published Jurisdictions</div>
    <h2>{esc(rules_index["count"])} countries available now</h2>
    <div class="grid">
      {cards}
    </div>
  </section>

  <div class="box-accent">
    <span class="box-label">Not a dynamic API</span>
    <p>These are static files, not a live service. There is no key, no login, and no request execution behind them. Read the boundary at <a href="/api.html" style="color:var(--accent);font-weight:600">/api.html</a>.</p>
  </div>
</div>
{FOOTER}
</body>
</html>
"""


def main() -> None:
    dataset, passage, dataset_countries, passage_countries = load_sources()

    rules_index = build_rules_index(dataset, dataset_countries)
    country_files = build_country_files(dataset, dataset_countries)
    passage_view = build_passage_check_view(passage, dataset)
    index_payload = build_index(dataset, rules_index, passage_view)

    API_V1_DIR.mkdir(parents=True, exist_ok=True)

    (API_V1_DIR / "index.json").write_text(json.dumps(index_payload, ensure_ascii=False, indent=1))
    (API_V1_DIR / "rules-index.json").write_text(json.dumps(rules_index, ensure_ascii=False, indent=1))
    (API_V1_DIR / "passage-check.json").write_text(json.dumps(passage_view, ensure_ascii=False, indent=1))
    (API_DIR / "index.html").write_text(render_api_index_html(rules_index))

    print(f"Wrote {(API_V1_DIR / 'index.json').relative_to(REPO)}")
    print(f"Wrote {(API_V1_DIR / 'rules-index.json').relative_to(REPO)} — {rules_index['count']} published jurisdictions")
    print(f"Wrote {(API_V1_DIR / 'passage-check.json').relative_to(REPO)} — {passage_view['count']} countries")
    print(f"Wrote {(API_DIR / 'index.html').relative_to(REPO)}")
    for cf in country_files:
        print(f"Wrote {cf['path'].relative_to(REPO)}")


if __name__ == "__main__":
    main()
