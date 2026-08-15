#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_human_claim_review.py — Phase 2 M2.5 human candidate-claim review.

Validates human_claim_review.json against candidate_claims.json and emits
claim_review_report.json. Infrastructure PASS ≠ milestone completion.
The validator never mutates authored review artifacts.

Run:
  python scripts/validate_human_claim_review.py
  python scripts/validate_human_claim_review.py brazil
  python scripts/validate_human_claim_review.py --check-drift
  python scripts/validate_human_claim_review.py --write-report
  python scripts/validate_human_claim_review.py --require-milestone-complete
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import pipeline_schema as ps  # noqa: E402
from validate_claim_extraction import fingerprint_candidate  # noqa: E402

INFRA_BLOCKING_LAYERS = {
    "structural",
    "vocabulary",
    "fingerprint",
    "projection",
    "promotion",
    "eligibility",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_policy() -> dict:
    return load_json(ps.POLICY_PATH)


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def canonical_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def fingerprint_for_review(candidate: dict, reviewed_text: Any) -> str:
    overlay = dict(candidate)
    overlay["reviewed_text"] = reviewed_text
    return fingerprint_candidate(overlay)


@dataclass
class Finding:
    layer: str
    field: str
    reason: str
    required_action: str
    blocking: bool = True

    def as_dict(self) -> dict:
        return {
            "layer": self.layer,
            "field": self.field,
            "reason": self.reason,
            "required_action": self.required_action,
            "blocking": self.blocking,
        }


@dataclass
class ClaimReviewResult:
    slug: str
    findings: List[Finding] = field(default_factory=list)
    needs_human_review: List[str] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)
    coverage: Dict[str, Any] = field(default_factory=dict)
    review_completion: str = "PENDING"
    infrastructure_decision: str = "PASS"

    @property
    def blocking(self) -> List[Finding]:
        return [f for f in self.findings if f.blocking]

    @property
    def improvements(self) -> List[Finding]:
        return [f for f in self.findings if not f.blocking]

    def error(self, layer: str, field: str, reason: str, action: str) -> None:
        self.findings.append(Finding(layer, field, reason, action, True))

    def warn(self, layer: str, field: str, reason: str, action: str) -> None:
        self.findings.append(Finding(layer, field, reason, action, False))


def _uses_forbidden_project_status(value: Any, forbidden: Set[str]) -> bool:
    if isinstance(value, str) and value in forbidden:
        return True
    return False


def compute_adoption_gate_conditions_met(
    candidate: dict,
    review: dict,
    eligibility: Dict[str, bool],
    policy: dict,
) -> bool:
    hcr = policy.get("human_claim_review") or {}
    ce = policy.get("claim_extraction") or {}
    if review.get("status") != "closed":
        return False
    decision = review.get("decision")
    if decision not in {"supported", "bounded"}:
        return False
    if review.get("semantic_review_status") != "closed":
        return False
    if (candidate.get("human_review") or {}).get("status") != "closed":
        return False
    fp = fingerprint_for_review(candidate, review.get("reviewed_text"))
    stored = review.get("reviewed_candidate_fingerprint")
    if not stored or stored != fp:
        return False
    if candidate.get("support_status") not in {"supported", "bounded"}:
        return False
    exception_types = set(ce.get("exception_review_required_claim_types") or [])
    claim_type = candidate.get("claim_type")
    needs_exception = claim_type in exception_types if exception_types else True
    if ce.get("exception_review_required_before_downstream") and needs_exception:
        if review.get("exception_review_status") != "closed":
            return False
        if (candidate.get("exception_handling") or {}).get("exception_review_status") != "closed":
            return False
    aps = review.get("authority_preservation_status")
    if aps != "human_confirmed":
        return False
    if aps == "mismatch" or (candidate.get("authority_posture") or {}).get(
        "authority_preservation_status"
    ) == "mismatch":
        return False
    banned = set(ce.get("banned_transformation_modes") or [])
    mode = (candidate.get("transformation") or {}).get("mode")
    if mode in banned:
        return False
    for link in candidate.get("evidence_links") or []:
        eid = (link or {}).get("excerpt_id")
        if eid and eligibility.get(eid) is not True:
            return False
    if candidate.get("special_review_required") is True:
        if review.get("special_review_addressed") is not True:
            return False
    if decision == "bounded":
        reviewed_text = review.get("reviewed_text")
        if not isinstance(reviewed_text, str) or not reviewed_text.strip():
            return False
        if hcr.get("bounded_requires_reviewed_text") and not reviewed_text.strip():
            return False
    return True


