#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_source_intake.py — Phase 2 Milestone 1 intake validator.

Validates authored sources.json + evidence_excerpts.json and generates
intake_report.json. Offline only: validates declared provenance and structural
controls; does NOT independently establish live textual fidelity.

Run:
  python scripts/validate_source_intake.py
  python scripts/validate_source_intake.py brazil
  python scripts/validate_source_intake.py --check-drift
  python scripts/validate_source_intake.py --write-report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import pipeline_schema as ps  # noqa: E402
import rules_schema as rs  # noqa: E402


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_policy() -> dict:
    return load_json(ps.POLICY_PATH)


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def canonical_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def is_https_url(url: Any) -> bool:
    if not isinstance(url, str) or not url.strip():
        return False
    parts = urlsplit(url.strip())
    return parts.scheme.lower() == "https" and bool(parts.netloc)


def parse_iso_date(value: Any) -> Optional[date]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


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
class IntakeResult:
    slug: str
    findings: List[Finding] = field(default_factory=list)
    needs_human_review: List[str] = field(default_factory=list)
    excerpt_eligibility: Dict[str, bool] = field(default_factory=dict)
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

    @property
    def downstream_eligible(self) -> bool:
        if self.decision != "PASS":
            return False
        if self.needs_human_review:
            return False
        return any(self.excerpt_eligibility.values())

    def error(self, layer: str, field: str, reason: str, action: str) -> None:
        self.findings.append(Finding(layer, field, reason, action, True))

    def warn(self, layer: str, field: str, reason: str, action: str) -> None:
        self.findings.append(Finding(layer, field, reason, action, False))


def pinpoint_has_locator(pinpoint: Any) -> bool:
    if not isinstance(pinpoint, dict):
        return False
    for key in ps.PINPOINT_LOCATOR_KEYS:
        val = pinpoint.get(key)
        if val not in (None, "", []):
            return True
    return False


def operator_voice_hit(text: str, patterns: List[str]) -> Optional[str]:
    lowered = text.lower()
    for pat in patterns:
        if pat.lower() in lowered:
            return pat
    return None


def compute_excerpt_downstream_eligible(
    excerpt: dict,
    source: Optional[dict],
    policy: dict,
    review_ids: Set[str],
) -> Tuple[bool, List[str]]:
    """Return (eligible, human_review_reasons)."""
    reasons: List[str] = []
    eid = excerpt.get("excerpt_id", "?")

    if excerpt.get("ambiguous") is True:
        reasons.append(f"{eid}: ambiguous")
    if excerpt.get("claim_neutrality_status") != "reviewed":
        reasons.append(f"{eid}: claim_neutrality_status not reviewed")
    if excerpt.get("representation") == "bounded_paraphrase":
        if policy["intake"].get("bounded_paraphrase_never_downstream_eligible_by_default", True):
            reasons.append(f"{eid}: bounded_paraphrase not downstream-eligible by default")
    if excerpt.get("operator_interpretation") not in (None, "", []):
        reasons.append(f"{eid}: operator_interpretation present")
    if source is None:
        reasons.append(f"{eid}: missing source")
    else:
        if source.get("currency") == "superseded":
            reasons.append(f"{eid}: superseded source never downstream-eligible")
        if policy["intake"].get("official_primary_only") and source.get("tier") != "primary":
            reasons.append(f"{eid}: non-primary source")
    if eid in review_ids or any(r.startswith(f"{eid}:") for r in review_ids):
        # review list may contain bare ids
        pass

    eligible = len(reasons) == 0
    return eligible, reasons


