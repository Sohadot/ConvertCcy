# Brazil Claim Matrix

Country: Brazil (`BR` / `BRA`)
Currency: BRL (Brazilian Real)
Date created: 2026-07-29
Protocol version: COUNTRY_REVIEW_EXECUTION_PROTOCOL.md §2

---

## Claims

| Claim ID | Claim | Authority | Type | Matching source | Evidence target | Workflow status |
|---|---|---|---|---|---|---|
| `BR-FX-01` | BCB administers Brazil's exchange-rate regime | Banco Central do Brasil | `positive` | Lei 14.286/2021 Art. 6 (not yet pinned) | `E0` | `source_intake_pending` |
| `BR-FX-02` | The exchange-rate regime is floating | Banco Central do Brasil | `operational` | BCB institutional / CMN resolution (not yet pinned) | `E1` | `source_intake_pending` |
| `BR-CUST-01` | Travellers must declare amounts exceeding USD 10,000 (or equivalent) in cash/instruments to Receita Federal on entry and exit | Receita Federal | `positive` | IN RFB (number not yet pinned; likely 1.385/2013 or successor under Lei 14.286/2021) | `E0` | `source_intake_pending` |
| `BR-CUST-02` | Foreign currency may be brought into Brazil without quantitative limit | Receita Federal | `negative` | none | `E2` | `verification_target` |
| `BR-CUST-03` | Export of foreign currency is restricted / subject to BCB rules | Banco Central do Brasil | `positive` | none (vague "BCB rules" unspecified) | `E1` | `verification_target` |
| `BR-ACC-01` | Residents are subject to BCB limits and approval requirements for foreign currency accounts | Banco Central do Brasil | `positive` | none; may be superseded by Lei 14.286/2021 | `E1` | `verification_target` |
| `BR-ACC-02` | Non-residents may open FX accounts and transfer funds more freely through authorised banks | Banco Central do Brasil | `positive` | none | `E1` | `verification_target` |
| `BR-BIZ-01` | Cross-border transactions must be settled through authorised banks per BCB FX regulations | Banco Central do Brasil | `positive` | Lei 14.286/2021 Art. 5 (not yet pinned) | `E1` | `source_intake_pending` |
| `BR-FX-03` | Brazil maintains controls on certain capital account transactions | Banco Central do Brasil / CMN | `positive` | none (vague) | `E1` | `verification_target` |
| `BR-FX-04` | Current account transactions are largely liberalised | Banco Central do Brasil / IMF | `positive` | IMF Article VIII acceptance (1999); no primary pinned | `E1` | `source_intake_pending` |
| `BR-NEG-01` | Residents are subject to BCB limits on taking foreign currency out | Banco Central do Brasil | `negative` | none | `E2` | `verification_target` |
| `BR-NEG-02` | Capital repatriation and certain payments require BCB approval or documentation | Banco Central do Brasil | `negative` | none; may be superseded by Lei 14.286/2021 | `E2` | `verification_target` |
| `BR-BANK-01` | FX conversion is available through authorised banks and licensed exchange offices (casas de câmbio) | Banco Central do Brasil | `operational` | BCB institutional (generic) | `E1` | `source_intake_pending` |

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
