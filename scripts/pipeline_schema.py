#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipeline_schema.py — Canonical schema for Governed Country Pipeline artifacts.

Phase 1 executable companion to COUNTRY_REVIEW_EXECUTION_PROTOCOL.md and
data/governance/country_pipeline_policy.json.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO / "data" / "governance" / "country_pipeline_policy.json"
PIPELINE_ROOT = REPO / "data" / "coverage" / "pipeline"
RULES_DIR = REPO / "data" / "rules"

CLAIM_STATUSES = {
    "verified",
    "bounded",
    "verification_target",
    "superseded",
    "source_intake_pending",
}

CLAIM_TYPES = {
    "positive",
    "negative",
    "operational",
    "historical",
    "compound",
}

EVIDENCE_LEVELS = {"E0", "E1", "E2", "E3"}

SOURCE_CURRENCY = {
    "current",
    "superseded",
    "unknown",
    "historical",
}

CLAIM_CATEGORIES = {
    "legal_thresholds",
    "mandatory_actions",
    "prohibited_actions",
    "operational",
    "regime",
    "negative_scope",
    "other",
}

REVIEW_DECISIONS = {"PASS", "BLOCK"}

REVIEW_LAYERS = {"structural", "evidence", "fidelity", "governance"}

SOURCES_REQUIRED_KEYS = {
    "schema_version",
    "country_slug",
    "country_name",
    "iso2",
    "sources",
}

SOURCE_ITEM_REQUIRED_KEYS = {
    "source_id",
    "label",
    "url",
    "type",
    "tier",
    "currency",
}

CLAIMS_REQUIRED_KEYS = {
    "schema_version",
    "country_slug",
    "claims",
}

CLAIM_ITEM_REQUIRED_KEYS = {
    "claim_id",
    "status",
    "type",
    "subject",
    "rule",
    "authority",
    "evidence_target",
    "source_refs",
    "allowed_wording",
    "forbidden_inferences",
}

CLAIM_ITEM_OPTIONAL_KEYS = {
    "scope",
    "final_evidence_level",
    "source_budget",
    "stop_condition",
    "category",
    "matching_source_note",
    "needs_human_review",
}

FIELD_BINDINGS_REQUIRED_KEYS = {
    "schema_version",
    "country_slug",
    "bindings",
}

BINDING_ITEM_REQUIRED_KEYS = {
    "field",
    "claim_ids",
}

BINDING_ITEM_OPTIONAL_KEYS = {
    "wording_boundary",
    "notes",
}

REVIEW_REPORT_REQUIRED_KEYS = {
    "schema_version",
    "country_slug",
    "decision",
    "layers",
    "blocking_findings",
    "improvement_findings",
    "needs_human_review",
}

FINDING_REQUIRED_KEYS = {
    "layer",
    "field",
    "reason",
    "required_action",
}

PIPELINE_SCHEMA_VERSION = "1.0.0"

PACK_FILENAMES = {
    "sources": "sources.json",
    "claims": "claims.json",
    "field_bindings": "field_bindings.json",
    "review_report": "review_report.json",
    "evidence_excerpts": "evidence_excerpts.json",
    "intake_report": "intake_report.json",
    "candidate_claims": "candidate_claims.json",
    "claim_extraction_report": "claim_extraction_report.json",
    "human_claim_review": "human_claim_review.json",
    "claim_review_report": "claim_review_report.json",
}

# Phase 2 M1 — intake / excerpt enums
CONTENT_PERSISTENCE = {"preserved", "fingerprinted", "not_preserved"}
EXCERPT_REPRESENTATIONS = {
    "verbatim_quote",
    "faithful_translation",
    "bounded_paraphrase",
}
CAPTURE_STATUSES = {"human_verified", "declared_unverified", "machine_assisted"}
CLAIM_NEUTRALITY_STATUSES = {"unreviewed", "reviewed", "exception_required"}
INTAKE_LAYERS = {
    "structural",
    "provenance",
    "authority",
    "currency",
    "neutrality",
    "eligibility",
}

# Phase 2 M2 — candidate claim enums
CANDIDATE_CLAIM_TYPES = {
    "descriptive_rule",
    "threshold",
    "required_action",
    "permitted_action",
    "prohibited_action",
    "institutional_role",
    "regime_description",
    "documentation_requirement",
    "exception",
    "definition",
}
TRANSFORMATION_MODES = {
    "direct_restating",
    "faithful_translation",
    "bounded_normalization",
    "single_source_composition",
    "multi_source_synthesis",
}
SUPPORT_STATUSES = {
    "unreviewed",
    "needs_evidence",
    "needs_human_review",
    "supported",
    "bounded",
    "rejected",
    "superseded",
}
SEMANTIC_REVIEW_STATUSES = {"pending", "closed"}
AUTHORITY_PRESERVATION_STATUSES = {
    "unreviewed",
    "structurally_consistent",
    "human_confirmed",
    "mismatch",
}
EXCEPTION_SIGNALS = {"unknown", "none_detected", "present"}
EXCEPTION_REVIEW_STATUSES = {"pending", "closed"}
HUMAN_REVIEW_STATUSES = {"pending", "closed"}
ORIGIN_MODES = {"generated", "human_authored"}
CLOSED_REVIEW_DECISIONS = {"supported", "bounded", "rejected", "needs_evidence"}
FORBIDDEN_PROJECT_CLAIM_STATUSES = {"verified", "verification_target"}
SEMANTIC_APPROVAL_STATES = {
    "not_established",
    "partially_reviewed",
    "human_review_closed",
}
REVIEW_COMPLETION_STATES = {"PENDING", "COMPLETE", "BLOCK"}
MILESTONE_DECISIONS = {"PASS", "PENDING", "BLOCK"}
CLAIM_REVIEW_LAYERS = {
    "structural",
    "coverage",
    "vocabulary",
    "fingerprint",
    "projection",
    "promotion",
    "eligibility",
}
SUPPORT_ROLES = {
    "direct",
    "definition",
    "scope",
    "exception",
    "temporal",
    "authority",
}
TEMPORAL_SCOPES = {
    "current",
    "historical",
    "effective_from",
    "effective_until",
    "unknown",
}
EXTRACTION_LAYERS = {
    "structural",
    "evidence",
    "transformation",
    "authority",
    "exception",
    "eligibility",
    "atomicity",
}