def validate_sources(
    slug: str,
    sources_doc: dict,
    policy: dict,
    result: IntakeResult,
) -> Dict[str, dict]:
    intake = policy.get("intake") or {}
    official_kinds = set(intake.get("official_authority_kinds") or [])
    stale_days = int(intake.get("stale_source_warn_days") or 180)
    today = date.today()

    missing = ps.SOURCES_REQUIRED_KEYS - set(sources_doc.keys())
    if missing:
        result.error(
            "structural",
            "sources.json",
            f"Missing keys: {sorted(missing)}",
            "Complete sources.json top-level keys",
        )
    if sources_doc.get("country_slug") != slug:
        result.error(
            "structural",
            "sources.json",
            f"country_slug mismatch: expected {slug}",
            "Align country_slug with pack directory",
        )

    by_id: Dict[str, dict] = {}
    items = sources_doc.get("sources") or []
    current = 0
    superseded = 0
    for i, item in enumerate(items):
        prefix = f"sources[{i}]"
        if not isinstance(item, dict):
            result.error("structural", prefix, "Source must be an object", "Fix shape")
            continue
        missing_item = ps.SOURCE_ITEM_M1_REQUIRED_KEYS - set(item.keys())
        if missing_item:
            result.error(
                "structural",
                prefix,
                f"Missing M1 keys: {sorted(missing_item)}",
                "Add authority/authority_kind/jurisdiction/accessed_at/content_persistence",
            )
            continue
        sid = item["source_id"]
        if sid in by_id:
            result.error("structural", prefix, f"Duplicate source_id {sid}", "Make IDs unique")
        by_id[sid] = item

        if not is_https_url(item.get("url")):
            result.error("structural", sid, "URL must be HTTPS", "Use an https:// official URL")
        if item.get("type") not in rs.VALID_SOURCE_TYPES:
            result.error("authority", sid, f"Invalid type {item.get('type')}", "Use VALID_SOURCE_TYPES")
        if item.get("currency") not in ps.SOURCE_CURRENCY:
            result.error("currency", sid, f"Invalid currency {item.get('currency')}", "Fix currency enum")
        if item.get("content_persistence") not in ps.CONTENT_PERSISTENCE:
            result.error(
                "provenance",
                sid,
                f"Invalid content_persistence {item.get('content_persistence')}",
                "Use preserved|fingerprinted|not_preserved",
            )
        if not item.get("authority"):
            result.error("authority", sid, "authority is empty", "Set official authority name")
        if item.get("authority_kind") not in official_kinds:
            result.error(
                "authority",
                sid,
                f"authority_kind '{item.get('authority_kind')}' not in official set",
                "Use an official authority_kind from policy.intake",
            )
        if intake.get("official_primary_only") and item.get("tier") != "primary":
            # Allowed only as audit/superseded companions; block if used as current evidence later
            result.warn(
                "authority",
                sid,
                "Non-primary source present in pack",
                "Keep only as audit context; never downstream-eligible",
            )

        if item.get("currency") == "superseded":
            superseded += 1
            succ = item.get("superseded_by")
            if not succ:
                result.error(
                    "currency",
                    sid,
                    "superseded source lacks superseded_by",
                    "Point to successor source_id",
                )
        elif item.get("currency") == "current":
            current += 1

        persistence = item.get("content_persistence")
        if persistence == "fingerprinted" and not item.get("content_fingerprint"):
            result.error(
                "provenance",
                sid,
                "fingerprinted requires content_fingerprint",
                "Add sha256 fingerprint or set not_preserved",
            )
        if persistence == "preserved" and not item.get("retrieved_artifact"):
            result.error(
                "provenance",
                sid,
                "preserved requires retrieved_artifact path",
                "Add local capture path or set not_preserved",
            )
        if persistence == "preserved":
            rel = item.get("retrieved_artifact")
            if isinstance(rel, str) and rel:
                art = REPO / rel
                if not art.exists():
                    result.error(
                        "provenance",
                        sid,
                        f"retrieved_artifact missing on disk: {rel}",
                        "Commit the capture or change content_persistence",
                    )
                elif item.get("content_fingerprint"):
                    digest = "sha256:" + hashlib.sha256(art.read_bytes()).hexdigest()
                    if digest != item["content_fingerprint"]:
                        result.error(
                            "provenance",
                            sid,
                            "content_fingerprint does not match retrieved_artifact bytes",
                            "Recompute fingerprint or refresh capture",
                        )

        accessed = parse_iso_date(item.get("accessed_at"))
        if accessed is None:
            result.error("provenance", sid, "accessed_at must be ISO date", "Set accessed_at")
        else:
            age = (today - accessed).days
            if age > stale_days:
                result.warn(
                    "provenance",
                    sid,
                    f"accessed_at is {age} days old (>{stale_days})",
                    "Re-access source and update accessed_at",
                )
                result.needs_human_review.append(f"{sid}: stale_access")

    # Resolve superseded_by after all IDs known
    for sid, item in by_id.items():
        succ = item.get("superseded_by")
        if item.get("currency") == "superseded" and succ and succ not in by_id:
            result.error(
                "currency",
                sid,
                f"superseded_by '{succ}' not found",
                "Point to an existing source_id",
            )

    for conflict in sources_doc.get("source_conflicts") or []:
        result.needs_human_review.append(f"source_conflict:{conflict}")
        result.warn(
            "eligibility",
            "sources.source_conflicts",
            f"Source conflict recorded: {conflict}",
            "Resolve via human review before downstream use",
        )

    result.stats = {
        "sources_total": len(by_id),
        "sources_current": current,
        "sources_superseded": superseded,
        "excerpts_total": 0,
        "excerpts_downstream_eligible": 0,
    }
    return by_id


