#!/usr/bin/env python3
"""
C3 — Golden-fixture capture script (one-time; run before Slice 5 deletes seed/).

Captures tests/fixtures/askedgar/{slugs.json, headings.json, seed_page.html}
from live askedgar.readme.io using Playwright.

Usage:
    PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 python seed/capture_fixtures.py

The seed URL is https://askedgar.readme.io/reference/health_check_health_get.
If the site is unreachable (404, timeout, browser launch failure), this script
exits with a non-zero code and a clear error message. Do not re-run repeatedly;
if the site is consistently unavailable, create synthetic fixtures manually and
record the limitation in tests/fixtures/askedgar/README.md.

Output:
    tests/fixtures/askedgar/seed_page.html  — rendered HTML of seed URL (for offline discover_slugs)
    tests/fixtures/askedgar/slugs.json      — JSON array of discovered slug strings
    tests/fixtures/askedgar/headings.json   — JSON object {slug: [heading_key, ...]}

Note: headings.json uses the keys from extract_sections (all keys except _title),
exactly as produced by core.extract_sections — lowercased, stripped heading text.
"""

import json
import sys
import time
from pathlib import Path

# Resolve project root
PROJECT_ROOT = Path(__file__).parent.parent
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures" / "askedgar"

SEED_URL = "https://askedgar.readme.io/reference/health_check_health_get"
BASE_URL = "https://askedgar.readme.io"
LINK_PATTERN = "/reference/"
PAGE_TIMEOUT_MS = 25_000
SETTLE_SECONDS = 2.5
POLITE_DELAY_SECONDS = 0.8

# Add project root to sys.path so scraper imports work
sys.path.insert(0, str(PROJECT_ROOT))

from scraper import core  # noqa: E402


def fetch(page, url: str) -> str:
    """Navigate and return fully-rendered HTML."""
    page.goto(url, wait_until="networkidle", timeout=PAGE_TIMEOUT_MS)
    time.sleep(SETTLE_SECONDS)
    return page.content()


def main() -> int:
    from playwright.sync_api import sync_playwright

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Launching Playwright Chromium...", flush=True)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = ctx.new_page()

            try:
                print(f"Fetching seed page: {SEED_URL}", flush=True)
                seed_html = fetch(page, SEED_URL)

                # Save seed page HTML
                seed_html_path = FIXTURES_DIR / "seed_page.html"
                seed_html_path.write_text(seed_html, encoding="utf-8")
                print(f"Saved seed_page.html ({len(seed_html)} bytes)", flush=True)

                # Discover slugs
                pairs = core.discover_slugs(seed_html)
                if not pairs:
                    print("ERROR: no slugs discovered from seed page", file=sys.stderr)
                    return 1

                slugs = [slug for _label, slug in pairs]
                print(f"Discovered {len(slugs)} slugs", flush=True)

                # Save slugs.json
                slugs_path = FIXTURES_DIR / "slugs.json"
                slugs_path.write_text(
                    json.dumps(slugs, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                print(f"Saved slugs.json", flush=True)

                # Fetch each slug and collect headings
                headings: dict[str, list[str]] = {}
                for i, (label, slug) in enumerate(pairs, 1):
                    url = f"{BASE_URL}{LINK_PATTERN}{slug}"
                    print(f"  [{i}/{len(pairs)}] {slug}", flush=True)
                    try:
                        html = fetch(page, url)
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(html, "html.parser")
                        container = core.get_main(soup)
                        if container is not None:
                            sections = core.extract_sections(container)
                            heading_keys = [k for k in sections.keys() if k != "_title"]
                            headings[slug] = heading_keys
                        else:
                            headings[slug] = []
                        if i < len(pairs):
                            time.sleep(POLITE_DELAY_SECONDS)
                    except Exception as exc:
                        print(f"    WARNING: failed to fetch {slug}: {exc}", file=sys.stderr)
                        headings[slug] = []

                # Save headings.json
                headings_path = FIXTURES_DIR / "headings.json"
                headings_path.write_text(
                    json.dumps(headings, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                print(f"Saved headings.json ({len(headings)} entries)", flush=True)

            finally:
                ctx.close()
                browser.close()

    except Exception as exc:
        print(f"ERROR: capture failed: {exc}", file=sys.stderr)
        return 1

    print("Fixture capture complete.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
