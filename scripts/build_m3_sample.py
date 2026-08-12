#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_m3_sample.py — build the M3 public governed sample (M3-1 artifact).

This is the reproducible builder for the "ConvertCCY Governed Currency Rules —
Public Sample Dataset". It is a *projection* of the already-published governed
rules layer (rules/dataset.json). It creates no new governed data: it only
selects a fixed subset of jurisdictions that are already eligible in the
published layer, and emits them plus reproducibility metadata.

Governed by docs/M3_DATASET_DISCOVERY_PLAN.md (§5.0). Key rules enforced here:

  * The source is read from a PINNED git object (SOURCE_COMMIT below), via
    `git show <commit>:rules/dataset.json`, NOT from the working tree or HEAD.
    This makes v0.1.0 exactly reproducible: checkout any commit, run the
    builder, and the committed data/README/CITATION hashes reproduce. It also
    prevents attributing uncommitted local edits to a real commit.
  * Fixed five-jurisdiction subset (representational diversity, not traffic).
  * No automatic substitution. If any of the five is not `published` or not
    `indexing_allowed` at the pinned source commit, the sample gate HALTS and
    reports; it never silently swaps in another jurisdiction.
  * DOI is not fabricated: `doi` is null and `doi_status` is "not_reserved"
    until an actual DOI is reserved on Zenodo (M3-2, out of scope here).
  * The emitted data file carries only values that are stable at the pinned
    source commit (no wall-clock), so its SHA-256 is reproducible. The
    wall-clock `generated_at` lives in the manifest only.

To cut a new version later (e.g. v0.2.0) that tracks newer governed data,
bump SAMPLE_VERSION and SOURCE_COMMIT together as a deliberate decision.

Run: python3 scripts/build_m3_sample.py
Exit code 0 = sample written; non-zero = sample gate halted (nothing written).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "dataset" / "sample"

# Path of the governed dataset inside the pinned git object.
SOURCE_DATASET_PATH = "rules/dataset.json"

# The sample is pinned to a specific commit of the governed data, so v0.1.0 is
# reproducible from a Git object rather than from whatever is in the working
# tree. Bumping this is a deliberate versioning decision (see module docstring).
SOURCE_COMMIT = "7298908e189ee9cedd6d03db4b0632d481c61343"

SAMPLE_VERSION = "0.1.0"
SOURCE_REPOSITORY = "https://github.com/Sohadot/ConvertCcy"
CANONICAL_DATASET_URL = "https://convertccy.com/dataset.html"
FULL_DATASET_URL = "https://convertccy.com/rules/dataset.json"
LICENSE = "CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/"
ATTRIBUTION = "ConvertCCY (https://convertccy.com/)"
DATA_FILENAME = "convertccy-governed-currency-rules-sample.json"

# Fixed, approved subset. Order is meaningful and must not be reordered.
INCLUDED_JURISDICTIONS = [
    "south-korea",
    "india",
    "france",
    "south-africa",
    "canada",
]

SELECTION_RULE = (
    "A fixed illustrative subset of five already-published governed "
    "jurisdictions, selected to expose materially different currency-passage "
    "and regulatory structures across regions and authority patterns. "
    "Selection is based on representational diversity of the governed model, "
    "not traffic, market size, commercial attractiveness, or new research "
    "performed for M3. No jurisdiction is included unless it is already "
    "eligible in the published governed layer at the pinned source commit."
)


def _read_pinned_source() -> str:
    """Read rules/dataset.json from the PINNED commit's git object.

    Not from the working tree and not from HEAD — this is what makes v0.1.0
    reproducible and keeps provenance honest.
    """
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO), "show", f"{SOURCE_COMMIT}:{SOURCE_DATASET_PATH}"],
            text=True,
        )
    except subprocess.CalledProcessError:
        _halt(
            f"cannot read {SOURCE_DATASET_PATH} at pinned commit "
            f"{SOURCE_COMMIT} (object missing? fetch full history)"
        )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _halt(reason: str) -> "NoReturn":  # type: ignore[name-defined]
    sys.stderr.write(
        "\nSAMPLE GATE HALT — no sample written, no automatic substitution.\n"
        f"Reason: {reason}\n"
        "Resolve the governance status of the jurisdiction (or escalate) "
        "before re-running. build_m3_sample.py will not choose a replacement.\n\n"
    )
    sys.exit(1)


