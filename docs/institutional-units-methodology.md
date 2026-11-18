# Institutional Units Methodology (SEO-A4.5)

Scope: **XDR** (IMF Special Drawing Right), **CLF** (Chile Unidad de Fomento), **UYW** (Uruguay
Unidad Previsional), **XUA** (African Development Bank Unit of Account) and **XSU** (SUCRE).
These are institutional units. They do not circulate, are not legal tender and are not priced by
an FX market. Their governing value, where one exists, is the one the issuer publishes. ConvertCCY
renders them as institutional references, never as currency converters.

## 1. Institutional taxonomy

The A4.1 taxonomy (`data/instrument_classification.json`) is authoritative. The generator asks
`instrument_policy.resolve(code)` and never hard-codes a code list.

| Code | A4.1 type | Pair role | Valuation type | Issuer / publisher |
|---|---|---|---|---|
| XDR | `special_instrument` | `supranational_valuation_reference` | `basket_valuation` | International Monetary Fund |
| CLF | `unit_of_account` | `indexed_unit_reference` | `indexed_unit_value` | Banco Central de Chile |
| UYW | `unit_of_account` | `indexed_unit_reference` | `indexed_unit_value` | Instituto Nacional de Estadística (Uruguay) |
| XUA | `regional_unit` | `institutional_valuation_reference` | `institutional_parity` (relationship only) | African Development Bank |
| XSU | `regional_unit` | `institutional_valuation_reference` | `unavailable` | unresolved |

When both sides of a pair are institutional units, the pair role is `institutional_relative_reference`.

## 2. Source hierarchy

1. **Issuer or statutory publisher**: the IMF, Banco Central de Chile, INE Uruguay and the AfDB.
2. **Official methodology or republication by a government body**: the CMF API documentation for
   the UF methodology, and SII daily UF values.
3. **ISO 4217 maintenance agency (SIX)**: identity only, meaning designation, entity and numeric code.
4. **Secondary press**: these entries carry `source_tier: "secondary_press"` in the registry. They
   may support only claims worded as reports, in `reported_indicators`. They never support issuer
   statements. The policy validator enforces both rules.

Generic currency websites are never a source for institutional definitions. The FX provider
values for XDR and CLF stay in `data/rate_snapshot.json`, which is unmodified, and are classified
in `provider_values`. They are never rendered.

## 3. Source audit (2026-11-18)

| Code | Verified (primary) | Not obtainable / unresolved |
|---|---|---|
| XDR | IMF SDR Valuation page: basket summation at market rates, daily except IMF holidays, Bank of England mid-market rates, six-significant-digit rounding. IMF factsheet: reserve asset, "not a currency", five-currency basket. IMF Copyright and Usage: attribution required; **commercial reuse of IMF Data requires permission**. | IMF permission for commercial reuse (not requested). |
| CLF | CMF API documentation: UF calculated monthly by Banco Central de Chile, CPI geometric-rate adjustment, period runs from day 10 to day 9. SII publishes daily UF values. | Reuse terms of BCCh, SII and CMF data. The BCCh terms page is behind a bot wall. |
| UYW | INE bulletin quoting Ley N° 19.608: creation, initial value, daily IMSN indexation, **INE administers and publishes the daily value** (art. 3). The INE value series is live. | INE reuse terms. The BCU pages returned HTTP 503. |
| XUA | A4.1 registry entries (AfDB): net assets in Units of Account; UA equivalent to the IMF SDR; UA tracks SDR composition. Search-index copies of the AfDB pages carry the same wording. | Direct fetches of afdb.org were refused (HTTP 403). No AfDB methodology statement for a standing numeric parity was found. |
| XSU | ISO 4217 still lists XSU under the SUCRE system. | Any current issuer publication. The former official domain redirects to an unrelated site, and the BCV and BCB pages were unavailable or silent. Press reports citing Banco Central del Ecuador data describe no operations since 2020 and Ecuador's treaty denunciation. |

## 4. Valuation-source decisions

| Code | Decision (A/B/C) | Label |
|---|---|---|
| XDR | B — issuer methodology only | **IMF REFERENCE ONLY** |
| CLF | B — issuer methodology only | **METHODOLOGY ONLY** |
| UYW | B — issuer methodology only | **REFERENCE ONLY** |
| XUA | C — reference layer only | **SDR-RELATIONSHIP REFERENCE ONLY** |
| XSU | C — reference layer only | **STATUS UNRESOLVED** |

No numeric institutional value is published. The reason is licensing, not methodology. For CLF,
UYW and XDR the methodology is fully verified and an official daily value exists, but each source
is classified `license_unclear`.

## 5. Licensing gate

`license_state` is one of `redistribution_permitted`, `attribution_required`, `derived_use_only`,
`display_only`, `license_unclear` and `not_usable`. Only the first two allow a value to render, and
a publishable licence must cite resolvable `license_evidence`. All three current sources are
`license_unclear`.

## 6. Value model (`institutional_reference.py`)

