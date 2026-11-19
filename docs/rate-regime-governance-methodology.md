# Rate-Regime Governance Methodology (SEO-A4.6B)

Internal governance document. Not user-facing copy.

> A provider rate may exist and still represent the wrong monetary regime.
>
> Available provider rate ≠ correct semantic meaning. A number is not presented as "the rate"
> until its regime, authority, freshness, provenance and publication rights are understood.

## 1. Scope

**In scope.** Six active fiat currencies that **have** a value in `data/rate_snapshot.json`.
They are review-flagged in A4.1 (`official_vs_market_rate_review`):

* CUP
* IRR
* MMK
* SYP
* TMT
* VES

**Not in scope:**

* KPW and VED. They have no provider value and are A4.6A, which this sprint leaves unchanged.
* Every higher-precedence layer:
  * historical;
  * standards (XTS/XXX);
  * metals;
  * institutional units.

**Status.** Implemented:

* the governed model;
* a new router treatment, `rate_regime_governed`;
* 1,758 regenerated pair pages and 6 hubs.

**No issuer or market figure is stored or published, because their licences are unclear.**
Provider values are unchanged.

## 2. Source hierarchy

1. Central bank or monetary authority.
2. Ministry or official government source.
3. Official exchange or interbank venue.
4. IMF or another supranational authority.
5. Authoritative market source.
6. Secondary reporting, used only as clearly labelled context. It is never treated as the issuer.

Source tiers in the model:

* `issuer`;
* `official_republisher`;
* `standards_registry`;
* `fx_provider`;
* `licensed_market_data`;
* `unverified_official_copy` (a site that claims to be the issuer but labels itself a copy);
* `market_aggregator`;
* `secondary_press`;
* `secondary_analysis`.

The last three can support only `regime_claims` that name the reporter. They can never support a
value.

## 3. Source audit (2026-11-19)

| Code | Official source (state) | Official regime(s) | Market regime | Provider value (2026-11-18) | Provider likely regime | Licence | Freshness | Decision |
|---|---|---|---|---|---|---|---|---|
| **CUP** | Banco Central de Cuba (bc.gob.cu): connection reset / 503 on every attempt | Several segments, all from secondary sources: a legacy fixed rate for core state transactions (Segment I), a second fixed rate (Segment II) and a floating official rate for households and private business (Segment III) | Informal market (elTOQUE, as reported; elTOQUE refused automated access) | 24.0 | **Segment I**, by exact equality with the reported fixed rate. This is an inference. | Issuer unknown; secondary sources `not_usable` | Fixed segments `fixed_official`; Segment III `official_daily`; informal `market_daily` | `multi_segment_official` · `comparison_only` · availability `official_source_unresolved` |
| **IRR** | CBI (cbi.ir) and Iran Center for Exchange (ice.ir): unreachable | **Not verified** | Tehran free market (Alanchand aggregator, 19 Nov) | 1,816,886.22 | **Unresolved.** About 33% below the free-market rate; no verified official value | Issuer unknown; aggregator `not_usable` | `official_daily` / `market_daily` | `official_source_unresolved` · `suppressed` (no number) · availability `provider_regime_unresolved` |
| **MMK** | Central Bank of Myanmar (forex.cbm.gov.mm page and API): accessible | **Reference Rate** and **Market Trading Rate**, both issuer-published for 2026-11-18. The CBM says the reference rate is "published for reference purpose only" and that "most of the transactions are occurred by market trading rate" | Official market trading rate (issuer) | 2101.07 | **CBM reference rate**: +0.051% on the same date, against −42.594% vs the market trading rate | Issuer `license_unclear` (copyright notice, no reuse terms) | `official_daily` | `official_reference_plus_market_trading` · `comparison_only` · availability `license_unresolved` |
| **SYP** | cb.gov.sy shows a "banks and exchange bulletin" figure in new pounds (19 Nov), but the page labels itself "Demonstration copy — this is not the official government website" | Bulletin figure from an **unverified copy**. Redenomination of 100 old to 1 new pound from 1 January 2026 (Xinhua). The ISO 4217 code is still SYP 760 (List One, 2026-09-17) | Not verified (Enab Baladi returned 403) | 121.8 (new-pound scale) | **Reported official bulletin**: −0.164%, one day apart | `license_unclear` | `official_daily` | `single_official_reference` · `secondary_provider_value` · availability `provider_value_regime_labelled` |
| **TMT** | Central Bank of Turkmenistan (cbt.tm list valid 19 Nov 2026, set "according to the outcome of transactions on Interbank foreign exchange"): accessible | Official rate. The CBT does **not** call it fixed, so it is not modelled as fixed | Parallel rate coexists (BTI 2026, secondary analysis); no current value verified | 3.5 | **CBT official**: 0.000%, one day apart | Issuer `license_unclear`; BTI `not_usable` | `official_daily`; parallel `market_weekly` | `official_reference_plus_parallel_market` · `secondary_provider_value` · availability `provider_value_regime_labelled` |
| **VES** | BCV (bcv.org.ve): TLS chain failure here and 503 for the fetch agent | Official rate as reported by the press: Banca y Negocios, source line "BCV - BVC": prior close and 18/11 values | Not assessed | 916.65 | **Reported BCV official**: 0.000% vs the prior close (−0.123% vs the 18/11 value) | Issuer unknown; press "reproduction requires authorisation" | `official_daily` | `single_official_reference` · `secondary_provider_value` · availability `provider_value_regime_labelled` |