def _active_reviews(reviews: List[dict]) -> Dict[str, dict]:
    """Last non-invalidated review per candidate_id wins; default one active."""
    active: Dict[str, dict] = {}
    for item in reviews:
        if not isinstance(item, dict):
            continue
        cid = item.get("candidate_id")
        if not cid:
            continue
        if item.get("invalidates_prior_review") is True:
            active[cid] = item
            continue
        if cid not in active:
            active[cid] = item
        else:
            # duplicate without explicit supersession — keep first, caller BLOCKs
            pass
    return active


def validate_review_pack(
    slug: str,
    candidates_doc: dict,
    ledger_doc: dict,
    excerpts_doc: dict,
    intake_doc: dict,
    policy: dict,
    result: ClaimReviewResult,
) -> None:
    hcr = policy.get("human_claim_review") or {}
    forbidden_vocab = set(
        hcr.get("forbidden_project_claim_statuses") or ps.FORBIDDEN_PROJECT_CLAIM_STATUSES
    )
    closed_decisions = set(hcr.get("closed_decisions") or ps.CLOSED_REVIEW_DECISIONS)
    brazil_scope = (hcr.get("brazil_review_scope") or {}) if slug == "brazil" else {}
    default_ids = list(brazil_scope.get("candidate_ids") or [])

    missing_top = ps.HUMAN_CLAIM_REVIEW_REQUIRED_KEYS - set(ledger_doc.keys())
    if missing_top:
        result.error(
            "structural",
            "human_claim_review.json",
            f"Missing keys: {sorted(missing_top)}",
            "Complete human_claim_review.json top-level keys",
        )
        result.infrastructure_decision = "BLOCK"
        result.review_completion = "BLOCK"
        return

    if ledger_doc.get("country_slug") != slug:
        result.error(
            "structural",
            "human_claim_review.json",
            f"country_slug mismatch: expected {slug}",
            "Align country_slug",
        )
    if ledger_doc.get("milestone") != "m2.5":
        result.error(
            "structural",
            "human_claim_review.json",
            f"milestone must be m2.5, found {ledger_doc.get('milestone')!r}",
            "Set milestone to m2.5",
        )

    scope = ledger_doc.get("review_scope") or {}
    scoped_ids = list(scope.get("candidate_ids") or [])
    required_n = scope.get("required_reviews")
    if slug == "brazil" and default_ids and scoped_ids != default_ids:
        result.error(
            "coverage",
            "review_scope",
            f"Brazil review_scope.candidate_ids must equal policy brazil_review_scope",
            "Use the ratified five-candidate scope",
        )
    if required_n != len(scoped_ids):
        result.error(
            "coverage",
            "review_scope",
            f"required_reviews ({required_n}) != len(candidate_ids) ({len(scoped_ids)})",
            "Align required_reviews with scoped IDs",
        )

    candidates = {
        c["candidate_id"]: c
        for c in (candidates_doc.get("candidates") or [])
        if isinstance(c, dict) and c.get("candidate_id")
    }
    eligibility = dict(intake_doc.get("excerpt_eligibility") or {})

    reviews_raw = ledger_doc.get("reviews") or []
    if not isinstance(reviews_raw, list):
        result.error("structural", "reviews", "reviews must be a list", "Fix reviews array")
        result.infrastructure_decision = "BLOCK"
        result.review_completion = "BLOCK"
        return

    seen_review_ids: Set[str] = set()
    seen_candidate_ids: Set[str] = set()
    duplicate_candidates: Set[str] = set()
    recorded_ids: List[str] = []
    closed_ids: List[str] = []
    pending_ids: List[str] = []

    stats = {
        "candidates_in_scope": len(scoped_ids),
        "reviews_recorded": 0,
        "reviews_closed": 0,
        "supported": 0,
        "bounded": 0,
        "rejected": 0,
        "needs_evidence": 0,
        "downstream_eligible": 0,
        "adoption_gate_conditions_met": 0,
        "adoption_eligible": 0,
        "claims_adopted": 0,
    }

    for i, review in enumerate(reviews_raw):
        prefix = f"reviews[{i}]"
        if not isinstance(review, dict):
            result.error("structural", prefix, "Review must be an object", "Fix review shape")
            continue
        missing_item = ps.HUMAN_REVIEW_ITEM_REQUIRED_KEYS - set(review.keys())
        if missing_item:
            result.error(
                "structural",
                prefix,
                f"Missing keys: {sorted(missing_item)}",
                "Complete review contract fields",
            )
            continue

        rid = review.get("review_id")
        cid = review.get("candidate_id")
        if rid in seen_review_ids:
            result.error("structural", rid, "Duplicate review_id", "Make review IDs unique")
        seen_review_ids.add(rid)
        if cid in seen_candidate_ids and review.get("invalidates_prior_review") is not True:
            duplicate_candidates.add(cid)
            result.error(
                "structural",
                cid,
                "Duplicate active review for candidate without invalidates_prior_review",
                "Keep one active review per candidate",
            )
        seen_candidate_ids.add(cid)
        recorded_ids.append(cid)
        stats["reviews_recorded"] += 1

        if cid not in candidates:
            result.error(
                "structural",
                cid,
                "Review references unknown candidate_id",
                "Link to candidate_claims.json",
            )
            continue
        candidate = candidates[cid]

        for field_name, value in (
            ("decision", review.get("decision")),
            ("support_status", candidate.get("support_status")),
            ("human_review.decision", (candidate.get("human_review") or {}).get("decision")),
        ):
            if _uses_forbidden_project_status(value, forbidden_vocab):
                result.error(
                    "vocabulary",
                    cid,
                    f"{field_name}={value!r} is a project-claim status, not an M2.5 candidate decision "
                    f"(supported ≠ verified; needs_evidence ≠ verification_target)",
                    "Use M2.5 closed decisions only: supported|bounded|rejected|needs_evidence",
                )

        if candidate.get("adopted") is True:
            result.error(
                "vocabulary",
                cid,
                "adopted=true is forbidden in M2.5",
                "Leave adoption to the later Adoption Gate",
            )

        status = review.get("status")
        if status not in ps.HUMAN_REVIEW_STATUSES:
            result.error("structural", cid, f"Invalid review status {status!r}", "Use pending|closed")
            continue

        if status == "pending":
            pending_ids.append(cid)
            result.needs_human_review.append(f"{cid}:review_pending")
            if review.get("decision") not in (None, "deferred"):
                result.error(
                    "structural",
                    cid,
                    "Pending review must not carry a closed decision",
                    "Set decision null until close, or close the review",
                )
            if review.get("decision") == "deferred" or (
                hcr.get("forbids_open_deferred_in_pilot_scope") and review.get("decision") == "deferred"
            ):
                result.error(
                    "structural",
                    cid,
                    "Open deferred is banned in the Brazil M2.5 pilot",
                    "Close with supported|bounded|rejected|needs_evidence",
                )
            if review.get("semantic_review_status") != "pending":
                result.error(
                    "projection",
                    cid,
                    "Pending review requires semantic_review_status=pending",
                    "Keep semantic review pending until close",
                )

        if status == "closed":
            closed_ids.append(cid)
            decision = review.get("decision")
            if decision not in closed_decisions:
                result.error(
                    "structural",
                    cid,
                    f"Closed decision {decision!r} not allowed",
                    "Use supported|bounded|rejected|needs_evidence",
                )
            if review.get("semantic_review_status") != "closed":
                result.error(
                    "projection",
                    cid,
                    "Closed review requires semantic_review_status=closed",
                    "Close semantic review with the human decision",
                )
            if review.get("candidate_text_snapshot") != candidate.get("candidate_text"):
                result.error(
                    "projection",
                    cid,
                    "candidate_text_snapshot does not match candidate_text",
                    "Do not rewrite candidate_text; refresh snapshot only after human reopen",
                )
            if candidate.get("reviewed_text") != review.get("reviewed_text"):
                result.error(
                    "projection",
                    cid,
                    "reviewed_text mismatch between ledger and candidate",
                    "Project ledger reviewed_text onto the candidate",
                )
            expected_fp = fingerprint_for_review(candidate, review.get("reviewed_text"))
            stored = review.get("reviewed_candidate_fingerprint")
            cand_fp = (candidate.get("human_review") or {}).get("reviewed_candidate_fingerprint")
            if not stored:
                result.error(
                    "fingerprint",
                    cid,
                    "Closed review missing reviewed_candidate_fingerprint",
                    "Bind fingerprint at close time",
                )
            elif stored != expected_fp:
                result.error(
                    "fingerprint",
                    cid,
                    "Stale fingerprint: closed review does not match current candidate bytes",
                    "Human must reopen, reset pending/unreviewed/false, and re-close; validator will not mutate artifacts",
                )
            if cand_fp != stored:
                result.error(
                    "projection",
                    cid,
                    "Candidate human_review fingerprint does not match ledger",
                    "Project ledger fingerprint onto the candidate",
                )
            hr = candidate.get("human_review") or {}
            if hr.get("status") != "closed" or hr.get("decision") != decision:
                result.error(
                    "projection",
                    cid,
                    "Candidate human_review does not project closed ledger decision",
                    "Project status/decision from human_claim_review.json",
                )
            if candidate.get("support_status") != decision:
                result.error(
                    "projection",
                    cid,
                    f"support_status {candidate.get('support_status')!r} != decision {decision!r}",
                    "Project closed decision onto candidate support_status (candidate-local vocabulary)",
                )
            if candidate.get("semantic_review_status") != "closed":
                result.error(
                    "projection",
                    cid,
                    "Closed review requires candidate semantic_review_status=closed",
                    "Project semantic_review_status from the ledger",
                )
            if decision == "bounded":
                rt = review.get("reviewed_text")
                if not isinstance(rt, str) or not rt.strip():
                    result.error(
                        "promotion",
                        cid,
                        "bounded decision requires reviewed_text",
                        "Set narrowed reviewed_text before closing as bounded",
                    )
            if decision in {"rejected", "needs_evidence"}:
                if review.get("downstream_eligible") is True or review.get("adoption_eligible") is True:
                    result.error(
                        "promotion",
                        cid,
                        f"{decision} cannot be downstream_eligible or adoption_eligible",
                        "Keep both flags false for non-accepted closed outcomes",
                    )
            if stats.get(decision) is not None:
                stats[decision] += 1

            computed = compute_adoption_gate_conditions_met(
                candidate, review, eligibility, policy
            )
            ledger_met = review.get("adoption_gate_conditions_met")
            cand_met = candidate.get("adoption_gate_conditions_met")
            if ledger_met is not computed:
                result.error(
                    "promotion",
                    cid,
                    f"adoption_gate_conditions_met ledger={ledger_met!r} computed={computed!r}",
                    "Echo the machine-computed value; humans do not invent it",
                )
            if cand_met is not computed:
                result.error(
                    "projection",
                    cid,
                    "Candidate adoption_gate_conditions_met does not match recomputation",
                    "Project the computed boolean onto the candidate",
                )
            if computed:
                stats["adoption_gate_conditions_met"] += 1
            if review.get("adoption_eligible") is True:
                if not computed:
                    result.error(
                        "promotion",
                        cid,
                        "adoption_eligible true while adoption_gate_conditions_met is false",
                        "Nominate only after conditions are met",
                    )
                else:
                    stats["adoption_eligible"] += 1
            if review.get("downstream_eligible") is True:
                if candidate.get("support_status") not in {"supported", "bounded"}:
                    result.error(
                        "promotion",
                        cid,
                        "downstream_eligible true requires accepted support_status",
                        "Keep downstream_eligible false unless supported or bounded",
                    )
                if stored != expected_fp:
                    result.error(
                        "promotion",
                        cid,
                        "downstream_eligible true with stale fingerprint",
                        "Reopen and re-close before promoting",
                    )
                stats["downstream_eligible"] += 1
            if candidate.get("downstream_eligible") != review.get("downstream_eligible"):
                result.error(
                    "projection",
                    cid,
                    "downstream_eligible mismatch between ledger and candidate",
                    "Project ledger downstream_eligible onto the candidate",
                )
            if candidate.get("adoption_eligible") != review.get("adoption_eligible"):
                result.error(
                    "projection",
                    cid,
                    "adoption_eligible mismatch between ledger and candidate",
                    "Project ledger adoption_eligible onto the candidate",
                )

        else:
            # pending projection
            if candidate.get("adoption_eligible") is True or review.get("adoption_eligible") is True:
                result.error(
                    "promotion",
                    cid,
                    "Pending review cannot be adoption_eligible",
                    "Keep adoption_eligible false until closed conditions + human mark",
                )
            computed = False
            if review.get("adoption_gate_conditions_met") is not False:
                result.error(
                    "promotion",
                    cid,
                    "Pending review adoption_gate_conditions_met must be false",
                    "Leave computed flag false until close",
                )
            if candidate.get("adoption_gate_conditions_met") is not False:
                result.error(
                    "projection",
                    cid,
                    "Pending candidate adoption_gate_conditions_met must be false",
                    "Default the computed flag to false",
                )
            if review.get("candidate_text_snapshot") not in (
                None,
                candidate.get("candidate_text"),
            ):
                result.error(
                    "projection",
                    cid,
                    "Pending candidate_text_snapshot must match candidate_text when set",
                    "Copy candidate_text into the snapshot",
                )

        missing_cand_fields = {"adoption_eligible", "adoption_gate_conditions_met"} - set(
            candidate.keys()
        )
        if missing_cand_fields:
            result.error(
                "structural",
                cid,
                f"Candidate missing M2.5 fields: {sorted(missing_cand_fields)}",
                "Add adoption_gate_conditions_met and adoption_eligible (default false)",
            )

    missing_ids = [cid for cid in scoped_ids if cid not in seen_candidate_ids]
    extra_ids = [cid for cid in recorded_ids if cid not in scoped_ids]
    result.coverage = {
        "required": len(scoped_ids),
        "recorded": len(set(recorded_ids) & set(scoped_ids)),
        "closed": len([c for c in closed_ids if c in scoped_ids]),
        "missing_candidate_ids": missing_ids,
    }
    stats["reviews_closed"] = result.coverage["closed"]
    result.stats = stats

    if extra_ids:
        result.warn(
            "coverage",
            "reviews",
            f"Reviews outside declared scope: {extra_ids}",
            "Keep reviews inside review_scope",
        )
    if missing_ids:
        result.error(
            "coverage",
            "review_scope",
            f"Missing review row for scoped candidates: {missing_ids}",
            "Add one review row per scoped candidate_id",
        )
        result.review_completion = "BLOCK"
    elif any(cid in pending_ids for cid in scoped_ids) or result.coverage["closed"] < len(
        scoped_ids
    ):
        result.review_completion = "PENDING"
    elif result.coverage["closed"] == len(scoped_ids) and not missing_ids:
        result.review_completion = "COMPLETE"
    else:
        result.review_completion = "PENDING"

    infra_blocks = [f for f in result.blocking if f.layer in INFRA_BLOCKING_LAYERS]
    if infra_blocks:
        result.infrastructure_decision = "BLOCK"
    else:
        result.infrastructure_decision = "PASS"

    if result.infrastructure_decision == "BLOCK" and result.review_completion == "COMPLETE":
        # stale/projection errors prevent completion
        result.review_completion = "BLOCK"


