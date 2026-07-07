#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_generated_artifacts.py — fail CI if a committed generated artifact
is stale relative to its source data.

Several public artifacts are generated, never hand-edited (standing rule
since P3/P4/P6/P7A). It is easy to forget to re-run the generator after
editing its source data, silently shipping a stale artifact. This script
regenerates each deterministic artifact into memory (or a scratch copy for
build_passage_briefs.py, which writes files directly) and fails if the
result differs from what is committed.

Covered (fully deterministic — no live network call, no self-timestamp
that changes between identical runs, or with the one timestamp field
normalized out):
  - rules/passage-check.json      (scripts/build_passage_check.py)
  - briefs/*.html                 (scripts/build_passage_briefs.py)
  - api/v1/*.json, api/v1/rules/*.json, api/index.html
                                   (scripts/build_static_agent_interface.py)
    — every api/v1/*.json file stamps its own "generated_at"; that single
      key is excluded from the comparison, everything else must match byte
      for byte.

Deliberately NOT covered here (documented, not silently skipped):
  - rules/dataset.json and rules/*.html (scripts/generate_rules.py) — a much
    larger regeneration (six-gate validation over all 23 country files,
    manifest rebuild) that also stamps its own generated_at; re-running it
    is a deliberate human step, not a per-PR CI gate.
  - pages/*.html (generate.py, 28,730 files) and sitemap.xml — regeneration
    is slow, and sitemap.xml's lastmod is expected to move on every run
    regardless of content; sitemap URL-set correctness is instead enforced
    by scripts/validate_coverage_intake.py (no candidate leak) and the
    existing Deployment Gate discipline (0 removed / N added review, done
    by hand at merge time — see DECISION_LOG.md).
  - rates/snapshot.json (scripts/build_rate_snapshot.py) — hits a live
    third-party network endpoint; refreshed manually, not on every PR.

Run: python3 scripts/validate_generated_artifacts.py
"""

from __future__ import annotations

import filecmp
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def run(script: str, cwd: Path) -> None:
    result = subprocess.run(
        [PYTHON, str(REPO / "scripts" / script)],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.exit(
            f"ERROR: {script} failed while regenerating for drift check "
            f"(exit {result.returncode})\n--- stdout ---\n{result.stdout}"
            f"\n--- stderr ---\n{result.stderr}"
        )


def check_passage_check_drift() -> list[str]:
    target = REPO / "rules" / "passage-check.json"
    before = target.read_bytes()
    run("build_passage_check.py", REPO)
    after = target.read_bytes()
    target.write_bytes(before)  # always restore the working tree; regeneration here is comparison-only
    if before != after:
        return ["rules/passage-check.json is stale — regenerate with scripts/build_passage_check.py and commit the result"]
    return []


def check_briefs_drift() -> list[str]:
    briefs_dir = REPO / "briefs"
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "briefs_before"
        shutil.copytree(briefs_dir, backup)
        run("build_passage_briefs.py", REPO)
        cmp = filecmp.dircmp(backup, briefs_dir)
        diffs = _dircmp_diffs(cmp, "briefs")
        shutil.rmtree(briefs_dir)
        shutil.copytree(backup, briefs_dir)  # always restore the working tree
        if diffs:
            return [f"briefs/ is stale ({d}) — regenerate with scripts/build_passage_briefs.py and commit the result" for d in diffs]
    return []


def _dircmp_diffs(cmp: filecmp.dircmp, label: str) -> list[str]:
    diffs = []
    for name in cmp.diff_files:
        diffs.append(f"{label}/{name} differs")
    for name in cmp.left_only:
        diffs.append(f"{label}/{name} would be removed by regeneration")
    for name in cmp.right_only:
        diffs.append(f"{label}/{name} is new / not yet regenerated")
    return diffs


def _strip_generated_at(obj):
    if isinstance(obj, dict):
        return {k: _strip_generated_at(v) for k, v in obj.items() if k != "generated_at"}
    if isinstance(obj, list):
        return [_strip_generated_at(v) for v in obj]
    return obj


def check_static_agent_interface_drift() -> list[str]:
    api_dir = REPO / "api"
    with tempfile.TemporaryDirectory() as tmp:
        backup = Path(tmp) / "api_before"
        shutil.copytree(api_dir, backup)
        run("build_static_agent_interface.py", REPO)

        diffs = []
        before_files = {p.relative_to(backup) for p in backup.rglob("*") if p.is_file()}
        after_files = {p.relative_to(api_dir) for p in api_dir.rglob("*") if p.is_file()}

        for rel in sorted(before_files - after_files):
            diffs.append(f"api/{rel} would be removed by regeneration")
        for rel in sorted(after_files - before_files):
            diffs.append(f"api/{rel} is new / not yet committed")

        for rel in sorted(before_files & after_files):
            before_path = backup / rel
            after_path = api_dir / rel
            if str(rel).endswith(".json"):
                before_obj = _strip_generated_at(json.loads(before_path.read_text()))
                after_obj = _strip_generated_at(json.loads(after_path.read_text()))
                if before_obj != after_obj:
                    diffs.append(f"api/{rel} content differs (ignoring generated_at)")
            else:
                if before_path.read_bytes() != after_path.read_bytes():
                    diffs.append(f"api/{rel} differs")

        shutil.rmtree(api_dir)
        shutil.copytree(backup, api_dir)  # always restore the working tree
        if diffs:
            return [f"{d} — regenerate with scripts/build_static_agent_interface.py and commit the result" for d in diffs]
    return []


def main() -> int:
    all_errors: list[str] = []
    checks = [
        ("rules/passage-check.json drift", check_passage_check_drift),
        ("briefs/ drift", check_briefs_drift),
        ("Static Agent Interface (api/) drift", check_static_agent_interface_drift),
    ]

    for name, fn in checks:
        errors = fn()
        if errors:
            print(f"[FAIL] {name} — {len(errors)} issue(s)")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"[PASS] {name}")
        all_errors.extend(errors)

    if all_errors:
        print(f"\nGenerated-artifact drift check FAILED — {len(all_errors)} total issue(s)")
        return 1

    print("\nGenerated-artifact drift check PASSED — all covered artifacts match their generators")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
