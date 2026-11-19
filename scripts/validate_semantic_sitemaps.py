#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_semantic_sitemaps.py — SEO-A5.1 gate for the semantic sitemap index and the
indexation-measurement manifest.

Fails closed unless:

  index        sitemap.xml is a sitemaps.org <sitemapindex> listing exactly the generator's
               child sitemaps (sitemaps/<cohort>.xml), each once, in cohort order, each with
               a <lastmod> equal to the newest <lastmod> inside that child
  children     every child exists, is a valid <urlset>, sorted lexically by <loc>, within the
               50,000-URL / 50 MiB protocol limits, with YYYY-MM-DD <lastmod> values
  membership   every URL appears in exactly one child; the union equals sitemap_entries()
               (the indexable URL set — this layer adds or removes nothing); each pair URL is
               in the child of its router treatment; every currency hub is in currency-hubs;
               every other URL is in core-pages; no standards_special pair (noindex,follow)
               is in any sitemap; every URL's file exists, carries no noindex robots, has a
               self canonical where it declares one, and is not a _redirects source; every
               indexable pair page on disk is listed
  generator    the committed index, children and data/generated/sitemap_measurement_manifest.json
               are byte-identical to what generate.py --sitemaps-only derives from the current
               repository (router + Git content history); URL source files must be committed
  manifest     per-cohort url_count, treatment, lastmod and totals agree with the children

