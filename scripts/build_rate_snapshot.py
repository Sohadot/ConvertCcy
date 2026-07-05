#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_rate_snapshot.py — capture a dated reference-rate snapshot for fallback use.

Why this exists (R2): every pair page and the home converter fetch live rates
from a single keyless third-party endpoint with no SLA. If that source is slow,
changes, or disappears, the interface previously fell back to a misleading 1:1
rate on pair pages. methodology.html already promises "predefined fallback rate
values" used only for continuity when the live source is unavailable — this
script produces exactly those values, dated and source-attributed, so the
promise and the implementation match.

Governance / rights posture:
  - The snapshot is an INDICATIVE reference cache for degraded-mode display only.
  - It is captured from the same public source the live path already uses, is
    clearly attributed, links the provider's terms, and is NOT relicensed
    (no CC BY, unlike rules/dataset.json). It is never presented as live or as a
    dealing rate.
  - If the capture fails, any existing committed snapshot is preserved unchanged
    (we never overwrite good fallback data with a failed fetch).

Outputs (identical content, two locations):
  - data/rate_snapshot.json      (source-of-truth in the data tree)
  - rates/snapshot.json          (served publicly for the client-side fallback)

Run: python3 scripts/build_rate_snapshot.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA_OUT = REPO / "data" / "rate_snapshot.json"
PUBLIC_OUT = REPO / "rates" / "snapshot.json"

SOURCE_ENDPOINT = "https://api.exchangerate-api.com/v4/latest/USD"
SOURCE_NAME = "exchangerate-api.com"
SOURCE_TERMS = "https://www.exchangerate-api.com/terms"
BASE = "USD"

NOTICE = (
    "Indicative USD-based reference rates captured for degraded-mode fallback "
    "display only. Not live, not a dealing rate, and not relicensed. Pages fetch "
    "live rates first and use this snapshot only when the live source is "
    "unavailable; when shown, it is labelled with its capture date."
)


def fetch_rates() -> dict:
    req = urllib.request.Request(SOURCE_ENDPOINT, headers={"User-Agent": "ConvertCCY-snapshot/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    rates = payload.get("rates") or {}
    if payload.get("base") != BASE or not isinstance(rates, dict) or BASE not in rates:
        raise ValueError("Unexpected source payload shape")
    # Keep only sane positive numeric rates; base must be exactly 1.
    clean = {}
    for code, val in rates.items():
        if isinstance(val, (int, float)) and val > 0 and str(code).isalpha() and len(str(code)) == 3:
            clean[str(code).upper()] = round(float(val), 6)
    clean[BASE] = 1.0
    src_date = payload.get("date", "")
    return {"rates": clean, "source_date": src_date}


def write_snapshot(rates: dict, source_date: str) -> dict:
    now = datetime.now(timezone.utc)
    snapshot = {
        "type": "reference_rate_snapshot",
        "purpose": "fallback",
        "base": BASE,
        "as_of": source_date or now.strftime("%Y-%m-%d"),
        "captured_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": SOURCE_NAME,
        "source_endpoint": SOURCE_ENDPOINT,
        "source_terms": SOURCE_TERMS,
        "notice": NOTICE,
        "count": len(rates),
        "rates": dict(sorted(rates.items())),
    }
    text = json.dumps(snapshot, ensure_ascii=False, indent=1)
    DATA_OUT.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_OUT.parent.mkdir(parents=True, exist_ok=True)
    DATA_OUT.write_text(text + "\n")
    PUBLIC_OUT.write_text(text + "\n")
    return snapshot


def main() -> None:
    try:
        captured = fetch_rates()
    except Exception as exc:  # noqa: BLE001 — any failure must preserve existing snapshot
        if DATA_OUT.exists():
            print(f"WARN: capture failed ({exc}). Keeping existing committed snapshot unchanged.")
            existing = json.loads(DATA_OUT.read_text())
            print(f"  existing snapshot as_of={existing.get('as_of')} count={existing.get('count')}")
            return
        sys.exit(f"ERROR: capture failed and no existing snapshot to fall back on: {exc}")

    snap = write_snapshot(captured["rates"], captured["source_date"])
    print(f"Wrote {DATA_OUT.relative_to(REPO)} and {PUBLIC_OUT.relative_to(REPO)}")
    print(f"  as_of={snap['as_of']}  captured_at={snap['captured_at']}  base={snap['base']}  count={snap['count']}")
    print(f"  source={snap['source']}  (attributed, not relicensed)")


if __name__ == "__main__":
    main()