def validate_excerpts(
    slug: str,
    excerpts_doc: dict,
    source_by_id: Dict[str, dict],
    policy: dict,
    result: IntakeResult,
) -> None:
    intake = policy.get("intake") or {}
    patterns = list(intake.get("forbidden_operator_voice_patterns") or [])

    missing = ps.EXCERPTS_REQUIRED_KEYS - set(excerpts_doc.keys())
    if missing:
        result.error(
            "structural",
            "evidence_excerpts.json",
            f"Missing keys: {sorted(missing)}",
            "Complete evidence_excerpts.json",
        )
        return
    if excerpts_doc.get("country_slug") != slug:
        result.error(
            "structural",
            "evidence_excerpts.json",
            f"country_slug mismatch: expected {slug}",
            "Align country_slug",
        )

    items = excerpts_doc.get("excerpts") or []
    seen: Set[str] = set()
    eligible_count = 0

    for i, item in enumerate(items):
        prefix = f"excerpts[{i}]"
        if not isinstance(item, dict):
            result.error("structural", prefix, "Excerpt must be an object", "Fix shape")
            continue
        missing_item = ps.EXCERPT_ITEM_REQUIRED_KEYS - set(item.keys())
        if missing_item:
            result.error(
                "structural",
                prefix,
                f"Missing keys: {sorted(missing_item)}",
                "Complete excerpt contract fields",
            )
            continue

        eid = item["excerpt_id"]
        if eid in seen:
            result.error("structural", eid, "Duplicate excerpt_id", "Make IDs unique")
        seen.add(eid)

        sid = item.get("source_id")
        source = source_by_id.get(sid) if isinstance(sid, str) else None
        if source is None:
            result.error(
                "structural",
                eid,
                f"Unknown source_id '{sid}'",
                "Bind excerpt to sources.json",
            )

        rep = item.get("representation")
        if rep not in ps.EXCERPT_REPRESENTATIONS:
            result.error(
                "structural",
                eid,
                f"Invalid representation '{rep}'",
                "Use verbatim_quote|faithful_translation|bounded_paraphrase",
            )

        source_text = item.get("source_text")
        if not isinstance(source_text, str) or not source_text.strip():
            result.error("structural", eid, "source_text is empty", "Provide source-language text")
        else:
            hit = operator_voice_hit(source_text, patterns)
            if hit and rep != "verbatim_quote":
                result.error(
                    "neutrality",
                    eid,
                    f"Operator/lifecycle voice '{hit}' in non-verbatim text",
                    "Remove project voice or use verbatim_quote of official text only",
                )
            elif hit and rep == "verbatim_quote":
                # Allowed only as official quotation; still warn if looks like ConvertCCY jargon
                if hit in {"page_status", "indexing_allowed", "evidence_tier", "downstream_eligible"}:
                    result.error(
                        "neutrality",
                        eid,
                        f"Project lifecycle term '{hit}' must not appear in excerpts",
                        "Remove ConvertCCY lifecycle vocabulary",
                    )

        if not pinpoint_has_locator(item.get("pinpoint")):
            result.error(
                "provenance",
                eid,
                "pinpoint lacks any locator",
                "Set article/section/heading/page/url_fragment/locator_note",
            )

        if item.get("capture_status") not in ps.CAPTURE_STATUSES:
            result.error("provenance", eid, "Invalid capture_status", "Use capture_status enum")
        if item.get("claim_neutrality_status") not in ps.CLAIM_NEUTRALITY_STATUSES:
            result.error(
                "neutrality",
                eid,
                "Invalid claim_neutrality_status",
                "Use unreviewed|reviewed|exception_required",
            )
        for date_key in ("verified_at", "captured_at", "source_accessed_at"):
            if parse_iso_date(item.get(date_key)) is None:
                result.error("provenance", eid, f"{date_key} must be ISO date", f"Fix {date_key}")

        if rep == "faithful_translation":
            if not isinstance(item.get("translation_text"), str) or not item.get("translation_text", "").strip():
                result.error(
                    "structural",
                    eid,
                    "faithful_translation requires translation_text",
                    "Add translation_text while retaining source_text",
                )
            result.needs_human_review.append(f"{eid}: translation_review")
        if rep == "bounded_paraphrase":
            # Paraphrase must not pretend to be the quotation field alone without disclosure
            if item.get("paraphrase_text") in (None, "") and item.get("translation_text") in (None, ""):
                result.error(
                    "structural",
                    eid,
                    "bounded_paraphrase requires paraphrase_text (or translation_text holding paraphrase)",
                    "Store paraphrase separately from source_text quotation",
                )
            result.needs_human_review.append(f"{eid}: paraphrase_not_downstream")

        if item.get("ambiguous") is True:
            result.needs_human_review.append(eid)

        if source and source.get("currency") == "superseded":
            if not item.get("allows_superseded"):
                result.error(
                    "currency",
                    eid,
                    "Excerpt binds superseded source without allows_superseded",
                    "Use a current source or set allows_superseded with human review",
                )
            result.needs_human_review.append(f"{eid}: superseded_source")
        elif (
            intake.get("excerpt_requires_current_source")
            and source
            and source.get("currency") != "current"
        ):
            result.error(
                "currency",
                eid,
                f"Excerpt source currency is '{source.get('currency')}', expected current",
                "Bind to a current official source",
            )

        if item.get("claim_neutrality_status") == "exception_required":
            result.needs_human_review.append(f"{eid}: neutrality_exception")
        if item.get("claim_neutrality_status") == "unreviewed":
            result.needs_human_review.append(f"{eid}: neutrality_unreviewed")

        review_set = set(result.needs_human_review)
        eligible, reasons = compute_excerpt_downstream_eligible(item, source, policy, review_set)
        # Recompute after accumulating review markers for this excerpt
        if any(x == eid or x.startswith(f"{eid}:") for x in result.needs_human_review):
            eligible = False
        if item.get("representation") == "bounded_paraphrase":
            eligible = False
        if source and source.get("currency") == "superseded":
            eligible = False
        if item.get("claim_neutrality_status") != "reviewed":
            eligible = False
        if item.get("ambiguous") is True:
            eligible = False
        if item.get("operator_interpretation") not in (None, "", []):
            eligible = False
            result.needs_human_review.append(f"{eid}: operator_interpretation")

        result.excerpt_eligibility[eid] = eligible
        if eligible:
            eligible_count += 1
        elif reasons:
            for reason in reasons:
                if reason not in result.needs_human_review and eid in reason:
                    result.warn("eligibility", eid, reason, "Close human review before Milestone 2 use")

    result.stats["excerpts_total"] = len(seen)
    result.stats["excerpts_downstream_eligible"] = eligible_count


