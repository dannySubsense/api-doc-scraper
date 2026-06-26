"""
ReadMe.io platform adapter.

Wraps scraper/core.py (discover_slugs, get_main, extract_sections, render_sections).
Uses Playwright for browser-rendered SPA fetch (requires_browser = True).

Discovery: calls core.discover_slugs with options from ctx.config.options.
Applies discovery_min_slugs threshold + fallback_slugs; fast-fails on zero slugs
with no fallback.

Render: Playwright networkidle + settle -> core.get_main -> core.extract_sections
-> core.render_sections -> Document with FR-16a metadata (platform-specific nullable
fields set to None: package, repo, breadcrumb, git_ref).
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup

from scraper import core
from scraper.adapters.base import Item, PlatformAdapter, RunContext
from scraper.emit import Document

if TYPE_CHECKING:
    pass


class ReadMeIoAdapter(PlatformAdapter):
    name = "readme_io"
    requires_browser = True

    def discover(self, ctx: RunContext) -> list[Item]:
        """
        Fetch the seed URL via Playwright, parse sidebar links via core.discover_slugs.

        Applies discovery_min_slugs threshold: if fewer slugs than threshold are found,
        falls back to fallback_slugs from config. Raises RuntimeError on zero slugs
        with no fallback (fast-fail per UI-SPEC §Fast-fail).
        """
        opts = ctx.config.options
        seed_url: str = opts.get("seed_url", "")
        link_pattern: str = opts.get("link_pattern", "/reference/")
        slug_methods = opts.get("slug_methods", None)  # None -> core defaults
        slug_filter = opts.get("slug_filter", None)
        discovery_min_slugs: int = int(opts.get("discovery_min_slugs", 5))
        fallback_slugs: list[dict] = opts.get("fallback_slugs") or []

        if not seed_url:
            raise ValueError("readme_io adapter requires options.seed_url")

        page = ctx.page
        if page is None:
            raise RuntimeError("readme_io adapter requires a Playwright page (requires_browser=True)")

        # Fetch seed page with Playwright
        page.goto(
            seed_url,
            wait_until="networkidle",
            timeout=ctx.config.page_timeout_ms,
        )
        time.sleep(ctx.config.settle_seconds)
        html = page.content()

        pairs = core.discover_slugs(
            html,
            link_pattern=link_pattern,
            slug_methods=slug_methods if slug_methods else None,
            slug_filter=slug_filter,
        )

        if len(pairs) < discovery_min_slugs:
            if not fallback_slugs:
                raise RuntimeError(
                    f"readme_io discovery returned {len(pairs)} slugs "
                    f"(threshold: {discovery_min_slugs}) and no fallback_slugs configured"
                )
            # Use fallback list
            return [
                Item(
                    label=entry.get("label", entry["slug"]),
                    identifier=entry["slug"],
                )
                for entry in fallback_slugs
            ]

        return [Item(label=label, identifier=slug) for label, slug in pairs]

    def render(self, ctx: RunContext, item: Item) -> Document:
        """
        Fetch item page via Playwright, extract sections, return Document.

        Front-matter: all FR-16a fields present; nullable fields (package, repo,
        breadcrumb, git_ref) are explicitly None for readme_io platform.
        """
        opts = ctx.config.options
        base_url: str = opts.get("base_url", "")
        link_pattern: str = opts.get("link_pattern", "/reference/")

        if not base_url:
            raise ValueError("readme_io adapter requires options.base_url")

        page = ctx.page
        if page is None:
            raise RuntimeError("readme_io adapter requires a Playwright page (requires_browser=True)")

        # Build the full URL from base_url + link_pattern + slug
        slug = item.identifier
        source_url = f"{base_url.rstrip('/')}{link_pattern}{slug}"

        page.goto(
            source_url,
            wait_until="networkidle",
            timeout=ctx.config.page_timeout_ms,
        )
        time.sleep(ctx.config.settle_seconds)
        html = page.content()

        soup = BeautifulSoup(html, "html.parser")
        container = core.get_main(soup)
        if container is None:
            raise RuntimeError(f"readme_io: no main container found for slug '{slug}'")

        sections = core.extract_sections(container)

        # Use the assigned collision-safe slug from runner if available
        output_slug: str = item.extra.get("_slug") or f"{slug}.md"

        body_markdown = core.render_sections(sections, item.label, slug, source_url)

        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        content_hash = hashlib.sha256(body_markdown.encode("utf-8")).hexdigest()

        metadata = {
            "source_url": source_url,
            "title": item.label,
            "platform": "readme_io",
            "target": ctx.config.name,
            "package": None,        # readme_io: not applicable
            "repo": None,           # readme_io: not applicable
            "breadcrumb": None,     # readme_io: not applicable
            "fetched_at": fetched_at,
            "content_hash": content_hash,
            "git_ref": None,        # readme_io: not applicable
        }

        return Document(
            slug=output_slug,
            title=item.label,
            body_markdown=body_markdown,
            metadata=metadata,
        )
