#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_commercial_feed.py — build the ConvertCCY Commercial Reference Feed (M2).

This generates the PACKAGED, LICENSEE-ONLY delivery artifact from the same
published, source-mapped governed data that backs the public reference. It sells
nothing the CC BY 4.0 reference does not already contain — it sells the
*packaging, delivery, and commercial terms* around it (see /licensing.html).

Binding boundaries (DECISION_LOG.md; mirrors build_static_agent_interface.py):
  - PUBLISHED governed data only. Never /preview/, never an unpublished or
    verified-but-unpublished jurisdiction. The drift guard below refuses to emit
    if any source entry is not page_status == "published".
  - This is a build-time file generator. No server, no API key, no auth, no
    billing. Nothing here runs on convertccy.com.
  - The output is NOT part of the public static site. It is written under
    dist/ (git-ignored) and delivered to licensees directly. It must never be
    linked from the site, listed in the sitemap, or served publicly.

Input (published governed data only):
  - rules/dataset.json   (public CC BY 4.0 dataset — already published-only)

Outputs (default: dist/commercial-feed/):
  - convertccy-commercial-feed-v1.json   full governed rules, published only
  - convertccy-commercial-feed-v1.csv    flat, spreadsheet-/pipeline-ready
  - manifest.json                        coverage, counts, review dates, tiers
  - sources.json                         per-field / per-jurisdiction source map
  - change-log.json                      review history + change notices
  - license.txt                          commercial terms for this delivery

Run:
  python3 scripts/build_commercial_feed.py            # build into dist/commercial-feed
  python3 scripts/build_commercial_feed.py --check    # validate only, write nothing
  python3 scripts/build_commercial_feed.py --out DIR  # build into DIR
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATASET = REPO / "rules" / "dataset.json"
DEFAULT_OUT = REPO / "dist" / "commercial-feed"

FEED_VERSION = "v1"
SCHEMA_VERSION = "1.0.0"
BASE_URL = "https://convertccy.com"
CONTACT = "agent@sohadot.com"

DISCLAIMER = (
    "This data is a governed reference, not legal, tax, customs, compliance, "
    "or financial advice. It does not predict, hedge, or guarantee any "
    "financial outcome, and it carries no warranty of any regulatory outcome. "
    "Verify time-sensitive figures against the official sources listed before "
    "acting."
)

USE_BOUNDARY = (
    "Published jurisdictions only. Absence of a jurisdiction means it is not yet "
    "published — never infer coverage from a currency code, and a shared "
    "currency (e.g. EUR) does not imply coverage of every country that uses it. "
    "Surface the coverage boundary and the official source(s) when relaying this "
    "data downstream."
)

# Flat, stable column order for the CSV delivery.
RULE_FIELDS = [
    "bring_foreign_currency_in",
    "take_foreign_currency_out",
    "cash_declaration_threshold",
    "resident_holding_rules",
    "non_resident_rules",
    "business_invoicing_settlement",
    "exchange_controls",
    "banking_conversion_practicality",
]

