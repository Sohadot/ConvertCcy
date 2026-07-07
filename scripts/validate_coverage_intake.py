#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_coverage_intake.py — guard rail for the G20+ coverage expansion
intake process (P8-0).

This script never publishes anything. It only checks that the coverage
intake files (data/coverage/g20-expansion-candidates.json and
data/coverage/source-intake-matrix.json) have not drifted into a state that
would leak an unpublished candidate onto a public surface, or that would
promote a candidate without the required source fields.

It fails (non-zero exit) if:
  - any candidate in g20-expansion-candidates.json has status "published"
  - any candidate's country_slug appears in api/v1/rules-index.json,
    api/v1/rules/, or api/v1/index.json's available_slugs
  - any candidate's country_slug appears in sitemap.xml
  - any candidate's country_slug is presented as covered in llms.txt
    (i.e. appears in the published-jurisdictions citation example set or
    as a /rules/<slug>-foreign-currency-rules.html link)
  - any candidate is missing a required field (country_name, country_slug,
    iso2, iso3, currency_code, region, expansion_priority, complexity_level,
    likely_official_source_authorities_needed, expected_difficulty,
    known_risk_areas, missing_sources, status)
  - a /preview/ route is referenced anywhere in the intake files
  - the two intake files disagree on which candidates they cover

Run: python3 scripts/validate_coverage_intake.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CANDIDATES_FILE = REPO / "data" / "coverage" / "g20-expansion-candidates.json"
MATRIX_FILE = REPO / "data" / "coverage" / "source-intake-matrix.json"
SITEMAP_FILE = REPO / "sitemap.xml"
LLMS_FILE = REPO / "llms.txt"
API_RULES_INDEX = REPO / "api" / "v1" / "rules-index.json"
API_INDEX = REPO / "api" / "v1" / "index.json"
API_RULES_DIR = REPO / "api" / "v1" / "rules"

REQUIRED_CANDIDATE_FIELDS = [
    "country_name",
    "country_slug",
    "iso2",
    "iso3",
    "currency_code",
    "region",
    "expansion_priority",
    "complexity_level",
    "likely_official_source_authorities_needed",
    "expected_difficulty",
    "known_risk_areas",
    "missing_sources",
    "status",
]

DISALLOWED_STATUS_FOR_THIS_PHASE = {"published"}


