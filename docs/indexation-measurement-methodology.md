# Indexation Measurement Methodology (SEO-A5.1)

Internal governance document. Not user-facing copy.

> Repository semantics define the intended cohort.
> Sitemap membership exposes that cohort to measurement.
> Google independently decides what it indexes.
> GSC measures Google's response.

The aim is to make indexing outcomes **measurable per semantic cohort**. It is not to push Google to
index everything. This sprint builds the measurement capability. It sets **no** KPI targets and
reports **no** Search Console results, because no Search Console connection exists in the
repository and nothing has been observed yet.

## 1. Sitemap architecture (implemented)

`sitemap.xml` is a sitemaps.org **sitemap index**. `robots.txt` already pointed at it and is
unchanged. The index lists one child sitemap per cohort:

| Child sitemap | Cohort | Membership rule |
|---|---|---|
| `sitemaps/core-pages.xml` | Core public pages | Every indexable URL that is neither a pair page nor a currency hub: home, static and authority pages, ontology, articles, briefs, published rules, and the human API hub |
| `sitemaps/currency-hubs.xml` | Currency hubs | `currencies/<code>.html` |
| `sitemaps/ordinary-fx.xml` | `ordinary_fx` | pair treatment from `generate.pair_semantic_treatment` |
| `sitemaps/historical.xml` | `historical` | as above |
| `sitemaps/precious-metals.xml` | `precious_metal` | as above |
| `sitemaps/institutional-units.xml` | `institutional_unit` | as above |
| `sitemaps/live-fiat-coverage.xml` | `live_fiat_coverage` | as above |
| `sitemaps/rate-regime-governed.xml` | `rate_regime_governed` | as above |

* The URL set is exactly `generate.sitemap_entries()`, which is the existing set of indexable
  surfaces. This layer neither adds nor removes URLs.
* A pair's child is determined by the semantic router, never by a URL list.
* `standards_special` pairs (674 pages, `noindex,follow`) are in **no** sitemap, per the A4.3
  policy. The XTS and XXX hubs stay in `currency-hubs.xml`.
* An unmapped treatment fails closed. `unsupported_specialized` currently holds 0 pages; if it
  ever became non-empty, generation would stop until a cohort is defined for it.
* Inside each child, URLs are sorted lexically. The same repository state always produces
  byte-identical files.
* The largest child, `ordinary-fx.xml`, holds about 20.6k URLs and about 2.3 MB. That is well
  within the protocol limit of 50,000 URLs and 50 MiB per file. Generation fails if a child would
  exceed a limit.

The command is:

```
python3 generate.py --sitemaps-only
```

It writes the index, every child sitemap and the measurement manifest, and renders no page. It
refuses to run while a sitemap URL's source file is uncommitted.
`scripts/generate_sitemap.py` now delegates to it.

## 2. `<lastmod>` semantics

**Diagnosis of the pre-A5.1 behaviour:**

* The dates were taken from `git log --pretty=%cI --name-only --diff-filter=ACMR`, using the first
  committer date seen per path. Merge commits list no files in that form, so content introduced
  only by a merge was never dated. Two such merges exist in this repository's history.
* A modified or untracked file was stamped with the current date, which is a wall-clock value.
* The main reason for stale dates was workflow, not the algorithm. From A2 to A4.6B, sprints
  merged the monolithic sitemap **additively**, keeping existing entries byte-identical. As a
  result, 25,802 URLs kept `2026-09-07` after their pages were rewritten.

**New algorithm (`generate.build_git_content_lastmod_index`).** A URL's `<lastmod>` is the
**UTC date of the newest commit author date at which its rendered file changed**:

* It uses `git log --diff-merges=dense-combined --diff-filter=ACMR --name-only`, which covers
  every commit reachable from HEAD on all parents. A non-merge commit contributes the files it
  changed. A merge commit contributes only files whose merged content differs from **every**
  parent, meaning conflict resolutions and merge-only edits.
* **Author date, not committer date.** The author date is preserved when a pull request is
  merged. Dates computed on the feature branch therefore equal the dates on `main` after the
  merge and on CI's synthetic pull-request merge, so the committed sitemaps stay valid.
* **Clean merges add no dates.** A merge that changes nothing relative to its parents does not
  move any `<lastmod>`.
* **Plain `--first-parent` was rejected.** It would date every pull-request file at the merge
  commit. The pull-request-time sitemaps would then go stale on merge, and CI's synthetic merge
  would date everything at CI time.
* **The newest date per path wins**, independent of log order.
* **Uncommitted files get no date.** A modified or untracked file has no committed content date
  yet, so its `<lastmod>` is omitted. `--sitemaps-only` refuses to run in that state.
* **No clock input.** Wall-clock time, sitemap generation time and filesystem mtime are never used.
* **Index dates.** A child sitemap's `<lastmod>` in the index is the newest `<lastmod>` among its
  URLs.

**Limitations:**

* Every content change to a rendered file counts as meaningful, including
  data-refresh-only changes such as an A3 snapshot refresh. This is by design, because the
  rendered page did change.
