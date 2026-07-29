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
- 8 claims → `verified` (7× E0, 1× E1)
- 1 claim → `bounded` (BR-FX-03: rewrite required)
- 1 claim → `bounded` (BR-CUST-02: structural inference, not explicit statutory text)
- 3 claims → `superseded` (BR-ACC-01, BR-NEG-01, BR-NEG-02)
- 3 New Claim Candidates recorded (not added to rules file)
- H1 confirmed, H2 partially confirmed, H3 deferred

---

## Claims

| Claim ID | Claim | Authority | Type | Matching source | Evidence target | Source budget | Stop condition | Workflow status |
|---|---|---|---|---|---|---|---|---|
| `BR-FX-01` | BCB regulates Brazil's exchange-rate market | Banco Central do Brasil | `positive` | **Lei 14.286/2021 Art. 5** (planalto.gov.br, full text obtained) | `E0` | 1 | — | **verified** |
| `BR-FX-02` | The exchange rate is freely agreed between authorised institutions and their clients (floating) | Banco Central do Brasil | `operational` | **Lei 14.286/2021 Art. 2 §único** | `E0` | 1 | — | **verified** |
| `BR-CUST-01` | Travellers carrying cash exceeding USD 10,000 (or equivalent) must file e-DBV with Receita Federal on entry and exit; paper money only (excludes cheques/traveller's cheques) | Receita Federal | `positive` | **Lei 14.286/2021 Art. 14 §1-I** + Receita Federal official page (gov.br, updated 18/11/2024) + IN RFB 1.385/2013 | `E0` | 2 | — | **verified** |
| `BR-CUST-02` | Foreign currency may be brought into Brazil without quantitative limit (only declaration above USD 10,000) | Receita Federal / Lei 14.286 | `negative` | **Lei 14.286/2021 Art. 14 §1**: carrying up to USD 10,000 is exempt from the institutional-channel rule; no upper limit stated in the law | `E1` | 2 | Bounded: Art. 14 establishes the declaration obligation but does not explicitly state "no limit"; inference from structure | **bounded** |
| `BR-CUST-03` | Cross-border movement of currency must go through an authorised institution (except hand-carried cash up to USD 10,000) | Banco Central do Brasil / Lei 14.286 | `positive` | **Lei 14.286/2021 Art. 14** (ingresso e saída exclusivamente por meio de instituição autorizada) | `E0` | 1 | — | **verified** |
| `BR-ACC-01` | ~~Residents are subject to BCB limits and approval requirements for foreign currency accounts~~ | Banco Central do Brasil | `positive` | **SUPERSEDED** — Lei 14.286/2021 Art. 2 (operations freely, without value limitation) + Art. 5-IX (BCB regulates FX accounts but as a regulatory framework, not per-transaction approval) | — | — | — | **superseded** |
| `BR-ACC-02` | BCB regulates the conditions for opening and operating foreign-currency accounts in Brazil (residents and non-residents) | Banco Central do Brasil | `positive` | **Lei 14.286/2021 Art. 5-IX** (BCB regulamenta contas em moeda estrangeira no País, inclusive requisitos e procedimentos para abertura e movimentação) | `E0` | 1 | — | **verified** |
| `BR-BIZ-01` | FX market operations must be conducted exclusively through BCB-authorised institutions | Banco Central do Brasil | `positive` | **Lei 14.286/2021 Art. 3** | `E0` | 1 | — | **verified** |
| `BR-FX-03` | ~~Brazil maintains controls on certain capital account transactions~~ | Banco Central do Brasil / CMN | `positive` | **CANNOT BE VERIFIED AS STATED** — Art. 2 says "freely, without value limitation"; Art. 9 says foreign capital gets identical treatment to national capital. BCB retains regulatory power (Art. 5) but no specific "capital control" is identified in the law | — | 2 | — | **bounded** (rewrite required: BCB has regulatory authority over FX market conditions, but no general capital-account control is established by this law) |
| `BR-FX-04` | Current account transactions are largely liberalised | Banco Central do Brasil / IMF | `positive` | **Lei 14.286/2021 Art. 2** (freely, no value limitation) + Brazil's IMF Article VIII acceptance (22 Nov 1999) | `E1` | 2 | — | **verified** |
| `BR-NEG-01` | ~~Residents are subject to BCB limits on taking foreign currency out~~ | Banco Central do Brasil | `negative` | **SUPERSEDED** — Lei 14.286/2021 Art. 2 (sem limitação de valor) + Art. 26 (export proceeds may be kept abroad) | — | — | — | **superseded** |
| `BR-NEG-02` | ~~Capital repatriation and certain payments require BCB approval or documentation~~ | Banco Central do Brasil | `negative` | **SUPERSEDED** — Lei 14.286/2021 Art. 9 (equal treatment) + Art. 26 (free retention abroad) + Art. 2 (no value limitation) | — | — | — | **superseded** |
| `BR-BANK-01` | FX conversion is available through BCB-authorised institutions (banks + casas de câmbio); individuals may trade up to USD 500 cash between themselves | Banco Central do Brasil | `operational` | **Lei 14.286/2021 Art. 3** (authorised institutions) + **Art. 19** (USD 500 individual exception) | `E0` | 1 | — | **verified** |

---

## Source Intake Priority Order

Per the review hypothesis H1, the **first research question** must be:

> Does Lei 14.286/2021 (effective 30 Dec 2022) supersede the on-file claims about BCB approval requirements, resident limits, and capital-account controls?

This single question resolves the status of BR-ACC-01, BR-NEG-01, BR-NEG-02, BR-FX-03, and BR-CUST-03 in one pass. Only after H1 is answered should individual claim-level source pinning proceed.

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
| `H1` | Lei 14.286/2021 (effective 30 Dec 2022) materially liberalised the FX regime, superseding older BCB circulars and removing approval requirements | **CONFIRMED** — Art. 2 (free operations, no value limitation), Art. 9 (equal treatment of foreign capital), Art. 26 (export proceeds kept abroad). Revokes 20+ older laws/decrees including Lei 4.131/1962 Arts. 1–8 (old foreign capital registration). | Claims BR-ACC-01, BR-NEG-01, BR-NEG-02 → `superseded`; BR-FX-03 → `bounded` (rewrite needed) |
| `H2` | The Receita Federal declaration rule (IN RFB 1.385/2013) may have been updated or replaced | **PARTIALLY CONFIRMED** — Lei 14.286/2021 Art. 14 is now the primary legal basis (raised threshold from R$10,000 to USD 10,000); IN RFB 1.385/2013 remains listed as associated legislation on the Receita Federal page (updated 18/11/2024). The threshold and scope changed but the IN was not revoked. | BR-CUST-01 source updated to cite Lei 14.286 Art. 14 as primary + IN RFB 1.385/2013 as implementing regulation |
| `H3` | COAF's AML reporting scope is distinct from customs declaration and from BCB's FX framework | **NOT YET TESTED** — deferred; no claims in the matrix depend on COAF. To be confirmed if AML fields are added in a future matrix revision. | No current impact |

---

## New Claim Candidates

| Candidate ID | Proposition | Source | Justification for inclusion |
|---|---|---|---|
| `NCC-01` | Individuals may buy/sell foreign currency cash up to USD 500 between themselves without using an authorised institution | Lei 14.286/2021 Art. 19 | New liberalisation not in the on-file brazil.json; incorporated into BR-BANK-01 for now |
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

This matrix is the gating artifact. Source intake may begin only after this matrix is reviewed and accepted. Source intake answers these claims; it does not discover new ones (Protocol §11).
