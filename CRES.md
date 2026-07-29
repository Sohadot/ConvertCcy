# Currency Reference Evidence Standard (CRES) — v0.1 (DRAFT)

**Status:** v0.1 DRAFT. Normative *principles* are fixed in this document; the
*data-model* and *gate* implementations are illustrative only and deferred to a
later phase. **This document changes no schema, no country data, and no public
surface.** It is a governance specification, not code.

**Relationship to a general standard.** CRES is the currency-domain instance of
a domain-neutral pattern, the **Reference Evidence Standard (RES)**. Everything
in §§2–8 that does not mention currency, foreign exchange, or a specific
authority is RES core and may be lifted verbatim by other reference assets. The
currency-specific parts (source hierarchy examples, AREAER placement, the
regime-separation rule) are the CRES layer on top.

---

## 1. Purpose

ConvertCCY does **not** publish "the rule." It publishes **the evidence and its
strength**. The unit of truth is not the page and not the country — it is the
individual **claim**.

> We do not assert what the law *is*. We publish what we *found*, when we found
> it, how strong that finding is, and what we still do not know.

This inverts the usual failure mode of a reference database. A database that
asserts rules must either be perfectly current and complete (impossible) or
silently wrong (worse). A database that publishes *evidence and its strength* is
honest at every level of completeness: a fully-evidenced claim and a
not-yet-evidenced claim are both truthful statements, because each exposes its
own standing.

Two failures this standard exists to prevent, both observed in practice:

