# ConvertCCY — Asset Intelligence Factory Plan

**Asset:** convertccy.com
**System context:** Sovereign Asset System — Tier 1 (AI-era category artifact candidate)
**Plan status:** v1.0 — adopted
**Audit date:** 2026-07-04
**Companion documents:** `domain-dossier.md` (strategic brief), `DECISION_LOG.md` (governance record), `RULES_ARCHITECTURE.md` (pipeline)

This file governs the transformation of convertccy.com from *category asset* to
*category intelligence source*: a factory that produces governed jurisdictional
FX intelligence, not a website that publishes currency content.

---

## Part 1 — Methodology Compliance Audit

Verified against the Sovereign Asset System methodology on 2026-07-04, by direct
inspection of the repository (not self-reported).

### What the audit measured

| Check | Method | Result |
|---|---|---|
| Dead links / fractures | 6,048 internal hrefs resolved across all top-level, article, rules pages + 300 sampled pair pages | **0 broken** |
| Ghost pages in sitemap | 500 sitemap URLs sampled against files on disk (28,752 total URLs) | **0 missing** |
| SEO discipline | canonical tags, robots.txt, preview noindex, JSON-LD (3 blocks/pair page), llms.txt | **Present and coherent** |
| Governance | quality gate v1.2.1, schema validation, lifecycle separation (preview vs sovereign layer), decision log | **Operational** |
| Agent readability | llms.txt, open dataset (CC BY 4.0), citation blocks, per-field source mapping | **Present** |
| Pair page uniqueness | word-level diff of sampled pair pages | **78–86% similar** ⚠ |
| Rules pipeline health | `data/generated/rules_manifest.json` | **16 of 24 country files fail validation** ⚠ |
| Monetization | full-text scan for revenue surfaces | **None exists** ⚠ |

### Scorecard against the methodology's pillars

| # | Pillar | Verdict | Evidence |
|---|---|---|---|
| 1 | Strategic value maximization | **Partial** | Dossier and framework exist; intelligence layers (ontology, standard, engine) not yet named or public |
| 2 | Conceptual story & contextual frame | **Strong** | manifesto, framework, methodology pages are manually governed authority pages |
| 3 | SEO strength & quality | **Strong hygiene, one structural risk** | Zero fractures, clean canonicals — but 28,730 near-identical pair pages is a scaled-content exposure (see Risk R1) |
| 4 | Sovereign reference content | **Strong but shallow** | Rules layer is genuinely reference-grade (source-mapped, review-dated) but only 5 countries published |
| 5 | Respectable recurring income | **Absent** | No monetization surface of any kind exists today. Largest unmet pillar |
| 6 | Authority & trust consolidation | **Strong** | Citation blocks, review dates, official-source mapping, GSC verified |
| 7 | No ghost pages / strong internal links | **Met mechanically, at risk substantively** | No orphan URLs; but pair pages are template-thin relative to their count |
| 8 | No fractures / dead links | **Met** | 0/6,048 broken |
| 9 | No SEO randomness | **Met** | Generator-driven, sitemap-eligible only when published, preview disallowed in robots.txt |
| 10 | Buyer logic | **Documented, not yet embodied** | Exists in dossier (internal); the public asset does not yet perform its buyer logic |
| 11 | Future respectable income | **Planned here** | Part 3, Layer 10 |
| 12 | Acquisition readiness | **Partial** | Framework has acquisition logic; missing: usage signals, income proof, named standard |
| 13 | Domain inevitability in category | **In progress** | Owns the converter + rules intersection; inevitability requires the rules layer at 25+ countries and a named standard |
| 14 | Loss-if-not-acquired | **Not yet true** | Becomes true when the dataset, standard, and engine exist at coverage — see Part 4 |

### Honest overall verdict

The asset **respects the methodology's hygiene and governance pillars at a high
level** — link integrity, lifecycle governance, source discipline, and agent
readability are genuinely above market standard. It **does not yet respect the
factory pillars**: it publishes governed content but does not yet *produce
intelligence*, generates **zero income**, and its strongest differentiator (the
rules layer) is 5 pages deep while 16 country files sit failed in the pipeline.

ConvertCCY today is a well-governed reference site. It is not yet a Category
Intelligence Factory. Part 3 defines the conversion.

### Material risks found

- **R1 — Scaled-content exposure.** 28,730 pair pages at 78–86% textual
  similarity (~500 visible words each) is the profile search engines classify
  as scaled content. Mitigation: enrich, don't delete — inject per-pair unique
  intelligence (jurisdictional rule links for both currencies, pair-specific
  regime notes, volatility class) so each page carries data no template clone
  has. No mass deletion: pillar 9 forbids abrupt SEO shocks.
