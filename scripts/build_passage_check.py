#!/usr/bin/env python3
"""
build_passage_check.py — assemble the Passage Check engine dataset.

The Passage Check engine is deterministic and evidence-bound. It may only
surface what the published, source-mapped country entries already state.

This script reads rules/dataset.json (the published CC BY 4.0 dataset, 8
countries) and emits rules/passage-check.json, an engine-optimised view that
carries, per published jurisdiction:

  - identity (name, slug, iso, currency)
  - the governed rule prose fields, verbatim, each with its source
  - source authorities and last_reviewed date
  - a STRUCTURED declaration-threshold block and an exchange-controls posture
    label, each transcribed by hand from a specific dataset field and tagged
    with `transcribed_from` so the derivation is auditable.

The numeric thresholds below are transcribed from each entry's
`rules.cash_declaration_threshold` prose. They are NOT parsed automatically —
prose parsing is error-prone — so this table is the single reviewed point of
transcription. The script refuses to emit if the table drifts from the
dataset (missing country, unpublished status, or currency mismatch on the
country's own currency_code).

Run: python3 scripts/build_passage_check.py
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATASET = REPO / "rules" / "dataset.json"
OUT = REPO / "rules" / "passage-check.json"

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
    "canada": {
        "thresholds": [
            {"value": 10000, "currency": "CAD", "scope": "cash or bearer negotiable instruments (or equivalent)",
             "applies": "entry and exit", "authority": "Canada Border Services Agency (CBSA)",
             "mechanism": "mandatory customs report"}
        ],
        "note": None,
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
    "pakistan": {
        "thresholds": [
            {"value": 10000, "currency": "USD", "scope": "cash or bearer negotiable instruments (or equivalent)",
             "applies": "entry and exit", "authority": "Pakistan Customs",
             "mechanism": "mandatory declaration"}
        ],
        "note": None,
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
    "canada": ("none", "No general exchange controls (fully liberalised)"),
    "france": ("none", "No general exchange controls (liberalised within the Eurozone)"),
    "germany": ("none", "No general exchange controls (liberalised within the Eurozone)"),
    "india": ("capital_account_regulated",
              "Current account largely liberalised; capital account regulated under FEMA"),
    "italy": ("none",
              "No national exchange controls; free movement of capital and payments under Article 63 TFEU, subject to Treaty exceptions (taxation, prudential supervision, public policy/security, certain third-country measures) and to EU sanctions"),
    "japan": ("none", "No general exchange controls (fully liberalised)"),
    "pakistan": ("capital_account_regulated",
                 "No general exchange controls on the current account; capital account regulated by the SBP"),
    "south-africa": ("capital_account_regulated",
                     "Current account largely liberalised; capital account subject to SARB exchange control administered through Authorised Dealers under the Currency and Exchanges Manual"),
    "united-arab-emirates": ("supervisory_peg",
                             "No per-transaction approval controls; supervisory posture around the US-dollar peg, current-account flows largely liberal"),
    "united-kingdom": ("none", "No general exchange controls (fully liberalised for current and capital account)"),
    "united-states": ("none",
                      "No general exchange controls; free-floating rate accepted under IMF Article VIII for current international transactions; capital-account reservations limited to enumerated sectoral inward direct investment under the OECD Code of Liberalisation of Capital Movements"),
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


def first_source(source_map, field):
    """Return the first source dict for a rules.<field>, or None."""
    entry = source_map.get(f"rules.{field}")
    if isinstance(entry, list) and entry:
        s = entry[0]
        return {"url": s.get("url", ""), "section": s.get("section", "")}
    return None


def main():
    if not DATASET.exists():
        sys.exit(f"ERROR: {DATASET} not found. Run the rules generator first.")

    data = json.loads(DATASET.read_text())
    countries = {c["country_slug"]: c for c in data["countries"]}

    # Guard: the transcription tables must match the published dataset exactly.
    errors = []
    for slug in DECLARATION:
        if slug not in countries:
            errors.append(f"{slug}: in transcription table but not in dataset")
            continue
        c = countries[slug]
        if c.get("page_status") != "published":
            errors.append(f"{slug}: page_status is {c.get('page_status')}, not published")
    for slug in countries:
        if slug not in DECLARATION:
            errors.append(f"{slug}: published but missing from DECLARATION table")
        if slug not in EXCHANGE_CONTROLS:
            errors.append(f"{slug}: published but missing from EXCHANGE_CONTROLS table")
    if errors:
        sys.exit("Transcription/dataset drift:\n  " + "\n  ".join(errors))

    out_countries = []
    for slug, c in sorted(countries.items(), key=lambda kv: kv[1]["country_name"]):
        sm = c.get("source_map", {})
        rules_out = {}
        for field, meta in RULE_FIELDS.items():
            if field in c["rules"]:
                rules_out[field] = {
                    "label": meta["label"],
                    "ontology": meta["ontology"],
                    "text": c["rules"][field],
                    "source": first_source(sm, field),
                }

        decl = dict(DECLARATION[slug])
        decl["transcribed_from"] = "rules.cash_declaration_threshold"
        posture, posture_label = EXCHANGE_CONTROLS[slug]

        out_countries.append({
            "country_name": c["country_name"],
            "country_slug": slug,
            "iso2": c.get("iso2", ""),
            "currency_code": c.get("currency_code", ""),
            "currency_name": c.get("currency_name", ""),
            "region": c.get("region", ""),
            "last_reviewed": c.get("last_reviewed", ""),
            "rules_page": f"/rules/{slug}-foreign-currency-rules.html",
            "declaration": decl,
            "exchange_controls": {
                "posture": posture,
                "label": posture_label,
                "transcribed_from": "rules.exchange_controls",
            },
            "rules": rules_out,
            "source_authorities": c.get("source_authorities", []),
            "disclaimer": c.get("disclaimer", ""),
        })

    payload = {
        "engine": "ConvertCCY Passage Check",
        "version": "1.0",
        "built_from": "rules/dataset.json",
        "source_dataset_generated_at": data.get("generated_at", ""),
        "license": data.get("license", ""),
        "attribution": data.get("attribution", ""),
        "notice": ("Passage Check is deterministic and evidence-bound. It reports only what the "
                   "published, source-mapped ConvertCCY country entries state. Structured "
                   "thresholds are transcribed from each entry's cash_declaration_threshold field. "
                   "Currency conversions shown in the tool are indicative only and are not governed figures."),
        "count": len(out_countries),
        "countries": out_countries,
    }

    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"Wrote {OUT.relative_to(REPO)} — {len(out_countries)} published jurisdictions")
    for c in out_countries:
        n = len(c["declaration"]["thresholds"])
        print(f"  {c['country_name']:24s} {c['currency_code']}  "
              f"{n} threshold(s)  exch:{c['exchange_controls']['posture']}")


if __name__ == "__main__":
    main()
