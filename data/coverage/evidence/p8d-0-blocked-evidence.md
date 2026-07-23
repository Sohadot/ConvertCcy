# P8D-0 — Blocked Evidence Acquisition

**Phase type:** independent evidence acquisition. Read-only with respect to the
governed layer. This document records claim-specific, **page-pinpointed** source
passages for the fields currently marked `[HARDENING]` on the United States and
South Africa. It changes **no** country status, **no** rule content, and
publishes nothing. It is the input for an independent review; only a **later,
separate phase** may apply this evidence to clear the markers and re-take either
country to the readiness gate.

**Date compiled:** 2026-07-23.

## Why this phase exists

The recurring blocker on both countries was never the absence of sources — it
was the inability to extract specific pages/passages from the governing PDFs
(no `poppler`, and the system `cryptography`/`_cffi_backend` binding was broken,
which also broke every Python PDF library).

**Resolution (tooling):** installed `pdfminer.six` (pure-Python) **and** a
working userspace `cffi` + `cryptography` (replacing the broken system binding).
Both target PDFs then extracted as fully machine-readable text (not image scans).

- Extraction tool: `pdfminer.six 20260107`.
- Method: per-page `extract_pages` → `LTTextContainer` text, page numbers are the
  PDF's own 1-based page order (the printed folio, where it differs, is noted).

---

## A. United States — OECD Code of Liberalisation of Capital Movements, Annex B

**Source PDF:** OECD Code of Liberalisation of Capital Movements (compiled
edition, © OECD 2026).
**URL:** https://www.oecd.org/content/dam/oecd/en/topics/policy-issues/investment/Code-capital-movements-EN.pdf
**Provenance:** SHA-256 `841dfe37902cc77052adb1c7ddc8922616e3bbf3d255f2a1f3157addc768cb74`; 173 pages; downloaded 2026-07-23.
**Companion legal instrument:** Decision of the Council Adopting the Code of
Liberalisation of Capital Movements (OECD/LEGAL/0002),
https://legalinstruments.oecd.org/public/doc/249/249.en.pdf

**Location of the US reservation record:** Annex B, heading **UNITED STATES**,
PDF **page 134** (printed folio "ANNEX B. │ 133"). The entire US reservation
schedule fits on that one page; page 135 begins Annex C.

### Exact reservation text (page 134)

> **UNITED STATES**
> **List A, I/A — Direct investment:** In the country concerned by non-residents.
> Remark: The reservation applies only to investment in: i) atomic energy;
> ii) broadcasting (radio and television), common carrier, aeronautical en route,
> or aeronautical fixed radio station licenses as provided for in 47 United States
> Code § 310, unless an authorisation is granted under 47 United States Code
> § 310(b)(4); iii) air transport; iv) coastal and domestic shipping (including
> dredging and salvaging in coastal waters and transporting offshore supplies from
> a point within the United States to an offshore drilling rig or platform on the
> continental shelf); v) ocean thermal energy, hydroelectric power, geothermal
> steam or related resources on federal lands, mining on federal lands or on the
> outer continental shelf or on the deep seabed, fishing in the "Exclusive Economic
> Zone", and deepwater ports, except through an enterprise incorporated in the
> United States; vi) branches of foreign insurance companies, to the extent that
> they are not permitted to provide surety bonds for US government contracts.
>
> **List A, IV/B1, B2 — Operations in securities on capital markets:** Issue
> through placing or public sale of foreign securities on the domestic capital
> market. Remark: The reservation applies only to the use of small business
> registration forms and a small issues exemption by non-resident issuers.
> Introduction of foreign securities on a recognised domestic capital market.
> Remark: The reservation applies only to the use of small business registration
> forms and a small issues exemption by non-resident issuers.

### What this evidence establishes (for review)

The United States lodges **only** two narrow reservation classes under the
Capital Movements Code: (1) **sectoral inward direct investment** limited to
enumerated strategic/national-security sectors, and (2) a **small-issues
securities-registration** carve-out for non-resident issuers. There is **no**
reservation touching residents'/non-residents' ability to hold foreign currency,
convert, transfer, or repatriate funds. Read with the already-cited IMF 2026
Article IV Informational Annex (current-account, Article VIII), this is the
claim-specific capital-account record that the `[HARDENING]` markers were waiting
for.

**Bearing on the three US `[HARDENING]` fields:**
- `resident_holding_rules` — no OECD capital-account reservation restricts resident foreign-currency holding/transfer. Supports the framework claim; the only US reservations are inward-FDI-sectoral + small-issues securities.
- `non_resident_rules` — the sole non-resident-facing reservations are the sectoral inward-FDI list and the small-issues securities-registration carve-out; nothing restricts non-resident account operation, transfer, or repatriation generally.
- `banking_conversion_practicality` — no OECD reservation on capital-movement convertibility/availability; consistent with a liberalised capital account.

**Caveat for the reviewer:** the reservation text is national-treatment/market-access on inward investment and securities *issuance*; it is not itself a positive statement that "all account access is unrestricted." The honest framing to apply in the later phase is "the US maintains no capital-movement exchange controls beyond the enumerated sectoral inward-investment and small-issues securities reservations," not an absolute "everything is free."

---

## B. South Africa — Currency and Exchanges Manual for Authorised Dealers