def semantic_approval_for(coverage: dict) -> str:
    closed = int(coverage.get("closed") or 0)
    required = int(coverage.get("required") or 0)
    if closed <= 0:
        return "not_established"
    if required and closed >= required:
        return "human_review_closed"
    return "partially_reviewed"


def milestone_decision_for(infra: str, completion: str) -> str:
    if infra == "BLOCK" or completion == "BLOCK":
        return "BLOCK"
    if infra == "PASS" and completion == "COMPLETE":
        return "PASS"
    return "PENDING"


def build_report(result: ClaimReviewResult, policy: dict) -> dict:
    hcr = policy.get("human_claim_review") or {}
    milestone = milestone_decision_for(result.infrastructure_decision, result.review_completion)
    approval = semantic_approval_for(result.coverage)
    review: List[str] = []
    seen: Set[str] = set()
    for item in result.needs_human_review:
        if item not in seen:
            seen.add(item)
            review.append(item)
    if result.infrastructure_decision == "PASS" and result.review_completion == "PENDING":
        summary = "INFRASTRUCTURE PASS; REVIEW COMPLETION PENDING (not milestone-complete)"
    elif milestone == "PASS":
        summary = "CLAIM REVIEW PASS (classification only; not adopted)"
    elif result.infrastructure_decision == "BLOCK":
        summary = f"INFRASTRUCTURE BLOCK ({len(result.blocking)} finding(s))"
    else:
        summary = f"REVIEW COMPLETION {result.review_completion}; milestone {milestone}"
    return {
        "schema_version": ps.PIPELINE_SCHEMA_VERSION,
        "country_slug": result.slug,
        "infrastructure_decision": result.infrastructure_decision,
        "review_completion": result.review_completion,
        "milestone_decision": milestone,
        "adoption_status": "not_adopted",
        "semantic_approval": approval,
        "review_coverage": result.coverage,
        "blocking_findings": [f.as_dict() for f in result.blocking],
        "improvement_findings": [f.as_dict() for f in result.improvements],
        "needs_human_review": review,
        "stats": result.stats,
        "summary": summary,
        "capability_note": (
            "M2.5 separates infrastructure validation from human review completion. "
            "Milestone PASS requires full closed coverage. It does not write claims.json, "
            "does not map supported to verified, and does not prove publishability."
        ),
        "vocabulary_boundary": {
            "supported_is_not_verified": True,
            "needs_evidence_is_not_verification_target": True,
            "bounded_is_candidate_wording_narrowing": True,
            "no_projection_into_claims_json": True,
        },
        "claims_adopted": 0,
        "forbids_claims_adoption": bool(hcr.get("forbids_claims_adoption", True)),
    }