`data/institutional_reference_snapshot.json` is the only numeric source. It is separate from the FX
and metal snapshots. A stored value has these fields: `instrument_code`, `instrument_name`,
`instrument_type`, `issuer`, `valuation_type`, `value` (a decimal string), `denomination_currency`,
`valuation_date`, `source_timestamp`, `retrieved_at`, `methodology_id`, `source_id`,
`license_state`, `freshness_state`, `derived` (always false), `derivation_method` (always null)
and `provenance_id`.

Value types:

* **Direct.** `issuer_published_valuation`, `indexed_unit_value` or `basket_valuation`: one unit in
  its own denomination currency (XDR→USD, CLF→CLP, UYW→UYU).
* **`derived_reference_value`.** The inverse of a direct value, or the direct value times a
  governed FX cross. It is computed at render time and never stored. It is labelled
  **DERIVED FROM <ISSUER> VALUATION — not a direct issuer quote** and shows the issuer source, the
  valuation date, the methodology, the FX source, the FX timestamp and the derivation method.
* **`institutional_parity`.** A relationship type only. XUA's issuer-stated equivalence to the SDR
  is rendered as a cited statement and never as a perpetual numeric identity.
* **`unavailable`.** The current state for every pair.

## 7. Freshness and timestamp skew

Cadences are issuer-specific (`freshness_policies`). No universal FX TTL is applied:

* `imf_business_daily`: current ≤ 96 h, recent ≤ 168 h, FX skew ≤ 24 h. The windows cover weekends and IMF holidays.
* `uf_daily_by_monthly_period` and `up_daily_by_monthly_bulletin`: each calendar day has its own
  official value, published in advance. Only the value for the build day is current (≤ 24 h,
  recent ≤ 48 h). Advance-dated values are accepted up to one month ahead, and FX skew is ≤ 24 h.
* `follows_sdr` (XUA) and `unresolved` (XSU) publish no value of their own and take no age limits.

A `captured_at` timestamp may exist only when values exist, so no timestamp is fabricated. A
value whose `retrieved_at` precedes its `source_timestamp` is rejected.

## 8. Precision

A direct value is shown exactly at the issuer's published precision, with grouping only. The IMF
rounds the US dollar in SDR to six significant digits. UF and UP values carry their official
decimals. A derived value never shows more significant digits than its weakest input supports,
which is the A3/A4.4 rule.

## 9. Page semantics

* The router (`generate.pair_semantic_treatment`) applies standards_special › historical ›
  precious_metal › **institutional_unit** › unsupported_specialized / ordinary_fx. So XDR/XTS stays
  standards, XDR/BGN stays historical, and XAU/XDR stays a metal page (with its institutional-side
  note). Every other pair with an institutional side becomes `institutional_unit`, even where the
  FX snapshot carries a provider value.
* Institutional pages have `data-mode="institutional"`, a pair role, a decision badge and
  registry-cited unit blocks. They have no converter, no rate runtime and no conversion rows. The
  bank-rate, market-driver and exchange-rate-explainer sections are replaced by an
  institutional-unit explainer. Structured data is WebPage, BreadcrumbList and FAQPage, with no
  WebApplication. Visible FAQ and JSON-LD are identical.
* Hubs are institution-aware references: identity, purpose, methodology, status, valuation state,
  source governance, FAQ and reference links. Robots are `index,follow`, canonicals point to the
  page itself, and the sitemap is unchanged.

## 10. XSU decision

**STATUS UNRESOLVED.** No current issuer evidence supports "active". The only indicators of
dormancy are secondary press reports, which is not enough to assert "inactive" or "historical" as
an issuer fact. Pages state that the status is unresolved, show the press indicators labelled as
reports, publish no value and are not promoted. The taxonomy enum cannot express "unresolved", so
`instrument_status` stays `active`. The validator fails any XSU page that asserts activity.

## 11. Provider versus issuer comparison

The comparison was made on 2026-11-18 and is recorded in `provider_values`. Issuer figures are not
stored in the repository, because they are unlicensed. The figures are given in the A4.5 PR.

* XDR: the provider value matches the IMF valuation for the same day within the provider's
  published precision. Classification: `provider_value_secondary_only`.
* CLF: the provider-implied CLF/CLP value differs from the official UF for the same day by more
  than the provider's precision can explain, and the cause is not established. Classification:
  `provider_value_pending_issuer_comparison`, state `unresolved_difference`.

## 12. Future historical datasets (not ingested)

* **XDR**: the IMF publishes daily SDR valuations and historical series. This is a high-value SDR
  history, subject to IMF commercial-reuse permission.
* **CLF**: a complete daily official series exists (SII yearly tables; the CMF API needs a key). It
  is an indexed-unit history, with terms to be verified.
* **UYW**: INE publishes the full daily series since creation as a spreadsheet, with terms to be
  verified.
* **XUA**: there is no independent series. It follows the SDR.
* **XSU**: no published series was found.

Possible future products are an institutional-unit API, an issuer-valuation and provenance
dataset, SDR and indexed-unit histories, and academic exports. All depend on the licensing gate
above.

## 13. Gates and commands

```
python3 generate.py --institutional-units-only     # cohort from policy; a second run changes 0 files
python3 scripts/validate_institutional_snapshot.py
python3 scripts/validate_institutional_units.py
python3 -m unittest tests.test_institutional_units
```
