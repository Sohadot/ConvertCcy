#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
country_pipeline.py — Governed Country Pipeline orchestrator.

Commands:
  review <slug>         Phase 1 multi-layer draft review → review_report.json
  fix <slug>            One bounded auto-correct cycle, then re-review
  intake-review <slug>  Phase 2 M1 intake review → intake_report.json

Examples:
  python scripts/country_pipeline.py review brazil
  python scripts/country_pipeline.py fix brazil --apply
  python scripts/country_pipeline.py intake-review brazil
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import pipeline_schema as ps  # noqa: E402
from validate_country_pipeline import (  # noqa: E402
    load_json,
    load_policy,
    print_result,
    review_country,
    write_review_report,
)
from validate_source_intake import (  # noqa: E402
    print_result as print_intake_result,
    review_intake,
    write_intake_report,
)


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def cmd_review(slug: str, require_publish_ready: bool = False) -> int:
    result = review_country(slug, require_publish_ready=require_publish_ready)
    report_path = write_review_report(slug, result)
    print_result(result, report_path)
    return 0 if result.decision == "PASS" else 1


def _replace_superseded_urls(rules: dict, source_by_id: Dict[str, dict]) -> List[str]:
    """Replace superseded URLs in draft with successor URLs when declared."""
    actions: List[str] = []
    url_to_successor: Dict[str, str] = {}
    for src in source_by_id.values():
        if src.get("currency") != "superseded":
            continue
        successor_id = src.get("superseded_by")
        if not successor_id or successor_id not in source_by_id:
            continue
        successor = source_by_id[successor_id]
        if successor.get("url"):
            url_to_successor[src["url"]] = successor["url"]

    if not url_to_successor:
        return actions

    for i, auth in enumerate(rules.get("source_authorities") or []):
        if not isinstance(auth, dict):
            continue
        old = auth.get("url")
        if old in url_to_successor:
            new = url_to_successor[old]
            auth["url"] = new
            # Prefer successor label/type when available
            succ = next(
                (s for s in source_by_id.values() if s.get("url") == new),
                None,
            )
            if succ:
                auth["label"] = succ.get("label", auth.get("label"))
                auth["type"] = succ.get("type", auth.get("type"))
                auth["tier"] = succ.get("tier", auth.get("tier"))
            actions.append(f"source_authorities[{i}]: replaced superseded URL")

    source_map = rules.get("source_map") or {}
    if isinstance(source_map, dict):
        for key, entries in source_map.items():
            if not isinstance(entries, list):
                continue
            for j, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                old = entry.get("url")
                if old in url_to_successor:
                    entry["url"] = url_to_successor[old]
                    actions.append(f"source_map.{key}[{j}]: replaced superseded URL")

    return actions


def _remove_forbidden_bindings(
    bindings: dict,
    claim_by_id: Dict[str, dict],
    policy: dict,
) -> List[str]:
    actions: List[str] = []
    allowed = set(policy["drafting"]["allowed_claim_statuses"])
    forbidden = set(policy["drafting"]["forbidden_claim_statuses"])
    for item in bindings.get("bindings") or []:
        if not isinstance(item, dict):
            continue
        original = list(item.get("claim_ids") or [])
        kept = []
        for cid in original:
            claim = claim_by_id.get(cid) or {}
            status = claim.get("status")
            if status in forbidden or status not in allowed:
                actions.append(
                    f"field_bindings[{item.get('field')}]: removed non-draftable claim {cid} ({status})"
                )
            else:
                kept.append(cid)
        item["claim_ids"] = kept
    return actions


def _strip_forbidden_phrases(rules: dict, claim_by_id: Dict[str, dict], policy: dict) -> List[str]:
    """Remove exact forbidden inference phrases from draft fields when safe."""
    actions: List[str] = []
    fields = policy["drafting"]["required_binding_fields"]

    phrases: List[Tuple[str, str]] = []
    for claim in claim_by_id.values():
        for phrase in claim.get("forbidden_inferences") or []:
            if phrase:
                phrases.append((claim["claim_id"], phrase))

    def scrub(text: str, field: str) -> str:
        updated = text
        for cid, phrase in phrases:
            if phrase.lower() in updated.lower():
                # Case-insensitive replace of the exact phrase
                pattern = re.compile(re.escape(phrase), re.IGNORECASE)
                new_text, n = pattern.subn("", updated)
                if n:
                    # Clean doubled spaces / awkward punctuation left behind
                    new_text = re.sub(r"\s{2,}", " ", new_text)
                    new_text = re.sub(r"\s+,", ",", new_text)
                    new_text = re.sub(r",\s*,", ",", new_text)
                    new_text = re.sub(r"\s+\.", ".", new_text)
                    updated = new_text.strip()
                    actions.append(
                        f"{field}: removed forbidden inference phrase from {cid}: '{phrase}'"
                    )
        return updated

    if "country_overview" in fields and isinstance(rules.get("country_overview"), str):
        rules["country_overview"] = scrub(rules["country_overview"], "country_overview")

    summary = rules.get("summary")
    if isinstance(summary, dict):
        for key in ("traveler", "business"):
            field = f"summary.{key}"
            if field in fields and isinstance(summary.get(key), str):
                summary[key] = scrub(summary[key], field)

    rules_obj = rules.get("rules")
    if isinstance(rules_obj, dict):
        for key, val in list(rules_obj.items()):
            field = f"rules.{key}"
            if field in fields and isinstance(val, str):
                rules_obj[key] = scrub(val, field)

    return actions


