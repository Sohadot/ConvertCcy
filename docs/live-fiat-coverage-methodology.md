# Live-Fiat Coverage Methodology (SEO-A4.6A)

Internal governance document. Not user-facing copy.

## 1. Scope and status

**Scope:** the residual `unsupported_specialized` cohort left after A4.2–A4.5. This is every pair
with a **KPW** or **VED** side that no higher-precedence layer (standards, historical, metal,
institutional) governs.

| Codes involved | Pages |
|---|---:|
| KPW with a non-VED code | 300 |
| VED with a non-KPW code | 300 |
| KPW ↔ VED | 2 |
| **Total** | **602** |

Two hubs are in scope: `currencies/kpw.html` and `currencies/ved.html`.

**Status:** implemented. **No numeric value is activated** (`activation_state: reference_layer_only`).

**Out of scope (A4.6B, deferred):** CUP, IRR, MMK, SYP, TMT and VES. They have provider values
and still render as `ordinary_fx`. The scope rule in §5 makes it impossible for them to enter
this layer.

Governing principles:

> Missing provider coverage does not invalidate the currency or the page.
>
> A provider value, where one exists elsewhere, is not sufficient evidence of the correct rate regime.

## 2. Source audit (2026-11-19)

| Source | Tier | Access | What it supports |
|---|---|---|---|
| SIX, ISO 4217 List One (published 2026-09-17) | standards registry | accessible | KPW: 408, "North Korean Won", 2 minor units, entity DPRK. VED: 926, "Bolívar Soberano", 2 minor units, Venezuela. VES: 928, also "Bolívar Soberano". |
| SIX, ISO 4217 Amendment 170 (1 October 2021) | standards registry | accessible (PDF text extracted) | VED/926 introduced "for any internal needs during the redenomination process, but is not replacing VES as the official currency code". The Central Bank of Venezuela "will not adopt the new codes in the local system, VES/928 remains in use". VES/928 "remains the valid code … to use in any future transactions". |
| exchangerate-api.com `/v4/latest/USD` | FX provider | accessible | Returns 166 codes, with **no KPW and no VED** (checked 2026-11-19). The committed `data/rate_snapshot.json` (2026-11-18) also has neither code. |
| Banco Central de Venezuela (bcv.org.ve) | issuer | **HTTP 503** on every attempt | Nothing could be read: no rate, no date and no reuse terms. |
| DPRK government portal (naenara.com.kp) | — | **HTTP 503** on every attempt | Not recorded as a source. It could not be confirmed as a monetary-authority publication. |
| Daily NK, 16 April 2026 | secondary press | accessible | Reports an informal-market (jangmadang) won–dollar rate in Pyongyang, from Daily NK's own regular market survey. **Reported indicator only.** The figure is not reproduced. |
| 38 North, H1 2026 economy review | secondary analysis | **HTTP 403** | Not used. Its official-rate figure was seen only in search snippets and could not be verified. |
| Third-party converter sites (search results) | aggregator | not fetched | They show a constant figure around 900 KPW/USD and do not state its regime. They are **not used**, and the figure is not published. |

## 3. KPW decision: official source unresolved

| Question | Finding |
|---|---|
| Identity | Verified (ISO List One). KPW is a real, active currency. |
| Issuer publication of an official rate | Not located or accessible. `issuer_or_authority` is left null rather than naming an unverified publisher. |
| Market rate | An informal-market rate exists according to secondary press (Daily NK). This is a reported indicator only, never a value source. |
| Multiple regimes | Not verified. Only the informal rate was confirmed from a fetched source, so `rate_regime` is `unresolved`. |
| Provider coverage | None (`provider_regime_status: no_provider_value`). |
| Licence | No candidate value source exists, so `license_state` is null. Daily NK is `not_usable` as a value source. |
| A4.1 classification | Unchanged: `restricted_fiat_currency`, confidence `high`, no review flags. `non_convertible` and `market_pricing_expected: false` were **not re-verified** from a primary source in this audit; they stay A4.1 data. See §9. |

`availability_status: official_source_unresolved`, label **OFFICIAL SOURCE UNRESOLVED**.

