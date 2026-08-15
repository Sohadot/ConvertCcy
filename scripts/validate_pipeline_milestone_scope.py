#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_pipeline_milestone_scope.py — PR/diff scope gate for pipeline milestones.

When M1/M2/M2.5 paths change:
  - every changed file must match the positive allowlist
  - forbidden globs (claims/bindings/rules/M3) still BLOCK
  - candidate_claims.json review-field freeze applies only when an M2.5
    surface is in the diff (ledger/report/validator)

Run:
  python scripts/validate_pipeline_milestone_scope.py
  python scripts/validate_pipeline_milestone_scope.py --base origin/main
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO / "data" / "governance" / "country_pipeline_policy.json"

CANDIDATE_CLAIMS_GLOB = "data/coverage/pipeline/*/candidate_claims.json"

MILESTONE_TOUCH_GLOBS = [
    "data/coverage/pipeline/*/evidence_excerpts.json",
    "data/coverage/pipeline/*/intake_report.json",
    "data/coverage/pipeline/*/candidate_claims.json",
    "data/coverage/pipeline/*/claim_extraction_report.json",
    "data/coverage/pipeline/*/human_claim_review.json",
    "data/coverage/pipeline/*/claim_review_report.json",
]

# Field-level freeze of candidate_claims.json is M2.5-only.
M2_5_SURFACE_GLOBS = [
    "data/coverage/pipeline/*/human_claim_review.json",
    "data/coverage/pipeline/*/claim_review_report.json",
]


