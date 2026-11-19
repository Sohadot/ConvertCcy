#!/usr/bin/env python3
"""
ConvertCCY sitemap generator — compatibility entry point (SEO-A5.1)
====================================================================

`generate.py` is the single authoritative sitemap generator (DECISION_LOG: SEO-A1).
Since SEO-A5.1, sitemap.xml is a sitemap INDEX whose child sitemaps under
sitemaps/ each hold one semantic cohort (core pages, currency hubs, and one per
pair treatment), plus data/generated/sitemap_measurement_manifest.json.

This script used to build its own flat sitemap.xml with filesystem-based dates.
It now delegates to `generate.py --sitemaps-only`, so country-publication
workflows that still call it cannot overwrite the sitemap index with a second,
competing sitemap truth model. Options of the former script are accepted and
ignored, except that --output may no longer point anywhere but sitemap.xml.

Run after committing the pages whose URLs the sitemaps list:
    python3 scripts/generate_sitemap.py      # == python3 generate.py --sitemaps-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ConvertCCY semantic sitemaps (delegates to generate.py)")
    parser.add_argument("--site-root", default=".", help="ignored (repository root is used)")
    parser.add_argument("--base-url", default="https://convertccy.com", help="must be the canonical base URL")
    parser.add_argument("--output", default="sitemap.xml", help="must be sitemap.xml (the sitemap index)")
    args, _unknown = parser.parse_known_args()
    import generate
    if args.output != "sitemap.xml" or args.base_url.rstrip("/") != generate.BASE_URL:
        print("generate_sitemap.py: only the canonical sitemap index (sitemap.xml) at "
              f"{generate.BASE_URL} is supported; use generate.py --sitemaps-only")
        return 2
    generate.write_semantic_sitemaps(generate.load_pair_profiles(), strict=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
