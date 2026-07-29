# Country Review Execution Protocol

This protocol turns country-review work into a deterministic, auditable flow. Its purpose is to keep review strict while preventing iterative, open-ended rewrite cycles.

## 1. Stop Conditions

Before any country file is drafted, every candidate claim must be assigned one of three allowed states:

- `verified`
- `bounded`
- `verification_target`

If a claim cannot be supported within the allocated research pass, it does not stay ambiguous. It is downgraded immediately to `bounded` or `verification_target`, depending on what is actually known.

## 2. Claim Matrix First

No claim enters a country JSON file until it exists in a claim matrix with a known grade and a claim-matched source.

Required columns:

| Claim ID | Claim | Matching source | Evidence level | Status |
|---|---|---|---|---|
| `MX-FX-01` | Comisión de Cambios has statutory authority to determine the exchange-rate regime | Ley del Banco de México Art. 21 | `E0` | `verified` |
| `MX-FX-02` | The currently applied regime is free-floating | SHCP/Banxico institutional confirmation | `E1` | `verified` |
| `MX-ACC-01` | Resident account eligibility / operation | No claim-matched source yet | `E3` | `verification_target` |
| `MX-NEG-01` | No general authorisation regime identified in the reviewed statutes | Bounded inference from reviewed statutes | `E2` | `bounded` |

The matrix is the pre-write control surface. The JSON is an output artifact, not the place where evidence classification is invented.

## 3. Compound-Claim Rule

Hybrid grades such as `E0/E1` are forbidden.

If one sentence contains multiple independently meaningful legal or regulatory propositions, either:

1. split the propositions into separate internal claims, or
2. keep a composite surface sentence, but assign the composite sentence the weakest evidence level required by any necessary sub-claim.

Example:

`Mexico operates a free-floating exchange-rate regime, set by the Comisión de Cambios.`

Internal grading:

- statutory authority of Comisión de Cambios -> `E0`
- current free-floating regime -> `E1`

Surface-field grading:

- composite claim -> `E1`

## 4. Negative-Claim Rule

Claims such as:

- no restriction
- no approval
- no authorisation
- unrestricted transfer
- free repatriation
- no limit

must not be graded `E0` or `E1` unless a claim-matched official source affirmatively supports that exact negative proposition.

Otherwise they must be recorded as one of:

- `E2` bounded
- `E3` verification target

No country review may treat "absence found in reviewed materials" as a universal legal negative.

## 5. Fixed Country Field Set

Each country review should assess the same field families, even if some remain unresolved:

- border declaration
- exchange-rate regime
- foreign-currency settlement
- resident account rules
- non-resident account rules
- repatriation
- banking conversion
- AML cash restrictions
- domestic cash-payment restrictions
- tax/reporting
- negative claims

This fixed structure prevents ad hoc coverage and makes future validators straightforward.

## 6. Regime-Separation Gate

The reviewer and implementer must verify that these regimes remain distinct:

- customs / border declaration
- exchange-rate regime
- AML reporting
- bank cash-operation restrictions
- domestic cash-payment limits
- tax / information reporting

Blocking issue: any conflation that makes one regime appear to prove another.

## 7. Pre-PR Gate Checklist

Every country PR must pass a single pre-review checklist before opening:

### Evidence Gate

- every claim has a claim-matched source or an explicit downgrade
- every claim has one unambiguous evidence level
- every composite claim inherits the weakest required level
- no unsupported negative claims are framed as verified

### Technical Gate

- JSON valid
- schema valid
- duplicate / similarity checks pass
- source URLs present and correctly scoped
- indexing state correct
- no accidental public-surface change
- sitemap / dataset / `llms.txt` consistency preserved

### Security Gate

- no secrets or tokens
- no untrusted scriptable content inside data fields
- no unreviewed dependency changes
- generated artifacts, if any, match intended inputs

## 8. Two-Round Review Limit

Country-review PRs follow a strict maximum of two review rounds.

Round 1:

- reviewer collects all known blocking findings in one pass

Round 2:

- reviewer checks closure of prior findings
- reviewer may block only on regression or on a newly surfaced material defect that could not reasonably have been identified in round 1

After round 2, the outcome must be one of:

- `PASS`
- `BLOCK` for a material defect

Purely editorial refinements do not reopen the gate.

## 9. Blocking Taxonomy

### Blocking

- claim exceeds its evidence
- source does not support the asserted proposition
- hybrid or ambiguous evidence grading
- conflation of distinct legal regimes
- legal, numeric, or source-authority error
- schema / validator / security failure
- accidental publication or public-surface drift
- governance inconsistency that prevents deterministic validation

### Required Before Next Country

- reusable validator gap
- undocumented methodological rule discovered during the review
- process weakness likely to recur across countries

### Improvement

- wording polish
- structure polish
- naming cleanup
- non-material supporting citation

Only the first category blocks merge.

## 10. Merge Criteria

A country PR is merge-ready when all of the following are true:

1. all blocking findings are closed
2. all gates pass
3. the final diff is scoped to the reviewed issue set
4. unresolved claims are honestly downgraded rather than stretched
5. the final decision is binary: `PASS` or a proven material defect

This protocol is designed to preserve strictness without turning each country into a bespoke research project.
