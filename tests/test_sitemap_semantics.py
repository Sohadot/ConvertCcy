#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SEO-A1 — truthful sitemap lastmod + search-surface segregation."""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import generate  # noqa: E402

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _parse_locs_and_lastmods(xml: str) -> Dict[str, Optional[str]]:
    root = ET.fromstring(xml)
    out: Dict[str, Optional[str]] = {}
    for url_el in root.findall("sm:url", NS):
        loc = url_el.findtext("sm:loc", default="", namespaces=NS)
        lastmod_el = url_el.find("sm:lastmod", NS)
        out[loc] = lastmod_el.text if lastmod_el is not None else None
    return out


class SitemapLastmodResolverTest(unittest.TestCase):
    def test_unchanged_tracked_file_uses_history_date(self):
        history = {"pages/usd-to-eur.html": "2024-01-15"}
        dirty: Set[str] = set()
        self.assertEqual(
            generate.resolve_content_lastmod("pages/usd-to-eur.html", history, dirty, "2026-09-11"),
            "2024-01-15",
        )

    def test_dirty_tracked_file_uses_today(self):
        history = {"pages/usd-to-eur.html": "2024-01-15"}
        dirty = {"pages/usd-to-eur.html"}
        self.assertEqual(
            generate.resolve_content_lastmod("pages/usd-to-eur.html", history, dirty, "2026-09-11"),
            "2026-09-11",
        )

    def test_new_untracked_file_uses_today(self):
        history: Dict[str, str] = {}
        dirty = {"pages/new-pair.html"}
        self.assertEqual(
            generate.resolve_content_lastmod("pages/new-pair.html", history, dirty, "2026-09-11"),
            "2026-09-11",
        )

    def test_unknown_date_omits_lastmod(self):
        self.assertIsNone(
            generate.resolve_content_lastmod(
                "pages/ghost.html", {}, set(), "2026-09-11"
            )
        )

    def test_unrelated_dirty_file_does_not_advance_other_url(self):
        history = {
            "pages/usd-to-eur.html": "2024-01-15",
            "pages/usd-to-gbp.html": "2024-02-01",
        }
        dirty = {"pages/usd-to-gbp.html"}
        self.assertEqual(
            generate.resolve_content_lastmod("pages/usd-to-eur.html", history, dirty, "2026-09-11"),
            "2024-01-15",
        )
        self.assertEqual(
            generate.resolve_content_lastmod("pages/usd-to-gbp.html", history, dirty, "2026-09-11"),
            "2026-09-11",
        )

    def test_git_index_parses_newest_commit_first(self):
        def fake_runner(args: List[str]):
            class R:
                returncode = 0
                stdout = ""
                stderr = ""

            if args[:1] == ["log"]:
                # Newest commit first
                R.stdout = (
                    "2026-03-10T12:00:00+00:00\n"
                    "pages/usd-to-eur.html\n"
                    "\n"
                    "2024-01-15T12:00:00+00:00\n"
                    "pages/usd-to-eur.html\n"
                )
                return R()
            if args[:1] == ["status"]:
                R.stdout = ""
                return R()
            R.returncode = 1
            return R()

        history, dirty, today, _elapsed = generate.build_git_content_lastmod_index(
            REPO, today="2026-09-11", git_runner=fake_runner
        )
        self.assertEqual(history["pages/usd-to-eur.html"], "2026-03-10")
        self.assertEqual(dirty, set())
        self.assertEqual(today, "2026-09-11")

    def test_git_unavailable_yields_empty_history(self):
        def fake_runner(args: List[str]):
            class R:
                returncode = 128
                stdout = ""
                stderr = "not a git repository"

            return R()

        history, dirty, _today, _elapsed = generate.build_git_content_lastmod_index(
            REPO, today="2026-09-11", git_runner=fake_runner
        )
        self.assertEqual(history, {})
        self.assertEqual(dirty, set())


class SitemapSearchSurfaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        profiles = generate.load_pair_profiles()
        # Stable injected history so tests do not depend on wall clock.
        history = {f"pages/{p['pair_slug']}.html": "2025-01-01" for p in profiles.values()}
        history.update(
            {
                "index.html": "2025-01-01",
                "api.html": "2025-01-01",
                "api/index.html": "2025-01-01",
                "currencies.html": "2025-01-01",
                "passage-check.html": "2025-01-01",
                "rules/switzerland-foreign-currency-rules.html": "2025-01-01",
            }
        )
        cls.xml = generate.build_sitemap(
            profiles,
            history_dates=history,
            dirty_paths=set(),
            today="2099-01-01",
        )
        cls.locs = _parse_locs_and_lastmods(cls.xml)

    def test_machine_surfaces_excluded(self):
        forbidden = [
            "https://convertccy.com/api/v1/index.json",
            "https://convertccy.com/api/v1/rules-index.json",
            "https://convertccy.com/api/v1/passage-check.json",
            "https://convertccy.com/api/v1/rules/australia.json",
            "https://convertccy.com/api/v1/rules/switzerland.json",
            "https://convertccy.com/llms.txt",
        ]
        for url in forbidden:
            self.assertNotIn(url, self.locs)

    def test_human_api_surfaces_retained(self):
        self.assertIn("https://convertccy.com/api.html", self.locs)
        self.assertIn("https://convertccy.com/api/", self.locs)

    def test_representative_search_surfaces_retained(self):
        required = [
            "https://convertccy.com/",
            "https://convertccy.com/currencies.html",
            "https://convertccy.com/passage-check.html",
            "https://convertccy.com/rules/switzerland-foreign-currency-rules.html",
            "https://convertccy.com/pages/usd-to-eur.html",
            "https://convertccy.com/pages/usd-to-chf.html",
        ]
        for url in required:
            self.assertIn(url, self.locs)

    def test_no_preview_urls(self):
        for url in self.locs:
            self.assertNotIn("/preview/", url)

    def test_locs_unique(self):
        raw = re.findall(r"<loc>(.*?)</loc>", self.xml)
        self.assertEqual(len(raw), len(set(raw)))

    def test_xml_well_formed(self):
        ET.fromstring(self.xml)

    def test_no_iso_today_stamping_on_clean_tree(self):
        # Injected history dates must appear; fake "today" must not.
        self.assertEqual(self.locs["https://convertccy.com/pages/usd-to-eur.html"], "2025-01-01")
        self.assertNotEqual(self.locs["https://convertccy.com/pages/usd-to-eur.html"], "2099-01-01")

    def test_omit_lastmod_when_history_missing(self):
        profiles = {"x": {"pair_slug": "aaa-to-bbb"}}
        # Point BASE_DIR pages existence is not required for URL emission from profiles,
        # but file_exists checks use real disk for static pages — use empty profiles subset
        # via real load and override history to empty for one path through resolver unit.
        lastmod = generate.resolve_content_lastmod("pages/does-not-exist-in-history.html", {}, set(), "2026-09-11")
        self.assertIsNone(lastmod)

    def test_rebuild_deterministic_with_injected_maps(self):
        profiles = generate.load_pair_profiles()
        history = {"pages/usd-to-eur.html": "2025-06-01", "index.html": "2025-06-01"}
        dirty: Set[str] = set()
        a = generate.build_sitemap(profiles, history_dates=history, dirty_paths=dirty, today="2099-01-01")
        b = generate.build_sitemap(profiles, history_dates=history, dirty_paths=dirty, today="2099-12-31")
        # Clean tree: today unused → identical output despite different clock.
        self.assertEqual(a, b)

    def test_architectural_url_delta_removes_only_machine_surfaces(self):
        """Pre-A1 generator inventory minus post-A1 must be machine URLs only."""
        # Reconstruct the pre-A1 machine set from disk (same presence checks).
        machine = []
        api_v1 = REPO / "api" / "v1"
        if (api_v1 / "index.json").exists():
            machine.append(f"{generate.BASE_URL}/api/v1/index.json")
        if (api_v1 / "rules-index.json").exists():
            machine.append(f"{generate.BASE_URL}/api/v1/rules-index.json")
        if (api_v1 / "passage-check.json").exists():
            machine.append(f"{generate.BASE_URL}/api/v1/passage-check.json")
        if (api_v1 / "rules").exists():
            for f in sorted((api_v1 / "rules").glob("*.json")):
                machine.append(f"{generate.BASE_URL}/api/v1/rules/{f.name}")
        if (REPO / "llms.txt").exists():
            machine.append(f"{generate.BASE_URL}/llms.txt")

        post = set(self.locs)
        for url in machine:
            self.assertNotIn(url, post)
        # Human API hubs must remain.
        self.assertIn(f"{generate.BASE_URL}/api.html", post)
        self.assertIn(f"{generate.BASE_URL}/api/", post)


class SitemapGitIndexIntegrationSmoke(unittest.TestCase):
    def test_real_git_index_has_pair_paths_and_no_mtime_reliance(self):
        history, dirty, today, elapsed = generate.build_git_content_lastmod_index(REPO)
        self.assertGreater(len(history), 1000)
        self.assertIn("pages/usd-to-eur.html", history)
        self.assertRegex(history["pages/usd-to-eur.html"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertLess(elapsed, 60.0)
        # Dirty set may be non-empty during local edits; must not force failure.
        self.assertIsInstance(dirty, set)
        self.assertRegex(today or "", r"^\d{4}-\d{2}-\d{2}$")


if __name__ == "__main__":
    unittest.main()
