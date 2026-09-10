#!/usr/bin/env python3
"""
build_passage_check.py — assemble the Passage Check engine dataset.

The Passage Check engine is deterministic and evidence-bound. It may only
surface what the published, source-mapped country entries already state.

Schema version 1.1 (backward-compatible minor evolution):

  - Legacy jurisdictions remain authored in DECLARATION + EXCHANGE_CONTROLS
    (v1.0-style grandfathered records).
  - Opt-in typed jurisdictions are authored in BORDER_CASH_CONTROLS and/or
    EXCHANGE_CONTROL_PROFILES (exactly one border source and exactly one
    exchange-control source per published jurisdiction).
  - Typed border-cash emits canonical ``border_cash`` plus a compatibility
    ``declaration`` projection that contains declaration-kind numeric
    thresholds only. Authored ``BORDER_CASH_CONTROLS`` profiles declare
    ``declaration.mode`` only; ``mechanisms[]`` is the sole authored source
    for declaration mechanisms — emitted thresholds are derived.
  - Layered exchange profiles emit ``posture: "layered"`` as a routing key;
    the legal answer is the hand-reviewed label/components.

Principle: prose truth → reviewed transcription → typed engine structure.
The taxonomy must never force country truth into a false declaration
threshold or a false scalar exchange-control posture.

Run: python3 scripts/build_passage_check.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent
DATASET = REPO / "rules" / "dataset.json"
OUT = REPO / "rules" / "passage-check.json"

ENGINE_VERSION = "1.1"

DECLARATION_MODES = frozenset({
    "numeric_threshold",
    "always",
    "none_spontaneous",
    "mixed",
    "not_established",
})

MECHANISM_KINDS = frozenset({
    "declaration",
    "reporting",
    "inquiry",
    "registration",
    "carriage_limit",
    "permit",
    "enforcement",
})

AMOUNT_OPERATORS = frozenset({">", ">=", "<", "<="})

TRIGGER_TYPES = frozenset({"amount", "condition", "always"})

# Ontology mapping for typed mechanisms. None = explicit unmapped (do not invent).
MECHANISM_ONTOLOGY: Dict[str, Optional[str]] = {
    "declaration": "declaration-regimes",
    "reporting": "reporting-obligations",
    "inquiry": "reporting-obligations",
    "registration": "reporting-obligations",
    "carriage_limit": "import-export-ceilings",
    "permit": "channel-restrictions",
    "enforcement": "penalty-regimes",
}

KIND_UI_LABEL = {
    "declaration": "Declaration threshold",
    "reporting": "Reporting threshold",
    "inquiry": "Inquiry threshold",
    "registration": "Registration threshold",
    "carriage_limit": "Carriage limit",
    "permit": "Permit / authorisation threshold",
    "enforcement": "Enforcement trigger",
}

# Hand-verified transcription of the declaration thresholds.
# Every value here is read off the entry's rules.cash_declaration_threshold
# prose. `currency` is the currency the THRESHOLD is denominated in (which is
# not always the country's own currency — India and Pakistan state USD).
DECLARATION = {
    "australia": {
        "thresholds": [
            {"value": 10000, "currency": "AUD", "scope": "cash or bearer negotiable instruments",
             "applies": "inbound and outbound", "authority": "AUSTRAC",
             "mechanism": "AML reporting trigger"}
        ],
        "note": "No mandatory customs declaration threshold for ordinary travellers; "
                "the figure is an anti-money-laundering reporting trigger reported to AUSTRAC.",
    },
    "brazil": {
        "thresholds": [
            {"value": 10000, "currency": "USD",
             "scope": "paper money in cash (national or foreign), excluding credit instruments, cheques and traveller's cheques; or the equivalent in another currency",
             "applies": "entry and exit",
             "authority": "Receita Federal (Brazilian Federal Revenue / Customs)",
             "mechanism": "mandatory declaration via the Declaração Eletrônica de Bens de Viajantes (e-DBV)"}
        ],
        "note": "Declaration is triggered ABOVE USD 10,000 (or the equivalent in another currency), applied to "
                "paper money in cash and excluding credit instruments, cheques and traveller's cheques. On "
                "departure the traveller must also present the declared cash and the applicable supporting "
                "evidence identified by Receita Federal. This Receita Federal customs border-declaration regime "
                "is distinct from the Banco Central do Brasil FX-market framework under Law 14.286/2021.",
    },
    "canada": {
        "thresholds": [
            {"value": 10000, "currency": "CAD", "scope": "cash or bearer negotiable instruments (or equivalent)",
             "applies": "entry and exit", "authority": "Canada Border Services Agency (CBSA)",
             "mechanism": "mandatory customs report"}
        ],
        "note": None,
    },
    "china": {
        "thresholds": [
            {"value": 5000, "currency": "USD",
             "scope": "foreign-currency physical cash or equivalent",
             "applies": "entering China / ordinary inbound passenger rule",
             "authority": "Chinese Customs / SAFE",
             "mechanism": "mandatory written Customs declaration when exceeding (超过等值5000美元, strictly >); declaration trigger, NOT an import ceiling"},
            {"value": 5000, "currency": "USD",
             "scope": "foreign-currency physical cash",
             "applies": "leaving China",
             "authority": "Chinese Customs / SAFE",
             "mechanism": "Customs declaration/red-channel condition when exceeding; outbound legal treatment is NOT symmetric with inbound; where there is no/insufficient latest inbound declaration, > USD 5,000 through ≤ USD 10,000 enters the bank-issued 携带证 pathway"},
            {"value": 10000, "currency": "USD",
             "scope": "foreign-currency physical cash",
             "applies": "leaving China",
             "authority": "SAFE / Chinese Customs",
             "mechanism": "amounts exceeding USD 10,000 are in principle not carried, subject to specifically provided exceptional SAFE permit cases; NOT a universal ordinary export allowance of USD 10,000"},
            {"value": 20000, "currency": "CNY",
             "scope": "physical Renminbi cash",
             "applies": "entering or leaving China",
             "authority": "PBOC / Chinese Customs",
             "mechanism": "CNY 20,000 per-person, per-entry/exit carriage limit under PBOC Announcement〔2004〕No. 18 / State Council Order No. 108; Customs uses 人民币现钞超过20000元 as the strict-exceeding declaration/red-channel condition; the exceeding part is prohibited as a carriage-limit matter"},
        ],
        "note": "Inbound FX cash > USD 5,000 (超过等值5000美元, strictly '>', never '>=') is a Customs declaration trigger, not an import ceiling. "
                "Art. 89 also imposes a special regardless-of-amount written-declaration rule for same-day / short-interval second-and-subsequent inbound entries; "
                "that repeated-entry rule is a bounded qualification, NOT a second ordinary numeric threshold record. "
                "Customs may list > USD 5,000 declaration conditions in both directions, but the outbound legal architecture is not symmetric with inbound: "
                "outbound FX preserves ≤ USD 5,000 (generally no 携带证) / > USD 5,000–≤ USD 10,000 (bank-issued 携带证 where applicable) / > USD 10,000 "
                "(in principle not carried except specified SAFE permit cases), and outbound treatment depends where applicable on the latest inbound declaration record. "
                "Physical RMB CNY 20,000 is a separate carriage limit (PBOC Announcement〔2004〕No. 18 / State Council Order No. 108). "
                "Negotiable/payment instruments are not silently folded into Huifa〔2003〕102 foreign-cash thresholds. "
                "The USD 50,000 individual annual 便利化额度 is NOT a border-cash threshold and must not be read from this declaration block.",
        # Optional compact pair-page presentation metadata. Does not replace the
        # structured thresholds above; generate.py uses this when present so mixed
        # declaration / permit / carriage regimes are not flattened into one
        # generic "declaration at … / …" numeric list.
        "pair_surface_summary": (
            "inbound FX cash > USD 5,000 declaration · "
            "outbound FX ≤5k / >5k–≤10k / >10k permit architecture · "
            "RMB CNY 20,000 carriage limit"
        ),
    },
    "egypt": {
        "thresholds": [
            {"value": 10000, "currency": "USD", "operator": ">",
             "scope": "foreign currency and bearer negotiable instruments, individually or combined",
             "applies": "entering Egypt",
             "authority": "Egyptian Customs under AML Law 80 Art. 12 / Exec Reg Art. 14(3), with Law 194 Art. 213 overlapping for foreign-currency cash",
             "mechanism": "mandatory customs disclosure when value exceeds USD 10,000 equivalent (تجاوز / جاوز, strictly >); exactly USD 10,000 is outside this disclosure trigger; no general inbound FX cash ceiling under Law 194 Art. 213"},
            {"value": 5000, "currency": "USD", "operator": ">",
             "scope": "foreign currency and bearer negotiable instruments, individually or combined",
             "applies": "leaving Egypt",
             "authority": "Egyptian Customs under AML Law 80 Art. 12 / Exec Reg Art. 14(4)",
             "mechanism": "mandatory customs disclosure when value exceeds USD 5,000 equivalent (تجاوز, strictly >); DISCLOSURE threshold only — NOT the ordinary FX carriage ceiling; exactly USD 5,000 is outside this disclosure trigger"},
            {"value": 10000, "currency": "USD", "operator": "<=",
             "scope": "physical foreign-currency cash",
             "applies": "ordinary departure from Egypt",
             "authority": "Law 194/2020 Art. 213 / CBE framework",
             "mechanism": "ordinary FX cash carriage not exceeding USD 10,000 equivalent (ألا يزيد على, <=); CARRIAGE rule, not a declaration threshold; travellers may carry the remainder of foreign currency previously disclosed on arrival even when the remainder exceeds USD 10,000"},
            {"value": 5000, "currency": "EGP", "operator": "<=",
             "scope": "physical Egyptian-pound banknotes; AML Executive Regulation also covers bearer negotiable instruments in this EGP-valued limb",
             "applies": "entering or leaving Egypt",
             "authority": "CBE Board Decision 2200/2020 for EGP banknotes + AML Exec Reg Art. 14(5) for EGP banknotes/BNI overlay",
             "mechanism": "carriage within EGP 5,000 (<=); carriage ceiling, not a declaration threshold; Decision 2200 itself regulates EGP banknotes — the BNI extension is from AML Exec Reg Art. 14(5)"},
        ],
        "note": "Mixed dual-layer architecture — do not collapse. "
                "(A) Law 194 Art. 213 is the FX-cash architecture: inbound FX free with no general quantitative ceiling and Art. 213-form disclosure when FX exceeds USD 10,000 (جاوز / strictly >); "
                "outbound ordinary FX cash carriage not exceeding USD 10,000 (ألا يزيد على / <=), plus a previously-declared inbound FX remainder exception above USD 10,000 for travellers generally. "
                "(B) AML Law 80 Art. 12 / Exec Reg Art. 14 is the FX+BNI customs-disclosure architecture: inbound disclosure when FX and/or BNI (aggregated) exceeds USD 10,000; "
                "outbound disclosure when FX and/or BNI (aggregated) exceeds USD 5,000 — a disclosure threshold distinct from and lower than the Art. 213 FX carriage ceiling. "
                "(C) Decision 2200/2020 sets the physical EGP banknote carriage ceiling at EGP 5,000 entering or leaving; Exec Reg Art. 14(5) also covers EGP banknotes or BNI within EGP 5,000. "
                "BNI is defined in Exec Reg Art. 1 and must not be assigned Art. 213 FX-only semantics. "
                "Never publish 'USD 10,000 declaration at entry and exit' or 'USD 5,000 outbound cash limit'. "
                "Disclosure threshold ≠ carriage ceiling.",
        "pair_surface_summary": (
            "FX/BNI disclose >USD10k in / >USD5k out · "
            "outbound FX cash ≤USD10k (+ declared remainder) · "
            "EGP notes/BNI ≤EGP5k"
        ),
    },
    "france": {
        "thresholds": [
            {"value": 10000, "currency": "EUR", "scope": "cash or bearer negotiable instruments (or equivalent)",
             "applies": "entry and exit", "authority": "French Customs (Douane)",
             "mechanism": "mandatory declaration (DALIA online or paper)"}
        ],
        "note": None,
    },
    "germany": {
        "thresholds": [
            {"value": 10000, "currency": "EUR", "scope": "cash or bearer negotiable instruments (or equivalent)",
             "applies": "entry and exit", "authority": "German Customs",
             "mechanism": "mandatory declaration"}
        ],
        "note": None,
    },
    "india": {
        "thresholds": [
            {"value": 5000, "currency": "USD", "scope": "foreign currency notes",
             "applies": "arrival-side framing", "authority": "CBIC Indian Customs",
             "mechanism": "Currency Declaration Form (CDF) pathway"},
            {"value": 10000, "currency": "USD", "scope": "aggregate foreign exchange (notes + in-scope traveller instruments)",
             "applies": "arrival-side framing", "authority": "CBIC Indian Customs",
             "mechanism": "Currency Declaration Form (CDF) pathway"},
        ],
        "note": "Two-tier threshold: the lower figure applies to foreign-currency notes, "
                "the higher to aggregate foreign exchange. Endorsed CDF documentation anchors "
                "later authorised-dealer conversions and outbound movement.",
    },
    "indonesia": {
        "thresholds": [
            {"value": 100000000, "currency": "IDR",
             "scope": "cash and/or bearer payment instruments (cheques, traveller's cheques, promissory notes, bills of exchange), in Rupiah or foreign currency, reaching or exceeding this amount in total",
             "applies": "entering or leaving Indonesia",
             "authority": "Indonesian Customs (Directorate General of Customs and Excise / Bea Cukai)",
             "mechanism": "mandatory Customs Declaration via the applicable channel (All Indonesia integrated declaration for air/sea arrivals; Bea Cukai e-CD for land-border arrivals and outbound cash declarations); Government Regulation 99/2016"}
        ],
        "note": "The declaration is triggered when the total value REACHES OR EXCEEDS IDR 100,000,000 (>=; 'IDR 100,000,000 or more'), or the equivalent in another currency, aggregating cash and bearer payment instruments in Rupiah or foreign currency, symmetric on entry and exit; failure to declare carries an administrative fine of 10% of the amount carried, up to a maximum of IDR 300,000,000. This is a customs / anti-money-laundering border-transparency declaration, NOT a currency import/export ceiling or a currency-control cap. It is distinct from three separate regimes that must not be conflated with it: the physical-Rupiah carriage rules (outbound Rupiah of IDR 100,000,000 or more requires prior Bank Indonesia permission; inbound is subject to a Customs authenticity examination), the foreign-banknote (UKA) carriage rules (IDR 1,000,000,000 or more restricted to Bank Indonesia-authorised entities), and the DHE SDA export-proceeds retention/placement regime.",
    },
    "italy": {
        "thresholds": [
            {"value": 10000, "currency": "EUR",
             "scope": "cash — currency (banknotes and coins), bearer-negotiable instruments, and gold used as a highly liquid store of value",
             "applies": "entering or leaving the European Union through Italy",
             "authority": "Agenzia delle Dogane e dei Monopoli (ADM), Italian Customs",
             "mechanism": "mandatory declaration under Article 3, Regulation (EU) 2018/1672"},
            {"value": 10000, "currency": "EUR",
             "scope": "same cash categories (currency, bearer-negotiable instruments, gold)",
             "applies": "entering or leaving Italian national territory, including to or from other EU Member States",
             "authority": "Agenzia delle Dogane e dei Monopoli (ADM), Italian Customs",
             "mechanism": "mandatory declaration under Article 3, Legislative Decree 195/2008"},
        ],
        "note": "Two parallel EUR 10,000 regimes administered through a single ADM declaration form: the EU "
                "external-border regime (Art. 3 Reg (EU) 2018/1672) and the Italian national-territory regime, "
                "which also covers intra-EU movements to or from other Member States (Art. 3 D.Lgs 195/2008). "
                "Unaccompanied cash sent by post, freight or courier is covered separately by Art. 4 of Regulation "
                "(EU) 2018/1672 (disclosure on customs request). This border cash-declaration regime is distinct "
                "from the general capital-movement framework under Article 63 TFEU.",
    },
    "japan": {
        "thresholds": [
            {"value": 1000000, "currency": "JPY", "scope": "cash or equivalent",
             "applies": "inbound and outbound", "authority": "Ministry of Finance / Bank of Japan",
             "mechanism": "may trigger AML reporting"}
        ],
        "note": "No mandatory declaration threshold for ordinary travellers; movements at or "
                "above this figure may trigger reporting under AML regulations.",
    },
    "mexico": {
        "thresholds": [
            {"value": 10000, "currency": "USD",
             "scope": "means of payment — cash, national or foreign checks, payment orders or any other collectible document, or a combination — exceeding this amount in total",
             "applies": "entering or leaving Mexico",
             "authority": "Agencia Nacional de Aduanas de México (ANAM); SAT-approved form",
             "mechanism": "mandatory customs declaration (Ley Aduanera Art. 9)"}
        ],
        "note": "The declaration is triggered only ABOVE USD 10,000 (exceeding, not 'USD 10,000 or more'), "
                "aggregating cash, national or foreign checks, payment orders and other collectible documents; "
                "failure to declare carries a fine of 20%–40% of the excess (Ley Aduanera Art. 185 fr. VII). "
                "This is a customs currency-transparency declaration, not a currency-control cap, and is distinct "
                "from the anti-money-laundering controls and quantitative US-dollar cash-operation limits banks "
                "apply under Article 115 of the Ley de Instituciones de Crédito, from UIF AML reporting, and from "
                "the LFPIORPI domestic cash-payment limits.",
    },
    "morocco": {
        "thresholds": [
            {"value": 100000, "currency": "MAD",
             "scope": "effects of commerce, means of payment and bearer-negotiable financial instruments / covered foreign means and instruments",
             "applies": "entering and leaving Morocco",
             "authority": "Office des Changes / Moroccan Customs",
             "mechanism": "mandatory Customs declaration when value is equal to or greater than MAD 100,000 (>=; Art. 37 inbound / Art. 40 outbound)"},
            {"value": 2000, "currency": "MAD",
             "scope": "physical Moroccan-dirham banknotes",
             "applies": "entering and leaving Morocco / traveller carriage",
             "authority": "Office des Changes / Moroccan Customs",
             "mechanism": "traveller carriage exception not exceeding MAD 2,000 (<=); import/export of MAD banknotes otherwise prohibited in principle (Art. 42) — NOT a declaration threshold"},
        ],
        "note": "Mixed architecture: >= MAD 100,000 is the Customs declaration trigger for covered means/instruments "
                "(Arts 37/40; exactly MAD 100,000 is inside the trigger); below MAD 100,000 inbound declaration is "
                "facultative, but presentation of the import declaration may still be required regardless of amount "
                "to justify origin for eligible FX/convertible-dirham account funding, re-export, or qualifying "
                "export-proceeds proof. MAD 100,000 is not a carriage ceiling. Separately, <= MAD 2,000 is the "
                "Art. 42 physical-MAD banknote traveller carriage exception (import/export otherwise prohibited in "
                "principle). These two numeric regimes must not be collapsed.",
        "pair_surface_summary": (
            "foreign means/instruments ≥ MAD 100,000 declaration · "
            "physical MAD ≤2,000 traveller carriage exception"
        ),
    },
    "nigeria": {
        "thresholds": [
            {"value": 10000, "currency": "USD", "operator": ">",
             "scope": "cash or negotiable instruments (or equivalent)",
             "applies": "entering or leaving Nigeria",
             "authority": "Money Laundering (Prevention and Prohibition) Act, 2022 / Nigeria Customs Service",
             "mechanism": "statutory MLPPA s.3(3) declaration trigger when transporting cash or negotiable instruments in excess of US$10,000 or its equivalent (operator >; exactly USD 10,000 is outside this statutory trigger); declaration obligation, NOT a foreign-currency carriage ceiling"},
            {"value": 10000, "currency": "USD", "operator": ">=",
             "scope": "cash or negotiable instruments as captured on the Customs electronic currency declaration form",
             "applies": "Customs e-CDF operational interface for Nigeria border declaration",
             "authority": "Nigeria Customs Service — Electronic Currency Declaration",
             "mechanism": "Customs operational e-CDF trigger of US$10,000 or more / equal to or greater than US$10,000 (operator >=); OPERATIONAL interface posture only — does not formally amend or interpret the statutory MLPPA > trigger into a single reconciled operator"},
        ],
        "note": "Keep statutory and operational triggers distinct — do not flatten. "
                "(A) Statutory MLPPA 2022: transportation of cash or negotiable instruments in excess of US$10,000 "
                "or its equivalent into or out of Nigeria shall be declared to the Nigeria Customs Service "
                "(operator >; exactly USD 10,000 is outside the statutory trigger). "
                "(B) Separately, current Customs e-CDF operational guidance uses US$10,000 or more / >= "
                "(operator >=). The Customs operational interface does not formally amend the statute. "
                "Declaration threshold ≠ foreign-currency carriage ceiling; do not publish "
                "'USD 10,000 cash limit', 'maximum USD 10,000', or 'outbound limited to amount declared on entry'. "
                "Separately, FEMMPA s.14 prohibits importation and exportation of the naira except as permitted "
                "under guidelines issued from time to time by the Central Bank; a current numeric traveller "
                "NGN exception is not established in the published Nigeria rules and must not be invented.",
        "pair_surface_summary": (
            "statutory cash/NI declaration > USD 10,000 · "
            "Customs e-CDF operational >= USD 10,000 · "
            "physical NGN prohibited except CBN guidelines (no numeric exception established)"
        ),
    },
    "pakistan": {
        "thresholds": [
            {"value": 10000, "currency": "USD", "scope": "cash or bearer negotiable instruments (or equivalent)",
             "applies": "entry and exit", "authority": "Pakistan Customs",
             "mechanism": "mandatory declaration"}
        ],
        "note": None,
    },
    "saudi-arabia": {
        "thresholds": [
            {"value": 40000, "currency": "SAR",
             "scope": "currency (Saudi or foreign), bearer negotiable instruments, gold bullion, precious metals, gemstones and worked jewellery — combined total value reaching or exceeding this amount, or the equivalent in another currency",
             "applies": "entering or leaving the Kingdom",
             "authority": "Zakat, Tax and Customs Authority (ZATCA); Article 23/1 of the Implementing Regulation to the Anti-Money Laundering Law (Umm Al-Qura)",
             "mechanism": "mandatory written declaration under the prescribed form"}
        ],
        "note": "The declaration is triggered when the combined total value REACHES OR EXCEEDS SAR 40,000 (>=; "
                "'SAR 40,000 or more', not merely 'exceeding'), or the equivalent in another currency, aggregating "
                "currency, bearer negotiable instruments, gold bullion, precious metals, gemstones and worked "
                "jewellery, symmetric on entry and exit. This is a border anti-money-laundering / customs "
                "transparency declaration under Article 23/1 of the Implementing Regulation to the Anti-Money "
                "Laundering Law (primary legal locator in the Umm Al-Qura official gazette; operationally "
                "corroborated by the ZATCA traveller-declaration page), NOT a currency-control cap or an export "
                "ceiling, and is distinct from bank AML/KYC reporting and from SAMA's account-eligibility rules. "
                "The fixed SAR/USD peg is a separate monetary-regime fact.",
    },
    "singapore": {
        "thresholds": [
            {"value": 20000, "currency": "SGD",
             "scope": "physical currency and bearer negotiable instruments (CBNI)",
             "applies": "entering or leaving Singapore",
             "authority": "Singapore Police Force / Immigration & Checkpoints Authority under CDSA",
             "mechanism": "mandatory CBNI report (Form NP 727) when total value EXCEEDS S$20,000"},
        ],
        "note": "Reporting is triggered only when total CBNI value exceeds S$20,000 (CDSA 1992 s60(1) "
                "'exceeds the prescribed amount'; CBNI Regulations 2007 reg 2A; strictly '>', never '>='). "
                "Exactly S$20,000 is outside the trigger. The rule applies inbound and outbound. "
                "ICA states there is no restriction on CBNI type or amount — this is a reporting trigger, "
                "not a carriage ceiling. This is CDSA Part 6A cross-border cash/CBNI reporting, not an "
                "Exchange Control Act capital control.",
        "pair_surface_summary": "CBNI > S$20,000 report · no carriage ceiling",
    },
    "south-africa": {
        "thresholds": [
            {"value": 25000, "currency": "ZAR", "scope": "South African bank notes",
             "applies": "taking out; unlimited within the Common Monetary Area",
             "authority": "South African Reserve Bank (SARB); declared to SARS Customs",
             "mechanism": "prior SARB authorisation required above this amount"},
            {"value": 100000, "currency": "ZAR",
             "scope": "'excess currency' — any amount in rand, or foreign currency convertible to rand",
             "applies": "entering or leaving",
             "authority": "South African Reserve Bank (SARB); declared to SARS Customs",
             "mechanism": "written SARB permission required"},
        ],
        "note": "Two distinct SARB exchange-control thresholds: the R25,000 rand-carrying limit on "
                "South African bank notes (unlimited within the Common Monetary Area, sourced to the "
                "SARS Departure page) and the R100,000 excess-currency rule covering rand or foreign "
                "currency convertible to rand (sourced to the SARS Travellers page). Separately, the "
                "traveller declaration — bank notes, foreign currency, securities and gold — is "
                "administered by SARS via an online form or the manual Traveller Declaration (TD-01). "
                "This R25,000 rand-carrying limit is a SARB exchange-control figure and is NOT the "
                "Currency and Exchanges Manual's R25,000 ADLA money-transfer cap.",
    },
    "south-korea": {
        "thresholds": [
            {"value": 10000, "currency": "USD",
             "scope": "means of payment — foreign currency, Korean-won notes and checks — combined, exceeding this amount in total",
             "applies": "entering or leaving South Korea",
             "authority": "Korea Customs Service",
             "mechanism": "mandatory declaration (Traveler Declaration Form item no. 3; Certificate of Foreign Currency Declaration)"}
        ],
        "note": "The declaration is triggered only ABOVE USD 10,000 (exceeding, not 'USD 10,000 or more'), "
                "aggregating foreign currency, Korean-won notes and checks; at or below USD 10,000 none is "
                "required. This Korea Customs border declaration is distinct from three separate regimes: "
                "Foreign Exchange Transactions Act capital-transaction and method-of-payment reporting "
                "(FETA Art. 16/18); foreign exchange banks' reporting of FX sales over USD 10,000 to the "
                "National Tax Service (FETA Art. 21); and KoFIU anti-money-laundering reporting.",
    },
    "turkey": {
        "thresholds": [
            {"value": 185000, "currency": "TRY",
             "scope": "Turkish lira cash",
             "applies": "leaving Türkiye / outbound only",
             "authority": "Ministry of Trade / Turkish Customs",
             "mechanism": "mandatory Nakit Beyan Formu declaration (Decree No. 32 Art. 3(d); Communiqué 2008-32/34 Art. 3(5)); triggered only when exceeding (aşan, strictly >)"},
            {"value": 10000, "currency": "EUR",
             "scope": "foreign banknotes / efektif, or the equivalent in another foreign currency",
             "applies": "leaving Türkiye / outbound only",
             "authority": "Ministry of Trade / Turkish Customs",
             "mechanism": "mandatory Nakit Beyan Formu declaration (Decree No. 32 Art. 4(f); Communiqué 2008-32/34 Art. 4(2)); triggered only when exceeding (aşan, strictly >)"},
        ],
        "note": "Both outbound triggers apply only when exceeded (aşan, strictly '>'), not when merely reached; "
                "they are outbound declaration triggers on the Nakit Beyan Formu, not export ceilings. "
                "Ordinary inbound foreign currency has no general mandatory numeric declaration threshold "
                "under Decree No. 32 Art. 4(a); inbound declaration may be voluntary, and Customs may request "
                "an explanation of amount, source and purpose under Law No. 5549. Source/purpose cash "
                "categories that must move through banking channels remain a separate regime. The TRY and "
                "foreign-banknote (efektif) thresholds are distinct and must not be collapsed into one "
                "generic traveller figure, and must not be read as creating a symmetric inbound EUR 10,000 "
                "or 'entry and exit' threshold.",
    },
    "united-arab-emirates": {
        "thresholds": [
            {"value": 60000, "currency": "AED",
             "scope": "combined value of cash, negotiable instruments without a named payee, jewellery, and precious metals",
             "applies": "travellers aged 18 and above, inbound and outbound",
             "authority": "UAE Customs / Central Bank of the UAE",
             "mechanism": "AML transparency declaration"}
        ],
        "note": "The trigger is a COMBINED declarable value across several asset categories, "
                "not cash alone, and applies to passengers aged eighteen and above.",
    },
    "united-kingdom": {
        "thresholds": [
            {"value": 10000, "currency": "GBP",
             "scope": "cash and specified monetary instruments (notes and coins, bearer bonds, signed travellers' cheques), or equivalent in foreign currency",
             "applies": "Great Britain (England, Scotland, Wales), entering or leaving the UK",
             "authority": "HM Revenue & Customs (HMRC) via Border Force",
             "mechanism": "mandatory declaration"},
            {"value": 10000, "currency": "EUR",
             "scope": "cash and specified monetary instruments (also money orders, gold coins, bullion, prepaid cards), or equivalent",
             "applies": "Northern Ireland, travelling to or from a non-EU country outside the UK",
             "authority": "HM Revenue & Customs (HMRC) via Border Force",
             "mechanism": "mandatory declaration"},
        ],
        "note": "Two thresholds by jurisdiction: Great Britain applies GBP 10,000 (or equivalent) "
                "on entering or leaving the UK; Northern Ireland applies EUR 10,000 (or equivalent) "
                "when travelling between NI and a non-EU country outside the UK. Both derive from UK "
                "anti-money-laundering legislation and are administered by HMRC through Border Force.",
    },
    "united-states": {
        "thresholds": [
            {"value": 10000, "currency": "USD",
             "scope": "aggregate cash or covered monetary instruments",
             "applies": "into or out of the United States",
             "authority": "U.S. Customs and Border Protection (CBP) / FinCEN",
             "mechanism": "mandatory Currency and Monetary Instrument Report (FinCEN Form 105 / CMIR)"}
        ],
        "note": "Transporting an aggregate exceeding USD 10,000 across the US border triggers a "
                "mandatory FinCEN Form 105 (CMIR) to CBP under 31 U.S.C. 5316 and 31 CFR 1010.340. "
                "This traveller border report is distinct from Bank Secrecy Act filings by financial "
                "institutions — Currency Transaction Reports (CTR) and Suspicious Activity Reports "
                "(SAR) — and from Foreign Bank Account Reports (FBAR); none of those is a traveller "
                "declaration.",
    },
}

# Transcribed exchange-controls posture, read from rules.exchange_controls prose.
EXCHANGE_CONTROLS = {
    "australia": ("none", "No general exchange controls (fully liberalised)"),
    "brazil": ("floating_regulated_market",
               "Floating exchange-rate regime regulated by the Banco Central do Brasil; FX transaction rates freely agreed between authorised institutions and their clients"),
    "canada": ("none", "No general exchange controls (fully liberalised)"),
    "china": ("capital_account_regulated",
              "Current international payments and transfers are not generally restricted under State Council Decree No. 532 Art. 5; "
              "current-account FX remains subject to genuine/lawful transaction basis and bank authenticity/consistency review under Art. 12; "
              "capital-account FX is transaction-specific and may involve bank handling, registration, reporting, account/permitted-use controls, "
              "quotas or approval where specifically required; the PBOC managed-floating RMB regime is a separate monetary-regime fact and is not "
              "itself an exchange-control rule; no universal SAFE approval regime is asserted. Absence of a located restriction is not evidence that none exists."),
    "egypt": ("floating_regulated_market",
              "Market-determined EGP exchange rate under Law 194/CBE, with FX retention and "
              "inward/outward transfers permitted through licensed channels; domestic EGP "
              "settlement rules, licensed-market supervision and separate AML/cross-border "
              "cash controls remain operative"),
    "france": ("none", "No general exchange controls (liberalised within the Eurozone)"),
    "germany": ("none", "No general exchange controls (liberalised within the Eurozone)"),
    "india": ("capital_account_regulated",
              "Current account largely liberalised; capital account regulated under FEMA"),
    "indonesia": ("capital_account_regulated",
                  "Free-foreign-exchange framework (Law 24/1999) with a floating Rupiah under a Flexible Inflation Targeting Framework, stated as a monetary-regime fact kept separate from controls; the reviewed official sources do not establish a single general exchange-control authorisation regime, but specific layered rules apply and are kept distinct — DHE SDA sector-specific export-proceeds retention/placement, non-resident Rupiah/foreign-exchange-market restrictions, the domestic Rupiah-use obligation, and the cross-border cash-declaration and Rupiah/UKA carriage regimes; absence of a located restriction is not evidence that none exists"),
    "italy": ("none",
              "No national exchange controls; free movement of capital and payments under Article 63 TFEU, subject to Treaty exceptions (taxation, prudential supervision, public policy/security, certain third-country measures) and to EU sanctions"),
    "japan": ("none", "No general exchange controls (fully liberalised)"),
    "mexico": ("floating_regulated_market",
               "Free-floating exchange-rate regime set by the Comisión de Cambios (SHCP and Banco de México); the reviewed official sources do not establish a general foreign-exchange authorisation regime, with anti-money-laundering, US-dollar cash-operation, customs-declaration and any sectoral restrictions kept distinct"),
    "morocco": ("capital_account_regulated",
                "Regulated, category- and transaction-specific foreign-exchange framework "
                "under Office des Changes / IGOC 2026; current and capital operations use "
                "authorised channels, allowances, account rules and transaction-specific "
                "conditions rather than one universal prior-approval screen"),
    "nigeria": ("capital_account_regulated",
                "CBN-regulated foreign-exchange Market architecture under FEMMPA: Authorised Dealer/"
                "Authorised Buyer appointment and Market channels; documentation-backed Market FX "
                "purchase eligibility; Certificate of Capital Importation issuance and related CBN "
                "returns for qualifying inward investment; foreign-currency domiciliary accounts with "
                "Authorised Dealers subject to financial-institution identification evidence; statutory "
                "cash/negotiable-instrument border declaration in excess of US$10,000; physical-naira "
                "import/export prohibition except as permitted under Central Bank guidelines; and CBN/"
                "FMDA regulation of EFEMS with published guidelines for FX Code / Market Operating "
                "Guidelines compliance — discrete regulated mechanisms rather than one universal "
                "prior-approval screen, without asserting a formal floating/managed-float taxonomy "
                "or a severity classification of exchange controls"),
    "pakistan": ("capital_account_regulated",
                 "No general exchange controls on the current account; capital account regulated by the SBP"),
    "saudi-arabia": ("supervisory_peg",
                     "Saudi riyal maintained at a fixed rate against the US dollar (SAR 3.75) by the Saudi Central Bank (SAMA) as a monetary-regime fact, kept separate from control posture; the reviewed official sources establish a licensed, SAMA-regulated foreign-exchange market (banks and money-exchange businesses) but do not establish a general exchange-control authorisation regime for buying, holding or transferring currency, and absence of a located restriction is not evidence that none exists — the AML border declaration, account-eligibility and any sectoral rules are kept distinct"),
    "singapore": ("none",
                  "No operative general exchange-control approval regime under the MAS blanket "
                  "exemption; Exchange Control Act remains in force through 31 December 2033"),
    "south-africa": ("capital_account_regulated",
                     "Current account largely liberalised; capital account subject to SARB exchange control administered through Authorised Dealers under the Currency and Exchanges Manual"),
    "south-korea": ("capital_account_regulated",
                    "Current-account payments and receipts substantially liberalised; capital transactions and certain methods of payment or receipt subject to transaction-specific notification, permission or reporting under the Foreign Exchange Transactions Act (via foreign exchange banks, the Bank of Korea Governor, or MOEF as competent authority); the Korean won is not fully internationalised"),
    "turkey": ("floating_regulated_market",
               "Türkiye operates a floating exchange-rate regime with no nominal or real exchange-rate target; the reviewed official sources do not establish a single general foreign-exchange authorisation regime, while specific regulated layers remain distinct — resident/non-resident FX account and transfer rules under Decree No. 32, outbound physical-cash declaration triggers, banking-channel-only source/purpose categories, domestic FX-contract restrictions, export-proceeds repatriation/sale requirements, and transaction-specific reporting. Absence of a located restriction is not evidence of absence. The floating regime is a monetary fact, not itself an exchange-control rule."),
    "united-arab-emirates": ("supervisory_peg",
                             "No per-transaction approval controls; supervisory posture around the US-dollar peg, current-account flows largely liberal"),
    "united-kingdom": ("none", "No general exchange controls (fully liberalised for current and capital account)"),
    "united-states": ("none",
                      "No general exchange controls; free-floating rate accepted under IMF Article VIII for current international transactions; capital-account reservations limited to enumerated sectoral inward direct investment under the OECD Code of Liberalisation of Capital Movements"),
}

# Opt-in typed border-cash transcription (Passage Check v1.1).
# Exactly one of DECLARATION or BORDER_CASH_CONTROLS may author a published slug.
# Switzerland is the first live typed consumer.
BORDER_CASH_CONTROLS: Dict[str, dict] = {
    "switzerland": {
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
                "scope": (
                    "covered notes, coins, foreign currencies and bearer negotiable "
                    "instruments within the governed Swiss border-cash rule"
                ),
                "applies": "cross-border Swiss customs cash movement/check context",
                "authority": "FOCBS / SR 631.052",
                "mechanism": (
                    "at CHF 10,000 or the foreign-currency equivalent, express customs "
                    "questioning requires the governed information package concerning "
                    "identity, cash movement, origin, intended use and beneficial owner"
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
                "scope": (
                    "covered notes, coins, foreign currencies and bearer negotiable "
                    "instruments within the governed Swiss border-cash rule"
                ),
                "applies": "cross-border Swiss customs cash movement/check context",
                "authority": "FOCBS / SR 631.052",
                "mechanism": (
                    "at the governed threshold, an entry is registered in the FOCBS "
                    "information system"
                ),
            },
            {
                "kind": "inquiry",
                "trigger": {
                    "type": "condition",
                    "condition": (
                        "money-laundering or terrorist-financing suspicion below CHF 10,000"
                    ),
                },
                "scope": (
                    "covered notes, coins, foreign currencies and bearer negotiable "
                    "instruments within the governed Swiss border-cash rule"
                ),
                "applies": "cross-border Swiss customs cash movement/check context",
                "authority": "FOCBS / SR 631.052",
                "mechanism": (
                    "such suspicion may activate customs information powers"
                ),
            },
            {
                "kind": "enforcement",
                "trigger": {
                    "type": "condition",
                    "condition": (
                        "suspicion basis for provisional seizure under the governed "
                        "Swiss customs framework"
                    ),
                },
                "scope": (
                    "covered notes, coins, foreign currencies and bearer negotiable "
                    "instruments within the governed Swiss border-cash rule"
                ),
                "applies": "cross-border Swiss customs cash movement/check context",
                "authority": "Customs Act Art. 104 / FOCBS / SR 631.052",
                "mechanism": (
                    "provisional seizure may occur on suspicion and is amount-independent"
                ),
            },
            {
                "kind": "enforcement",
                "trigger": {
                    "type": "condition",
                    "condition": (
                        "refusal or false information concerning the governed identity "
                        "and cash-movement information limbs"
                    ),
                },
                "scope": (
                    "covered notes, coins, foreign currencies and bearer negotiable "
                    "instruments within the governed Swiss border-cash rule"
                ),
                "applies": "cross-border Swiss customs cash movement/check context",
                "authority": "FOCBS / SR 631.052",
                "mechanism": (
                    "the governed conduct may constitute the applicable administrative offence"
                ),
            },
        ],
        "note": (
            "There is no spontaneous FOCBS declaration threshold merely because covered "
            "cash crosses the Swiss border. CHF 10,000 or the foreign-currency equivalent "
            "is an inquiry and information-system-registration trigger, not a declaration "
            "threshold or carriage ceiling. Below that amount, ML/TF suspicion may still "
            "activate information powers; provisional seizure and false/refused-information "
            "consequences are conduct/suspicion mechanisms rather than numeric declaration "
            "rules."
        ),
        "pair_surface_summary": (
            "no spontaneous declaration · ≥ CHF 10,000 inquiry + FOCBS registration · "
            "below-threshold ML/TF suspicion powers · seizure/offence are non-threshold controls"
        ),
    },
}

# Opt-in layered exchange-control profiles (Passage Check v1.1).
# Exactly one of EXCHANGE_CONTROLS or EXCHANGE_CONTROL_PROFILES may author a published slug.
# Switzerland is the first live layered consumer.
EXCHANGE_CONTROL_PROFILES: Dict[str, dict] = {
    "switzerland": {
        "classification_mode": "layered",
        "posture": "layered",
        "label": (
            "IMF exchange system free of multiple currency practices and of restrictions "
            "on payments and transfers for current international transactions except "
            "security-related restrictions notified under Decision No. 144–(52/51); "
            "separate Swiss sanctions architecture under the Embargo Act and "
            "actor-/transaction-specific OECD capital and investment reservations."
        ),
        "components": [
            {
                "scope": "Current international transactions",
                "summary": (
                    "The IMF 2026 Informational Annex describes Switzerland's exchange system as "
                    "free of multiple currency practices and of restrictions on payments and "
                    "transfers for current international transactions, except security-related "
                    "restrictions notified pursuant to Executive Board Decision No. 144–(52/51)."
                ),
            },
            {
                "scope": "Security and sanctions",
                "summary": (
                    "The Embargo Act is the Swiss framework law for sanctions implementation; "
                    "concrete measures are contained in separate ordinances, and the Federal "
                    "Council may enact measures such as financial sanctions, trade restrictions, "
                    "travel bans and asset freezes."
                ),
            },
            {
                "scope": "Capital and investment reservations",
                "summary": (
                    "OECD Code Annex B records actor- and transaction-specific Swiss reservations, "
                    "including specified inward direct-investment situations, non-resident "
                    "real-estate acquisition controls, and private pension-fund / insurance limits "
                    "on foreign securities, money-market instruments and deposits with "
                    "non-resident financial institutions."
                ),
            },
            {
                "scope": "Classification boundary",
                "summary": (
                    "SNB monetary-policy intervention, Swiss border-cash controls, AML/KYC "
                    "account-relationship duties, VAT conversion mechanics and SIC payment "
                    "infrastructure are not classified by the governed Switzerland rule as "
                    "exchange controls."
                ),
            },
        ],
    },
}

# Which rule fields the engine surfaces, and the ontology class each maps into.
RULE_FIELDS = {
    "bring_foreign_currency_in": {"label": "Bringing currency in", "ontology": "declaration-regimes"},
    "take_foreign_currency_out": {"label": "Taking currency out", "ontology": "import-export-ceilings"},
    "cash_declaration_threshold": {"label": "Declaration threshold", "ontology": "declaration-regimes"},
    "exchange_controls": {"label": "Exchange controls", "ontology": "exchange-controls"},
    "resident_holding_rules": {"label": "Resident rules", "ontology": "residency-divergence"},
    "non_resident_rules": {"label": "Non-resident rules", "ontology": "residency-divergence"},
    "banking_conversion_practicality": {"label": "Banking & channels", "ontology": "channel-restrictions"},
}


def sources_for_field(source_map, field):
    """Return the complete ordered source list for rules.<field>.

    Copies upstream ``source_map['rules.<field>']`` entries without legal or
    content transformation, preserving order and every source property
    (url, section, pages, status, etc.). Returns [] when no valid list exists.
    """
    entry = source_map.get(f"rules.{field}")
    if isinstance(entry, list):
        return copy.deepcopy(entry)
    return []


def is_numeric_amount(value: Any) -> bool:
    """True for int/float amounts; False for bool (bool is a Python int subclass)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def format_amount_value(value: Any) -> str:
    """Format a threshold amount without truncating decimals or forcing ``.0``.

    Integers render as ``10,000``. Meaningful decimals are preserved
    (``10000.5`` → ``10,000.5``). Bool is rejected.
    """
    if not is_numeric_amount(value):
        raise TypeError(
            f"amount value must be int or float, not {type(value).__name__}"
        )
    if isinstance(value, int):
        return f"{value:,}"
    # Float path: use Decimal(str(...)) to avoid binary float artifacts and
    # preserve authored decimal literals faithfully.
    from decimal import Decimal

    d = Decimal(str(value))
    sign = "-" if d < 0 else ""
    d = abs(d)
    if d == d.to_integral_value():
        return f"{sign}{int(d):,}"
    fixed = format(d, "f")
    whole, frac = fixed.split(".", 1)
    frac = frac.rstrip("0")
    return f"{sign}{int(whole):,}.{frac}" if frac else f"{sign}{int(whole):,}"