CANDIDATES_REQUIRED_KEYS = {
    "schema_version",
    "country_slug",
    "generation_mode",
    "candidates",
}

CANDIDATE_ITEM_REQUIRED_KEYS = {
    "candidate_id",
    "candidate_text",
    "claim_language",
    "claim_type",
    "scope",
    "evidence_links",
    "transformation",
    "authority_posture",
    "exception_handling",
    "origin",
    "semantic_review_status",
    "special_review_required",
    "support_status",
    "downstream_eligible",
    "adoption_gate_conditions_met",
    "adoption_eligible",
    "human_review",
}

HUMAN_CLAIM_REVIEW_REQUIRED_KEYS = {
    "schema_version",
    "country_slug",
    "milestone",
    "review_scope",
    "reviews",
}

HUMAN_REVIEW_ITEM_REQUIRED_KEYS = {
    "review_id",
    "candidate_id",
    "reviewer",
    "reviewed_at",
    "status",
    "decision",
    "candidate_text_snapshot",
    "reviewed_text",
    "reviewed_candidate_fingerprint",
    "semantic_review_status",
    "authority_preservation_status",
    "exception_review_status",
    "downstream_eligible",
    "adoption_gate_conditions_met",
    "adoption_eligible",
    "rationale",
}

SOURCE_ITEM_M1_REQUIRED_KEYS = SOURCE_ITEM_REQUIRED_KEYS | {
    "authority",
    "authority_kind",
    "jurisdiction",
    "accessed_at",
    "content_persistence",
}

EXCERPTS_REQUIRED_KEYS = {
    "schema_version",
    "country_slug",
    "excerpts",
}

EXCERPT_ITEM_REQUIRED_KEYS = {
    "excerpt_id",
    "source_id",
    "representation",
    "source_text",
    "source_language",
    "pinpoint",
    "capture_status",
    "verified_by",
    "verified_at",
    "verification_method",
    "captured_at",
    "captured_by",
    "method",
    "source_accessed_at",
    "claim_neutrality_status",
}

PINPOINT_LOCATOR_KEYS = {
    "article",
    "section",
    "heading",
    "page",
    "url_fragment",
    "locator_note",
}


def pack_dir(slug: str) -> Path:
    return PIPELINE_ROOT / slug


def pack_path(slug: str, kind: str) -> Path:
    return pack_dir(slug) / PACK_FILENAMES[kind]


def list_pipeline_slugs() -> list[str]:
    if not PIPELINE_ROOT.exists():
        return []
    slugs = []
    for child in sorted(PIPELINE_ROOT.iterdir()):
        if not child.is_dir():
            continue
        if (child / PACK_FILENAMES["claims"]).exists() and (
            child / PACK_FILENAMES["field_bindings"]
        ).exists() and (child / PACK_FILENAMES["sources"]).exists():
            slugs.append(child.name)
    return slugs


def list_intake_slugs() -> list[str]:
    """Packs that opted into Phase 2 M1 (have evidence_excerpts.json)."""
    if not PIPELINE_ROOT.exists():
        return []
    slugs = []
    for child in sorted(PIPELINE_ROOT.iterdir()):
        if not child.is_dir():
            continue
        if (child / PACK_FILENAMES["sources"]).exists() and (
            child / PACK_FILENAMES["evidence_excerpts"]
        ).exists():
            slugs.append(child.name)
    return slugs


def list_claim_extraction_slugs() -> list[str]:
    """Packs that opted into Phase 2 M2 (have candidate_claims.json)."""
    if not PIPELINE_ROOT.exists():
        return []
    slugs = []
    for child in sorted(PIPELINE_ROOT.iterdir()):
        if not child.is_dir():
            continue
        if (child / PACK_FILENAMES["candidate_claims"]).exists():
            slugs.append(child.name)
    return slugs


def list_human_claim_review_slugs() -> list[str]:
    """Packs that opted into Phase 2 M2.5 (have human_claim_review.json)."""
    if not PIPELINE_ROOT.exists():
        return []
    slugs = []
    for child in sorted(PIPELINE_ROOT.iterdir()):
        if not child.is_dir():
            continue
        if (child / PACK_FILENAMES["human_claim_review"]).exists():
            slugs.append(child.name)
    return slugs


def rules_path(slug: str) -> Path:
    return RULES_DIR / f"{slug}.json"
