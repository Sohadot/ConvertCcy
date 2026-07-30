#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_country_pipeline.py — Governed Country Pipeline validator (Phase 1).

Validates pipeline packs under data/coverage/pipeline/{slug}/ against
data/governance/country_pipeline_policy.json and the country rules JSON.

Layers:
  structural — artifact shape + rules schema wrap
  evidence   — bindings only use drafting-allowed claims; primary sources
               for threshold/mandatory/prohibited categories
  fidelity   — draft text must not contain claim forbidden_inferences;
               superseded URLs must not appear in draft source maps
  governance — forbidden claim statuses never bound into draft fields;
               publication readiness checks are informational unless
               --require-publish-ready is set

Countries without a pipeline pack are skipped (Phase 1 opt-in).

Run:
  python scripts/validate_country_pipeline.py
  python scripts/validate_country_pipeline.py brazil
  python scripts/validate_country_pipeline.py --require-publish-ready brazil
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
import rules_schema as rs  # noqa: E402
from validate_rules import validate_file as validate_rules_file  # noqa: E402


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_policy() -> dict:
    return load_json(ps.POLICY_PATH)


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
class ReviewResult:
    slug: str
    findings: List[Finding] = field(default_factory=list)
    needs_human_review: List[str] = field(default_factory=list)

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


def field_text(rules: dict, field_path: str) -> Optional[str]:
    if field_path == "country_overview":
        val = rules.get("country_overview")
        return val if isinstance(val, str) else None
    if field_path.startswith("summary."):
        key = field_path.split(".", 1)[1]
        summary = rules.get("summary") or {}
        val = summary.get(key)
        return val if isinstance(val, str) else None
    if field_path.startswith("rules."):
        key = field_path.split(".", 1)[1]
        rules_obj = rules.get("rules") or {}
        val = rules_obj.get(key)
        return val if isinstance(val, str) else None
    return None


def validate_pack_structure(
    slug: str,
    sources: dict,
    claims: dict,
    bindings: dict,
    result: ReviewResult,
) -> Tuple[Dict[str, dict], Dict[str, dict]]:
    for doc, required, label in [
        (sources, ps.SOURCES_REQUIRED_KEYS, "sources.json"),
        (claims, ps.CLAIMS_REQUIRED_KEYS, "claims.json"),
        (bindings, ps.FIELD_BINDINGS_REQUIRED_KEYS, "field_bindings.json"),
    ]:
        missing = required - set(doc.keys())
        if missing:
            result.error(
                "structural",
                label,
                f"Missing required keys: {sorted(missing)}",
                "Add the missing top-level keys to the pack artifact",
            )
        if doc.get("country_slug") != slug:
            result.error(
                "structural",
                label,
                f"country_slug mismatch: expected '{slug}', got '{doc.get('country_slug')}'",
                "Align country_slug with the pack directory name",
            )

    source_by_id: Dict[str, dict] = {}
    for i, item in enumerate(sources.get("sources") or []):
        prefix = f"sources.json[{i}]"
        if not isinstance(item, dict):
            result.error("structural", prefix, "Source entry must be an object", "Fix source entry shape")
            continue
        missing = ps.SOURCE_ITEM_REQUIRED_KEYS - set(item.keys())
        if missing:
            result.error(
                "structural",
                prefix,
                f"Missing keys: {sorted(missing)}",
                "Complete the source metadata",
            )
            continue
        sid = item["source_id"]
        if sid in source_by_id:
            result.error("structural", prefix, f"Duplicate source_id '{sid}'", "Make source_id unique")
        source_by_id[sid] = item
        if item.get("currency") not in ps.SOURCE_CURRENCY:
            result.error(
                "structural",
                prefix,
                f"Invalid currency '{item.get('currency')}'",
                f"Use one of {sorted(ps.SOURCE_CURRENCY)}",
            )
        if item.get("type") not in rs.VALID_SOURCE_TYPES:
            result.error(
                "structural",
                prefix,
                f"Invalid source type '{item.get('type')}'",
                f"Use a rules_schema VALID_SOURCE_TYPES value",
            )
        if item.get("currency") == "superseded" and not item.get("superseded_by"):
            result.warn(
                "structural",
                prefix,
                "Superseded source lacks superseded_by",
                "Declare the successor source_id",
            )

    claim_by_id: Dict[str, dict] = {}
    for i, item in enumerate(claims.get("claims") or []):
        prefix = f"claims.json[{i}]"
        if not isinstance(item, dict):
            result.error("structural", prefix, "Claim entry must be an object", "Fix claim entry shape")
            continue
        missing = ps.CLAIM_ITEM_REQUIRED_KEYS - set(item.keys())
        if missing:
            result.error(
                "structural",
                prefix,
                f"Missing keys: {sorted(missing)}",
                "Complete the claim metadata",
            )
            continue
        cid = item["claim_id"]
        if cid in claim_by_id:
            result.error("structural", prefix, f"Duplicate claim_id '{cid}'", "Make claim_id unique")
        claim_by_id[cid] = item
        if item.get("status") not in ps.CLAIM_STATUSES:
            result.error(
                "structural",
                prefix,
                f"Invalid status '{item.get('status')}'",
                f"Use one of {sorted(ps.CLAIM_STATUSES)}",
            )
        if item.get("type") not in ps.CLAIM_TYPES:
            result.error(
                "structural",
                prefix,
                f"Invalid type '{item.get('type')}'",
                f"Use one of {sorted(ps.CLAIM_TYPES)}",
            )
        if item.get("evidence_target") not in ps.EVIDENCE_LEVELS:
            result.error(
                "structural",
                prefix,
                f"Invalid evidence_target '{item.get('evidence_target')}'",
                f"Use one of {sorted(ps.EVIDENCE_LEVELS)}",
            )
        for ref in item.get("source_refs") or []:
            if ref not in source_by_id:
                result.error(
                    "structural",
                    cid,
                    f"Unknown source_ref '{ref}'",
                    "Point source_refs at sources.json source_id values",
                )
        if item.get("needs_human_review"):
            result.needs_human_review.append(cid)

    for i, item in enumerate(bindings.get("bindings") or []):
        prefix = f"field_bindings.json[{i}]"
        if not isinstance(item, dict):
            result.error("structural", prefix, "Binding must be an object", "Fix binding shape")
            continue
        missing = ps.BINDING_ITEM_REQUIRED_KEYS - set(item.keys())
        if missing:
            result.error(
                "structural",
                prefix,
                f"Missing keys: {sorted(missing)}",
                "Complete the binding",
            )
            continue
        for cid in item.get("claim_ids") or []:
            if cid not in claim_by_id:
                result.error(
                    "structural",
                    item.get("field", prefix),
                    f"Unknown claim_id '{cid}' in binding",
                    "Bind only to claims present in claims.json",
                )

    return source_by_id, claim_by_id


