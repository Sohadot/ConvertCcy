#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scope-gate unit tests for M2.5 allowlist and candidate field mutations."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from validate_pipeline_milestone_scope import (  # noqa: E402
    candidate_field_violations,
    evaluate_milestone_scope,
    is_m2_5_surface_touched,
    load_policy,
)


class MilestoneScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_policy()
        self.allowed_fields = list(
            (self.policy.get("human_claim_review") or {}).get("allowed_candidate_mutation_fields")
            or []
        )

    def test_non_allowlisted_file_blocks_when_milestone_touched(self) -> None:
        errors = evaluate_milestone_scope(
            [
                "data/coverage/pipeline/brazil/human_claim_review.json",
                "README.md",
            ],
            self.policy,
        )
        self.assertTrue(any("README.md" in e and "allowlist" in e for e in errors))

    def test_allowlisted_review_files_pass(self) -> None:
        errors = evaluate_milestone_scope(
            [
                "data/coverage/pipeline/brazil/human_claim_review.json",
                "data/coverage/pipeline/brazil/claim_review_report.json",
                "scripts/validate_human_claim_review.py",
                "tests/test_human_claim_review.py",
            ],
            self.policy,
        )
        self.assertEqual(errors, [])

    def test_forbidden_claims_json_blocks(self) -> None:
        errors = evaluate_milestone_scope(
            [
                "data/coverage/pipeline/brazil/human_claim_review.json",
                "data/coverage/pipeline/brazil/claims.json",
            ],
            self.policy,
        )
        self.assertTrue(any("claims.json" in e and "forbidden" in e for e in errors))

    def test_candidate_text_mutation_blocks(self) -> None:
        base = {
            "schema_version": "1.0.0",
            "country_slug": "brazil",
            "notes": "original",
            "candidates": [
                {
                    "candidate_id": "CC-BR-FX-001",
                    "candidate_text": "original text",
                    "scope": {"jurisdiction": "BR"},
                    "evidence_links": [],
                    "transformation": {"mode": "direct_restating"},
                    "origin": {"mode": "human_authored"},
                    "support_status": "unreviewed",
                    "downstream_eligible": False,
                    "adoption_eligible": False,
                    "adoption_gate_conditions_met": False,
                    "human_review": {"status": "pending"},
                    "authority_posture": {"authority_preservation_status": "unreviewed"},
                    "exception_handling": {"exception_review_status": "pending"},
                }
            ],
        }
        head = json.loads(json.dumps(base))
        head["candidates"][0]["candidate_text"] = "mutated text"
        errors = candidate_field_violations(base, head, self.allowed_fields)
        self.assertTrue(any("candidate_text" in e for e in errors))

    def test_allowed_review_field_mutation_passes(self) -> None:
        base = {
            "schema_version": "1.0.0",
            "country_slug": "brazil",
            "notes": "original",
            "candidates": [
                {
                    "candidate_id": "CC-BR-FX-001",
                    "candidate_text": "original text",
                    "scope": {"jurisdiction": "BR"},
                    "support_status": "unreviewed",
                    "downstream_eligible": False,
                    "adoption_eligible": False,
                    "adoption_gate_conditions_met": False,
                    "human_review": {"status": "pending"},
                    "authority_posture": {"authority_preservation_status": "unreviewed"},
                    "exception_handling": {"exception_review_status": "pending"},
                }
            ],
        }
        head = json.loads(json.dumps(base))
        head["candidates"][0]["support_status"] = "needs_evidence"
        head["candidates"][0]["adoption_eligible"] = False
        head["candidates"][0]["human_review"] = {"status": "closed", "decision": "needs_evidence"}
        errors = candidate_field_violations(base, head, self.allowed_fields)
        self.assertEqual(errors, [])

    def test_top_level_notes_mutation_blocks(self) -> None:
        base = {
            "schema_version": "1.0.0",
            "country_slug": "brazil",
            "notes": "original",
            "candidates": [{"candidate_id": "CC-X", "candidate_text": "t", "support_status": "unreviewed"}],
        }
        head = json.loads(json.dumps(base))
        head["notes"] = "changed"
        errors = candidate_field_violations(base, head, self.allowed_fields)
        self.assertTrue(any("notes" in e for e in errors))

    def test_m2_only_candidate_text_correction_does_not_freeze_fields(self) -> None:
        changed = [
            "data/coverage/pipeline/brazil/candidate_claims.json",
            "scripts/validate_claim_extraction.py",
        ]
        self.assertFalse(is_m2_5_surface_touched(changed))
        errors = evaluate_milestone_scope(changed, self.policy)
        self.assertEqual(errors, [])

    def test_m2_5_surface_plus_candidate_text_blocks(self) -> None:
        changed = [
            "data/coverage/pipeline/brazil/candidate_claims.json",
            "data/coverage/pipeline/brazil/human_claim_review.json",
        ]
        self.assertTrue(is_m2_5_surface_touched(changed))
        base = {
            "schema_version": "1.0.0",
            "country_slug": "brazil",
            "candidates": [
                {"candidate_id": "CC-BR-FX-001", "candidate_text": "original", "support_status": "unreviewed"}
            ],
        }
        head = json.loads(json.dumps(base))
        head["candidates"][0]["candidate_text"] = "corrected in same PR as M2.5"
        field_errors = candidate_field_violations(base, head, self.allowed_fields)
        errors = evaluate_milestone_scope(
            changed, self.policy, candidate_violations=field_errors
        )
        self.assertTrue(any("candidate_text" in e for e in errors))

    def test_special_review_required_cannot_be_cleared(self) -> None:
        base = {
            "schema_version": "1.0.0",
            "country_slug": "brazil",
            "candidates": [
                {
                    "candidate_id": "CC-BR-CUST-002",
                    "candidate_text": "text",
                    "special_review_required": True,
                    "support_status": "unreviewed",
                    "human_review": {"status": "pending"},
                }
            ],
        }
        head = json.loads(json.dumps(base))
        head["candidates"][0]["special_review_required"] = False
        errors = candidate_field_violations(base, head, self.allowed_fields)
        self.assertTrue(any("special_review_required" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