def validate_trigger(trigger: dict, ctx: str) -> List[str]:
    errors: List[str] = []
    if not isinstance(trigger, dict):
        return [f"{ctx}: trigger must be an object"]
    ttype = trigger.get("type")
    if ttype not in TRIGGER_TYPES:
        errors.append(f"{ctx}: trigger.type must be one of {sorted(TRIGGER_TYPES)}")
        return errors
    if ttype == "amount":
        if "value" not in trigger or not is_numeric_amount(trigger["value"]):
            errors.append(
                f"{ctx}: amount trigger requires numeric value "
                "(int or float; bool not allowed)"
            )
        if not trigger.get("currency"):
            errors.append(f"{ctx}: amount trigger requires currency")
        op = trigger.get("operator")
        if op not in AMOUNT_OPERATORS:
            errors.append(
                f"{ctx}: amount trigger requires operator in {sorted(AMOUNT_OPERATORS)} "
                "(no default; do not invent >=)"
            )
    elif ttype == "condition":
        if not str(trigger.get("condition") or "").strip():
            errors.append(f"{ctx}: condition trigger requires condition text")
        if "value" in trigger and trigger["value"] is not None:
            errors.append(f"{ctx}: condition trigger must not carry a numeric value")
    elif ttype == "always":
        if "value" in trigger and trigger["value"] is not None:
            errors.append(f"{ctx}: always trigger must not carry a numeric value")
    return errors


