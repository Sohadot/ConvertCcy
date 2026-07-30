# Brazil Claim Matrix

Country: Brazil (`BR` / `BRA`)
Currency: BRL (Brazilian Real)
Date created: 2026-07-29
Source intake completed: 2026-07-29
Protocol version: COUNTRY_REVIEW_EXECUTION_PROTOCOL.md §2

## Source Intake Summary

**Primary source obtained:** Lei 14.286/2021 full text (planalto.gov.br, 29 articles, effective 30 Dec 2022).
**Secondary confirmation:** Receita Federal Traveller's Guide (gov.br, updated 18/11/2024).

**Outcome:**
- 9 claims → `verified` (6× E0, 3× E1)
- 3 claims → `bounded` (BR-CUST-02, BR-ACC-01A, BR-NEG-01)
- 2 claims → `verification_target` (BR-FX-03, BR-NEG-02)
- 1 claim → `superseded` (BR-ACC-01 old wording only)
- 3 New Claim Candidates recorded (not added to rules file)
- Row count increased because compound claims were split into claim-level entries (for example `BR-FX-02A` / `BR-FX-02B` and `BR-ACC-01A` / `BR-ACC-01B`).
- H1 partially confirmed, H2 partially confirmed, H3 deferred

---

## Claims

| Claim ID | Claim | Authority | Type | Matching source | Evidence target | Final evidence level | Source budget | Stop condition | Workflow status |
|---|---|---|---|---|---|---|---|---|---|
| `BR-FX-01` | BCB regulates Brazil's exchange-rate market | Banco Central do Brasil | `positive` | **Lei 14.286/2021 Art. 5** (planalto.gov.br, full text obtained) | `E0` | `E0` | 1 | — | **verified** |
| `BR-FX-02A` | The exchange rate for FX transactions is freely agreed between authorised institutions and their clients | Banco Central do Brasil | `operational` | **Lei 14.286/2021 Art. 2 § único** | `E0` | `E0` | 1 | — | **verified** |
| `BR-FX-02B` | Brazil's current exchange-rate regime is floating, with BCB intervening only occasionally | Banco Central do Brasil | `operational` | **BCB official regime page** (`bcb.gov.br/htms/mercosul/regcam.asp?frame=1&idpai=`): "O sistema cambial brasileiro é do tipo flutuante" | `E1` | `E1` | 2 | If no current institutional source found → `verification_target` | **verified** |
| `BR-CUST-01` | Travellers carrying cash exceeding USD 10,000 (or equivalent) must file e-DBV with Receita Federal on entry and exit; paper money only (excludes cheques/traveller's cheques) | Receita Federal | `positive` | **Lei 14.286/2021 Art. 14 §1-I** + Receita Federal official page (gov.br, updated 18/11/2024) + IN RFB 1.385/2013 | `E0` | `E0` | 2 | — | **verified** |
| `BR-CUST-02` | Foreign currency may be brought into Brazil without quantitative limit (only declaration above USD 10,000) | Receita Federal / Lei 14.286 | `negative` | **Lei 14.286/2021 Art. 14 §1**: carrying up to USD 10,000 is exempt from the institutional-channel rule; no upper limit stated in the law | `E1` | `E2` | 2 | Bounded: Art. 14 establishes the declaration obligation but does not explicitly state "no limit"; inference from structure | **bounded** |
| `BR-CUST-03` | Travellers may carry cash across the border, but amounts above USD 10,000 or equivalent must be declared to Receita Federal; on departure, proof of lawful acquisition or prior declaration may be required | Receita Federal | `positive` | **Receita Federal official departure page** (updated 30/12/2022) requiring `e-DBV` above USD 10,000 plus proof of purchase / prior entry declaration / proof of receipt in cash for eligible non-residents | `E1` | `E1` | 2 | If departure guidance not found → `bounded` | **verified** |
| `BR-ACC-01` | ~~Residents are subject to BCB limits and approval requirements for foreign currency accounts~~ | Banco Central do Brasil | `compound` | Old on-file wording overstates the rule. **Not carried forward as stated.** Lei 14.286/2021 Art. 5-IX gives BCB regulatory authority over FX accounts, but current BCB regulation still limits account holders to listed eligible categories. | — | — | 2 | — | **superseded** |
| `BR-ACC-01A` | General resident access to domestic foreign-currency accounts is not established by the sources reviewed | Banco Central do Brasil | `negative` | **RMCCI 1-14, Section 1 items 1–2** list eligible account-holder categories and do not establish a general resident entitlement | `E2` | `E2` | 2 | If a broader resident-entitlement source is not found within budget → remains `bounded` | **bounded** |
| `BR-ACC-01B` | Foreign-currency accounts in Brazil remain available only under BCB-defined conditions and eligible categories, and must be held at banks authorised to operate in the FX market | Banco Central do Brasil | `positive` | **Lei 14.286/2021 Art. 5-IX** + **RMCCI 1-14, Section 1 items 1–2** | `E1` | `E1` | 2 | If current BCB regulation were unavailable → `verification_target` | **verified** |
| `BR-BIZ-01` | FX market operations must be conducted exclusively through BCB-authorised institutions | Banco Central do Brasil | `positive` | **Lei 14.286/2021 Art. 3** | `E0` | `E0` | 1 | — | **verified** |
| `BR-FX-03` | ~~Brazil maintains controls on certain capital account transactions~~ | Banco Central do Brasil / CMN | `compound` | **Not verified as stated.** Art. 2 says "freely, without value limitation"; Art. 9 gives equal treatment to foreign capital; BCB retains regulatory authority, but no current claim-matched "certain capital controls" proposition was pinned in this intake. | — | `E3` | 2 | If no specific current control is pinned within budget → `verification_target` | **verification_target** |
| `BR-FX-04` | Current account transactions are largely liberalised | Banco Central do Brasil / IMF | `positive` | **Lei 14.286/2021 Art. 2** (freely, no value limitation) + Brazil's IMF Article VIII acceptance (22 Nov 1999) | `E1` | `E1` | 2 | — | **verified** |
| `BR-NEG-01` | ~~Residents are subject to BCB limits on taking foreign currency out~~ | Banco Central do Brasil / Receita Federal | `negative` | Old on-file wording is too broad. The current official sources support a narrower traveller rule: declaration above USD 10,000 and proof of lawful acquisition / prior declaration on departure. They do **not** establish a general "BCB limits" claim for residents as stated. | `E2` | `E2` | 2 | If no claim-matched source for a general resident-limits proposition is found → remain `bounded` and do not carry forward | **bounded** |
| `BR-NEG-02` | ~~Capital repatriation and certain payments require BCB approval or documentation~~ | Banco Central do Brasil | `compound` | The on-file proposition bundles repatriation, certain payments, approval, and documentation. The sources reviewed do not verify this full combination, nor do they prove the universal opposite. | `E3` | `E3` | 2 | If not split into narrower claims with claim-matched sources → remain `verification_target` | **verification_target** |
| `BR-BANK-01` | FX conversion is available through BCB-authorised institutions (banks + casas de câmbio) | Banco Central do Brasil | `operational` | **Lei 14.286/2021 Art. 3** (authorised institutions) + BCB institutional regime page (banks, corretoras, agências de turismo authorised by BCB) | `E1` | `E1` | 2 | If no current institutional page found → `bounded` | **verified** |

---

## Source Intake Priority Order

Per the review hypothesis H1, the **first research question** must be:

> Does Lei 14.286/2021 (effective 30 Dec 2022) supersede the on-file claims about BCB approval requirements, resident limits, and capital-account controls?

This single question resolved the old broad-claim risk, but it did **not** by itself prove the current account-eligibility, traveller-cash, or current-regime claims. Those required separate claim-matched confirmation from BCB and Receita Federal.

**Intake sequence:**
1. Lei 14.286/2021 full text (resolves H1, impacts 5+ claims)
2. Receita Federal declaration rule (resolves BR-CUST-01)
3. BCB institutional pages for regime/routing (resolves BR-FX-01, BR-FX-02, BR-BIZ-01, BR-BANK-01)
4. IMF Article VIII confirmation (resolves BR-FX-04)
5. COAF scope (confirms regime separation for H3; no claims depend on it yet)

---

## Review Hypotheses

| Hypothesis ID | Hypothesis | Resolution | Impact |
|---|---|---|---|
| `H1` | Lei 14.286/2021 (effective 30 Dec 2022) materially liberalised the FX regime, superseding older BCB circulars and removing approval requirements | **PARTIALLY CONFIRMED** — Art. 2 (free operations, no value limitation), Art. 9 (equal treatment of foreign capital), and Art. 26 (export proceeds kept abroad) confirm substantial liberalisation. But current BCB regulation still restricts who may hold domestic foreign-currency accounts, so the law did not create a general resident entitlement. | The old BR-ACC-01 wording is `superseded`, but the underlying subject remains regulated; BR-NEG-01 is only `bounded`, BR-NEG-02 stays `verification_target`, and BR-FX-03 stays `verification_target` until pinned narrowly |
| `H2` | The Receita Federal declaration rule (IN RFB 1.385/2013) may have been updated or replaced | **PARTIALLY CONFIRMED** — Lei 14.286/2021 Art. 14 is now the primary legal basis (raised threshold from R$10,000 to USD 10,000); IN RFB 1.385/2013 remains listed as associated legislation on the Receita Federal page (updated 18/11/2024). The threshold and scope changed but the IN was not revoked. | BR-CUST-01 source updated to cite Lei 14.286 Art. 14 as primary + IN RFB 1.385/2013 as implementing regulation |
| `H3` | COAF's AML reporting scope is distinct from customs declaration and from BCB's FX framework | **NOT YET TESTED** — deferred; no claims in the matrix depend on COAF. To be confirmed if AML fields are added in a future matrix revision. | No current impact |

---

## New Claim Candidates

| Candidate ID | Proposition | Source | Justification for inclusion |
|---|---|---|---|
| `NCC-01` | Individuals may buy/sell foreign currency cash up to USD 500 between themselves without using an authorised institution | Lei 14.286/2021 Art. 19 | New liberalisation not in the on-file `brazil.json`; kept outside the active claims until a controlled matrix revision approves inclusion |
| `NCC-02` | Penalty for undeclared cash above USD 10,000: forfeiture of the excess to the National Treasury + criminal sanctions | Lei 14.286/2021 Art. 14 §3 | Penalty clause; may be relevant for the rules file traveller section |
| `NCC-03` | Exporters may retain foreign-currency export proceeds abroad without repatriation obligation | Lei 14.286/2021 Art. 26 (amending Lei 11.371/2006 Art. 1) | Material liberalisation relevant to business/repatriation field |

These are recorded per Protocol §12. They do not enter the rules file until incorporated in a controlled matrix revision.

---

## Regime-Separation Map (Protocol §6)

| Regime | Authority | Must not be conflated with |
|---|---|---|
| Customs border declaration | Receita Federal | FX regime, AML, banking |
| Exchange-rate regime | BCB / CMN | Customs, capital controls |
| Capital-account controls | BCB / CMN | Current-account freedom, AML |
| AML reporting | COAF | Customs declaration, banking FX routing |
| Banking FX routing | BCB (prudential) | AML, customs |
| Tax / information reporting | Receita Federal | Customs declaration, FX regime |

---

## Decision

Source intake is complete.

Only claims marked `verified` or `bounded` may be carried into draft generation.
`verification_target` claims must not appear as affirmative rules.
`superseded` wording must be removed and retained only in audit history.

Draft generation may begin only after the intake summary and final evidence levels remain internally consistent.
