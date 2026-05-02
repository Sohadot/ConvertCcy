"""
ConvertCCY sitemap generator
============================
generate_sitemap.py v1.2.1

Strong sitemap builder for root pages, articles, rules, and pair pages.
Avoids old GSC problems by:
- normalizing URLs
- skipping snippets, temp files, hidden files, and non-public files
- deduplicating entries
- generating shards when needed
- optionally writing sitemap index automatically
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import xml.etree.ElementTree as ET

SKIP_DIRS = {
    '.git', '.github', '__pycache__', 'node_modules', 'venv', '.venv',
    'scripts', 'data', 'assets', 'static', 'dist', 'build',
    # Never expose preview surfaces via sitemap.xml (staging / QA only)
    'preview',
}
SKIP_FILES = {
    'index-articles-section.html',
    '_sitemap_rules_fragment.xml',
}
SKIP_PATTERNS = (
    '.backup.', '.bak', '.tmp', 'copy of', 'draft-', '_draft', 'temp-',
)
PUBLISHABLE_ROOT_FILES = {
    'index.html', 'about.html', 'contact.html', 'currencies.html',
    'framework.html', 'manifesto.html', 'methodology.html',
    'privacy.html', 'disclaimer.html'
}
MAX_URLS_PER_SITEMAP = 40000


def iso_lastmod(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date().isoformat()


def should_skip_file(path: Path) -> bool:
    name = path.name.lower()
    if path.name in SKIP_FILES:
        return True
    if any(p in name for p in SKIP_PATTERNS):
        return True
    if ' ' in path.name or '(' in path.name or ')' in path.name:
        return True
    if path.suffix.lower() != '.html':
        return True
    return False


def is_public_html(site_root: Path, path: Path) -> bool:
    rel = path.relative_to(site_root)
    parts = rel.parts
    if any(p in SKIP_DIRS for p in parts[:-1]):
        return False
    if should_skip_file(path):
        return False

    # root html pages
    if len(parts) == 1:
        return parts[0] in PUBLISHABLE_ROOT_FILES

    # publishable section pages (exclude legacy /public/rules mirror; sovereign layer lives at /rules/)
    if parts[0] in {'articles', 'rules', 'pages'}:
        return True

    return False


def path_to_url(base_url: str, site_root: Path, path: Path) -> str:
    rel = path.relative_to(site_root).as_posix()
    if rel == 'index.html':
        return base_url + '/'
    if rel.endswith('/index.html'):
        return base_url + '/' + rel[:-10].rstrip('/') + '/'
    return base_url + '/' + quote(rel)


def classify_url(path: Path) -> tuple[str, str]:
    rel = path.as_posix()
    name = path.name
    if name == 'index.html' and path.parent.name == '':
        return 'daily', '1.0'
    if name == 'index.html' and path.parent.name in {'articles', 'rules'}:
        return 'weekly', '0.9'
    if path.parts and path.parts[0] == 'articles':
        return 'monthly', '0.75'
    if path.parts and path.parts[0] == 'rules':
        return 'monthly', '0.72'
    if path.parts and path.parts[0] == 'pages':
        return 'weekly', '0.65'
    if name in {'framework.html', 'manifesto.html', 'methodology.html'}:
        return 'monthly', '0.8'
    return 'monthly', '0.7'


def gather_public_html(site_root: Path):
    found = []
    for path in site_root.rglob('*.html'):
        if is_public_html(site_root, path):
            found.append(path)
    return sorted(found)


def build_url_entries(site_root: Path, base_url: str):
    entries = []
    seen = set()
    for path in gather_public_html(site_root):
        rel = path.relative_to(site_root)
        url = path_to_url(base_url, site_root, path)
        if url in seen:
            continue
        seen.add(url)
        changefreq, priority = classify_url(rel)
        entries.append({
            'url': url,
            'lastmod': iso_lastmod(path),
            'changefreq': changefreq,
            'priority': priority,
        })
    # force root first
    entries.sort(key=lambda x: (x['url'] != base_url + '/', x['url']))
    return entries


def write_urlset(entries, output_file: Path):
    urlset = ET.Element('urlset', {
        'xmlns': 'http://www.sitemaps.org/schemas/sitemap/0.9'
    })
    for entry in entries:
        u = ET.SubElement(urlset, 'url')
        ET.SubElement(u, 'loc').text = entry['url']
        ET.SubElement(u, 'lastmod').text = entry['lastmod']
        ET.SubElement(u, 'changefreq').text = entry['changefreq']
        ET.SubElement(u, 'priority').text = entry['priority']
    tree = ET.ElementTree(urlset)
    ET.indent(tree, space='  ')
    tree.write(output_file, encoding='utf-8', xml_declaration=True)


def write_sitemap_index(sitemap_urls, output_file: Path):
    root = ET.Element('sitemapindex', {
        'xmlns': 'http://www.sitemaps.org/schemas/sitemap/0.9'
    })
    today = datetime.now(timezone.utc).date().isoformat()
    for sm_url in sitemap_urls:
        sm = ET.SubElement(root, 'sitemap')
        ET.SubElement(sm, 'loc').text = sm_url
        ET.SubElement(sm, 'lastmod').text = today
    tree = ET.ElementTree(root)
    ET.indent(tree, space='  ')
    tree.write(output_file, encoding='utf-8', xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description='Generate strong sitemap.xml for ConvertCCY')
    parser.add_argument('--site-root', default='.', help='Project root')
    parser.add_argument('--base-url', default='https://convertccy.com', help='Canonical base URL')
    parser.add_argument('--output', default='sitemap.xml', help='Output sitemap or sitemap index')
    args = parser.parse_args()

    site_root = Path(args.site_root).resolve()
    base_url = args.base_url.rstrip('/')
    output = Path(args.output)
    if not output.is_absolute():
        output = site_root / output

    entries = build_url_entries(site_root, base_url)
    if not entries:
        raise SystemExit('No publishable HTML files found for sitemap generation.')

    if len(entries) <= MAX_URLS_PER_SITEMAP:
        write_urlset(entries, output)
        print(f'[OK] Generated {output} with {len(entries)} URLs')
        return

    # shard mode
    sitemap_urls = []
    chunks = [entries[i:i+MAX_URLS_PER_SITEMAP] for i in range(0, len(entries), MAX_URLS_PER_SITEMAP)]
    for i, chunk in enumerate(chunks, start=1):
        shard_name = f'sitemap-{i}.xml'
        shard_path = output.parent / shard_name
        write_urlset(chunk, shard_path)
        sitemap_urls.append(base_url + '/' + shard_name)
        print(f'[OK] Generated {shard_path} with {len(chunk)} URLs')

    write_sitemap_index(sitemap_urls, output)
    print(f'[OK] Generated sitemap index {output} with {len(chunks)} shards')


if __name__ == '__main__':
    main()