def validate_mechanism(mech: dict, idx: int) -> List[str]:
    errors: List[str] = []
    ctx = f"mechanisms[{idx}]"
    if not isinstance(mech, dict):
        return [f"{ctx}: must be an object"]
    kind = mech.get("kind")
    if kind not in MECHANISM_KINDS:
        errors.append(f"{ctx}: kind must be one of {sorted(MECHANISM_KINDS)}")
    errors.extend(validate_trigger(mech.get("trigger") or {}, f"{ctx}.trigger"))
    if not str(mech.get("mechanism") or "").strip():
        errors.append(f"{ctx}: mechanism text is required")
    if "ontology" in mech and mech["ontology"] is not None:
        # Allow explicit override; otherwise builder fills from MECHANISM_ONTOLOGY.
        if not isinstance(mech["ontology"], str):
            errors.append(f"{ctx}: ontology must be a string or null")
    return errors


def _declaration_mechanisms(mechs: List[dict]) -> List[dict]:
    return [m for m in mechs if isinstance(m, dict) and m.get("kind") == "declaration"]


def validate_declaration_mode_consistency(
    slug: str, mode: Optional[str], mechs: List[dict]
) -> List[str]:
    """Fail-closed consistency between declaration.mode and declaration mechanisms.

    Exclusivity (declaration-kind only; inquiry/registration/etc. are independent):

    - numeric_threshold: ≥1 amount; no always; no condition
    - always: ≥1 always; no amount; no condition
    - none_spontaneous: no amount; no always; condition MAY exist
    - not_established: zero declaration-kind mechanisms of any trigger type
    - mixed: ≥2 declaration mechanisms with ≥2 distinct trigger types
    """
    errors: List[str] = []
    if mode not in DECLARATION_MODES:
        return errors
    decl_mechs = _declaration_mechanisms(mechs)
    amount_decls = [
        m for m in decl_mechs
        if (m.get("trigger") or {}).get("type") == "amount"
    ]
    always_decls = [
        m for m in decl_mechs
        if (m.get("trigger") or {}).get("type") == "always"
    ]
    condition_decls = [
        m for m in decl_mechs
        if (m.get("trigger") or {}).get("type") == "condition"
    ]
    trigger_types = {
        (m.get("trigger") or {}).get("type")
        for m in decl_mechs
        if (m.get("trigger") or {}).get("type") in TRIGGER_TYPES
    }

    if mode == "numeric_threshold":
        if not amount_decls:
            errors.append(
                f"{slug}: declaration.mode=numeric_threshold requires at least one "
                "declaration-kind amount-trigger mechanism"
            )
        if always_decls:
            errors.append(
                f"{slug}: declaration.mode=numeric_threshold must not contain a "
                "declaration-kind always trigger"
            )
        if condition_decls:
            errors.append(
                f"{slug}: declaration.mode=numeric_threshold must not contain a "
                "declaration-kind condition trigger"
            )
    elif mode == "always":
        if not always_decls:
            errors.append(
                f"{slug}: declaration.mode=always requires at least one "
                "declaration-kind always-trigger mechanism"
            )
        if amount_decls:
            errors.append(
                f"{slug}: declaration.mode=always must not contain a "
                "declaration-kind amount trigger"
            )
        if condition_decls:
            errors.append(
                f"{slug}: declaration.mode=always must not contain a "
                "declaration-kind condition trigger"
            )
    elif mode == "none_spontaneous":
        if amount_decls or always_decls:
            errors.append(
                f"{slug}: declaration.mode=none_spontaneous must not contain a "
                "declaration-kind amount or always trigger (no spontaneous "
                "declaration obligation)"
            )
        # Conditional declaration-kind mechanisms MAY exist (request/condition-bound).
    elif mode == "not_established":
        if decl_mechs:
            errors.append(
                f"{slug}: declaration.mode=not_established requires zero "
                "declaration-kind mechanisms of any trigger type"
            )
    elif mode == "mixed":
        if len(decl_mechs) < 2 or len(trigger_types) < 2:
            errors.append(
                f"{slug}: declaration.mode=mixed requires heterogeneous declaration "
                "architecture (at least two declaration-kind mechanisms with "
                "distinct trigger types)"
            )
    return errors