## 4. VED decision: transitional ISO code, no governed value

| Question | Finding |
|---|---|
| Exact role | A transitional ISO 4217 code (`instrument_role: transitional_iso_code`). Amendment 170 introduced it for internal redenomination needs. It does not replace VES as the official code. |
| Independently operative? | No issuer use is documented. Per Amendment 170, the issuer uses VES/928. |
| Relation to VES | Both codes are listed as "Bolívar Soberano". VES remains the valid code for transactions. **ConvertCCY does not alias VED to VES and applies no numeric VED/VES mapping.** Pages link the VES hub as the operative code, with the sentence "No value is copied from VES to VED". |
| Provider value | None (`no_provider_value`). |
| Rate regime | `not_applicable`. There is no independent VED rate to state. |
| A4.1 classification | Unchanged: `fiat_currency`, confidence `medium`, flags `code_mapping_review` and `official_vs_market_rate_review`. The A4.1 type is broader than the documented code role. See §9. |

`availability_status: no_governed_value_available`, label **TRANSITIONAL ISO CODE**. Pages are
titled "Code-Status Reference".

## 5. Data model and scope rule

The governing data is `data/live_fiat_reference_snapshot.json`, read through
`live_fiat_reference.py`. It is separate from `data/rate_snapshot.json`, which is never modified.

* **Scope rule (fail-closed).** A covered code must be an active `fiat_currency` or
  `restricted_fiat_currency` in `data/instrument_classification.json`, **and** it must have no
  value in `data/rate_snapshot.json`. If the provider starts publishing KPW or VED, the gate fails
  and forces an explicit A4.6B-style regime decision. The value is never adopted silently.
* **No parallel status system.** `classification_confidence` and `review_flags` must equal the
  A4.1 values. `license_state` and `activation_state` use the enums from A4.4 and A4.5. The new
  layer-specific states are `availability_status` and `rate_regime`.
* **Per-code fields:**
  * identity and status: `currency_code`, `display_name`, `issuer_or_authority`,
    `issuer_source_state`, `instrument_role`, `rate_regime`, `availability_status`,
    `decision_label`, `classification_confidence`, `review_flags`;
  * provider and value fields: `provider_value`, `provider_regime_status`,
    `official_reference_value`, `market_reference_value`, `value_source`, `freshness_policy`,
    `license_state`;
  * evidence and wording: `identity_claims`, `coverage_claims`, `reported_indicators`,
    `explanations`, `decision_reason`, `faq`;
  * VED only: `operative_code`.

  The value-related fields **must be null** unless availability is `live_verified` or
  `live_caveated`.
* **Sources.** Each source carries `id`, `title`, `url`, `authority`, `source_tier`, `accessed`,
  `access_state`, `license_state` and `role`. Identity claims must cite an accessible source.
  Secondary press may support only `reported_indicators`, and those may not state a rate figure.
* **Availability states:** `live_verified`, `live_caveated`, `official_source_unresolved`,
  `provider_regime_unresolved`, `license_unresolved`, `no_governed_value_available`,
  `code_role_under_review`. Only the two `live_*` states can carry a value.

## 6. Value activation rules

A number renders only if **all** of the following hold. If any check fails, the page shows the
governed status and no number.

1. The snapshot is `source_activated` and has a `captured_at` timestamp.
2. The code's availability is `live_verified` or `live_caveated`.
3. The value's `rate_regime` is `official_reference` or `market_reference`, and it agrees with the
   code's regime.
4. The source tier fits the regime:
   * official: `issuer` or `official_republisher`;
   * market: `licensed_market_data` or `issuer`;
   * never `secondary_press`, `fx_provider` or `standards_registry`.
5. The source licence is `redistribution_permitted` or `attribution_required`, and it matches the
   licence on the value.
6. The value has a valuation date, source timestamp, retrieval time (not earlier than the source
   timestamp) and a provenance id.
7. Freshness against `captured_at` is current or recent under the value's policy:
   * `official_daily`: current ≤ 24 h, recent ≤ 72 h;
   * `market_weekly`: current ≤ 168 h, recent ≤ 336 h.

