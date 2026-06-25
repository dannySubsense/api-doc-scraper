#!/usr/bin/env python3
"""
AskEdgar API Reference Scraper  —  SEED / REFERENCE IMPLEMENTATION

This is the original, working, AskEdgar-specific scraper, ported verbatim from
the gap-lens-dilution repo as the worked example for the generalization effort.
It is the ground truth: whatever the generalized `scraper/` package produces for
the AskEdgar target must match what this script produces. Do not delete it until
`targets/askedgar.yaml` reproduces its output (see PLAN.md, Phase 2 sanity check).

Loads each /reference/{slug} page from askedgar.readme.io using Playwright,
extracts parameter + response documentation, writes raw markdown output to
docs/askedgar-reference-raw.md for gap-checking against askedgar-api-docs.md.

Usage:
    python seed/scrape_askedgar_reference.py             # full run
    python seed/scrape_askedgar_reference.py --discover  # list slugs only
    python seed/scrape_askedgar_reference.py --slug dilution_rating_v1_dilution_rating_get
"""

import argparse
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://askedgar.readme.io"
# Starting URL confirmed from site — slug pattern: {op_name}_{path_components}_{method}
SEED_URL = f"{BASE_URL}/reference/health_check_health_get"
OUTPUT_PATH = Path("docs/askedgar-reference-raw.md")

PAGE_TIMEOUT_MS = 25_000   # 25s max per page
SETTLE_SECONDS = 2.5       # extra wait after networkidle for SPA hydration
POLITE_DELAY_SECONDS = 0.8 # between pages — be courteous

# Fallback slug list derived from confirmed pattern + menu screenshot (2026-05-09).
# Menu sections in order: Public, Reverse Splits, Float/Outstanding, Dilution Rating,
# Nasdaq Compliance, Offerings-Advanced, Dilution Data, Offerings,
# Dilution Data-Advanced, Historical Float, ROFR & Tail Financings, Pump & Dump,
# News, Registrations, Agreements, AI Gap Analysis, Ownership, Research Reports,
# Screener, Market Strength, Filing Titles, Corporate Actions, Historical Tickers,
# Gap Stats.
# "Corporate Actions" is NOT in our existing docs — priority gap.
# Verified by auto-discovery run 2026-05-09 — 30 slugs confirmed from sidebar.
# "Corporate Actions" in the sidebar = split_status_v1_split_status_get (same endpoint).
# Note: /estimate and /health do not appear as endpoint-style slugs in the sidebar.
FALLBACK_SLUGS: list[tuple[str, str]] = [
    ("Health Check",                             "health_check_health_get"),
    ("Endpoint Listing",                         "list_endpoints_endpoints_get"),
    ("Reverse Splits",                           "reverse_splits_v1_reverse_splits_get"),
    ("Float, Outstanding, Market Cap & Key Data","float_outstanding_v1_float_outstanding_get"),
    ("Dilution Rating",                          "dilution_rating_v1_dilution_rating_get"),
    ("Historical Dilution Rating",               "historical_dilution_v1_historical_dilution_get"),
    ("Nasdaq Compliance",                        "nasdaq_compliance_v1_nasdaq_compliance_get"),
    ("Offerings — Funds & Underwriters",         "offerings_advanced_v1_offerings_advanced_get"),
    ("Dilution Data",                            "dilution_data_v1_dilution_data_get"),
    ("Offerings",                                "offerings_v1_offerings_get"),
    ("Dilution Data — Funds & Underwriters",     "funds_underwriters_v1_dilution_data_advanced_get"),
    ("Historical Float & Market Cap",            "historical_float_pro_v1_historical_float_pro_get"),
    ("Right of First Refusals & Tail Financings","rofr_v1_rofr_get"),
    ("Pump & Dump Tracker",                      "pump_and_dump_tracker_v1_pump_and_dump_tracker_get"),
    ("News",                                     "news_v1_news_get"),
    ("News Basic",                               "news_basic_v1_news_basic_get"),
    ("Registrations",                            "registrations_v1_registrations_get"),
    ("Agreements",                               "agreements_v1_agreements_get"),
    ("AI Gap Analysis",                          "ai_chart_analysis_v1_ai_chart_analysis_get"),
    ("Ownership",                                "ownership_v1_ownership_get"),
    ("Research Reports",                         "research_reports_v1_research_reports_get"),
    ("Research Reports — Short",                 "research_reports_short_v1_research_reports_short_get"),
    ("Research Reports — TLDR",                  "research_reports_tldr_v1_research_reports_tldr_get"),
    ("Screener",                                 "screener_v1_screener_get"),
    ("Screener Options",                         "screener_options_v1_screener_options_get"),
    ("Market Strength",                          "market_strength_v1_market_strength_get"),
    ("Filing Titles",                            "filing_titles_v1_filing_titles_get"),
    ("Corporate Actions (Split Status)",         "split_status_v1_split_status_get"),
    ("Historical Tickers",                       "historical_tickers_v1_historical_tickers_get"),
    ("Gap Stats",                                "gap_stats_v1_gap_stats_get"),
]