def validate_border_cash_profile(slug: str, profile: dict) -> List[str]:
    errors: List[str] = []
    if not isinstance(profile, dict):
        return [f"{slug}: BORDER_CASH_CONTROLS entry must be an object"]
    decl = profile.get("declaration")
    mode: Optional[str] = None
    if not isinstance(decl, dict):
        errors.append(f"{slug}: declaration object is required")
    else:
        mode = decl.get("mode")
        if mode not in DECLARATION_MODES:
            errors.append(f"{slug}: declaration.mode must be one of {sorted(DECLARATION_MODES)}")
        # Single authored source: mechanisms[] only. Never author thresholds here.
        if "thresholds" in decl:
            errors.append(
                f"{slug}: declaration.thresholds must not be authored in "
                "BORDER_CASH_CONTROLS; mechanisms[] is the sole authored source and "
                "emitted thresholds are derived from declaration-kind amount mechanisms"
            )
    mechs = profile.get("mechanisms")
    if not isinstance(mechs, list):
        errors.append(f"{slug}: mechanisms must be a list")
        return errors
    for i, mech in enumerate(mechs):
        errors.extend(validate_mechanism(mech, i))
    if isinstance(decl, dict) and mode in DECLARATION_MODES:
        errors.extend(validate_declaration_mode_consistency(slug, mode, mechs))
    return errors


