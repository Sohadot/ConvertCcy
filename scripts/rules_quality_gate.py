"""
ConvertCCY rules quality gate
=============================
Final gate before publishing /rules/ layer.
Checks consistency between source data, generated pages, index, and sitemap fragment.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

PUBLISHABLE = {'verified', 'published'}


def load_json(path: Path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def fail(msg: str):
    print(f'[FAIL] {msg}')


def warn(msg: str):
    print(f'[WARN] {msg}')


def ok(msg: str):
    print(f'[OK] {msg}')


def get_source_authorities(data: dict) -> list:
    return data.get('source_authorities') or data.get('official_sources') or []


def main() -> int:
    root = Path('.')
    data_dir = root / 'data' / 'rules'
    rules_dir = root / 'rules'
    index_json_path = root / 'data' / 'rules_index.json'
    sitemap_fragment = rules_dir / '_sitemap_rules_fragment.xml'
    rules_index_html = rules_dir / 'index.html'

    errors = 0

    if not data_dir.exists():
        fail('data/rules directory is missing')
        return 1
    if not rules_dir.exists():
        fail('rules output directory is missing')
        return 1

    source_files = sorted(data_dir.glob('*.json'))
    publishable = []
    all_countries = []
    for f in source_files:
        data = load_json(f)
        all_countries.append(data)
        if data.get('page_status') in PUBLISHABLE:
            publishable.append(data)

    if not publishable:
        fail('No publishable country files found in data/rules')
        return 1

    # Check generated HTML pages
    for item in publishable:
        expected = rules_dir / f"{item['country_slug']}-foreign-currency-rules.html"
        if not expected.exists():
            fail(f'Missing generated page: {expected}')
            errors += 1

    if rules_index_html.exists():
        ok('rules/index.html exists')
    else:
        fail('rules/index.html is missing')
        errors += 1

    if index_json_path.exists():
        index_data = load_json(index_json_path)
        if len(index_data) != len(all_countries):
            fail(f'data/rules_index.json count mismatch: {len(index_data)} != {len(all_countries)}')
            errors += 1
        else:
            ok('data/rules_index.json count matches source data')
    else:
        fail('data/rules_index.json is missing')
        errors += 1

    if sitemap_fragment.exists():
        text = sitemap_fragment.read_text(encoding='utf-8')
        for item in publishable:
            expected_loc = f"https://convertccy.com/rules/{item['country_slug']}-foreign-currency-rules.html"
            if expected_loc not in text:
                fail(f'Sitemap fragment missing URL: {expected_loc}')
                errors += 1
        ok('rules/_sitemap_rules_fragment.xml exists')
    else:
        fail('rules/_sitemap_rules_fragment.xml is missing')
        errors += 1

    # Check minimum source discipline
    for item in publishable:
        sources = get_source_authorities(item)
        if len(sources) < 1:
            fail(f"{item['country_name']} has no official source authorities")
            errors += 1
        elif len(sources) < 2:
            warn(f"{item['country_name']} has only one official source")

        if not item.get('last_reviewed'):
            fail(f"{item['country_name']} is missing last_reviewed")
            errors += 1

        if not item.get('country_overview'):
            fail(f"{item['country_name']} is missing country_overview")
            errors += 1

    if errors:
        fail(f'Rules quality gate failed with {errors} error(s)')
        return 1

    ok(f'Rules quality gate passed for {len(publishable)} publishable countries')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