* An author date can precede deployment by the pull request's review time.
* A squash or rebase merge strategy would re-date commits. This repository uses merge commits.
* A non-clean CI synthetic merge, where the same file is changed on both sides, would date that
  file at the synthetic merge. Rebase the branch and rerun `--sitemaps-only`.

**Workflow:**

1. Commit the page changes.
2. Run `python3 generate.py --sitemaps-only`.
3. Commit the sitemaps.

`scripts/validate_semantic_sitemaps.py` rebuilds every file from history and fails on any
difference.

## 3. Measurement manifest

`data/generated/sitemap_measurement_manifest.json` is generated with the sitemaps and holds no
clock values. Per child it records:

* the file and URL;
* the cohort kind and router treatment;
* `url_count` (the **denominator**);
* the indexability requirement;
* representative URLs (first, middle and last, lexically);
* the newest and oldest content `lastmod`;
* the number of URLs without a `lastmod`;
* the size in bytes;
* for core pages, a per-section breakdown.

It also records:

* the repository's pair cohorts (all 28,730 pages by treatment);
* the excluded treatments and their reason;
* the router precedence;
* the `lastmod` semantics;
* totals.

It is not a public SEO claim and not a Search Console result.

## 4. Measuring after deployment

The steps below are performed by a person in Google Search Console. The repository cannot read
Search Console.

1. Deploy, and confirm that `https://convertccy.com/sitemap.xml` and every `sitemaps/*.xml` file
   are served with HTTP 200.
2. In Search Console, submit `https://convertccy.com/sitemap.xml` under **Sitemaps**. Search
   Console reads the index and lists each child sitemap. Child sitemaps may also be submitted
   individually, but that is not required.
3. Allow Google time to process them. Record each child's "Discovered pages" count and its
   status.
4. Open **Indexing → Pages** and use the sitemap filter, choosing "All submitted pages" and then
   each child sitemap in turn. For each child, record the following.
   * the **Indexed** count;
   * the **Not indexed** count, broken down by reason: "Crawled – currently not indexed",
     "Discovered – currently not indexed", "Duplicate…", "Excluded by noindex", and so on;
   * the observation date;
   * the manifest's `url_count` for that child, together with the repository commit SHA, so the
     denominator is reproducible.
5. Repeat at a fixed cadence, for example every 2–4 weeks. Compare only cycles that use the same
   denominator definition. If a cohort's `url_count` changed between cycles, record that change
   alongside the results.

### Observation table (to be filled from Search Console; no values are assumed)

| Cohort (child sitemap) | Repository URLs (manifest) | GSC indexed | GSC not indexed | of which crawled – currently not indexed | Coverage % | Observation date | Commit |
|---|---:|---:|---:|---:|---:|---|---|
| Core pages | 82 | | | | | | |
| Currency hubs | 170 | | | | | | |
| Ordinary FX | 20,592 | | | | | | |
| Historical | 2,296 | | | | | | |
| Precious metals | 1,268 | | | | | | |
| Institutional units | 1,540 | | | | | | |
| Live-fiat coverage | 602 | | | | | | |
| Rate-regime governed | 1,758 | | | | | | |

The repository counts above match the manifest at this sprint's commit. For later cycles, always
take the counts from the manifest of the deployed commit.

### Metrics

* **Indexation rate** = GSC indexed URLs ÷ sitemap cohort URLs.
* **Crawled-not-indexed rate** = "Crawled – currently not indexed" ÷ sitemap cohort URLs.
* **Cohort improvement** = the change in indexation rate between two cycles that use the same
  denominator definition.
* **Hub-to-pair contrast** = the indexation rate of currency hubs compared with each pair cohort.

No targets are set here. Targets should be chosen only after several observation cycles provide
evidence.

## 5. Baseline GSC context (historical)

The original aggregate figure was a point-in-time Search Console total:

| Status | Count |
|---|---:|
| Crawled — currently not indexed | 7,173 |
| Redirects (intentional 301s: `_redirects`, http→https, www→apex) | 1,165 |
| Redirect error | 1 |
| Not found (404) | 1 |
| **Total** | **8,340** |

> **"8,340 → 0" is not a valid programme success metric.** That total includes intentional
> redirects and deliberate `noindex` pages, and its URL population was never exported.

The semantic sitemaps replace that aggregate with per-cohort denominators. Each cohort can be
measured against itself over time.

## 6. Gates

* `scripts/validate_semantic_sitemaps.py` (Governance Gate) checks:
  * the index's validity and its children;
  * cohort membership against the router;
  * that the URL union equals the indexable set;
  * that no URL is listed twice;
  * that no standards_special, noindex, redirected or non-canonical URL is listed;
  * hub and core-page placement;
  * ordering and the 50,000-URL and 50 MiB limits;
  * `lastmod` validity and the index `lastmod`;
  * byte equality with the generator output, including the manifest.
* Existing validators that assert sitemap membership now read the union of child sitemaps
  (`generate.read_sitemap_locs`), so their assertions are unchanged.
* `tests/test_semantic_sitemaps.py` includes real-git regression tests for:
  * a merged pull request;
  * merge-only content;
  * a CI synthetic merge;
  * an unchanged file;
  * the newest change winning;
  * uncommitted files getting no clock date.