LAYERED_BANNED_SHORTHAND = (
    "fully liberalised",
    "fully liberalized",
    "no exchange controls",
    "no general exchange controls",
)


def _layered_banned_hits(text: str) -> List[str]:
    lowered = text.lower()
    return [banned for banned in LAYERED_BANNED_SHORTHAND if banned in lowered]


def validate_exchange_profile(slug: str, profile: dict) -> List[str]:
    errors: List[str] = []
    if not isinstance(profile, dict):
        return [f"{slug}: EXCHANGE_CONTROL_PROFILES entry must be an object"]
    if profile.get("classification_mode") != "layered":
        errors.append(f"{slug}: classification_mode must be 'layered'")
    if profile.get("posture") != "layered":
        errors.append(f"{slug}: posture must be 'layered'")
    label = str(profile.get("label") or "").strip()
    if not label:
        errors.append(f"{slug}: layered profile requires a non-empty label")
    for banned in _layered_banned_hits(label):
        errors.append(f"{slug}: layered label must not contain '{banned}'")
    comps = profile.get("components")
    if not isinstance(comps, list) or not comps:
        errors.append(f"{slug}: layered profile requires non-empty components")
    else:
        for i, comp in enumerate(comps):
            if not isinstance(comp, dict):
                errors.append(f"{slug}: components[{i}] must be an object")
                continue
            if not str(comp.get("scope") or "").strip():
                errors.append(f"{slug}: components[{i}].scope is required")
            summary = str(comp.get("summary") or "").strip()
            if not summary:
                errors.append(f"{slug}: components[{i}].summary is required")
            else:
                for banned in _layered_banned_hits(summary):
                    errors.append(
                        f"{slug}: components[{i}].summary must not contain '{banned}'"
                    )
    # Monetary-regime tokens must not be smuggled as the posture answer.
    for bad in ("floating_regulated_market", "capital_account_regulated", "supervisory_peg"):
        if profile.get("posture") == bad:
            errors.append(f"{slug}: layered profile must not use posture '{bad}'")
    return errors


