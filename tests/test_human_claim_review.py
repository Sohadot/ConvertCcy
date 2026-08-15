#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic M2.5 infrastructure tests. No Brazil human semantic close."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from validate_human_claim_review import (  # noqa: E402
    fingerprint_for_review,
    review_human_claim_review,
    write_report,
)

BRAZIL = REPO / "data" / "coverage" / "pipeline" / "brazil"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _copy_brazil(tmp: Path) -> Path:
    dest = tmp / "brazil"
    shutil.copytree(BRAZIL, dest)
    return dest


def _close_needs_evidence(candidate: dict, review: dict) -> None:
    review["exception_preserved"] = candidate["exception_handling"].get("exception_preserved")
    review["authority_preservation_status"] = candidate["authority_posture"].get(
        "authority_preservation_status"
    )
    fp = fingerprint_for_review(candidate, None)
    review.update(
        {
            "status": "closed",
            "decision": "needs_evidence",
            "reviewer": "fixture-operator",
            "reviewed_at": "2026-08-15",
            "reviewed_text": None,
            "reviewed_candidate_fingerprint": fp,
            "semantic_review_status": "closed",
            "rationale": "fixture: closed without accepting the candidate",
            "downstream_eligible": False,
            "adoption_gate_conditions_met": False,
            "adoption_eligible": False,
            "exception_review_status": "closed",
        }
    )
    candidate["support_status"] = "needs_evidence"
    candidate["semantic_review_status"] = "closed"
    candidate["reviewed_text"] = None
    candidate["adoption_gate_conditions_met"] = False
    candidate["adoption_eligible"] = False
    candidate["downstream_eligible"] = False
    candidate["exception_handling"]["exception_review_status"] = "closed"
    candidate["human_review"] = {
        "status": "closed",
        "reviewed_by": "fixture-operator",
        "reviewed_at": "2026-08-15",
        "decision": "needs_evidence",
        "reviewed_candidate_fingerprint": fp,
        "notes": "fixture",
    }


def _close_accepted(
    candidate: dict,
    review: dict,
    *,
    decision: str,
    reviewed_text=None,
    special_addressed: bool = False,
) -> None:
    if reviewed_text is not None:
        candidate["reviewed_text"] = reviewed_text
        review["reviewed_text"] = reviewed_text
    else:
        candidate["reviewed_text"] = None
        review["reviewed_text"] = None
    candidate["authority_posture"]["authority_preservation_status"] = "human_confirmed"
    review["authority_preservation_status"] = "human_confirmed"
    candidate["exception_handling"]["exception_review_status"] = "closed"
    review["exception_review_status"] = "closed"
    preserved = candidate["exception_handling"].get("exception_preserved")
    review["exception_preserved"] = preserved
    if special_addressed:
        review["special_review_addressed"] = True
    fp = fingerprint_for_review(candidate, review.get("reviewed_text"))
    review.update(
        {
            "status": "closed",
            "decision": decision,
            "reviewer": "fixture-operator",
            "reviewed_at": "2026-08-15",
            "reviewed_candidate_fingerprint": fp,
            "semantic_review_status": "closed",
            "rationale": f"fixture:{decision}",
            "downstream_eligible": True,
            "adoption_gate_conditions_met": True,
            "adoption_eligible": True,
        }
    )
    candidate["support_status"] = decision
    candidate["semantic_review_status"] = "closed"
    candidate["downstream_eligible"] = True
    candidate["adoption_gate_conditions_met"] = True
    candidate["adoption_eligible"] = True
    candidate["human_review"] = {
        "status": "closed",
        "reviewed_by": "fixture-operator",
        "reviewed_at": "2026-08-15",
        "decision": decision,
        "reviewed_candidate_fingerprint": fp,
        "notes": f"fixture:{decision}",
    }


