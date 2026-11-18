# Instrument Classification & Treatment Policy (SEO-A4.1)

Internal governance document. Not user-facing copy.

## 1. Authority and data model

| Layer | File | Role |
|---|---|---|
| Identity | `data/currencies.json` | Names, symbols, numeric codes, aliases. Its `instrument_type` is a **legacy compatibility label** only. |
| Classification + policy (authoritative) | `data/instrument_classification.json` | One record per code (170) plus one treatment policy per instrument type. |
| Access layer | `instrument_policy.py` | `resolve(code)`, `resolve_pair(a, b)`, `is_ordinary_converter(code)`, `build_matrix()`. Generators must use this, never the raw file. |
| Derived | `data/generated/instrument_policy_matrix.json` | Built by `python3 instrument_policy.py --write-matrix`. Never hand-edited. |
| Gate | `scripts/validate_instrument_classification.py` | Fail-closed validation + matrix drift check (Governance Gate). |

Any departure from `legacy_type_mapping` (old label → new type) must carry a
`reclassification_reason`. Name data is not duplicated: names come from the identity layer.

## 2. Taxonomy (exactly one primary type per code)

| Type | Rule | Codes |
|---|---|---|
| `fiat_currency` | Circulating legal tender from a national or currency-union authority | 150 (incl. EUR, XAF, XOF, XCD, XPF via `jurisdiction_scope`) |
| `restricted_fiat_currency` | Legal tender that is officially non-convertible / has no accessible international quotation | CUP, KPW |
| `precious_metal` | ISO metal code per troy ounce; no issuer | XAU, XAG, XPT, XPD |
| `unit_of_account` | Non-circulating accounting/indexation unit of a national authority | CLF, UYW |
| `regional_unit` | Non-circulating unit defined by a regional/multilateral body | XSU, XUA |
| `special_instrument` | Supranational reserve asset that is also a unit of account | XDR |
| `historical_currency` | Withdrawn from legal tender, replaced by a successor | ANG, BGN, CUC, HRK, ZWL |
| `legacy_transition` | Superseded in practice (redenomination/dollarization), possibly still de jure listed | SLL, SVC |
| `test_code` | ISO 4217 testing code | XTS |
| `no_currency` | ISO 4217 "no currency involved" | XXX |

Non-overlap rules: circulation + legal tender separate fiat from units; issuer type separates
`unit_of_account` (national) / `regional_unit` (regional body) / `special_instrument` (IMF);
`instrument_status` separates `historical_currency` (withdrawn) from `legacy_transition`
(superseded). Validator enforces each combination.

Secondary attributes: `instrument_status`, `circulation_status`, `legal_tender_status`,
`convertibility_status` (`not_assessed` for ordinary fiat — no pseudo-precision),
`issuer_type`, `issuer_name` (null unless well established), `jurisdiction_scope`,
`market_pricing_expected`, `reference_rate_expected`, `active`, `historical`,
`classification_confidence`, `evidence`, `review_flags`, `successor_code`,
`documented_conversion` (verification state is explicit; historical conversions are promoted to `verified` only after an authoritative-source check).

## 3. Policy matrix (per type)

| Type | page_role | converter | rate_policy | hub index | pair index |
|---|---|---|---|---|---|
| fiat_currency | fx_converter_reference | standard | live_plus_snapshot | index | index |
| restricted_fiat_currency | restricted_currency_reference | caveated | official_reference_with_regime_caveat | specialized | specialized |
| precious_metal | precious_metal_reference | valuation_only | dedicated_metal_benchmark_required | specialized | specialized |
| unit_of_account | institutional_unit_dossier | valuation_only | issuer_published_valuation | specialized | needs_further_evidence |
| regional_unit | institutional_unit_dossier | valuation_only | issuer_published_valuation | specialized | needs_further_evidence |
| special_instrument | supranational_instrument_dossier | valuation_only | issuer_published_valuation | specialized | specialized |
| historical_currency | historical_currency_dossier | archival_only | archival_fixed_conversion_only | specialized | needs_further_evidence |
| legacy_transition | legacy_currency_dossier | archival_only | fixed_parity_or_successor_reference | specialized | needs_further_evidence |
| test_code | iso_standards_reference | none | no_rate | specialized | candidate_for_consolidation |
| no_currency | iso_semantics_reference | none | no_rate | specialized | candidate_for_consolidation |

"specialized" = `index_with_specialized_reference_role`. A pair takes the **most restrictive**
side (`index` < specialized < `needs_further_evidence` < `candidate_for_consolidation` <
`candidate_for_noindex`). No class defaults to `candidate_for_noindex`; this sprint changes
no robots/canonical tags.

Pair cohorts (28,730): index 22,350 · specialized 2,142 · needs_further_evidence 3,564 ·
candidate_for_consolidation 674 (every XTS/XXX pair).

