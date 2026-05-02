"""
ConvertCCY — Global FX Rules Reference Layer
=============================================
rules_schema.py v1.2 — Canonical schema for country rule files.

Sovereign Reference Standard
─────────────────────────────
Every field must trace to an official source.
Every source must trace to a specific page or section.
No generic or unverifiable content is permitted.
No page is published before passing all 9 validation gates.

Changes from v1.1
─────────────────
+ country_overview            mandatory new field
+ source_map                  mandatory new field (field-level traceability)
+ PageStatus.NEEDS_HARDENING  new lifecycle stage
+ EvidenceTier.OFFICIAL_VERIFIED_PARTIAL  new partial tier
+ VALID_SOURCE_TYPES expanded:
    primary_regulator
    primary_regulator_faq
    primary_regulator_rule_page
+ Gate 9: source_map integrity check
+ HARDENING_CHECKLIST for needs_hardening → verified transition
"""

from enum import Enum


# ─────────────────────────────────────────────────────────────────────────────
# PAGE STATUS
# ─────────────────────────────────────────────────────────────────────────────

class PageStatus(str, Enum):
    """
    Lifecycle:
        needs_source_review → needs_hardening → verified → published

    needs_source_review:
        Research incomplete. Internal only. Never published.

    needs_hardening:
        Sources identified and URL-cited in source_map.
        Content written field-by-field from official documents.
        PDF page numbers may still be pending.
        Not yet published — awaiting final hardening review.

    verified:
        All 9 gates passed. source_map complete.
        PDF page numbers filled. Ready for public HTML generation.

    published:
        Live. Indexed. In sitemap.

    secondary_review:
        Tier B — secondary sources only. noindex enforced.

    blocked:
        Known issue. Never published.
    """
    PUBLISHED        = "published"
    VERIFIED         = "verified"
    NEEDS_HARDENING  = "needs_hardening"      # NEW v1.2
    NEEDS_REVIEW     = "needs_source_review"
    SECONDARY_REVIEW = "secondary_review"
    BLOCKED          = "blocked"


# ─────────────────────────────────────────────────────────────────────────────
# EVIDENCE TIER
# ─────────────────────────────────────────────────────────────────────────────

class EvidenceTier(str, Enum):
    """
    Tier A  — official_verified:
        Every field sourced from primary official documents.
        source_map complete. PDF page numbers filled.
        Full indexing. Core of the sovereign reference layer.

    Tier A- — official_verified_partial:   (NEW v1.2)
        Primary sources identified and URL-cited.
        source_map populated. PDF page numbers pending.
        Published as reference with source_notice disclosure.
        Eligible for indexing with explicit notice.

    Tier B  — secondary_institutional:
        Credible secondary sources only.
        Published with strong source notice. noindex enforced.

    Tier C  — internal:
        Incomplete or unverifiable. Never published.
    """
    OFFICIAL_VERIFIED         = "official_verified"
    OFFICIAL_VERIFIED_PARTIAL = "official_verified_partial"  # NEW v1.2
    SECONDARY_INSTITUTIONAL   = "secondary_institutional"
    INTERNAL                  = "internal"


# ─────────────────────────────────────────────────────────────────────────────
# PUBLICATION CLASS
# ─────────────────────────────────────────────────────────────────────────────

class PublicationClass(str, Enum):
    REFERENCE = "reference"   # Tier A / A- — fully indexed
    LIMITED   = "limited"     # Tier B — source notice, noindex
    BLOCKED   = "blocked"     # Tier C — not published


# ─────────────────────────────────────────────────────────────────────────────
# REGION
# ─────────────────────────────────────────────────────────────────────────────

class Region(str, Enum):
    NORTH_AFRICA   = "North Africa"
    SUB_SAHARAN    = "Sub-Saharan Africa"
    MIDDLE_EAST    = "Middle East"
    SOUTH_ASIA     = "South Asia"
    EAST_ASIA      = "East Asia"
    SOUTHEAST_ASIA = "Southeast Asia"
    CENTRAL_ASIA   = "Central Asia"
    EASTERN_EUROPE = "Eastern Europe"
    WESTERN_EUROPE = "Western Europe"
    NORTH_AMERICA  = "North America"
    LATIN_AMERICA  = "Latin America"
    CARIBBEAN      = "Caribbean"
    OCEANIA        = "Oceania"
    SOUTH_EUROPE   = "Southern Europe"
    NORTH_EUROPE   = "Northern Europe"
    CENTRAL_EUROPE = "Central Europe"
    CAUCASUS       = "Caucasus"
    PACIFIC        = "Pacific"