class HumanClaimReviewInfrastructureTests(unittest.TestCase):
    def test_brazil_pending_is_infrastructure_pass_not_milestone(self) -> None:
        result, report = review_human_claim_review("brazil")
        self.assertEqual(report["infrastructure_decision"], "PASS")
        self.assertEqual(report["review_completion"], "PENDING")
        self.assertEqual(report["milestone_decision"], "PENDING")
        self.assertEqual(report["semantic_approval"], "not_established")
        self.assertEqual(report["adoption_status"], "not_adopted")
        self.assertEqual(report["stats"]["claims_adopted"], 0)
        self.assertEqual(report["review_coverage"]["required"], 5)
        self.assertEqual(report["review_coverage"]["recorded"], 5)
        self.assertEqual(report["review_coverage"]["closed"], 0)
        self.assertEqual(report["review_coverage"]["missing_candidate_ids"], [])
        self.assertTrue(report["vocabulary_boundary"]["supported_is_not_verified"])
        self.assertNotIn("verified", json.dumps(report["stats"]))
        self.assertEqual(result.infrastructure_decision, "PASS")

    def test_missing_review_blocks_completion_not_infrastructure(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            pack = _copy_brazil(Path(raw))
            ledger = _load(pack / "human_claim_review.json")
            ledger["reviews"] = ledger["reviews"][:-1]
            _save(pack / "human_claim_review.json", ledger)
            result, report = review_human_claim_review("brazil", pack_dir=pack)
            self.assertEqual(report["infrastructure_decision"], "PASS")
            self.assertEqual(report["review_completion"], "BLOCK")
            self.assertEqual(report["milestone_decision"], "BLOCK")
            self.assertEqual(report["review_coverage"]["missing_candidate_ids"], ["CC-BR-CUST-002"])
            self.assertTrue(any(f.layer == "coverage" for f in result.blocking))

    def test_stale_fingerprint_blocks_and_does_not_mutate(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            pack = _copy_brazil(Path(raw))
            candidates = _load(pack / "candidate_claims.json")
            ledger = _load(pack / "human_claim_review.json")
            cand = candidates["candidates"][0]
            review = ledger["reviews"][0]
            _close_needs_evidence(cand, review)
            review["reviewed_candidate_fingerprint"] = "sha256:stale"
            cand["human_review"]["reviewed_candidate_fingerprint"] = "sha256:stale"
            _save(pack / "candidate_claims.json", candidates)
            _save(pack / "human_claim_review.json", ledger)
            before_c = hashlib.sha256((pack / "candidate_claims.json").read_bytes()).hexdigest()
            before_l = hashlib.sha256((pack / "human_claim_review.json").read_bytes()).hexdigest()
            result, report = review_human_claim_review("brazil", pack_dir=pack)
            after_c = hashlib.sha256((pack / "candidate_claims.json").read_bytes()).hexdigest()
            after_l = hashlib.sha256((pack / "human_claim_review.json").read_bytes()).hexdigest()
            self.assertEqual(before_c, after_c)
            self.assertEqual(before_l, after_l)
            self.assertEqual(report["infrastructure_decision"], "BLOCK")
            self.assertTrue(any(f.layer == "fingerprint" for f in result.blocking))

    def test_vocabulary_verified_is_not_supported(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            pack = _copy_brazil(Path(raw))
            candidates = _load(pack / "candidate_claims.json")
            ledger = _load(pack / "human_claim_review.json")
            cand = candidates["candidates"][0]
            review = ledger["reviews"][0]
            _close_needs_evidence(cand, review)
            review["decision"] = "verified"
            cand["support_status"] = "verified"
            cand["human_review"]["decision"] = "verified"
            _save(pack / "candidate_claims.json", candidates)
            _save(pack / "human_claim_review.json", ledger)
            result, report = review_human_claim_review("brazil", pack_dir=pack)
            self.assertEqual(report["infrastructure_decision"], "BLOCK")
            vocab = [f for f in result.blocking if f.layer == "vocabulary"]
            self.assertTrue(vocab)
            self.assertTrue(any("verified" in f.reason for f in vocab))

    def test_vocabulary_verification_target_is_not_needs_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            pack = _copy_brazil(Path(raw))
            candidates = _load(pack / "candidate_claims.json")
            ledger = _load(pack / "human_claim_review.json")
            cand = candidates["candidates"][0]
            review = ledger["reviews"][0]
            _close_needs_evidence(cand, review)
            review["decision"] = "verification_target"
            cand["support_status"] = "verification_target"
            cand["human_review"]["decision"] = "verification_target"
            _save(pack / "candidate_claims.json", candidates)
            _save(pack / "human_claim_review.json", ledger)
            result, report = review_human_claim_review("brazil", pack_dir=pack)
            self.assertEqual(report["infrastructure_decision"], "BLOCK")
            self.assertTrue(any("verification_target" in f.reason for f in result.blocking))

    def test_five_closed_needs_evidence_is_milestone_pass_not_adoption(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            pack = _copy_brazil(Path(raw))
            candidates = _load(pack / "candidate_claims.json")
            ledger = _load(pack / "human_claim_review.json")
            by_id = {c["candidate_id"]: c for c in candidates["candidates"]}
            for review in ledger["reviews"]:
                _close_needs_evidence(by_id[review["candidate_id"]], review)
            _save(pack / "candidate_claims.json", candidates)
            _save(pack / "human_claim_review.json", ledger)
            result, report = review_human_claim_review("brazil", pack_dir=pack)
            self.assertEqual(report["infrastructure_decision"], "PASS", result.blocking)
            self.assertEqual(report["review_completion"], "COMPLETE")
            self.assertEqual(report["milestone_decision"], "PASS")
            self.assertEqual(report["semantic_approval"], "human_review_closed")
            self.assertEqual(report["stats"]["needs_evidence"], 5)
            self.assertEqual(report["stats"]["supported"], 0)
            self.assertEqual(report["stats"]["claims_adopted"], 0)
            self.assertEqual(report["adoption_status"], "not_adopted")
            claims_path = pack / "claims.json"
            before = hashlib.sha256(claims_path.read_bytes()).hexdigest()
            write_report("brazil", report, pack_dir=pack)
            after = hashlib.sha256(claims_path.read_bytes()).hexdigest()
            self.assertEqual(before, after)
            self.assertTrue((pack / "claim_review_report.json").exists())

    def test_forbidden_writes_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            pack = _copy_brazil(Path(raw))
            paths = [
                pack / "claims.json",
                pack / "field_bindings.json",
            ]
            hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
            review_human_claim_review("brazil", pack_dir=pack)
            for p, digest in hashes.items():
                self.assertEqual(digest, hashlib.sha256(p.read_bytes()).hexdigest(), p.name)

    def test_partial_close_is_partially_reviewed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            pack = _copy_brazil(Path(raw))
            candidates = _load(pack / "candidate_claims.json")
            ledger = _load(pack / "human_claim_review.json")
            _close_needs_evidence(candidates["candidates"][0], ledger["reviews"][0])
            _save(pack / "candidate_claims.json", candidates)
            _save(pack / "human_claim_review.json", ledger)
            _, report = review_human_claim_review("brazil", pack_dir=pack)
            self.assertEqual(report["infrastructure_decision"], "PASS")
            self.assertEqual(report["review_completion"], "PENDING")
            self.assertEqual(report["milestone_decision"], "PENDING")
            self.assertEqual(report["semantic_approval"], "partially_reviewed")
            self.assertEqual(report["review_coverage"]["closed"], 1)

    def test_superseding_review_keeps_five_active_not_six(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            pack = _copy_brazil(Path(raw))
            candidates = _load(pack / "candidate_claims.json")
            ledger = _load(pack / "human_claim_review.json")
            by_id = {c["candidate_id"]: c for c in candidates["candidates"]}
            for review in ledger["reviews"]:
                _close_needs_evidence(by_id[review["candidate_id"]], review)
            historical = dict(ledger["reviews"][0])
            successor = dict(historical)
            successor["review_id"] = "HCR-BR-001-SUPERSEDE"
            successor["invalidates_prior_review"] = True
            _close_accepted(by_id["CC-BR-FX-001"], successor, decision="supported")
            ledger["reviews"].append(successor)
            _save(pack / "candidate_claims.json", candidates)
            _save(pack / "human_claim_review.json", ledger)
            result, report = review_human_claim_review("brazil", pack_dir=pack)
            self.assertEqual(report["infrastructure_decision"], "PASS", result.blocking)
            self.assertEqual(report["review_completion"], "COMPLETE")
            self.assertEqual(report["milestone_decision"], "PASS")
            self.assertEqual(report["review_coverage"]["closed"], 5)
            self.assertEqual(report["review_coverage"]["historical_reviews"], 1)
            self.assertEqual(report["stats"]["needs_evidence"], 4)
            self.assertEqual(report["stats"]["supported"], 1)
            self.assertEqual(len(ledger["reviews"]), 6)
            self.assertEqual(by_id["CC-BR-FX-001"]["support_status"], "supported")
            self.assertEqual(historical["decision"], "needs_evidence")

    def test_authority_mismatch_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            pack = _copy_brazil(Path(raw))
            candidates = _load(pack / "candidate_claims.json")
            ledger = _load(pack / "human_claim_review.json")
            _close_needs_evidence(candidates["candidates"][0], ledger["reviews"][0])
            ledger["reviews"][0]["authority_preservation_status"] = "human_confirmed"
            _save(pack / "candidate_claims.json", candidates)
            _save(pack / "human_claim_review.json", ledger)
            result, report = review_human_claim_review("brazil", pack_dir=pack)
            self.assertEqual(report["infrastructure_decision"], "BLOCK")
            self.assertTrue(
                any("authority_preservation_status" in f.reason for f in result.blocking)
            )

    def test_exception_mismatch_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            pack = _copy_brazil(Path(raw))
            candidates = _load(pack / "candidate_claims.json")
            ledger = _load(pack / "human_claim_review.json")
            _close_needs_evidence(candidates["candidates"][0], ledger["reviews"][0])
            candidates["candidates"][0]["exception_handling"]["exception_review_status"] = "pending"
            _save(pack / "candidate_claims.json", candidates)
            _save(pack / "human_claim_review.json", ledger)
            result, report = review_human_claim_review("brazil", pack_dir=pack)
            self.assertEqual(report["infrastructure_decision"], "BLOCK")
            self.assertTrue(any("exception_review_status" in f.reason for f in result.blocking))

    def test_supported_path_meets_adoption_conditions(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            pack = _copy_brazil(Path(raw))
            candidates = _load(pack / "candidate_claims.json")
            ledger = _load(pack / "human_claim_review.json")
            by_id = {c["candidate_id"]: c for c in candidates["candidates"]}
            for review in ledger["reviews"]:
                cid = review["candidate_id"]
                if cid == "CC-BR-FX-002":
                    _close_accepted(by_id[cid], review, decision="supported")
                else:
                    _close_needs_evidence(by_id[cid], review)
            _save(pack / "candidate_claims.json", candidates)
            _save(pack / "human_claim_review.json", ledger)
            result, report = review_human_claim_review("brazil", pack_dir=pack)
            self.assertEqual(report["infrastructure_decision"], "PASS", result.blocking)
            self.assertEqual(report["milestone_decision"], "PASS")
            self.assertEqual(report["stats"]["supported"], 1)
            self.assertEqual(report["stats"]["needs_evidence"], 4)
            self.assertEqual(report["stats"]["adoption_gate_conditions_met"], 1)
            self.assertEqual(report["stats"]["adoption_eligible"], 1)
            self.assertEqual(report["stats"]["downstream_eligible"], 1)
            self.assertEqual(report["adoption_status"], "not_adopted")
            self.assertEqual(report["stats"]["claims_adopted"], 0)

    def test_bounded_path_requires_reviewed_text(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            pack = _copy_brazil(Path(raw))
            candidates = _load(pack / "candidate_claims.json")
            ledger = _load(pack / "human_claim_review.json")
            by_id = {c["candidate_id"]: c for c in candidates["candidates"]}
            narrowed = "Viajante ao sair do Brasil com mais de US$ 10.000,00 deve apresentar e-DBV."
            for review in ledger["reviews"]:
                cid = review["candidate_id"]
                if cid == "CC-BR-CUST-002":
                    _close_accepted(
                        by_id[cid],
                        review,
                        decision="bounded",
                        reviewed_text=narrowed,
                        special_addressed=True,
                    )
                else:
                    _close_needs_evidence(by_id[cid], review)
            _save(pack / "candidate_claims.json", candidates)
            _save(pack / "human_claim_review.json", ledger)
            result, report = review_human_claim_review("brazil", pack_dir=pack)
            self.assertEqual(report["infrastructure_decision"], "PASS", result.blocking)
            self.assertEqual(report["milestone_decision"], "PASS")
            self.assertEqual(report["stats"]["bounded"], 1)
            self.assertEqual(by_id["CC-BR-CUST-002"]["reviewed_text"], narrowed)
            self.assertEqual(report["stats"]["adoption_eligible"], 1)


if __name__ == "__main__":
    unittest.main()
