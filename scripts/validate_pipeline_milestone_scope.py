#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_pipeline_milestone_scope.py — PR/diff scope gate for pipeline milestones.

When M1 intake, M2 claim-extraction, or M2.5 human-review paths change, forbid
simultaneous mutation of claims.json, field_bindings.json, or data/rules/**.

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
from typing import List, Set

REPO = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO / "data" / "governance" / "country_pipeline_policy.json"


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


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate pipeline milestone PR scope")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--allow-rules-touch", action="store_true")
    args = parser.parse_args(argv)

    policy = load_policy()
    intake = policy.get("intake") or {}
    forbidden = list(intake.get("milestone_scope_forbidden_path_globs") or [])

    changed = git_changed_files(args.base)
    if not changed:
        print("Milestone scope check: no changed files detected (ok).")
        return 0

    milestone_touched = any(
        fnmatch.fnmatch(p, "data/coverage/pipeline/*/evidence_excerpts.json")
        or fnmatch.fnmatch(p, "data/coverage/pipeline/*/intake_report.json")
        or fnmatch.fnmatch(p, "data/coverage/pipeline/*/candidate_claims.json")
        or fnmatch.fnmatch(p, "data/coverage/pipeline/*/claim_extraction_report.json")
        or fnmatch.fnmatch(p, "data/coverage/pipeline/*/human_claim_review.json")
        or fnmatch.fnmatch(p, "data/coverage/pipeline/*/claim_review_report.json")
        or p.endswith("validate_source_intake.py")
        or p.endswith("validate_claim_extraction.py")
        or p.endswith("validate_human_claim_review.py")
        or p.endswith("validate_pipeline_milestone_scope.py")
        for p in changed
    )

    print(f"Changed files ({len(changed)}):")
    for p in changed:
        print(f"  {p}")

    if not milestone_touched:
        print("Milestone scope check: no M1/M2/M2.5 milestone paths touched (ok).")
        return 0

    errors: List[str] = []
    for path in changed:
        if args.allow_rules_touch and path.startswith("data/rules/"):
            continue
        if matches_any(path, forbidden):
            errors.append(
                f"Milestone scope violation: '{path}' is forbidden while M1/M2/M2.5 files change"
            )

    if errors:
        print("\nMilestone scope check FAILED:")
        for e in errors:
            print(f"  - {e}")
        print(
            "\nPipeline milestones must not rewrite claims, field_bindings, or rules. "
            "Split those changes into a separate PR."
        )
        return 1

    print("\nMilestone scope check PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