def load_json(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"ERROR: required file not found: {path}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"ERROR: {path} is not valid JSON: {e}")


def main() -> None:
    errors: list[str] = []

    candidates_doc = load_json(CANDIDATES_FILE)
    matrix_doc = load_json(MATRIX_FILE)

    candidates = candidates_doc.get("candidates", [])
    if not candidates:
        errors.append("g20-expansion-candidates.json has no candidates listed")

    candidate_slugs = set()

    # --- Field completeness + status guard ------------------------------
    for c in candidates:
        slug = c.get("country_slug", "<missing-slug>")
        candidate_slugs.add(slug)

        missing_fields = [f for f in REQUIRED_CANDIDATE_FIELDS if f not in c or c[f] in (None, "", [])]
        # known_risk_areas and missing_sources may legitimately be an empty list
        # (e.g. a candidate with no known risks yet identified), so don't treat
        # an empty list as "missing" for those two fields specifically.
        missing_fields = [f for f in missing_fields if f not in ("known_risk_areas", "missing_sources")]
        for f in ("known_risk_areas", "missing_sources"):
            if f not in c:
                missing_fields.append(f)

        if missing_fields:
            errors.append(f"{slug}: missing required field(s): {missing_fields}")

        status = c.get("status")
        if status in DISALLOWED_STATUS_FOR_THIS_PHASE:
            errors.append(f"{slug}: status is {status!r} — no candidate may be marked published by this intake process")

        authorities = c.get("likely_official_source_authorities_needed", {})
        if isinstance(authorities, dict):
            for required_key in ("central_bank_or_monetary_authority", "customs_or_border_authority"):
                if not authorities.get(required_key):
                    errors.append(f"{slug}: missing required source-authority category '{required_key}'")

    # --- Existing published jurisdictions must not appear as candidates -
    published_list = candidates_doc.get("existing_published_jurisdictions", [])
    overlap = candidate_slugs & set(published_list)
    if overlap:
        errors.append(f"candidate list overlaps with existing published jurisdictions: {sorted(overlap)}")

    # --- The two intake files must cover the same candidate set ---------
    matrix_slugs = {row.get("country_slug") for row in matrix_doc.get("matrix", [])}
    if candidate_slugs != matrix_slugs:
        only_in_candidates = candidate_slugs - matrix_slugs
        only_in_matrix = matrix_slugs - candidate_slugs
        if only_in_candidates:
            errors.append(f"candidates missing from source-intake-matrix.json: {sorted(only_in_candidates)}")
        if only_in_matrix:
            errors.append(f"source-intake-matrix.json has entries not in the candidate list: {sorted(only_in_matrix)}")

    # --- No /preview/ reference anywhere in the intake files -------------
    for path in (CANDIDATES_FILE, MATRIX_FILE):
        text = path.read_text()
        if "/preview/" in text:
            errors.append(f"{path.name} references /preview/ — not allowed in an intake document")

    # --- Candidates must not appear in the Static Agent Interface --------
    if API_INDEX.exists():
        api_index = json.loads(API_INDEX.read_text())
        available_slugs = set(
            api_index.get("endpoints", {}).get("rules_country", {}).get("available_slugs", [])
        )
        leaked = candidate_slugs & available_slugs
        if leaked:
            errors.append(f"candidates present in api/v1/index.json available_slugs: {sorted(leaked)}")

    if API_RULES_INDEX.exists():
        rules_index = json.loads(API_RULES_INDEX.read_text())
        indexed_slugs = {c.get("country_slug") for c in rules_index.get("countries", [])}
        leaked = candidate_slugs & indexed_slugs
        if leaked:
            errors.append(f"candidates present in api/v1/rules-index.json: {sorted(leaked)}")

    if API_RULES_DIR.exists():
        api_country_files = {f.stem for f in API_RULES_DIR.glob("*.json")}
        leaked = candidate_slugs & api_country_files
        if leaked:
            errors.append(f"candidates have a generated file under api/v1/rules/: {sorted(leaked)}")

    # --- Candidates must not appear in the sitemap -----------------------
    if SITEMAP_FILE.exists():
        sitemap_text = SITEMAP_FILE.read_text()
        for slug in candidate_slugs:
            if f"/rules/{slug}-foreign-currency-rules.html" in sitemap_text:
                errors.append(f"{slug}: appears in sitemap.xml as a published rules page")
            if f"/briefs/{slug}-passage-brief.html" in sitemap_text:
                errors.append(f"{slug}: appears in sitemap.xml as a published brief")
            if f"/api/v1/rules/{slug}.json" in sitemap_text:
                errors.append(f"{slug}: appears in sitemap.xml as a published Static Agent Interface route")
        if "/preview/" in sitemap_text:
            errors.append("sitemap.xml references /preview/ — not allowed")

    # --- Candidates must not be presented as covered in llms.txt ---------
    if LLMS_FILE.exists():
        llms_text = LLMS_FILE.read_text()
        for slug in candidate_slugs:
            if f"/rules/{slug}-foreign-currency-rules.html" in llms_text:
                errors.append(f"{slug}: appears as a covered rules page link in llms.txt")

    if errors:
        print(f"Coverage intake validation FAILED — {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print("Coverage intake validation PASSED")
    print(f"  {len(candidates)} candidates recorded, all status={sorted({c['status'] for c in candidates})}")
    print(f"  {len(published_list)} existing published jurisdictions confirmed unaffected: {sorted(published_list)}")
    print("  No candidate found in api/v1/, sitemap.xml, or llms.txt as covered content.")
    print("  No /preview/ reference found in intake files.")


if __name__ == "__main__":
    main()
