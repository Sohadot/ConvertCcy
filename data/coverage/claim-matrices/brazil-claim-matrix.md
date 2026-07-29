# Brazil Claim Matrix

Country: Brazil (`BR` / `BRA`)
Currency: BRL (Brazilian Real)
Date created: 2026-07-29
Protocol version: COUNTRY_REVIEW_EXECUTION_PROTOCOL.md §2

---

## Claims

| Claim ID | Claim | Authority | Type | Matching source | Evidence target | Source budget | Stop condition | Workflow status |
|---|---|---|---|---|---|---|---|---|
| `BR-FX-01` | BCB administers Brazil's exchange-rate regime | Banco Central do Brasil | `positive` | Lei 14.286/2021 Art. 6 (not yet pinned) | `E0` | 1 | If Art. 6 text not obtainable → `E1` | `source_intake_pending` |
| `BR-FX-02` | The exchange-rate regime is floating | Banco Central do Brasil | `operational` | BCB institutional / CMN resolution (not yet pinned) | `E1` | 2 | If no official statement found → `bounded` | `source_intake_pending` |
| `BR-CUST-01` | Travellers must declare amounts exceeding USD 10,000 (or equivalent) in cash/instruments to Receita Federal on entry and exit | Receita Federal | `positive` | IN RFB (number not yet pinned) | `E0` | 2 | If IN RFB text not obtainable → `E1` | `source_intake_pending` |
| `BR-CUST-02` | Foreign currency may be brought into Brazil without quantitative limit | Receita Federal | `negative` | none | `E2` | 2 | If no affirmative source → stays `verification_target` | `verification_target` |
| `BR-CUST-03` | Export of foreign currency is restricted / subject to BCB rules | Banco Central do Brasil | `positive` | none | `E1` | 2 | If no specific rule pinned → `verification_target` | `verification_target` |
| `BR-ACC-01` | Residents are subject to BCB limits and approval requirements for foreign currency accounts | Banco Central do Brasil | `positive` | none; may be superseded by Lei 14.286/2021 | `E1` | 2 | If Lei 14.286 supersedes → `superseded` | `verification_target` |
| `BR-ACC-02` | Non-residents may open FX accounts and transfer funds more freely through authorised banks | Banco Central do Brasil | `positive` | none | `E1` | 2 | If no specific rule pinned → `verification_target` | `verification_target` |
| `BR-BIZ-01` | Cross-border transactions must be settled through authorised banks per BCB FX regulations | Banco Central do Brasil | `positive` | Lei 14.286/2021 Art. 5 (not yet pinned) | `E1` | 1 | If Art. 5 text not obtainable → `bounded` | `source_intake_pending` |
| `BR-FX-03` | Brazil maintains controls on certain capital account transactions | Banco Central do Brasil / CMN | `positive` | none | `E1` | 2 | If no specific control identified → `verification_target` | `verification_target` |
| `BR-FX-04` | Current account transactions are largely liberalised | Banco Central do Brasil / IMF | `positive` | IMF Article VIII acceptance (1999); no primary pinned | `E1` | 2 | If IMF Art. VIII acceptance not confirmable → `bounded` | `source_intake_pending` |
| `BR-NEG-01` | Residents are subject to BCB limits on taking foreign currency out | Banco Central do Brasil | `negative` | none | `E2` | 2 | If no affirmative source → stays `verification_target` | `verification_target` |
| `BR-NEG-02` | Capital repatriation and certain payments require BCB approval or documentation | Banco Central do Brasil | `negative` | none; may be superseded by Lei 14.286/2021 | `E2` | 2 | If Lei 14.286 supersedes → `superseded` | `verification_target` |
| `BR-BANK-01` | FX conversion is available through authorised banks and licensed exchange offices (casas de câmbio) | Banco Central do Brasil | `operational` | BCB institutional (generic) | `E1` | 1 | If no institutional page confirms → `bounded` | `source_intake_pending` |

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

| Hypothesis ID | Hypothesis | Impact if confirmed |
|---|---|---|
| `H1` | Lei 14.286/2021 (New FX Law, effective 30 Dec 2022) materially liberalised the FX regime, superseding older BCB circulars and removing several approval requirements | Claims BR-ACC-01, BR-NEG-01, BR-NEG-02, BR-FX-03 may be `superseded` or require downgrade to `bounded` |
| `H2` | The Receita Federal declaration rule (IN RFB 1.385/2013) may have been updated or replaced following Lei 14.286/2021 | Claim BR-CUST-01 source reference may need updating |
| `H3` | COAF's AML reporting scope is distinct from the customs declaration and from BCB's FX authorisation framework | If confirmed, AML claims (not yet in matrix) remain excluded from customs/FX fields; if refuted, regime-separation is at risk |

---

## New Claim Candidates

(Empty — to be populated only if source intake reveals a proposition not covered above)

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
