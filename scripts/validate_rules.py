#!/usr/bin/env python3
"""
ConvertCCY — Global FX Rules Reference Layer
============================================
validate_rules.py v1.2.1

Purpose
-------
Strict validator for country rule JSON files under the sovereign reference standard.

Implements:
- Gate 8: lifecycle consistency
- Gate 9: source_map integrity
- Gate 10: country_overview quality signals

Usage
-----
    python scripts/validate_rules.py data/rules/india.json
    python scripts/validate_rules.py data/rules/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent

if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

try:
    import rules_schema as rs
except Exception as exc:
    print(f"ERROR: Could not import rules_schema.py: {exc}", file=sys.stderr)
    sys.exit(2)


@dataclass
class ValidationResult:
    path: Path
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors and not self.warnings


TRACKING_QUERY_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "gclid", "fbclid", "mc_cid", "mc_eid", "ref", "ref_src",
}


def canonicalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return url

    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()

    filtered_qs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in TRACKING_QUERY_KEYS
    ]
    query = urlencode(filtered_qs, doseq=True)

    path = parts.path or ""
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    return urlunsplit((scheme, netloc, path, query, ""))


def is_https_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("https://")


def is_pdf_url(url: str) -> bool:
    canon = canonicalize_url(url)
    return any(canon.lower().endswith(suffix) for suffix in rs.PDF_SOURCE_SUFFIXES)


def similarity_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def text_contains_forbidden_pattern(text: str) -> Optional[str]:
    lowered = text.lower()
    for pat in rs.FORBIDDEN_PATTERNS:
        if pat.lower() in lowered:
            return pat
    return None


def ensure_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def ensure_list_of_ints(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, int) for v in value)


def slug_like(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value))


def parse_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def gather_json_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    return sorted(p for p in path.glob("*.json") if p.is_file())


def validate_top_level_structure(data: Dict[str, Any], result: ValidationResult) -> None:
    missing = rs.REQUIRED_TOP_LEVEL_KEYS - set(data.keys())
    if missing:
        result.error(f"Missing required top-level keys: {sorted(missing)}")

    if data.get("schema_version") != rs.SCHEMA_VERSION_CURRENT:
        result.error(
            f"schema_version must be '{rs.SCHEMA_VERSION_CURRENT}', got '{data.get('schema_version')}'"
        )

    if not slug_like(data.get("country_slug")):
        result.error("country_slug must be lowercase kebab-case")

    if not ensure_non_empty_string(data.get("country_name")):
        result.error("country_name must be a non-empty string")

    if not ensure_non_empty_string(data.get("currency_code")):
        result.error("currency_code must be a non-empty string")

    if data.get("region") not in {r.value for r in rs.Region}:
        result.error(f"region must be one of {[r.value for r in rs.Region]}")

    summary = data.get("summary")
    if not isinstance(summary, dict):
        result.error("summary must be an object")
    else:
        missing = rs.REQUIRED_SUMMARY_KEYS - set(summary.keys())
        if missing:
            result.error(f"Missing summary keys: {sorted(missing)}")

    rules = data.get("rules")
    if not isinstance(rules, dict):
        result.error("rules must be an object")
    else:
        missing = rs.REQUIRED_RULE_KEYS - set(rules.keys())
        if missing:
            result.error(f"Missing rules keys: {sorted(missing)}")


def validate_text_quality(data: Dict[str, Any], result: ValidationResult) -> None:
    overview = data.get("country_overview")
    if not ensure_non_empty_string(overview):
        result.error("country_overview must be a non-empty string")
    else:
        if len(overview.strip()) < rs.MIN_CHARS_OVERVIEW:
            result.error(
                f"country_overview must be at least {rs.MIN_CHARS_OVERVIEW} characters"
            )
        pat = text_contains_forbidden_pattern(overview)
        if pat:
            result.error(f"country_overview contains forbidden placeholder pattern: {pat}")

    summary = data.get("summary", {})
    for key in rs.REQUIRED_SUMMARY_KEYS:
        value = summary.get(key)
        if not ensure_non_empty_string(value):
            result.error(f"summary.{key} must be a non-empty string")
            continue
        if len(value.strip()) < rs.MIN_CHARS_SUMMARY:
            result.error(f"summary.{key} must be at least {rs.MIN_CHARS_SUMMARY} characters")
        pat = text_contains_forbidden_pattern(value)
        if pat:
            result.error(f"summary.{key} contains forbidden placeholder pattern: {pat}")

    rules = data.get("rules", {})
    rule_values: Dict[str, str] = {}
    for key in rs.REQUIRED_RULE_KEYS:
        value = rules.get(key)
        if not ensure_non_empty_string(value):
            result.error(f"rules.{key} must be a non-empty string")
            continue
        value = value.strip()
        rule_values[key] = value
        if len(value) < rs.MIN_CHARS_RULE_FIELD:
            result.error(f"rules.{key} must be at least {rs.MIN_CHARS_RULE_FIELD} characters")
        pat = text_contains_forbidden_pattern(value)
        if pat:
            result.error(f"rules.{key} contains forbidden placeholder pattern: {pat}")

    keys = list(rule_values.keys())
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a_key, b_key = keys[i], keys[j]
            ratio = similarity_ratio(rule_values[a_key], rule_values[b_key])
            if ratio > rs.MAX_SIMILARITY_RATIO:
                result.error(
                    f"rules.{a_key} and rules.{b_key} are too similar ({ratio:.2f} > {rs.MAX_SIMILARITY_RATIO})"
                )


OVERVIEW_SIGNAL_KEYWORDS = {
    "regulatory_authority": [
        "reserve bank", "central bank", "customs", "office des changes",
        "administered by", "regulated by", "regulator", "authorised dealer",
        "authorized dealer", "ministry", "authority", "authorities",
    ],
    "fx_regime": [
        "exchange regime", "managed", "floating", "float", "peg", "pegged",
        "fema", "framework", "foreign exchange management act", "fx regime",
        "current account", "capital account",
    ],
    "convertibility_or_controls": [
        "convertible", "convertibility", "exchange controls", "exchange control",
        "controls", "restricted", "regulated", "non-convertible",
        "capital controls", "liberalised", "liberalized",
    ],
}


def validate_country_overview_signals(data: Dict[str, Any], result: ValidationResult) -> None:
    overview = data.get("country_overview")
    if not ensure_non_empty_string(overview):
        return

    lowered = overview.lower()
    missing_signals = []
    for signal in rs.COUNTRY_OVERVIEW_REQUIRED_SIGNALS:
        keywords = OVERVIEW_SIGNAL_KEYWORDS.get(signal, [])
        if not any(k in lowered for k in keywords):
            missing_signals.append(signal)

    if missing_signals:
        result.error(f"country_overview is missing required quality signals: {sorted(missing_signals)}")


def validate_source_authorities(data: Dict[str, Any], result: ValidationResult) -> Set[str]:
    source_authorities = data.get("source_authorities")
    normalized_urls: Set[str] = set()

    if not isinstance(source_authorities, list) or not source_authorities:
        result.error("source_authorities must be a non-empty list")
        return normalized_urls

    primary_count = 0

    for idx, item in enumerate(source_authorities):
        prefix = f"source_authorities[{idx}]"
        if not isinstance(item, dict):
            result.error(f"{prefix} must be an object")
            continue

        missing = rs.SOURCE_AUTHORITY_REQUIRED_KEYS - set(item.keys())
        if missing:
            result.error(f"{prefix} missing required keys: {sorted(missing)}")

        label = item.get("label")
        url = item.get("url")
        source_type = item.get("type")
        tier = item.get("tier")

        if not ensure_non_empty_string(label):
            result.error(f"{prefix}.label must be a non-empty string")

        if not is_https_url(url):
            result.error(f"{prefix}.url must be an HTTPS URL")
        else:
            normalized_urls.add(canonicalize_url(url))

        if source_type not in rs.VALID_SOURCE_TYPES:
            result.error(f"{prefix}.type invalid: {source_type}")

        if tier not in {"primary", "secondary"}:
            result.error(f"{prefix}.tier must be 'primary' or 'secondary'")

        if source_type in rs.PRIMARY_SOURCE_TYPES and tier != "primary":
            result.error(f"{prefix} has primary source type but tier='{tier}'")

        if source_type in rs.SECONDARY_SOURCE_TYPES and tier != "secondary":
            result.error(f"{prefix} has secondary source type but tier='{tier}'")

        if source_type in rs.PRIMARY_SOURCE_TYPES:
            primary_count += 1

    if primary_count == 0:
        result.error("source_authorities must include at least one primary official source")

    if primary_count < 2:
        result.warn("source_authorities has fewer than two primary official sources")

    return normalized_urls


PROBLEMATIC_LEGAL_PHRASES = [
    "guaranteed compliant",
    "legally guaranteed",
    "this is legal advice",
    "certified legal guidance",
]


def validate_source_map(data: Dict[str, Any], source_authority_urls: Set[str], result: ValidationResult) -> None:
    source_map = data.get("source_map")
    status = data.get("page_status")

    if not isinstance(source_map, dict):
        result.error("source_map must be present and must be an object")
        return

    missing_keys = set(rs.SOURCE_MAP_KEYS) - set(source_map.keys())
    if missing_keys:
        result.error(f"source_map missing required keys: {sorted(missing_keys)}")

    for key in rs.SOURCE_MAP_KEYS:
        entries = source_map.get(key)
        if not isinstance(entries, list) or not entries:
            result.error(f"source_map['{key}'] must be a non-empty list")
            continue

        for i, entry in enumerate(entries):
            prefix = f"source_map['{key}'][{i}]"
            if not isinstance(entry, dict):
                result.error(f"{prefix} must be an object; raw string entries are not allowed")
                continue

            missing = rs.SOURCE_MAP_ENTRY_REQUIRED_KEYS - set(entry.keys())
            if missing:
                result.error(f"{prefix} missing required keys: {sorted(missing)}")

            unknown = set(entry.keys()) - (rs.SOURCE_MAP_ENTRY_REQUIRED_KEYS | rs.SOURCE_MAP_ENTRY_OPTIONAL_KEYS)
            if unknown:
                result.warn(f"{prefix} has unknown keys: {sorted(unknown)}")

            url = entry.get("url")
            pages = entry.get("pages")
            section = entry.get("section")

            if not is_https_url(url):
                result.error(f"{prefix}.url must be an HTTPS URL")
                continue

            canon_url = canonicalize_url(url)
            if rs.NORMALIZE_SOURCE_URL_MATCHING and canon_url not in source_authority_urls:
                result.error(f"{prefix}.url does not match any canonicalized source_authorities URL: {url}")

            if not ensure_list_of_ints(pages):
                result.error(f"{prefix}.pages must be a list of integers")
            else:
                if is_pdf_url(url) and status in {rs.PageStatus.VERIFIED.value, rs.PageStatus.PUBLISHED.value} and len(pages) == 0:
                    result.error(f"{prefix}.pages must be non-empty for PDF sources when status is {status}")

            if not ensure_non_empty_string(section):
                result.error(f"{prefix}.section must be a non-empty string")


def validate_lifecycle_consistency(data: Dict[str, Any], result: ValidationResult) -> None:
    status = data.get("page_status")
    tier = data.get("evidence_tier")
    pub_class = data.get("publication_class")
    indexing = data.get("indexing_allowed")
    official_available = data.get("official_source_available")
    source_notice = data.get("source_notice", "")

    if status == rs.PageStatus.PUBLISHED.value:
        if tier != rs.EvidenceTier.OFFICIAL_VERIFIED.value:
            result.error("published requires evidence_tier=official_verified")
        if pub_class != rs.PublicationClass.REFERENCE.value:
            result.error("published requires publication_class=reference")
        if indexing is not True:
            result.error("published requires indexing_allowed=True")

    elif status == rs.PageStatus.VERIFIED.value:
        if tier != rs.EvidenceTier.OFFICIAL_VERIFIED.value:
            result.error("verified requires evidence_tier=official_verified")
        if pub_class != rs.PublicationClass.REFERENCE.value:
            result.error("verified requires publication_class=reference")

    elif status == rs.PageStatus.NEEDS_HARDENING.value:
        if tier != rs.EvidenceTier.OFFICIAL_VERIFIED_PARTIAL.value:
            result.error("needs_hardening requires evidence_tier=official_verified_partial")
        if indexing is not False:
            result.error("needs_hardening requires indexing_allowed=False")
        if not ensure_non_empty_string(source_notice):
            result.error("needs_hardening requires a non-empty source_notice")

    elif status == rs.PageStatus.SECONDARY_REVIEW.value:
        if tier != rs.EvidenceTier.SECONDARY_INSTITUTIONAL.value:
            result.error("secondary_review requires evidence_tier=secondary_institutional")
        if pub_class != rs.PublicationClass.LIMITED.value:
            result.error("secondary_review requires publication_class=limited")
        if indexing is not False:
            result.error("secondary_review requires indexing_allowed=False")
        if not ensure_non_empty_string(source_notice):
            result.error("secondary_review requires a non-empty source_notice")

    elif status in {rs.PageStatus.NEEDS_REVIEW.value, rs.PageStatus.BLOCKED.value}:
        if tier != rs.EvidenceTier.INTERNAL.value:
            result.error(f"{status} requires evidence_tier=internal")
        if pub_class != rs.PublicationClass.BLOCKED.value:
            result.error(f"{status} requires publication_class=blocked")
        if indexing is not False:
            result.error(f"{status} requires indexing_allowed=False")
    else:
        result.error(f"Invalid page_status: {status}")

    if tier in {rs.EvidenceTier.OFFICIAL_VERIFIED.value, rs.EvidenceTier.OFFICIAL_VERIFIED_PARTIAL.value} and official_available is not True:
        result.error(f"{tier} requires official_source_available=True")

    if tier in {rs.EvidenceTier.SECONDARY_INSTITUTIONAL.value, rs.EvidenceTier.INTERNAL.value} and official_available is not False:
        result.error(f"{tier} requires official_source_available=False")

    if status in {rs.PageStatus.VERIFIED.value, rs.PageStatus.PUBLISHED.value}:
        if source_notice not in {"", None}:
            result.warn(f"{status} should normally have an empty source_notice")

    if indexing is True and status not in rs.INDEXABLE_STATUSES:
        result.error(f"indexing_allowed=True is only valid for statuses in {sorted(rs.INDEXABLE_STATUSES)}")


def validate_disclaimer(data: Dict[str, Any], result: ValidationResult) -> None:
    disclaimer = data.get("disclaimer")
    if not ensure_non_empty_string(disclaimer):
        result.error("disclaimer must be a non-empty string")
        return

    if len(disclaimer.strip()) < rs.MIN_DISCLAIMER_CHARS:
        result.error(f"disclaimer must be at least {rs.MIN_DISCLAIMER_CHARS} characters")

    lowered = disclaimer.lower()
    for phrase in PROBLEMATIC_LEGAL_PHRASES:
        if phrase in lowered:
            result.error(f"disclaimer contains problematic legal phrase: {phrase}")

    pat = text_contains_forbidden_pattern(disclaimer)
    if pat:
        result.error(f"disclaimer contains forbidden placeholder pattern: {pat}")


def validate_file(path: Path) -> ValidationResult:
    result = ValidationResult(path=path)

    try:
        data = parse_json(path)
    except Exception as exc:
        result.error(f"Invalid JSON: {exc}")
        return result

    if not isinstance(data, dict):
        result.error("Top-level JSON must be an object")
        return result

    validate_top_level_structure(data, result)
    validate_text_quality(data, result)
    validate_country_overview_signals(data, result)
    authority_urls = validate_source_authorities(data, result)
    validate_source_map(data, authority_urls, result)
    validate_lifecycle_consistency(data, result)
    validate_disclaimer(data, result)

    return result


def print_result(result: ValidationResult) -> None:
    print(f"\nFILE: {result.path}")
    for note in result.notes:
        print(f"  NOTE: {note}")
    for warning in result.warnings:
        print(f"  WARNING: {warning}")
    for error in result.errors:
        print(f"  ERROR: {error}")

    if result.ok:
        print("  PASS — 0 errors, 0 warnings")
    else:
        print(f"  FAIL — {len(result.errors)} error(s), {len(result.warnings)} warning(s)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ConvertCCY sovereign FX rules JSON files")
    parser.add_argument("path", help="Path to a JSON file or a directory containing JSON files")
    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f"ERROR: path does not exist: {target}", file=sys.stderr)
        return 2

    files = gather_json_files(target)
    if not files:
        print(f"ERROR: no JSON files found under: {target}", file=sys.stderr)
        return 2

    results = [validate_file(p) for p in files]
    for result in results:
        print_result(result)

    total_errors = sum(len(r.errors) for r in results)
    total_warnings = sum(len(r.warnings) for r in results)

    print("\nSUMMARY")
    print(f"  Files checked: {len(results)}")
    print(f"  Errors:        {total_errors}")
    print(f"  Warnings:      {total_warnings}")

    return 0 if total_errors == 0 and total_warnings == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