- **Asserting an unsupported rule.** (e.g. an on-file claim of "Banxico approval
  required" with no source behind it.)
- **Replacing an unsupported claim with the unsupported opposite.** Finding that
  "approval required" is unsupported does **not** license asserting "no approval
  required." The correct result is *the old claim is unsupported; the true rule
  is a verification target.* (§7.)

---

## 2. The three independent axes (core governance rule)

Every claim carries three attributes. **They are orthogonal. No axis determines
another.** This separation is normative and is the heart of the standard.

| Axis | Values | Question it answers |
|---|---|---|
| **Evidence** | `E0` `E1` `E2` `E3` | How strong is the support for this claim? (§3) |
| **Publication** | `published` / `not_published` | Does this claim appear on a public surface? |
| **Indexing** | `index` / `noindex` | May search engines rank this claim? |

Because the axes are independent, all combinations are expressible. Some
deliberately useful ones:

- `E0 · published · index` — a pinpointed primary-law claim, live and rankable.
- **`E3 · published · noindex`** — a *declared knowledge gap*, shown live for
  honesty, but withheld from search ranking until it is evidenced. **This
  combination is valid and is the reason the axes must not be collapsed.**
- `E1 · published · noindex` — official institutional support, live, but held
  back from ranking pending primary-law confirmation.
- `E2 · not_published` — partial evidence retained internally, not yet surfaced.

**Prohibited couplings** (the mistakes this table prevents):

- Evidence level MUST NOT imply a publication state. A low level is not a reason
  to hide a claim; a high level is not a licence to publish it.
- Evidence level MUST NOT imply an indexing state.
- Publication MUST NOT force indexing. A published claim may be `noindex`.

An evidence standard is not a publication policy and not an SEO policy. CRES
governs the **Evidence** axis normatively and only *constrains* the other two
(see §6, §9); the publication and indexing policies are separate documents that
consume the Evidence axis without being merged into it.

---

## 3. Evidence levels (E0–E3)

Levels are assigned **per claim, never per page**. A page never inherits a
single level: it is a container of independently-graded claims and routinely
carries mixed levels (e.g. a customs threshold at `E0`, a resident-account rule
at `E3`). Each claim carries its own Evidence level, Source, As-of date, and
Known gap (§4) — the page-level status is only a projection of its claims.

| Level | Name | Definition | Currency example |
|---|---|---|---|
| **E0** | Pinpointed primary authority | The controlling national legal instrument, cited to the article/section/paragraph, with an as-of date, **directly on the claim**. | Ley Aduanera (MX) Art. 9o — mandatory declaration exceeding USD 10,000. |
| **E1** | Official institutional / official translation | A claim-specific official source that is *not* the primary legal text: central-bank / ministry / regulator guidance, or an official (even if non-binding) translation of the primary law. | Bank of Korea "Foreign Exchange System" guidance; KLRI English reference translation of FETA (non-binding). |
| **E2** | Partial / indirect | The framework is verified but the *specific* claim is not yet pinpointed; or only a comparison/verification layer (e.g. AREAER) supports it; or a primary source supports a *broader* fact from which the claim is inferred but not stated. | "A free-floating regime is verified" used to support a claim *about capital-movement restrictions* — the mechanism is E-verified, the restriction claim is not. |
| **E3** | Not yet evidenced | No claim-matched source has been verified. The field is **not empty and never asserts a rule**; it publishes an explicit gap statement: *what we do not yet know and why.* | "Resident foreign-currency-account rules: not yet evidenced — primary regulatory source not verified." |

**E3 is a first-class, publishable state, not an absence.** An E3 field renders,
when published, as:

```
Resident holding rules
  Status:          Not yet evidenced
  Evidence level:  E3
  Reason:          Primary regulatory source not yet verified
  As-of:           2026-07-28
  Verification target: national FX statute / central-bank circular
```

**Level down-grade rule.** A claim inherits the level of its *weakest necessary
support for that exact proposition*. Verifying a broad fact (a float regime)
does not raise a narrower claim (absence of controls) above `E2`/`E3`; it must
have its own claim-matched source to reach `E1`/`E0`. This is the Mexico rule of
§7 stated as a grading rule.

---

## 4. The four-part disclosure (mandatory per published claim)

Every **published** claim MUST expose all four, or it fails the gate:

1. **Source** — the citation, to the pinpoint (article/section/page) where the
   level requires it. For `E3`, where no claim-matched source is yet verified,
   this requirement is satisfied by a **declared null-source disclosure** (see
   "E3 and the Source requirement" below) — the slot is never simply omitted.
2. **As-of date** — the date the source was verified as current, and (where the
   source states it) the source's own effective/amendment date. For `E3`, the
   date the gap was last confirmed.
3. **Evidence level** — `E0`–`E3` per §3.
4. **Known gap** — what remains unverified for this claim. For `E0` this may be
   "none identified"; for `E3` it is the verification target.

A claim missing any of the four is not publishable. `not_published` claims
should still carry as many of the four as are known, so the intake ledger is
complete before surfacing.

**E3 and the Source requirement.** An `E3` claim has no verified source, but the
Source slot is **declared, not absent**. The null-source disclosure below
*satisfies* requirement 1, so a published `E3` claim passes this section (and the
`E3 · published · noindex` state of §2 is therefore gate-legal, not — as a naïve
reading of "every published claim MUST expose a Source" would have it —
forbidden):

```json
{
  "evidence_level": "E3",
  "verified_source": null,
  "source_status": "no_claim_matched_source_verified",
  "sources_checked": [],
  "verification_target": "National FX statute or central-bank circular",
  "known_gap": "Resident holding rules not yet evidenced",
  "as_of": "2026-07-28"
}
```

The Source slot does not disappear; it **asserts** that no claim-matched source
is verified as of the date, and records what was checked (`sources_checked`) and
what would resolve the gap (`verification_target`). An `E3` claim MUST NOT be
published without this disclosure, and MUST NOT present any `verified_source`.

---

## 5. Source hierarchy: authority tier × workflow role (CRES layer)

A source has **two independent** properties. Collapsing them into one ranked
list is an error — it lets a comparative layer appear "above" a stronger
authority. CRES keeps them apart.

**Dimension A — Authority tier** (proof strength; sets the *ceiling* on a claim's
evidence level):

```
A1. Primary binding authority             national legal instrument / official regulator text        → up to E0
A2. Official claim-specific institutional  central bank / ministry / supervisor guidance; official translations  → up to E1
A3. Comparative / secondary references     incl. IMF AREAER; reputable secondary material            → capped at E2 (never sole support for a mandatory claim)
```

**Dimension B — Workflow role** (what the source is *used for*; orthogonal to
tier): **discovery**, **corroboration**, or **publication-support**.

Tier and role are independent. IMF **AREAER** is an authority-tier **A3** source
(comparative — it caps a claim at `E2`) whose legitimate roles are **discovery,
cross-check, and gap-detection**. It is strong for *coverage and comparison*
across jurisdictions, but it is **not a higher proof authority than official
central-bank or regulator guidance** (A2), and it is **never a publication
authority**: a claim supported only by AREAER MUST NOT be published as an
asserted rule, and AREAER never overrides a claim-matched A1/A2 source.

Because tier ≠ role, the contradiction of a single "preference" ladder — placing
AREAER *above* institutional guidance while also capping AREAER (`E2`) *below*
institutional (`E1`) — cannot arise: preference for **proof** follows the
authority tier (A1 > A2 > A3), while AREAER's value lives in the **role**
dimension.

**AREAER licensing clause (mandatory).** *Compliance with IMF licensing and
reuse terms is mandatory before incorporating AREAER-derived content or
metadata.* The cleared/undetermined licensing status MUST be recorded on the
source entry. Absent a cleared licence, AREAER may be used for internal
discovery / cross-check / gap-detection only and MUST NOT be reproduced —
content or metadata — on any public surface.

**Regime-separation rule (CRES-specific).** Distinct legal regimes MUST NOT be
conflated within or across claims — e.g. customs border declaration ≠
foreign-exchange regulation ≠ bank/intermediary reporting ≠ AML/FIU reporting ≠
tax reporting ≠ domestic cash-payment limits. Each is its own claim with its own
evidence.

---

## 6. Source language and translation confidence (independent of authority)

Legal-source **authority** and **translation confidence** are two independent
axes and MUST NOT be conflated. Every source entry declares its translation
standing so it can be weighed *separately* from the source's authority tier (§5):

```json
{
  "language": "es",
  "machine_translation": true,
  "translation_verified": false
}
```

**Governing rule.** *Evidence level is determined by the authority that directly
supports the claim (§5). Translation provenance does not upgrade a source and
does not automatically downgrade a binding original source; it creates an
independent translation-confidence disclosure and may create a known gap or a
human-review requirement.*

Consequences:

- A claim tied **directly to a pinpointed binding official legal text**
  (article/section) may remain **`E0`** even when a machine or non-binding
  translation was used as a *reading aid* — provided `translation_verified:
  false` is disclosed and, where the reading is load-bearing, a
  `known_gap: "translation not human-verified"` (or a human-review requirement)
  is recorded. The binding original, in its own language, is always the cited
  authority.
- A **translation alone** — without the binding original, or not matched to the
  specific claim — does **not** reach `E0`. It is at most an A2 official
  institutional source (`E1`), or lower if unofficial.
- `translation_verified: true` requires a recorded human check against the
  original; it raises *translation confidence*, not the evidence level.

This is the disciplined form of a distinction ConvertCCY already makes in prose
— citing the binding primary text as the authority while a non-binding reference
translation is used, clearly subordinate, as a reading aid (e.g. South Korea:
the binding `law.go.kr` FETA text as authority, the KLRI non-binding English
translation as the reading aid, its `translation_verified: false` disclosed).

---

## 7. The unsupported-claim rule (verification targets)

When an on-file or proposed claim is **not** corroborated by a verified source:

1. It is recorded as **unsupported** (not as *false*).
2. Its true value becomes a named **verification target**: the specific
   authority/source type that would settle it.
3. It is **never** replaced with the unsupported opposite. "Claim X is
   unsupported" does not establish "not-X."
4. At the next review it is either **substantiated** (raised to `E0`/`E1`) or
   **removed**.

This rule is normative RES core. It is what keeps an evidence standard from
degrading into an opinion standard.

---

## 8. History / change ledger (per claim)

Each claim carries an append-only history, turning the asset from an
information database into a **reference ledger**. The market says "the rule is
X"; almost no one records *what it was, when it changed, who changed it, and by
what reference.*

**Two ledgers, one location each — never duplicated.**

- **`DECISION_LOG.md`** records *why the project changed* — phase decisions,
  governance rulings, readiness transitions.
- **A claim's `history[]`** records *why that specific claim changed* — its own
  value provenance over time.

Project-level rationale stays in `DECISION_LOG`; claim-level provenance stays in
`history[]`. The same fact is not written in both places: a phase entry may
*reference* a claim change, but the claim's evidentiary history lives only on
the claim.

```json
"history": [
  {
    "as_of": "2026-07-25",
    "value_summary": "Mandatory declaration exceeding USD 10,000 (Ley Aduanera Art. 9o)",
    "evidence_level": "E0",
    "changed_by": "P8G-1",
    "change_source": "diputados.gob.mx Ley Aduanera, última reforma DOF 19-11-2025",
    "note": "Prior on-file value ('USD 10,000 or equivalent') tightened to 'exceeding'."
  }
]
```

Minimum fields per history entry: `as_of`, `value_summary`, `evidence_level`,
`changed_by`, `change_source`. History is never rewritten, only appended.

---

## 9. Non-normative data-model sketch (implementation deferred)

**This section is illustrative only.** It shows how CRES *could* map onto the
existing per-field `source_map` without a disruptive redesign. No part of §9 is
binding in v0.1; the actual schema change is a later, separately-reviewed phase.

Today each `source_map[<field>]` is already a per-field list of
`{url, pages, section}`. CRES extends each field with the four disclosure
attributes, translation-confidence metadata on each source (§6), and a history
array. An **evidenced** field and an **`E3`** field take two shapes — the latter
uses the null-source disclosure of §4 (so translation fields are
confidence-only, never a lever on the evidence level):

```jsonc
"source_map": {
  "cash_declaration_threshold": {          // evidenced — E0
    "evidence_level": "E0",
    "as_of": "2026-07-25",
    "gap": "none identified",
    "sources": [
      { "url": "https://www.diputados.gob.mx/LeyesBiblio/pdf/LAdua.pdf",
        "pages": [1], "section": "Ley Aduanera Art. 9o",
        "language": "es", "machine_translation": true, "translation_verified": false }
      // binding Spanish original is the authority; the machine translation is a
      // reading aid and does NOT lower the level below E0 (§6)
    ],
    "history": [ /* §8 */ ]
  },
  "resident_holding_rules": {              // not yet evidenced — E3 (§4 contract)
    "evidence_level": "E3",
    "as_of": "2026-07-28",
    "verified_source": null,
    "source_status": "no_claim_matched_source_verified",
    "sources_checked": [],
    "verification_target": "National FX statute or central-bank circular",
    "known_gap": "Resident holding rules not yet evidenced",
    "history": [ /* §8 */ ]
  }
}
```

**Relationship to the existing pipeline (for migration planning, not v0.1):**

- The current `[HARDENING]` marker is, in CRES terms, an **`E3`/`E2` verification
  target**. CRES generalizes it into the typed Evidence axis.
- `page_status` (`verified` / `published` …) and `indexing_allowed` are, in CRES
  terms, page-level projections of the per-claim **Publication** and **Indexing**
  axes. A future gate would compute page-level indexability from the claims'
  axes rather than from a single page flag.
- The six-gate publication pipeline remains; a CRES-aware gate would additionally
  assert the four-part disclosure (§4) on every published claim and the
  axis-independence rule (§2).

---

## 10. Governance of the standard itself

- **Versioning.** CRES is versioned (this is v0.1). Normative changes bump the
  version; the changelog lives with the document.
- **CRES vs RES.** The domain-neutral core (§§2, 3, 4, 6, 7, 8 and the axis rule)
  is RES; §5's hierarchy/AREAER/regime-separation and the currency examples are
  the CRES layer. A future `RES.md` may extract the core for reuse by other
  assets.
- **Scope discipline.** Adopting CRES is a standard-first act: this document
  fixes the principles. Applying them to a field, a country, or the schema, and
  enforcing them in the gate, are **separate, later, individually-reviewed
  phases** — none performed here.

---

## 11. Status and next steps

- **v0.1 DRAFT** — principles (§§1–8, §10) normative; data-model (§9) illustrative.
- **No schema, data, or public-surface change** is made by this document.
- Proposed sequence, each its own reviewed phase:
  1. Adopt CRES v0.1 (this document).
  2. Prototype the per-claim model on **one field of one country** (illustrative,
     unpublished).
  3. Schema extension + generator/gate support.
  4. Backfill evidence levels, disclosures, and history across published
     jurisdictions.
  5. Optional: extract `RES.md` for cross-asset reuse.

---

## Decision record (v0.1)

Design decisions fixed for this version:

- **Granularity — claim-level.** Evidence, Source, As-of, and Known gap attach to
  each claim; a page never inherits a single level (§3).
- **History location — on the claim.** `history[]` lives in each claim's data;
  `DECISION_LOG.md` keeps project-level rationale; the two are not duplicated (§8).
- **AREAER — authority tier × workflow role.** Source authority and workflow role
  are separate dimensions; AREAER is an authority-tier **A3** source (capped at
  `E2`) whose roles are discovery / cross-check / gap-detection; it is never a
  publication authority and never outranks a claim-matched A1/A2 source. IMF
  licensing/reuse compliance is mandatory before incorporating any AREAER content
  or metadata (§5).
- **Three independent axes.** Evidence, Publication, and Indexing are orthogonal;
  no axis determines another (§2).
- **E3 is gate-legal.** A published `E3` claim carries a declared null-source
  disclosure (`verified_source: null`, `source_status`, `sources_checked`,
  `verification_target`) that satisfies the four-part Source requirement — so
  `E3 · published · noindex` is permitted, not forbidden (§4).
- **Evidence authority ≠ translation confidence.** The evidence level is set by
  the authority supporting the claim; translation provenance is an independent
  disclosure that neither upgrades a source nor auto-downgrades a binding
  original (a pinpointed binding text stays `E0` with an unverified translation
  aid, the gap disclosed) (§6).
