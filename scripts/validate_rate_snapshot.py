#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_rate_snapshot.py — SEO-A3 gate for the reference-rate snapshot and the
static pair-rate regions derived from it.

Snapshot checks (data/rate_snapshot.json, public copy rates/snapshot.json):
  - both copies exist and are byte-identical
  - valid JSON, no duplicate keys, schema (type, base, as_of, captured_at,
    source, count), 3-letter uppercase codes, numeric finite positive rates,
    base rate exactly 1, count == len(rates)
  - every site currency without a rate has an explicit classification in
    generate.UNSUPPORTED_CODE_REASONS (no silent unsupported codes)
  - age is reported; --max-age-days N turns staleness into a failure
    (not on by default so CI never fails purely because time passed)

Static-region checks (pages/*.html):
  - each pair page has exactly one STATIC-RATE, STATIC-RATE-TABLE and
    RATE-SCRIPT marker pair
  - every supported page carries the same baked as_of, and it is not newer
    than the snapshot (the JSON may be refreshed ahead of the HTML)
  - when the baked as_of equals the snapshot as_of, every region is
    byte-identical to what generate.py derives from the snapshot
  - unsupported pages carry no numeric rate (no data-rate, NO RATE badge)
  - assets/js/pair-rate.js exists

FAQ truthfulness checks (SEO-A3.1, pages/*.html):
  - exactly one FAQPage JSON-LD block, valid JSON
  - visible FAQ list and FAQPage JSON-LD carry identical questions/answers
  - FAQ regions equal generate.py's rate-aware FAQ output (support status
    from static_pair_rate, the same snapshot logic as the rate regions)
  - no unsupported page claims "shows the latest available reference exchange rate"

Run: python3 scripts/validate_rate_snapshot.py [--max-age-days N] [--skip-pages]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import generate as g  # noqa: E402

import html as _html

LD_RE = re.compile(r'(?s)<script type="application/ld\+json">\n(.*?)\n</script>')
VIS_FAQ_RE = re.compile(r'(?s)<div class="faq-q"[^>]*>(.*?)</div>\s*<div class="faq-a">(.*?)</div>')
FALSE_RATE_CLAIM = "shows the latest available reference exchange rate"

ASOF_RE = re.compile(r'id="rate-root"[^>]*data-asof="(\d{4}-\d{2}-\d{2})"')


def check_snapshot(today: date, max_age_days):
    errors, info = [], []
    data_p, pub_p = g.RATE_SNAPSHOT_FILE, g.PUBLIC_RATE_SNAPSHOT_FILE
    for p in (data_p, pub_p):
        if not p.exists():
            errors.append(f"missing {p.relative_to(REPO)}")
    if errors:
        return errors, info, None
    if data_p.read_bytes() != pub_p.read_bytes():
        errors.append("data/rate_snapshot.json and rates/snapshot.json differ (must be byte-identical)")
    try:
        snap = g.parse_rate_snapshot(data_p.read_text(encoding="utf-8"))
    except g.RateSnapshotError as exc:
        return errors + [str(exc)], info, None
    errs = g.validate_rate_snapshot_data(snap)
    errors.extend(errs)
    if errs:
        return errors, info, None

    currencies = json.loads((REPO / "data" / "currencies.json").read_text(encoding="utf-8"))["currencies"]
    codes = sorted(c.upper() for c in currencies)
    missing = [c for c in codes if c not in snap["rates"]]
    unclassified = [c for c in missing if c not in g.UNSUPPORTED_CODE_REASONS]
    if unclassified:
        errors.append(f"site currencies without a snapshot rate and without a classification: {unclassified}")
    n, m = len(codes), len(missing)
    unsupported_pairs = 2 * m * (n - m) + m * (m - 1)
    age = (today - datetime.strptime(snap["as_of"], "%Y-%m-%d").date()).days
    info.append(
        f"snapshot as_of={snap['as_of']} age={age}d source={snap['source']} rates={len(snap['rates'])} "
        f"site_currencies={n} supported_codes={n - m} unsupported_codes={m} {missing}"
    )
    info.append(f"pairs supported={n * (n - 1) - unsupported_pairs} unsupported={unsupported_pairs}")
    if age < 0:
        errors.append(f"snapshot as_of {snap['as_of']} is in the future")
    if max_age_days is not None and age > max_age_days:
        errors.append(f"snapshot is {age} days old (> --max-age-days {max_age_days})")
    return errors, info, snap


def check_pages(snap):
    errors, info = [], []
    currencies = g.load_currencies()
    profiles = g.load_pair_profiles()
    content = g.load_content_blocks()
    baked = {}
    mismatched = 0
    faq = {"malformed_jsonld": 0, "faqpage_not_1": 0, "visible_jsonld_mismatch": 0,
           "unsupported_false_claim": 0, "faq_region_drift": 0}
    for profile in profiles.values():
        a, b = profile["from_code"], profile["to_code"]
        if a == b or a not in currencies or b not in currencies:
            continue
        path = g.PAGES_DIR / f'{profile["pair_slug"]}.html'
        if not path.exists():
            errors.append(f"missing pair page {path.name}")
            continue
        page = path.read_text(encoding="utf-8")
        for s, e, label in ((g.STATIC_RATE_START, g.STATIC_RATE_END, "STATIC-RATE"),
                            (g.STATIC_TABLE_START, g.STATIC_TABLE_END, "STATIC-RATE-TABLE"),
                            (g.RATE_SCRIPT_START, g.RATE_SCRIPT_END, "RATE-SCRIPT")):
            if page.count(s) != 1 or page.count(e) != 1:
                errors.append(f"{path.name}: {label} markers {page.count(s)}/{page.count(e)}")
        treatment = g.pair_rate_treatment(a, b, snap)   # policy first (SEO-A4.2), then coverage
        supported = treatment == "snapshot"
        faq_pages = []
        for blk in LD_RE.findall(page):
            try:
                obj = json.loads(blk)
            except ValueError:
                faq["malformed_jsonld"] += 1
                continue
            if isinstance(obj, dict) and obj.get("@type") == "FAQPage":
                faq_pages.append(obj)
        if len(faq_pages) != 1:
            faq["faqpage_not_1"] += 1
        else:
            ld = [(e["name"], e["acceptedAnswer"]["text"]) for e in faq_pages[0]["mainEntity"]]
            vis = [(_html.unescape(q), _html.unescape(x)) for q, x in VIS_FAQ_RE.findall(page)]
            if ld != vis:
                faq["visible_jsonld_mismatch"] += 1
        if not supported and FALSE_RATE_CLAIM in page:
            faq["unsupported_false_claim"] += 1
        tokens = g.make_pair_tokens(profile, currencies)
        items = g.rate_aware_faq_items(g.build_faq_items(profile, content, tokens), tokens, snap, currencies)
        try:
            if g.replace_faq_regions(page, items) != page:
                faq["faq_region_drift"] += 1
        except ValueError as exc:
            errors.append(f"{path.name}: {exc}")
        m = ASOF_RE.search(page)
        if treatment == "historical":
            # historical/legacy pages: never a current-rate state (detail in validate_historical_instruments.py)
            if 'data-mode="historical"' not in page or "data-rate=" in page or g.RATE_SCRIPT_SRC in page:
                errors.append(f"{path.name}: historical page carries a current-rate state or the rate runtime")
        elif treatment == "precious_metal":
            # precious-metal pages: never an FX rate state (detail in validate_precious_metals.py)
            if 'data-mode="metal"' not in page or "data-rate=" in page or g.RATE_SCRIPT_SRC in page:
                errors.append(f"{path.name}: metal page carries an FX rate state or the rate runtime")
        elif treatment == "institutional_unit":
            # institutional-unit pages: never an FX rate state (detail in validate_institutional_units.py)
            if 'data-mode="institutional"' not in page or "data-rate=" in page or g.RATE_SCRIPT_SRC in page:
                errors.append(f"{path.name}: institutional page carries an FX rate state or the rate runtime")
        elif treatment == "live_fiat_coverage":
            # live-fiat coverage pages (SEO-A4.6A): never an FX rate state (detail in validate_live_fiat_coverage.py)
            if 'data-mode="live_fiat"' not in page or "data-rate=" in page or g.RATE_SCRIPT_SRC in page:
                errors.append(f"{path.name}: live-fiat page carries an FX rate state or the rate runtime")
        elif treatment == "standards_special":
            # ISO 4217 test/no-currency pages: never a rate state (detail in validate_standards_special_codes.py)
            if 'data-mode="standards"' not in page or "data-rate=" in page or g.RATE_SCRIPT_SRC in page:
                errors.append(f"{path.name}: standards page carries a rate state or the rate runtime")
        elif 'data-mode="unsupported"' in page:
            if "data-rate=" in page or 'data-mode="snapshot"' in page:
                errors.append(f"{path.name}: unsupported page carries a numeric rate")
        elif m:
            baked.setdefault(m.group(1), 0)
            baked[m.group(1)] += 1
        else:
            errors.append(f"{path.name}: no static-rate root")
            continue
        if m and m.group(1) == snap["as_of"]:
            expected = g.replace_static_rate_regions(page, profile, g.make_pair_tokens(profile, currencies), snap)
            if expected != page:
                mismatched += 1
        elif not m and supported:
            # page baked from an older snapshot that lacked a now-supported code
            info.append(f"{path.name}: unsupported in HTML but supported by the current snapshot")
    if len(baked) > 1:
        errors.append(f"pair pages carry mixed baked as_of dates: {baked}")
    for d in baked:
        if d > snap["as_of"]:
            errors.append(f"baked as_of {d} is newer than snapshot as_of {snap['as_of']}")
    if mismatched:
        errors.append(f"{mismatched} pair pages' static-rate regions differ from the snapshot derivation "
                      f"(run: python3 generate.py --static-rates-only)")
    if not (REPO / g.RATE_SCRIPT_SRC.lstrip("/")).exists():
        errors.append(f"missing {g.RATE_SCRIPT_SRC}")
    for k, v in faq.items():
        if v:
            errors.append(f"FAQ: {k} = {v}" + (" (run: python3 generate.py --faq-only)" if k == "faq_region_drift" else ""))
    info.append(f"baked as_of dates: {baked or 'none'}")
    info.append(f"FAQ checks: {faq}")
    return errors, info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-age-days", type=int, default=None)
    ap.add_argument("--skip-pages", action="store_true")
    ap.add_argument("--today", default=None, help="YYYY-MM-DD (testing)")
    args = ap.parse_args()
    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else datetime.now(timezone.utc).date()

    errors, info, snap = check_snapshot(today, args.max_age_days)
    if snap is not None and not args.skip_pages:
        e2, i2 = check_pages(snap)
        errors += e2
        info += i2
    for line in info:
        print(line)
    if errors:
        print("FAIL")
        for e in errors[:50]:
            print(f"  - {e}")
        return 1
    print("PASS: rate snapshot and static pair-rate regions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