**Source PDF:** Currency and Exchanges Manual for Authorised Dealers, South
African Reserve Bank, Financial Surveillance Department.
**Version on the live PDF:** **2026-06-25** (cover page) — **newer** than the
`2026-05-15` version referenced in earlier phases; the later phase should update
the version string accordingly.
**URL:** https://www.resbank.co.za/content/dam/sarb/what-we-do/financial-surveillance/financial-surveillance-documents/2026/Currency%20and%20Exchanges%20Manual%20for%20Authorised%20Dealers.pdf
**Provenance:** SHA-256 `b949e4372588c287e18cadf5d7d632e157e9ff5d3b4513e14b74b561ab72c494`; 298 pages; downloaded 2026-07-23.
**Landing page (already a source authority):** https://www.resbank.co.za/en/home/what-we-do/financial-surveillance/financial-surveillance-documents

### B.1 Resident allowances — `resident_holding_rules`

**Single discretionary allowance (SDA) = R2 million per calendar year** (page 102,
section B.4):

> "...single discretionary allowance limit of R2 million. ... an allowance within
> the single discretionary allowance limit of R2 million per calendar year..."

**Foreign capital allowance (FCA) = R10 million per applicant per calendar year**,
and the two allowances are the binding annual caps (page 111):

> "The annual limit of the R2 million single discretionary allowance and the
> R10 million foreign capital allowance dispensations may not be exceeded."

FCA confirmed again at page 48 ("...invest in excess of the R10 million foreign
capital allowance limit..."). Both allowances run through **Authorised Dealers**
and are subject to a **Tax Compliance Status (TCS) process at SARS** (pages 48,
87, 111).

> **Correction recorded:** the SDA is **R2 million**, not the "R1 million" that
> an unsourced draft might assume. The later phase must use R2 million / R10 million.

### B.2 Travel allowance (traveller framing)

Travel allowance for residents is provided **within the R2 million SDA** (page
100); minors under 18 get a separate travel allowance **not exceeding R400 000
per calendar year** (page 100):

> "(ii) Travel allowance limits (a) Foreign currency may be made available within
> the single discretionary allowance limit of R2 million per calendar year...
> (b) Residents (natural persons) who are under the age of 18 years may be accorded
> a travel allowance not exceeding an amount of R400 000 per calendar year."

> **Important non-conflation finding:** the Manual's own **"R25 000"** (pages 23
> and 113) is an **ADLA money-transfer service cap** ("R5 000 per transaction per
> day within a limit of R25 000 per applicant per calendar month"), **not** the
> traveller rand-carrying limit. The traveller **R25 000** rand-carrying limit and
> the **R100 000** excess-currency rule remain correctly sourced to the **SARS**
> Departure / Travellers pages (as set in P8C-2). Do **not** re-source those two
> traveller figures to this Manual.

### B.3 Non-resident rules — `non_resident_rules`

Exchange controls on non-residents have been **abolished**, and non-resident
income/securities proceeds are **freely transferable** (page 197):

> "(bb) since all income due to non-residents on their securities is freely
> transferable... (cc) since exchange controls on non-residents have been
> abolished..."

Non-residents transact through **Non-resident Rand accounts** and **vostro
accounts** held by the Authorised Dealer (pages 120, 197). Funds introduced from
abroad may be **re-transferred** (page 118):

> "...they may be permitted to retransfer funds introduced from abroad."

### B.4 Banking/dealer practicality — `banking_conversion_practicality`

Transactions run through **Authorised Dealers**, with **FIC Act** customer due
diligence expressly cited (page 113, "...in terms of section 21 of the FIC Act..."),
and all transactions reported via the SARB **Reporting System** with purpose codes
(page 99, "...reporting the transaction on the Reporting System... indicated in the
subject field as 'SDA'..."). This substantiates the licensing/documentary/reporting
and FICA elements of the field at page-pinpointed level.

### Bearing on the three SA `[HARDENING]` fields

- `resident_holding_rules` — **clearable**: R2m SDA (p.102/111), R10m FCA (p.48/111), TCS-at-SARS, via Authorised Dealers.
- `non_resident_rules` — **clearable**: non-resident exchange controls abolished, income freely transferable, Non-resident Rand/vostro accounts, retransfer of introduced funds (p.118/120/197).
- `banking_conversion_practicality` — **clearable**: Authorised Dealer framework, FIC Act s.21 CDD (p.113), SARB Reporting System (p.99).

---

## C. Scope boundary held by this phase

- No `data/rules/*.json` content or `page_status` changed.
- No `data/coverage/g20-expansion-candidates.json` status changed (US and South Africa remain `source_review_ready`).
- No publication, no public route, no sitemap / API / Passage Check / llms.txt change; no other country touched.
- This document is an internal evidence record under `data/coverage/evidence/`; it is not a public surface and exposes no candidate as covered content.

## D. Recommended next phases (for the manager's decision — not executed here)

1. **Independent review** of the passages above against the cited pages.
2. **P8C-2b — South Africa hardening close:** apply B.1–B.4 to clear the three SA markers; update the Manual version string to 2026-06-25; keep the traveller R25 000 / R100 000 SARS-sourced; then re-take South Africa to the readiness gate.
3. **P8B-2c — United States hardening close:** apply the Annex B page-134 record to clear the three US markers under the honest framing in A; then re-take the United States to the readiness gate.

Publication and any `publish_ready` advance remain governed by the consistency
rule adopted in P8C-2a: no unresolved `[HARDENING]` on a public rule field may
coexist with `publish_ready` absent an explicit governance exception.
