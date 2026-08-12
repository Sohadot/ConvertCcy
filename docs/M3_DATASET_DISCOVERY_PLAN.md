# Commercial Discovery Experiment — Milestone 3 (Dataset-Native Passive Discovery)

> One-line charter: **Place the governed dataset where buyers already look for
> data, then measure real commercial intent — not downloads — over a fixed
> passive-observation window, with a hard build cap and no new product built
> until intent is demonstrated.**

This document is a governance plan, not an implementation. It records the M3
decision so that the build that follows is bounded by it. Nothing here
authorizes new product surface area beyond the artifacts listed in §5–§8.

---

## 1. Purpose

M3 tests one commercial hypothesis and only one:

> If the governed ConvertCCY currency-rules dataset is present, as a
> citable dataset, in the places where data buyers and data-consuming agents
> already search for datasets, then genuine commercial demand (licensing,
> integration, expanded coverage, redistribution, API, pricing inquiry) will
> surface on its own — without paid audience building and without a personal
> distribution channel standing between the asset and the buyer.

M3 replaces the earlier commercial-experiment posture:

- **From:** *Audience-led discovery* — demand is manufactured by pushing the
  asset through a personal/owned channel (the LinkedIn-style funnel), which
  measures the channel, not the asset.
- **To:** *Dataset-native passive discovery* — the asset is published as a
  first-class dataset in dataset-native surfaces, and demand is observed
  passively.

The strategic reason for the switch: dataset-native surfaces
(Google Dataset Search, Hugging Face, Zenodo) are built specifically to
discover pages that *describe datasets* via structured metadata. If a buyer
finds the asset because the data was sitting where they look for data, that is
a far stronger demand signal than a buyer who had to pass through the founder's
personal feed or marketing content first.

This milestone is deliberately small. It is a commercial *experiment*, not a
new marketing programme disguised as a test.

---

## 2. Explicit non-goals (hard boundaries)

These are non-negotiable for the duration of M3. Crossing any of them
converts the experiment into a product build, which is exactly what M3 is
designed to defer until intent is proven.

- **Build cap: 12 hours of build effort, total.** If an artifact cannot be
  produced inside the cap, it is cut, not extended.
- **No API build.** The existing static agent interface (`/api/v1/…`) stands
  as-is; M3 adds no server, no metering, no authentication.
- **No dashboard.** No analytics UI, no admin surface.
- **No accounts / no auth / no login.**
- **No Stripe / no payment integration / no checkout.**
- **No Monitor / no scheduled polling job** to babysit the experiment.
- **No additional datasets** built "to improve the experiment." Coverage is
  frozen at what already exists in the published governed layer.
- **No LinkedIn dependence** and no dependence on any personal channel as the
  discovery mechanism. The founder's channel may *link* to the asset, but the
  experiment must not require it to succeed.

M3 does **not** extend automatically. There is no rollover to a 180-day
window (see §9).

---

## 3. M3-0 — Measurement contract (mandatory, unchanged in principle)

The measurement contract established in prior commercial experiments carries
forward. It is adapted to this channel, not weakened.

### 3.1 Signals we record

| Signal | Meaning | Nature |
| --- | --- | --- |
| `dataset_landing_views` | Views of the canonical dataset landing page | leading |
| `sample_downloads_on_convertccy` | Downloads of the public sample from convertccy.com | leading |
| `huggingface_downloads` | HF-reported dataset downloads | leading |
| `commercial_surface_clicks` | Clicks on the "commercial use / licensing" path | leading |
| `qualified_inquiries` | Inbound asking about commercial use / license / integration / coverage / API / pricing | **decision** |
| `referrer` / `source` | Where the discovery originated | attribution |
| `version` | Dataset version the signal is attached to | attribution |

Hugging Face computes dataset downloads server-side, with approximate
deduplication of repeated pulls from the same client within a short window, so
`huggingface_downloads` is at least an *independent* count not sourced from our
own analytics.

### 3.2 The rule that governs the contract

> **download ≠ demand.**

Downloads, landing views, and citations are **leading indicators only**. They
do not establish willingness-to-pay. 100 downloads prove interest in free
data, not a buyer.

The single terminal success signal is **commercial intent**: a person or
organization asking about commercial use, integration, broader coverage,
update feeds, licensing, API access, redistribution rights, or price.

Everything else is instrumentation.

---

## 4. M3-1 — Canonical dataset + licensing surface

**Artifact:** one page. Not a licensing page with dataset metadata bolted on —
a **canonical dataset landing page** that also carries the two commercial
exits.

### 4.1 Structured metadata

The page embeds a complete `schema.org/Dataset` JSON-LD block. Include as many
of the following as the published data legitimately supports:

`name`, `description`, `creator`, `publisher`, `datePublished`,
`dateModified`, `version`, `identifier`, `license`, `keywords`,
`isAccessibleForFree`, `distribution` / `DataDownload`, `encodingFormat`,
`contentUrl`, `sameAs`, `citation`.

Google does not require all of these. It emphasizes `name` and `description`
and recommends provenance elements — `identifier`, `license`, `sameAs`. Those
provenance fields are the ones that matter most here because ConvertCCY's whole
thesis is source-disciplined provenance.

### 4.2 Two exits, no more

From this page there are exactly two clear destinations:

1. **Open sample** — download the public governed sample (CC BY 4.0).
2. **Commercial use / licensing** — the path that produces `qualified_inquiries`.

No third call-to-action.

---

