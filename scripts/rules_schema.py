"""
ConvertCCY — Global FX Rules Reference Layer
============================================
rules_schema.py v1.2.1 — Canonical schema for country rule files.

Sovereign Reference Standard
────────────────────────────
Every field must trace to an official source.
Every source must trace to a specific page, section, FAQ, article, or clause.
No generic or unverifiable content is permitted.
No file enters the public indexed layer until it passes all validation gates
and the final hardening checklist.

Core doctrine
─────────────
1. needs_hardening is INTERNAL staging only.
2. verified is READY_FOR_PUBLICATION but not yet live.
3. published is LIVE + INDEXED + IN_SITEMAP.
4. secondary_review is never part of the sovereign public reference layer.
5. official_verified_partial is a staging evidence tier, not final truth.
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
        Research incomplete. Internal only. Never rendered publicly.

    needs_hardening:
        Source map is populated field-by-field.
        Primary sources identified.
        Final pinpoint hardening still pending.
        Internal staging only. Never public. Never indexed. Never in sitemap.

    verified:
        All validation gates passed.
        Source map complete and hardened.
        Eligible for HTML generation and release approval.
        Not yet live until explicitly published.

    published:
        Live. Public. Indexed. Included in sitemap.

    secondary_review:
        Secondary-source orientation only.
        Never part of the sovereign public reference layer.
        Noindex / preview only if explicitly rendered.

    blocked:
        Unusable. Never rendered.
    """
    PUBLISHED        = "published"
    VERIFIED         = "verified"
    NEEDS_HARDENING  = "needs_hardening"
    NEEDS_REVIEW     = "needs_source_review"
    SECONDARY_REVIEW = "secondary_review"
    BLOCKED          = "blocked"


# ─────────────────────────────────────────────────────────────────────────────
# EVIDENCE TIER
# ─────────────────────────────────────────────────────────────────────────────

class EvidenceTier(str, Enum):
    """
    official_verified:
        Full sovereign-grade evidence.
        Every content field is traceable to primary official sources.
        PDF citations pinpointed with page numbers where applicable.

    official_verified_partial:
        Primary sources identified and source_map populated,
        but final pinpoint hardening is still pending.
        Internal staging tier only. Never final public truth.

    secondary_institutional:
        Strong non-primary institutional material only.
        Orientation tier, never sovereign reference truth.

    internal:
        Incomplete, blocked, or research-only.
    """
    OFFICIAL_VERIFIED         = "official_verified"
    OFFICIAL_VERIFIED_PARTIAL = "official_verified_partial"
    SECONDARY_INSTITUTIONAL   = "secondary_institutional"
    INTERNAL                  = "internal"


# ─────────────────────────────────────────────────────────────────────────────
# PUBLICATION CLASS
# ─────────────────────────────────────────────────────────────────────────────

class PublicationClass(str, Enum):
    REFERENCE = "reference"   # sovereign reference layer
    LIMITED   = "limited"     # internal preview / secondary orientation only
    BLOCKED   = "blocked"     # never rendered


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

SCHEMA_VERSION_CURRENT = "1.2.1"

MIN_CHARS_OVERVIEW   = 200
MIN_CHARS_RULE_FIELD = 80
MIN_CHARS_SUMMARY    = 120
MIN_DISCLAIMER_CHARS = 60
MAX_SIMILARITY_RATIO = 0.72

# country_overview quality signals
COUNTRY_OVERVIEW_REQUIRED_SIGNALS = {
    "regulatory_authority",
    "fx_regime",
    "convertibility_or_controls",
}

# required sections
REQUIRED_TOP_LEVEL_KEYS = {
    "country_name",
    "country_slug",
    "iso2",
    "iso3",
    "region",
    "currency_code",
    "currency_name",
    "schema_version",
    "page_status",
    "last_reviewed",
    "evidence_tier",
    "official_source_available",
    "publication_class",
    "indexing_allowed",
    "source_notice",
    "country_overview",
    "summary",
    "rules",
    "source_authorities",
    "source_map",
    "disclaimer",
}

REQUIRED_SUMMARY_KEYS = {
    "traveler",
    "business",
}

REQUIRED_RULE_KEYS = {
    "bring_foreign_currency_in",
    "take_foreign_currency_out",
    "cash_declaration_threshold",
    "resident_holding_rules",
    "non_resident_rules",
    "business_invoicing_settlement",
    "exchange_controls",
    "banking_conversion_practicality",
}


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE TYPES
# ─────────────────────────────────────────────────────────────────────────────

VALID_SOURCE_TYPES = {
    # primary official
    "central_bank",
    "customs",
    "ministry",
    "regulator",
    "primary_regulator",
    "primary_regulator_faq",
    "primary_regulator_rule_page",
    "fiu",  # Financial Intelligence Unit / AML authority (e.g. NCA UKFIU, FinCEN, FINTRAC)
    # secondary institutional
    "law_firm",
    "big_four",
    "chamber_of_commerce",
    "multilateral",
    "banking_guide",
    "other",
}

