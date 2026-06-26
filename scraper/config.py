"""
Config layer: TargetConfig dataclass and load_target loader.

load_target reads targets/{name}.yaml, validates the platform field against the
ADAPTERS registry, and raises on unknown platforms (triggers exit 1 in CLI).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class TargetConfig:
    name: str
    platform: str           # "readme_io" | "docusaurus" | "github_org"
    output_dir: str         # relative to project root; default "output/{name}"
    output_mode: str        # "per_doc" (default) | "single_file" (readme_io parity)
    polite_delay_seconds: float = 0.8
    page_timeout_ms: int = 25_000
    settle_seconds: float = 2.5
    options: dict = field(default_factory=dict)
    # readme_io options: seed_url, base_url, link_pattern, slug_methods, slug_filter,
    #                    discovery_min_slugs, fallback_slugs, header
    # docusaurus options: sitemap_url, base_url, include_patterns, exclude_patterns,
    #                     content_selectors (list; default: ["article",
    #                     ".theme-doc-markdown", "main"])
    # github_org options: org, include_globs, include_archived


def load_target(name: str) -> TargetConfig:
    """
    Read targets/{name}.yaml, validate platform against ADAPTERS registry.

    Raises SystemExit(1) if the file is missing or the platform is unknown.
    Import of ADAPTERS is deferred to avoid circular imports.
    """
    # Locate the project root relative to this file (scraper/config.py -> project root)
    project_root = Path(__file__).parent.parent
    yaml_path = project_root / "targets" / f"{name}.yaml"

    if not yaml_path.exists():
        print(
            f'Error: target "{name}" not found. Expected targets/{name}.yaml',
            file=sys.stderr,
        )
        sys.exit(1)

    with yaml_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not raw or not isinstance(raw, dict):
        print(
            f'Error: targets/{name}.yaml is empty or not a valid YAML mapping',
            file=sys.stderr,
        )
        sys.exit(1)

    platform = raw.get("platform", "")
    if not platform:
        print(
            f'Error: targets/{name}.yaml is missing the required "platform" field',
            file=sys.stderr,
        )
        sys.exit(1)

    # Deferred import to avoid circular dependency (ADAPTERS is in adapters/__init__.py)
    from scraper.adapters import ADAPTERS  # noqa: PLC0415

    if platform not in ADAPTERS:
        print(
            f'Error: unknown platform "{platform}" in targets/{name}.yaml',
            file=sys.stderr,
        )
        sys.exit(1)

    output_dir = raw.get("output_dir", f"output/{name}")

    # --- output_dir safety validation (fast-fail before any destructive op) ---
    # Reject values that would cause rmtree to operate outside the working tree.
    _od = str(output_dir).strip() if output_dir is not None else ""
    if not _od:
        print(
            f'Error: targets/{name}.yaml has an empty "output_dir" value',
            file=sys.stderr,
        )
        sys.exit(1)
    _od_path = Path(_od)
    if _od_path.is_absolute():
        print(
            f'Error: targets/{name}.yaml "output_dir" must be a relative path, '
            f'got absolute: "{_od}"',
            file=sys.stderr,
        )
        sys.exit(1)
    if _od == ".":
        print(
            f'Error: targets/{name}.yaml "output_dir" must not be "." '
            f'(would wipe the working directory)',
            file=sys.stderr,
        )
        sys.exit(1)
    if any(part == ".." for part in _od_path.parts):
        print(
            f'Error: targets/{name}.yaml "output_dir" must not contain ".." '
            f'path components, got: "{_od}"',
            file=sys.stderr,
        )
        sys.exit(1)
    output_dir = _od  # normalised stripped string

    output_mode = raw.get("output_mode", "per_doc")
    polite_delay_seconds = float(raw.get("polite_delay_seconds", 0.8))
    page_timeout_ms = int(raw.get("page_timeout_ms", 25_000))
    settle_seconds = float(raw.get("settle_seconds", 2.5))
    options = raw.get("options", {}) or {}

    return TargetConfig(
        name=name,
        platform=platform,
        output_dir=output_dir,
        output_mode=output_mode,
        polite_delay_seconds=polite_delay_seconds,
        page_timeout_ms=page_timeout_ms,
        settle_seconds=settle_seconds,
        options=options,
    )
