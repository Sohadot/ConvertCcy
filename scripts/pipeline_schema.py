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


def rules_path(slug: str) -> Path:
    return RULES_DIR / f"{slug}.json"