# ─────────────────────────────────────────────────────────────────────────────
# VERSION & THRESHOLDS
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA_VERSION_CURRENT = "1.2"

MIN_CHARS_OVERVIEW   = 200   # country_overview (raised from v1.1)
MIN_CHARS_RULE_FIELD = 80    # each rules.* field
MIN_CHARS_SUMMARY    = 120   # each summary.* field
MAX_SIMILARITY_RATIO = 0.72  # reject near-duplicate content between rule fields


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE TYPES
# ─────────────────────────────────────────────────────────────────────────────

VALID_SOURCE_TYPES = {
    # Primary official
    "central_bank",
    "customs",
    "ministry",
    "regulator",
    "primary_regulator",            # NEW v1.2 — general primary regulatory body
    "primary_regulator_faq",        # NEW v1.2 — official FAQ or Q&A page
    "primary_regulator_rule_page",  # NEW v1.2 — official instruction/rule page
    # Secondary institutional
    "law_firm",
    "big_four",
    "chamber_of_commerce",
    "multilateral",
    "banking_guide",
    "other",
}

PRIMARY_SOURCE_TYPES = {
    "central_bank", "customs", "ministry", "regulator",
    "primary_regulator", "primary_regulator_faq",
    "primary_regulator_rule_page",
}

SECONDARY_SOURCE_TYPES = {
    "law_firm", "big_four", "chamber_of_commerce",
    "multilateral", "banking_guide", "other",
}


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE MAP (NEW v1.2)
# ─────────────────────────────────────────────────────────────────────────────

# All 11 content fields that require source_map entries
SOURCE_MAP_KEYS = [
    "country_overview",
    "summary.traveler",
    "summary.business",
    "rules.bring_foreign_currency_in",
    "rules.take_foreign_currency_out",
    "rules.cash_declaration_threshold",
    "rules.resident_holding_rules",
    "rules.non_resident_rules",
    "rules.business_invoicing_settlement",
    "rules.exchange_controls",
    "rules.banking_conversion_practicality",
]

# Structure of each source_map entry:
# {
#   "url":     "https://..."   — HTTPS, must match a source_authorities URL
#   "pages":   [1, 2, 15]     — page numbers within PDF; [] for web pages
#   "section": "Article 14"   — section name, FAQ number, chapter, or article
# }
#
# Rule: for page_status = "verified"    → PDF sources must have non-empty pages
# Rule: for page_status = "needs_hardening" → pages: [] is permitted (pending)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLISHABLE STATUS SETS
# ─────────────────────────────────────────────────────────────────────────────

PUBLISHABLE_TIER_A = {
    PageStatus.PUBLISHED.value,
    PageStatus.VERIFIED.value,
}

PUBLISHABLE_WITH_DISCLOSURE = {
    PageStatus.NEEDS_HARDENING.value,   # Published with source_notice in v1.2
}

PUBLISHABLE_TIER_B = {
    PageStatus.SECONDARY_REVIEW.value,
}

ALL_PUBLISHABLE = (
    PUBLISHABLE_TIER_A |
    PUBLISHABLE_WITH_DISCLOSURE |
    PUBLISHABLE_TIER_B
)

NEVER_PUBLISH = {
    PageStatus.NEEDS_REVIEW.value,
    PageStatus.BLOCKED.value,
}


# ─────────────────────────────────────────────────────────────────────────────
# STANDARD TEXT BLOCKS
# ─────────────────────────────────────────────────────────────────────────────

STANDARD_DISCLAIMER_TIER_A = (
    "This page provides general informational reference only. "
    "Foreign currency rules change frequently and vary by individual circumstances, "
    "residency status, transaction type, and applicable law. "
    "This is not legal, regulatory, tax, financial, or compliance advice. "
    "Always verify current rules with the relevant official authority "
    "before making any financial or travel decisions."
)

STANDARD_DISCLAIMER_TIER_B = (
    "This page is based on secondary institutional sources and has not been "
    "independently verified against primary official regulatory publications. "
    "It provides general informational orientation only and should not be "
    "treated as an authoritative regulatory statement. "
    "Foreign currency rules change frequently. "
    "This is not legal, regulatory, tax, financial, or compliance advice. "
    "Always verify current rules directly with the relevant official authority "
    "before making any financial, business, or travel decisions."
)

STANDARD_SOURCE_NOTICE_TIER_B = (
    "This entry is based on secondary institutional sources "
    "(advisory, legal, or industry publications) rather than primary official "
    "government or regulatory sources. It is provided for general orientation "
    "and should not be treated as a regulatory reference."
)

