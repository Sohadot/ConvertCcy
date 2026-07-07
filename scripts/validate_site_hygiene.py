#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_site_hygiene.py — repo-wide JSON well-formedness + link-hygiene gate.

Part of the CI governance gate. Three cheap, deterministic sweeps over the
committed tree:

1. Every *.json file in the repository parses as valid JSON. Catches a
   hand-edit typo before it reaches main.
2. Every <a target="_blank"> anchor in every *.html file carries
   rel="noopener" (reverse-tabnabbing hardening — a page opened via
   target="_blank" without rel="noopener" can use window.opener to
   navigate the originating tab).
3. No *.html file outside preview/ contains a live href into /preview/.
   The preview layer is intentionally non-public (noindex, not linked,
   not in the sitemap); a stray public link into it would be a leak of
   an unpublished/RC entry, which the project's standing rules forbid.

This script does not regenerate anything and does not touch git state. It
only reads the working tree as committed.

Run: python3 scripts/validate_site_hygiene.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

EXCLUDE_DIR_PARTS = {".git", "node_modules", "__pycache__"}

TARGET_BLANK_RE = re.compile(r'<a\b[^>]*\btarget="_blank"[^>]*>', re.IGNORECASE)
REL_NOOPENER_RE = re.compile(r'\brel="[^"]*\bnoopener\b[^"]*"', re.IGNORECASE)
PREVIEW_HREF_RE = re.compile(r'href="[^"]*preview[^"]*"', re.IGNORECASE)


def iter_files(suffix: str):
    for path in REPO.rglob(f"*{suffix}"):
        if any(part in EXCLUDE_DIR_PARTS for part in path.parts):
            continue
        yield path


def check_json_wellformed() -> list[str]:
    errors = []
    for path in iter_files(".json"):
        try:
            json.loads(path.read_text())
        except json.JSONDecodeError as e:
            errors.append(f"{path.relative_to(REPO)}: invalid JSON — {e}")
        except UnicodeDecodeError as e:
            errors.append(f"{path.relative_to(REPO)}: unreadable as UTF-8 — {e}")
    return errors


def check_target_blank_noopener() -> list[str]:
    errors = []
    for path in iter_files(".html"):
        text = path.read_text(errors="replace")
        for m in TARGET_BLANK_RE.finditer(text):
            tag = m.group(0)
            if not REL_NOOPENER_RE.search(tag):
                errors.append(
                    f"{path.relative_to(REPO)}: target=\"_blank\" anchor missing rel=\"noopener\": {tag[:140]}"
                )
    return errors


def check_no_public_preview_links() -> list[str]:
    errors = []
    for path in iter_files(".html"):
        rel = path.relative_to(REPO)
        if rel.parts and rel.parts[0] == "preview":
            continue  # preview pages may link within preview
        text = path.read_text(errors="replace")
        for m in PREVIEW_HREF_RE.finditer(text):
            errors.append(f"{rel}: public page links into /preview/: {m.group(0)}")
    return errors


def main() -> int:
    all_errors: list[str] = []
    checks = [
        ("JSON well-formedness", check_json_wellformed),
        ("target=\"_blank\" / rel=\"noopener\" hygiene", check_target_blank_noopener),
        ("no public /preview/ links", check_no_public_preview_links),
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
        print(f"\nSite hygiene validation FAILED — {len(all_errors)} total issue(s)")
        return 1

    print("\nSite hygiene validation PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
