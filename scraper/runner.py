"""
Runner: full orchestration of a scraper target run.

Owns: config load, adapter resolution, optional Playwright lifecycle,
discovery with fallback, collision-safe slug assignment, --discover exit,
--limit truncation, render loop with per-item error capture (NFR-4),
stderr progress per UI-SPEC, and emit.write_all call.
"""

from __future__ import annotations

import os
import sys
import time
import urllib.request
from contextlib import contextmanager
from typing import TYPE_CHECKING

from scraper.adapters import ADAPTERS
from scraper.adapters.base import Item, RunContext
from scraper.config import load_target
from scraper import emit
from scraper.slugify import identifier_to_slug, resolve_collisions

if TYPE_CHECKING:
    import argparse


_USER_AGENT = (
    "Mozilla/5.0 (compatible; api-doc-scraper/0.1; "
    "+https://github.com/islandef/api-doc-scraper-multi-platform)"
)
_HTTP_TIMEOUT = 30  # seconds


def _http_get(url: str) -> str:
    """urllib GET with User-Agent + timeout; raises on non-2xx."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
        return resp.read().decode("utf-8")


@contextmanager
def _browser_if_needed(requires_browser: bool):
    """
    Context manager: yields a Playwright page if requires_browser is True,
    otherwise yields None. Manages the full Playwright lifecycle when needed.
    """
    if not requires_browser:
        yield None
        return

    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=_USER_AGENT,
        )
        page = ctx.new_page()
        try:
            yield page
        finally:
            ctx.close()
            browser.close()


def _get_github_token() -> str | None:
    """Return GitHub token from gh CLI or GITHUB_TOKEN env var."""
    import subprocess  # noqa: PLC0415

    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            token = result.stdout.strip()
            if token:
                return token
    except Exception:
        pass

    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token

    print(
        "Warning: no GitHub token found (gh auth token failed; GITHUB_TOKEN not set). "
        "Unauthenticated GitHub API access is rate-limited to ~60 requests/hour.",
        file=sys.stderr,
    )
    return None


def run(args: argparse.Namespace) -> int:
    """
    Execute a full scraper run based on parsed CLI args.

    Returns exit code (0 = success, 1 = runtime error, 2 = usage error).
    """
    # --- Config load ---
    cfg = load_target(args.target)  # exits 1 on error
    print(
        f"Loading target: {cfg.name}  (platform: {cfg.platform})",
        file=sys.stderr,
    )

    # --- Adapter resolution ---
    # ADAPTERS is already validated by load_target; KeyError cannot happen here
    adapter_class = ADAPTERS[cfg.platform]
    adapter = adapter_class()

    # --- GitHub token (github_org only) ---
    token = _get_github_token() if cfg.platform == "github_org" else None

    with _browser_if_needed(adapter.requires_browser) as page:
        ctx = RunContext(
            config=cfg,
            page=page,
            http_get=_http_get,
            token=token,
        )

        # --- Discovery ---
        if args.slug:
            # Single-item mode: synthetic Item, skip discovery
            print(
                f"Single-item mode: {args.slug}",
                file=sys.stderr,
            )
            raw_items = [Item(label=args.slug, identifier=args.slug)]
        elif getattr(args, "no_discover", False):
            # Fallback list mode
            fallback_slugs = cfg.options.get("fallback_slugs", [])
            raw_items = [
                Item(label=entry.get("label", entry["slug"]), identifier=entry["slug"])
                for entry in fallback_slugs
            ]
            print(
                f"Using fallback list: {len(raw_items)} items",
                file=sys.stderr,
            )
        else:
            print("Discovering items...", file=sys.stderr)
            raw_items = adapter.discover(ctx)
            discovered_count = len(raw_items)

            # Fallback if below threshold
            min_slugs = cfg.options.get("discovery_min_slugs", 5)
            if len(raw_items) < min_slugs:
                fallback_slugs = cfg.options.get("fallback_slugs", [])
                if not fallback_slugs:
                    print(
                        f'Error: discovery returned {len(raw_items)} items '
                        f'(below threshold {min_slugs}) and fallback_slugs is empty',
                        file=sys.stderr,
                    )
                    return 1
                raw_items = [
                    Item(label=entry.get("label", entry["slug"]), identifier=entry["slug"])
                    for entry in fallback_slugs
                ]
                print(
                    f"Auto-discovery returned only {discovered_count} slugs — "
                    f"falling back to fallback list ({len(raw_items)} items)",
                    file=sys.stderr,
                )
            else:
                print(f"Discovered {len(raw_items)} items", file=sys.stderr)

        if not raw_items:
            print(
                f'Error: discovery returned 0 items for target "{cfg.name}" '
                f'— no fallback configured',
                file=sys.stderr,
            )
            return 1

        # --- Collision-safe slug assignment (before render loop) ---
        id_to_slug = resolve_collisions(
            [
                (it.identifier, identifier_to_slug(it.identifier, cfg.platform))
                for it in raw_items
            ]
        )
        items = [
            Item(it.label, it.identifier, {**it.extra, "_slug": id_to_slug[it.identifier]})
            for it in raw_items
        ]

        # --- --discover exit point ---
        if args.discover:
            if args.limit:
                items = items[: args.limit]
            for it in items:
                print(f"  {it.identifier}  →  {id_to_slug[it.identifier]}")
            print(f"Discovered {len(items)} items", file=sys.stderr)
            return 0

        # --- --limit truncation ---
        total_discovered = len(items)
        if args.limit:
            items = items[: args.limit]

        # --- Regenerate output directory (NFR-3, AC-1d, ARCHITECTURE §output lifecycle) ---
        # "output/ is regenerated each run; history is not retained."
        # Clear the target's output dir before writing so the directory reflects
        # ONLY the current run — no accumulation across --limit or --slug runs.
        #
        # Belt-and-suspenders safety (defence in depth — config.py already
        # validated output_dir is a clean relative path):
        #   1. Resolve output_dir against cwd (not project root) so we get a
        #      canonical absolute path with no symlink or ".." components.
        #   2. Require resolved path is STRICTLY INSIDE cwd: it must be a
        #      descendant (is_relative_to) AND not equal to cwd itself.
        #   3. Only then rmtree + recreate.
        import shutil as _shutil  # noqa: PLC0415
        from pathlib import Path as _Path  # noqa: PLC0415
        _cwd = _Path.cwd().resolve()
        _resolved = (_cwd / cfg.output_dir).resolve()
        if _resolved == _cwd or not _resolved.is_relative_to(_cwd):
            print(
                f'Error: output_dir "{cfg.output_dir}" resolved to "{_resolved}" '
                f'which is not strictly inside cwd "{_cwd}" — aborting to prevent '
                f'accidental data loss',
                file=sys.stderr,
            )
            return 1
        if _resolved.exists():
            _shutil.rmtree(_resolved)
        _resolved.mkdir(parents=True, exist_ok=True)

        # --- Render loop ---
        docs: list[emit.Document] = []
        failures: list[dict] = []

        for i, it in enumerate(items, 1):
            print(f"[{i}/{len(items)}] {it.label}", file=sys.stderr)
            try:
                doc = adapter.render(ctx, it)
                docs.append(doc)
            except Exception as exc:
                err_msg = str(exc)
                print(f"  ERROR: {err_msg}", file=sys.stderr)
                failures.append({"identifier": it.identifier, "error": err_msg})

            # Polite delay between items (not after last item)
            if i < len(items) and not args.slug:
                time.sleep(cfg.polite_delay_seconds)

        # --- Emit ---
        try:
            emit.write_all(docs, failures, cfg)
        except Exception as exc:
            print(f"Error: failed to write manifest: {exc}", file=sys.stderr)
            return 1

        # --- Completion summary ---
        from pathlib import Path  # noqa: PLC0415
        project_root = Path(__file__).parent.parent
        output_dir = project_root / cfg.output_dir

        failure_part = f", {len(failures)} failure{'s' if len(failures) != 1 else ''}" if failures else ""
        limit_part = f" (limited to {len(items)} of {total_discovered} discovered)" if args.limit else ""
        doc_word = "document" if len(docs) == 1 else "documents"

        print(
            f"Wrote {len(docs)} {doc_word}{failure_part}{limit_part}",
            file=sys.stderr,
        )
        print(f"Output: {cfg.output_dir}/", file=sys.stderr)
        print(f"Manifest: {cfg.output_dir}/manifest.json", file=sys.stderr)

        return 0
