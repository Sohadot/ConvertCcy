"""
ConvertCCY — Global FX Rules Reference Layer
=============================================
validate_rules.py — Strict validation engine for country rule JSON files.
A file must pass ALL gates to be eligible for publication.
"""

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from difflib import SequenceMatcher

from rules_schema import (
    COUNTRY_RULE_SCHEMA, SOURCE_AUTHORITY_SCHEMA, PageStatus, Region,
    FORBIDDEN_PATTERNS, MIN_CHARS_RULE_FIELD, MIN_CHARS_SUMMARY,
    MIN_CHARS_OVERVIEW, MAX_SIMILARITY_RATIO, STANDARD_DISCLAIMER
)


# ── Validation result ─────────────────────────────────────────────────────────

class ValidationResult:
    def __init__(self):
        self.errors:   list[str] = []
        self.warnings: list[str] = []

    @property
    def passed(self) -> bool:
        return len(self.errors) == 0

    def error(self, msg: str):
        self.errors.append(f"[ERROR] {msg}")

    def warn(self, msg: str):
        self.warnings.append(f"[WARN]  {msg}")

    def report(self, country: str = "") -> str:
        lines = [f"=== Validation: {country} ==="]
        lines += self.errors
        lines += self.warnings
        lines.append(f"Result: {'PASS' if self.passed else 'FAIL'} "
                     f"({len(self.errors)} errors, {len(self.warnings)} warnings)")
        return "\n".join(lines)


# ── Gate 1: Schema integrity ──────────────────────────────────────────────────

def get_source_authorities(data: dict) -> list:
    """Accept the canonical source_authorities key and the official_sources alias."""
    return data.get("source_authorities") or data.get("official_sources") or []


def gate_schema_integrity(data: dict, result: ValidationResult):
    """All required top-level keys must exist with correct types."""
    required_top = [
        "country_name", "country_slug", "iso2", "iso3",
        "region", "currency_code", "currency_name",
        "page_status", "last_reviewed", "schema_version",
        "country_overview", "summary", "rules", "disclaimer",
    ]
    for key in required_top:
        if key not in data:
            result.error(f"Missing required field: '{key}'")
        elif not data[key]:
            result.error(f"Field '{key}' is empty")

    if "source_authorities" not in data and "official_sources" not in data:
        result.error("Missing required field: 'source_authorities' or 'official_sources'")
    elif not get_source_authorities(data):
        result.error("Source authority list is empty")

    # summary sub-fields
    summary = data.get("summary", {})
    for sub in ("traveler", "business"):
        if sub not in summary:
            result.error(f"Missing summary.{sub}")
        elif not summary[sub] or not summary[sub].strip():
            result.error(f"summary.{sub} is empty")

    # rules sub-fields
    rules = data.get("rules", {})
    required_rule_fields = [
        "bring_foreign_currency_in",
        "take_foreign_currency_out",
        "cash_declaration_threshold",
        "resident_holding_rules",
        "non_resident_rules",
        "business_invoicing_settlement",
        "exchange_controls",
        "banking_conversion_practicality",
    ]
    for rf in required_rule_fields:
        if rf not in rules:
            result.error(f"Missing rules.{rf}")
        elif not rules[rf] or not rules[rf].strip():
            result.error(f"rules.{rf} is empty")


# ── Gate 2: Enum validity ─────────────────────────────────────────────────────

def gate_enum_validity(data: dict, result: ValidationResult):
    status = data.get("page_status", "")
    if status not in [e.value for e in PageStatus]:
        result.error(f"Invalid page_status: '{status}'. "
                     f"Must be one of {[e.value for e in PageStatus]}")

    region = data.get("region", "")
    if region not in [e.value for e in Region]:
        result.warn(f"Region '{region}' not in standard Region enum — verify spelling")

    iso2 = data.get("iso2", "")
    if not re.match(r"^[A-Z]{2}$", iso2):
        result.error(f"iso2 '{iso2}' must be exactly 2 uppercase letters")

    iso3 = data.get("iso3", "")
    if not re.match(r"^[A-Z]{3}$", iso3):
        result.error(f"iso3 '{iso3}' must be exactly 3 uppercase letters")

    currency = data.get("currency_code", "")
    if not re.match(r"^[A-Z]{3}$", currency):
        result.error(f"currency_code '{currency}' must be 3 uppercase letters")


# ── Gate 3: Source integrity ──────────────────────────────────────────────────

def gate_source_integrity(data: dict, result: ValidationResult):
    sources = get_source_authorities(data)

    if not isinstance(sources, list):
        result.error("source_authorities/official_sources must be a list")
        return

    if len(sources) < 1:
        result.error("At least 1 source_authority required")
        return

    if len(sources) < 2:
        result.warn("Only 1 source — recommend adding a second official source")

    for i, src in enumerate(sources):
        if not isinstance(src, dict):
            result.error(f"source_authorities[{i}] must be a dict")
            continue

        for key in ("label", "url", "type"):
            if key not in src or not src[key]:
                result.error(f"source_authorities[{i}] missing or empty '{key}'")

        url = src.get("url", "")
        parsed = urlparse(url)
        if parsed.scheme != "https":
            result.error(f"source_authorities[{i}] URL must use HTTPS: '{url}'")
        if not parsed.netloc:
            result.error(f"source_authorities[{i}] URL has no domain: '{url}'")

        valid_types = {"central_bank", "customs", "ministry", "regulator", "other"}
        if src.get("type", "") not in valid_types:
            result.error(
                f"source_authorities[{i}] type '{src.get('type')}' "
                f"must be one of {valid_types}"
            )


