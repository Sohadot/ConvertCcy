#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Passage Check Taxonomy v1.1 — typed border-cash + layered exchange profiles.

Capability / guard / legacy-regression tests. Does not publish any jurisdiction.
Synthetic fixtures represent Switzerland-like architecture without using a
published Switzerland record.
"""
from __future__ import annotations

import copy
import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import build_passage_check as bpc  # noqa: E402
import generate as gen  # noqa: E402


def _synthetic_border_cash_profile() -> dict:
    return {
        "declaration": {
            "mode": "none_spontaneous",
            "thresholds": [],
        },
        "mechanisms": [
            {
                "kind": "inquiry",
                "trigger": {
                    "type": "amount",
                    "value": 10000,
                    "currency": "CHF",
                    "operator": ">=",
                },
                "scope": "covered notes/coins/foreign currencies/bearer instruments",
                "applies": "inbound, outbound and transit",
                "authority": "FOCBS / SR 631.052",
                "mechanism": (
                    "express customs questioning / inquiry package "
                    "(identity, origin, intended use, beneficial owner)"
                ),
            },
            {
                "kind": "registration",
                "trigger": {
                    "type": "amount",
                    "value": 10000,
                    "currency": "CHF",
                    "operator": ">=",
                },
                "scope": "covered cash instruments",
                "applies": "cross-border carriage",
                "authority": "FOCBS",
                "mechanism": "FOCBS information-system registration entry",
            },
            {
                "kind": "inquiry",
                "trigger": {
                    "type": "condition",
                    "condition": (
                        "money-laundering or terrorist-financing suspicion "
                        "below CHF 10,000"
                    ),
                },
                "scope": "covered cash instruments",
                "applies": "cross-border carriage",
                "authority": "FOCBS / SR 631.052",
                "mechanism": "customs may require information below the amount trigger",
            },
            {
                "kind": "enforcement",
                "trigger": {
                    "type": "condition",
                    "condition": "suspicion of money laundering or terrorist financing",
                },
                "scope": "covered cash instruments",
                "applies": "cross-border carriage",
                "authority": "Customs Act Art. 104 / FOCBS",
                "mechanism": "provisional seizure may occur on suspicion (amount-independent)",
            },
        ],
        "note": (
            "No spontaneous FOCBS declaration threshold merely for crossing the border. "
            "CHF 10,000 activates inquiry and registration — not declaration, carriage "
            "ceiling, or permission."
        ),
        "pair_surface_summary": (
            "no spontaneous declaration · inquiry/registration >= CHF 10,000 · "
            "below-threshold ML/TF information powers · suspicion-based seizure"
        ),
    }


def _synthetic_layered_profile() -> dict:
    return {
        "classification_mode": "layered",
        "posture": "layered",
        "label": (
            "IMF exchange system free of multiple currency practices and of restrictions "
            "on payments and transfers for current international transactions, except "
            "security-related restrictions notified under Decision No. 144–(52/51); "
            "Embargo Act framework with ordinance-level sanctions measures; OECD Annex B "
            "actor/transaction-specific capital and investment reservations"
        ),
        "components": [
            {
                "scope": "current international transactions",
                "summary": (
                    "Free of MCP and of restrictions on payments/transfers for current "
                    "international transactions, except Decision 144–(52/51) security exception"
                ),
            },
            {
                "scope": "security / sanctions",
                "summary": (
                    "Embargo Act framework law; concrete measures in separate ordinances "
                    "(financial sanctions, trade restrictions, travel bans, asset freezes)"
                ),
            },
            {
                "scope": "capital / investment",
                "summary": (
                    "OECD Annex B actor/transaction-specific reservations "
                    "(e.g. enumerated inward FDI, non-resident real estate, "
                    "private pension funds / insurance)"
                ),
            },
        ],
    }


class PassageCheckV11TaxonomyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = json.loads((REPO / "rules" / "dataset.json").read_text(encoding="utf-8"))
        cls.html = (REPO / "passage-check.html").read_text(encoding="utf-8")
        cls.briefs_py = (REPO / "scripts" / "build_passage_briefs.py").read_text(encoding="utf-8")

    def test_engine_version_constant(self):
        self.assertEqual(bpc.ENGINE_VERSION, "1.1")

    def test_synthetic_border_cash_capability(self):
        profile = _synthetic_border_cash_profile()
        errs = bpc.validate_border_cash_profile("fixture-ch-like", profile)
        self.assertEqual(errs, [])
        record = bpc.build_border_cash_record(profile)
        self.assertEqual(record["declaration"]["mode"], "none_spontaneous")
        self.assertEqual(record["declaration"]["thresholds"], [])
        kinds = [m["kind"] for m in record["mechanisms"]]
        self.assertIn("inquiry", kinds)
        self.assertIn("registration", kinds)
        self.assertIn("enforcement", kinds)
        # CHF 10,000 never appears as a declaration threshold.
        self.assertFalse(
            any(
                t.get("value") == 10000 and t.get("currency") == "CHF"
                for t in record["declaration"]["thresholds"]
            )
        )
        amount_mechs = [
            m for m in record["mechanisms"]
            if (m.get("trigger") or {}).get("type") == "amount"
        ]
        self.assertTrue(all(m["kind"] != "declaration" for m in amount_mechs))
        compat = bpc.compatibility_declaration_from_border_cash(record)
        self.assertEqual(compat["thresholds"], [])
        self.assertTrue(compat.get("compatibility_view"))

    def test_synthetic_layered_exchange_capability(self):
        profile = _synthetic_layered_profile()
        errs = bpc.validate_exchange_profile("fixture-layered", profile)
        self.assertEqual(errs, [])
        # Build against empty legacy maps for this slug alone via assemble helper
        # using a minimal fake country + tables.
        fake_country = {
            "country_name": "Fixture",
            "country_slug": "fixture-layered",
            "iso2": "XX",
            "currency_code": "XXX",
            "currency_name": "Fixture",
            "region": "Test",
            "last_reviewed": "2026-09-10",
            "rules": {"exchange_controls": "layered fixture prose"},
            "source_map": {},
            "source_authorities": [],
            "disclaimer": "",
            "page_status": "published",
        }
        out = bpc.assemble_country(
            "fixture-layered",
            fake_country,
            declaration={"fixture-layered": {"thresholds": [], "note": None}},
            border_cash_table={},
            exchange_controls={},
            exchange_profiles={"fixture-layered": profile},
        )
        ec = out["exchange_controls"]
        self.assertEqual(ec["posture"], "layered")
        self.assertEqual(ec["classification_mode"], "layered")
        self.assertNotEqual(ec["posture"], "none")
        self.assertNotEqual(ec["posture"], "floating_regulated_market")
        self.assertNotEqual(ec["posture"], "capital_account_regulated")
        lowered = ec["label"].lower()
        self.assertNotIn("fully liberalised", lowered)
        self.assertNotIn("no exchange controls", lowered)
        self.assertEqual(len(ec["components"]), 3)
        # Monetary regime must not be the machine posture.
        self.assertNotIn(ec["posture"], {"floating_regulated_market", "supervisory_peg"})

    def test_builder_rejects_neither_and_both_border(self):
        countries = {"aaa": {"page_status": "published"}, "bbb": {"page_status": "published"}}
        decl = {"aaa": {"thresholds": []}}
        border = {}
        exch = {"aaa": ("none", "x"), "bbb": ("none", "y")}
        profiles = {}
        errs = bpc.validate_transcription_tables(countries, decl, border, exch, profiles)
        self.assertTrue(any("bbb" in e and "BORDER_CASH" in e for e in errs))

        border_both = {"aaa": _synthetic_border_cash_profile()}
        errs2 = bpc.validate_transcription_tables(
            {"aaa": {"page_status": "published"}},
            {"aaa": {"thresholds": []}},
            border_both,
            {"aaa": ("none", "x")},
            {},
        )
        self.assertTrue(any("both DECLARATION and BORDER_CASH" in e for e in errs2))

    def test_builder_rejects_neither_and_both_exchange(self):
        countries = {"aaa": {"page_status": "published"}}
        errs = bpc.validate_transcription_tables(
            countries,
            {"aaa": {"thresholds": []}},
            {},
            {},
            {},
        )
        self.assertTrue(any("EXCHANGE_CONTROLS" in e and "EXCHANGE_CONTROL_PROFILES" in e for e in errs))

        errs2 = bpc.validate_transcription_tables(
            countries,
            {"aaa": {"thresholds": []}},
            {},
            {"aaa": ("none", "x")},
            {"aaa": _synthetic_layered_profile()},
        )
        self.assertTrue(any("both EXCHANGE_CONTROLS and" in e for e in errs2))

    def test_typed_validation_guards(self):
        bad = _synthetic_border_cash_profile()
        bad["mechanisms"][0]["trigger"] = {"type": "amount", "value": 1, "currency": "CHF"}
        errs = bpc.validate_border_cash_profile("x", bad)
        self.assertTrue(any("operator" in e for e in errs))

        bad2 = _synthetic_border_cash_profile()
        bad2["mechanisms"][2]["trigger"]["value"] = 1
        errs2 = bpc.validate_border_cash_profile("x", bad2)
        self.assertTrue(any("must not carry a numeric value" in e for e in errs2))

        bad3 = _synthetic_layered_profile()
        bad3["label"] = "No general exchange controls (fully liberalised)"
        errs3 = bpc.validate_exchange_profile("x", bad3)
        self.assertTrue(any("must not contain" in e for e in errs3))

        bad4 = _synthetic_layered_profile()
        bad4["components"] = []
        errs4 = bpc.validate_exchange_profile("x", bad4)
        self.assertTrue(any("non-empty components" in e for e in errs4))

    def test_legacy_23_semantic_regression(self):
        payload = bpc.build_payload(self.dataset)
        self.assertEqual(payload["count"], 23)
        self.assertEqual(payload["version"], "1.1")
        after_by = {c["country_slug"]: c for c in payload["countries"]}
        self.assertEqual(set(after_by), set(bpc.DECLARATION))
        self.assertEqual(set(after_by), set(bpc.EXCHANGE_CONTROLS))
        self.assertNotIn("switzerland", after_by)
        self.assertEqual(bpc.BORDER_CASH_CONTROLS, {})
        self.assertEqual(bpc.EXCHANGE_CONTROL_PROFILES, {})
        for slug, new in after_by.items():
            self.assertNotIn("border_cash", new)
            legacy_decl = bpc.DECLARATION[slug]
            self.assertEqual(new["declaration"].get("thresholds"), legacy_decl.get("thresholds"))
            self.assertEqual(new["declaration"].get("note"), legacy_decl.get("note"))
            self.assertEqual(
                new["declaration"].get("pair_surface_summary"),
                legacy_decl.get("pair_surface_summary"),
            )
            posture, label = bpc.EXCHANGE_CONTROLS[slug]
            self.assertEqual(new["exchange_controls"]["posture"], posture)
            self.assertEqual(new["exchange_controls"]["label"], label)
            self.assertNotIn("classification_mode", new["exchange_controls"])

    def test_ui_feature_detection_and_labels(self):
        self.assertIn("if(country.border_cash)", self.html)
        self.assertIn("Border cash controls", self.html)
        self.assertIn("Conditional control", self.html)
        self.assertIn("posture==='layered'", self.html)
        self.assertIn("border-cash controls and exchange-control profile", self.html)
        self.assertIn("function borderCashRow", self.html)
        self.assertIn("function evalTypedMechanism", self.html)
        self.assertIn("mech.ui_label", self.html)
        # Kind labels are emitted on typed records (not hardcoded as declaration).
        self.assertEqual(bpc.KIND_UI_LABEL["inquiry"], "Inquiry threshold")
        self.assertEqual(bpc.KIND_UI_LABEL["registration"], "Registration threshold")
        self.assertEqual(bpc.KIND_UI_LABEL["declaration"], "Declaration threshold")

    def test_briefs_typed_path(self):
        self.assertIn("border_cash_glance_html", self.briefs_py)
        self.assertIn('glance_k = "Declaration threshold"', self.briefs_py)
        self.assertIn("Border cash controls", self.briefs_py)
        self.assertIn('if pc.get("border_cash")', self.briefs_py)

    def test_pair_surface_precedence(self):
        fake_pc = {
            "countries": [
                {
                    "currency_code": "TST",
                    "country_name": "Test",
                    "country_slug": "testland",
                    "rules_page": "/rules/testland-foreign-currency-rules.html",
                    "last_reviewed": "2026-09-10",
                    "exchange_controls": {"label": "L", "posture": "layered"},
                    "declaration": {
                        "thresholds": [{"value": 1, "currency": "TST"}],
                        "pair_surface_summary": "legacy declaration summary",
                    },
                    "border_cash": {
                        "pair_surface_summary": "typed border summary",
                        "declaration": {"mode": "none_spontaneous", "thresholds": []},
                        "mechanisms": [],
                    },
                }
            ]
        }
        # Temporarily point PASSAGE_FILE via monkeypatch of generate module constant.
        path = REPO / "tmp_pc_pair_test.json"
        path.write_text(json.dumps(fake_pc), encoding="utf-8")
        old = gen.PASSAGE_FILE
        try:
            gen.PASSAGE_FILE = path
            gov = gen.load_governed_currency_map()
            self.assertEqual(gov["TST"][0]["pair_surface_summary"], "typed border summary")
            # Without border_cash summary, fall back to declaration.
            fake_pc["countries"][0]["border_cash"]["pair_surface_summary"] = ""
            path.write_text(json.dumps(fake_pc), encoding="utf-8")
            gov2 = gen.load_governed_currency_map()
            self.assertEqual(gov2["TST"][0]["pair_surface_summary"], "legacy declaration summary")
        finally:
            gen.PASSAGE_FILE = old
            path.unlink(missing_ok=True)

    def test_no_switzerland_in_live_tables(self):
        self.assertNotIn("switzerland", bpc.DECLARATION)
        self.assertNotIn("switzerland", bpc.BORDER_CASH_CONTROLS)
        self.assertNotIn("switzerland", bpc.EXCHANGE_CONTROLS)
        self.assertNotIn("switzerland", bpc.EXCHANGE_CONTROL_PROFILES)
        self.assertEqual(self.dataset["count"], 23)
        self.assertFalse(
            any(c["country_slug"] == "switzerland" for c in self.dataset["countries"])
        )


if __name__ == "__main__":
    unittest.main()
