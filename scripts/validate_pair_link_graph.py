#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_pair_link_graph.py — SEO-A2 internal-link graph gate for pair pages.

Builds the site's crawlable link graph from committed HTML and proves that
every pair page is reachable from the homepage through ordinary <a href>
links, with bounded depth and bounded related-link fan-out.

Graph model
  - Nodes: every *.html file in the repo outside .git/ and preview/.
  - Edges: href attributes of <a> elements only. <script>, <style> and
    <noscript> bodies are removed first, so JS template strings and
    JS-only navigation (e.g. the pair swap button) never count as links.
  - Internal targets are normalised to repo paths ("/x/" -> "x/index.html",
    "https://convertccy.com/..." -> local). Fragments and query strings are
    dropped. External, mailto:, tel:, javascript: links are ignored.
  - Depth: number of link hops from index.html (homepage = 0), shortest
    path, breadth-first.

Assertions (exit 1 on any failure)
  A  pair pages on disk == directed pairs implied by data/currencies.json
  B  every pair page reachable from index.html
  C  (= B) unreachable pair pages == 0
  D  sitemap-only pair pages (in sitemap.xml but not reachable from index.html) == 0
  E  isolated reverse-pair 2-cycles == 0
  F  every pair page has >= 1 non-pair inbound link
  G  max pair crawl depth <= MAX_DEPTH (3)
  H  every currency has exactly one hub at currencies/<code>.html, self-canonical
  I  every hub links all N-1 FROM pairs (and all N-1 TO pairs), all existing
  J  no broken internal .html links anywhere in the crawlable graph
  K  each pair page's Related Pairs block holds 1..MAX_RELATED pair links,
     and every pair page links both of its currency hubs

Run: python3 scripts/validate_pair_link_graph.py [--report]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List, Optional, Set

REPO = Path(__file__).resolve().parent.parent
SITE = "https://convertccy.com"
MAX_DEPTH = 3
MAX_RELATED = 16
EXCLUDE_TOP = {".git", "preview", "node_modules"}

STRIP_RE = re.compile(r"(?is)<(script|style|noscript)\b[^>]*>.*?</\1\s*>")
ANCHOR_RE = re.compile(r"(?is)<a\b[^>]*?\bhref\s*=\s*(\"([^\"]*)\"|'([^']*)')")
PAIR_RE = re.compile(r"^pages/([a-z0-9]{3})-to-([a-z0-9]{3})\.html$")
CANON_RE = re.compile(r'<link rel="canonical" href="([^"]+)"')
RELATED_BLOCK_RE = re.compile(
    r'(?s)<div class="sec-title">Related Pairs</div>\s*<div class="related-grid">(.*?)</div>'
)
SITEMAP_LOC_RE = re.compile(r"<loc>([^<]+)</loc>")


def sitemap_page_locs(root: Path) -> List[str]:
    """Page URLs exposed by sitemap.xml: a plain urlset, or the union of the child sitemaps of a
    sitemap index (SEO-A5.1). A child sitemap that the index names but the repo lacks is an error."""
    index = root / "sitemap.xml"
    if not index.exists():
        return []
    text = index.read_text(encoding="utf-8")
    locs = SITEMAP_LOC_RE.findall(text)
    if "<sitemapindex" not in text:
        return locs
    out: List[str] = []
    for child in locs:
        rel = re.sub(r"^https://convertccy\.com/", "", child)
        path = root / rel
        if not path.exists():
            raise FileNotFoundError(f"sitemap index references a missing child sitemap: {child}")
        out += SITEMAP_LOC_RE.findall(path.read_text(encoding="utf-8"))
    return out


def html_files(root: Path) -> List[str]:
    out = []
    for dp, dns, fns in os.walk(root):
        rel = Path(dp).relative_to(root)
        if rel.parts and rel.parts[0] in EXCLUDE_TOP:
            dns[:] = []
            continue
        dns[:] = [d for d in dns if not (not rel.parts and d in EXCLUDE_TOP)]
        for fn in fns:
            if fn.endswith(".html"):
                out.append((rel / fn).as_posix())
    return sorted(out)


def normalize(src: str, href: str) -> Optional[str]:
    href = href.strip()
    if href.startswith(SITE):
        href = href[len(SITE):] or "/"
    low = href.lower()
    if not href or href.startswith("#") or low.startswith(("http:", "https:", "//", "mailto:", "tel:", "javascript:", "data:")):
        return None
    href = href.split("#", 1)[0].split("?", 1)[0]
    if not href:
        return None
    if href.startswith("/"):
        path = href
    else:
        path = "/" + os.path.normpath(os.path.join(os.path.dirname(src), href)).replace("\\", "/")
    if path.endswith("/"):
        path += "index.html"
    path = os.path.normpath(path).replace("\\", "/").lstrip("/")
    return path or "index.html"


def anchors(text: str) -> List[str]:
    text = STRIP_RE.sub(" ", text)
    return [m.group(2) if m.group(2) is not None else m.group(3) for m in ANCHOR_RE.finditer(text)]