def validate_transcription_tables(
    countries: Dict[str, dict],
    declaration: Dict[str, dict],
    border_cash: Dict[str, dict],
    exchange_controls: Dict[str, tuple],
    exchange_profiles: Dict[str, dict],
) -> List[str]:
    """Reject neither/both authorship for border-cash and exchange-control sources."""
    errors: List[str] = []
    published = set(countries)

    for slug in declaration:
        if slug not in published:
            errors.append(f"{slug}: in DECLARATION but not in published dataset")
        elif countries[slug].get("page_status") != "published":
            errors.append(f"{slug}: DECLARATION page_status is not published")
        if slug in border_cash:
            errors.append(
                f"{slug}: authored in both DECLARATION and BORDER_CASH_CONTROLS"
            )

    for slug in border_cash:
        if slug not in published:
            errors.append(f"{slug}: in BORDER_CASH_CONTROLS but not in published dataset")
        elif countries[slug].get("page_status") != "published":
            errors.append(f"{slug}: BORDER_CASH_CONTROLS page_status is not published")
        errors.extend(validate_border_cash_profile(slug, border_cash[slug]))

    for slug in published:
        in_legacy = slug in declaration
        in_typed = slug in border_cash
        if not in_legacy and not in_typed:
            errors.append(
                f"{slug}: published but missing from both DECLARATION and "
                "BORDER_CASH_CONTROLS"
            )

    for slug in exchange_controls:
        if slug not in published:
            errors.append(f"{slug}: in EXCHANGE_CONTROLS but not in published dataset")
        if slug in exchange_profiles:
            errors.append(
                f"{slug}: authored in both EXCHANGE_CONTROLS and "
                "EXCHANGE_CONTROL_PROFILES"
            )

    for slug in exchange_profiles:
        if slug not in published:
            errors.append(
                f"{slug}: in EXCHANGE_CONTROL_PROFILES but not in published dataset"
            )
        errors.extend(validate_exchange_profile(slug, exchange_profiles[slug]))

    for slug in published:
        in_legacy = slug in exchange_controls
        in_layered = slug in exchange_profiles
        if not in_legacy and not in_layered:
            errors.append(
                f"{slug}: published but missing from both EXCHANGE_CONTROLS and "
                "EXCHANGE_CONTROL_PROFILES"
            )

    return errors


