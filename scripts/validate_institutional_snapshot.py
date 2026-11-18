#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_institutional_snapshot.py — SEO-A4.5 gate for data/institutional_reference_snapshot.json.

Fails closed (institutional_reference.validate_institutional_snapshot) on: wrong type or
activation state; duplicate keys or source ids; freshness policies without a
cadence-appropriate definition (no universal FX TTL: issuer cadences are explicit);
methodologies whose evidence does not resolve to the verification registry; sources
without a valid licence state, role or basis, or a publishable licence without
evidence; instrument policies that disagree with data/instrument_classification.json
or lack a methodology; any stored value that is not a direct, positive decimal string
with issuer, valuation type, denomination, valuation date, source timestamp,
retrieval time, methodology, provenance and a source whose licence permits
publication; a captured_at timestamp without values (no fabricated time); and
provider values that are not classified secondary or pending comparison.
A reference_layer_only snapshot must carry no values.

Run: python3 scripts/validate_institutional_snapshot.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import institutional_reference as ir  # noqa: E402
import instrument_policy as ip  # noqa: E402


def main() -> int:
    try:
        snap = ir.load_institutional_snapshot()
    except (ir.InstitutionalSnapshotError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    errs = ir.validate_institutional_snapshot(snap, ip.load_raw())
    lic = Counter(s.get("license_state") for s in snap.get("sources", []))
    dec = Counter(v.get("value_decision") for v in snap.get("instruments", {}).values())
    print(f"activation_state={snap.get('activation_state')} sources={len(snap.get('sources', []))} "
          f"values={len(snap.get('values', []))} licence states={dict(lic)} decisions={dict(dec)}")
    if errs:
        print(f"FAIL: {len(errs)} institutional snapshot errors")
        for e in errs[:40]:
            print(f"  - {e}")
        return 1
    print("PASS: institutional reference snapshot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
