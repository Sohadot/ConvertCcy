# SEO-A4.6 — Missing-Live-Currency Coverage & Source Governance

Baseline: `main` after merge of PR #136 (`ed6a4f67bd4ce1322e3fee24166c4411d82b1990`).

## Governing principle

A4.6 does **not** reclassify every page without a live rate as a weak or restricted page.

The 4,238 formerly unsupported pages were never one problem. A4.2–A4.5 already split standards codes, historical/legacy instruments, precious metals, and institutional units into their correct semantic layers.

A4.6 is intentionally narrower:

> Preserve the ordinary currency role for genuine live fiat currencies, and fix the missing or ambiguous data coverage through source expansion, rate-regime modelling, availability metadata, and provenance.

No page receives `noindex` merely because exchangerate-api does not cover its code.

## Current A4.6 cohort

Primary review set:

- CUP
- KPW
- VED / VES
- IRR
- MMK
- SYP
- TMT

These are investigated because the current provider coverage, rate regime, official-source availability, or code mapping is incomplete or ambiguous.

## What A4.6 is not

The following remain governed by their already merged layers and must be semantically frozen:

- XTS / XXX → standards reference
- XAU / XAG / XPT / XPD → precious-metals reference
- XDR / CLF / UYW / XUA / XSU → institutional reference
- historical and legacy codes → historical/legacy reference

A4.6 must not collapse any of those back into an “unsupported currency” bucket.

## A4.6 data problem classes

### 1. Missing provider coverage

The currency is real and operational, but the current FX provider does not return a usable quote.

Correct response: discover an authoritative alternative source or an explicitly governed fallback.

### 2. Ambiguous rate regime

A monetary authority may publish more than one meaningful rate: official reference, market-trading, interbank, auction, segment-specific, or another controlled regime.

Correct response: preserve the converter role but label the represented regime explicitly.

### 3. Provider / issuer disagreement

A provider may return a number that materially differs from an issuer or official publication.

Correct response: compare, classify, retain provenance, and fail closed until the represented regime is understood.

### 4. Source unavailable or licensing unclear

A valid currency may have no sufficiently accessible or reusable official source.

Correct response: retain an indexed reference page with transparent availability/provenance state; do not fabricate or silently promote a provider value.

### 5. Code-mapping ambiguity

A code may require special treatment because provider behaviour does not match the current ISO/issuer role.

Correct response: resolve the mapping at the data-governance layer before deciding whether ordinary converter semantics remain valid.

## Source decisions — 2026-11-18

### MMK — VERIFIED MULTI-REGIME OFFICIAL SOURCE

Primary source: Central Bank of Myanmar.

The CBM publishes both a Reference Rate and a Market Trading Rate on the same official surface. On 2026-11-18 the published USD values were:

- Reference Rate: 2,100 MMK per USD
- Market Trading Rate: 3,660 MMK per USD

The CBM also publishes weighted-average interbank and bank-customer transaction rates.

Decision: `official_reference_plus_market_trading`.

A4.6 must not render one unqualified MMK “exchange rate”. The page remains a live-currency reference/converter surface, but every value must identify its regime.

Sources:
- https://forex.cbm.gov.mm/index.php/fxrate
- https://cbm.gov.mm/foreign-exchange-market

### VED / VES — CODE-MAPPING REVIEW

Primary standards source: ISO 4217 Maintenance Agency (SIX), Amendment 170.

The source audit indicates that VED/926 was introduced for internal needs during the 2021 redenomination while VES/928 remained the operative transaction code.

Decision:
- VES remains in the live-fiat coverage path.
- VED remains in A4.6 because the immediate problem is provider/code mapping, not an SEO-indexability decision.
- No VED rate is promoted until its provider semantics and ISO/issuer role are reconciled.

Source:
- https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/amendments/dl_currency_iso_amendment_170.pdf

### CUP — MULTI-SEGMENT REGIME INDICATED; PRIMARY REOPEN REQUIRED

Current discovery indicates multiple official BCC segments rather than one universal CUP rate.

Decision: `primary_source_required_before_activation`.

The page remains a live-currency surface. A4.6 must model the actual rate segment rather than hide the page or collapse all CUP values into one generic quote.

