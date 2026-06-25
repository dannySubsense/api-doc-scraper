"""
Unit tests for scraper/emit.py.

Acceptance criteria covered (FR-16a, FR-17, NFR-4, ARCHITECTURE §Emit layer):
- _atomic_write: parent dir creation; no partial file on exception
- write_document: raises ValueError on missing non-nullable FR-16a field
- write_document: YAML front-matter round-trips (parse back; fields intact; body unchanged)
- write_manifest: produces valid JSON; document_count == number of passed docs
- single_file mode: all docs concatenated into one file
- (xfail) write_document: raises/records when git_ref is missing for github_org platform
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest.mock
from pathlib import Path

import pytest
import yaml

from scraper.config import TargetConfig
from scraper.emit import Document, _atomic_write, write_document, write_manifest, write_all


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cfg(tmp_path: Path, output_mode: str = "per_doc", platform: str = "docusaurus") -> TargetConfig:
    """Return a TargetConfig whose output_dir is an absolute tmp_path.

    Because write_document computes: project_root / cfg.output_dir / doc.slug,
    and Path('/absolute/path') / Path('/other/absolute') returns the latter,
    passing an absolute tmp_path as output_dir redirects all writes into tmp_path.
    """
    return TargetConfig(
        name="test-target",
        platform=platform,
        output_dir=str(tmp_path),
        output_mode=output_mode,
    )


def _minimal_metadata(platform: str = "docusaurus") -> dict:
    """Return a metadata dict with all FR-16a non-nullable fields present."""
    return {
        "source_url": "https://example.com/page",
        "title": "Test Page",
        "platform": platform,
        "target": "test-target",
        "package": None,
        "repo": None,
        "breadcrumb": None,
        "fetched_at": "2026-06-25T12:00:00Z",
        "content_hash": "abc123def456abc123def456abc123def456abc123def456abc123def456abc1",
        "git_ref": None,
    }


def _make_doc(
    slug: str = "docs/page.md",
    body: str = "# Hello\n\nBody text.",
    platform: str = "docusaurus",
) -> Document:
    return Document(
        slug=slug,
        title="Test Page",
        body_markdown=body,
        metadata=_minimal_metadata(platform),
    )


# ---------------------------------------------------------------------------
# _atomic_write
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    def test_creates_parent_dirs(self, tmp_path: Path):
        """_atomic_write creates missing parent directories."""
        target = tmp_path / "a" / "b" / "c" / "file.md"
        _atomic_write(target, "content")
        assert target.exists()
        assert target.read_text(encoding="utf-8") == "content"

    def test_content_written_correctly(self, tmp_path: Path):
        """_atomic_write writes the exact content to the target path."""
        target = tmp_path / "out.md"
        _atomic_write(target, "hello world")
        assert target.read_text(encoding="utf-8") == "hello world"

    def test_no_partial_file_on_exception(self, tmp_path: Path):
        """If an exception occurs after mkstemp but before replace, no temp file persists."""
        target = tmp_path / "output.md"

        original_replace = os.replace

        def failing_replace(src, dst):
            raise OSError("simulated replace failure")

        with unittest.mock.patch("scraper.emit.os.replace", side_effect=failing_replace):
            with pytest.raises(OSError, match="simulated replace failure"):
                _atomic_write(target, "partial content")

        # Target file must not exist (write was aborted)
        assert not target.exists()
        # No .tmp files left behind
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == [], f"Leftover temp files: {tmp_files}"

    def test_overwrites_existing_file(self, tmp_path: Path):
        """_atomic_write replaces an existing file atomically."""
        target = tmp_path / "out.md"
        target.write_text("old content", encoding="utf-8")
        _atomic_write(target, "new content")
        assert target.read_text(encoding="utf-8") == "new content"

    def test_unicode_content_written_correctly(self, tmp_path: Path):
        """_atomic_write handles multi-byte Unicode content."""
        target = tmp_path / "unicode.md"
        content = "# Heading\n\nCafé résumé — unicode test."
        _atomic_write(target, content)
        assert target.read_text(encoding="utf-8") == content


# ---------------------------------------------------------------------------
# write_document — FR-16a field validation
# ---------------------------------------------------------------------------

class TestWriteDocumentValidation:
    @pytest.mark.parametrize("missing_field", [
        "source_url",
        "title",
        "platform",
        "target",
        "fetched_at",
        "content_hash",
    ])
    def test_raises_when_non_nullable_field_missing(
        self, tmp_path: Path, missing_field: str
    ):
        """FR-16a: missing any non-nullable field raises ValueError."""
        cfg = _make_cfg(tmp_path)
        meta = _minimal_metadata()
        del meta[missing_field]
        doc = Document(
            slug="page.md",
            title="Page",
            body_markdown="body",
            metadata=meta,
        )
        with pytest.raises(ValueError, match=missing_field):
            write_document(doc, cfg)

    @pytest.mark.parametrize("empty_field", [
        "source_url",
        "title",
        "platform",
        "target",
        "fetched_at",
        "content_hash",
    ])
    def test_raises_when_non_nullable_field_is_empty_string(
        self, tmp_path: Path, empty_field: str
    ):
        """FR-16a: empty string in a non-nullable field is also rejected."""
        cfg = _make_cfg(tmp_path)
        meta = _minimal_metadata()
        meta[empty_field] = ""
        doc = Document(
            slug="page.md",
            title="Page",
            body_markdown="body",
            metadata=meta,
        )
        with pytest.raises(ValueError, match=empty_field):
            write_document(doc, cfg)

    def test_raises_when_non_nullable_field_is_none(self, tmp_path: Path):
        """FR-16a: None value in a non-nullable field raises ValueError."""
        cfg = _make_cfg(tmp_path)
        meta = _minimal_metadata()
        meta["source_url"] = None
        doc = Document(
            slug="page.md",
            title="Page",
            body_markdown="body",
            metadata=meta,
        )
        with pytest.raises(ValueError):
            write_document(doc, cfg)

    def test_github_org_requires_git_ref_non_null(self, tmp_path: Path):
        """FR-16a: for github_org platform, git_ref must not be null."""
        cfg = _make_cfg(tmp_path, platform="github_org")
        meta = _minimal_metadata(platform="github_org")
        meta["git_ref"] = None  # violates FR-16a for github_org
        doc = Document(
            slug="page.md",
            title="Page",
            body_markdown="body",
            metadata=meta,
        )
        with pytest.raises(ValueError, match="git_ref"):
            write_document(doc, cfg)


# ---------------------------------------------------------------------------
# write_document — YAML front-matter round-trip
# ---------------------------------------------------------------------------

class TestWriteDocumentFrontMatter:
    def test_yaml_front_matter_parses_cleanly(self, tmp_path: Path):
        """The written file's front-matter block is valid YAML."""
        cfg = _make_cfg(tmp_path)
        doc = _make_doc()
        write_document(doc, cfg)

        output_file = tmp_path / doc.slug
        raw = output_file.read_text(encoding="utf-8")

        # Must start with ---
        assert raw.startswith("---\n")
        end = raw.index("\n---\n", 4)
        fm_text = raw[4:end]
        parsed = yaml.safe_load(fm_text)
        assert isinstance(parsed, dict)

    def test_front_matter_contains_all_required_keys(self, tmp_path: Path):
        """All FR-16a keys survive the YAML round-trip."""
        cfg = _make_cfg(tmp_path)
        doc = _make_doc()
        write_document(doc, cfg)

        output_file = tmp_path / doc.slug
        raw = output_file.read_text(encoding="utf-8")
        end = raw.index("\n---\n", 4)
        parsed = yaml.safe_load(raw[4:end])

        for key in ["source_url", "title", "platform", "target", "fetched_at", "content_hash"]:
            assert key in parsed, f"Key '{key}' missing from parsed front-matter"

    def test_body_unchanged_after_front_matter(self, tmp_path: Path):
        """The markdown body after the front-matter fence is exactly doc.body_markdown."""
        body = "# My Page\n\nSome content here.\n"
        cfg = _make_cfg(tmp_path)
        doc = _make_doc(body=body)
        write_document(doc, cfg)

        output_file = tmp_path / doc.slug
        raw = output_file.read_text(encoding="utf-8")

        # Content after the closing --- fence (plus newline + blank line)
        end_fence = raw.index("\n---\n", 4) + len("\n---\n\n")
        actual_body = raw[end_fence:]
        assert actual_body == body

    def test_nullable_fields_present_in_output(self, tmp_path: Path):
        """Nullable fields (package, repo, breadcrumb, git_ref) appear in front-matter."""
        cfg = _make_cfg(tmp_path)
        doc = _make_doc()
        write_document(doc, cfg)

        output_file = tmp_path / doc.slug
        raw = output_file.read_text(encoding="utf-8")
        end = raw.index("\n---\n", 4)
        parsed = yaml.safe_load(raw[4:end])

        for key in ["package", "repo", "breadcrumb", "git_ref"]:
            assert key in parsed, f"Nullable key '{key}' absent from front-matter"

    def test_file_written_atomically_to_correct_path(self, tmp_path: Path):
        """write_document creates the file at output_dir / slug."""
        cfg = _make_cfg(tmp_path)
        doc = _make_doc(slug="subdir/page.md")
        write_document(doc, cfg)
        assert (tmp_path / "subdir" / "page.md").exists()


