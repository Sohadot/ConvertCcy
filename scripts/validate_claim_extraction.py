#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_claim_extraction.py — Phase 2 Milestone 2 claim-extraction validator.

Validates candidate_claims.json against M1 intake eligibility and generates
claim_extraction_report.json. Structural PASS ≠ semantic approval.

Run:
  python scripts/validate_claim_extraction.py
  python scripts/validate_claim_extraction.py brazil
  python scripts/validate_claim_extraction.py --check-drift
  python scripts/validate_claim_extraction.py --write-report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import pipeline_schema as ps  # noqa: E402


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_policy() -> dict:
    return load_json(ps.POLICY_PATH)


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def canonical_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def fingerprint_candidate(candidate: dict) -> str:
    """Stable fingerprint for closed-review invalidation."""
    payload = {
        "candidate_text": candidate.get("candidate_text"),
        "reviewed_text": candidate.get("reviewed_text"),
        "scope": candidate.get("scope"),
        "evidence_links": candidate.get("evidence_links"),
        "transformation": candidate.get("transformation"),
        "claim_type": candidate.get("claim_type"),
        "claim_language": candidate.get("claim_language"),
        "authority_level": (candidate.get("authority_posture") or {}).get("source_authority_level"),
        "claim_voice": (candidate.get("authority_posture") or {}).get("claim_voice"),
        "exception_handling": {
            "evidence_exception_signal": (candidate.get("exception_handling") or {}).get(
                "evidence_exception_signal"
            ),
            "exception_preserved": (candidate.get("exception_handling") or {}).get(
                "exception_preserved"
            ),
            "exception_excerpt_ids": (candidate.get("exception_handling") or {}).get(
                "exception_excerpt_ids"
            ),
        },
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
class ExtractionResult:
    slug: str
    findings: List[Finding] = field(default_factory=list)
    needs_human_review: List[str] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)

    @property
    def blocking(self) -> List[Finding]:
        return [f for f in self.findings if f.blocking]

    @property
    def improvements(self) -> List[Finding]:
        return [f for f in self.findings if not f.blocking]

    @property
    def decision(self) -> str:
        return "BLOCK" if self.blocking else "PASS"

    def error(self, layer: str, field: str, reason: str, action: str) -> None:
        self.findings.append(Finding(layer, field, reason, action, True))

    def warn(self, layer: str, field: str, reason: str, action: str) -> None:
        self.findings.append(Finding(layer, field, reason, action, False))


def atomicity_heuristic(text: str, markers: List[str]) -> bool:
    """True if text looks compound (heuristic only)."""
    lowered = f" {text.lower()} "
    hits = 0
    for m in markers:
        if m.lower() in lowered:
            hits += 1
    # Portuguese " e " is common inside single clauses; require stronger signal
    if "; " in text or text.count(".") >= 2:
        return True
    if " and " in lowered and (" must " in lowered or " shall " in lowered):
        return True
    if " enquanto " in lowered or " bem como " in lowered:
        return True
    return False