STANDARD_SOURCE_NOTICE_HARDENING = (
    "This entry has been sourced from primary official publications. "
    "Field-level source mapping is complete. Page-level citations for PDF sources "
    "are pending final verification. Content should be independently confirmed "
    "with the relevant official authority before use in compliance decisions."
)


# ─────────────────────────────────────────────────────────────────────────────
# FORBIDDEN PATTERNS
# ─────────────────────────────────────────────────────────────────────────────

FORBIDDEN_PATTERNS = [
    "TBD", "TODO", "PLACEHOLDER", "to be added",
    "coming soon", "under review", "Lorem ipsum",
    "fill in", "[insert", "{{", "}}",
]


# ─────────────────────────────────────────────────────────────────────────────
# HARDENING CHECKLIST (NEW v1.2)
# ─────────────────────────────────────────────────────────────────────────────

HARDENING_CHECKLIST = """
ConvertCCY — Pre-publish hardening checklist
needs_hardening → verified transition

□ 01. country_overview
      - Written from primary official source
      - Cites specific law/regulation name and year
      - Minimum 200 characters
      - Positions the country in its regional/global FX context

□ 02. source_map keys
      - All 11 SOURCE_MAP_KEYS present
      - Each key has at least one entry

□ 03. source_map entries — PDF sources
      - `pages: []` replaced with actual page numbers
      - `section` cites article, chapter, or FAQ number

□ 04. source_map entries — web page sources
      - `section` cites FAQ number, article title, or section name
      - `pages: []` is acceptable for web pages

□ 05. source_map URL alignment
      - Every source_map URL appears in source_authorities

□ 06. Rule field content quality
      - Specific numbers, thresholds, legal references present
      - No field is purely generic (e.g. "check with authorities")
      - No forbidden placeholder patterns

□ 07. source_authorities
      - All URLs verified live and HTTPS
      - All types in VALID_SOURCE_TYPES
      - At least one PRIMARY_SOURCE_TYPES entry

□ 08. source_notice
      - Tier A verified: source_notice = ""
      - Tier A- partial: STANDARD_SOURCE_NOTICE_HARDENING or stronger
      - Tier B: STANDARD_SOURCE_NOTICE_TIER_B or stronger

□ 09. disclaimer
      - Present, minimum 60 characters
      - No problematic legal phrases

□ 10. schema_version = "1.2"

□ 11. Validation
      Run: python scripts/validate_rules.py data/rules/<slug>.json
      Required: PASS — 0 errors, 0 warnings
"""


# ─────────────────────────────────────────────────────────────────────────────
# DECISION MATRIX
# ─────────────────────────────────────────────────────────────────────────────
#
#  evidence_tier               | pub_class | indexing | source_map  | pages req.
#  ──────────────────────────────────────────────────────────────────────────────
#  official_verified           | reference | True     | complete    | YES (PDF)
#  official_verified_partial   | reference | True     | populated   | pending OK
#  secondary_institutional     | limited   | False    | populated   | not req.
#  internal                    | blocked   | False    | optional    | not req.
#
#
# GATE 8 INVARIANTS (evidence tier consistency — from v1.1, updated v1.2):
#
#   I1: indexing_allowed=True requires tier in
#       {official_verified, official_verified_partial}
#
#   I2: publication_class=reference requires tier in
#       {official_verified, official_verified_partial}
#
#   I3: Tier B requires source_notice non-empty
#
#   I4: Tier A / A- requires official_source_available=True
#
#   I5: Tier B requires official_source_available=False
#
#   I6: Tier B page_status must be secondary_review (or draft/blocked)
#
#   I7: Tier A / A- page_status must not be secondary_review
#
#   I8: Tier C requires indexing_allowed=False
#
#   I9: publication_class must match evidence_tier per matrix above
#
#
# GATE 9 INVARIANTS (source_map integrity — NEW v1.2):
#
#   I10: source_map must be present as a dict
#
#   I11: All 11 SOURCE_MAP_KEYS must be present in source_map
#
#   I12: Each key must have at least one entry (non-empty list)
#
#   I13: Each entry must have:
#        - url: HTTPS string (validated)
#        - pages: list of ints (may be empty for web pages)
#        - section: non-empty string
#
#   I14: For page_status=verified:
#        PDF sources (entries where url ends in .pdf) must have
#        non-empty pages list
#
#   I15: source_map URLs must each appear in source_authorities URLs
