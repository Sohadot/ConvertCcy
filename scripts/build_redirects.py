#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_redirects.py — generate exact 301 redirects for legacy pre-P3 pair URLs (GSC-1).

Before the P3 canonical migration, currency-pair pages lived at the site root
(e.g. /pln-to-sdg). They now live at /pages/pln-to-sdg.html. Google Search
Console still remembers ~1,500 of the old root URLs and reports them under
"Introuvable (404)". This script turns a GSC 404 export into a Cloudflare Pages
`_redirects` file with one EXACT 301 per known legacy URL — no broad wildcard,
so no legitimate root path is ever caught.

Safety rules:
  - EXACT match only. Each output line is `/<slug>  /pages/<slug>.html  301`.
    There is no `/:placeholder` or `/*` splat rule.
  - A redirect is emitted ONLY if the target file pages/<slug>.html actually
    exists. This guarantees no redirect ever points at a new 404, and it
    automatically drops non-pair noise (e.g. /cdn-cgi/l/email-protection).
  - Only root-form pair slugs (xxx-to-yyy, three-letter currency codes) are
    considered. Anything else in the export is ignored.

Input:
  One or more GSC exports of the "Introuvable (404)" report. Accepts CSV
  (any column may hold the URL), TSV, or a plain list of URLs/paths — the
  parser just scans each file for convertccy.com pair URLs or /xxx-to-yyy paths.
  GSC caps a single export at 1,000 rows; pass multiple exports and they are
  merged and de-duplicated.

Output:
  _redirects  (Cloudflare Pages format) at the repo root by default.

Run:
  python3 scripts/build_redirects.py path/to/gsc-404-export.csv [more.csv ...]
  python3 scripts/build_redirects.py export.csv --check   # report only, write nothing
  python3 scripts/build_redirects.py export.csv --out _redirects
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAGES_DIR = REPO / "pages"
DEFAULT_OUT = REPO / "_redirects"

# Cloudflare Pages serves the first 2,000 static redirects from _redirects.
CLOUDFLARE_STATIC_LIMIT = 2000

# A legacy root-form pair slug: three-letter ISO-style codes, e.g. pln-to-sdg.
PAIR_SLUG = re.compile(r"^[a-z]{3}-to-[a-z]{3}$")
# Find candidate paths anywhere in a line: a leading-slash slug, with or without
# the convertccy.com host in front, tolerating query strings / trailing slashes.
PATH_IN_LINE = re.compile(r"/([a-z]{3}-to-[a-z]{3})(?:[/?#\s\"',]|$)")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def extract_slugs(text: str) -> set[str]:
    """Pull every root-form pair slug out of one export file's raw text."""
    found: set[str] = set()
    for m in PATH_IN_LINE.finditer(text.lower()):
        slug = m.group(1)
        if PAIR_SLUG.match(slug):
            found.add(slug)
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate exact 301 redirects for legacy pair URLs from a GSC 404 export.")
    parser.add_argument("inputs", nargs="+", help="GSC 404 export file(s): CSV, TSV, or plain URL list")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output _redirects path (default: repo-root/_redirects)")
    parser.add_argument("--check", action="store_true", help="report only; write nothing")
    args = parser.parse_args()

    if not PAGES_DIR.is_dir():
        sys.exit(f"ERROR: {PAGES_DIR} not found — run from the repo, pages/ must exist to validate targets.")

    # 1) Gather candidate slugs from every export.
    candidates: set[str] = set()
    for raw in args.inputs:
        p = Path(raw)
        if not p.exists():
            sys.exit(f"ERROR: input not found: {p}")
        candidates |= extract_slugs(p.read_text(errors="replace"))

    if not candidates:
        sys.exit(
            "No legacy pair URLs (/xxx-to-yyy) found in the input. Make sure you "
            "exported the 'Introuvable (404)' report, not an empty or unrelated file."
        )

    # 2) Keep only those whose target page actually exists (no redirect to a 404).
    redirects: list[tuple[str, str]] = []
    missing_target: list[str] = []
    for slug in sorted(candidates):
        target_file = PAGES_DIR / f"{slug}.html"
        if target_file.exists():
            redirects.append((f"/{slug}", f"/pages/{slug}.html"))
        else:
            missing_target.append(slug)

    # 3) Report.
    print(f"Legacy pair URLs found in export(s): {len(candidates)}")
    print(f"  → with a live target page (will redirect): {len(redirects)}")
    print(f"  → target page missing (skipped, stays 404): {len(missing_target)}")
    if missing_target:
        preview = ", ".join(missing_target[:8])
        print(f"    skipped examples: {preview}{' …' if len(missing_target) > 8 else ''}")
    if len(redirects) > CLOUDFLARE_STATIC_LIMIT:
        print(
            f"  WARNING: {len(redirects)} redirects exceeds Cloudflare Pages' "
            f"{CLOUDFLARE_STATIC_LIMIT} static-redirect limit. Split or prune the list."
        )
    if not redirects:
        sys.exit("Nothing to write: no legacy URL had a live target page.")

    # 4) Compose the _redirects file.
    header = (
        "# ConvertCCY legacy pair-URL redirects (GSC-1)\n"
        f"# Generated: {now_iso()} by scripts/build_redirects.py\n"
        "# Exact 301s from pre-P3 root URLs (/xxx-to-yyy) to canonical /pages/xxx-to-yyy.html.\n"
        "# No wildcard/placeholder rules — only exact, target-validated lines below.\n"
        f"# Count: {len(redirects)} (Cloudflare Pages static limit: {CLOUDFLARE_STATIC_LIMIT}).\n"
        "\n"
    )
    body = "\n".join(f"{src}  {dst}  301" for src, dst in redirects) + "\n"
    content = header + body

    if args.check:
        print(f"\n--check: would write {len(redirects)} redirects to {args.out} (nothing written).")
        return

    out = Path(args.out)
    out.write_text(content)
    print(f"\nWrote {out} — {len(redirects)} exact 301 redirects.")


if __name__ == "__main__":
    main()
