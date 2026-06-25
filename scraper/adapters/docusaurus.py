"""
Docusaurus platform adapter.

DocusaurusAdapter(PlatformAdapter):
  requires_browser = False  — content is SSR'd; plain HTTP is sufficient.

discover(ctx):
  Fetches sitemap_url, parses <loc> URLs, applies include/exclude glob filters,
  returns list[Item]. Fast-fails on zero results.

render(ctx, item):
  Fetches the URL, selects content container by priority (article,
  .theme-doc-markdown, main), converts to markdown with htmlmd.to_markdown,
  builds Document with full FR-16a metadata.
"""

from __future__ import annotations

import fnmatch
import hashlib
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from scraper import htmlmd
from scraper.adapters.base import Item, PlatformAdapter, RunContext
from scraper.emit import Document

# Default content container selectors in priority order (Docusaurus)
_DEFAULT_SELECTORS = ["article", ".theme-doc-markdown", "main"]

# Regex to extract package from /api/@scope/pkg/ path pattern
_API_PACKAGE_RE = re.compile(
    r"^/api/(@[^/]+/[^/]+|[^/@][^/]*)(?:/|$)"
)


class DocusaurusAdapter(PlatformAdapter):
    name = "docusaurus"
    requires_browser = False

    def discover(self, ctx: RunContext) -> list[Item]:
        """
        Fetch sitemap_url and return list[Item] for all matching URLs.

        Applies include_patterns and exclude_patterns glob filters from options.
        Fast-fails (exit 1) if zero URLs remain after filtering.

        Item.identifier = full URL.
        Item.label = URL path (human-readable).
        """
        sitemap_url = ctx.config.options.get("sitemap_url", "")
        if not sitemap_url:
            print(
                "Error: docusaurus adapter requires options.sitemap_url",
                file=sys.stderr,
            )
            sys.exit(1)

        xml_text = ctx.http_get(sitemap_url)

        # Parse <loc> elements from the sitemap XML
        root = ElementTree.fromstring(xml_text)
        # Handle the sitemap namespace
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locs = [el.text.strip() for el in root.findall(".//sm:loc", ns) if el.text]
        if not locs:
            # Try without namespace (some sitemaps omit it)
            locs = [el.text.strip() for el in root.iter() if el.tag.endswith("loc") and el.text]

        include_patterns = ctx.config.options.get("include_patterns") or []
        exclude_patterns = ctx.config.options.get("exclude_patterns") or []

        filtered = []
        for url in locs:
            parsed = urlparse(url)
            path = parsed.path

            # Apply include_patterns (glob on path); default = accept all
            if include_patterns:
                if not any(fnmatch.fnmatch(path, pat) for pat in include_patterns):
                    continue

            # Apply exclude_patterns (glob on path)
            if exclude_patterns:
                if any(fnmatch.fnmatch(path, pat) for pat in exclude_patterns):
                    continue

            filtered.append(url)

        if not filtered:
            print(
                f"Error: discovery returned 0 URLs from {sitemap_url} "
                f"after applying include/exclude filters",
                file=sys.stderr,
            )
            sys.exit(1)

        return [
            Item(
                label=urlparse(url).path or url,
                identifier=url,
            )
            for url in filtered
        ]

    def render(self, ctx: RunContext, item: Item) -> Document:
        """
        Fetch item URL, extract content container, convert to markdown.

        Container selection: article > .theme-doc-markdown > main (first match).
        Raises ValueError if no container is found (recorded as NFR-4 failure by runner).
        Derives:
          - package: from /api/@scope/pkg/ path pattern
          - breadcrumb: path segments joined with ' / '
        Builds Document with full FR-16a metadata.
        """
        url = item.identifier
        html_text = ctx.http_get(url)

        soup = BeautifulSoup(html_text, "html.parser")

        # Select content container by priority order
        selectors = ctx.config.options.get("content_selectors") or _DEFAULT_SELECTORS
        container = None
        for sel in selectors:
            container = soup.select_one(sel)
            if container is not None:
                break

        if container is None:
            raise ValueError(
                f"No content container found in {url} "
                f"(tried: {', '.join(selectors)})"
            )

        # Convert to markdown
        body_markdown = htmlmd.to_markdown(container)

        # Derive title: prefer <h1> in container, fall back to <title> tag
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
        else:
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else url

        # Derive package from /api/@scope/pkg/ path pattern
        parsed = urlparse(url)
        path = parsed.path
        package = _extract_package(path)

        # Derive breadcrumb from path segments (strip query/fragment)
        breadcrumb = _path_to_breadcrumb(path)

        # content_hash: sha256 of body_markdown
        content_hash = hashlib.sha256(body_markdown.encode("utf-8")).hexdigest()

        # fetched_at: ISO-8601 UTC
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # slug: carried from runner via item.extra["_slug"]
        slug = item.extra.get("_slug", "")

        metadata = {
            "source_url": url,
            "title": title,
            "platform": "docusaurus",
            "target": ctx.config.name,
            "package": package,
            "repo": None,
            "breadcrumb": breadcrumb,
            "fetched_at": fetched_at,
            "content_hash": content_hash,
            "git_ref": None,
        }

        return Document(
            slug=slug,
            title=title,
            body_markdown=body_markdown,
            metadata=metadata,
        )


def _extract_package(path: str) -> str | None:
    """
    Derive package name from /api/@scope/pkg/ URL path pattern.

    Examples:
      /api/@thatopen/components-front/classes/Angle  -> @thatopen/components-front
      /api/components/classes/Foo                    -> components
      /docs/getting-started                          -> None
    """
    m = _API_PACKAGE_RE.match(path)
    if m:
        return m.group(1)
    return None


def _path_to_breadcrumb(path: str) -> str | None:
    """
    Derive a breadcrumb string from a URL path.

    Joins non-empty path segments with ' / ' separator.
    Example: /docs/getting-started -> docs / getting-started
    """
    segments = [s for s in path.split("/") if s]
    if not segments:
        return None
    return " / ".join(segments)
