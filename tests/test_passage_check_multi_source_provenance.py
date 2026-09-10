#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Passage Check multi-source provenance: no first-source collapse.

Locks the invariant that every Passage Check rule field preserves the full
ordered ``source_map['rules.<field>']`` list from ``rules/dataset.json``,
exposes it as ``sources[]``, and keeps singular ``source`` only as a
compatibility alias equal to ``sources[0]``.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import build_passage_check as bpc  # noqa: E402

RULE_FIELDS = list(bpc.RULE_FIELDS.keys())


class PassageCheckMultiSourceProvenanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads((REPO / "rules" / "dataset.json").read_text(encoding="utf-8"))
        cls.pc = json.loads((REPO / "rules" / "passage-check.json").read_text(encoding="utf-8"))
        cls.api = json.loads((REPO / "api" / "v1" / "passage-check.json").read_text(encoding="utf-8"))
        cls.ds_by = {c["country_slug"]: c for c in cls.dataset["countries"]}
        cls.pc_by = {c["country_slug"]: c for c in cls.pc["countries"]}
        cls.api_by = {c["country_slug"]: c for c in cls.api["countries"]}
        cls.html = (REPO / "passage-check.html").read_text(encoding="utf-8")

    def test_published_count(self):
        # Durable cross-surface consistency (not a hardcoded pre-Switzerland count).
        self.assertEqual(len(self.ds_by), len(self.pc_by))
        self.assertEqual(self.pc["count"], len(self.pc["countries"]))
        self.assertEqual(self.pc["count"], len(self.pc_by))
        self.assertEqual(self.api.get("count"), self.pc["count"])
        self.assertEqual(set(self.ds_by), set(self.pc_by))
        self.assertEqual(set(self.pc_by), set(self.api_by))
        # Publication Closure acceptance: Switzerland is jurisdiction 24.
        self.assertEqual(len(self.ds_by), 24)
        self.assertIn("switzerland", self.ds_by)
        self.assertIn("switzerland", self.pc_by)
        self.assertIn("switzerland", self.api_by)

    def test_nigeria_semantics(self):
        self.assertIn("nigeria", self.pc_by)
        nigeria = self.pc_by["nigeria"]
        self.assertEqual(nigeria["exchange_controls"]["posture"], "capital_account_regulated")
        self.assertNotEqual(nigeria["exchange_controls"]["posture"], "floating_regulated_market")
        label = (nigeria["exchange_controls"].get("label") or "").lower()
        self.assertNotIn("managed float", label)
        self.assertNotIn("floating_regulated_market", label)
        self.assertNotIn("significant exchange controls", label)
        note = (nigeria["declaration"].get("note") or "").lower()
        self.assertIn("operator >", note)
        self.assertIn("operator >=", note)
        self.assertIn("declaration threshold", note)
        self.assertIn("not established", note)
        self.assertNotIn("n10,000", note)
        self.assertNotIn("n20,000", note)
        self.assertNotIn("n100,000", note)
        thresholds = nigeria["declaration"]["thresholds"]
        self.assertEqual(len(thresholds), 2)
        ops = {t.get("operator") for t in thresholds}
        self.assertEqual(ops, {">", ">="})
        for t in thresholds:
            self.assertEqual(t["value"], 10000)
            self.assertEqual(t["currency"], "USD")
        self.assertEqual(
            nigeria["declaration"]["pair_surface_summary"],
            "statutory cash/NI declaration > USD 10,000 · "
            "Customs e-CDF operational >= USD 10,000 · "
            "physical NGN prohibited except CBN guidelines (no numeric exception established)",
        )

    def test_all_rule_fields_preserve_source_arrays(self):
        checked = 0
        for slug, ds in self.ds_by.items():
            pc = self.pc_by[slug]
            for field in RULE_FIELDS:
                if field not in ds.get("rules", {}):
                    continue
                upstream = ds.get("source_map", {}).get(f"rules.{field}", [])
                self.assertIsInstance(upstream, list)
                rule = pc["rules"][field]
                self.assertIn("sources", rule)
                self.assertEqual(rule["sources"], upstream)
                checked += 1
        self.assertGreaterEqual(checked, 100)

    def test_no_source_loss_on_multi_source_fields(self):
        multi = 0
        for slug, ds in self.ds_by.items():
            pc = self.pc_by[slug]
            for field in RULE_FIELDS:
                if field not in ds.get("rules", {}):
                    continue
                upstream = ds["source_map"][f"rules.{field}"]
                if len(upstream) <= 1:
                    continue
                multi += 1
                srcs = pc["rules"][field]["sources"]
                self.assertEqual(len(srcs), len(upstream))
                self.assertGreater(len(srcs), 1)
        self.assertGreaterEqual(multi, 1)

    def test_source_order_preserved(self):
        for slug, ds in self.ds_by.items():
            pc = self.pc_by[slug]
            for field in RULE_FIELDS:
                if field not in ds.get("rules", {}):
                    continue
                upstream = ds["source_map"][f"rules.{field}"]
                if len(upstream) <= 1:
                    continue
                srcs = pc["rules"][field]["sources"]
                self.assertEqual(
                    [s.get("url") for s in srcs],
                    [s.get("url") for s in upstream],
                )
                self.assertEqual(
                    [s.get("section") for s in srcs],
                    [s.get("section") for s in upstream],
                )
                self.assertEqual(
                    [s.get("pages") for s in srcs],
                    [s.get("pages") for s in upstream],
                )

    def test_compatibility_alias_equals_sources_zero(self):
        for slug, pc in self.pc_by.items():
            for field, rule in pc["rules"].items():
                srcs = rule.get("sources") or []
                if srcs:
                    self.assertEqual(rule.get("source"), srcs[0])
                else:
                    self.assertIsNone(rule.get("source"))

    def test_china_non_resident_rules_multi_source(self):
        ds = self.ds_by["china"]
        upstream = ds["source_map"]["rules.non_resident_rules"]
        self.assertGreaterEqual(len(upstream), 2)
        for surface_name, by in (("pc", self.pc_by), ("api", self.api_by)):
            rule = by["china"]["rules"]["non_resident_rules"]
            self.assertEqual(rule["sources"], upstream, surface_name)
            self.assertEqual(len(rule["sources"]), len(upstream), surface_name)
            self.assertEqual(rule["text"], ds["rules"]["non_resident_rules"])

    def test_china_semantics_unchanged(self):
        china = self.pc_by["china"]
        self.assertEqual(len(china["declaration"]["thresholds"]), 4)
        self.assertEqual(china["exchange_controls"]["posture"], "capital_account_regulated")
        self.assertEqual(
            china["declaration"]["pair_surface_summary"],
            "inbound FX cash > USD 5,000 declaration · "
            "outbound FX ≤5k / >5k–≤10k / >10k permit architecture · "
            "RMB CNY 20,000 carriage limit",
        )
        self.assertTrue((china["declaration"].get("note") or "").strip())

    def test_single_source_backward_compatibility(self):
        # Canada bring_foreign_currency_in is a stable single-source field.
        ds = self.ds_by["canada"]
        field = "bring_foreign_currency_in"
        upstream = ds["source_map"][f"rules.{field}"]
        self.assertEqual(len(upstream), 1)
        rule = self.pc_by["canada"]["rules"][field]
        self.assertEqual(rule["sources"], upstream)
        self.assertEqual(rule["source"], upstream[0])
        self.assertEqual(rule["text"], ds["rules"][field])

    def test_api_mirrors_passage_check_rule_sources(self):
        for slug, pc in self.pc_by.items():
            api = self.api_by[slug]
            for field, rule in pc["rules"].items():
                self.assertEqual(
                    api["rules"][field]["sources"],
                    rule["sources"],
                    f"{slug}.{field}",
                )
                self.assertEqual(
                    api["rules"][field].get("source"),
                    rule.get("source"),
                    f"{slug}.{field} alias",
                )

    def test_ui_prefers_sources_and_renders_multi(self):
        self.assertIn("function srcLines(", self.html)
        self.assertIn("rule.sources", self.html)
        self.assertIn("Sources:", self.html)
        # Call sites use srcLines(rule), not singular-only srcLine(source)
        self.assertIn("${srcLines(r)}", self.html)
        self.assertIn("${srcLines(dRule)}", self.html)
        self.assertNotIn("function srcLine(", self.html)
        # Fallback to singular source still present
        self.assertIn("rule.source", self.html)
        self.assertIn('rel="noopener"', self.html)

    def test_sources_for_field_helper(self):
        sm = {
            "rules.exchange_controls": [
                {"url": "https://a.example/1", "section": "A", "pages": [1]},
                {"url": "https://a.example/2", "section": "B", "pages": []},
            ]
        }
        out = bpc.sources_for_field(sm, "exchange_controls")
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["pages"], [1])
        # Deep copy: mutating result must not mutate input
        out[0]["section"] = "MUTATED"
        self.assertEqual(sm["rules.exchange_controls"][0]["section"], "A")
        self.assertEqual(bpc.sources_for_field({}, "exchange_controls"), [])


if __name__ == "__main__":
    unittest.main()