PRIMARY_SOURCE_TYPES = {
    "central_bank",
    "customs",
    "ministry",
    "regulator",
    "primary_regulator",
    "primary_regulator_faq",
    "primary_regulator_rule_page",
    "fiu",
}

SECONDARY_SOURCE_TYPES = {
    "law_firm",
    "big_four",
    "chamber_of_commerce",
    "multilateral",
    "banking_guide",
    "other",
}


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE AUTHORITIES STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

SOURCE_AUTHORITY_REQUIRED_KEYS = {
    "label",
    "url",
    "type",
    "tier",
}

# Example:
# {
#   "label": "Office des Changes — FAQ on exporting dirhams",
#   "url": "https://www.oc.gov.ma/fr/faq/peut-exporter-des-dirhams",
#   "type": "primary_regulator_faq",
#   "tier": "primary"
# }


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE MAP
# ─────────────────────────────────────────────────────────────────────────────

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

SOURCE_MAP_ENTRY_REQUIRED_KEYS = {
    "url",
    "pages",
    "section",
}

SOURCE_MAP_ENTRY_OPTIONAL_KEYS = {
    "article",
    "clause",
    "source_kind",   # pdf | html | faq | notification | law | guidance
    "quote_hint",    # short human-readable trace hint
}

# Canonical source_map item:
# {
#   "url": "https://...",
#   "pages": [15, 16],     # [] allowed only for non-PDF sources OR needs_hardening files
#   "section": "Chapter V – Accounts",
#   "article": "Article 14",
#   "clause": "Clause 3",
#   "source_kind": "pdf",
#   "quote_hint": "threshold stated in import declaration rule"
# }

PDF_SOURCE_SUFFIXES = (".pdf",)
REQUIRE_PDF_PAGES_FOR_VERIFIED = True


# ─────────────────────────────────────────────────────────────────────────────
# STATUS / PUBLICATION POLICY
# ─────────────────────────────────────────────────────────────────────────────

# Public sovereign layer
LIVE_PUBLIC_STATUSES = {
    PageStatus.PUBLISHED.value,
}

# Ready for release, but not yet live
RELEASE_CANDIDATE_STATUSES = {
    PageStatus.VERIFIED.value,
}

# Internal or preview-only, never in public indexed layer
NON_PUBLIC_STATUSES = {
    PageStatus.NEEDS_HARDENING.value,
    PageStatus.NEEDS_REVIEW.value,
    PageStatus.SECONDARY_REVIEW.value,
    PageStatus.BLOCKED.value,
}

# Sitemap eligibility
SITEMAP_ELIGIBLE_STATUSES = {
    PageStatus.PUBLISHED.value,
}

# Indexing must correspond to the sovereign public layer only
INDEXABLE_STATUSES = {
    PageStatus.PUBLISHED.value,
}

# Preview-only rendering is an implementation choice, not a public publication state
PREVIEW_RENDERABLE_STATUSES = {
    PageStatus.VERIFIED.value,
    PageStatus.NEEDS_HARDENING.value,
    PageStatus.SECONDARY_REVIEW.value,
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
    "This entry is based on secondary institutional sources rather than primary "
    "official government or regulatory publications. It is provided for general "
    "orientation only and should not be treated as sovereign-grade regulatory truth."
)

STANDARD_SOURCE_NOTICE_HARDENING = (
    "This entry has been mapped field-by-field to primary official sources. "
    "Final pinpoint hardening is still pending. It is not yet part of the "
    "public sovereign reference layer."
)


# ─────────────────────────────────────────────────────────────────────────────
# FORBIDDEN PATTERNS
# ─────────────────────────────────────────────────────────────────────────────

FORBIDDEN_PATTERNS = [
    "TBD",
    "TODO",
    "PLACEHOLDER",
    "to be added",
    "coming soon",
    "under review",
    "Lorem ipsum",
    "fill in",
    "[insert",
    "{{",
    "}}",
]


# ─────────────────────────────────────────────────────────────────────────────
# URL NORMALIZATION POLICY
# ─────────────────────────────────────────────────────────────────────────────
#
# Gate 9 should compare canonicalized URLs, not raw strings.
# Validator should:
#   - strip trailing slash differences where safe
#   - remove tracking parameters
#   - lowercase scheme + hostname
#   - preserve path case unless platform rules allow normalization
#   - treat exact canonical match as valid
#
# This avoids false negatives when source_map and source_authorities
# point to the same source using slightly different URL forms.
# ─────────────────────────────────────────────────────────────────────────────

NORMALIZE_SOURCE_URL_MATCHING = True


# ─────────────────────────────────────────────────────────────────────────────
# HARDENING CHECKLIST
# ─────────────────────────────────────────────────────────────────────────────

