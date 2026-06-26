"""
Integration tests for the Docusaurus adapter: AC-1a through AC-1d.

These tests require live network access to docs.thatopen.com and are
marked @pytest.mark.network so the default suite (pytest -q) excludes them.

Run with: pytest tests/test_docusaurus_ac1.py -m network

AC-1a: No output file contains chrome-bleed strings (Skip to main content, etc.)
AC-1b: Pages with <code>/<pre> in source HTML produce ``` fences in output
AC-1c: Every output file has valid YAML front-matter with all FR-16a fields
AC-1d: manifest.json document_count == len(documents) == .md file count
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tests.test_output_quality import output_dir_checker


@pytest.mark.network
def test_ac1_limited_run(tmp_path: Path) -> None:
    """
    AC-1a + AC-1b + AC-1c + AC-1d: run --target thatopen-docs --limit 5 into
    a temporary output directory, then assert all four quality-gate criteria
    pass over the produced files.

    Requires live access to docs.thatopen.com — excluded from default suite.
    """
    # Run the CLI as a subprocess so polite_delay_seconds and all runner
    # orchestration are exercised end-to-end.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scraper.cli",
            "--target",
            "thatopen-docs",
            "--limit",
            "5",
        ],
        capture_output=True,
        text=True,
        # Run from the project root so targets/thatopen-docs.yaml is found
        # and output is written to the project's output/ directory.
        cwd=Path(__file__).parent.parent,
    )

    # Surface stderr on failure to aid debugging
    assert result.returncode == 0, (
        f"CLI exited with code {result.returncode}.\n"
        f"STDOUT:\n{result.stdout}\n"
        f"STDERR:\n{result.stderr}"
    )

    # Locate the output directory (project root / output / thatopen-docs)
    project_root = Path(__file__).parent.parent
    output_dir = project_root / "output" / "thatopen-docs"

    assert output_dir.exists(), (
        f"Expected output directory not found: {output_dir}\n"
        f"STDERR:\n{result.stderr}"
    )

    # Assert AC-1a, AC-1b (lenient — no source HTML available), AC-1c, AC-1d
    # output_dir_checker raises AssertionError on any failure.
    output_dir_checker(output_dir, "docusaurus")