def build_graph(root: Path):
    files = html_files(root)
    fileset = set(files)
    out: Dict[str, Set[str]] = {}
    texts: Dict[str, str] = {}
    for f in files:
        text = (root / f).read_text(encoding="utf-8", errors="replace")
        texts[f] = text
        targets = set()
        for h in anchors(text):
            n = normalize(f, h)
            if n and n != f:
                targets.add(n)
        out[f] = targets
    return files, fileset, out, texts


def bfs(out: Dict[str, Set[str]], fileset: Set[str], start: str = "index.html") -> Dict[str, int]:
    depth = {start: 0}
    q = deque([start])
    while q:
        u = q.popleft()
        for v in out.get(u, ()):
            if v in fileset and v not in depth:
                depth[v] = depth[u] + 1
                q.append(v)
    return depth


def pct(values: List[int], p: float) -> int:
    s = sorted(values)
    if not s:
        return 0
    k = max(0, min(len(s) - 1, int(round(p * (len(s) - 1)))))
    return s[k]


def analyse(root: Path) -> dict:
    currencies = json.loads((root / "data" / "currencies.json").read_text(encoding="utf-8"))["currencies"]
    codes = sorted(c.upper() for c in currencies)
    expected_pairs = {f"pages/{a.lower()}-to-{b.lower()}.html" for a in codes for b in codes if a != b}

    files, fileset, out, texts = build_graph(root)
    pairs = sorted(f for f in files if PAIR_RE.match(f))
    inbound: Dict[str, Set[str]] = defaultdict(set)
    for src, tgts in out.items():
        for t in tgts:
            inbound[t].add(src)

    depth = bfs(out, fileset)

    def reverse(p: str) -> str:
        a, b = PAIR_RE.match(p).groups()
        return f"pages/{b}-to-{a}.html"

    sitemap_locs = set()
    for loc in sitemap_page_locs(root):   # SEO-A5.1: sitemap index -> child sitemaps
        n = normalize("index.html", loc)
        if n:
            sitemap_locs.add(n)

    pair_set = set(pairs)
    indeg = {p: len(inbound.get(p, ())) for p in pairs}
    nonpair_in = {p: sum(1 for s in inbound.get(p, ()) if s not in pair_set) for p in pairs}
    unreachable = [p for p in pairs if p not in depth]
    # Discoverable only via the sitemap: listed there but not reachable from the
    # homepage through <a href> links (a reverse-pair-only 2-cycle counts here).
    sitemap_only = [p for p in pairs if p in sitemap_locs and p not in depth]
    two_cycles = 0
    for p in pairs:
        r = reverse(p)
        if p < r and r in pair_set:
            if inbound.get(p, set()) <= {r} and inbound.get(r, set()) <= {p}:
                two_cycles += 1
    reverse_only = sum(1 for p in pairs if inbound.get(p) and inbound[p] == {reverse(p)})

    broken = defaultdict(set)
    for src, tgts in out.items():
        for t in tgts:
            if t.endswith(".html") and t not in fileset:
                broken[t].add(src)

    # Hubs
    hub_errors: List[str] = []
    hubs = {c: f"currencies/{c.lower()}.html" for c in codes}
    hub_files = sorted(f for f in files if f.startswith("currencies/"))
    if sorted(hubs.values()) != hub_files:
        hub_errors.append(
            f"hub file set mismatch: missing={sorted(set(hubs.values()) - set(hub_files))[:5]} "
            f"extra={sorted(set(hub_files) - set(hubs.values()))[:5]}"
        )
    canon_seen: Dict[str, str] = {}
    for c, h in hubs.items():
        if h not in fileset:
            continue
        canon = CANON_RE.findall(texts[h])
        if canon != [f"{SITE}/{h}"]:
            hub_errors.append(f"{h}: canonical {canon!r}")
        elif canon[0] in canon_seen:
            hub_errors.append(f"{h}: duplicate canonical with {canon_seen[canon[0]]}")
        else:
            canon_seen[canon[0]] = h
        tgts = out[h]
        want_from = {f"pages/{c.lower()}-to-{o.lower()}.html" for o in codes if o != c}
        want_to = {f"pages/{o.lower()}-to-{c.lower()}.html" for o in codes if o != c}
        if not want_from <= tgts:
            hub_errors.append(f"{h}: missing {len(want_from - tgts)} FROM-pair links")
        if not want_to <= tgts:
            hub_errors.append(f"{h}: missing {len(want_to - tgts)} TO-pair links")
        stray = {t for t in tgts if PAIR_RE.match(t)} - want_from - want_to
        if stray:
            hub_errors.append(f"{h}: {len(stray)} pair links not involving {c}")
    hubs_linked_from_index = all(f"currencies/{c.lower()}.html" in out.get("currencies.html", ()) for c in codes)

    # Pair navigation blocks
    nav_errors: List[str] = []
    related_counts: List[int] = []
    for p in pairs:
        a, b = PAIR_RE.match(p).groups()
        m = RELATED_BLOCK_RE.search(STRIP_RE.sub(" ", texts[p]))
        if not m:
            nav_errors.append(f"{p}: no Related Pairs block")
            continue
        rel = [normalize(p, h) for h in anchors(m.group(1))]
        rel_pairs = [x for x in rel if x and PAIR_RE.match(x)]
        related_counts.append(len(rel_pairs))
        if not (1 <= len(rel_pairs) <= MAX_RELATED):
            nav_errors.append(f"{p}: {len(rel_pairs)} related pair links")
        if p in rel_pairs:
            nav_errors.append(f"{p}: links to itself")
        for hub in (f"currencies/{a}.html", f"currencies/{b}.html"):
            if hub not in out[p]:
                nav_errors.append(f"{p}: missing hub link {hub}")

    pair_depths = [depth[p] for p in pairs if p in depth]
    indeg_values = list(indeg.values())
    return {
        "currencies": len(codes),
        "pair_pages": len(pairs),
        "expected_pairs": len(expected_pairs),
        "pair_set_matches": pair_set == expected_pairs,
        "reachable": len(pairs) - len(unreachable),
        "unreachable": len(unreachable),
        "unreachable_sample": unreachable[:5],
        "sitemap_pairs": len(pair_set & sitemap_locs),
        "sitemap_only": len(sitemap_only),
        "isolated_2_cycles": two_cycles,
        "reverse_only_inbound": reverse_only,
        "zero_inbound": sum(1 for v in indeg_values if v == 0),
        "exactly_one_inbound": sum(1 for v in indeg_values if v == 1),
        "no_nonpair_inbound": sum(1 for v in nonpair_in.values() if v == 0),
        "depth_max": max(pair_depths) if pair_depths else None,
        "depth_median": statistics.median(pair_depths) if pair_depths else None,
        "depth_hist": {str(k): pair_depths.count(k) for k in sorted(set(pair_depths))},
        "inbound_min": min(indeg_values) if indeg_values else 0,
        "inbound_median": statistics.median(indeg_values) if indeg_values else 0,
        "inbound_p90": pct(indeg_values, 0.90),
        "inbound_p99": pct(indeg_values, 0.99),
        "inbound_max": max(indeg_values) if indeg_values else 0,
        "inbound_max_page": max(indeg, key=indeg.get) if indeg else None,
        "related_min": min(related_counts) if related_counts else 0,
        "related_max": max(related_counts) if related_counts else 0,
        "broken_links": {k: sorted(v)[:3] for k, v in sorted(broken.items())},
        "hub_errors": hub_errors,
        "hubs_linked_from_currencies_html": hubs_linked_from_index,
        "nav_errors_count": len(nav_errors),
        "nav_errors_sample": nav_errors[:5],
    }


