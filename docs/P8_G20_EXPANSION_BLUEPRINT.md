# P8-0 — G20+ Coverage Expansion Blueprint

**Status:** Blueprint / intake only. No country rules pages, briefs, Static Agent
Interface entries, or sitemap URLs were generated in this phase.

## Why a blueprint phase, not immediate publication

P7A closed with a live Static Agent Interface: any jurisdiction that reaches
`page_status: published` in `data/rules/<slug>.json` now automatically flows
into `/rules/`, `/briefs/`, Passage Check, `/api/v1/`, and the sitemap. That
automation is exactly why coverage expansion must start with a controlled
intake plan instead of mass publication — a mistake made once now propagates
across five public surfaces instead of one.

P8-0 does one thing: it identifies the remaining G20 candidates, records what
research each one needs, and puts a machine-checkable guard rail in place
*before* any research or publication work begins. It changes zero page_status
values and adds zero public files.

## What this phase produced

| File | Purpose |
|---|---|
| `data/coverage/g20-expansion-candidates.json` | The 13 remaining G20 candidates, with priority, complexity, required source-authority categories, expected difficulty, known risk areas, and missing sources. Every entry's `status` is `candidate_only`. |
| `data/coverage/source-intake-matrix.json` | Per-candidate, per-source-category tracking: `not_started` / `identified` / `needs_verification` / `verified_on_file` / `not_applicable`, distinguishing "we know the institution's name" from "we have a live, cited, official source URL." |
| `scripts/validate_coverage_intake.py` | A guard rail that fails the build if any candidate is marked `published`, appears in `/api/v1/`, appears in `sitemap.xml`, appears as covered in `llms.txt`, is missing a required field, or if a `/preview/` route is referenced anywhere in the intake files. |

None of these three files can publish anything by themselves. Publication
still happens exactly one way: a candidate's own `data/rules/<slug>.json` is
independently researched, passes the existing six-gate pipeline (see
`governance.html`), and its `page_status` is set to `published` through that
pipeline — never by editing a coverage-tracking file.

## The candidate status model

```
candidate_only → source_intake → source_review_ready → publish_ready → published
                                        ↓
                                     blocked
```

- **candidate_only** — identified as in-scope; no dedicated research work has
  started under this intake process yet. Every candidate in this phase is at
  this status, including the 10 that already have an internal `verified`
  research file from earlier project phases — that prior work is noted for
  context (`prior_research_state`) but is not treated as fulfilling this
  intake round's own review.
- **source_intake** — primary official sources are being actively identified
  and fetched.
- **source_review_ready** — sources are fetched, dated, and staged for the
  same schema/quality-gate review every other country file goes through.
- **blocked** — intake stalled on a specific, named obstacle (e.g. an
  unreachable official source, an unresolved translation question, a rapidly
  changing regulatory environment that makes any snapshot stale on arrival).
- **publish_ready** — passed the six-gate pipeline in `verified` form and is
  waiting on an explicit publish decision.
- **published** — live on `/rules/`, `/briefs/`, Passage Check, and
  `/api/v1/`. This status may only ever be set on `data/rules/<slug>.json`
  itself, through the existing pipeline — never on a coverage file.

## The 13 remaining G20 candidates

G20 has 19 member countries. 6 are already published: Australia, Canada,
France, Germany, India, Japan. (The site also separately publishes Pakistan
and the United Arab Emirates, which are not G20 members, so the total
published count is 8.) The 13 that remain:

| Country | Priority | Complexity | Internal research state |
|---|---|---|---|
| United Kingdom | High | Low | `verified` on file — central bank + customs sourced |
| United States | High | Medium | `verified` on file — central bank + customs + FinCEN sourced |
| Mexico | High | Low | `verified` on file — central bank + customs sourced |
| South Korea | High | Medium | `verified` on file — central bank + customs sourced |
| Brazil | High | Medium | `verified` on file — recheck against 2021 FX Law consolidation |
| Indonesia | Medium | Medium | `verified` on file — central bank + customs sourced |
| Saudi Arabia | Medium | Medium | `verified` on file — central bank + customs sourced |
| South Africa | Medium | Medium | `verified` on file — central bank + customs sourced |
| Italy | Medium | Medium | None — from-scratch intake; EU-level + national sourcing needed |
| Turkey | Medium | High | `verified` on file — high regulatory-change risk |
| China | Medium | High | `verified` on file — capital-account complexity, HTTPS sources confirmed |
| Argentina | Low | High | None — from-scratch intake; multi-rate regime risk |
| Russia | Low | High | None — from-scratch intake; sanctions/rapid-change risk |

10 of the 13 already carry a `verified`-status internal research file from
earlier phases of this project (`page_status` is not `published`, so it is
not rendered into any public rules page or public coverage surface — the
file's *content* was never designed to be reachable-but-hidden, it is simply
not yet promoted). That prior work
is real and reusable, but this blueprint still records every one of them as
`candidate_only` in the new coverage-tracking system, because none has yet
been re-reviewed against the source-intake matrix's finer-grained categories
(in particular, none of the 10 has a financial-intelligence-unit/AML source
on file yet — every one of them is missing that category).

Argentina, Italy, and Russia have no prior research at all — only a generic
seed entry in `data/rules_seed_index.json` reserving their slug and ISO
identity. These three are genuinely starting from zero.

## What was deliberately not done in this phase

- No `data/rules/<slug>.json` `page_status` field was changed, for any of the
  13 candidates or the 8 published jurisdictions.
- No new file was written under `/rules/`, `/briefs/`, or `/api/v1/`.
- No candidate slug was added to `sitemap.xml`.
- No candidate was presented as covered in `llms.txt`.
- No rule, threshold, or exchange-control posture was asserted for any
  candidate. Every "known risk area" and "expected difficulty" note above
  describes what makes the *research* harder — it is not a claim about the
  country's actual regulatory content, and none of it may be copied into a
  future `data/rules/<slug>.json` file without its own independent, dated,
  primary-source citation.
- No inference was drawn from currency code, region, G20 membership, EU/AU
  membership, or a neighboring/already-published country. Italy shares EUR
  with the already-published France and Germany entries; its rules are
  explicitly flagged as **not** assumable to be identical to either.

## Next steps (not part of this phase)

Future phases will move individual candidates through the status model one
at a time — starting research, running each through the same six-gate
pipeline that produced the 8 currently published entries, and only then
setting `page_status: published` on that candidate's own file. Each such
promotion is its own reviewed change, gated by
`scripts/validate_coverage_intake.py` continuing to pass and by the existing
`rules_quality_gate.py` / `validate_rules.py` checks the pipeline already
enforces.