# ── Gate 4: Content integrity ─────────────────────────────────────────────────

def gate_content_integrity(data: dict, result: ValidationResult):
    """Reject thin, placeholder, or near-duplicate content."""

    def check_field(text: str, field_name: str, min_chars: int):
        if not text or not text.strip():
            result.error(f"Content field '{field_name}' is empty")
            return

        stripped = text.strip()

        if len(stripped) < min_chars:
            result.error(
                f"'{field_name}' too short: {len(stripped)} chars "
                f"(minimum {min_chars})"
            )

        for pattern in FORBIDDEN_PATTERNS:
            if pattern.lower() in stripped.lower():
                result.error(
                    f"'{field_name}' contains forbidden placeholder: '{pattern}'"
                )

    # Check summaries
    check_field(data.get("country_overview", ""), "country_overview", MIN_CHARS_OVERVIEW)

    summary = data.get("summary", {})
    check_field(summary.get("traveler", ""), "summary.traveler", MIN_CHARS_SUMMARY)
    check_field(summary.get("business", ""), "summary.business", MIN_CHARS_SUMMARY)

    # Check rules fields
    rules = data.get("rules", {})
    rule_fields = [
        "bring_foreign_currency_in",
        "take_foreign_currency_out",
        "cash_declaration_threshold",
        "resident_holding_rules",
        "non_resident_rules",
        "business_invoicing_settlement",
        "exchange_controls",
        "banking_conversion_practicality",
    ]
    rule_texts = []
    for rf in rule_fields:
        text = rules.get(rf, "")
        check_field(text, f"rules.{rf}", MIN_CHARS_RULE_FIELD)
        rule_texts.append((rf, text))

    # Similarity check — prevent copy-paste between rule fields
    for i in range(len(rule_texts)):
        for j in range(i + 1, len(rule_texts)):
            name_a, text_a = rule_texts[i]
            name_b, text_b = rule_texts[j]
            if not text_a or not text_b:
                continue
            ratio = SequenceMatcher(None, text_a.lower(), text_b.lower()).ratio()
            if ratio > MAX_SIMILARITY_RATIO:
                result.error(
                    f"Content too similar between '{name_a}' and '{name_b}' "
                    f"(similarity {ratio:.2f} > {MAX_SIMILARITY_RATIO}) — "
                    f"likely copy-paste or generic content"
                )


# ── Gate 5: Legal safety ──────────────────────────────────────────────────────

def gate_legal_safety(data: dict, result: ValidationResult):
    disclaimer = data.get("disclaimer", "")
    if not disclaimer or len(disclaimer.strip()) < 60:
        result.error("Disclaimer missing or too short (min 60 chars)")

    forbidden_legal = [
        "legal advice", "guaranteed", "definitive", "final answer",
        "always accurate", "fully up to date", "replace a lawyer",
        "legally binding",
    ]
    for phrase in forbidden_legal:
        if phrase.lower() in disclaimer.lower():
            result.error(
                f"Disclaimer contains problematic phrase: '{phrase}'"
            )


# ── Gate 6: Date integrity ────────────────────────────────────────────────────

def gate_date_integrity(data: dict, result: ValidationResult):
    last_reviewed = data.get("last_reviewed", "")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", last_reviewed):
        result.error(
            f"last_reviewed '{last_reviewed}' must be ISO format YYYY-MM-DD"
        )


# ── Gate 7: Slug integrity ────────────────────────────────────────────────────

def gate_slug_integrity(data: dict, result: ValidationResult):
    slug = data.get("country_slug", "")
    if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", slug):
        result.error(
            f"country_slug '{slug}' must be lowercase alphanumeric with hyphens only"
        )
    expected_suffix = "-foreign-currency-rules"
    # Slug in data is just the country part; page slug appends suffix in generator


# ── Master validation function ────────────────────────────────────────────────

def validate_country_file(filepath: str | Path) -> ValidationResult:
    result = ValidationResult()
    path = Path(filepath)

    if not path.exists():
        result.error(f"File not found: {filepath}")
        return result

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        result.error(f"Invalid JSON: {e}")
        return result

    country = data.get("country_name", path.stem)

    gate_schema_integrity(data, result)
    gate_enum_validity(data, result)
    gate_source_integrity(data, result)
    gate_content_integrity(data, result)
    gate_legal_safety(data, result)
    gate_date_integrity(data, result)
    gate_slug_integrity(data, result)

    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def validate_directory(rules_dir: str = "data/rules") -> dict:
    """Validate all JSON files in a rules directory. Returns summary dict."""
    path = Path(rules_dir)
    if not path.exists():
        print(f"Directory not found: {rules_dir}")
        return {}

    files = sorted(path.glob("*.json"))
    if not files:
        print(f"No JSON files found in {rules_dir}")
        return {}

    results = {}
    passed = failed = 0

    for f in files:
        r = validate_country_file(f)
        results[f.stem] = r
        print(r.report(f.stem))
        print()
        if r.passed:
            passed += 1
        else:
            failed += 1

    print(f"{'='*50}")
    print(f"Total: {len(files)} | Passed: {passed} | Failed: {failed}")
    return results


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "data/rules"
    p = Path(target)
    if p.is_file():
        r = validate_country_file(p)
        print(r.report(p.stem))
        sys.exit(0 if r.passed else 1)
    else:
        results = validate_directory(target)
        failed = sum(1 for r in results.values() if not r.passed)
        sys.exit(1 if failed else 0)