def _dump(obj) -> str:
    """Stable serialization: preserve source key order, 2-space indent."""
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    dataset = json.loads(_read_pinned_source())
    by_slug = {c["country_slug"]: c for c in dataset.get("countries", [])}

    # --- Sample gate: validate all five, halt (never substitute) on any miss.
    projected = []
    for slug in INCLUDED_JURISDICTIONS:
        country = by_slug.get(slug)
        if country is None:
            _halt(f"'{slug}' is not present in the published dataset")
        if country.get("page_status") != "published":
            _halt(
                f"'{slug}' page_status is "
                f"'{country.get('page_status')}', not 'published'"
            )
        if country.get("indexing_allowed") is not True:
            _halt(f"'{slug}' indexing_allowed is not true")
        projected.append(country)

    source_commit = SOURCE_COMMIT

    # --- Emit the data file (stable at a commit; no wall-clock inside it).
    sample_data = {
        "dataset": "ConvertCCY Governed Currency Rules — Public Sample Dataset",
        "description": (
            "A fixed five-jurisdiction public sample of the ConvertCCY "
            "governed foreign-currency-rules dataset. Each field is mapped to "
            "official sources with a visible review date. This is a projection "
            "of the published governed layer, not a separate dataset."
        ),
        "canonical_dataset": CANONICAL_DATASET_URL,
        "full_dataset": FULL_DATASET_URL,
        "license": LICENSE,
        "attribution": ATTRIBUTION,
        "citation": (
            "ConvertCCY. Governed Currency Rules — Public Sample Dataset "
            f"(v{SAMPLE_VERSION}). {CANONICAL_DATASET_URL}"
        ),
        "sample_version": SAMPLE_VERSION,
        "source_commit": source_commit,
        "doi": None,
        "doi_status": "not_reserved",
        "selection_rule": SELECTION_RULE,
        "count": len(projected),
        "jurisdictions": projected,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data_path = OUT_DIR / DATA_FILENAME
    data_path.write_text(_dump(sample_data), encoding="utf-8")

    readme = _render_readme(source_commit)
    citation = _render_citation(source_commit)
    (OUT_DIR / "README.md").write_text(readme, encoding="utf-8")
    (OUT_DIR / "CITATION.cff").write_text(citation, encoding="utf-8")

    # --- Manifest: lists every emitted file with SHA-256. Manifest excludes
    #     itself. Wall-clock generated_at lives here only.
    files = []
    for name in sorted(p.name for p in OUT_DIR.iterdir() if p.name != "manifest.json"):
        p = OUT_DIR / name
        files.append(
            {"path": name, "bytes": p.stat().st_size, "sha256": _sha256(p)}
        )

    manifest = {
        "sample": "ConvertCCY Governed Currency Rules — Public Sample Dataset",
        "sample_version": SAMPLE_VERSION,
        "source_repository": SOURCE_REPOSITORY,
        "source_commit": source_commit,
        "canonical_dataset_url": CANONICAL_DATASET_URL,
        "full_dataset_url": FULL_DATASET_URL,
        "license": LICENSE,
        "attribution": ATTRIBUTION,
        "doi": None,
        "doi_status": "not_reserved",
        "generated_at": _dt.datetime.now(_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "selection_basis": "representational_diversity",
        "selection_rule": SELECTION_RULE,
        "included_jurisdictions": [
            {
                "country_slug": c["country_slug"],
                "country_name": c["country_name"],
                "iso2": c["iso2"],
                "currency_code": c["currency_code"],
                "last_reviewed": c["last_reviewed"],
                "evidence_tier": c["evidence_tier"],
            }
            for c in projected
        ],
        "integrity": {"algorithm": "SHA-256"},
        "files": files,
    }
    (OUT_DIR / "manifest.json").write_text(_dump(manifest), encoding="utf-8")

    print(f"Sample written to {OUT_DIR.relative_to(REPO)}/")
    print(f"  source_commit: {source_commit}")
    print(f"  jurisdictions: {', '.join(INCLUDED_JURISDICTIONS)}")
    for f in files:
        print(f"  {f['sha256'][:12]}…  {f['path']}  ({f['bytes']} B)")
    print("  doi: null (not_reserved)")
    return 0


def _render_readme(source_commit: str) -> str:
    juris = "\n".join(f"- {s}" for s in INCLUDED_JURISDICTIONS)
    return f"""# ConvertCCY Governed Currency Rules — Public Sample Dataset

Version: {SAMPLE_VERSION}
License: {LICENSE}
Attribution: {ATTRIBUTION}
Canonical dataset page: {CANONICAL_DATASET_URL}
Full open dataset: {FULL_DATASET_URL}
Source repository: {SOURCE_REPOSITORY}
Source commit: {source_commit}
DOI: not reserved yet (doi_status: not_reserved)

## What this is

A fixed five-jurisdiction public sample of the ConvertCCY governed
foreign-currency-rules dataset. Each field is mapped to official sources
(central banks, customs authorities) with a visible review date. This file is a
**projection of the published governed layer** — it is not a separate dataset,
and it contains no data that is not already published and eligible for
indexing at the pinned source commit.

## Jurisdictions included

{juris}

## Selection rule

{SELECTION_RULE}

## Citation

ConvertCCY. Governed Currency Rules — Public Sample Dataset (v{SAMPLE_VERSION}).
{CANONICAL_DATASET_URL}

Under CC BY 4.0 this sample may be used, including commercially, with
attribution. Broader coverage, managed/current distributions, update delivery,
change history, an SLA, and integration support are separate enterprise
services — see the canonical dataset page.
"""


def _render_citation(source_commit: str) -> str:
    return f"""cff-version: 1.2.0
message: "If you use this sample, please cite it as below."
title: "ConvertCCY Governed Currency Rules — Public Sample Dataset"
version: "{SAMPLE_VERSION}"
license: CC-BY-4.0
url: "{CANONICAL_DATASET_URL}"
repository-code: "{SOURCE_REPOSITORY}"
commit: "{source_commit}"
authors:
  - name: "ConvertCCY"
    website: "https://convertccy.com/"
# doi: reserved on publication (Zenodo). doi_status: not_reserved
"""


if __name__ == "__main__":
    raise SystemExit(main())