def validate_candidates(
    slug: str,
    candidates_doc: dict,
    excerpts_by_id: Dict[str, dict],
    eligibility: Dict[str, bool],
    policy: dict,
    result: ExtractionResult,
) -> None:
    ce = policy.get("claim_extraction") or {}
    allowed_types = set(ce.get("allowed_claim_types") or [])
    allowed_modes = set(ce.get("allowed_transformation_modes") or [])
    banned_modes = set(ce.get("banned_transformation_modes") or [])
    exception_types = set(ce.get("exception_review_required_claim_types") or [])
    markers = list(ce.get("atomicity_heuristic_markers") or [])

    missing = ps.CANDIDATES_REQUIRED_KEYS - set(candidates_doc.keys())
    if missing:
        result.error(
            "structural",
            "candidate_claims.json",
            f"Missing keys: {sorted(missing)}",
            "Complete candidate_claims.json top-level keys",
        )
        return
    if candidates_doc.get("country_slug") != slug:
        result.error(
            "structural",
            "candidate_claims.json",
            f"country_slug mismatch: expected {slug}",
            "Align country_slug",
        )

    items = candidates_doc.get("candidates") or []
    seen: Set[str] = set()
    used_excerpts: Dict[str, str] = {}

    stats = {
        "candidate_claims_total": 0,
        "direct_restating": 0,
        "translation_based": 0,
        "bounded_normalization": 0,
        "semantic_review_pending": 0,
        "downstream_eligible": 0,
        "human_review_required": 0,
    }

    for i, item in enumerate(items):
        prefix = f"candidates[{i}]"
        if not isinstance(item, dict):
            result.error("structural", prefix, "Candidate must be an object", "Fix shape")
            continue
        missing_item = ps.CANDIDATE_ITEM_REQUIRED_KEYS - set(item.keys())
        if missing_item:
            result.error(
                "structural",
                prefix,
                f"Missing keys: {sorted(missing_item)}",
                "Complete candidate contract fields",
            )
            continue

        cid = item["candidate_id"]
        if cid in seen:
            result.error("structural", cid, "Duplicate candidate_id", "Make IDs unique")
        seen.add(cid)
        stats["candidate_claims_total"] += 1

        text = item.get("candidate_text")
        if not isinstance(text, str) or not text.strip():
            result.error("structural", cid, "candidate_text is empty", "Provide candidate wording")

        claim_type = item.get("claim_type")
        if claim_type not in allowed_types or claim_type not in ps.CANDIDATE_CLAIM_TYPES:
            result.error(
                "structural",
                cid,
                f"claim_type '{claim_type}' not allowed in M2.0",
                "Use an allowed claim_type",
            )

        scope = item.get("scope") or {}
        if not isinstance(scope, dict) or scope.get("jurisdiction") in (None, ""):
            result.error("structural", cid, "scope.jurisdiction required", "Set jurisdiction")
        if scope.get("temporal_scope") not in ps.TEMPORAL_SCOPES:
            result.error(
                "structural",
                cid,
                f"Invalid temporal_scope '{scope.get('temporal_scope')}'",
                "Use temporal_scope enum",
            )

        # Evidence links
        links = item.get("evidence_links") or []
        if not isinstance(links, list) or not links:
            result.error("evidence", cid, "evidence_links empty", "Add at least one direct link")
            continue
        direct_ids: List[str] = []
        for j, link in enumerate(links):
            if not isinstance(link, dict):
                result.error("evidence", f"{cid}.links[{j}]", "Link must be object", "Fix link")
                continue
            eid = link.get("excerpt_id")
            role = link.get("support_role")
            if role not in ps.SUPPORT_ROLES:
                result.error("evidence", cid, f"Invalid support_role '{role}'", "Use support_role enum")
            if eid not in excerpts_by_id:
                result.error("evidence", cid, f"Unknown excerpt_id '{eid}'", "Link to evidence_excerpts")
                continue
            if eligibility.get(eid) is not True:
                result.error(
                    "evidence",
                    cid,
                    f"Excerpt '{eid}' is not M1 downstream-eligible",
                    "Use only eligible excerpts",
                )
            excerpt = excerpts_by_id[eid]
            if ce.get("ban_paraphrase_substrate") and excerpt.get("representation") == "bounded_paraphrase":
                result.error(
                    "evidence",
                    cid,
                    f"Excerpt '{eid}' is bounded_paraphrase substrate (banned)",
                    "Use verbatim_quote or reviewed translation path",
                )
            if role == "direct":
                direct_ids.append(eid)

        if ce.get("require_direct_evidence_link") and not direct_ids:
            result.error(
                "evidence",
                cid,
                "Missing direct evidence link",
                "Add support_role=direct for one eligible excerpt",
            )
        if ce.get("require_exactly_one_direct_excerpt") and len(direct_ids) != 1:
            result.error(
                "evidence",
                cid,
                f"M2.0 requires exactly one direct excerpt, found {len(direct_ids)}",
                "Bind candidate to exactly one direct excerpt",
            )

        if len(direct_ids) == 1:
            eid = direct_ids[0]
            if eid in used_excerpts and used_excerpts[eid] != cid:
                result.warn(
                    "evidence",
                    cid,
                    f"Excerpt '{eid}' also used by {used_excerpts[eid]}",
                    "Prefer one candidate per excerpt in M2.0 pilot",
                )
            used_excerpts[eid] = cid

        # Transformation / language
        tr = item.get("transformation") or {}
        mode = tr.get("mode")
        if mode in banned_modes or mode not in allowed_modes:
            result.error(
                "transformation",
                cid,
                f"transformation.mode '{mode}' banned/not allowed in M2.0",
                "Use direct_restating|faithful_translation|bounded_normalization",
            )
        if mode == "direct_restating":
            stats["direct_restating"] += 1
        elif mode == "faithful_translation":
            stats["translation_based"] += 1
        elif mode == "bounded_normalization":
            stats["bounded_normalization"] += 1

        claim_lang = item.get("claim_language")
        if len(direct_ids) == 1 and mode in allowed_modes:
            excerpt = excerpts_by_id[direct_ids[0]]
            src_lang = excerpt.get("source_language")
            if mode == "direct_restating" and ce.get("direct_restating_requires_same_language"):
                if claim_lang != src_lang:
                    result.error(
                        "transformation",
                        cid,
                        f"direct_restating requires claim_language == source_language "
                        f"({claim_lang!r} != {src_lang!r})",
                        "Use same language or faithful_translation",
                    )
            if mode == "faithful_translation":
                if claim_lang == src_lang:
                    result.error(
                        "transformation",
                        cid,
                        "faithful_translation requires claim_language != source_language",
                        "Use direct_restating for same-language claims",
                    )
                ts = tr.get("translation_source") or {}
                if ce.get("faithful_translation_requires_closed_translation_review"):
                    if ts.get("translation_review_status") != "closed":
                        result.error(
                            "transformation",
                            cid,
                            "faithful_translation requires closed translation_review_status",
                            "Close translation review before using cross-language claims",
                        )
            if isinstance(tr.get("added_terms"), list) and tr.get("added_terms"):
                # Semantic additions are blocked; formal normalizations belong in normalizations[]
                result.error(
                    "transformation",
                    cid,
                    f"Non-empty added_terms not allowed without normalization allowlist: {tr['added_terms']}",
                    "Remove semantic additions or move formal changes to normalizations[]",
                )

        # Authority posture
        ap = item.get("authority_posture") or {}
        aps = ap.get("authority_preservation_status")
        if aps not in ps.AUTHORITY_PRESERVATION_STATUSES:
            result.error(
                "authority",
                cid,
                f"Invalid authority_preservation_status '{aps}'",
                "Use authority_preservation_status enum",
            )
        if aps == "human_confirmed" and (item.get("human_review") or {}).get("status") != "closed":
            result.error(
                "authority",
                cid,
                "human_confirmed authority requires closed human_review",
                "Close human review before confirming authority preservation",
            )
        if aps == "mismatch":
            result.error(
                "authority",
                cid,
                "authority_preservation_status is mismatch",
                "Fix claim voice or mark for human review",
            )

        # Exception handling
        eh = item.get("exception_handling") or {}
        signal = eh.get("evidence_exception_signal")
        if signal not in ps.EXCEPTION_SIGNALS:
            result.error(
                "exception",
                cid,
                f"Invalid evidence_exception_signal '{signal}'",
                "Use unknown|none_detected|present",
            )
        ers = eh.get("exception_review_status")
        if ers not in ps.EXCEPTION_REVIEW_STATUSES:
            result.error(
                "exception",
                cid,
                f"Invalid exception_review_status '{ers}'",
                "Use pending|closed",
            )

        # Origin
        origin = item.get("origin") or {}
        if origin.get("mode") not in ps.ORIGIN_MODES:
            result.error("structural", cid, "Invalid origin.mode", "Use generated|human_authored")

        # Review defaults
        srs = item.get("semantic_review_status")
        if srs not in ps.SEMANTIC_REVIEW_STATUSES:
            result.error("eligibility", cid, "Invalid semantic_review_status", "Use pending|closed")
        if srs == "pending":
            stats["semantic_review_pending"] += 1
            result.needs_human_review.append(f"{cid}:semantic_review_pending")

        if item.get("special_review_required") is True:
            stats["human_review_required"] += 1
            result.needs_human_review.append(f"{cid}:special_review")

        ss = item.get("support_status")
        if ss not in ps.SUPPORT_STATUSES:
            result.error("eligibility", cid, f"Invalid support_status '{ss}'", "Use support_status enum")

        hr = item.get("human_review") or {}
        if hr.get("status") not in ps.HUMAN_REVIEW_STATUSES:
            result.error("eligibility", cid, "Invalid human_review.status", "Use pending|closed")

        # Downstream eligibility gate
        de = item.get("downstream_eligible")
        if de is True:
            stats["downstream_eligible"] += 1
            errors = []
            if hr.get("status") != "closed":
                errors.append("human_review not closed")
            if srs != "closed":
                errors.append("semantic_review not closed")
            if ss not in {"supported", "bounded"}:
                errors.append(f"support_status '{ss}' not accepted")
            if ce.get("exception_review_required_before_downstream"):
                # Listed types always require closed exception review before downstream.
                # If the policy list is empty, require it for every claim type.
                needs_exception_review = (
                    claim_type in exception_types if exception_types else True
                )
                if needs_exception_review and ers != "closed":
                    errors.append("exception_review not closed")
            fp = fingerprint_candidate(item)
            stored = hr.get("reviewed_candidate_fingerprint")
            if not stored:
                errors.append("missing reviewed_candidate_fingerprint")
            elif stored != fp:
                errors.append("fingerprint mismatch — review invalidated by content change")
                result.error(
                    "eligibility",
                    cid,
                    "Closed review fingerprint does not match current candidate",
                    "Re-open review and re-close after content changes",
                )
            if hr.get("decision") not in {"supported", "bounded"} and ss in {"supported", "bounded"}:
                result.warn(
                    "eligibility",
                    cid,
                    "support_status accepted but human_review.decision missing/mismatch",
                    "Align human_review.decision with support_status",
                )
            if errors:
                result.error(
                    "eligibility",
                    cid,
                    "downstream_eligible true but gate failed: " + "; ".join(errors),
                    "Keep downstream_eligible false until all promotion gates pass",
                )
        elif de is not False:
            result.error(
                "eligibility",
                cid,
                "downstream_eligible must be boolean",
                "Set downstream_eligible false by default",
            )

        # Machine must not claim supported without closed review
        if ss in {"supported", "bounded"} and hr.get("status") != "closed":
            result.error(
                "eligibility",
                cid,
                f"support_status '{ss}' requires closed human_review",
                "Only humans may accept candidates after closed review",
            )

        if text and atomicity_heuristic(text, markers):
            result.warn(
                "atomicity",
                cid,
                "Candidate text may be compound (heuristic)",
                "Split into atomic candidates if multiple propositions",
            )

    result.stats = stats