def check(r: dict) -> List[str]:
    f = []
    if not r["pair_set_matches"]:
        f.append(f"A: pair pages on disk ({r['pair_pages']}) != expected directed pairs ({r['expected_pairs']})")
    if r["unreachable"]:
        f.append(f"B/C: {r['unreachable']} pair pages unreachable from index.html, e.g. {r['unreachable_sample']}")
    if r["sitemap_only"]:
        f.append(f"D: {r['sitemap_only']} sitemap-only pair pages")
    if r["isolated_2_cycles"]:
        f.append(f"E: {r['isolated_2_cycles']} isolated reverse-pair 2-cycles")
    if r["no_nonpair_inbound"]:
        f.append(f"F: {r['no_nonpair_inbound']} pair pages without a non-pair inbound link")
    if r["depth_max"] is None or r["depth_max"] > MAX_DEPTH:
        f.append(f"G: max pair crawl depth {r['depth_max']} > {MAX_DEPTH}")
    if r["hub_errors"]:
        f.append(f"H/I: {len(r['hub_errors'])} hub errors, e.g. {r['hub_errors'][:3]}")
    if not r["hubs_linked_from_currencies_html"]:
        f.append("H: currencies.html does not link every currency hub")
    if r["broken_links"]:
        f.append(f"J: {len(r['broken_links'])} broken internal link targets, e.g. {list(r['broken_links'].items())[:3]}")
    if r["nav_errors_count"]:
        f.append(f"K: {r['nav_errors_count']} pair navigation errors, e.g. {r['nav_errors_sample']}")
    return f


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--root", default=str(REPO), help="site root to analyse (default: repo)")
    ap.add_argument("--report", action="store_true", help="print the full metrics JSON")
    args = ap.parse_args()
    r = analyse(Path(args.root))
    if args.report:
        print(json.dumps(r, indent=2))
    failures = check(r)
    print(
        f"pairs={r['pair_pages']} reachable={r['reachable']} depth_max={r['depth_max']} "
        f"2-cycles={r['isolated_2_cycles']} no-nonpair-inbound={r['no_nonpair_inbound']} "
        f"inbound min/median/p90/max={r['inbound_min']}/{r['inbound_median']}/{r['inbound_p90']}/{r['inbound_max']}"
    )
    if failures:
        print("FAIL")
        for x in failures:
            print(f"  - {x}")
        return 1
    print("PASS: pair internal-link graph")
    return 0


if __name__ == "__main__":
    sys.exit(main())
