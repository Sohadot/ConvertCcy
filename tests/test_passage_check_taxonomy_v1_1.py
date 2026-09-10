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

    def test_rejects_authored_declaration_thresholds(self):
        """mechanisms[] is the sole authored source — no dual threshold list."""
        profile = _synthetic_border_cash_profile()
        profile["declaration"]["thresholds"] = []
        errs = bpc.validate_border_cash_profile("x", profile)
        self.assertTrue(any("must not be authored" in e for e in errs))

        profile2 = _synthetic_border_cash_profile()
        profile2["declaration"]["thresholds"] = [
            {"value": 10000, "currency": "CHF", "operator": ">="}
        ]
        errs2 = bpc.validate_border_cash_profile("x", profile2)
        self.assertTrue(any("must not be authored" in e for e in errs2))

        # Emitted thresholds remain mechanism-derived only.
        ok = _synthetic_border_cash_profile()
        record = bpc.build_border_cash_record(ok)
        self.assertEqual(record["declaration"]["thresholds"], [])
        self.assertNotIn("thresholds", ok["declaration"])

    def test_declaration_mode_consistency_contradictions(self):
        def base(**overrides):
            p = {
                "declaration": {"mode": "numeric_threshold"},
                "mechanisms": [],
                "note": "t",
            }
            p.update(overrides)
            return p

        decl_amount = {
            "kind": "declaration",
            "trigger": {"type": "amount", "value": 1000, "currency": "USD", "operator": ">="},
            "mechanism": "mandatory declaration",
        }
        decl_amount_2 = {
            "kind": "declaration",
            "trigger": {"type": "amount", "value": 5000, "currency": "EUR", "operator": ">"},
            "mechanism": "second declaration band",
        }
        decl_always = {
            "kind": "declaration",
            "trigger": {"type": "always"},
            "mechanism": "always declare",
        }
        decl_condition = {
            "kind": "declaration",
            "trigger": {
                "type": "condition",
                "condition": "on customs request",
            },
            "mechanism": "declare when requested",
        }
        inquiry_amount = {
            "kind": "inquiry",
            "trigger": {"type": "amount", "value": 10000, "currency": "CHF", "operator": ">="},
            "mechanism": "inquiry package",
        }

        # Required trigger missing
        errs = bpc.validate_border_cash_profile(
            "x", base(declaration={"mode": "numeric_threshold"}, mechanisms=[])
        )
        self.assertTrue(any("numeric_threshold requires" in e for e in errs))

        # numeric_threshold exclusivity
        errs_nt_always = bpc.validate_border_cash_profile(
            "x",
            base(
                declaration={"mode": "numeric_threshold"},
                mechanisms=[decl_amount, decl_always],
            ),
        )
        self.assertTrue(any("numeric_threshold must not contain a declaration-kind always" in e for e in errs_nt_always))

        errs_nt_cond = bpc.validate_border_cash_profile(
            "x",
            base(
                declaration={"mode": "numeric_threshold"},
                mechanisms=[decl_amount, decl_condition],
            ),
        )
        self.assertTrue(any("numeric_threshold must not contain a declaration-kind condition" in e for e in errs_nt_cond))

        self.assertEqual(
            bpc.validate_border_cash_profile(
                "x",
                base(
                    declaration={"mode": "numeric_threshold"},
                    mechanisms=[decl_amount, decl_amount_2],
                ),
            ),
            [],
        )

        # always exclusivity
        errs_al_amt = bpc.validate_border_cash_profile(
            "x",
            base(
                declaration={"mode": "always"},
                mechanisms=[decl_always, decl_amount],
            ),
        )
        self.assertTrue(any("mode=always must not contain a declaration-kind amount" in e for e in errs_al_amt))

        errs_al_cond = bpc.validate_border_cash_profile(
            "x",
            base(
                declaration={"mode": "always"},
                mechanisms=[decl_always, decl_condition],
            ),
        )
        self.assertTrue(any("mode=always must not contain a declaration-kind condition" in e for e in errs_al_cond))

        self.assertEqual(
            bpc.validate_border_cash_profile(
                "x",
                base(declaration={"mode": "always"}, mechanisms=[decl_always]),
            ),
            [],
        )

        # none_spontaneous: amount/always fail; condition MAY pass; inquiry independent
        errs_ns_amt = bpc.validate_border_cash_profile(
            "x",
            base(
                declaration={"mode": "none_spontaneous"},
                mechanisms=[decl_amount],
            ),
        )
        self.assertTrue(any("none_spontaneous must not contain" in e for e in errs_ns_amt))

        errs_ns_always = bpc.validate_border_cash_profile(
            "x",
            base(
                declaration={"mode": "none_spontaneous"},
                mechanisms=[decl_always],
            ),
        )
        self.assertTrue(any("none_spontaneous must not contain" in e for e in errs_ns_always))

        self.assertEqual(
            bpc.validate_border_cash_profile(
                "x",
                base(
                    declaration={"mode": "none_spontaneous"},
                    mechanisms=[decl_condition, inquiry_amount],
                ),
            ),
            [],
        )

        # not_established: zero declaration-kind of any trigger type
        errs_ne_cond = bpc.validate_border_cash_profile(
            "x",
            base(
                declaration={"mode": "not_established"},
                mechanisms=[decl_condition],
            ),
        )
        self.assertTrue(any("not_established requires zero" in e for e in errs_ne_cond))

        errs_ne_amt = bpc.validate_border_cash_profile(
            "x",
            base(
                declaration={"mode": "not_established"},
                mechanisms=[decl_amount],
            ),
        )
        self.assertTrue(any("not_established requires zero" in e for e in errs_ne_amt))

        self.assertEqual(
            bpc.validate_border_cash_profile(
                "x",
                base(
                    declaration={"mode": "not_established"},
                    mechanisms=[inquiry_amount],
                ),
            ),
            [],
        )

        # mixed
        errs_mixed = bpc.validate_border_cash_profile(
            "x",
            base(declaration={"mode": "mixed"}, mechanisms=[decl_amount]),
        )
        self.assertTrue(any("mode=mixed requires heterogeneous" in e for e in errs_mixed))

        self.assertEqual(
            bpc.validate_border_cash_profile(
                "x",
                base(
                    declaration={"mode": "mixed"},
                    mechanisms=[decl_amount, decl_always],
                ),
            ),
            [],
        )
        self.assertEqual(
            bpc.validate_border_cash_profile(
                "x",
                base(
                    declaration={"mode": "mixed"},
                    mechanisms=[decl_amount, decl_condition],
                ),
            ),
            [],
        )

        # Switzerland-like fixture continues to pass.
        self.assertEqual(
            bpc.validate_border_cash_profile("fixture", _synthetic_border_cash_profile()),
            [],
        )

    def test_typed_rule_label_and_full_builder_payload(self):
        """Full build_payload path: typed label + layered EC + empty derived thresholds."""
        slug = "fixture-ch-like"
        country = {
            "country_name": "Fixtureland",
            "country_slug": slug,
            "page_status": "published",
            "iso2": "XX",
            "currency_code": "CHF",
            "currency_name": "Fixture Franc",
            "region": "Test",
            "last_reviewed": "2026-09-10",
            "rules": {
                "cash_declaration_threshold": (
                    "No spontaneous declaration; inquiry/registration at CHF 10,000."
                ),
                "exchange_controls": "Layered current-international / sanctions / capital profile.",
            },
            "source_map": {},
            "source_authorities": [],
            "disclaimer": "fixture disclaimer",
        }
        dataset = {
            "generated_at": "2026-09-10T00:00:00+00:00",
            "license": "CC BY 4.0",
            "attribution": "ConvertCCY",
            "count": 1,
            "countries": [country],
        }
        payload = bpc.build_payload(
            dataset,
            declaration={},
            border_cash={slug: _synthetic_border_cash_profile()},
            exchange_controls={},
            exchange_profiles={slug: _synthetic_layered_profile()},
        )
        self.assertEqual(payload["count"], 1)
        rec = payload["countries"][0]
        self.assertIn("border_cash", rec)
        self.assertTrue(rec["declaration"].get("compatibility_view"))
        self.assertEqual(rec["declaration"]["thresholds"], [])
        self.assertEqual(rec["border_cash"]["declaration"]["thresholds"], [])
        self.assertEqual(rec["exchange_controls"]["posture"], "layered")
        self.assertEqual(
            rec["rules"]["cash_declaration_threshold"]["label"],
            "Border cash controls",
        )
        # Field name unchanged; only the presentation label is typed-aware.
        self.assertIn("cash_declaration_threshold", rec["rules"])

        # Static Agent Interface mirror preserves the typed-aware label.
        import build_static_agent_interface as sai

        view = sai.build_passage_check_view(payload, dataset)
        self.assertEqual(
            view["countries"][0]["rules"]["cash_declaration_threshold"]["label"],
            "Border cash controls",
        )

        # Legacy live jurisdiction retains Declaration threshold label.
        live = bpc.build_payload(self.dataset)
        au = next(c for c in live["countries"] if c["country_slug"] == "australia")
        self.assertEqual(
            au["rules"]["cash_declaration_threshold"]["label"],
            "Declaration threshold",
        )

    def test_numeric_amount_contract_preserves_decimal_rejects_bool(self):
        self.assertEqual(bpc.format_amount_value(10000), "10,000")
        self.assertEqual(bpc.format_amount_value(10000.5), "10,000.5")
        self.assertEqual(bpc.format_amount_value(10000.0), "10,000")
        with self.assertRaises(TypeError):
            bpc.format_amount_value(True)

        bad = {
            "declaration": {"mode": "numeric_threshold"},
            "mechanisms": [
                {
                    "kind": "declaration",
                    "trigger": {
                        "type": "amount",
                        "value": True,
                        "currency": "USD",
                        "operator": ">=",
                    },
                    "mechanism": "declare",
                }
            ],
        }
        errs = bpc.validate_border_cash_profile("x", bad)
        self.assertTrue(any("bool not allowed" in e for e in errs))

        decimal_ok = {
            "declaration": {"mode": "numeric_threshold"},
            "mechanisms": [
                {
                    "kind": "declaration",
                    "trigger": {
                        "type": "amount",
                        "value": 10000.5,
                        "currency": "USD",
                        "operator": ">=",
                    },
                    "mechanism": "declare",
                    "scope": "cash",
                    "applies": "in/out",
                    "authority": "X",
                }
            ],
        }
        self.assertEqual(bpc.validate_border_cash_profile("x", decimal_ok), [])
        record = bpc.build_border_cash_record(decimal_ok)
        self.assertEqual(record["declaration"]["thresholds"][0]["value"], 10000.5)
        # Typed brief path must not truncate decimals.
        import build_passage_briefs as briefs

        heading, body = briefs.border_cash_glance_html(
            {
                "border_cash": {
                    "declaration": {"mode": "numeric_threshold"},
                    "mechanisms": decimal_ok["mechanisms"],
                }
            }
        )
        self.assertEqual(heading, "Border cash controls")
        self.assertIn("10,000.5", body)
        self.assertIn("USD 10,000.5 (&gt;=)", body)

    def test_layered_component_banned_shorthand(self):
        profile = _synthetic_layered_profile()
        profile["components"][0]["summary"] = "No general exchange controls apply here"
        errs = bpc.validate_exchange_profile("x", profile)
        self.assertTrue(any("components[0].summary must not contain" in e for e in errs))

        profile2 = _synthetic_layered_profile()
        profile2["components"][1]["summary"] = "Market is fully liberalised for all accounts"
        errs2 = bpc.validate_exchange_profile("x", profile2)
        self.assertTrue(any("fully liberalised" in e for e in errs2))

        # Scope-sensitive IMF current-transactions language remains allowed.
        self.assertEqual(
            bpc.validate_exchange_profile("ok", _synthetic_layered_profile()),
            [],
        )

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
            cash_rule = new["rules"].get("cash_declaration_threshold")
            self.assertIsNotNone(cash_rule)
            self.assertEqual(cash_rule["label"], "Declaration threshold")
            # Governed prose unchanged vs dataset.
            ds = next(c for c in self.dataset["countries"] if c["country_slug"] == slug)
            self.assertEqual(cash_rule["text"], ds["rules"]["cash_declaration_threshold"])

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
        self.assertIn("border-cash controls at a glance", self.briefs_py)
        self.assertIn('cash_checklist_label', self.briefs_py)
        self.assertIn('"Border cash controls" if pc.get("border_cash") else "Declaration"', self.briefs_py)

        self.assertIn("See border-cash controls in the full rules", self.briefs_py)
        self.assertNotIn("See bordered cash mechanisms in full rules", self.briefs_py)

        import build_passage_briefs as briefs

        fake_pc = {
            "country_name": "Fixture",
            "country_slug": "fixture-ch-like",
            "currency_code": "CHF",
            "currency_name": "Swiss Franc",
            "region": "Test",
            "last_reviewed": "2026-09-10",
            "border_cash": bpc.build_border_cash_record(_synthetic_border_cash_profile()),
            "declaration": {
                "thresholds": [],
                "mode": "none_spontaneous",
                "compatibility_view": True,
            },
            "exchange_controls": {
                "posture": "layered",
                "label": "layered label",
                "components": [],
            },
        }
        rules = {
            "rules": {
                "bring_foreign_currency_in": "in",
                "take_foreign_currency_out": "out",
                "cash_declaration_threshold": "inquiry/registration prose",
                "resident_holding_rules": "r",
                "non_resident_rules": "nr",
                "business_invoicing_settlement": "b",
                "exchange_controls": "e",
                "banking_conversion_practicality": "bank",
            },
            "summary": {"traveler": "t", "business": "biz"},
            "source_authorities": [],
            "evidence_tier": "official_verified",
        }
        html = briefs.render_brief(fake_pc, rules)
        self.assertIn("<strong>Border cash controls:</strong>", html)
        self.assertNotIn("<strong>Declaration:</strong>", html)
        self.assertIn("No spontaneous declaration obligation", html)
        self.assertIn("Inquiry:", html)
        self.assertIn("Registration:", html)

    def test_pair_surface_taxonomy_neutral_copy(self):
        gen_src = (REPO / "generate.py").read_text(encoding="utf-8")
        self.assertIn(
            "the governed border-cash controls and exchange-control profile are shown below",
            gen_src,
        )
        self.assertNotIn(
            "the governed declaration threshold and exchange-control posture are shown below",
            gen_src,
        )

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