def build_report(result: ExtractionResult, policy: dict) -> dict:
    ce = policy.get("claim_extraction") or {}
    review: List[str] = []
    seen: Set[str] = set()
    for item in result.needs_human_review:
        if item not in seen:
            seen.add(item)
            review.append(item)
    return {
        "schema_version": ps.PIPELINE_SCHEMA_VERSION,
        "country_slug": result.slug,
        "decision": result.decision,
        "semantic_approval": ce.get("semantic_approval_default", "not_established"),
        "blocking_findings": [f.as_dict() for f in result.blocking],
        "improvement_findings": [f.as_dict() for f in result.improvements],
        "needs_human_review": review,
        "stats": result.stats,
        "summary": (
            f"BLOCKED BY {len(result.blocking)} FINDING(S)"
            if result.decision == "BLOCK"
            else "CLAIM EXTRACTION PASS (structural only)"
        ),
        "capability_note": (
            "M2 validator checks extraction contract structure, evidence eligibility, "
            "language/mode consistency, and review/fingerprint gates. It does not establish "
            "legal or semantic approval of candidate claims."
        ),
    }


def review_extraction(slug: str) -> Tuple[ExtractionResult, dict]:
    policy = load_policy()
    result = ExtractionResult(slug=slug)

    candidates_path = ps.pack_path(slug, "candidate_claims")
    excerpts_path = ps.pack_path(slug, "evidence_excerpts")
    intake_path = ps.pack_path(slug, "intake_report")

    if not candidates_path.exists():
        result.error(
            "structural",
            "candidate_claims.json",
            "Missing candidate_claims.json",
            "Create M2 candidate pack",
        )
        return result, build_report(result, policy)
    if not excerpts_path.exists():
        result.error(
            "structural",
            "evidence_excerpts.json",
            "Missing evidence_excerpts.json (M1 required)",
            "Complete M1 before M2",
        )
        return result, build_report(result, policy)
    if not intake_path.exists():
        result.error(
            "structural",
            "intake_report.json",
            "Missing intake_report.json",
            "Generate M1 intake report first",
        )
        return result, build_report(result, policy)

    candidates_doc = load_json(candidates_path)
    excerpts_doc = load_json(excerpts_path)
    intake_doc = load_json(intake_path)

    excerpts_by_id = {
        e["excerpt_id"]: e
        for e in (excerpts_doc.get("excerpts") or [])
        if isinstance(e, dict) and e.get("excerpt_id")
    }
    eligibility = dict(intake_doc.get("excerpt_eligibility") or {})

    validate_candidates(slug, candidates_doc, excerpts_by_id, eligibility, policy, result)
    return result, build_report(result, policy)