No inaccessible source is treated as confirmation. Numeric closeness is recorded as an **inference**
in `match_basis` ("the provider does not state its source"). It is never treated as proof.

## 4. Provider comparison and tolerances

`rate_regime_governance.comparison_policy` holds the thresholds:

| Parameter | Value | Why |
|---|---|---|
| `official_match_tolerance_pct` | 0.5 | Covers provider rounding and a one-day lag of a daily managed official rate. Every observed regime gap is ≥ 5%, so 0.5% cannot admit a different regime. |
| `material_divergence_pct` | 5.0 | Above this, two regimes are materially different. |
| `max_match_date_gap_days` | 1 | A match also needs the provider and source valuation dates within one day. The only exception is an undated fixed segment. |
| `provider_revalidation_days` | 7 | A provider value is re-trusted only while the FX snapshot is within 7 days of the audited provider date… |
| `provider_drift_tolerance_pct` | 2.0 | …and within 2% of the audited provider value. |

The provider-regime match vocabulary is:

* `provider_matches_official_within_tolerance` (requires an issuer-verified official regime);
* `provider_matches_reported_official`;
* `provider_matches_reported_official_segment`;
* `provider_closer_to_market`;
* `provider_regime_unresolved`;
* `provider_stale_against_official`;
* `provider_conflicts_with_authoritative_source`.

The validator rechecks every claimed match against the recorded comparisons, the regime's
evidence state, the tolerance and the date gap.

**Downgrade (fail-closed, deterministic).** `live_fiat_reference.effective_provider_policy`
applies two rules:

* If the snapshot is stale relative to the audit, a `secondary_provider_value` becomes
  `comparison_only` ("regime match not re-verified").
* If the provider value drifts by more than 2%, `secondary` becomes `comparison_only`, and
  `comparison_only` becomes `suppressed`.

These depend only on committed data, not on wall-clock time.

## 5. Model (extends A4.6A)

The governance data is the `rate_regime_governance` section of
`data/live_fiat_reference_snapshot.json`. It is read by `live_fiat_reference.py`, using
`validate_rate_regime`, `effective_provider_policy` and `pair_regime_view`.

**Scope rule.** A governed code must:

* be an active `fiat_currency` or `restricted_fiat_currency` in A4.1;
* **have** a provider value;
* not be an A4.6A code.

Its `classification_confidence` and `review_flags` must equal the A4.1 values.

**Currency fields:**

* `currency_code`, `display_name`, `issuer_or_authority`, `issuer_source_state`;
* `regime_type`, `availability_status`;
* `regimes[]`;
* `provider` (`provider_value`, `provider_as_of`, `provider_timestamp`, `comparisons[]`,
  `provider_regime_match`, `match_basis`, `confidence`);
* `provider_policy`, `decision_reason`;
* `classification_confidence`, `review_flags`;
* `identity_claims`, `coverage_claims`, `regime_claims`;
* `explanations`, `faq`.

**Regime fields:**

* `regime_id`, `regime_type`, `regime_label`, `authority`, `source_id`;
* `evidence_state` (`issuer_verified` | `secondary_reported` | `unverified_copy` | `unresolved`);
* `valuation_date`, `captured_at`;
* `value` with `value_withheld_reason`, `unit`;
* `freshness_policy`, `license_state`, `activation_state`, `confidence`, `notes`.

**Rules for regime values.** A `value` may be stored only when the source is issuer-verified,
licensed (`redistribution_permitted` or `attribution_required`) and activated. Every value is
currently `null`.

**Mapping to the existing governance axes.**

| Axis | Field |
|---|---|
| Verification | `evidence_state` |
| Confidence | `classification_confidence` (equal to A4.1) and per-regime `confidence` |
| Licence | `license_state` |
| Activation | `activation_state` |
| Availability | `availability_status`, plus one new state, `provider_value_regime_labelled`: the provider value is used with a regime label and no issuer value is published |
| Open issues | `review_flags` (equal to A4.1) |

## 6. Router and cohort

```
standards_special › historical › precious_metal › institutional_unit › live_fiat_coverage
  › rate_regime_governed › ordinary_fx › unsupported_specialized
```

