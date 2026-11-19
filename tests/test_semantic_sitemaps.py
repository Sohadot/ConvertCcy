#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEO-A5.1 — semantic sitemap index, content-aware lastmod and the measurement manifest.

Locks in:
  * cohort classification: each pair treatment maps to exactly one child sitemap; standards pairs
    to none; an unmapped treatment fails closed
  * exhaustiveness / exclusivity: every indexable URL exactly once; hubs and core pages placed
  * URL-set preservation against the pre-A5.1 monolithic sitemap (baseline dc5e66697)
  * lastmod: plain commit, merged PR (no stale pre-change date), merge-only content, unchanged
    file, newest change wins, CI synthetic merge adds nothing, deterministic output, no clock
  * index lastmod = newest child lastmod; manifest consistency; idempotent generation
  * semantic freeze: no page or hub differs from the baseline
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
for p in (REPO, REPO / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import generate as g  # noqa: E402

BASELINE = "dc5e6669768c22f77dcfc5466415aab8273cf78e"   # main before SEO-A5.1 (PR #139 merged)
PROFILES = g.load_pair_profiles()
FX = g.load_rate_snapshot()
HISTORY, DIRTY, _, _ = g.build_git_content_lastmod_index(REPO)
DIRTY_SOURCES = sorted(rel for _, rel in g.sitemap_entries(PROFILES) if rel in DIRTY)


def git_show(rev, rel):
    out = subprocess.run(["git", "show", f"{rev}:{rel}"], cwd=REPO, capture_output=True, text=True)
    return out.stdout if out.returncode == 0 else None


class CohortClassificationTest(unittest.TestCase):
    def test_treatment_mapping(self):
        self.assertEqual(g.PAIR_SITEMAP_COHORTS, {
            "ordinary_fx": "ordinary-fx", "historical": "historical", "precious_metal": "precious-metals",
            "institutional_unit": "institutional-units", "live_fiat_coverage": "live-fiat-coverage",
            "rate_regime_governed": "rate-regime-governed"})
        self.assertEqual(set(g.SITEMAP_EXCLUDED_TREATMENTS), {"standards_special"})
        self.assertEqual(len(set(g.SITEMAP_COHORT_ORDER)), len(g.SITEMAP_COHORT_ORDER))

    def test_every_pair_in_its_router_cohort(self):
        cohorts = g.semantic_sitemap_cohorts(PROFILES, FX)
        where = {u: n for n, rows in cohorts.items() for u, _ in rows}
        for p in PROFILES.values():
            a, b = p["from_code"], p["to_code"]
            if a == b:
                continue
            url = f"{g.BASE_URL}/pages/{p['pair_slug']}.html"
            t = g.pair_semantic_treatment(a, b, FX)
            if t == "standards_special":
                self.assertNotIn(url, where)
            else:
                self.assertEqual(where[url], g.PAIR_SITEMAP_COHORTS[t], url)

    def test_unmapped_treatment_fails_closed(self):
        real = g.pair_semantic_treatment
        with mock.patch.object(g, "pair_semantic_treatment",
                               side_effect=lambda a, b, s=None: "unsupported_specialized" if (a, b) == ("USD", "EUR") else real(a, b, s)):
            with self.assertRaises(ValueError):
                g.semantic_sitemap_cohorts(PROFILES, FX)

    def test_counts_regression_guard(self):
        # Regression guard for the repository state this sprint was built on (not used by the generator).
        cohorts = g.semantic_sitemap_cohorts(PROFILES, FX)
        self.assertEqual({n: len(r) for n, r in cohorts.items()}, {
            "core-pages": 82, "currency-hubs": 170, "ordinary-fx": 20592, "historical": 2296,
            "precious-metals": 1268, "institutional-units": 1540, "live-fiat-coverage": 602,
            "rate-regime-governed": 1758})


class CommittedSitemapsTest(unittest.TestCase):
    def test_index_lists_every_child_once(self):
        index = (REPO / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("<sitemapindex", index)
        locs = re.findall(r"<loc>([^<]+)</loc>", index)
        self.assertEqual(locs, [g.sitemap_child_url(n) for n in g.SITEMAP_COHORT_ORDER])

    def test_exhaustive_and_exclusive(self):
        seen = Counter()
        for n in g.SITEMAP_COHORT_ORDER:
            seen.update(re.findall(r"<loc>([^<]+)</loc>", (REPO / "sitemaps" / f"{n}.xml").read_text(encoding="utf-8")))
        self.assertEqual([u for u, c in seen.items() if c > 1], [])
        self.assertEqual(set(seen), {u for u, _ in g.sitemap_entries(PROFILES)})

    def test_standards_pairs_absent(self):
        locs = set(g.read_sitemap_locs(REPO))
        n = 0
        for p in PROFILES.values():
            if p["from_code"] != p["to_code"] and g.pair_semantic_treatment(p["from_code"], p["to_code"], FX) == "standards_special":
                self.assertNotIn(f"{g.BASE_URL}/pages/{p['pair_slug']}.html", locs)
                n += 1
        self.assertEqual(n, 674)

    def test_hubs_and_core(self):
        hubs = re.findall(r"<loc>([^<]+)</loc>", (REPO / "sitemaps" / "currency-hubs.xml").read_text(encoding="utf-8"))
        self.assertEqual(hubs, sorted(f"{g.BASE_URL}/currencies/{f.name}" for f in (REPO / "currencies").glob("*.html")))
        core = re.findall(r"<loc>([^<]+)</loc>", (REPO / "sitemaps" / "core-pages.xml").read_text(encoding="utf-8"))
        self.assertIn(f"{g.BASE_URL}/", core)
        self.assertFalse(any("/pages/" in u or "/currencies/" in u or "/docs/" in u or "/preview/" in u for u in core))

    def test_url_set_preserved_from_monolithic_sitemap(self):
        old = git_show(BASELINE, "sitemap.xml")
        if old is None:
            self.skipTest("baseline commit not available")
        self.assertIn("<urlset", old)
        self.assertEqual(set(g.read_sitemap_locs(REPO)), set(re.findall(r"<loc>([^<]+)</loc>", old)))

    def test_index_lastmod_is_newest_child_lastmod(self):
        index = (REPO / "sitemap.xml").read_text(encoding="utf-8")
        for loc, lastmod in re.findall(r"<loc>([^<]+)</loc>\n    <lastmod>([^<]+)</lastmod>", index):
            child = (REPO / loc[len(g.BASE_URL) + 1:]).read_text(encoding="utf-8")
            self.assertEqual(lastmod, max(re.findall(r"<lastmod>([^<]+)</lastmod>", child)))

    def test_robots_txt_points_to_index(self):
        self.assertIn("Sitemap: https://convertccy.com/sitemap.xml", (REPO / "robots.txt").read_text(encoding="utf-8"))

    def test_manifest_consistent(self):
        m = json.loads((REPO / g.MEASUREMENT_MANIFEST_PATH).read_text(encoding="utf-8"))
        for n in g.SITEMAP_COHORT_ORDER:
            count = (REPO / "sitemaps" / f"{n}.xml").read_text(encoding="utf-8").count("<loc>")
            self.assertEqual(m["sitemaps"][n]["url_count"], count, n)
        self.assertEqual(m["excluded_pair_treatments"]["standards_special"]["pages"], 674)
        self.assertEqual(m["repository_pair_pages"], 28730)
        self.assertEqual(sum(m["repository_pair_cohorts"].values()), 28730)
        self.assertNotIn("generated_at", json.dumps(m))   # no clock in the manifest

    @unittest.skipIf(DIRTY_SOURCES, "sitemap URL sources uncommitted in this working tree")
    def test_committed_files_equal_generator_output(self):
        files, _ = g.build_semantic_sitemaps(PROFILES, history_dates=HISTORY, dirty_paths=DIRTY, snapshot=FX)
        for rel, text in files.items():
            self.assertEqual((REPO / rel).read_text(encoding="utf-8"), text, rel)

    @unittest.skipIf(DIRTY_SOURCES, "sitemap URL sources uncommitted in this working tree")
    def test_gate_passes(self):
        import contextlib
        import io
        import validate_semantic_sitemaps as gate
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gate.main(), 0)


class DeterminismTest(unittest.TestCase):
    def test_pure_and_deterministic(self):
        a = g.build_semantic_sitemaps(PROFILES, history_dates=dict(HISTORY), dirty_paths=set(), snapshot=FX)[0]
        b = g.build_semantic_sitemaps(PROFILES, history_dates=dict(HISTORY), dirty_paths=set(), snapshot=FX)[0]
        self.assertEqual(a, b)

    def test_dirty_source_omits_lastmod_and_strict_mode_refuses(self):
        files, m = g.build_semantic_sitemaps(PROFILES, history_dates=dict(HISTORY), dirty_paths={"pages/usd-to-eur.html"}, snapshot=FX)
        self.assertIn("<loc>https://convertccy.com/pages/usd-to-eur.html</loc>\n  </url>", files["sitemaps/ordinary-fx.xml"])
        self.assertEqual(m["sitemaps"]["ordinary-fx"]["urls_without_lastmod"], 1)
        fake = lambda root: (dict(HISTORY), {"pages/usd-to-eur.html"}, None, 0.0)   # noqa: E731
        with self.assertRaises(SystemExit):
            g.write_semantic_sitemaps(PROFILES, strict=True, lastmod_index_builder=fake)


@unittest.skipIf(shutil.which("git") is None, "git not available")
class GitLastmodSemanticsTest(unittest.TestCase):
    """Real repository: a merged PR must not keep a stale pre-change lastmod."""

    def git(self, *args, date=None):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
        if date:
            env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
        return subprocess.run(["git", *args], cwd=self.dir, env=env, capture_output=True, text=True, check=True).stdout

    def write(self, rel, text):
        p = Path(self.dir) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def index(self):
        return g.build_git_content_lastmod_index(Path(self.dir))[0]

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.git("init", "-q", "-b", "main")
        for rel in ("pages/a.html", "pages/b.html", "pages/c.html", "pages/d.html"):
            self.write(rel, f"{rel} v1\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "initial", date="2026-01-01T10:00:00+00:00")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_merged_pr_change_dated_by_its_commit_not_stale(self):
        self.git("checkout", "-q", "-b", "feature")
        self.write("pages/a.html", "a v2\n")
        self.git("commit", "-q", "-am", "change a", date="2026-02-01T09:00:00+00:00")
        self.git("checkout", "-q", "main")
        self.write("pages/b.html", "b v2\n")
        self.git("commit", "-q", "-am", "change b", date="2026-01-15T09:00:00+00:00")
        self.git("merge", "-q", "--no-ff", "feature", "-m", "Merge pull request #1", date="2026-03-01T09:00:00+00:00")
        idx = self.index()
        self.assertEqual(idx["pages/a.html"], "2026-02-01")      # not the stale 2026-01-01
        self.assertEqual(idx["pages/b.html"], "2026-01-15")      # plain commit on main
        self.assertEqual(idx["pages/c.html"], "2026-01-01")      # unchanged file keeps its creation date
        self.assertNotIn("2026-03-01", idx.values())             # a clean merge adds no content date

    def test_merge_only_content_dated_by_the_merge(self):
        self.git("checkout", "-q", "-b", "feature")
        self.write("pages/d.html", "d feature\n")
        self.git("commit", "-q", "-am", "feature d", date="2026-02-01T09:00:00+00:00")
        self.git("checkout", "-q", "main")
        self.write("pages/d.html", "d main\n")
        self.git("commit", "-q", "-am", "main d", date="2026-02-02T09:00:00+00:00")
        subprocess.run(["git", "merge", "--no-ff", "feature", "-m", "merge"], cwd=self.dir, capture_output=True)
        self.write("pages/d.html", "d resolved differently from both parents\n")
        self.git("add", "pages/d.html")
        self.git("commit", "-q", "--no-edit", date="2026-03-05T09:00:00+00:00")
        self.assertEqual(self.index()["pages/d.html"], "2026-03-05")   # pre-A5.1 index missed this content

    def test_feature_branch_dates_survive_ci_synthetic_merge(self):
        self.git("checkout", "-q", "-b", "feature")
        self.write("pages/a.html", "a v2\n")
        self.git("commit", "-q", "-am", "change a", date="2026-02-01T09:00:00+00:00")
        on_branch = self.index()
        self.git("checkout", "-q", "main")
        self.write("pages/b.html", "b v2\n")
        self.git("commit", "-q", "-am", "main moves on", date="2026-02-10T09:00:00+00:00")
        self.git("checkout", "-q", "--detach", "main")
        self.git("merge", "-q", "--no-ff", "feature", "-m", "synthetic PR merge", date="2026-04-01T09:00:00+00:00")
        after = self.index()
        self.assertEqual(after["pages/a.html"], on_branch["pages/a.html"])   # PR-time sitemap stays valid on CI/main
        self.assertEqual(after["pages/a.html"], "2026-02-01")

    def test_newest_change_wins_and_no_clock(self):
        self.write("pages/c.html", "c v2\n")
        self.git("commit", "-q", "-am", "c2", date="2026-05-01T09:00:00+00:00")
        self.write("pages/c.html", "c v3\n")
        self.git("commit", "-q", "-am", "c3", date="2026-06-01T09:00:00+00:00")
        self.write("pages/c.html", "c dirty\n")
        history, dirty, today, _ = g.build_git_content_lastmod_index(Path(self.dir))
        self.assertEqual(history["pages/c.html"], "2026-06-01")
        self.assertIn("pages/c.html", dirty)
        self.assertIsNone(today)
        self.assertIsNone(g.resolve_content_lastmod("pages/c.html", history, dirty, "2099-01-01"))


class SemanticFreezeTest(unittest.TestCase):
    def test_pages_hubs_and_data_unchanged(self):
        if git_show(BASELINE, "index.html") is None:
            self.skipTest("baseline commit not available")
        out = subprocess.run(["git", "diff", "--name-only", BASELINE, "--", "pages", "currencies", "data/rate_snapshot.json",
                              "rates", "data/metal_reference_snapshot.json", "data/institutional_reference_snapshot.json",
                              "data/live_fiat_reference_snapshot.json", "data/instrument_classification.json",
                              "data/currencies.json", "_redirects", "robots.txt", "index.html", "currencies.html"],
                             cwd=REPO, capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "")

    def test_legacy_script_delegates(self):
        import generate_sitemap as legacy
        with mock.patch.object(sys, "argv", ["generate_sitemap.py", "--output", "other.xml"]):
            self.assertEqual(legacy.main(), 2)


if __name__ == "__main__":
    unittest.main()