def write_report(slug: str, report: dict) -> Path:
    out = ps.pack_path(slug, "claim_extraction_report")
    out.parent.mkdir(parents=True, exist_ok=True)
    save_json(out, report)
    return out


def check_drift(slug: str, report: dict) -> Optional[str]:
    path = ps.pack_path(slug, "claim_extraction_report")
    if not path.exists():
        return f"{slug}: committed claim_extraction_report.json missing"
    committed = load_json(path)
    if canonical_json(committed) != canonical_json(report):
        return f"{slug}: claim_extraction_report.json drift — regenerate with --write-report"
    return None


def print_result(result: ExtractionResult, report_path: Optional[Path] = None) -> None:
    print(f"\nCLAIM EXTRACTION: {result.slug}")
    print(f"DECISION: {result.decision}")
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


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 2 M2 claim extraction packs")
    parser.add_argument("slugs", nargs="*", help="Country slugs (default: M2-opted packs)")
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--check-drift", action="store_true")
    args = parser.parse_args(argv)

    slugs = args.slugs or ps.list_claim_extraction_slugs()
    if not slugs:
        print("No claim-extraction packs found (need candidate_claims.json).")
        return 0

    policy = load_policy()
    fail_drift = args.check_drift or bool(
        (policy.get("claim_extraction") or {}).get("fail_on_report_drift")
    )
    if args.write_report:
        fail_drift = False

    exit_code = 0
    for slug in slugs:
        result, report = review_extraction(slug)
        report_path = None
        if args.write_report:
            report_path = write_report(slug, report)
        print_result(result, report_path)
        if result.decision == "BLOCK":
            exit_code = 1
        if fail_drift and not args.write_report:
            drift = check_drift(slug, report)
            if drift:
                print(f"DRIFT: {drift}")
                exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