The cohort is derived by the router; there is no URL list. It contains **1,758 pairs**, each
governed currency appearing in 298. Both sides are governed in 30 pairs. Every pair of a governed
code with a higher-precedence code stays in that layer:

* KPW or VED → `live_fiat_coverage`;
* XTS or XXX → standards;
* BGN and other historical codes → historical;
* XAU and other metals → metals;
* XDR and other institutional units → institutional.

**Pair modes** (`pair_regime_view` combines both sides, fail-closed):

| Mode | Rule | Pages |
|---|---|---:|
| `converter` | every governed side is `secondary_provider_value` | 870 |
| `comparison` | some side is `comparison_only` and none is numberless | 590 |
| `none` | some side is `suppressed` or `unresolved` | 298 |

## 7. Page semantics, converter behaviour and structured data

* **Every page** has a "Rate-Regime Governance" card with one block per governed side:
  * cited ISO identity;
  * issuer and the state of its source;
  * regime type;
  * **every regime**, with its evidence state, valuation date and a "value not republished"
    reason;
  * cited regime claims, labelled "Reported (secondary source)" where applicable;
  * provider coverage;
  * the provider snapshot statement, policy and audit basis;
  * scope limits;
  * a link to the hub.

  The Pair Overview is replaced by a "Rate Regimes" overview.
* **Converter** (TMT, SYP and VES pairs):
  * the A3 converter, table and runtime are kept;
  * the title stays "X to Y Converter", with a regime-aware description;
  * the A1 FAQ answer is replaced by a regime-labelled one;
  * structured data is WebPage + WebApplication + BreadcrumbList + FAQPage.
* **Comparison** (CUP and MMK pairs without IRR):
  * the value appears as `PROVIDER SNAPSHOT · COMPARISON ONLY` and is not attributed to any
    official rate;
  * there is no converter, rate runtime or table rows;
  * the title is "X to Y — Exchange-Rate Regime Reference";
  * structured data is WebPage + BreadcrumbList + FAQPage, with no WebApplication.
* **None** (every IRR pair):
  * the page shows "No rate shown" and `PROVIDER REGIME UNRESOLVED`;
  * no provider number (rate, inverse or table) appears anywhere;
  * structured data is WebPage + BreadcrumbList + FAQPage.

A provider value is never described as "the official rate". The wording is "a provider snapshot
that matches / equals …".

## 8. Hubs

The CUP, IRR, MMK, SYP, TMT and VES hubs gain the following sections:

* Identity;
* Rate regimes (every regime and its evidence);
* Provider value and how it is used (policy and decision reason);
* Provenance (each source with its tier and access result);
* Current limitations;
* FAQ (WebPage + FAQPage).

Hubs where conversion is not allowed (CUP, IRR, MMK) become "Exchange-Rate Regime Reference" hubs,
with "Rate-regime references" headings. The TMT, SYP and VES hubs keep their converter title and
headings. All 338 pair links on each hub are kept.

## 9. Indexability, sitemap and canonicals

These are unchanged. All 1,758 pages and the 6 hubs stay `index,follow`, self-canonical and in
`sitemap.xml`, which is byte-identical to baseline. No `noindex` was used to avoid complexity.

## 10. Generation, validation and tests

```
python3 generate.py --rate-regime-governance-only   # 1,758 pages + 6 hubs; a second run changes 0 files
python3 scripts/validate_live_fiat_snapshot.py      # A4.6A model + validate_rate_regime
python3 scripts/validate_rate_regime_governance.py  # cohort, precedence, cards, modes, hubs, parity
python3 -m unittest tests.test_rate_regime_governance
```

`scripts/validate_rate_snapshot.py` recognises reference-only `rate_regime` pages.

## 11. Unresolved issues

* **IRR:** the official mechanisms are unverified, because the issuer and the exchange centre
  were unreachable. A re-audit from a reachable official source is needed before any number
  returns.
* **CUP:** the issuer site was unreachable, and the segment structure rests on secondary sources.
  The floating Segment III value is not verified from the issuer.
* **SYP:**
  * the cb.gov.sy page is self-labelled a demonstration copy, so an authoritative bulletin must
    be found;
  * the old-pound exchange deadline and its current status were not verified;
  * ISO 4217 still uses SYP 760 for the new pound.
* **VES:** the BCV site was not reachable (TLS / 503). The match rests on press attribution, and
  the BCV reuse terms are unknown. A parallel market was not assessed.
* **TMT:** no current parallel-market value was verified.
* **MMK:** the CBM reuse terms are absent. If the CBM grants reuse, a governed multi-regime display
  (reference and market trading) becomes possible.
* **Licences:** every official figure is `license_unclear` or unread. No issuer value can be
  activated until reuse rights are established.