def build_intake_report(result: IntakeResult) -> dict:
    summary = (
        f"BLOCKED BY {len(result.blocking)} FINDING(S)"
        if result.decision == "BLOCK"
        else (
            "INTAKE PASS"
            if result.downstream_eligible
            else "INTAKE PASS (not downstream-eligible)"
        )
    )
    # Deduplicate human-review ids while preserving order
    seen: Set[str] = set()
    review: List[str] = []
    for item in result.needs_human_review:
        if item not in seen:
            seen.add(item)
            review.append(item)

    return {
        "schema_version": ps.PIPELINE_SCHEMA_VERSION,
        "country_slug": result.slug,
        "decision": result.decision,
        "downstream_eligible": result.downstream_eligible,
        "blocking_findings": [f.as_dict() for f in result.blocking],
        "improvement_findings": [f.as_dict() for f in result.improvements],
        "needs_human_review": review,
        "excerpt_eligibility": result.excerpt_eligibility,
        "stats": result.stats,
        "summary": summary,
        "capability_note": (
            "M1 validator validates declared provenance and structural evidence controls; "
            "it does not independently establish textual fidelity unless a locally preserved "
            "source capture is available."
        ),
    }


def review_intake(slug: str) -> Tuple[IntakeResult, dict]:
    policy = load_policy()
    result = IntakeResult(slug=slug)
    sources_path = ps.pack_path(slug, "sources")
    excerpts_path = ps.pack_path(slug, "evidence_excerpts")

    if not sources_path.exists():
        result.error("structural", "sources.json", "Missing sources.json", "Create authored sources pack")
        return result, build_intake_report(result)
    if not excerpts_path.exists():
        result.error(
            "structural",
            "evidence_excerpts.json",
            "Missing evidence_excerpts.json",
            "Create authored excerpts pack",
        )
        return result, build_intake_report(result)

    sources_doc = load_json(sources_path)
    excerpts_doc = load_json(excerpts_path)
    source_by_id = validate_sources(slug, sources_doc, policy, result)
    validate_excerpts(slug, excerpts_doc, source_by_id, policy, result)
    report = build_intake_report(result)
    return result, report