### IRR — OFFICIAL-RATE PUBLICATION INDICATED; PRIMARY REOPEN REQUIRED

Current reporting attributes official tables to the Central Bank of Iran, but the primary publication and reuse terms still need direct verification.

Decision: `primary_source_required_before_activation`.

Any provider value must carry a regime classification before public use.

### SYP — OFFICIAL BULLETIN + MARKET GAP INDICATED; PRIMARY REOPEN REQUIRED

Current discovery indicates a distinct official bulletin and market rate.

Decision: `primary_source_required_before_activation`.

The page remains a live-currency surface; the missing task is source/regime governance.

### TMT — FIXED OFFICIAL USD RELATIONSHIP INDICATED; PRIMARY REOPEN REQUIRED

Current discovery consistently reports an official USD/TMT relationship, but the primary Central Bank publication and reuse terms still require direct verification.

Decision: `primary_source_required_before_activation`.

### KPW — LIVE CURRENCY, OFFICIAL SOURCE UNRESOLVED

KPW remains a genuine national currency in the A4.6 live-currency coverage problem. No sufficiently current primary monetary-authority publication has yet been verified for rate activation.

Decision: `official_source_unresolved`.

The page must not be demoted solely because the present provider cannot supply a trustworthy quote. Instead it should expose source availability, provenance, last verification state, and the unresolved official-vs-market regime.

## Required A4.6 architecture

The live-currency coverage model should carry explicit fields for:

- `currency_code`
- `issuer_or_authority`
- `rate_regime`
- `source_tier`
- `source_url`
- `valuation_date`
- `captured_at`
- `freshness_policy`
- `license_state`
- `official_reference_rate`
- `market_or_trading_rate`
- `provider_value`
- `provider_regime_status`
- `availability_status`
- `confidence`
- `activation_state`
- `decision_reason`

Minimum regime enum candidate:

- `single_official_reference`
- `multi_segment_official`
- `official_reference_plus_market_trading`
- `fixed_official_reference`
- `market_reference_only`
- `official_source_unresolved`
- `provider_regime_unresolved`

Minimum availability states:

- `live_verified`
- `live_caveated`
- `official_source_unavailable`
- `license_unresolved`
- `provider_only_unverified`
- `temporarily_unavailable`

## Page behaviour

For genuine live fiat currencies:

- preserve the live-currency page identity;
- preserve indexability unless a separate SEO analysis proves otherwise;
- show a numeric value only when source, regime, freshness and licensing gates pass;
- when no governed value is available, show a transparent source-availability state rather than “unsupported” as if the currency itself were invalid;
- expose provenance and rate-regime context;
- retain the possibility of later API/dataset use.

This is the foundation for a future ConvertCCY Source Coverage Matrix.

## Fail-closed rules

1. No value renders without verified provenance, identified regime, acceptable freshness, and a publication-permitting licence state.
2. No provider value is described as official unless the issuer/authority confirms that regime.
3. Where multiple regimes exist, every rendered value carries its regime label.
4. Missing provider coverage never implies `noindex`.
5. KPW remains indexable as a real-currency reference even while the numeric value is unavailable.
6. VED remains under code-mapping review; no provider value is promoted until its semantic role is reconciled.
7. Existing A4.2–A4.5 router precedence and public surfaces remain frozen.

## Commercial / knowledge objective

A4.6 is not just a repair layer. It establishes the basis for:

- ConvertCCY Source Coverage Matrix
- source-availability datasets
- official-vs-market rate intelligence
- provenance APIs
- confidence/freshness metadata
- compliance and cross-border intelligence
- AI retrieval over monetary-source status

The long-term object remains the ConvertCCY Reference Graph: currencies and instruments connected to issuers, jurisdictions, legal status, convertibility, reference-rate regimes, sources, historical regimes, and provenance.

## Next implementation step

Implement a dedicated live-fiat coverage snapshot/model, source hierarchy, availability and rate-regime fields, then regenerate only the A4.6 cohort. Add fail-closed validators and semantic-freeze tests proving that A4.2–A4.5 surfaces are byte-identical.
