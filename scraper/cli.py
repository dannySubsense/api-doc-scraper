"""
CLI entry point for the multi-platform documentation scraper.

Usage:
    python -m scraper.cli --target <name> [flags]

Flags:
    --target NAME      (required) target name; resolves to targets/<name>.yaml
    --discover         list discovered items to stdout and exit; no files written
    --slug NAME        fetch one document by identifier; alias: --single
    --no-discover      skip live discovery; use target's fallback_slugs list
    --limit N          cap documents rendered (for smoke tests)

Mutual exclusion: --discover and --slug are mutually exclusive (exit 2).
Exit codes: 0 = success, 1 = runtime error, 2 = usage error.
"""

from __future__ import annotations

import argparse
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scraper.cli",
        description="Scrape API/reference documentation from a configured target.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--target",
        metavar="NAME",
        required=True,
        help="Target name; resolves to targets/<name>.yaml",
    )

    parser.add_argument(
        "--discover",
        action="store_true",
        default=False,
        help=(
            "Run discovery only: print discovered items to stdout and exit. "
            "Mutually exclusive with --slug."
        ),
    )

    parser.add_argument(
        "--slug",
        "--single",
        metavar="NAME",
        default=None,
        dest="slug",
        help=(
            "Fetch and render exactly one document by identifier. "
            "Aliases: --slug, --single. Mutually exclusive with --discover."
        ),
    )

    parser.add_argument(
        "--no-discover",
        action="store_true",
        default=False,
        dest="no_discover",
        help=(
            "Skip live discovery; use the target's configured fallback_slugs list. "
            "Applies to ReadMe.io targets."
        ),
    )

    parser.add_argument(
        "--limit",
        metavar="N",
        type=int,
        default=None,
        help="Cap the number of documents processed (for smoke tests).",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # Mutual exclusion: --discover + --slug -> exit 2
    if args.discover and args.slug:
        print("Error: --discover and --slug are mutually exclusive", file=sys.stderr)
        parser.print_usage(sys.stderr)
        sys.exit(2)

    # Validate --limit is positive
    if args.limit is not None and args.limit <= 0:
        print(
            f"Error: --limit must be a positive integer, got {args.limit}",
            file=sys.stderr,
        )
        parser.print_usage(sys.stderr)
        sys.exit(2)

    from scraper import runner  # noqa: PLC0415 — deferred to speed up --help

    exit_code = runner.run(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