def load_policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def git_changed_files(base: str) -> List[str]:
    cmds = [
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "diff", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    files: Set[str] = set()
    for cmd in cmds:
        try:
            out = subprocess.check_output(cmd, cwd=REPO, text=True, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            continue
        for line in out.splitlines():
            line = line.strip().replace("\\", "/")
            if line:
                files.add(line)
    return sorted(files)


def matches_any(path: str, globs: List[str]) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in globs)


def is_m2_5_surface_touched(changed: List[str]) -> bool:
    """True when the diff includes M2.5 ledger, report, or validator."""
    return any(
        matches_any(p, M2_5_SURFACE_GLOBS) or p.endswith("validate_human_claim_review.py")
        for p in changed
    )


def _nested_get(obj: Any, dotted: str) -> Any:
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _nested_set_marker(fields: List[str]) -> Set[str]:
    return set(fields)


def candidate_field_violations(
    base_doc: dict,
    head_doc: dict,
    allowed_fields: List[str],
) -> List[str]:
    """Return violations when head mutates fields outside the M2.5 allowlist."""
    errors: List[str] = []
    allowed = set(allowed_fields)
    base_items = {
        c.get("candidate_id"): c
        for c in (base_doc.get("candidates") or [])
        if isinstance(c, dict) and c.get("candidate_id")
    }
    head_items = {
        c.get("candidate_id"): c
        for c in (head_doc.get("candidates") or [])
        if isinstance(c, dict) and c.get("candidate_id")
    }
    if set(base_items) != set(head_items):
        errors.append(
            "candidate_claims.json added/removed candidates; M2.5 may only mutate review fields"
        )
        return errors

    top_skip = {"candidates"}
    for key in set(base_doc.keys()) | set(head_doc.keys()):
        if key in top_skip:
            continue
        if base_doc.get(key) != head_doc.get(key):
            errors.append(
                f"candidate_claims.json top-level field '{key}' changed; not an allowed review mutation"
            )

    for cid, head in head_items.items():
        base = base_items[cid]
        # Walk union of keys; nested allowlist uses dotted paths.
        all_keys = set(base.keys()) | set(head.keys())
        for key in sorted(all_keys):
            dotted_allowed = {f.split(".", 1)[0] for f in allowed}
            if key not in dotted_allowed and key not in allowed:
                if base.get(key) != head.get(key):
                    errors.append(
                        f"{cid}: field '{key}' changed but is not in allowed_candidate_mutation_fields"
                    )
                continue
            if key == "human_review":
                continue  # entire object allowed
            if key in allowed:
                continue  # whole field allowed (reviewed_text, support_status, ...)
            # Nested object: only listed dotted children may change.
            base_obj = base.get(key) if isinstance(base.get(key), dict) else {}
            head_obj = head.get(key) if isinstance(head.get(key), dict) else {}
            child_keys = set(base_obj.keys()) | set(head_obj.keys())
            for child in sorted(child_keys):
                dotted = f"{key}.{child}"
                if dotted in allowed:
                    continue
                if base_obj.get(child) != head_obj.get(child):
                    errors.append(
                        f"{cid}: field '{dotted}' changed but is not in allowed_candidate_mutation_fields"
                    )
    return errors


def evaluate_milestone_scope(
    changed: List[str],
    policy: dict,
    allow_rules_touch: bool = False,
    candidate_violations: Optional[List[str]] = None,
) -> List[str]:
    intake = policy.get("intake") or {}
    forbidden = list(intake.get("milestone_scope_forbidden_path_globs") or [])
    allowed = list(intake.get("milestone_scope_allowed_path_globs") or [])

    milestone_touched = any(
        matches_any(p, MILESTONE_TOUCH_GLOBS)
        or p.endswith("validate_source_intake.py")
        or p.endswith("validate_claim_extraction.py")
        or p.endswith("validate_human_claim_review.py")
        or p.endswith("validate_pipeline_milestone_scope.py")
        for p in changed
    )
    if not changed or not milestone_touched:
        return []

    errors: List[str] = []
    for path in changed:
        if allow_rules_touch and path.startswith("data/rules/"):
            continue
        if matches_any(path, forbidden):
            errors.append(
                f"Milestone scope violation: '{path}' is forbidden while M1/M2/M2.5 files change"
            )
            continue
        if allowed and not matches_any(path, allowed):
            errors.append(
                f"Milestone scope violation: '{path}' is not on the positive allowlist"
            )
    if candidate_violations:
        errors.extend(candidate_violations)
    return errors


def git_show_json(base: str, path: str) -> Optional[dict]:
    try:
            out = subprocess.check_output(
            ["git", "show", f"{base}:{path}"],
            cwd=REPO,
            text=True,
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def candidate_violations_vs_base(base: str, changed: List[str], policy: dict) -> List[str]:
    allowed = list(
        (policy.get("human_claim_review") or {}).get("allowed_candidate_mutation_fields") or []
    )
    errors: List[str] = []
    for path in changed:
        if not fnmatch.fnmatch(path.replace("\\", "/"), CANDIDATE_CLAIMS_GLOB):
            continue
        head_path = REPO / path
        if not head_path.exists():
            continue
        head_doc = json.loads(head_path.read_text(encoding="utf-8"))
        base_doc = git_show_json(base, path)
        if base_doc is None:
            continue
        errors.extend(candidate_field_violations(base_doc, head_doc, allowed))
    return errors


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate pipeline milestone PR scope")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--allow-rules-touch", action="store_true")
    args = parser.parse_args(argv)

    policy = load_policy()
    changed = git_changed_files(args.base)
    if not changed:
        print("Milestone scope check: no changed files detected (ok).")
        return 0

    print(f"Changed files ({len(changed)}):")
    for p in changed:
        print(f"  {p}")

    milestone_touched = any(
        matches_any(p, MILESTONE_TOUCH_GLOBS)
        or p.endswith("validate_source_intake.py")
        or p.endswith("validate_claim_extraction.py")
        or p.endswith("validate_human_claim_review.py")
        or p.endswith("validate_pipeline_milestone_scope.py")
        for p in changed
    )
    if not milestone_touched:
        print("Milestone scope check: no M1/M2/M2.5 milestone paths touched (ok).")
        return 0

    field_errors: List[str] = []
    if is_m2_5_surface_touched(changed):
        field_errors = candidate_violations_vs_base(args.base, changed, policy)
    errors = evaluate_milestone_scope(
        changed, policy, allow_rules_touch=args.allow_rules_touch, candidate_violations=field_errors
    )

    if errors:
        print("\nMilestone scope check FAILED:")
        for e in errors:
            print(f"  - {e}")
        print(
            "\nPipeline milestones must stay on the allowlist, must not rewrite "
            "claims/bindings/rules/M3, and may only mutate allowed candidate review fields."
        )
        return 1

    print("\nMilestone scope check PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