def _tighten_soft_modals(rules: dict, claim_by_id: Dict[str, dict], bindings: dict) -> List[str]:
    """
    Limited modal tightening: when a bound claim forbids 'may be required'
    style phrasing and requires 'must' wording, replace known soft patterns.
    """
    actions: List[str] = []
    soft_to_hard = [
        (
            r"supporting proof may be required",
            "the traveller must present the declared cash and the applicable supporting evidence",
        ),
        (
            r"Receita Federal guidance states that supporting proof may be required",
            "The traveller must present the declared cash and the applicable supporting evidence identified by Receita Federal",
        ),
        (
            r"proof may be required",
            "supporting evidence must be presented",
        ),
        (
            r"may require proof",
            "requires presentation of supporting evidence",
        ),
    ]

    fields_needing_must: set[str] = set()
    for item in bindings.get("bindings") or []:
        if not isinstance(item, dict):
            continue
        field = item.get("field")
        for cid in item.get("claim_ids") or []:
            claim = claim_by_id.get(cid) or {}
            forbidden = " ".join(claim.get("forbidden_inferences") or []).lower()
            allowed = " ".join(claim.get("allowed_wording") or []).lower()
            if "may be required" in forbidden or "must present" in allowed or "must be declared" in allowed:
                if field:
                    fields_needing_must.add(field)

    def apply_field(field: str, text: str) -> str:
        if field not in fields_needing_must:
            return text
        updated = text
        for pattern, replacement in soft_to_hard:
            new_text, n = re.subn(pattern, replacement, updated, flags=re.IGNORECASE)
            if n:
                updated = new_text
                actions.append(f"{field}: tightened soft modal matching /{pattern}/")
        return updated

    if isinstance(rules.get("country_overview"), str):
        rules["country_overview"] = apply_field("country_overview", rules["country_overview"])

    summary = rules.get("summary")
    if isinstance(summary, dict):
        for key in ("traveler", "business"):
            field = f"summary.{key}"
            if isinstance(summary.get(key), str):
                summary[key] = apply_field(field, summary[key])

    rules_obj = rules.get("rules")
    if isinstance(rules_obj, dict):
        for key, val in list(rules_obj.items()):
            field = f"rules.{key}"
            if isinstance(val, str):
                rules_obj[key] = apply_field(field, val)

    return actions


def cmd_fix(slug: str, apply: bool) -> int:
    policy = load_policy()
    allowed_actions = set(policy["auto_correct"]["allowed_actions"])

    sources = load_json(ps.pack_path(slug, "sources"))
    claims = load_json(ps.pack_path(slug, "claims"))
    bindings = load_json(ps.pack_path(slug, "field_bindings"))
    rules_file = ps.rules_path(slug)
    rules = load_json(rules_file)

    source_by_id = {s["source_id"]: s for s in sources.get("sources") or [] if "source_id" in s}
    claim_by_id = {c["claim_id"]: c for c in claims.get("claims") or [] if "claim_id" in c}

    actions: List[str] = []

    if "remove_forbidden_status_bindings" in allowed_actions:
        actions.extend(_remove_forbidden_bindings(bindings, claim_by_id, policy))
    if "replace_superseded_source_urls" in allowed_actions:
        actions.extend(_replace_superseded_urls(rules, source_by_id))
    if "tighten_soft_modals_from_claim_wording" in allowed_actions:
        actions.extend(_tighten_soft_modals(rules, claim_by_id, bindings))
    if "remove_forbidden_inference_phrases" in allowed_actions:
        actions.extend(_strip_forbidden_phrases(rules, claim_by_id, policy))

    if not actions:
        print(f"No allowlisted auto-corrections applicable for '{slug}'.")
    else:
        print(f"Proposed auto-corrections ({len(actions)}):")
        for a in actions:
            print(f"  - {a}")

    if apply and actions:
        save_json(rules_file, rules)
        save_json(ps.pack_path(slug, "field_bindings"), bindings)
        print(f"Applied corrections to {rules_file.name} and field_bindings.json")
    elif actions and not apply:
        print("Dry run only. Re-run with --apply to write changes.")

    # One-cycle re-review (protocol: max one auto-correct cycle)
    print("\n--- Re-review after fix cycle ---")
    return cmd_review(slug)


def cmd_intake_review(slug: str) -> int:
    result, report = review_intake(slug)
    report_path = write_intake_report(slug, report)
    print_intake_result(result, report_path)
    return 0 if result.decision == "PASS" else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Governed Country Pipeline orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_review = sub.add_parser("review", help="Run Phase 1 multi-layer draft review")
    p_review.add_argument("slug", help="Country slug (e.g. brazil)")
    p_review.add_argument(
        "--require-publish-ready",
        action="store_true",
        help="Treat publication lifecycle mismatches as blocking",
    )

    p_fix = sub.add_parser("fix", help="Apply one limited auto-correct cycle then review")
    p_fix.add_argument("slug", help="Country slug (e.g. brazil)")
    p_fix.add_argument(
        "--apply",
        action="store_true",
        help="Write corrections (default is dry-run)",
    )

    p_intake = sub.add_parser(
        "intake-review",
        help="Run Phase 2 M1 intake review and write intake_report.json",
    )
    p_intake.add_argument("slug", help="Country slug (e.g. brazil)")

    args = parser.parse_args(argv)

    if args.command == "review":
        return cmd_review(args.slug, require_publish_ready=args.require_publish_ready)
    if args.command == "fix":
        return cmd_fix(args.slug, apply=args.apply)
    if args.command == "intake-review":
        return cmd_intake_review(args.slug)
    return 2


if __name__ == "__main__":
    sys.exit(main())
