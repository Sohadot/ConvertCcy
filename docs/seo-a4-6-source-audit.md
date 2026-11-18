# SEO-A4.6 — Restricted & Missing Fiat Source Audit

Baseline: `main` after merge of PR #136 (`ed6a4f67bd4ce1322e3fee24166c4411d82b1990`).

## Scope

Initial review cohort: CUP, KPW, VED, VES, IRR, MMK, SYP, TMT.

A4.6 must distinguish at least four cases instead of treating all review-flagged fiat as ordinary FX:

1. official rate with regime caveat;
2. multiple official/market-trading regimes published by the monetary authority;
3. code whose ISO status is transitional/internal rather than an independently operative currency code;
4. missing or non-verifiable official source, where no numeric value may be promoted.

Provider values are never sufficient by themselves to establish the regime represented by a rate.

## Source decisions — 2026-11-18

### MMK — VERIFIED MULTI-REGIME OFFICIAL SOURCE

Primary source: Central Bank of Myanmar.

The CBM publishes both a Reference Rate and a Market Trading Rate on the same official surface. On 2026-11-18 the published USD values were:

- Reference Rate: 2,100 MMK per USD
- Market Trading Rate: 3,660 MMK per USD

The CBM also publishes weighted-average interbank and bank-customer transaction rates. Therefore MMK must not be represented by one unqualified “exchange rate”. A4.6 needs a regime-labelled model.

Sources:
- https://forex.cbm.gov.mm/index.php/fxrate
- https://cbm.gov.mm/foreign-exchange-market

Decision: `multi_regime_official_reference`.

### VED / VES — VERIFIED ISO CODE-ROLE DISTINCTION

Primary standards source: ISO 4217 Maintenance Agency (SIX), Amendment 170.

VED/926 was introduced for internal needs during the 2021 redenomination and did not replace VES/928 as the official currency code used for future transactions. VES remains the operative transaction code.

Source:
- https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/amendments/dl_currency_iso_amendment_170.pdf

Decision:
- VES: operative fiat code; rate treatment still requires issuer/provider regime audit.
- VED: do not treat as an independent ordinary converter merely because a provider returns a value. Route through a specialized code-status reference.

### CUP — MULTI-SEGMENT REGIME INDICATED; PRIMARY REOPEN REQUIRED

Current discovery surfaces report three official BCC segments, including a variable Segment III. The primary Banco Central de Cuba source/API must be reopened and its reuse terms verified before any value is admitted to a governed snapshot.

Decision: `primary_source_required_before_activation`.

Do not collapse the three regimes into one generic CUP rate.

### IRR — OFFICIAL-RATE PUBLICATION INDICATED; PRIMARY REOPEN REQUIRED

Current reporting attributes a daily official table to the Central Bank of Iran. Direct primary-source retrieval and reuse terms remain to be verified.

Decision: `primary_source_required_before_activation`.

Any provider/market value must not be labelled “the IRR rate” without a regime identifier.

### SYP — OFFICIAL BULLETIN + MARKET GAP INDICATED; PRIMARY REOPEN REQUIRED

Current discovery shows Central Bank of Syria bulletin rates and a distinct market rate. The primary bulletin archive must be reopened directly and the current currency-unit treatment verified before activation.

Decision: `primary_source_required_before_activation`.

### TMT — FIXED OFFICIAL USD RELATIONSHIP INDICATED; PRIMARY REOPEN REQUIRED

Current discovery consistently reports an official USD/TMT value of 3.5, but the Central Bank of Turkmenistan primary publication and reuse terms must be reopened directly.

Decision: `primary_source_required_before_activation`.

### KPW — NO SUFFICIENT CURRENT PRIMARY SOURCE

No current primary DPRK monetary-authority publication has been verified in this audit. Third-party sources show a large divergence between state/official and market rates, but those sources cannot activate a public numeric value under the governance policy.

Decision: `official_source_unresolved`.

No numeric KPW value should be promoted from an ordinary FX provider until the represented regime and provenance are established.

## Required A4.6 architecture

The restricted/missing-fiat layer should carry explicit fields for:

- `rate_regime`
- `issuer_or_authority`
- `source_tier`
- `source_url`
- `valuation_date`
- `captured_at`
- `license_state`
- `official_reference_rate`
- `market_trading_rate`
- `provider_value`
- `provider_regime_status`
- `activation_state`
- `decision_reason`

Minimum regime enum candidate:

- `single_official_reference`
- `multi_segment_official`
- `official_reference_plus_market_trading`
- `fixed_official_reference`
- `official_source_unresolved`
- `code_status_reference_only`

## Fail-closed rules

1. No value renders without a verified source and a publication-permitting licence state.
2. No provider value is described as official unless the issuer/authority confirms the same regime.
3. Where multiple regimes exist, every rendered value must carry its regime label.
4. VED must not silently inherit VES ordinary-converter semantics.
5. KPW remains value-unavailable until an adequate primary source is established.
6. Existing A4.2–A4.5 precedence remains frozen.

## Next implementation step

Implement a dedicated restricted-fiat snapshot/model and router branch, then regenerate only the A4.6 cohort and add fail-closed validators plus a semantic-freeze test against the A4.2–A4.5 controls.