# ── helpers ──────────────────────────────────────────────────────────────────

def fetch(page, url: str) -> str:
    """Navigate and return fully-rendered HTML."""
    page.goto(url, wait_until="networkidle", timeout=PAGE_TIMEOUT_MS)
    time.sleep(SETTLE_SECONDS)
    return page.content()


def discover_slugs(html: str) -> list[tuple[str, str]]:
    """
    Parse a rendered reference page (e.g. the seed URL) and return
    [(label, slug), ...] for every /reference/ link found in the sidebar.
    Filters to slugs that look like operation-IDs (contain underscores and
    end with _get, _post, _put, _delete, or _patch).
    """
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    results: list[tuple[str, str]] = []

    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        if "/reference/" not in href:
            continue
        slug = href.split("/reference/")[-1].split("#")[0].split("?")[0].strip("/")
        if not slug or slug in seen:
            continue
        # Only keep endpoint-style slugs (operation IDs end with HTTP method)
        if not any(slug.endswith(f"_{m}") for m in ("get", "post", "put", "delete", "patch")):
            continue
        seen.add(slug)
        label = a.get_text(" ", strip=True) or slug
        results.append((label, slug))

    return results


def get_main(soup: BeautifulSoup):
    """Return the primary content container, stripping nav/aside noise."""
    container = (
        soup.find("article")
        or soup.find("div", attrs={"role": "main"})
        or soup.find("main")
        or soup.body
    )
    if container:
        for noise in container.find_all(["nav", "aside", "footer", "script", "style"]):
            noise.decompose()
    return container


def extract_sections(container) -> dict[str, list[str]]:
    """
    Walk the container and bucket text lines into named sections.
    Section boundaries are h1–h4 headings. Returns:
        {"_title": [...], "query params": [...], "response": [...], ...}
    """
    sections: dict[str, list[str]] = {"_title": []}
    current = "_title"

    for elem in container.find_all(True):
        tag = elem.name
        if tag in ("script", "style", "noscript"):
            continue

        if tag in ("h1", "h2", "h3", "h4"):
            heading = elem.get_text(" ", strip=True)
            if heading:
                key = heading.lower().strip()
                sections.setdefault(key, [])
                current = key
            continue

        # Leaf-ish elements: extract text and assign to current section
        if tag in ("p", "li", "td", "th", "dt", "dd", "span", "code", "pre"):
            # skip if a parent of the same meaningful tags already captured this
            if elem.find(["p", "li", "td", "th", "dt", "dd"]):
                continue
            text = elem.get_text(" ", strip=True)
            if text and len(text) > 1:
                sections[current].append(text)

    return sections


