#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_live_fiat_snapshot.py — SEO-A4.6A gate for data/live_fiat_reference_snapshot.json.

Fails closed (live_fiat_reference.validate_live_fiat_snapshot) on: wrong type or
schema version; duplicate keys or source ids; unknown enum values; sources without
an https URL, tier, access state or audit date; secondary press marked publishable;
a covered code outside the scope rule (not an active fiat_currency /
restricted_fiat_currency in data/instrument_classification.json, or HAS a value in
data/rate_snapshot.json — such codes belong to A4.6B); classification_confidence or
review_flags that disagree with A4.1; a provider value recorded without an
identified regime; claims without a resolvable source, identity claims citing an
inaccessible source, secondary press outside reported indicators, or a reported
indicator stating a rate figure; value fields populated while the code is not live;
live availability without source_activated, an identified regime, value source,
freshness policy and licence; a transitional code without a resolvable operative
code; and any stored value that is not a direct positive decimal string with regime,
dates, provenance and a source whose tier fits the regime and whose licence permits
publication. A reference_layer_only snapshot carries no values and no captured_at.

Run: python3 scripts/validate_live_fiat_snapshot.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import live_fiat_reference as lf  # noqa: E402
import instrument_policy as ip  # noqa: E402


def main() -> int:
    try:
        snap = lf.load_live_fiat_snapshot()
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1
    fx = json.loads((REPO / "data" / "rate_snapshot.json").read_text(encoding="utf-8"))
    errs = lf.validate_live_fiat_snapshot(snap, ip.load_raw(), fx)
    cur = snap.get("currencies", {})
    avail = Counter(c.get("availability_status") for c in cur.values())
    tiers = Counter(s.get("source_tier") for s in snap.get("sources", []))
    print(f"activation_state={snap.get('activation_state')} covered={sorted(cur)} sources={len(snap.get('sources', []))} "
          f"values={len(snap.get('values', []))} availability={dict(avail)} source tiers={dict(tiers)}")
    if errs:
        print(f"FAIL: {len(errs)} live-fiat snapshot errors")
        for e in errs[:40]:
            print(f"  - {e}")
        return 1
    print("PASS: live-fiat reference snapshot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
