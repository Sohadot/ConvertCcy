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
   level requires it.
2. **As-of date** — the date the source was verified as current, and (where the
   source states it) the source's own effective/amendment date.
3. **Evidence level** — `E0`–`E3` per §3.
4. **Known gap** — what remains unverified for this claim. For `E0` this may be
   "none identified"; for `E3` it is the verification target.

A claim missing any of the four is not publishable. `not_published` claims
should still carry as many of the four as are known, so the intake ledger is
complete before surfacing.

---

## 5. Source hierarchy and AREAER placement (CRES layer)

Sources are ranked. A higher tier, when available and claim-specific, is
preferred; a lower tier may *raise confidence* or *fill a gap* but does not
override a higher tier.

```
1. Primary Authority      national legal instrument / official regulator text
        ↓
2. AREAER                 IMF Annual Report on Exchange Arrangements & Restrictions
        ↓                 — discovery / cross-check / gap-detection layer only
3. Institutional          central bank / ministry / supervisor guidance; official translations
        ↓
4. Other references       reputable secondary material (never sole support for a mandatory claim)
```

**AREAER is never a publication authority.** Its role is strictly:

- **Discovery** — surfacing claims to then confirm against primary authority;
- **Cross-check** — corroborating a claim already found elsewhere;
- **Gap detection** — revealing where a claim is missing or stale.

AREAER is **never a final source when a claim-matched primary or institutional
source exists**, and a claim supported *only* by AREAER is capped at `E2` and
MUST NOT be published as an asserted rule on the strength of AREAER alone.

**AREAER licensing clause (mandatory).** *Compliance with IMF licensing and
reuse terms is mandatory before incorporating AREAER-derived content or
metadata.* The cleared/undetermined licensing status MUST be recorded on the
source entry. Absent a cleared licence, AREAER may be used for internal
discovery/cross-check/gap-detection only and MUST NOT be reproduced — content or
metadata — on any public surface.

**Regime-separation rule (CRES-specific).** Distinct legal regimes MUST NOT be
conflated within or across claims — e.g. customs border declaration ≠
foreign-exchange regulation ≠ bank/intermediary reporting ≠ AML/FIU reporting ≠
tax reporting ≠ domestic cash-payment limits. Each is its own claim with its own
evidence.

---

## 6. Source language and translation metadata

Every source entry declares its language and translation standing, so a reader
(human or machine) can weigh it:

```json
{
  "language": "es",
  "machine_translation": true,
  "translation_verified": false
}
```

- A **non-binding** or **machine** translation may support at most `E1`, and
  only when the underlying primary text is cited alongside it; the binding
  primary-law citation in its original language is always retained.
- `translation_verified: true` requires a recorded human check against the
  original.

This is the structured form of a distinction ConvertCCY already makes in prose
(e.g. a non-binding reference translation cited *alongside*, and clearly
subordinate to, the official primary text).

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
attributes, translation metadata on each source, and a history array:

```jsonc
"source_map": {
  "resident_holding_rules": {
    "evidence_level": "E3",
    "as_of": "2026-07-28",
    "gap": "Primary FX statute / central-bank circular not yet verified",
    "sources": [
      { "url": "...", "pages": [], "section": "...",
        "language": "es", "machine_translation": false, "translation_verified": true }
    ],
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
- **AREAER — never a publication authority.** Discovery / cross-check /
  gap-detection only; capped at `E2`; IMF licensing/reuse compliance mandatory
  before incorporating any AREAER content or metadata (§5).
- **Three independent axes.** Evidence, Publication, and Indexing are orthogonal;
  no axis determines another (§2).