CSV_COLUMNS = [
    "country_name",
    "country_slug",
    "iso2",
    "iso3",
    "region",
    "currency_code",
    "currency_name",
    "last_reviewed",
    "evidence_tier",
    "summary_traveler",
    "summary_business",
    *RULE_FIELDS,
    "source_authorities",
    "rules_page",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_published() -> tuple[dict, list[dict]]:
    """Load the dataset and enforce the published-only drift guard."""
    if not DATASET.exists():
        sys.exit(f"ERROR: {DATASET} not found. Run the rules generator first.")

    dataset = json.loads(DATASET.read_text())
    countries = dataset.get("countries", [])
    if not countries:
        sys.exit("ERROR: rules/dataset.json contains no countries.")

    errors = []
    for c in countries:
        slug = c.get("country_slug", "<no-slug>")
        status = c.get("page_status")
        if status != "published":
            errors.append(
                f"{slug}: page_status={status!r}, expected 'published'. "
                "The commercial feed is published-only."
            )
        if not c.get("last_reviewed"):
            errors.append(f"{slug}: missing last_reviewed.")
        if not c.get("source_authorities"):
            errors.append(f"{slug}: missing source_authorities (source map).")
    if errors:
        sys.exit(
            "Commercial feed drift guard failed:\n  " + "\n  ".join(errors)
        )

    countries = sorted(countries, key=lambda c: c["country_name"])
    return dataset, countries


def feed_meta(dataset: dict, extra: dict | None = None) -> dict:
    base = {
        "product": "ConvertCCY Commercial Reference Feed",
        "feed_version": FEED_VERSION,
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "asset": "ConvertCCY",
        "source_scope": "published_governed_data_only",
        "public_reference": f"{BASE_URL}/rules/dataset.json",
        "public_reference_license": dataset.get("license", ""),
        "delivery": "licensee_only_not_public",
        "commercial_contact": CONTACT,
        "license_note": (
            "Delivered under a ConvertCCY commercial licence. The open reference "
            "at the URL above remains free and citable under CC BY 4.0; this "
            "packaged feed and its commercial terms are what the licence covers."
        ),
        "disclaimer": DISCLAIMER,
        "use_boundary": USE_BOUNDARY,
    }
    if extra:
        base.update(extra)
    return base


def build_feed_json(dataset: dict, countries: list[dict]) -> dict:
    entries = []
    for c in countries:
        entries.append({
            "country_name": c["country_name"],
            "country_slug": c["country_slug"],
            "iso2": c.get("iso2", ""),
            "iso3": c.get("iso3", ""),
            "region": c.get("region", ""),
            "currency_code": c.get("currency_code", ""),
            "currency_name": c.get("currency_name", ""),
            "page_status": c.get("page_status", ""),
            "last_reviewed": c.get("last_reviewed", ""),
            "evidence_tier": c.get("evidence_tier", ""),
            "country_overview": c.get("country_overview", ""),
            "summary": c.get("summary", {}),
            "rules": c.get("rules", {}),
            "source_authorities": c.get("source_authorities", []),
            "rules_page": f"{BASE_URL}/rules/{c['country_slug']}-foreign-currency-rules.html",
        })
    return feed_meta(dataset, extra={
        "license_tier": "commercial",
        "count": len(entries),
        "countries": entries,
    })


def build_csv(countries: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for c in countries:
        rules = c.get("rules", {})
        summary = c.get("summary", {})
        row = {
            "country_name": c["country_name"],
            "country_slug": c["country_slug"],
            "iso2": c.get("iso2", ""),
            "iso3": c.get("iso3", ""),
            "region": c.get("region", ""),
            "currency_code": c.get("currency_code", ""),
            "currency_name": c.get("currency_name", ""),
            "last_reviewed": c.get("last_reviewed", ""),
            "evidence_tier": c.get("evidence_tier", ""),
            "summary_traveler": summary.get("traveler", ""),
            "summary_business": summary.get("business", ""),
            "source_authorities": " | ".join(
                f"{s.get('label', '')} <{s.get('url', '')}>"
                for s in c.get("source_authorities", [])
            ),
            "rules_page": f"{BASE_URL}/rules/{c['country_slug']}-foreign-currency-rules.html",
        }
        for field in RULE_FIELDS:
            row[field] = rules.get(field, "")
        writer.writerow(row)
    return buf.getvalue()


def build_manifest(dataset: dict, countries: list[dict]) -> dict:
    return feed_meta(dataset, extra={
        "source_dataset_generated_at": dataset.get("generated_at", ""),
        "count": len(countries),
        "license_tiers": [
            "startup", "business", "enterprise",
            "agent_llm", "attribution_free", "data_update_subscription",
        ],
        "files": [
            f"convertccy-commercial-feed-{FEED_VERSION}.json",
            f"convertccy-commercial-feed-{FEED_VERSION}.csv",
            "manifest.json",
            "sources.json",
            "change-log.json",
            "license.txt",
        ],
        "jurisdictions": [
            {
                "country_name": c["country_name"],
                "country_slug": c["country_slug"],
                "iso3": c.get("iso3", ""),
                "currency_code": c.get("currency_code", ""),
                "last_reviewed": c.get("last_reviewed", ""),
                "evidence_tier": c.get("evidence_tier", ""),
            }
            for c in countries
        ],
    })


def build_sources(dataset: dict, countries: list[dict]) -> dict:
    return feed_meta(dataset, extra={
        "note": (
            "Per-jurisdiction map of the official authorities backing each "
            "published entry. Every rules field is sourced to these authorities."
        ),
        "count": len(countries),
        "jurisdictions": [
            {
                "country_slug": c["country_slug"],
                "country_name": c["country_name"],
                "last_reviewed": c.get("last_reviewed", ""),
                "source_authorities": c.get("source_authorities", []),
            }
            for c in countries
        ],
    })


def build_change_log(dataset: dict, countries: list[dict]) -> dict:
    """Grounded change log: one reviewed-at entry per jurisdiction.

    We do not fabricate historical diffs. Each entry records the most recent
    governed review date as the change signal a licensee can rely on; a
    subscription delivery appends future review/change notices here.
    """
    entries = sorted(
        (
            {
                "country_slug": c["country_slug"],
                "country_name": c["country_name"],
                "last_reviewed": c.get("last_reviewed", ""),
                "evidence_tier": c.get("evidence_tier", ""),
                "change_type": "reviewed",
                "note": "Entry reviewed against official sources on this date.",
            }
            for c in countries
        ),
        key=lambda e: (e["last_reviewed"], e["country_name"]),
        reverse=True,
    )
    return feed_meta(dataset, extra={
        "note": (
            "Review history for published jurisdictions. Each 'reviewed' entry "
            "is anchored to the governed last_reviewed date. Update-subscription "
            "deliveries append change notices and diffs here over time."
        ),
        "count": len(entries),
        "entries": entries,
    })


def build_license_txt(countries: list[dict]) -> str:
    return (
        "ConvertCCY Commercial Reference Feed — Licence Notice\n"
        "=====================================================\n\n"
        f"Generated: {now_iso()}\n"
        f"Feed version: {FEED_VERSION}\n"
        f"Published jurisdictions in this delivery: {len(countries)}\n\n"
        "This package is delivered under a ConvertCCY commercial licence. It is\n"
        "for the licensee's agreed commercial use only and is not a public\n"
        "download.\n\n"
        "The underlying reference data is also published openly at\n"
        f"{BASE_URL}/rules/dataset.json under CC BY 4.0. This commercial licence\n"
        "does not restrict that open reference; it covers the packaging,\n"
        "delivery, scheduled updates, attribution-free rights, and support\n"
        "agreed in your commercial terms.\n\n"
        "This data is a governed reference, not legal, tax, customs, compliance,\n"
        "or financial advice, and carries no warranty of any regulatory outcome.\n"
        "Verify time-sensitive figures against the official sources listed\n"
        "before acting.\n\n"
        f"Commercial terms and support: {CONTACT}\n"
    )


def validate_outputs(feed: dict, manifest: dict, sources: dict) -> list[str]:
    """Post-build assertions mirroring the licensing surface's promises."""
    problems = []
    if feed.get("count", 0) < 1:
        problems.append("feed contains no jurisdictions")
    for c in feed.get("countries", []):
        slug = c.get("country_slug", "<no-slug>")
        if c.get("page_status") != "published":
            problems.append(f"{slug}: non-published entry reached the feed")
        if not c.get("source_authorities"):
            problems.append(f"{slug}: source_map missing")
        if not c.get("last_reviewed"):
            problems.append(f"{slug}: last_reviewed missing")
    if not feed.get("disclaimer"):
        problems.append("feed: disclaimer missing")
    if not feed.get("license_tier"):
        problems.append("feed: license tier metadata missing")
    if not manifest.get("license_tiers"):
        problems.append("manifest: license_tiers missing")
    if sources.get("count") != feed.get("count"):
        problems.append("sources.json coverage does not match feed count")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the ConvertCCY Commercial Reference Feed.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output directory (default: dist/commercial-feed)")
    parser.add_argument("--check", action="store_true", help="validate only; write nothing")
    args = parser.parse_args()

    dataset, countries = load_published()

    feed = build_feed_json(dataset, countries)
    csv_text = build_csv(countries)
    manifest = build_manifest(dataset, countries)
    sources = build_sources(dataset, countries)
    change_log = build_change_log(dataset, countries)
    license_txt = build_license_txt(countries)

    problems = validate_outputs(feed, manifest, sources)
    if problems:
        sys.exit("Commercial feed validation failed:\n  " + "\n  ".join(problems))

    if args.check:
        print(f"OK: {feed['count']} published jurisdictions, all checks passed (no files written).")
        return

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    (out / f"convertccy-commercial-feed-{FEED_VERSION}.json").write_text(
        json.dumps(feed, ensure_ascii=False, indent=1))
    (out / f"convertccy-commercial-feed-{FEED_VERSION}.csv").write_text(csv_text)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    (out / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=1))
    (out / "change-log.json").write_text(json.dumps(change_log, ensure_ascii=False, indent=1))
    (out / "license.txt").write_text(license_txt)

    print(f"Commercial Reference Feed {FEED_VERSION} — {feed['count']} published jurisdictions")
    for name in (
        f"convertccy-commercial-feed-{FEED_VERSION}.json",
        f"convertccy-commercial-feed-{FEED_VERSION}.csv",
        "manifest.json", "sources.json", "change-log.json", "license.txt",
    ):
        print(f"  Wrote {(out / name)}")
    print(f"\nDelivery is licensee-only: {out} is under dist/ (git-ignored) and is not part of the public site.")


if __name__ == "__main__":
    main()