def validate_evidence_and_governance(
    policy: dict,
    bindings: dict,
    claim_by_id: Dict[str, dict],
    source_by_id: Dict[str, dict],
    result: ReviewResult,
) -> None:
    allowed = set(policy["drafting"]["allowed_claim_statuses"])
    forbidden = set(policy["drafting"]["forbidden_claim_statuses"])
    required_fields = policy["drafting"]["required_binding_fields"]
    primary_types = set(policy["sources"]["primary_source_types"])
    categories_needing_primary = set(policy.get("claim_categories_requiring_primary") or [])

    bound_fields = {b.get("field") for b in bindings.get("bindings") or [] if isinstance(b, dict)}
    if policy["drafting"].get("forbid_unmapped_fields"):
        for field in required_fields:
            if field not in bound_fields:
                result.error(
                    "evidence",
                    field,
                    "Required field has no claim binding",
                    "Add a field_bindings entry with drafting-allowed claim_ids",
                )

    for item in bindings.get("bindings") or []:
        if not isinstance(item, dict):
            continue
        field = item.get("field", "?")
        for cid in item.get("claim_ids") or []:
            claim = claim_by_id.get(cid)
            if not claim:
                continue
            status = claim.get("status")
            if status in forbidden or status not in allowed:
                result.error(
                    "governance",
                    field,
                    f"Binding uses claim '{cid}' with non-draftable status '{status}'",
                    "Remove the claim from field_bindings or change status only after evidence update",
                )
                continue

            category = claim.get("category")
            if category in categories_needing_primary:
                refs = claim.get("source_refs") or []
                has_primary = False
                for ref in refs:
                    src = source_by_id.get(ref)
                    if not src:
                        continue
                    if src.get("tier") == "primary" and src.get("type") in primary_types:
                        if src.get("currency") != "superseded":
                            has_primary = True
                            break
                if not has_primary:
                    result.error(
                        "evidence",
                        field,
                        f"Claim '{cid}' ({category}) lacks a current official primary source",
                        "Attach a current primary source_ref before drafting",
                    )


def _has_local_negation(text: str, start: int, window: int = 48) -> bool:
    """True when a forbidden phrase is locally negated (allowed negative framing)."""
    prefix = text[max(0, start - window) : start].lower()
    negation_markers = (
        "do not ",
        "does not ",
        "did not ",
        "not establish",
        "not established",
        "no support",
        "do not support",
        "without establishing",
        "rather than ",
        "not a ",
        "not an ",
        "never ",
    )
    return any(m in prefix for m in negation_markers)