# ---------------------------------------------------------------------------
# write_manifest
# ---------------------------------------------------------------------------

class TestWriteManifest:
    def test_manifest_is_valid_json(self, tmp_path: Path):
        """write_manifest produces a file that parses as valid JSON (AC-1d)."""
        cfg = _make_cfg(tmp_path)
        docs = [_make_doc("a.md"), _make_doc("b.md")]
        write_manifest(docs, [], cfg)

        manifest_path = tmp_path / "manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_document_count_equals_number_of_docs(self, tmp_path: Path):
        """manifest.document_count == len(docs) passed to write_manifest (AC-1d)."""
        cfg = _make_cfg(tmp_path)
        docs = [_make_doc("a.md"), _make_doc("b.md"), _make_doc("c.md")]
        write_manifest(docs, [], cfg)

        data = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert data["document_count"] == 3
        assert len(data["documents"]) == 3

    def test_manifest_contains_required_top_level_fields(self, tmp_path: Path):
        """Manifest has target, platform, generated_at, document_count, failure_count."""
        cfg = _make_cfg(tmp_path)
        write_manifest([], [], cfg)

        data = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        for field in ["target", "platform", "generated_at", "document_count", "failure_count", "documents", "failures"]:
            assert field in data, f"Missing manifest field: '{field}'"

    def test_manifest_document_entries_have_required_keys(self, tmp_path: Path):
        """Each documents[] entry has slug, title, source_url, content_hash."""
        cfg = _make_cfg(tmp_path)
        docs = [_make_doc("page.md")]
        write_manifest(docs, [], cfg)

        data = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        entry = data["documents"][0]
        for key in ["slug", "title", "source_url", "content_hash"]:
            assert key in entry, f"Missing document entry key: '{key}'"

    def test_manifest_failure_count_matches_failures_list(self, tmp_path: Path):
        """failure_count == len(failures) passed to write_manifest."""
        cfg = _make_cfg(tmp_path)
        failures = [
            {"identifier": "broken_page", "error": "HTTP 404"},
            {"identifier": "another_page", "error": "timeout"},
        ]
        write_manifest([], failures, cfg)

        data = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert data["failure_count"] == 2
        assert len(data["failures"]) == 2

    def test_manifest_written_atomically_no_partial_on_error(self, tmp_path: Path):
        """If manifest write fails mid-way, no partial manifest persists (NFR-4)."""
        cfg = _make_cfg(tmp_path)
        docs = [_make_doc("page.md")]

        original_replace = os.replace

        def failing_replace(src, dst):
            raise OSError("disk full")

        with unittest.mock.patch("scraper.emit.os.replace", side_effect=failing_replace):
            with pytest.raises(OSError, match="disk full"):
                write_manifest(docs, [], cfg)

        manifest_path = tmp_path / "manifest.json"
        assert not manifest_path.exists()
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == [], f"Leftover temp files: {tmp_files}"

    def test_empty_run_produces_valid_manifest(self, tmp_path: Path):
        """Zero docs and zero failures produces a valid manifest with counts == 0."""
        cfg = _make_cfg(tmp_path)
        write_manifest([], [], cfg)

        data = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert data["document_count"] == 0
        assert data["failure_count"] == 0
        assert data["documents"] == []
        assert data["failures"] == []