- **R2 — Single free rate dependency.** All pair pages fetch
  `api.exchangerate-api.com/v4` (free, no SLA, no key). One upstream change
  silently degrades 28,730 pages. Mitigation: server-side snapshot fallback +
  documented degradation mode (methodology.html already promises this;
  implementation must match).
- **R3 — Pipeline stall.** `validation_failed: 16` means two-thirds of drafted
  jurisdictions never reach the sovereign layer. The factory's production line
  is blocked at QA. This is the highest-leverage single fix in the repository.

---

## Part 2 — Factory Thesis

**From:** convertccy.com, a currency conversion reference site.
**To:** the governed intelligence source for *jurisdictional currency access* —
the system that answers not only "what is 1 USD in EUR" but **"what happens to
money when it crosses a border"**, in a form both humans and AI agents can
trust, cite, and build on.

The conceptual story (the "banana frame"): every converter shows the same
number. ConvertCCY's frame is that **a conversion is a jurisdictional event,
not an arithmetic one**. The rate is public; the *rules of passage* —
declaration thresholds, exchange controls, residency divergence — are
fragmented across hundreds of official sources in dozens of languages.
ConvertCCY governs that fragmentation into one disciplined, source-mapped,
versioned reference layer. The interface, the dataset, the standard, and the
engine all embody this single thesis.

---

## Part 3 — The Eleven Layers

### 1. Domain thesis
*The sentence that makes the name necessary:* **"Currency conversion is a
jurisdictional event, and convertccy.com is where that event is governed into
reference knowledge."** "Convert" = the universal intent; "Ccy" = the ISO
register of professionals. No other name states both the act and the register.

### 2. Category language
Vocabulary the asset will own and consistently use until the market uses it:

- **Currency passage** — the movement of value across a jurisdictional boundary.
- **Declaration threshold** — already in use on rules pages; anchor term.
- **Rules integrity** — the property of a rules statement being source-mapped,
  review-dated, and lifecycle-governed.
- **Sovereign layer** — the published, citable reference surface (already used
  internally; promote to public language).
