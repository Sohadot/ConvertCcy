#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_metal_snapshot.py — SEO-A4.4 gate for data/metal_reference_snapshot.json.

Fails closed (metal_reference.validate_metal_snapshot) on: wrong type or
activation state (must agree with data/instrument_classification.json), bad
freshness / derivation policy, sources without a valid license_state, role or
licence basis, licence evidence that does not resolve to the verification
registry, duplicate keys or source ids, and any quote that is not a positive
decimal string with metal code, unit, counter-currency, timestamps, provenance
and a source whose licence permits publication. A reference_layer_only
snapshot must carry no quotes.

Run: python3 scripts/validate_metal_snapshot.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import instrument_policy as ip  # noqa: E402
import metal_reference as mr  # noqa: E402


def main() -> int:
    try:
        snap = mr.load_metal_snapshot()
    except (mr.MetalSnapshotError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    errs = mr.validate_metal_snapshot(snap, ip.load_raw())
    lic = Counter(s.get("license_state") for s in snap.get("sources", []))
    print(f"activation_state={snap.get('activation_state')} sources={len(snap.get('sources', []))} "
          f"quotes={len(snap.get('quotes', []))} licence states={dict(lic)}")
    if errs:
        print(f"FAIL: {len(errs)} metal snapshot errors")
        for e in errs[:40]:
            print(f"  - {e}")
        return 1
    print("PASS: metal reference snapshot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