def _phrase_hits_without_negation(text: str, phrase: str) -> bool:
    lowered = text.lower()
    needle = phrase.lower()
    start = 0
    while True:
        idx = lowered.find(needle, start)
        if idx < 0:
            return False
        if not _has_local_negation(lowered, idx):
            return True
        start = idx + len(needle)


def validate_fidelity(
    policy: dict,
    rules: dict,
    bindings: dict,
    claim_by_id: Dict[str, dict],
    source_by_id: Dict[str, dict],
    result: ReviewResult,
) -> None:
    # Forbidden inferences from bound claims
    for item in bindings.get("bindings") or []:
        if not isinstance(item, dict):
            continue
        field = item.get("field", "?")
        text = field_text(rules, field) or ""
        for cid in item.get("claim_ids") or []:
            claim = claim_by_id.get(cid) or {}
            for phrase in claim.get("forbidden_inferences") or []:
                if phrase and _phrase_hits_without_negation(text, phrase):
                    result.error(
                        "fidelity",
                        field,
                        f"Draft contains forbidden inference from '{cid}': '{phrase}'",
                        f"Remove or rewrite the phrase; claim boundary forbids it",
                    )

    # Non-draftable claims must not leak affirmative forbidden wording into draft fields.
    scan_fields = policy["drafting"]["required_binding_fields"]
    forbidden_statuses = set(policy["drafting"]["forbidden_claim_statuses"])
    for claim in claim_by_id.values():
        if claim.get("status") not in forbidden_statuses:
            continue
        for phrase in claim.get("forbidden_inferences") or []:
            if not phrase:
                continue
            for field in scan_fields:
                text = field_text(rules, field) or ""
                if _phrase_hits_without_negation(text, phrase):
                    result.error(
                        "fidelity",
                        field,
                        f"Draft leaks wording from non-draftable claim '{claim['claim_id']}': '{phrase}'",
                        "Remove the unsupported inference from the draft field",
                    )

    # Superseded URLs must not appear in draft source_map / authorities
    if policy["sources"].get("forbid_superseded_urls_in_draft"):
        superseded_urls = {
            s["url"]
            for s in source_by_id.values()
            if s.get("currency") == "superseded" and s.get("url")
        }
        authorities = rules.get("source_authorities") or []
        for i, auth in enumerate(authorities):
            if isinstance(auth, dict) and auth.get("url") in superseded_urls:
                result.error(
                    "fidelity",
                    f"source_authorities[{i}]",
                    f"Draft cites superseded URL: {auth.get('url')}",
                    "Replace with the successor source declared in sources.json",
                )
        source_map = rules.get("source_map") or {}
        if isinstance(source_map, dict):
            for key, entries in source_map.items():
                if not isinstance(entries, list):
                    continue
                for j, entry in enumerate(entries):
                    if isinstance(entry, dict) and entry.get("url") in superseded_urls:
                        result.error(
                            "fidelity",
                            f"source_map.{key}[{j}]",
                            f"Draft source_map cites superseded URL: {entry.get('url')}",
                            "Replace with the current official source",
                        )


def validate_rules_structural(slug: str, rules_file: Path, result: ReviewResult) -> Optional[dict]:
    if not rules_file.exists():
        result.error(
            "structural",
            "rules",
            f"Missing rules file: {rules_file}",
            "Create data/rules/{slug}.json before pipeline review",
        )
        return None

    try:
        data = load_json(rules_file)
    except json.JSONDecodeError as e:
        result.error("structural", "rules", f"Invalid JSON: {e}", "Fix JSON syntax")
        return None

    vr = validate_rules_file(rules_file)
    for err in vr.errors:
        result.error("structural", "rules", err, "Fix the rules schema/lifecycle violation")
    for warn in vr.warnings:
        result.warn("structural", "rules", warn, "Review the rules warning")

    if data.get("country_slug") != slug:
        result.error(
            "structural",
            "rules.country_slug",
            f"Rules slug '{data.get('country_slug')}' != pack '{slug}'",
            "Align country_slug values",
        )
    return data


def validate_publication_readiness(policy: dict, rules: dict, result: ReviewResult, require: bool) -> None:
    pub = policy["publication"]
    status = rules.get("page_status")
    indexing = rules.get("indexing_allowed")
    tier = rules.get("evidence_tier")

    problems = []
    if status not in set(pub["require_page_status"]):
        problems.append(f"page_status is '{status}', publication requires {pub['require_page_status']}")
    if pub.get("require_indexing_allowed") and indexing is not True:
        problems.append("indexing_allowed must be true for publication")
    allowed_tiers = set(pub.get("require_evidence_tier") or [])
    if allowed_tiers and tier not in allowed_tiers:
        problems.append(f"evidence_tier is '{tier}', publication requires {sorted(allowed_tiers)}")

    for msg in problems:
        if require:
            result.error(
                "governance",
                "publication",
                msg,
                "Do not flip publication flags until all publication gates pass",
            )
        else:
            result.warn(
                "governance",
                "publication",
                msg + " (informational while draft is staging)",
                "Keep needs_hardening / indexing_allowed=false until READY TO PUBLISH",
            )