**XTS / XXX:** pair pages carry no information beyond the code's own semantics; a single ISO
reference page per code is the stronger canonical target. Recommended: consolidation (A4.2),
decided and executed in that sprint, not here.

## 4. Source policy and verification registry

| Type | Acceptable source classes |
|---|---|
| fiat | central bank · official government institution · established FX data provider |
| restricted fiat | central bank · official government institution (official vs market labelled) |
| precious metals | bullion benchmark administrator · established metals data provider |
| units / regional units | issuing institution · treaty body · official methodology publication |
| special instrument (XDR) | issuing institution · international financial institution record |
| historical / legacy | central bank (archive) · official government archive · IFI record |
| test / no-currency | ISO 4217 maintenance agency |

Authoritative URLs and the exact claims they support are recorded in the `verification_sources` registry inside `data/instrument_classification.json`. This keeps the policy machine-readable while preserving claim-level provenance.

## 5. Commercial role (strategic metadata only)

fiat: FX reference API, historical-rate dataset, cross-border intelligence, institutional licensing ·
restricted: source-availability dataset, compliance API, cross-border intelligence ·
metals: metals pricing intelligence, FX API, analytical dataset ·
units/XDR: institutional units reference, analytical dataset ·
historical/legacy: historical-currency dataset, provenance dataset, AI retrieval corpus ·
test/no-currency: standards reference API, AI retrieval corpus.

## 6. Current conformance (from the derived matrix)

| Gap | Codes | Meaning |
|---|---|---|
| rate_shown_contrary_to_policy | ANG, BGN, HRK, SLL, ZWL | Provider quotes a withdrawn/superseded code; pages show a market-style rate. ZWL's quote equals ZWG's (alias). |
| rate_source_missing | KPW, VED, UYW, XSU, XUA, XAU, XAG, XPT, XPD | Rate expected under policy, no acceptable source yet. |
| rate_shown_without_regime_caveat | CUP | Provider value (24.0) matches the 2021 parity; regime not stated. |
| provider_rate_pending_issuer_source | CLF, XDR | Provider quotes; issuer valuation is the governing source. |

Review flags on fiat (no reclassification without evidence): IRR, LBP, SYP, MMK, TMT, VES, VED
(`official_vs_market_rate_review`; VES/VED also `code_mapping_review`).

## 7. Source-verification pass and remaining uncertainties

The following facts are now anchored to authoritative sources in the repository registry:
- ANG → XCG: XCG introduction, 1:1 conversion, and end of ANG cash/legal-tender use — Centrale Bank van Curaçao en Sint Maarten.
- BGN → EUR: euro adoption and fixed EUR 1 = BGN 1.95583 conversion — European Central Bank.
- HRK → EUR: fixed EUR 1 = HRK 7.53450 conversion — European Central Bank.
- SLL → SLE: redenomination at 1,000 old leones = 1 new leone — Bank of Sierra Leone.
- ZWL → ZWG: replacement code and transition — Reserve Bank of Zimbabwe.
- CUC → CUP: withdrawal under monetary unification and official CUC 1 = CUP 24 conversion — Cuban official legal/monetary-ordering sources.
- SVC/USD: official 8.75 colones per USD quotation — Banco Central de Reserva de El Salvador.
- UYW: issuer/publication status — Banco Central del Uruguay.
- XUA: AfDB Unit of Account and SDR equivalence — African Development Bank.
- XDR: SDR valuation methodology — International Monetary Fund.
- CLF: UF calculation methodology — Chilean official financial/central-bank source.
- KPW: national-currency identity and attributed institutional rate series — United Nations Data.

Medium-confidence classifications now remaining (10): CUP, IRR, LBP, MMK, SLL, SYP, TMT, VED, VES, XSU.
SLL remains medium because the exact old-note legal-tender end state still needs a dated issuer notice even though the 1,000:1 redenomination is verified.
CUP remains medium because the 2021 official 24 CUP/USD unification rate is verified, while the current applicable exchange-rate regime still requires dedicated A4.6 treatment.
XCG and ZWG are not yet in the site's currency set.

## 8. Next implementation sequence

1. **A4.2 Historical & legacy rate correction** — stop presenting market-style rates for ANG,
   BGN, HRK, SLL, ZWL (live user-facing misstatement today, 1,670 pair pages), use the now-verified
   conversion facts, and decide successor additions (XCG, ZWG).
2. **A4.3 Test / no-currency standards reference** — XTS/XXX reference pages and the
   consolidation decision for their 674 pair pages.
3. **A4.4 Precious metals reference layer** — benchmark source, troy-ounce semantics.
4. **A4.5 Institutional units layer** — XDR, CLF, UYW, XSU, XUA from issuer valuations.
5. **A4.6 Restricted & missing fiat sources** — KPW, VED, CUP regime caveat, review-flagged
   fiat (IRR, LBP, SYP, MMK, TMT, VES).

Generators should be migrated to `instrument_policy.resolve()` in the sprint that first
changes their output; the legacy `instrument_type` label can then be retired.