def write_intake_report(slug: str, report: dict) -> Path:
    out = ps.pack_path(slug, "intake_report")
    out.parent.mkdir(parents=True, exist_ok=True)
    save_json(out, report)
    return out


def check_report_drift(slug: str, report: dict) -> Optional[str]:
    path = ps.pack_path(slug, "intake_report")
    if not path.exists():
        return f"{slug}: committed intake_report.json missing"
    committed = load_json(path)
    if canonical_json(committed) != canonical_json(report):
        return f"{slug}: intake_report.json drift — regenerate with --write-report"
    return None


def print_result(result: IntakeResult, report_path: Optional[Path] = None) -> None:
    print(f"\nINTAKE: {result.slug}")
    print(f"DECISION: {result.decision}")
    print(f"DOWNSTREAM_ELIGIBLE: {result.downstream_eligible}")
    if result.blocking:
        print(f"BLOCKING ({len(result.blocking)}):")
        for f in result.blocking:
            print(f"  [{f.layer}] {f.field}: {f.reason}")
    if result.improvements:
        print(f"IMPROVEMENTS ({len(result.improvements)}):")
        for f in result.improvements[:12]:
            print(f"  [{f.layer}] {f.field}: {f.reason}")
        if len(result.improvements) > 12:
            print(f"  ... {len(result.improvements) - 12} more")
    if result.needs_human_review:
        print(f"NEEDS_HUMAN_REVIEW: {result.needs_human_review}")
    if report_path:
        print(f"REPORT: {report_path}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 2 M1 source intake packs")
    parser.add_argument("slugs", nargs="*", help="Country slugs (default: intake-opted packs)")
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write/overwrite intake_report.json",
    )
    parser.add_argument(
        "--check-drift",
        action="store_true",
        help="Fail if committed intake_report.json drifts from regenerated report",
    )
    args = parser.parse_args(argv)

    slugs = args.slugs or ps.list_intake_slugs()
    if not slugs:
        print("No intake packs found (need sources.json + evidence_excerpts.json).")
        return 0

    policy = load_policy()
    fail_drift = args.check_drift or bool(
        (policy.get("intake") or {}).get("fail_on_intake_report_drift")
    )
    # Default CI mode: check drift without requiring callers to pass the flag when
    # policy says so — but only when not explicitly writing reports.
    if args.write_report:
        fail_drift = False

    exit_code = 0
    for slug in slugs:
        result, report = review_intake(slug)
        report_path = None
        if args.write_report:
            report_path = write_intake_report(slug, report)
        print_result(result, report_path)

        if result.decision == "BLOCK":
            exit_code = 1

        if fail_drift and not args.write_report:
            drift = check_report_drift(slug, report)
            if drift:
                print(f"DRIFT: {drift}")
                exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
