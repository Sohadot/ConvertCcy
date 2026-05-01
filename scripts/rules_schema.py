"""
ConvertCCY — Global FX Rules Reference Layer
=============================================
rules_schema.py — Canonical schema definition for all country rule files.
Every country JSON must conform to this schema before ingestion.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional
from enum import Enum


class PageStatus(str, Enum):
    PUBLISHED         = "published"
    VERIFIED          = "verified"
    DRAFT             = "draft"
    NEEDS_REVIEW      = "needs_source_review"
    BLOCKED           = "blocked"


class Region(str, Enum):
    NORTH_AFRICA      = "North Africa"
    SUB_SAHARAN       = "Sub-Saharan Africa"
    MIDDLE_EAST       = "Middle East"
    SOUTH_ASIA        = "South Asia"
    EAST_ASIA         = "East Asia"
    SOUTHEAST_ASIA    = "Southeast Asia"
    CENTRAL_ASIA      = "Central Asia"
    EASTERN_EUROPE    = "Eastern Europe"
    WESTERN_EUROPE    = "Western Europe"
    NORTH_AMERICA     = "North America"
    LATIN_AMERICA     = "Latin America"
    CARIBBEAN         = "Caribbean"
    OCEANIA           = "Oceania"
    SOUTH_EUROPE      = "Southern Europe"
    NORTH_EUROPE      = "Northern Europe"
    CENTRAL_EUROPE    = "Central Europe"
    CAUCASUS          = "Caucasus"
    PACIFIC           = "Pacific"


# ── Required field sentinel ─────────────────────────────────────────────────
REQUIRED = "__REQUIRED__"

# Minimum character thresholds — prevents placeholder/thin content
MIN_CHARS_RULE_FIELD     = 80
MIN_CHARS_SUMMARY        = 120
MIN_CHARS_OVERVIEW       = 150
MAX_SIMILARITY_RATIO     = 0.72   # Reject near-duplicate content across fields

# ── Source authority structure ───────────────────────────────────────────────
SOURCE_AUTHORITY_SCHEMA = {
    "label": str,       # e.g. "Reserve Bank of India"
    "url":   str,       # Must be HTTPS, validated
    "type":  str,       # "central_bank" | "customs" | "ministry" | "regulator" | "other"
}

# ── Full country rule schema ─────────────────────────────────────────────────
COUNTRY_RULE_SCHEMA = {
    # Identity
    "country_name":         str,        # Full English name: "Saudi Arabia"
    "country_slug":         str,        # URL slug: "saudi-arabia"
    "iso2":                 str,        # "SA"
    "iso3":                 str,        # "SAU"
    "region":               str,        # Must match Region enum
    "currency_code":        str,        # "SAR"
    "currency_name":        str,        # "Saudi Riyal"

    # Publishing
    "page_status":          str,        # Must match PageStatus enum
    "last_reviewed":        str,        # ISO date "2026-04-30"
    "schema_version":       str,        # "1.0"

    # Overview
    "country_overview":     str,        # Reference overview for the country's FX framework

    # Summaries (human-readable, min 120 chars each)
    "summary": {
        "traveler":         str,        # Practical note for visitors/tourists
        "business":         str,        # Practical note for companies/importers
    },

    # Core rule fields (min 80 chars each, no placeholders)
    "rules": {
        "bring_foreign_currency_in":        str,
        "take_foreign_currency_out":        str,
        "cash_declaration_threshold":       str,
        "resident_holding_rules":           str,
        "non_resident_rules":               str,
        "business_invoicing_settlement":    str,
        "exchange_controls":                str,
        "banking_conversion_practicality":  str,
    },

    # Sources — minimum 1, ideally 2+
    "source_authorities": list,     # List of SOURCE_AUTHORITY_SCHEMA dicts
    "official_sources":   list,     # Accepted alias for source_authorities

    # Legal
    "disclaimer": str,              # Standard or custom, must be present
}

# Standard disclaimer (used when custom not provided)
STANDARD_DISCLAIMER = (
    "This page provides general informational reference only. "
    "Foreign currency rules change frequently and vary by individual circumstances, "
    "residency status, transaction type, and applicable law. "
    "This is not legal, regulatory, tax, financial, or compliance advice. "
    "Always verify current rules with the relevant official authority "
    "before making any financial or travel decisions."
)

# Forbidden placeholder patterns — any of these in content = REJECT
FORBIDDEN_PATTERNS = [
    "TBD", "TODO", "PLACEHOLDER", "N/A", "to be added",
    "coming soon", "under review", "unknown", "not available",
    "Lorem ipsum", "fill in", "[insert", "{{", "}}",
]
