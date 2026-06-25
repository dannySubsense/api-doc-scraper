"""
G1 offline regression gate for the ReadMe.io adapter (AC-3a, AC-3b, AC-3c).

These tests have ZERO network dependency. They use committed fixture files:
  tests/fixtures/askedgar/seed_page.html — rendered HTML for offline discover_slugs
  tests/fixtures/askedgar/slugs.json    — golden slug set (exact set equality)
  tests/fixtures/askedgar/headings.json — golden heading sets per slug

Fixture status: SYNTHETIC (see tests/fixtures/askedgar/README.md).
  Live capture was not possible at forge time (Playwright Chromium launch failure
  due to missing libnspr4.so on the host; site 404 also known). G1 is NON-BLOCKING
  per architect designation (Slice 2, 2026-06-25).

Both tests pass cleanly against synthetic fixtures.  Live-parity assertions
(comparing against the real askedgar.readme.io site) are marked @pytest.mark.network
and excluded from the default run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from scraper import core

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "askedgar"
SEED_PAGE_HTML = FIXTURES_DIR / "seed_page.html"
SLUGS_JSON = FIXTURES_DIR / "slugs.json"
HEADINGS_JSON = FIXTURES_DIR / "headings.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_slug_set() -> set[str]:
    """Load committed slugs.json and return as a set."""
    return set(json.loads(SLUGS_JSON.read_text(encoding="utf-8")))


def _load_headings() -> dict[str, list[str]]:
    """Load committed headings.json."""
    return json.loads(HEADINGS_JSON.read_text(encoding="utf-8"))


def _load_seed_html() -> str:
    """Load committed seed_page.html."""
    return SEED_PAGE_HTML.read_text(encoding="utf-8")


# Stub HTML pages for each synthetic slug — mirrors ReadMe.io endpoint page structure.
# These are the per-slug HTML equivalents used to reproduce the heading sets in
# headings.json.  They must be consistent with the headings.json fixture.
_STUB_PAGES: dict[str, str] = {
    "health_check_health_get": """
        <article>
          <h1>Health Check</h1>
          <p>Returns the health status of the API.</p>
          <h2>Query Params</h2>
          <p>No parameters required.</p>
          <h2>Response</h2>
          <p>200 OK — healthy</p>
        </article>
    """,
    "list_endpoints_endpoints_get": """
        <article>
          <h1>Endpoint Listing</h1>
          <p>Lists all available API endpoints.</p>
          <h2>Query Params</h2>
          <p>No parameters required.</p>
          <h2>Response</h2>
          <p>Array of endpoint objects.</p>
        </article>
    """,
    "dilution_rating_v1_dilution_rating_get": """
        <article>
          <h1>Dilution Rating</h1>
          <p>Returns dilution rating for a ticker.</p>
          <h2>Query Params</h2>
          <p>ticker: Stock ticker symbol (required)</p>
          <h2>Responses</h2>
          <p>200 OK — dilution rating object</p>
        </article>
    """,
}


# ---------------------------------------------------------------------------
# AC-3a: slug set identity (offline)
# ---------------------------------------------------------------------------

class TestSlugSetIdentity:
    """AC-3a: core.discover_slugs on seed_page.html produces the exact committed slug set."""

    def test_fixture_files_exist(self):
        """Precondition: all three fixture files must exist before the test can run."""
        assert SEED_PAGE_HTML.exists(), f"Missing fixture: {SEED_PAGE_HTML}"
        assert SLUGS_JSON.exists(), f"Missing fixture: {SLUGS_JSON}"
        assert HEADINGS_JSON.exists(), f"Missing fixture: {HEADINGS_JSON}"

    def test_slug_set_identity(self):
        """
        Feed committed seed_page.html to core.discover_slugs; compare against slugs.json.

        Exact set equality — order differences are permitted (AC-3a).
        Zero network calls.

        NOTE: Fixtures are SYNTHETIC (see tests/fixtures/askedgar/README.md).
        This test confirms that discover_slugs correctly parses the committed HTML
        and that slugs.json is the faithful record of that output.
        """
        html = _load_seed_html()
        golden = _load_slug_set()

        pairs = core.discover_slugs(html)
        discovered = {slug for _label, slug in pairs}

        missing = golden - discovered
        extra = discovered - golden

        assert not missing, (
            f"Slugs in fixture but NOT discovered from seed_page.html: {sorted(missing)}"
        )
        assert not extra, (
            f"Slugs discovered from seed_page.html but NOT in fixture: {sorted(extra)}"
        )

    def test_seed_page_html_is_non_empty(self):
        """seed_page.html must be a non-empty HTML file."""
        content = _load_seed_html()
        assert len(content) > 0, "seed_page.html is empty"
        assert "<html" in content.lower() or "<!doctype" in content.lower(), (
            "seed_page.html does not look like HTML"
        )

    def test_slugs_json_parses_as_list(self):
        """slugs.json must parse as a non-empty JSON array of strings."""
        data = json.loads(SLUGS_JSON.read_text(encoding="utf-8"))
        assert isinstance(data, list), "slugs.json must be a JSON array"
        assert len(data) > 0, "slugs.json must be non-empty"
        for s in data:
            assert isinstance(s, str) and s, f"Each slug must be a non-empty string, got: {s!r}"


# ---------------------------------------------------------------------------
# AC-3b: heading sets match (offline, structural consistency)
# ---------------------------------------------------------------------------

class TestHeadingSetsMatch:
    """
    AC-3b: extract_sections heading keys match headings.json for each slug.

    NOTE: Fixtures are SYNTHETIC. This test confirms structural consistency:
    that core.extract_sections produces the same heading-key shape when applied
    to stub HTML equivalent to what was used to generate headings.json.

    Live parity (comparing against real askedgar.readme.io rendered pages) is
    deferred — see tests/fixtures/askedgar/README.md.
    """

    def test_heading_sets_match(self):
        """
        For each slug in headings.json, run extract_sections on stub HTML and
        compare heading keys (all keys except _title) against the fixture.

        Exact set equality per slug (AC-3b). Zero network calls.
        """
        golden_headings = _load_headings()
        golden_slugs = _load_slug_set()

        assert set(golden_headings.keys()) == golden_slugs, (
            "headings.json keys do not match slugs.json — fixture inconsistency"
        )

        for slug, expected_headings in golden_headings.items():
            assert slug in _STUB_PAGES, (
                f"No stub HTML defined for slug '{slug}' — add it to _STUB_PAGES"
            )
            stub_html = _STUB_PAGES[slug]
            soup = BeautifulSoup(stub_html, "html.parser")
            container = core.get_main(soup)
            assert container is not None, (
                f"core.get_main returned None for slug '{slug}' stub HTML"
            )
            sections = core.extract_sections(container)
            actual_headings = [k for k in sections.keys() if k != "_title"]

            assert set(actual_headings) == set(expected_headings), (
                f"Heading set mismatch for '{slug}':\n"
                f"  expected: {sorted(expected_headings)}\n"
                f"  actual:   {sorted(actual_headings)}"
            )

    def test_headings_json_parses_as_object(self):
        """headings.json must parse as a non-empty JSON object."""
        data = _load_headings()
        assert isinstance(data, dict), "headings.json must be a JSON object"
        assert len(data) > 0, "headings.json must be non-empty"
        for slug, heading_list in data.items():
            assert isinstance(slug, str) and slug, f"Slug key must be a non-empty string"
            assert isinstance(heading_list, list), (
                f"Heading list for '{slug}' must be a JSON array"
            )

    def test_extract_sections_returns_title_plus_headings(self):
        """
        Structural check: extract_sections always returns a dict with at least
        a '_title' key, plus any heading keys from h1-h4 in the HTML.
        """
        for slug, stub_html in _STUB_PAGES.items():
            soup = BeautifulSoup(stub_html, "html.parser")
            container = core.get_main(soup)
            sections = core.extract_sections(container)

            assert "_title" in sections, (
                f"extract_sections missing '_title' key for slug '{slug}'"
            )
            assert isinstance(sections, dict), (
                f"extract_sections must return a dict for slug '{slug}'"
            )
            for key, lines in sections.items():
                assert isinstance(key, str), f"Section key must be a string"
                assert isinstance(lines, list), f"Section value must be a list"


# ---------------------------------------------------------------------------
# Network-gated tests (excluded from default CI run)
# ---------------------------------------------------------------------------

@pytest.mark.network
class TestLiveSiteParity:
    """
    Live parity checks against askedgar.readme.io.

    Excluded from default test run (requires --run-network or explicit mark).
    These tests require Playwright + live site access. Mark them as xfail or
    skip them when the site is unreachable.
    """

    def test_live_discover_returns_nonzero_slugs(self):
        """
        NETWORK: live discover via Playwright returns >= 1 slug.

        This is a manual verification step — documented in PROGRESS.md.
        Excluded from CI.
        """
        pytest.skip(
            "Live askedgar.readme.io parity check is manual (see PROGRESS.md). "
            "Playwright Chromium is not functional on this host (libnspr4.so missing)."
        )