def render_sections(sections: dict[str, list[str]], label: str, slug: str, url: str) -> str:
    lines: list[str] = [f"## {label}", "", f"**Slug:** `{slug}`", f"**URL:** {url}", ""]

    # Title section — first meaningful lines (description text)
    title_lines = [t for t in sections.get("_title", []) if len(t) > 10]
    if title_lines:
        lines.append("### Overview")
        lines.extend(title_lines[:6])  # cap at 6 lines to avoid sidebar bleed
        lines.append("")

    # Params sections — any section whose key contains "param"
    for key, body in sections.items():
        if "param" in key and body:
            lines.append(f"### {key.title()}")
            lines.extend(body)
            lines.append("")

    # Response / responses section
    for key, body in sections.items():
        if key.startswith("response") and body:
            lines.append(f"### {key.title()}")
            lines.extend(body)
            lines.append("")

    # Everything else that isn't noise
    noise_keys = {"_title", "on this page", "table of contents", "contents"}
    for key, body in sections.items():
        if key in noise_keys or "param" in key or key.startswith("response"):
            continue
        if body:
            lines.append(f"### {key.title()}")
            lines.extend(body)
            lines.append("")

    return "\n".join(lines)


# ── core scrape ───────────────────────────────────────────────────────────────

def scrape_one(page, slug: str, label: str) -> str:
    url = f"{BASE_URL}/reference/{slug}"
    print(f"  {url}", flush=True)
    try:
        html = fetch(page, url)
        soup = BeautifulSoup(html, "html.parser")
        main = get_main(soup)
        if main is None:
            return f"## {label}\n\n**Error:** no main container found\n"
        sections = extract_sections(main)
        return render_sections(sections, label, slug, url)
    except Exception as exc:
        print(f"    ERROR: {exc}", file=sys.stderr)
        return f"## {label}\n\n**Slug:** `{slug}`\n**Error:** {exc}\n"


def build_browser_page(pw):
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    return browser, ctx, ctx.new_page()


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--discover", action="store_true", help="Print discovered slugs and exit (no individual page loads)")
    parser.add_argument("--slug", metavar="SLUG", help="Scrape a single slug (test mode)")
    parser.add_argument("--no-discover", action="store_true", help="Skip auto-discovery, use built-in fallback slug list")
    args = parser.parse_args()

    with sync_playwright() as pw:
        browser, ctx, page = build_browser_page(pw)
        try:
            if args.slug:
                slug_pairs = [(args.slug, args.slug)]
            elif args.no_discover:
                slug_pairs = FALLBACK_SLUGS
                print(f"Using fallback list: {len(slug_pairs)} slugs", flush=True)
            else:
                print(f"Loading seed page: {SEED_URL}", flush=True)
                seed_html = fetch(page, SEED_URL)
                slug_pairs = discover_slugs(seed_html)
                if len(slug_pairs) < 5:
                    print(f"Auto-discovery returned only {len(slug_pairs)} slugs — falling back to hardcoded list", flush=True)
                    slug_pairs = FALLBACK_SLUGS
                else:
                    print(f"Auto-discovered {len(slug_pairs)} endpoint slugs", flush=True)

            if args.discover:
                print("\nSlug list:")
                for label, slug in slug_pairs:
                    print(f"  {slug:60s}  {label}")
                return

            header = "\n".join([
                "# AskEdgar API Reference — Raw Scraped Output",
                "",
                f"Source: {SEED_URL}",
                "Date: 2026-05-09",
                "Purpose: Gap-check against docs/askedgar-api-docs.md",
                "Note: 'Corporate Actions' endpoint present in menu — not yet in our docs.",
                "",
                "---",
                "",
            ])
            parts = [header]

            for i, (label, slug) in enumerate(slug_pairs, 1):
                print(f"[{i}/{len(slug_pairs)}] {label}", flush=True)
                parts.append(scrape_one(page, slug, label))
                parts.append("\n---\n")
                if i < len(slug_pairs):
                    time.sleep(POLITE_DELAY_SECONDS)

        finally:
            ctx.close()
            browser.close()

    OUTPUT_PATH.write_text("\n".join(parts), encoding="utf-8")
    print(f"\nWrote {OUTPUT_PATH} ({OUTPUT_PATH.stat().st_size // 1024} KB)", flush=True)


if __name__ == "__main__":
    main()