Run: python3 scripts/validate_semantic_sitemaps.py
"""

from __future__ import annotations

import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (REPO, REPO / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import generate as g  # noqa: E402

NS = {"sm": g.SITEMAP_XMLNS}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ROBOTS_RE = re.compile(r'<meta name="robots" content="([^"]*)">')
CANON_RE = re.compile(r'<link rel="canonical" href="([^"]+)">')


def url_to_path(url: str) -> Path:
    rel = url[len(g.BASE_URL) + 1:] if url.startswith(g.BASE_URL + "/") else None
    if rel is None:
        raise ValueError(f"non-canonical host: {url}")
    if rel == "" or rel.endswith("/"):
        rel += "index.html"
    return REPO / rel


def main() -> int:
    errs = []
    counts = Counter()
    profiles = g.load_pair_profiles()
    fx = g.load_rate_snapshot()

    # --- index ------------------------------------------------------------
    index_text = (REPO / g.SITEMAP_INDEX_PATH).read_text(encoding="utf-8")
    try:
        root = ET.fromstring(index_text)
    except ET.ParseError as exc:
        print(f"FAIL: sitemap.xml is not well-formed: {exc}")
        return 1
    if root.tag != f"{{{g.SITEMAP_XMLNS}}}sitemapindex":
        print("FAIL: sitemap.xml must be a <sitemapindex>")
        return 1
    index_rows = [(s.findtext("sm:loc", namespaces=NS), s.findtext("sm:lastmod", namespaces=NS))
                  for s in root.findall("sm:sitemap", NS)]
    want_children = [g.sitemap_child_url(n) for n in g.SITEMAP_COHORT_ORDER]
    if [u for u, _ in index_rows] != want_children:
        errs.append(f"index children {[u for u, _ in index_rows]} != {want_children}")

    # --- children ----------------------------------------------------------
    member: dict = {}
    child_urls: dict = {}
    for (loc, idx_lastmod), name in zip(index_rows, g.SITEMAP_COHORT_ORDER):
        path = REPO / g.SITEMAP_CHILD_DIR / f"{name}.xml"
        if not path.exists():
            errs.append(f"missing child sitemap {path.name}")
            continue
        text = path.read_text(encoding="utf-8")
        if len(text.encode("utf-8")) > g.SITEMAP_MAX_BYTES:
            errs.append(f"{name}: exceeds 50 MiB")
        try:
            croot = ET.fromstring(text)
        except ET.ParseError as exc:
            errs.append(f"{name}: not well-formed ({exc})")
            continue
        if croot.tag != f"{{{g.SITEMAP_XMLNS}}}urlset":
            errs.append(f"{name}: must be a <urlset>")
        rows = [(u.findtext("sm:loc", namespaces=NS), u.findtext("sm:lastmod", namespaces=NS))
                for u in croot.findall("sm:url", NS)]
        if len(rows) > g.SITEMAP_MAX_URLS:
            errs.append(f"{name}: more than {g.SITEMAP_MAX_URLS} URLs")
        urls = [u for u, _ in rows]
        if urls != sorted(urls):
            errs.append(f"{name}: URLs not in lexical order")
        dates = [d for _, d in rows if d]
        bad = [d for d in dates if not DATE_RE.match(d)]
        if bad:
            errs.append(f"{name}: invalid lastmod values {bad[:3]}")
        if (max(dates) if dates else None) != idx_lastmod:
            errs.append(f"{name}: index lastmod {idx_lastmod} != newest child lastmod {max(dates) if dates else None}")
        for u in urls:
            if u in member:
                errs.append(f"{u} listed in both {member[u]} and {name}")
            member[u] = name
        child_urls[name] = urls
        counts[name] = len(urls)

    # --- membership --------------------------------------------------------
    entries = g.sitemap_entries(profiles)
    want_set = {u for u, _ in entries}
    if set(member) != want_set:
        errs.append(f"URL union != indexable set: +{sorted(set(member) - want_set)[:3]} "
                    f"-{sorted(want_set - set(member))[:3]}")
    redirects = set()
    rp = REPO / "_redirects"
    if rp.exists():
        for line in rp.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                redirects.add(line.split()[0])
    pair_paths = {f"pages/{p['pair_slug']}.html": (p["from_code"], p["to_code"]) for p in profiles.values()
                  if p["from_code"] != p["to_code"]}
    for url, name in member.items():
        try:
            path = url_to_path(url)
        except ValueError as exc:
            errs.append(str(exc))
            continue
        rel = path.relative_to(REPO).as_posix()
        if not path.exists():
            errs.append(f"{url}: no file {rel}")
            continue
        if "/preview/" in url:
            errs.append(f"{url}: preview surface")
        if "/" + url[len(g.BASE_URL) + 1:] in redirects:
            errs.append(f"{url}: is a _redirects source")
        page = path.read_text(encoding="utf-8", errors="replace")
        robots = ROBOTS_RE.search(page)
        if robots and "noindex" in robots.group(1):
            errs.append(f"{url}: noindex page in a sitemap")
        canon = CANON_RE.findall(page)
        if canon and canon != [url]:
            errs.append(f"{url}: canonical {canon[:1]} is not self")
        if rel in pair_paths:
            t = g.pair_semantic_treatment(*pair_paths[rel], fx)
            if g.PAIR_SITEMAP_COHORTS.get(t) != name:
                errs.append(f"{url}: treatment {t} but listed in {name}")
        elif rel.startswith("currencies/"):
            if name != "currency-hubs":
                errs.append(f"{url}: hub outside currency-hubs")
        elif name != "core-pages":
            errs.append(f"{url}: non-pair, non-hub URL outside core-pages")
    for rel, (a, b) in pair_paths.items():
        url = f"{g.BASE_URL}/{rel}"
        t = g.pair_semantic_treatment(a, b, fx)
        counts[f"router_{t}"] += 1
        if t in g.SITEMAP_EXCLUDED_TREATMENTS:
            if url in member:
                errs.append(f"{url}: {t} pair in a sitemap")
            counts["excluded_" + t] += 1
            continue
        if url not in member and g.pair_robots(a, b) == g.INDEXABLE_ROBOTS:
            errs.append(f"{url}: indexable pair missing from every sitemap")
    hubs = sorted(f"{g.BASE_URL}/currencies/{f.name}" for f in (REPO / "currencies").glob("*.html"))
    if child_urls.get("currency-hubs") != hubs:
        errs.append(f"currency-hubs lists {len(child_urls.get('currency-hubs', []))} URLs, repository has {len(hubs)} hubs")

    # --- generator equality (counts, routing, lastmod, manifest) -----------
    history, dirty, _unused, _elapsed = g.build_git_content_lastmod_index(REPO)
    dirty_sources = sorted(rel for _, rel in entries if rel in dirty)
    if not history:
        errs.append("Git history unavailable: content dates cannot be verified (need full history)")
    elif dirty_sources:
        errs.append(f"{len(dirty_sources)} sitemap URL source files uncommitted (e.g. {dirty_sources[:2]}); "
                    "commit them, then run python3 generate.py --sitemaps-only")
    else:
        files, manifest = g.build_semantic_sitemaps(profiles, history_dates=history, dirty_paths=dirty, snapshot=fx)
        for rel, text in sorted(files.items()):
            path = REPO / rel
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                errs.append(f"{rel} differs from generator output (run: python3 generate.py --sitemaps-only)")
        committed = json.loads((REPO / g.MEASUREMENT_MANIFEST_PATH).read_text(encoding="utf-8")) \
            if (REPO / g.MEASUREMENT_MANIFEST_PATH).exists() else {}
        for name in g.SITEMAP_COHORT_ORDER:
            m = committed.get("sitemaps", {}).get(name, {})
            if m.get("url_count") != counts.get(name):
                errs.append(f"manifest {name}.url_count {m.get('url_count')} != child {counts.get(name)}")
        if committed.get("totals", {}).get("sitemap_urls") != len(member):
            errs.append("manifest totals.sitemap_urls != sitemap URL union")

    print("semantic sitemaps: " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())) +
          f" union={len(member)} indexable_set={len(want_set)}")
    if errs:
        print(f"FAIL: {len(errs)}")
        for e in errs[:30]:
            print(f"  - {html.unescape(e)}")
        return 1
    print("PASS: semantic sitemap index, child sitemaps and measurement manifest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