def review_human_claim_review(
    slug: str,
    pack_dir: Optional[Path] = None,
) -> Tuple[ClaimReviewResult, dict]:
    policy = load_policy()
    result = ClaimReviewResult(slug=slug)

    def _path(kind: str) -> Path:
        if pack_dir is not None:
            return pack_dir / ps.PACK_FILENAMES[kind]
        return ps.pack_path(slug, kind)

    ledger_path = _path("human_claim_review")
    candidates_path = _path("candidate_claims")
    excerpts_path = _path("evidence_excerpts")
    intake_path = _path("intake_report")

    if not ledger_path.exists():
        result.error(
            "structural",
            "human_claim_review.json",
            "Missing human_claim_review.json",
            "Create M2.5 review ledger",
        )
        result.infrastructure_decision = "BLOCK"
        result.review_completion = "BLOCK"
        return result, build_report(result, policy)
    if not candidates_path.exists():
        result.error(
            "structural",
            "candidate_claims.json",
            "Missing candidate_claims.json (M2 required)",
            "Complete M2.0 before M2.5",
        )
        result.infrastructure_decision = "BLOCK"
        result.review_completion = "BLOCK"
        return result, build_report(result, policy)

    candidates_doc = load_json(candidates_path)
    ledger_doc = load_json(ledger_path)
    excerpts_doc = load_json(excerpts_path) if excerpts_path.exists() else {"excerpts": []}
    intake_doc = load_json(intake_path) if intake_path.exists() else {}

    validate_review_pack(
        slug, candidates_doc, ledger_doc, excerpts_doc, intake_doc, policy, result
    )
    return result, build_report(result, policy)


