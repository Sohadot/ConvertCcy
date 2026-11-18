# Precious-Metals Methodology (SEO-A4.4)

Internal governance document. Not user-facing copy.

## 1. Scope and status

Codes: XAU (gold), XAG (silver), XPT (platinum), XPD (palladium) — `precious_metal` in
`data/instrument_classification.json`. **Activation decision: B — reference layer only.**
Metal semantics, provenance and licensing are published; **no metal price is published**,
because no source with publication rights is available.

## 2. Verified facts (registry-cited)

| Fact | Source |
|---|---|
| ISO 4217 names XAU "Gold" (959), XAG "Silver" (961), XPT "Platinum" (962), XPD "Palladium" (964), minor units N.A. | SIX, ISO 4217 Maintenance Agency, list published 2026-09-17 |
| One troy ounce = 3.110 348 E+01 grams (rounded factor) | NIST SP 811, Appendix B.9 |
| LBMA Gold Price administered by IBA; valuation/pricing use requires an IBA usage licence | LBMA |
| LBMA Precious Metals Prices benchmark settings available under licence from IBA | IBA |
| Gold auctions commence at 10:30 and 15:00 London time | LBMA (recorded; not rendered) |

**Unit.** The ISO 4217 list states **no unit** for metal codes. Pages say so, describe the
troy ounce as the customary market convention, and commit to stating the unit exactly as an
activated source defines it. The commonly quoted 31.1034768 g is *not* published (only the
NIST-rounded factor was verified). No gram/kilogram conversions are provided.

## 3. Source discovery and licensing audit

| Source | Metals | Role | License state | Basis |
|---|---|---|---|---|
| LBMA Gold / Silver Price (IBA) | XAU, XAG | benchmark | `not_usable` | usage licence from IBA required; none held |
| LBMA Precious Metals Prices settings (IBA) | XAU, XAG | benchmark | `not_usable` | available under IBA licence only |
| LBMA Platinum / Palladium Price | XPT, XPD | benchmark | `license_unclear` | administrator terms not retrievable (automated access refused) |
| LPPM | XPT, XPD | market body | `license_unclear` | Good Delivery standards body; no published redistribution terms |
| exchangerate-api.com | — | FX provider | `not_usable` (for metals) | publishes no metal values; usable only as the FX leg of a future derived value |

Publishable licence states: `redistribution_permitted`, `attribution_required`. Everything else
blocks rendering (validator + `metal_reference.usable_quote`).

## 4. Architecture decision — Option C

Benchmark provenance (administrator, licence basis, evidence) is recorded per source in
`data/metal_reference_snapshot.json`, separately from any delivery feed. A quote may be stored
only for a source whose licence permits publication. Option A (one vendor for everything)
weakens benchmark provenance; Option B (benchmark-direct per metal family) is blocked by the
IBA licence and unclear LPPM/LME terms. Option C keeps the authority/delivery split and lets a
licensed provider be activated later without changing page semantics.

## 5. Value model

Stored quote fields: `metal_code, metal_name, unit, counter_currency, value (decimal string),
valuation_type (benchmark_reference | market_reference), source_id, source_timestamp,
retrieved_at, license_state, provenance_id, derived=false`. Derived values are computed at build
time, never stored.

| Value type | Rule |
|---|---|
| `benchmark_reference` / `market_reference` | direct quote, shown exactly as published |
| `derived_cross_value` | quote × (target FX / quote-currency FX) from `data/rate_snapshot.json`; both sources and timestamps shown |
| `derived_inverse` | currency → metal quantity = 1 / metal value |
| `derived_metal_ratio` | metal A / metal B, same currency and unit |
| `unavailable` | the current state for every page |

## 6. Freshness, skew and precision

- Freshness relative to the snapshot's `captured_at` (deterministic): `current` ≤ 24 h,
  `recent` ≤ 72 h, `stale` > 72 h (no number shown), plus `historical_snapshot`, `unavailable`.
  Badges: BENCHMARK / MARKET REFERENCE / DERIVED · AS OF YYYY-MM-DD; never LIVE.
- Derivation refused when metal and FX (or two metal) timestamps differ by more than
  `max_timestamp_skew_hours` = 24, on unit mismatch, or when any input is not publishable.
- Precision: direct values keep the source's published decimals; derived values use the A3 rule
  — significant digits = clamp(floor(−log10(Σ relative input uncertainty)), 3, 6).

## 7. Page semantics

Router precedence (`generate.pair_semantic_treatment`): standards_special › historical ›
**precious_metal** › unsupported_specialized / ordinary_fx. So XAU/XTS stays a standards page,
XAU/BGN stays historical, XAU/XDR is a metal page with no value (XDR valuation not activated).

Cohort: 1,340 pairs involve a metal (664 metal→other, 664 other→metal, 12 metal→metal); 16 are
standards-governed, 56 historical-governed, **1,268 precious-metal pages**.

Metal pages: no FX rate state, converter, table rows or rate runtime; reference card (ISO
designation, numeric code, minor units, unit convention, NIST factor, pricing status and IBA
licensing, hub link); titles "XAU to USD Gold Valuation Reference" / "USD to XAU Gold Valuation
Reference" / "XAU / XAG Gold-Silver Ratio Reference" ("Reference Price" only once a value is
active); FAQ (meaning, currency?, unit, determination, direct vs derived, dealer distinction,
timestamp); WebPage + FAQPage + BreadcrumbList, no WebApplication. Robots, canonicals and
sitemap unchanged (class stays `index_with_specialized_reference_role`).

Hubs: "XAU — Gold / ISO 4217 Reference" (switches to "Gold Price & ISO 4217 Reference" only
when a source is activated), with identity, unit, pricing/methodology, benchmark-vs-dealer,
FAQ and all pair links as "metal valuation references".

## 8. Refresh lifecycle (not scheduled)

1. Obtain a licence permitting publication (or a provider with redistribution rights).
2. Add the source and its licence evidence; ingest quotes manually.
3. `python3 scripts/validate_metal_snapshot.py` → `python3 generate.py --precious-metals-only`
   → `python3 scripts/validate_precious_metals.py`.
No automated fetching until rights and reliability are confirmed.

## 9. Future value layers (not implemented)

Gold/silver and gold/platinum ratios, currency-adjusted metal performance, historical benchmark
curves, volatility, premium-versus-benchmark, cross-currency comparison, metals/FX API,
institutional licensing, provenance dataset.
