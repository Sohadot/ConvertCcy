#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Focused tests for generate.py's --only-currency scoped-generation path.

This path is now a production mechanism: it published BRL pairs (PR #76),
closed the non-BRL propagation debt (PR #77), and will distribute the impact
of each newly published jurisdiction (e.g. MXN next). These tests lock in the
three guarantees the reconciliation sprints relied on:

  1. Scoped output for a fixed currency is byte-for-byte identical to the same
     pages produced by a full (unscoped) build.
  2. Scoped generation is idempotent.
  3. A scoped run touches only matching pair pages — never a non-matching pair
     page, and (via main()) never support pages or sitemap.xml.

Plus argument parsing for `--only-currency EUR,GBP` and repeated flags.

The tests exercise the real generator against real input data, but bound the
work to a tiny fixed set of pairs and redirect PAGES_DIR to a temp directory,
so nothing under the real pages/ tree is touched.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import generate  # noqa: E402

# A small, fixed fixture set of currencies. It deliberately mixes:
#   USD  — governed, maps to a single published jurisdiction
#   EUR  — governed, maps to multiple jurisdictions
#   JPY  — governed, single jurisdiction
#   CHF  — not published (plain identity block)
# The scoped fixture currency is USD.
FIXTURE_SET = {"USD", "EUR", "JPY", "CHF"}
FIX = "USD"


def _silent(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def _sha_dir(d: Path) -> dict[str, str]:
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(d.glob("*.html"))
    }


class ScopedGenerationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Real generator inputs, loaded once.
        cls.currencies = _silent(generate.load_currencies)
        cls.content = _silent(generate.load_content_blocks)
        all_profiles = _silent(generate.load_pair_profiles)
        # Bound the work: only profiles whose BOTH endpoints are in the fixture
        # set. Keeps the test to a handful of pages while exercising the real
        # render path (governed, multi-jurisdiction, and plain blocks).
        cls.subset = {
            k: p
            for k, p in all_profiles.items()
            if p["from_code"] in FIXTURE_SET
            and p["to_code"] in FIXTURE_SET
            and p["from_code"] != p["to_code"]
        }
        cls.fix_slugs = {
            p["pair_slug"]
            for p in cls.subset.values()
            if FIX in (p["from_code"], p["to_code"])
        }
        cls.nonfix_slugs = {
            p["pair_slug"]
            for p in cls.subset.values()
            if FIX not in (p["from_code"], p["to_code"])
        }

    def setUp(self):
        # Sanity: the fixture must actually cover the intended cases, otherwise
        # a silently-empty subset would make the parity assertions vacuous.
        self.assertTrue(self.subset, "fixture subset unexpectedly empty")
        self.assertTrue(self.fix_slugs, "no USD-involving fixture pairs found")
        self.assertTrue(self.nonfix_slugs, "no control (non-USD) fixture pairs found")

    @contextlib.contextmanager
    def _pages_dir(self):
        orig = generate.PAGES_DIR
        with tempfile.TemporaryDirectory() as tmp:
            generate.PAGES_DIR = Path(tmp)
            try:
                yield Path(tmp)
            finally:
                generate.PAGES_DIR = orig

    def _generate(self, out_dir_ctx, only):
        _silent(
            generate.generate_pair_pages,
            self.currencies,
            self.content,
            self.subset,
            only_currencies=only,
        )

    def test_scoped_equals_full_subset_byte_for_byte(self):
        with self._pages_dir() as full_dir:
            self._generate(full_dir, None)
            full = _sha_dir(full_dir)
        with self._pages_dir() as scoped_dir:
            self._generate(scoped_dir, {FIX})
            scoped = _sha_dir(scoped_dir)

        expected_scoped = {f"{s}.html" for s in self.fix_slugs}
        # Scoped writes exactly the USD-involving pages, nothing else.
        self.assertEqual(set(scoped), expected_scoped)
        # Full writes those plus the control (non-USD) pages.
        self.assertTrue(expected_scoped.issubset(set(full)))
        for s in self.nonfix_slugs:
            self.assertIn(f"{s}.html", full)
            self.assertNotIn(f"{s}.html", scoped)
        # Byte-for-byte parity on every scoped page.
        for name in expected_scoped:
            self.assertEqual(scoped[name], full[name], f"{name} differs from full build")

    def test_scoped_generation_is_idempotent(self):
        with self._pages_dir() as d1:
            self._generate(d1, {FIX})
            first = _sha_dir(d1)
        with self._pages_dir() as d2:
            self._generate(d2, {FIX})
            second = _sha_dir(d2)
        self.assertEqual(first, second)

    def test_main_scoped_run_leaves_support_and_sitemap_untouched(self):
        calls = {"support": 0, "sitemap": 0}
        orig = {
            "load_currencies": generate.load_currencies,
            "load_content_blocks": generate.load_content_blocks,
            "load_pair_profiles": generate.load_pair_profiles,
            "generate_support_pages": generate.generate_support_pages,
            "generate_sitemap": generate.generate_sitemap,
            "argv": sys.argv,
        }
        try:
            generate.load_currencies = lambda: self.currencies
            generate.load_content_blocks = lambda: self.content
            generate.load_pair_profiles = lambda: self.subset
            generate.generate_support_pages = lambda *a, **k: calls.__setitem__("support", calls["support"] + 1)
            generate.generate_sitemap = lambda *a, **k: calls.__setitem__("sitemap", calls["sitemap"] + 1)
            with self._pages_dir() as d:
                sys.argv = ["generate.py", "--only-currency", FIX]
                _silent(generate.main)
                written = {p.name for p in d.glob("*.html")}
            # Scoped main() must not regenerate support pages or the sitemap.
            self.assertEqual(calls["support"], 0)
            self.assertEqual(calls["sitemap"], 0)
            # And it must write only USD-involving pages.
            self.assertEqual(written, {f"{s}.html" for s in self.fix_slugs})
        finally:
            for k, v in orig.items():
                setattr(generate, k, v) if k != "argv" else None
            sys.argv = orig["argv"]

    def test_main_full_run_does_regenerate_support_and_sitemap(self):
        # Control: without the flag, main() DOES call support + sitemap, proving
        # the guard above is specific to the scoped branch (not always-skipped).
        calls = {"support": 0, "sitemap": 0}
        orig = {
            "load_currencies": generate.load_currencies,
            "load_content_blocks": generate.load_content_blocks,
            "load_pair_profiles": generate.load_pair_profiles,
            "generate_support_pages": generate.generate_support_pages,
            "generate_sitemap": generate.generate_sitemap,
            "argv": sys.argv,
        }
        try:
            generate.load_currencies = lambda: self.currencies
            generate.load_content_blocks = lambda: self.content
            generate.load_pair_profiles = lambda: self.subset
            generate.generate_support_pages = lambda *a, **k: calls.__setitem__("support", calls["support"] + 1)
            generate.generate_sitemap = lambda *a, **k: calls.__setitem__("sitemap", calls["sitemap"] + 1)
            with self._pages_dir():
                sys.argv = ["generate.py"]
                _silent(generate.main)
            self.assertEqual(calls["support"], 1)
            self.assertEqual(calls["sitemap"], 1)
        finally:
            for k, v in orig.items():
                setattr(generate, k, v) if k != "argv" else None
            sys.argv = orig["argv"]


class ParseOnlyCurrenciesTest(unittest.TestCase):
    def test_none_and_empty(self):
        self.assertIsNone(generate.parse_only_currencies(None))
        self.assertIsNone(generate.parse_only_currencies([]))
        self.assertIsNone(generate.parse_only_currencies(["", "  "]))

    def test_comma_separated(self):
        self.assertEqual(generate.parse_only_currencies(["EUR,GBP"]), {"EUR", "GBP"})

    def test_repeated_flags(self):
        self.assertEqual(generate.parse_only_currencies(["EUR", "GBP"]), {"EUR", "GBP"})

    def test_mixed_repeated_and_comma_with_case_and_space(self):
        self.assertEqual(
            generate.parse_only_currencies(["eur, gbp", "usd"]),
            {"EUR", "GBP", "USD"},
        )


if __name__ == "__main__":
    unittest.main()
