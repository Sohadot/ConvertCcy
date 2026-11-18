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
| provider_value_present_but_policy_disallows_live_use | ANG, BGN, HRK, SLL, ZWL | Provider still quotes a withdrawn/superseded code; since A4.2 pages render the historical reference instead (was `rate_shown_contrary_to_policy`). ZWL's quote equals ZWG's (alias). |
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
- LBP: official USD/LBP series at 89,500 in 2026, matching the current ConvertCCY snapshot — Banque du Liban.

Medium-confidence classifications now remaining (9): CUP, IRR, MMK, SLL, SYP, TMT, VED, VES, XSU.
SLL remains medium because the exact old-note legal-tender end state still needs a dated issuer notice even though the 1,000:1 redenomination is verified.
CUP remains medium because the 2021 official 24 CUP/USD unification rate is verified, while the current applicable exchange-rate regime still requires dedicated A4.6 treatment.
XCG and ZWG are not yet in the site's currency set.

## 8. A4.2 — Historical & legacy rendering policy (implemented)

**Branching.** `generate.pair_rate_treatment()` asks the policy layer first: a pair whose
`resolve_pair()` converter behaviour is `archival_only` (any `historical_currency` /
`legacy_transition` side, unless XTS/XXX governs) is rendered as a historical reference.
The legacy `currencies.json` label plays no part (XTS/XXX FAQ detection also moved to the
resolver). Cohort: 7 codes (ANG, BGN, CUC, HRK, SLL, SVC, ZWL) → 2,324 pair pages, of which
2,296 get historical treatment and 28 stay governed by XTS/XXX. Before A4.2, 1,540 of them
showed a SNAPSHOT/LIVE rate and 756 showed "no rate".

**Rendering rules.** Historical pages carry `data-mode="historical"`, no `data-rate`, no
LIVE/SNAPSHOT state, no converter inputs, no current-rate table, no `pair-rate.js`, no
WebApplication schema node, and a status-aware FAQ (visible list and FAQPage JSON-LD from one
item list). Every figure sits in a labelled element: `data-value-type` (a verified fixed
relationship) or `data-claim` (a registry-cited claim).

**Value types.**

| Type | When | Examples |
|---|---|---|
| `historical_fixed_conversion` | historical code ↔ successor, verified conversion | EUR 1 = BGN 1.95583 · EUR 1 = HRK 7.53450 · CUC 1 = CUP 24 |
| `redenomination` | legacy code ↔ successor, verified ratio | SLE 1 = SLL 1,000 |
| `fixed_legal_parity` | legacy code with an official fixed quotation | USD 1 = SVC 8.75 |
| `archival_unavailable` | every other pair (2,286 pages) | BGN → USD, ZWL → USD, ANG → USD |

Figures are shown only in the official direction (no derived inverses). ANG 1 = XCG 1 is shown
as a fact on ANG pages; there is no ANG↔XCG pair page because XCG is not in the site set.

**Verified facts only.** `historical_reference` in `data/instrument_classification.json` is the
only renderable source. Each claim and fixed conversion cites `verification_sources` by key,
index and the exact `supports` string; every date or number in a claim must occur in the cited
statements; a fixed conversion requires a `verified` `documented_conversion` with matching
figures. Status and successor come from the instrument record. Not rendered because not
verified: the HRK changeover date, the SLL legal-tender end date, any ZWL→ZWG conversion figure.

**Provider observations are preserved, not deleted.** The raw snapshot still holds ANG, BGN,
HRK, SLL, ZWL. Pages state that the provider publishes a value and that ConvertCCY does not
present it as a current market rate. "Derived from the successor" is stated only when the value
matches the verified conversion applied to the successor rate (ANG, BGN, HRK, SLL); "alias" only
when the value equals the successor's with no verified one-to-one conversion (ZWL = ZWG).

**Successor-derived values — decision: not implemented (architecture A).** A present-day
"successor-derived reference" (e.g. BGN → EUR → USD) is technically easy but reads as a BGN
market rate, adds the snapshot-bake churn to 2,286 more pages, and is only meaningful where the
old currency is still exchangeable (verified only for BGN banknotes at the Bulgarian National
Bank). Archival pages instead link the successor pair (e.g. BGN → USD links EUR → USD). If added
later it must be a distinct value type, outside the LIVE/SNAPSHOT lifecycle, restricted to
codes with verified exchangeability.

**XCG / ZWG — decision: ADD IN SEPARATE MIGRATION.** Both have verified issuers (CBCS, RBZ)
and provider quotes, and both would complete successor chains. But each breaks the 170-code
invariant (validator, graph gate, tests), adds 340 pair pages, needs pair profiles,
classification (ZWG regime review) and sitemap/hub additions. Not required for A4.2 correctness.

**Indexability — decision: unchanged.** Type-level `needs_further_evidence` stays for
historical and legacy pairs. The 10 successor pairs now carry verified reference value and are
candidates for `index_with_specialized_reference_role`, but the policy layer has no per-pair
override and the 2,286 archival pages still carry the generic templated pair prose.

**Gates.** `scripts/validate_historical_instruments.py` (Governance Gate) fails closed on any
current-rate marker, unlabelled figure, unverified value, snapshot-derived value leak, FAQ or
schema mismatch, WebApplication node, or region drift. `validate_rate_snapshot.py` takes
support status from `pair_rate_treatment()`. Targeted rebuild:
`python3 generate.py --historical-instruments-only` (idempotent).

**A4.2.1 — metadata & page semantics.** One resolver, `generate.pair_metadata()`, feeds
`<title>`, meta description, og/twitter copies and the WebPage JSON-LD name/description
(ordinary pairs: the pre-existing strings, byte-for-byte). Historical pairs are titled by value
type — "Historical Fixed Conversion", "Redenomination Reference", "Fixed Parity Reference" or
"Historical/Legacy Currency Reference" — and described as references with "No current market
rate is presented". `apply_historical_semantics()` (shared by the full build and
`--historical-instruments-only`) also replaces the subtitle, the Pair Overview (status,
successor, verified relationship, page purpose), removes the market-context line of the passage
section, replaces the three market-education sections with one "Reading a Historical Currency
Reference" section, and renames the table section by value type ("Historical Conversion Status"
when no fixed relationship applies). H1 is unchanged. Historical/legacy hubs are titled
"… Historical/Legacy Currency Reference", describe status and successor, and label their pair
lists as archived references. The historical gate checks every one of these surfaces against
the resolver and against the exact ordinary template strings for the pair.

## 9. Next implementation sequence

1. **A4.3 Test / no-currency standards reference** — XTS/XXX reference pages and the
   consolidation decision for their 674 pair pages.
2. **A4.4 Precious metals reference layer** — benchmark source, troy-ounce semantics.
3. **A4.5 Institutional units layer** — XDR, CLF, UYW, XSU, XUA from issuer valuations.
4. **A4.6 Restricted & missing fiat sources** — KPW, VED, CUP regime caveat, review-flagged
   fiat (IRR, SYP, MMK, TMT, VES).
5. **Successor migration (XCG, ZWG)** and a **per-pair indexability override** for the 10
   successor pairs.

The legacy `instrument_type` label in `currencies.json` is now used only for the generic hub
identity line of non-historical codes; it can be retired once A4.3–A4.5 move those to the
resolver.