# ---------------------------------------------------------------------------
# single_file mode (FR-18)
# ---------------------------------------------------------------------------

class TestSingleFileMode:
    def test_single_file_created_at_expected_path(self, tmp_path: Path):
        """single_file mode writes output/<target>/<target>.md."""
        cfg = _make_cfg(tmp_path, output_mode="single_file")
        docs = [_make_doc("a.md"), _make_doc("b.md")]
        write_all(docs, [], cfg)

        expected = tmp_path / "test-target.md"
        assert expected.exists()

    def test_single_file_contains_all_doc_bodies(self, tmp_path: Path):
        """single_file concatenation includes every document's body_markdown."""
        cfg = _make_cfg(tmp_path, output_mode="single_file")
        doc1 = _make_doc("a.md", body="# Doc A\n\nContent A.")
        doc2 = _make_doc("b.md", body="# Doc B\n\nContent B.")
        write_all([doc1, doc2], [], cfg)

        combined = (tmp_path / "test-target.md").read_text(encoding="utf-8")
        assert "Content A." in combined
        assert "Content B." in combined

    def test_single_file_contains_front_matter_for_each_doc(self, tmp_path: Path):
        """Each doc's front-matter is present in the concatenated single file."""
        cfg = _make_cfg(tmp_path, output_mode="single_file")
        docs = [_make_doc("a.md"), _make_doc("b.md")]
        write_all(docs, [], cfg)

        combined = (tmp_path / "test-target.md").read_text(encoding="utf-8")
        # Each document section starts with ---
        fm_fences = combined.count("---\n")
        # At minimum 2 opening + 2 closing fences
        assert fm_fences >= 4

    def test_single_file_mode_also_writes_manifest(self, tmp_path: Path):
        """write_all in single_file mode still writes manifest.json."""
        cfg = _make_cfg(tmp_path, output_mode="single_file")
        docs = [_make_doc("a.md")]
        write_all(docs, [], cfg)

        manifest_path = tmp_path / "manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["document_count"] == 1