HARDENING_CHECKLIST = """
ConvertCCY — Pre-publish hardening checklist
needs_hardening → verified transition

□ 01. country_overview
      - Written from primary official source
      - Mentions regulatory authority
      - Mentions FX regime
      - Mentions convertibility / exchange-control posture
      - Minimum 200 characters

□ 02. source_map keys
      - All 11 SOURCE_MAP_KEYS present
      - Each key has at least one entry

□ 03. source_map entries — shape
      - Every entry is an object
      - Required keys present: url, pages, section
      - Optional keys used where available: article, clause, source_kind, quote_hint

□ 04. source_map entries — PDF hardening
      - For verified files: all PDF entries have non-empty page lists
      - Section names are specific, not generic
      - Article / clause added where available

□ 05. source_map entries — web sources
      - section cites FAQ number, article title, or section name
      - pages=[] is acceptable for web pages

□ 06. source_authorities
      - Every source_map URL matches a canonicalized source_authorities URL
      - All URLs are HTTPS
      - All types are valid
      - At least two primary official sources exist where feasible

□ 07. rule content quality
      - Each summary field meets minimum length
      - Each rule field meets minimum length
      - No placeholders or unverifiable generic claims
      - No near-duplicate rule fields above MAX_SIMILARITY_RATIO

□ 08. evidence / publication consistency
      - official_verified_partial remains non-public
      - official_verified only after final hardening
      - secondary_institutional is never sovereign public truth

□ 09. disclaimer and source_notice
      - disclaimer present and compliant
      - source_notice matches lifecycle stage
      - verified files should normally have source_notice=""

□ 10. schema_version = "1.2.1"

□ 11. Validation
      Run: python scripts/validate_rules.py data/rules/<slug>.json
      Required: PASS — 0 errors, 0 warnings
"""


# ─────────────────────────────────────────────────────────────────────────────
# DECISION MATRIX
# ─────────────────────────────────────────────────────────────────────────────
#
# evidence_tier               | page_status         | pub_class | indexing | public layer
# ──────────────────────────────────────────────────────────────────────────────
# official_verified           | verified/published  | reference | true*    | yes (published only)
# official_verified_partial   | needs_hardening     | reference | false    | no
# secondary_institutional     | secondary_review    | limited   | false    | no
# internal                    | review/blocked      | blocked   | false    | no
#
# * indexing_allowed must be False for verified (release candidate); only published
#   may set indexing_allowed=True (INDEXABLE_STATUSES invariant).
#
#
# GATE 8 INVARIANTS (evidence / lifecycle consistency)
#
# I1: page_status=published requires:
#     evidence_tier=official_verified
#     publication_class=reference
#     indexing_allowed=True
#
# I2: page_status=verified requires:
#     evidence_tier=official_verified
#     publication_class=reference
#
# I3: page_status=needs_hardening requires:
#     evidence_tier=official_verified_partial
#     indexing_allowed=False
#
# I4: page_status=secondary_review requires:
#     evidence_tier=secondary_institutional
#     publication_class=limited
#     indexing_allowed=False
#
# I5: page_status in {needs_source_review, blocked} requires:
#     evidence_tier=internal
#     publication_class=blocked
#     indexing_allowed=False
#
# I6: official_source_available=True required for
#     {official_verified, official_verified_partial}
#
# I7: official_source_available=False required for
#     {secondary_institutional, internal}
#
# I8: source_notice must be empty or minimal for verified/published
#     and must be non-empty for needs_hardening / secondary_review
#
#
# GATE 9 INVARIANTS (source_map integrity)
#
# I9: source_map must be present and be a dict
#
# I10: all 11 SOURCE_MAP_KEYS must be present
#
# I11: each SOURCE_MAP_KEYS entry must be a non-empty list
#
# I12: every source_map item must be an object with:
#      - url: HTTPS string
#      - pages: list[int]
#      - section: non-empty string
#
# I13: if a source_map URL points to a PDF and page_status=verified or published,
#      pages must be non-empty
#
# I14: every source_map URL must match a canonicalized source_authorities URL
#
# I15: no raw string entries are allowed inside source_map lists


# ─────────────────────────────────────────────────────────────────────────────
# OPTIONAL SCHEMA SHAPE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

COUNTRY_RULE_SCHEMA = {
    "required_top_level_keys": REQUIRED_TOP_LEVEL_KEYS,
    "required_summary_keys": REQUIRED_SUMMARY_KEYS,
    "required_rule_keys": REQUIRED_RULE_KEYS,
    "required_source_authority_keys": SOURCE_AUTHORITY_REQUIRED_KEYS,
    "required_source_map_entry_keys": SOURCE_MAP_ENTRY_REQUIRED_KEYS,
    "optional_source_map_entry_keys": SOURCE_MAP_ENTRY_OPTIONAL_KEYS,
    "source_map_keys": SOURCE_MAP_KEYS,
    "valid_source_types": VALID_SOURCE_TYPES,
    "primary_source_types": PRIMARY_SOURCE_TYPES,
    "secondary_source_types": SECONDARY_SOURCE_TYPES,
    "schema_version_current": SCHEMA_VERSION_CURRENT,
}
