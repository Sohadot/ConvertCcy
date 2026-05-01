"""
Generate machine-readable seed files for most world countries/territories.
These are NOT publishable rule pages. They reserve identity, currency, region,
and next-step source targets for the Global FX Rules Reference Layer.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from babel.numbers import get_territory_currencies, get_currency_name
from countryinfo import CountryInfo
import pycountry

OUT_DIR = Path('data/rules_seed')
OUT_INDEX = Path('data/rules_seed_index.json')
EXCLUDE_SLUGS = {'india', 'morocco'}

ALIAS = {
    'Bahamas':'The Bahamas',
    'Bolivia, Plurinational State of':'Bolivia',
    'Brunei Darussalam':'Brunei',
    "Côte d'Ivoire":"Ivory Coast",
    'Congo, The Democratic Republic of the':'Democratic Republic of the Congo',
    'Congo':'Republic of the Congo',
    'Cabo Verde':'Cape Verde',
    'Czechia':'Czech Republic',
    'Micronesia, Federated States of':'Micronesia',
    'Gambia':'The Gambia',
    'Iran, Islamic Republic of':'Iran',
    'Korea, Republic of':'South Korea',
    'Korea, Democratic People\'s Republic of':'North Korea',
    'Macao':'Macau',
    'Moldova, Republic of':'Moldova',
    'North Macedonia':'North Macedonia',
    'Myanmar':'Myanmar',
    'Palestine, State of':'Palestine',
    'Timor-Leste':'East Timor',
    'Türkiye':'Turkey',
    'Taiwan, Province of China':'Taiwan',
    'Tanzania, United Republic of':'Tanzania',
    'Venezuela, Bolivarian Republic of':'Venezuela',
    'Viet Nam':'Vietnam',
    'Lao People\'s Democratic Republic':'Laos',
    'Russian Federation':'Russia',
    'Syrian Arab Republic':'Syria',
    'Holy See (Vatican City State)':'Vatican City',
    'Sao Tome and Principe':'São Tomé and Príncipe',
    'Eswatini':'Eswatini',
}

REGION_MAP = {
    'Northern Africa':'North Africa',
    'Middle Africa':'Sub-Saharan Africa',
    'Eastern Africa':'Sub-Saharan Africa',
    'Western Africa':'Sub-Saharan Africa',
    'Southern Africa':'Sub-Saharan Africa',
    'Sub-Saharan Africa':'Sub-Saharan Africa',
    'Western Asia':'Middle East',
    'Southern Asia':'South Asia',
    'Eastern Asia':'East Asia',
    'South-Eastern Asia':'Southeast Asia',
    'Southeast Asia':'Southeast Asia',
    'Central Asia':'Central Asia',
    'Eastern Europe':'Eastern Europe',
    'Western Europe':'Western Europe',
    'Northern Europe':'Northern Europe',
    'Southern Europe':'Southern Europe',
    'Central Europe':'Central Europe',
    'Northern America':'North America',
    'South America':'Latin America',
    'Central America':'Latin America',
    'Latin America and the Caribbean':'Latin America',
    'Caribbean':'Caribbean',
    'Australia and New Zealand':'Oceania',
    'Oceania':'Oceania',
    'Polynesia':'Pacific',
    'Melanesia':'Pacific',
    'Micronesia':'Pacific',
    'Caucasus':'Caucasus',
}

SPECIAL_SKIP_CURRENCIES = {'CHE','CHW','USN','USS','XCG'}


def slugify(name: str) -> str:
    s = name.lower()
    s = s.replace('&', ' and ')
    s = re.sub(r"[^a-z0-9]+", '-', s)
    return re.sub(r'-+', '-', s).strip('-')


def pick_currency(iso2: str):
    cur_codes = get_territory_currencies(iso2, tender=True) or []
    clean = [c for c in cur_codes if c not in SPECIAL_SKIP_CURRENCIES]
    if not clean:
        clean = cur_codes
    if not clean:
        return None, None
    chosen = clean[-1] if len(clean) > 1 and clean[0] in {'USD','EUR','ZAR'} else clean[0]
    try:
        cname = get_currency_name(chosen, locale='en') or chosen
    except Exception:
        cname = chosen
    return chosen, cname


def resolve_region(name: str):
    query = ALIAS.get(name, name)
    candidates = [query]
    try:
        country = pycountry.countries.lookup(name)
        for attr in ('official_name','common_name'):
            v = getattr(country, attr, None)
            if v and v not in candidates:
                candidates.append(v)
    except Exception:
        pass
    for q in candidates:
        try:
            info = CountryInfo(q).info()
            sub = info.get('subregion') or info.get('region') or ''
            if sub in REGION_MAP:
                return REGION_MAP[sub]
        except Exception:
            continue
    return None


def build_seed(country) -> dict | None:
    iso2 = getattr(country, 'alpha_2', None)
    iso3 = getattr(country, 'alpha_3', None)
    if not iso2 or not iso3:
        return None
    slug = slugify(country.name)
    if slug in EXCLUDE_SLUGS:
        return None
    currency_code, currency_name = pick_currency(iso2)
    if not currency_code:
        return None
    region = resolve_region(country.name)
    if not region:
        return None
    display_name = ALIAS.get(country.name, country.name)
    return {
        'country_name': display_name,
        'country_slug': slug,
        'iso2': iso2,
        'iso3': iso3,
        'region': region,
        'currency_code': currency_code,
        'currency_name': currency_name,
        'seed_status': 'unverified_seed',
        'seed_version': '1.0',
        'intended_page_path': f'/rules/{slug}-foreign-currency-rules.html',
        'source_targets': [
            {'type': 'central_bank', 'target_query': f'{display_name} central bank foreign exchange rules'},
            {'type': 'customs', 'target_query': f'{display_name} customs cash declaration foreign currency'},
            {'type': 'ministry', 'target_query': f'{display_name} ministry finance foreign exchange controls'},
        ],
        'notes': 'Machine-generated seed file for structured expansion of the Global FX Rules Reference Layer. This file is not publishable content. It must be upgraded to the full country rule schema and verified against official sources before public generation.'
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    seeds = []
    for country in sorted(pycountry.countries, key=lambda c: c.name):
        seed = build_seed(country)
        if not seed:
            continue
        out = OUT_DIR / f"{seed['country_slug']}.json"
        out.write_text(json.dumps(seed, indent=2, ensure_ascii=False), encoding='utf-8')
        seeds.append(seed)
    OUT_INDEX.write_text(json.dumps(seeds, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'[OK] Generated {len(seeds)} seed files in {OUT_DIR}')


if __name__ == '__main__':
    main()