def build_border_cash_record(profile: dict) -> dict:
    """Emit canonical border_cash from a validated typed profile."""
    mechs_out = []
    for mech in profile.get("mechanisms") or []:
        item = copy.deepcopy(mech)
        kind = item.get("kind")
        if "ontology" not in item:
            item["ontology"] = MECHANISM_ONTOLOGY.get(kind)
        if "ui_label" not in item:
            item["ui_label"] = KIND_UI_LABEL.get(kind, kind)
        mechs_out.append(item)

    decl_in = profile.get("declaration") or {}
    # Derived exclusively from declaration-kind amount mechanisms (never authored).
    compat_thresholds: List[dict] = []
    for mech in mechs_out:
        if mech.get("kind") != "declaration":
            continue
        trig = mech.get("trigger") or {}
        if trig.get("type") != "amount":
            continue
        compat_thresholds.append({
            "value": trig["value"],
            "currency": trig["currency"],
            "operator": trig["operator"],
            "scope": mech.get("scope", ""),
            "applies": mech.get("applies", ""),
            "authority": mech.get("authority", ""),
            "mechanism": mech.get("mechanism", ""),
        })

    record = {
        "declaration": {
            "mode": decl_in.get("mode"),
            "thresholds": compat_thresholds,
        },
        "mechanisms": mechs_out,
        "note": profile.get("note"),
        "transcribed_from": "rules.cash_declaration_threshold",
    }
    if profile.get("pair_surface_summary") is not None:
        record["pair_surface_summary"] = profile.get("pair_surface_summary")
    return record