Derivation and precision:

* A direct value is shown exactly as published.
* An inverse or an FX cross is labelled **DERIVED**. It shows the source, the regime and both
  dates, and it is refused if the FX timestamp skew exceeds 24 h.
* Precision of a derived value follows the A3 rule.
* A KPW↔VED pair never shows a value, because neither side has provider coverage.

## 7. Page, hub and structured-data treatment

**Pair pages:**

* `data-mode="live_fiat"`, with `data-availability` and `data-rate-regime` on the banner.
* A coverage block per covered side:
  * cited ISO identity;
  * role and issuer;
  * the operative code for VED;
  * availability and rate regime;
  * cited provider coverage;
  * reported indicators;
  * the next activation condition;
  * a link to the hub.
* No converter, no rate runtime (empty `RATE-SCRIPT`), no conversion rows and no A3 "NO RATE" wording.
* The generic market sections are replaced by "Reading a Live-Fiat Coverage Reference".
* Titles:
  * "KPW to USD — North Korean Won Coverage Reference";
  * "USD to VED — Bolívar Soberano Code-Status Reference";
  * "KPW / VED — Live-Fiat Coverage Reference".
* FAQ:
  * the pair question;
  * per-code questions on validity, the missing value and regimes, or for VED the code role and
    its relation to VES;
  * "Does a missing value mean the currency is not real?"
* Visible FAQ equals the FAQPage JSON-LD.

**Structured data:** WebPage + BreadcrumbList + FAQPage, with **no WebApplication**. This holds
even after a future activation, because the page has no conversion tool.

**Hubs:** each is a "Coverage Reference" (KPW) or "Code-Status Reference" (VED) with these sections:

* Identity;
* Status and role;
* Source coverage;
* Availability and rate regime;
* Provenance (sources with tier and access date);
* Current limitations;
* FAQ.

Hubs carry WebPage + FAQPage. All 338 pair links are kept, under "Coverage references" headings.

**Indexability:** unchanged. All 602 pages and both hubs stay `index,follow`, self-canonical and
in `sitemap.xml`. No `noindex` was introduced because a number is missing: the pages are genuine
reference surfaces for real codes.

## 8. Generation, validators and tests

```
python3 generate.py --live-fiat-coverage-only       # 602 pages + 2 hubs; a second run changes 0 files
python3 scripts/validate_live_fiat_snapshot.py      # schema, scope rule, A4.1 agreement, value gate
python3 scripts/validate_live_fiat_coverage.py      # cohort, precedence, pages, hubs, robots/sitemap, parity
python3 -m unittest tests.test_live_fiat_coverage
```

The cohort comes from the router (`generate.pair_semantic_treatment`). Membership is defined by
the snapshot. Nothing uses a slug list. Both gates run in the Governance Gate.

The A3 and A3.1 fallback tests used to rely on KPW and VED pages as their examples. They now build
a synthetic snapshot gap instead (ISK and PEN removed), because no published page uses the generic
unsupported template any more.

## 9. Known limitations and open questions

* **KPW issuer.** No issuer publication was reachable. A future audit should retry the DPRK
  monetary-authority sources and look for a reliable official-rate record. It must also confirm
  or correct A4.1's `non_convertible` and `market_pricing_expected: false`: secondary press
  documents an informal market.
* **VED A4.1 type.** `fiat_currency` is broader than the documented role, a transitional code not
  used by the issuer. A4.1 is unchanged here because a reclassification would alter the policy
  matrix. This is recommended for an A4.1 maintenance pass.
* **VED display name.** `data/currencies.json` uses "Venezuelan Digital Bolívar"; ISO 4217 uses
  "Bolívar Soberano". The legacy name still appears on other hubs and in passage blocks
  (framework debt H).
* **BCV terms.** The BCV site returned HTTP 503 throughout. Its reuse terms are unknown. That
  matters for A4.6B (VES), not for VED.
* **A4.6B is deferred.** CUP, IRR, MMK, SYP, TMT and VES need their own audit: official rate,
  market rate, multiple regimes, provider regime, divergence thresholds, fallback policy and
  public rendering.
