#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pair-surface semantic hardening: mixed border regimes must not flatten.

Locks the pre-CNY propagation fix: China (and any jurisdiction that supplies
an optional Passage Check ``pair_surface_summary``) must not render as a
generic ``declaration at USD 5,000 / USD 5,000 / …`` numeric list. Ordinary
single-threshold jurisdictions keep the legacy ``declaration at`` line
byte-for-byte.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import generate  # noqa: E402


class PairSurfaceSemanticHardeningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gov = generate.load_governed_currency_map()
        pc = json.loads((REPO / "rules" / "passage-check.json").read_text(encoding="utf-8"))
        cls.china_pc = next(c for c in pc["countries"] if c["country_slug"] == "china")
        cls.canada_pc = next(c for c in pc["countries"] if c["country_slug"] == "canada")

    def _china_gov(self):
        matches = [g for g in self.gov.get("CNY", []) if g["country_slug"] == "china"]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def _canada_gov(self):
        matches = [g for g in self.gov.get("CAD", []) if g["country_slug"] == "canada"]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_china_four_structured_thresholds_still_authoritative(self):
        ths = self.china_pc["declaration"]["thresholds"]
        self.assertEqual(len(ths), 4)
        self.assertEqual(
            [(t["value"], t["currency"]) for t in ths],
            [(5000, "USD"), (5000, "USD"), (10000, "USD"), (20000, "CNY")],
        )
        self.assertTrue(self.china_pc["declaration"].get("note"))
        self.assertEqual(
            self.china_pc["exchange_controls"]["posture"],
            "capital_account_regulated",
        )

    def test_china_does_not_flatten_to_generic_declaration_at_list(self):
        china = self._china_gov()
        # Prove the raw numeric reduction still exists on the record…
        self.assertEqual(
            china["thresholds"],
            ["USD 5,000", "USD 5,000", "USD 10,000", "CNY 20,000"],
        )
        # …but the pair-surface body must NOT use it.
        body = generate.pair_surface_threshold_body(china)
        banned = "declaration at USD 5,000 / USD 5,000 / USD 10,000 / CNY 20,000"
        self.assertNotEqual(body, banned)
        self.assertNotIn("declaration at USD 5,000 / USD 5,000", body)
        self.assertNotIn("USD 5,000 / USD 5,000", body)

        html = generate.build_currency_passage_section(
            {"from_code": "USD", "to_code": "CNY", "macro_context": ""},
            {
                "USD": {"name": "US Dollar", "symbol": "$"},
                "CNY": {"name": "Chinese Yuan Renminbi", "symbol": "¥"},
            },
            {"FROM_CODE": "USD", "TO_CODE": "CNY"},
            self.gov,
        )
        self.assertNotIn(banned, html)
        self.assertNotIn("declaration at USD 5,000 / USD 5,000", html)

    def test_china_compact_line_distinguishes_declaration_permit_carriage(self):
        china = self._china_gov()
        body = generate.pair_surface_threshold_body(china)
        self.assertIn("declaration", body.lower())
        self.assertIn("permit", body.lower())
        self.assertIn("carriage", body.lower())
        self.assertIn("> USD 5,000", body)
        self.assertIn("CNY 20,000", body)
        # Inbound declaration vs outbound permit vs RMB carriage — not one label.
        self.assertIn("inbound", body.lower())
        self.assertIn("outbound", body.lower())
        self.assertIn("RMB", body)
        summary = self.china_pc["declaration"].get("pair_surface_summary", "")
        self.assertEqual(body, summary)
        self.assertEqual(china["exch_posture"], "capital_account_regulated")

    def test_canada_legacy_declaration_at_line_unchanged(self):
        canada = self._canada_gov()
        self.assertFalse(canada.get("pair_surface_summary"))
        self.assertIsNone(self.canada_pc["declaration"].get("pair_surface_summary"))
        body = generate.pair_surface_threshold_body(canada)
        self.assertEqual(body, "declaration at CAD 10,000")

        html = generate.build_currency_passage_section(
            {"from_code": "CAD", "to_code": "JPY", "macro_context": ""},
            {
                "CAD": {"name": "Canadian Dollar", "symbol": "$"},
                "JPY": {"name": "Japanese Yen", "symbol": "¥"},
            },
            {"FROM_CODE": "CAD", "TO_CODE": "JPY"},
            self.gov,
        )
        self.assertIn(
            "<strong>Canada:</strong> declaration at CAD 10,000",
            html,
        )

    def test_border_cash_pair_surface_summary_precedes_declaration(self):
        """Typed border_cash.pair_surface_summary wins over declaration summary."""
        entry_typed = {
            "pair_surface_summary": "",  # filled by load_governed after precedence
            "thresholds": ["CHF 10,000"],
        }
        # Direct body helper still prefers non-empty pair_surface_summary field.
        entry_typed["pair_surface_summary"] = "typed border summary"
        self.assertEqual(
            generate.pair_surface_threshold_body(entry_typed),
            "typed border summary",
        )
        entry_legacy = {
            "pair_surface_summary": "legacy declaration summary",
            "thresholds": ["CHF 10,000"],
        }
        self.assertEqual(
            generate.pair_surface_threshold_body(entry_legacy),
            "legacy declaration summary",
        )
        entry_fallback = {"pair_surface_summary": "", "thresholds": ["CHF 10,000"]}
        self.assertEqual(
            generate.pair_surface_threshold_body(entry_fallback),
            "declaration at CHF 10,000",
        )


if __name__ == "__main__":
    unittest.main()
