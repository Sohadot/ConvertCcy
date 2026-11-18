#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_instrument_classification.py — SEO-A4.1 governance gate.

Validates data/instrument_classification.json through instrument_policy.validate():
  - exactly 170 classified codes, identical to data/currencies.json; no duplicates
  - exactly one primary instrument_type per code; every value in its enum
  - consistent status combinations (active/historical, legal tender, circulation,
    issuer type, rate expectation) per instrument type — fail closed
  - every type has page_role, rate_policy, source_policy, indexability and
    commercial_role; no default candidate_for_noindex for protected classes
  - anchored codes: XTS=test_code, XXX=no_currency, XAU/XAG/XPT/XPD=precious_metal,
    XUA/XSU/UYW not fiat, CUC/SVC historical/legacy, KPW/VED real currencies
  - any departure from the legacy currencies.json label carries a reason
  - snapshot-coverage evidence matches the current snapshot (coverage changes
    force a classification review)
and checks that data/generated/instrument_policy_matrix.json is current.

Run: python3 scripts/validate_instrument_classification.py [--report]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import instrument_policy as ip  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="print class counts and conformance")
    args = ap.parse_args()
    try:
        doc = ip.load_raw()
    except (ip.ClassificationError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}")
        return 1
    errs = ip.validate(doc)
    if errs:
        print(f"FAIL: {len(errs)} classification errors")
        for e in errs[:60]:
            print(f"  - {e}")
        return 1
    policy = ip.InstrumentPolicy(doc, validate_doc=False)
    text = ip.matrix_text(policy)
    if not ip.MATRIX_FILE.exists() or ip.MATRIX_FILE.read_text(encoding="utf-8") != text:
        print("FAIL: data/generated/instrument_policy_matrix.json is stale "
              "(run: python3 instrument_policy.py --write-matrix)")
        return 1
    m = json.loads(text)
    counts = {t: v["count"] for t, v in m["type_matrix"].items()}
    print(f"codes={sum(counts.values())} " + " ".join(f"{t}={n}" for t, n in counts.items()))
    nonconf = {k: v for k, v in m["policy_conformance"].items() if k != "conformant"}
    print("policy conformance gaps (informational, drive A4.x): "
          + "; ".join(f"{k}={len(v)} {v}" for k, v in nonconf.items()))
    if args.report:
        print(json.dumps(m["pair_cohorts"], indent=1))
    print("PASS: instrument classification and policy matrix")
    return 0


if __name__ == "__main__":
    sys.exit(main())
