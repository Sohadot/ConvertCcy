#!/usr/bin/env python3
"""
ConvertCCY — Global FX Rules Reference Layer
============================================
rules_quality_gate.py v1.2.1

Purpose
-------
Prevent lifecycle leakage between:
- preview layer
- release candidate layer
- public sovereign layer

This gate verifies that only `published` country rule entries can exist in the
public layer and be marked sitemap-eligible.

Checks
------
1. rules_manifest.json exists and is valid
2. manifest structure and counts are coherent
3. published entries only:
   - render into public/rules/*.html
   - have sitemap_eligible=True
   - may expose public_url
4. verified / needs_hardening / secondary_review:
   - render only under preview/
   - have sitemap_eligible=False
   - must not expose public_url
5. needs_source_review / blocked:
   - do not render at all
6. public/rules/ contains only published country pages (+ index.html)
7. preview/ contains only preview statuses
8. no lifecycle contamination between directories
9. public index is indexable; preview indexes are noindex
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set

CURRENT_DIR = Path(__file__).resolve().parent
PARENT_DIR = CURRENT_DIR.parent

if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

try:
    import rules_schema as rs
except Exception as exc:
    print(f"ERROR: Could not import rules_schema.py: {exc}", file=sys.stderr)
    sys.exit(2)


@dataclass
class GateResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors and not self.warnings


def read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def looks_noindex(html_text: str) -> bool:
    lowered = html_text.lower()
    return 'name="robots"' in lowered and "noindex" in lowered


def looks_indexable(html_text: str) -> bool:
    lowered = html_text.lower()
    return 'name="robots"' in lowered and "index,follow" in lowered


def normalize_path_str(path_str: str) -> str:
    return path_str.replace("\\", "/")


def expected_preview_statuses() -> Set[str]:
    return {
        rs.PageStatus.VERIFIED.value,
        rs.PageStatus.NEEDS_HARDENING.value,
        rs.PageStatus.SECONDARY_REVIEW.value,
    }


def validate_manifest_structure(manifest: Dict[str, Any], result: GateResult) -> None:
    required_top = {
        "generated_at",
        "base_url",
        "schema_version_target",
        "counts",
        "published_entries",
        "verified_entries",
        "needs_hardening_entries",
        "secondary_review_entries",
        "skipped_entries",
    }
    missing = required_top - set(manifest.keys())
    if missing:
        result.error(f"Manifest missing required top-level keys: {sorted(missing)}")

    if manifest.get("schema_version_target") != rs.SCHEMA_VERSION_CURRENT:
        result.error(
            f"Manifest schema_version_target must be {rs.SCHEMA_VERSION_CURRENT}, got {manifest.get('schema_version_target')}"
        )

    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        result.error("Manifest counts must be an object")
        return

    for key in ["published", "verified", "needs_hardening", "secondary_review", "skipped"]:
        if key not in counts:
            result.error(f"Manifest counts missing key: {key}")
        elif not isinstance(counts[key], int):
            result.error(f"Manifest counts.{key} must be an integer")


def check_counts(manifest: Dict[str, Any], result: GateResult) -> None:
    counts = manifest.get("counts", {})
    mapping = {
        "published": "published_entries",
        "verified": "verified_entries",
        "needs_hardening": "needs_hardening_entries",
        "secondary_review": "secondary_review_entries",
        "skipped": "skipped_entries",
    }
    for count_key, list_key in mapping.items():
        entries = manifest.get(list_key, [])
        if isinstance(entries, list) and counts.get(count_key) != len(entries):
            result.error(
                f"Manifest count mismatch: counts.{count_key}={counts.get(count_key)} but len({list_key})={len(entries)}"
            )


def validate_manifest_entries(site_root: Path, manifest: Dict[str, Any], result: GateResult) -> None:
    groups = {
        rs.PageStatus.PUBLISHED.value: manifest.get("published_entries", []),
        rs.PageStatus.VERIFIED.value: manifest.get("verified_entries", []),
        rs.PageStatus.NEEDS_HARDENING.value: manifest.get("needs_hardening_entries", []),
        rs.PageStatus.SECONDARY_REVIEW.value: manifest.get("secondary_review_entries", []),
    }

    for expected_status, entries in groups.items():
        if not isinstance(entries, list):
            result.error(f"Manifest group for {expected_status} must be a list")
            continue

        for idx, entry in enumerate(entries):
            prefix = f"{expected_status}[{idx}]"
            if not isinstance(entry, dict):
                result.error(f"{prefix} must be an object")
                continue

            status = entry.get("status")
            slug = entry.get("country_slug")
            output_html = entry.get("output_html")
            public_url = entry.get("public_url")
            sitemap_eligible = entry.get("sitemap_eligible")

            if status != expected_status:
                result.error(f"{prefix} status mismatch: expected {expected_status}, got {status}")

            if not isinstance(slug, str) or not slug.strip():
                result.error(f"{prefix} country_slug must be a non-empty string")

            if not isinstance(output_html, str) or not output_html.strip():
                result.error(f"{prefix} output_html must be a non-empty string")
                continue

            normalized_output = normalize_path_str(output_html)

            if expected_status == rs.PageStatus.PUBLISHED.value:
                if "/public/rules/" not in normalized_output:
                    result.error(f"{prefix} published entry must render under public/rules/: {output_html}")
                if sitemap_eligible is not True:
                    result.error(f"{prefix} published entry must have sitemap_eligible=True")
                if not public_url:
                    result.error(f"{prefix} published entry must have public_url")
            else:
                if "/preview/rules/" not in normalized_output:
                    result.error(f"{prefix} preview entry must render under preview/rules/: {output_html}")
                if sitemap_eligible is not False:
                    result.error(f"{prefix} preview entry must have sitemap_eligible=False")
                if public_url not in (None, ""):
                    result.error(f"{prefix} preview entry must not expose public_url")

            out_path = Path(output_html)
            if not out_path.is_absolute():
                out_path = (site_root / out_path).resolve()

            if not out_path.exists():
                result.error(f"{prefix} rendered output does not exist: {out_path}")
                continue

            html_text = read_text(out_path)
            if expected_status == rs.PageStatus.PUBLISHED.value:
                if not looks_indexable(html_text):
                    result.error(f"{prefix} public page must contain robots=index,follow")
            else:
                if not looks_noindex(html_text):
                    result.error(f"{prefix} preview page must contain robots=noindex")

    skipped_entries = manifest.get("skipped_entries", [])
    if not isinstance(skipped_entries, list):
        result.error("Manifest skipped_entries must be a list")
        return

    for idx, entry in enumerate(skipped_entries):
        prefix = f"skipped[{idx}]"
        if not isinstance(entry, dict):
            result.error(f"{prefix} must be an object")
            continue
        status = entry.get("status")
        if status not in {rs.PageStatus.NEEDS_REVIEW.value, rs.PageStatus.BLOCKED.value}:
            result.error(f"{prefix} invalid skipped status: {status}")


def scan_public_layer(site_root: Path, manifest: Dict[str, Any], result: GateResult) -> None:
    public_rules_dir = site_root / "public" / "rules"
    public_rules_dir.mkdir(parents=True, exist_ok=True)

    actual_public_pages = {
        p.stem
        for p in public_rules_dir.glob("*.html")
        if p.is_file() and p.name != "index.html"
    }

    manifest_published_slugs = {
        entry.get("country_slug")
        for entry in manifest.get("published_entries", [])
        if isinstance(entry, dict)
    }

    leaked_public = actual_public_pages - manifest_published_slugs
    missing_public = manifest_published_slugs - actual_public_pages

    if leaked_public:
        result.error(
            f"Public layer leakage detected. Non-published slugs present in public/rules/: {sorted(leaked_public)}"
        )
    if missing_public:
        result.error(
            f"Published slugs missing from public/rules/: {sorted(missing_public)}"
        )


def scan_preview_layer(site_root: Path, manifest: Dict[str, Any], result: GateResult) -> None:
    preview_rules_dir = site_root / "preview" / "rules"
    preview_rules_dir.mkdir(parents=True, exist_ok=True)

    expected = {
        rs.PageStatus.VERIFIED.value: {
            entry.get("country_slug")
            for entry in manifest.get("verified_entries", [])
            if isinstance(entry, dict)
        },
        rs.PageStatus.NEEDS_HARDENING.value: {
            entry.get("country_slug")
            for entry in manifest.get("needs_hardening_entries", [])
            if isinstance(entry, dict)
        },
        rs.PageStatus.SECONDARY_REVIEW.value: {
            entry.get("country_slug")
            for entry in manifest.get("secondary_review_entries", [])
            if isinstance(entry, dict)
        },
    }

    for status, expected_slugs in expected.items():
        dir_path = preview_rules_dir / status
        dir_path.mkdir(parents=True, exist_ok=True)
        actual_slugs = {
            p.stem
            for p in dir_path.glob("*.html")
            if p.is_file() and p.name != "index.html"
        }
        leaked = actual_slugs - expected_slugs
        missing = expected_slugs - actual_slugs

        if leaked:
            result.error(
                f"Preview layer contamination in preview/rules/{status}/: unexpected slugs {sorted(leaked)}"
            )
        if missing:
            result.error(
                f"Preview layer missing expected slugs in preview/rules/{status}/: {sorted(missing)}"
            )


def prevent_cross_layer_contamination(site_root: Path, manifest: Dict[str, Any], result: GateResult) -> None:
    published_slugs = {
        entry.get("country_slug")
        for entry in manifest.get("published_entries", [])
        if isinstance(entry, dict)
    }
    preview_slugs = set()
    for key in ["verified_entries", "needs_hardening_entries", "secondary_review_entries"]:
        preview_slugs |= {
            entry.get("country_slug")
            for entry in manifest.get(key, [])
            if isinstance(entry, dict)
        }

    overlap = published_slugs & preview_slugs
    if overlap:
        result.error(f"Lifecycle contamination: slugs appear in both public and preview layers: {sorted(overlap)}")

    public_rules_dir = site_root / "public" / "rules"
    for slug in preview_slugs:
        if (public_rules_dir / f"{slug}.html").exists():
            result.error(f"Preview slug leaked into public layer: {slug}")

    preview_rules_dir = site_root / "preview" / "rules"
    for slug in published_slugs:
        for status in expected_preview_statuses():
            if (preview_rules_dir / status / f"{slug}.html").exists():
                result.warn(f"Published slug also exists in preview/{status}: {slug}")


def validate_index_pages(site_root: Path, result: GateResult) -> None:
    public_index = site_root / "public" / "rules" / "index.html"
    if not public_index.exists():
        result.error("Missing public/rules/index.html")
    else:
        html_text = read_text(public_index)
        if not looks_indexable(html_text):
            result.error("public/rules/index.html must contain robots=index,follow")

    preview_root = site_root / "preview" / "rules"
    for status in expected_preview_statuses():
        idx = preview_root / status / "index.html"
        if not idx.exists():
            result.error(f"Missing preview/rules/{status}/index.html")
            continue
        html_text = read_text(idx)
        if not looks_noindex(html_text):
            result.error(f"preview/rules/{status}/index.html must contain robots=noindex")


def run_gate(site_root: Path) -> GateResult:
    result = GateResult()
    manifest_path = site_root / "data" / "generated" / "rules_manifest.json"

    if not manifest_path.exists():
        result.error(f"Missing manifest: {manifest_path}")
        return result

    try:
        manifest = read_json(manifest_path)
    except Exception as exc:
        result.error(f"Invalid manifest JSON: {exc}")
        return result

    validate_manifest_structure(manifest, result)
    check_counts(manifest, result)
    validate_manifest_entries(site_root, manifest, result)
    scan_public_layer(site_root, manifest, result)
    scan_preview_layer(site_root, manifest, result)
    prevent_cross_layer_contamination(site_root, manifest, result)
    validate_index_pages(site_root, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Strict quality gate for ConvertCCY rules lifecycle separation")
    parser.add_argument("--site-root", default=".", help="Repository / site root")
    args = parser.parse_args()

    site_root = Path(args.site_root).resolve()
    if not site_root.exists():
        print(f"ERROR: site root does not exist: {site_root}", file=sys.stderr)
        return 2

    result = run_gate(site_root)

    for note in result.notes:
        print(f"NOTE: {note}")
    for warning in result.warnings:
        print(f"WARNING: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")

    if result.ok:
        print("PASS — rules_quality_gate v1.2.1: 0 errors, 0 warnings")
        return 0

    print(f"FAIL — {len(result.errors)} error(s), {len(result.warnings)} warning(s)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