def write_report(slug: str, report: dict, pack_dir: Optional[Path] = None) -> Path:
    out = (pack_dir / ps.PACK_FILENAMES["claim_review_report"]) if pack_dir else ps.pack_path(
        slug, "claim_review_report"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    save_json(out, report)
    return out


def check_drift(slug: str, report: dict, pack_dir: Optional[Path] = None) -> Optional[str]:
    path = (pack_dir / ps.PACK_FILENAMES["claim_review_report"]) if pack_dir else ps.pack_path(
        slug, "claim_review_report"
    )
    if not path.exists():
        return f"{slug}: committed claim_review_report.json missing"
    committed = load_json(path)
    if canonical_json(committed) != canonical_json(report):
        return f"{slug}: claim_review_report.json drift — regenerate with --write-report"
    return None


def print_result(result: ClaimReviewResult, report: dict, report_path: Optional[Path] = None) -> None:
    print(f"\nCLAIM REVIEW: {result.slug}")
    print(f"INFRASTRUCTURE: {report.get('infrastructure_decision')}")
    print(f"REVIEW_COMPLETION: {report.get('review_completion')}")
    print(f"MILESTONE: {report.get('milestone_decision')}")
    print(f"SEMANTIC_APPROVAL: {report.get('semantic_approval')}")
    print(f"COVERAGE: {report.get('review_coverage')}")
    print(f"STATS: {result.stats}")
    if result.blocking:
        print(f"BLOCKING ({len(result.blocking)}):")
        for f in result.blocking:
            print(f"  [{f.layer}] {f.field}: {f.reason}")
    if result.improvements:
        print(f"IMPROVEMENTS ({len(result.improvements)}):")
        for f in result.improvements[:10]:
            print(f"  [{f.layer}] {f.field}: {f.reason}")
    if result.needs_human_review:
        print(f"NEEDS_HUMAN_REVIEW: {result.needs_human_review}")
    if report_path:
        print(f"REPORT: {report_path}")
    print("NOTE: infrastructure PASS is not M2.5 complete; candidates are not project claims.")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 2 M2.5 human claim review packs")
    parser.add_argument("slugs", nargs="*", help="Country slugs (default: M2.5-opted packs)")
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--check-drift", action="store_true")
    parser.add_argument(
        "--require-milestone-complete",
        action="store_true",
        help="Fail unless milestone_decision is PASS (5/5 closed). Default CI allows PENDING.",
    )
    args = parser.parse_args(argv)

    slugs = args.slugs or ps.list_human_claim_review_slugs()
    if not slugs:
        print("No human-claim-review packs found (need human_claim_review.json).")
        return 0

    policy = load_policy()
    fail_drift = args.check_drift or bool(
        (policy.get("human_claim_review") or {}).get("fail_on_report_drift")
    )
    if args.write_report:
        fail_drift = False

    exit_code = 0
    for slug in slugs:
        result, report = review_human_claim_review(slug)
        report_path = None
        if args.write_report:
            report_path = write_report(slug, report)
        print_result(result, report, report_path)
        if report.get("infrastructure_decision") == "BLOCK":
            exit_code = 1
        if args.require_milestone_complete and report.get("milestone_decision") != "PASS":
            print(
                f"MILESTONE INCOMPLETE: {slug} milestone_decision="
                f"{report.get('milestone_decision')} (infrastructure PASS is not completion)"
            )
            exit_code = 1
        if fail_drift and not args.write_report:
            drift = check_drift(slug, report)
            if drift:
                print(f"DRIFT: {drift}")
                exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