## 5. M3-2 — Zenodo + Hugging Face

Two dataset-native surfaces, with a deliberate execution order.

### 5.1 Execution order (corrected)

1. **Freeze the sample snapshot** so its content is final.
2. **Reserve a DOI on Zenodo before publishing.** Zenodo allows pre-reserving
   a DOI precisely so it can be embedded inside the record's own files before
   publication; the DOI is only finalized at publication.
3. **Embed the single stable identifier** everywhere the asset describes
   itself:
   - `manifest.json`
   - `README`
   - `CITATION`
   - `schema.org/Dataset` (the `identifier` / `sameAs` fields)
   - Hugging Face dataset card
   - sample metadata
4. **Publish** to both surfaces.

### 5.2 Roles (no surface is the sovereign source)

| Surface | Role |
| --- | --- |
| **Zenodo** | Archival / citation authority (DOI, DataCite propagation) |
| **Hugging Face** | Developer / AI / data discovery surface (Hub-native metadata + downloads) |
| **convertccy.com** | Canonical commercial authority — the sovereign source of the asset |

Neither Zenodo nor Hugging Face is the sovereign source of the asset. Both
mirror; convertccy.com governs. Hugging Face supports Git-based revisions and
tags, so sample releases can be pinned (e.g. `v0.1.0`) without destroying
history — use that instead of overwriting.

---

## 6. M3-3 — Agent-readable discovery (reclassified)

`llms.txt` is included, but classified correctly.

`llms.txt` is **not** an adopted, guaranteed-honored standard. Its own
originating document describes it as a *proposal* to help LLMs use a site's
content at inference time. Therefore:

- **Do not** frame it in governance as *"llms.txt is a buyer acquisition
  channel."*
- **Do** frame it as *"llms.txt is an agent-readable discovery pointer."*

The pointer announces, plainly:

- Governed dataset
- Public sample
- Machine-readable interface
- Dataset documentation
- Zenodo DOI
- Hugging Face dataset
- Commercial licensing
- Contact

This is cheap and sensible. But because there is no standardized, reliable
mechanism today to tell us who consumed `llms.txt` and who did not, **the
success or failure of `llms.txt` alone does not enter the M3 gate.**

---

## 7. Licensing boundary (the critical constraint)

We must **not** publish the commercial product itself to Zenodo / Hugging Face
and then try to sell it.

### 7.1 What we publish

> **ConvertCCY Governed Currency Rules — Public Sample Dataset.**

A limited, clear, citable sample. This is the free artifact.

### 7.2 What is sold later

Broader coverage **plus** structured commercial distributions, an update feed,
change history, higher-frequency verification, an SLA, integration/embedding
rights, and commercial support.

This separation matters especially because ConvertCCY already has a public
governed data layer. The commercial offer must never reduce to *"pay to get the
same JSON that is already free."* The paid tier is a different product surface,
not a paywall on the sample.

---

## 8. M3 — 90-day passive discovery observation window

The window is **90 days**. Its rationale is recorded precisely, because the
rationale governs how the window is interpreted.

> The 90 days are **not** a claim that indexes need 90 days to index.

- Zenodo metadata becomes searchable after publication and propagates to
  DataCite alongside DOI registration.
- Hugging Face makes the dataset repo and its metadata part of Hub discovery
  directly.

The 90 days are a **Passive Discovery Observation Window** — time for the
ecosystem to do its own work:

Google crawling + Dataset Search discovery + Hugging Face discovery +
DOI/DataCite propagation + organic linking + agent/developer discovery.

This framing is more honest than asserting a "90-day indexing delay."

---

## 9. M3 Gate — decision after 90 days

The gate is deliberately strict. Downloads do not open it.

| Outcome | Condition | Decision |
| --- | --- | --- |
| **PASS** | Real commercial intent surfaced — licensing, API, integration, expanded coverage, redistribution, pilot, or pricing inquiry | Proceed to a **paid pilot** |
| **WEAK SIGNAL** | Downloads / usage / citations appeared, but **no** commercial intent | **No product build** |
| **CHANNEL NOT DEMONSTRATED** | Not even meaningful discovery occurred | **No product build** |

Under no outcome does M3 auto-extend to 180 days.

---

## 10. Execution DAG

```
M3-0
Measurement contract
        │
        ▼
M3-1
Canonical Dataset + Licensing Surface
(schema.org/Dataset + public governed sample)
        │
        ├───────────────┐
        ▼               ▼
M3-2a               M3-2b
Zenodo              Hugging Face
DOI / DataCite      Dataset Hub
        │               │
        └───────┬───────┘
                ▼
M3-3
Agent-readable discovery
(llms.txt + machine links)
                │
                ▼
      90-day observation window
                │
                ▼
        COMMERCIAL INTENT?
          │            │
         YES           NO
          │            │
     Paid pilot      STOP
```

---

## 11. Constraints (locked, repeated for enforcement)

- Build cap: **12 hours**.
- No API build.
- No dashboard.
- No accounts.
- No Stripe.
- No Monitor.
- No additional datasets to "improve the experiment."
- No LinkedIn / personal-channel dependence.

---

## 12. Why this fits ConvertCCY

If M3 succeeds, the buyer will have found the asset **because the data itself
was where buyers look for data** — not because they were routed through a
personal feed or marketing content first. For a governed, versioned,
provenance-disciplined asset, dataset-native discovery is the demand test that
matches the product. This is a genuine commercial experiment for ConvertCCY,
not a new marketing programme wearing the costume of a test.