def review_country(slug: str, require_publish_ready: bool = False) -> ReviewResult:
    policy = load_policy()
    result = ReviewResult(slug=slug)

    sources_path = ps.pack_path(slug, "sources")
    claims_path = ps.pack_path(slug, "claims")
    bindings_path = ps.pack_path(slug, "field_bindings")
    rules_file = ps.rules_path(slug)

    for path in (sources_path, claims_path, bindings_path):
        if not path.exists():
            result.error(
                "structural",
                path.name,
                f"Missing pack file: {path}",
                "Create the pipeline pack artifact",
            )
    if result.blocking:
        return result

    sources = load_json(sources_path)
    claims = load_json(claims_path)
    bindings = load_json(bindings_path)

    source_by_id, claim_by_id = validate_pack_structure(slug, sources, claims, bindings, result)
    rules = validate_rules_structural(slug, rules_file, result)
    if rules is None:
        return result

    validate_evidence_and_governance(policy, bindings, claim_by_id, source_by_id, result)
    validate_fidelity(policy, rules, bindings, claim_by_id, source_by_id, result)
    validate_publication_readiness(policy, rules, result, require=require_publish_ready)

    # Source conflicts from pack
    for conflict in sources.get("source_conflicts") or []:
        result.needs_human_review.append(str(conflict))
        result.warn(
            "governance",
            "sources.source_conflicts",
            f"Source conflict recorded: {conflict}",
            "Resolve via human exception review",
        )

    return result


def write_review_report(slug: str, result: ReviewResult) -> Path:
    layers: Dict[str, List[dict]] = {layer: [] for layer in ps.REVIEW_LAYERS}
    for finding in result.findings:
        layers.setdefault(finding.layer, []).append(finding.as_dict())

    report = {
        "schema_version": ps.PIPELINE_SCHEMA_VERSION,
        "country_slug": slug,
        "decision": result.decision,
        "layers": {
            layer: {
                "blocking_count": sum(1 for f in findings if f.get("blocking", True)),
                "findings": findings,
            }
            for layer, findings in layers.items()
        },
        "blocking_findings": [f.as_dict() for f in result.blocking],
        "improvement_findings": [f.as_dict() for f in result.improvements],
        "needs_human_review": result.needs_human_review,
        "summary": (
            "READY TO PUBLISH"
            if result.decision == "PASS"
            and not any(
                f.field == "publication" and "informational" in f.reason
                for f in result.improvements
            )
            else (
                f"BLOCKED BY {len(result.blocking)} SPECIFIC FINDING(S)"
                if result.decision == "BLOCK"
                else "PASS (staging — publication readiness still informational)"
            )
        ),
    }
    out = ps.pack_path(slug, "review_report")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def print_result(result: ReviewResult, report_path: Optional[Path] = None) -> None:
    print(f"\nCOUNTRY: {result.slug}")
    print(f"DECISION: {result.decision}")
    if result.blocking:
        print(f"BLOCKING ({len(result.blocking)}):")
        for f in result.blocking:
            print(f"  [{f.layer}] {f.field}: {f.reason}")
            print(f"           -> {f.required_action}")
    if result.improvements:
        print(f"IMPROVEMENTS ({len(result.improvements)}):")
        for f in result.improvements:
            print(f"  [{f.layer}] {f.field}: {f.reason}")
    if result.needs_human_review:
        print(f"NEEDS HUMAN REVIEW: {result.needs_human_review}")
    if report_path:
        print(f"REPORT: {report_path}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Governed Country Pipeline packs")
    parser.add_argument("slugs", nargs="*", help="Country slugs (default: all packs)")
    parser.add_argument(
        "--require-publish-ready",
        action="store_true",
        help="Treat publication lifecycle mismatches as blocking",
    )
    parser.add_argument(
        "--write-report",
        action="store_true",
        default=True,
        help="Write review_report.json (default: true)",
    )
    parser.add_argument(
        "--no-write-report",
        action="store_true",
        help="Do not write review_report.json",
    )
    args = parser.parse_args(argv)

    slugs = args.slugs or ps.list_pipeline_slugs()
    if not slugs:
        print("No pipeline packs found under data/coverage/pipeline/")
        return 0

    exit_code = 0
    for slug in slugs:
        result = review_country(slug, require_publish_ready=args.require_publish_ready)
        report_path = None
        if not args.no_write_report:
            report_path = write_review_report(slug, result)
        print_result(result, report_path)
        if result.decision == "BLOCK":
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