- **Passage check** — the act of verifying what a specific amount triggers in a
  specific jurisdiction (names the Engine's output).

### 3. Ontology — *ConvertCCY Currency Passage Ontology*
The original classification of the category. Classes (each becomes a permanent
reference page under `/ontology/`):

1. Declaration regimes (thresholds, currencies of denomination, who declares)
2. Exchange controls (access restrictions, approval regimes)
3. Residency divergence (resident vs non-resident asymmetry)
4. Import/export ceilings (cash in vs cash out asymmetry)
5. Reporting obligations (banks, individuals, carriers)
6. Channel restrictions (cash vs transfer vs card treatment)
7. Penalty regimes (confiscation, fines, criminal exposure)
8. Rate regimes (floating, pegged, dual-rate, parallel-market economies)

The existing rules schema v1.2.1 already encodes most of these fields; the
ontology *names* them publicly, which is what makes ConvertCCY the language
maker rather than a market follower.

### 4. Standard — *Currency Rules Integrity Standard (CRIS)*
Already implicit in `scripts/rules_schema.py` + `validate_rules.py` +
`rules_quality_gate.py`. The move: publish it as a named, versioned public
standard page defining what a *trustworthy* country rules statement requires —
per-field official source, review date, lifecycle status, claims restraint.
The standard is the asset's moat statement: anyone can generate FX content;
only CRIS-conformant content is reference-grade.

### 5. Protocol
The public description of how intelligence is produced:
`draft → schema validation → source verification → quality gate → sovereign
layer`, with failed states (`needs_hardening`, `validation_failed`) never
leaking to the public surface. This already exists operationally (manifest +
gate v1.2.1). Publish it as `/governance/` so the discipline itself becomes
visible trust capital.

### 6. Engine — *Passage Check*
The rule-based diagnostic that turns readers into users. Input: origin
country, destination country, amount, residency status. Output: a governed
result — which declaration thresholds are crossed, which controls apply, which
sources say so, and the review date of every claim. **No AI required**: it is
a deterministic evaluation over `rules/dataset.json`, which already exists
with per-field sources. Every output links to the ontology class pages and the
country rules pages (engine output → class page linkage, as the methodology
prescribes). This is the single feature that converts the asset from
*publisher* to *factory*: the visitor receives an output, not a page.

### 7. Reference layer
- Fix the 16 validation-failed country files (R3) — the drafts exist; the
  factory is blocked at QA, not at research.
- Coverage sequence: 5 → G20 → 40 jurisdictions. Coverage breadth is what
  makes the dataset acquirable rather than admirable.
- Keep the open dataset (CC BY 4.0) as the citable research tier; it is the
  agent-readability play and the standard's proof of practice.
- Enrich pair pages (R1) with per-pair jurisdictional intelligence so the
  28,730-page footprint becomes defensible depth instead of scaled-content
  liability.

### 8. Governance
Already the asset's strongest layer: decision log, append-only manifest
discipline, lifecycle gates, one-concern-one-PR. Additions: public
`/governance/` page (see Layer 5), dataset changelog with versioned releases,
and a claims-restraint rule — no country page ever states more than its
sources support (already practiced; codify in CRIS).

### 9. Interface thesis
**The interface must behave like the reference layer it presents: nothing
decorative, everything evidentiary.** The existing design system already obeys
this — meta strips, review dates, citation boxes, source cards, mono-font data
register. Codify it: every visual element must answer *"what claim does this
support?"*. No WebGL, no spectacle; the aesthetic of a well-run registry is the
correct embodiment of a governance thesis. Conceptual first, then performance,
then beauty. Engine outputs inherit the same evidentiary styling as rules
pages — the tool must look like the standard it enforces.

### 10. Monetization — respectable, pre-sale, non-contaminating
Current income: **zero**. The methodology requires income that extends the
reference, never dilutes it. In order of trust-safety:

1. **Country Passage Briefs** — paid PDF per jurisdiction (traveler/business
   editions), generated from the same governed dataset. Income = the
   reference in portable form.
2. **Commercial dataset license** — CC BY 4.0 stays free for research/citation;
   commercial redistribution (fintechs, travel platforms) requires a paid
   license. Costs nothing to offer; prices the moat.
3. **Passage Check API** — metered access to the engine's JSON output once the
   engine exists. The agentic-web revenue line: AI agents are customers.
4. **Embeddable rules widget** — attribution-bearing embed of a country's
   thresholds; part distribution (links, citations), part paid tier.
5. **Independent reference sponsorship** — a single, labeled, editorially
   separated sponsor slot on rules index only. Last resort, with extreme care.

**Never:** programmatic ad units on rules pages, affiliate links inside
governed content, or any claim shaped by a payer.

### 11. Buyer logic
**Strategic buyers:** FX/remittance platforms (Wise-class), travel finance
products, financial data companies, compliance/RegTech vendors, and AI
companies needing governed jurisdictional grounding data.

**Why not buying is a loss:** any of them can build a converter in a weekend.
None of them can quickly assemble: the dual-register name, a 28,000-page
indexed footprint, a *named public standard* for FX rules integrity, a
source-mapped multi-jurisdiction dataset with a visible governance history, the
category's vocabulary, and an agent-readable citation layer that LLMs already
resolve. The acquisition is not a website — it is the category's language,
standard, dataset, and distribution in one artifact. Leaving it on the market
means a competitor owns the reference layer their own product must then cite.

---

## Part 4 — Execution Sequence

Ordered by leverage; one concern = one PR = one branch (standing rule).

| # | Action | Serves | Layer |
|---|---|---|---|
| P0 | Repair the 16 validation-failed country files; publish what passes the gate | R3, pillar 4 | 7 |
| P1 | Publish `/governance/` (protocol + CRIS v1.0 named standard) | Trust, pillar 6/12 | 4, 5, 8 |
| P2 | Publish `/ontology/` — 8 Currency Passage class pages | Language ownership, pillar 13 | 2, 3 |
| P3 | Build **Passage Check** engine over dataset.json; outputs link to class + country pages | Factory conversion | 6 |
| P4 | Pair-page enrichment pass (jurisdictional links, pair-specific data) | R1, pillar 3/7 | 7, 9 |
| P5 | Rate-source fallback snapshot (R2) | Reliability | 7 |
| P6 | Launch Passage Briefs + commercial dataset license page | Pillar 5 income | 10 |
| P7 | Passage Check API (metered) | Agentic revenue | 6, 10 |
| P8 | Coverage expansion to G20+ | Inevitability, pillar 13/14 | 7 |

Every step must pass the existing quality gate; no step may introduce
unpublished URLs to the sitemap, fracture a link, or attach income to governed
claims. The factory's rule is unchanged: **governed intelligence first,
distribution second, income as an extension of reference — never a tax on it.**