def compatibility_declaration_from_border_cash(border_cash: dict) -> dict:
    """Legacy ``declaration`` view for typed jurisdictions."""
    decl = border_cash.get("declaration") or {}
    out: Dict[str, Any] = {
        "thresholds": copy.deepcopy(decl.get("thresholds") or []),
        "note": border_cash.get("note"),
        "transcribed_from": "rules.cash_declaration_threshold",
        "compatibility_view": True,
        "compatibility_note": (
            "declaration.thresholds lists declaration-kind numeric mechanisms only. "
            "Inspect border_cash for the complete typed border-cash architecture."
        ),
    }
    if border_cash.get("pair_surface_summary") is not None:
        out["pair_surface_summary"] = border_cash.get("pair_surface_summary")
    # Preserve mode for consumers that understand v1.1.
    if decl.get("mode") is not None:
        out["mode"] = decl.get("mode")
    return out


def build_exchange_controls_record(
    slug: str,
    exchange_controls: Dict[str, tuple],
    exchange_profiles: Dict[str, dict],
) -> dict:
    if slug in exchange_profiles:
        profile = exchange_profiles[slug]
        return {
            "classification_mode": "layered",
            "posture": "layered",
            "label": profile["label"],
            "components": copy.deepcopy(profile.get("components") or []),
            "transcribed_from": "rules.exchange_controls",
        }
    posture, label = exchange_controls[slug]
    return {
        "posture": posture,
        "label": label,
        "transcribed_from": "rules.exchange_controls",
    }


def assemble_country(
    slug: str,
    c: dict,
    declaration: Dict[str, dict],
    border_cash_table: Dict[str, dict],
    exchange_controls: Dict[str, tuple],
    exchange_profiles: Dict[str, dict],
) -> dict:
    sm = c.get("source_map", {})
    rules_out = {}
    for field, meta in RULE_FIELDS.items():
        if field in c["rules"]:
            sources = sources_for_field(sm, field)
            # Typed border-cash jurisdictions: taxonomy-neutral label for the
            # upstream cash_declaration_threshold prose (field name unchanged).
            label = meta["label"]
            if field == "cash_declaration_threshold" and slug in border_cash_table:
                label = "Border cash controls"
            rules_out[field] = {
                "label": label,
                "ontology": meta["ontology"],
                "text": c["rules"][field],
                "sources": sources,
                "source": sources[0] if sources else None,
            }

    out: Dict[str, Any] = {
        "country_name": c["country_name"],
        "country_slug": slug,
        "iso2": c.get("iso2", ""),
        "currency_code": c.get("currency_code", ""),
        "currency_name": c.get("currency_name", ""),
        "region": c.get("region", ""),
        "last_reviewed": c.get("last_reviewed", ""),
        "rules_page": f"/rules/{slug}-foreign-currency-rules.html",
        "rules": rules_out,
        "source_authorities": c.get("source_authorities", []),
        "disclaimer": c.get("disclaimer", ""),
    }

    if slug in border_cash_table:
        border = build_border_cash_record(border_cash_table[slug])
        out["border_cash"] = border
        out["declaration"] = compatibility_declaration_from_border_cash(border)
    else:
        decl = dict(declaration[slug])
        decl["transcribed_from"] = "rules.cash_declaration_threshold"
        out["declaration"] = decl

    out["exchange_controls"] = build_exchange_controls_record(
        slug, exchange_controls, exchange_profiles
    )
    return out


def build_payload(
    dataset: dict,
    declaration: Optional[Dict[str, dict]] = None,
    border_cash: Optional[Dict[str, dict]] = None,
    exchange_controls: Optional[Dict[str, tuple]] = None,
    exchange_profiles: Optional[Dict[str, dict]] = None,
) -> dict:
    declaration = DECLARATION if declaration is None else declaration
    border_cash = BORDER_CASH_CONTROLS if border_cash is None else border_cash
    exchange_controls = EXCHANGE_CONTROLS if exchange_controls is None else exchange_controls
    exchange_profiles = (
        EXCHANGE_CONTROL_PROFILES if exchange_profiles is None else exchange_profiles
    )

    countries = {c["country_slug"]: c for c in dataset["countries"]}
    errors = validate_transcription_tables(
        countries, declaration, border_cash, exchange_controls, exchange_profiles
    )
    if errors:
        raise ValueError("Transcription/dataset drift:\n  " + "\n  ".join(errors))

    out_countries = []
    for slug, c in sorted(countries.items(), key=lambda kv: kv[1]["country_name"]):
        out_countries.append(
            assemble_country(
                slug, c, declaration, border_cash, exchange_controls, exchange_profiles
            )
        )

    return {
        "engine": "ConvertCCY Passage Check",
        "version": ENGINE_VERSION,
        "built_from": "rules/dataset.json",
        "source_dataset_generated_at": dataset.get("generated_at", ""),
        "license": dataset.get("license", ""),
        "attribution": dataset.get("attribution", ""),
        "schema": {
            "border_cash": (
                "Optional canonical typed border-cash profile. Authored via "
                "BORDER_CASH_CONTROLS with declaration.mode + mechanisms[] only; "
                "emitted declaration.thresholds are derived from declaration-kind "
                "amount mechanisms. When present, country.declaration is a "
                "compatibility projection of those derived thresholds only."
            ),
            "exchange_controls.layered": (
                "posture 'layered' is a compositional routing value: no single "
                "legacy scalar posture faithfully captures the governed architecture; "
                "consumers must inspect label/components. It is not a severity, "
                "liberalisation, floating, crawl, peg, or capital-account conclusion."
            ),
        },
        "notice": (
            "Passage Check is deterministic and evidence-bound. It reports only what "
            "the published, source-mapped ConvertCCY country entries state. It contains "
            "governed border-cash mechanisms and exchange-control profiles transcribed "
            "from published country rules. Not every structured amount is a declaration "
            "threshold — inquiry, registration, carriage, permit, and enforcement "
            "mechanisms are typed separately in v1.1. Currency conversions shown in the "
            "tool are indicative only and are not governed figures. Existing v1.0-style "
            "records remain grandfathered until individually migrated."
        ),
        "count": len(out_countries),
        "countries": out_countries,
    }


def main():
    if not DATASET.exists():
        sys.exit(f"ERROR: {DATASET} not found. Run the rules generator first.")

    data = json.loads(DATASET.read_text(encoding="utf-8"))
    try:
        payload = build_payload(data)
    except ValueError as exc:
        sys.exit(str(exc))

    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(REPO)} — {len(payload['countries'])} published jurisdictions (v{ENGINE_VERSION})")
    for c in payload["countries"]:
        n = len(c["declaration"]["thresholds"])
        typed = "typed" if "border_cash" in c else "legacy"
        print(
            f"  {c['country_name']:24s} {c['currency_code']}  "
            f"{n} decl-threshold(s)  exch:{c['exchange_controls']['posture']}  [{typed}]"
        )


if __name__ == "__main__":
    main()
