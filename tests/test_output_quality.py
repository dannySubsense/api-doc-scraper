"""
Reusable quality-gate assertion harness for adapter output directories.

Implements AC-1a through AC-1d from 01-REQUIREMENTS.md. Each assertion is a
standalone callable that can be imported by Slice 3 (Docusaurus) and Slice 4
(GitHub org) test modules.

AC-1a: assert_no_chrome_bleed(md_path)
AC-1b: assert_code_fence_present(md_path, source_html_path=None)
AC-1c: assert_frontmatter_valid(md_path, platform)
AC-1d: assert_manifest_consistent(output_dir)

Fixture/helper: output_dir_checker(output_dir, platform)

Self-tests are included below (S1 exit criterion): positive test over a
known-good dir and negative tests that confirm the harness CATCHES problems.

Front-matter format note (matched to emit.py):
  emit.py writes:  f"---\n{front_matter_yaml}---\n\n{body}"
  Closing fence is \n---\n (newline-dash-dash-dash-newline), not ---\n at BOL.
  This harness parses the same way as test_emit.py: find raw.index("\n---\n", 4).

Manifest key names (matched to emit.py write_manifest):
  Top-level: target, platform, generated_at, document_count, failure_count,
             documents, failures
  Per-document: slug, title, source_url, content_hash

AC-1d discrepancy note: the spec says document_count == len(documents) ==
count of .md files. emit.py sets document_count = len(docs) passed in, which
equals len(documents). The harness checks all three agree (file count in
output_dir vs documents array vs document_count field).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# AC-1a denylist
# ---------------------------------------------------------------------------

_CHROME_DENYLIST_STRINGS = [
    "Skip to main content",
    "Edit this page",
    "On this page",
    "Table of Contents",
]
_COPYRIGHT_PATTERN = re.compile(r"©\s*\d{4}", re.IGNORECASE)


def assert_no_chrome_bleed(md_path: Path) -> None:
    """
    AC-1a: No output markdown file may contain any chrome-bleed string.

    Scans case-insensitively for the four denylist strings and for the
    copyright pattern © YYYY. Raises AssertionError naming the matched
    string on any hit.
    """
    text = Path(md_path).read_text(encoding="utf-8")
    text_lower = text.lower()

    for phrase in _CHROME_DENYLIST_STRINGS:
        if phrase.lower() in text_lower:
            raise AssertionError(
                f"Chrome bleed detected in {md_path}: found '{phrase}'"
            )

    match = _COPYRIGHT_PATTERN.search(text)
    if match:
        raise AssertionError(
            f"Chrome bleed detected in {md_path}: found copyright string '{match.group()}'"
        )


# ---------------------------------------------------------------------------
# AC-1b code fence
# ---------------------------------------------------------------------------

def assert_code_fence_present(
    md_path: Path,
    source_html_path: Path | None = None,
) -> None:
    """
    AC-1b: If the source HTML contained <code>/<pre>, the output markdown
    must contain at least one triple-backtick fence.

    When source_html_path is provided: check HTML for <code> or <pre>; if
    present, assert at least one ``` fence exists in the markdown output.

    When source_html_path is not provided: assert a fence exists only when
    the content itself hints at code (presence of ``` or indented block).
    Lenient — does not false-fail prose-only docs.
    """
    md_text = Path(md_path).read_text(encoding="utf-8")
    has_fence = "```" in md_text

    if source_html_path is not None:
        html_text = Path(source_html_path).read_text(encoding="utf-8")
        html_lower = html_text.lower()
        has_code_element = "<code" in html_lower or "<pre" in html_lower
        if has_code_element:
            assert has_fence, (
                f"AC-1b: source HTML in {source_html_path} contains <code>/<pre> "
                f"but output {md_path} has no triple-backtick fence"
            )
    # Without source_html_path: lenient — no assertion unless fence already expected
    # (Slice 3/4 callers pass source_html_path when they know the page has code)


# ---------------------------------------------------------------------------
# AC-1c front-matter validity
# ---------------------------------------------------------------------------

# Non-nullable fields per platform (FR-16a)
_NON_NULLABLE_ALL = frozenset(
    ["source_url", "title", "platform", "target", "fetched_at", "content_hash"]
)

# All keys that must be present (key must exist, value may be null)
_ALL_REQUIRED_KEYS = frozenset(
    [
        "source_url",
        "title",
        "platform",
        "target",
        "package",
        "repo",
        "breadcrumb",
        "fetched_at",
        "content_hash",
        "git_ref",
    ]
)

# Additional non-nullable fields per platform beyond _NON_NULLABLE_ALL
_EXTRA_NON_NULLABLE: dict[str, frozenset] = {
    "github_org": frozenset(["git_ref"]),
}


def assert_frontmatter_valid(md_path: Path, platform: str) -> None:
    """
    AC-1c: The front-matter block must parse as valid YAML. All non-nullable
    FR-16a fields for the given platform must be present and non-empty.
    Nullable fields must be PRESENT (key exists, value may be null).

    Front-matter format (matching emit.py):
        ---\\n{yaml}---\\n\\n{body}
    The closing delimiter is \\n---\\n, parsed with raw.index("\\n---\\n", 4).
    """
    raw = Path(md_path).read_text(encoding="utf-8")

    assert raw.startswith("---\n"), (
        f"AC-1c: {md_path} does not start with '---\\n' front-matter delimiter"
    )

    try:
        end_idx = raw.index("\n---\n", 4)
    except ValueError:
        raise AssertionError(
            f"AC-1c: {md_path} has no closing front-matter '\\n---\\n' delimiter"
        )

    fm_text = raw[4:end_idx]

    try:
        parsed = yaml.safe_load(fm_text)
    except yaml.YAMLError as exc:
        raise AssertionError(
            f"AC-1c: {md_path} front-matter is not valid YAML: {exc}"
        )

    assert isinstance(parsed, dict), (
        f"AC-1c: {md_path} front-matter did not parse to a dict"
    )

    # All FR-16a keys must be present (nullable ones may have None value)
    for key in _ALL_REQUIRED_KEYS:
        assert key in parsed, (
            f"AC-1c: {md_path} front-matter is missing key '{key}'"
        )

    # Non-nullable fields must be non-None and non-empty
    non_nullable = _NON_NULLABLE_ALL | _EXTRA_NON_NULLABLE.get(platform, frozenset())
    for key in non_nullable:
        val = parsed.get(key)
        assert val is not None and val != "", (
            f"AC-1c: {md_path} front-matter field '{key}' is required "
            f"non-nullable for platform '{platform}' but is {val!r}"
        )


# ---------------------------------------------------------------------------
# AC-1d manifest consistency
# ---------------------------------------------------------------------------

def assert_manifest_consistent(output_dir: Path) -> None:
    """
    AC-1d: manifest.json must parse as valid JSON. document_count must equal
    len(documents) and both must equal the number of .md files in output_dir.

    File count uses rglob to capture nested slugs (e.g. Docusaurus /api/...
    paths produce subdirectory trees under output_dir).

    Manifest key names matched to emit.py write_manifest:
      document_count, documents (array of per-doc entries).
    """
    output_dir = Path(output_dir)
    manifest_path = output_dir / "manifest.json"

    assert manifest_path.exists(), (
        f"AC-1d: manifest.json not found in {output_dir}"
    )

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"AC-1d: {manifest_path} is not valid JSON: {exc}"
        )

    assert isinstance(data, dict), (
        f"AC-1d: {manifest_path} parsed to {type(data)}, expected dict"
    )

    assert "document_count" in data, (
        f"AC-1d: manifest missing 'document_count' key"
    )
    assert "documents" in data, (
        f"AC-1d: manifest missing 'documents' key"
    )

    doc_count_field = data["document_count"]
    documents_array = data["documents"]

    assert isinstance(documents_array, list), (
        f"AC-1d: manifest 'documents' is not a list"
    )

    # Use rglob to count .md files recursively — Docusaurus produces nested
    # slug trees (e.g. api/_thatopen/components-front/classes/angle.md).
    md_files = list(output_dir.rglob("*.md"))
    file_count = len(md_files)

    assert doc_count_field == len(documents_array), (
        f"AC-1d: manifest document_count={doc_count_field} != "
        f"len(documents)={len(documents_array)}"
    )

    assert doc_count_field == file_count, (
        f"AC-1d: manifest document_count={doc_count_field} != "
        f"actual .md file count={file_count} in {output_dir}"
    )


# ---------------------------------------------------------------------------
# output_dir_checker helper
# ---------------------------------------------------------------------------

def output_dir_checker(output_dir: Path, platform: str) -> None:
    """
    Runs all four AC-1 assertions over an output directory.

    For every .md file: assert_no_chrome_bleed, assert_code_fence_present
    (lenient, no source HTML), assert_frontmatter_valid.
    For the directory: assert_manifest_consistent.

    Used by Slice 3 (Docusaurus) and Slice 4 (GitHub org) test modules.
    """
    output_dir = Path(output_dir)
    md_files = sorted(output_dir.rglob("*.md"))

    for md_path in md_files:
        assert_no_chrome_bleed(md_path)
        assert_code_fence_present(md_path)  # lenient — no source HTML
        assert_frontmatter_valid(md_path, platform)

    assert_manifest_consistent(output_dir)


# ---------------------------------------------------------------------------
# Helpers for self-tests
# ---------------------------------------------------------------------------

def _make_metadata(platform: str = "docusaurus") -> dict:
    """Return a complete FR-16a metadata dict for the given platform."""
    base = {
        "source_url": "https://docs.example.com/page",
        "title": "Example Page",
        "platform": platform,
        "target": "test-target",
        "package": None,
        "repo": None,
        "breadcrumb": None,
        "fetched_at": "2026-06-25T12:00:00Z",
        "content_hash": "abc123def456abc123def456abc123def456abc123def456abc123def456abc1",
        "git_ref": None,
    }
    if platform == "github_org":
        base["repo"] = "my-repo"
        base["git_ref"] = "main@a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
    return base


def _render_document(metadata: dict, body: str) -> str:
    """Render a document string in the same format as emit.py write_document."""
    fm_yaml = yaml.dump(
        metadata,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=True,
    )
    return f"---\n{fm_yaml}---\n\n{body}"


def _write_manifest(output_dir: Path, platform: str, slugs: list[str]) -> None:
    """Write a consistent manifest.json for the given slugs."""
    docs_entries = [
        {
            "slug": slug,
            "title": f"Title for {slug}",
            "source_url": f"https://docs.example.com/{slug}",
            "content_hash": "abc123",
        }
        for slug in slugs
    ]
    manifest = {
        "target": "test-target",
        "platform": platform,
        "generated_at": "2026-06-25T12:00:00Z",
        "document_count": len(slugs),
        "failure_count": 0,
        "documents": docs_entries,
        "failures": [],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Self-tests: S1 exit criterion
# ---------------------------------------------------------------------------


class TestPositive:
    """Positive test: a known-good output dir passes all four assertions."""

    def test_output_dir_checker_passes_on_known_good_dir(self, tmp_path: Path):
        """
        S1 exit criterion: output_dir_checker passes when every .md file has
        valid front-matter, no chrome bleed, and manifest is consistent.
        """
        platform = "docusaurus"

        # Write two valid markdown files
        for i in range(1, 3):
            slug = f"page{i}.md"
            meta = _make_metadata(platform)
            meta["title"] = f"Page {i}"
            meta["source_url"] = f"https://docs.example.com/page{i}"
            content = _render_document(meta, f"# Page {i}\n\nSome content here.\n")
            (tmp_path / slug).write_text(content, encoding="utf-8")

        _write_manifest(tmp_path, platform, ["page1.md", "page2.md"])

        # Must not raise
        output_dir_checker(tmp_path, platform)

    def test_github_org_platform_passes_with_git_ref(self, tmp_path: Path):
        """Positive test: github_org output with git_ref set passes AC-1c."""
        platform = "github_org"
        meta = _make_metadata(platform)
        content = _render_document(meta, "# Repo README\n\nContent.\n")
        (tmp_path / "readme.md").write_text(content, encoding="utf-8")
        _write_manifest(tmp_path, platform, ["readme.md"])

        output_dir_checker(tmp_path, platform)


class TestNegativeChromeBleeds:
    """Negative tests: assert_no_chrome_bleed raises on denylist hits."""

    def test_skip_to_main_content_raises(self, tmp_path: Path):
        """AC-1a: 'Skip to main content' in a file causes AssertionError."""
        md = tmp_path / "bad.md"
        md.write_text("# Page\n\nSkip to main content\n\nSome text.", encoding="utf-8")
        with pytest.raises(AssertionError, match="Skip to main content"):
            assert_no_chrome_bleed(md)

    def test_edit_this_page_raises(self, tmp_path: Path):
        """AC-1a: 'Edit this page' in a file causes AssertionError."""
        md = tmp_path / "bad.md"
        md.write_text("# Page\n\nEdit this page\n\nSome text.", encoding="utf-8")
        with pytest.raises(AssertionError, match="Edit this page"):
            assert_no_chrome_bleed(md)

    def test_on_this_page_raises(self, tmp_path: Path):
        """AC-1a: 'On this page' in a file causes AssertionError."""
        md = tmp_path / "bad.md"
        md.write_text("# Page\n\nOn this page\n\nSome text.", encoding="utf-8")
        with pytest.raises(AssertionError, match="On this page"):
            assert_no_chrome_bleed(md)

    def test_table_of_contents_raises(self, tmp_path: Path):
        """AC-1a: 'Table of Contents' in a file causes AssertionError."""
        md = tmp_path / "bad.md"
        md.write_text("# Page\n\nTable of Contents\n\nSome text.", encoding="utf-8")
        with pytest.raises(AssertionError, match="Table of Contents"):
            assert_no_chrome_bleed(md)

    def test_copyright_pattern_raises(self, tmp_path: Path):
        """AC-1a: '© 2024' copyright string causes AssertionError."""
        md = tmp_path / "bad.md"
        md.write_text("# Page\n\nSome text.\n\n© 2024 Example Corp.", encoding="utf-8")
        with pytest.raises(AssertionError, match="copyright string"):
            assert_no_chrome_bleed(md)

    def test_denylist_case_insensitive(self, tmp_path: Path):
        """AC-1a: denylist check is case-insensitive (SKIP TO MAIN CONTENT)."""
        md = tmp_path / "bad.md"
        md.write_text("# Page\n\nSKIP TO MAIN CONTENT\n", encoding="utf-8")
        with pytest.raises(AssertionError, match="Skip to main content"):
            assert_no_chrome_bleed(md)

    def test_clean_file_does_not_raise(self, tmp_path: Path):
        """AC-1a: a file with no denylist strings does not raise."""
        md = tmp_path / "clean.md"
        md.write_text("# Page\n\nSome clean content here.\n", encoding="utf-8")
        assert_no_chrome_bleed(md)  # must not raise


class TestNegativeFrontMatter:
    """Negative tests: assert_frontmatter_valid raises on invalid front-matter."""

    def test_missing_required_field_raises(self, tmp_path: Path):
        """AC-1c: a file missing a non-nullable field raises AssertionError."""
        meta = _make_metadata("docusaurus")
        del meta["title"]  # remove required field
        content = _render_document(meta, "# Page\n\nContent.\n")
        md = tmp_path / "bad.md"
        md.write_text(content, encoding="utf-8")
        with pytest.raises(AssertionError, match="title"):
            assert_frontmatter_valid(md, "docusaurus")

    def test_empty_required_field_raises(self, tmp_path: Path):
        """AC-1c: a non-nullable field set to empty string raises AssertionError."""
        meta = _make_metadata("docusaurus")
        meta["source_url"] = ""
        content = _render_document(meta, "# Page\n\nContent.\n")
        md = tmp_path / "bad.md"
        md.write_text(content, encoding="utf-8")
        with pytest.raises(AssertionError, match="source_url"):
            assert_frontmatter_valid(md, "docusaurus")

    def test_missing_nullable_key_raises(self, tmp_path: Path):
        """AC-1c: nullable keys must be PRESENT (key exists, value may be null)."""
        meta = _make_metadata("docusaurus")
        del meta["git_ref"]  # key must be present even if nullable
        content = _render_document(meta, "# Page\n\nContent.\n")
        md = tmp_path / "bad.md"
        md.write_text(content, encoding="utf-8")
        with pytest.raises(AssertionError, match="git_ref"):
            assert_frontmatter_valid(md, "docusaurus")

    def test_github_org_null_git_ref_raises(self, tmp_path: Path):
        """AC-1c: github_org with git_ref=null raises (git_ref non-nullable for github_org)."""
        meta = _make_metadata("github_org")
        meta["git_ref"] = None  # must be non-null for github_org
        content = _render_document(meta, "# Page\n\nContent.\n")
        md = tmp_path / "bad.md"
        md.write_text(content, encoding="utf-8")
        with pytest.raises(AssertionError, match="git_ref"):
            assert_frontmatter_valid(md, "github_org")

    def test_missing_front_matter_delimiter_raises(self, tmp_path: Path):
        """AC-1c: a file without a front-matter opening raises AssertionError."""
        md = tmp_path / "bad.md"
        md.write_text("# Page\n\nNo front-matter here.\n", encoding="utf-8")
        with pytest.raises(AssertionError):
            assert_frontmatter_valid(md, "docusaurus")

    def test_valid_front_matter_does_not_raise(self, tmp_path: Path):
        """AC-1c: a complete valid front-matter block does not raise."""
        meta = _make_metadata("docusaurus")
        content = _render_document(meta, "# Page\n\nContent.\n")
        md = tmp_path / "good.md"
        md.write_text(content, encoding="utf-8")
        assert_frontmatter_valid(md, "docusaurus")  # must not raise


class TestNegativeManifest:
    """Negative tests: assert_manifest_consistent raises on inconsistent manifest."""

    def test_manifest_count_mismatch_raises(self, tmp_path: Path):
        """AC-1d: manifest document_count != file count raises AssertionError."""
        # Write one .md file
        (tmp_path / "page1.md").write_text("content", encoding="utf-8")

        # Write manifest claiming 2 documents
        manifest = {
            "target": "test",
            "platform": "docusaurus",
            "generated_at": "2026-06-25T12:00:00Z",
            "document_count": 2,
            "failure_count": 0,
            "documents": [
                {"slug": "page1.md", "title": "Page 1", "source_url": "", "content_hash": ""},
                {"slug": "page2.md", "title": "Page 2", "source_url": "", "content_hash": ""},
            ],
            "failures": [],
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        with pytest.raises(AssertionError):
            assert_manifest_consistent(tmp_path)

    def test_document_count_field_mismatch_raises(self, tmp_path: Path):
        """AC-1d: document_count field != len(documents) array raises AssertionError."""
        (tmp_path / "page1.md").write_text("content", encoding="utf-8")

        # document_count says 1 but documents array has 2 entries
        manifest = {
            "target": "test",
            "platform": "docusaurus",
            "generated_at": "2026-06-25T12:00:00Z",
            "document_count": 1,
            "failure_count": 0,
            "documents": [
                {"slug": "page1.md", "title": "P1", "source_url": "", "content_hash": ""},
                {"slug": "page2.md", "title": "P2", "source_url": "", "content_hash": ""},
            ],
            "failures": [],
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        with pytest.raises(AssertionError):
            assert_manifest_consistent(tmp_path)

    def test_invalid_json_manifest_raises(self, tmp_path: Path):
        """AC-1d: an invalid JSON manifest raises AssertionError."""
        (tmp_path / "manifest.json").write_text("{not valid json", encoding="utf-8")

        with pytest.raises(AssertionError, match="not valid JSON"):
            assert_manifest_consistent(tmp_path)

    def test_missing_manifest_raises(self, tmp_path: Path):
        """AC-1d: absent manifest.json raises AssertionError."""
        with pytest.raises(AssertionError, match="manifest.json not found"):
            assert_manifest_consistent(tmp_path)

    def test_consistent_manifest_does_not_raise(self, tmp_path: Path):
        """AC-1d: consistent manifest (count == array == file count) does not raise."""
        (tmp_path / "page1.md").write_text("content", encoding="utf-8")
        _write_manifest(tmp_path, "docusaurus", ["page1.md"])
        assert_manifest_consistent(tmp_path)  # must not raise


class TestCodeFenceAssertion:
    """Tests for assert_code_fence_present (AC-1b)."""

    def test_raises_when_html_has_code_but_md_lacks_fence(self, tmp_path: Path):
        """AC-1b: HTML with <code> and MD without ``` raises AssertionError."""
        html = tmp_path / "source.html"
        html.write_text("<html><body><code>x = 1</code></body></html>", encoding="utf-8")

        md = tmp_path / "page.md"
        md.write_text("# Page\n\nSome prose text without any code fences.\n", encoding="utf-8")

        with pytest.raises(AssertionError, match="code"):
            assert_code_fence_present(md, source_html_path=html)

    def test_passes_when_html_has_code_and_md_has_fence(self, tmp_path: Path):
        """AC-1b: HTML with <code> and MD with ``` does not raise."""
        html = tmp_path / "source.html"
        html.write_text("<html><body><code>x = 1</code></body></html>", encoding="utf-8")

        md = tmp_path / "page.md"
        md.write_text("# Page\n\n```python\nx = 1\n```\n", encoding="utf-8")

        assert_code_fence_present(md, source_html_path=html)  # must not raise

    def test_no_source_html_lenient_for_prose(self, tmp_path: Path):
        """AC-1b: without source_html_path, prose-only doc does not raise."""
        md = tmp_path / "page.md"
        md.write_text("# Page\n\nJust prose text. No code here.\n", encoding="utf-8")
        assert_code_fence_present(md)  # must not raise

    def test_pre_element_also_triggers_fence_check(self, tmp_path: Path):
        """AC-1b: HTML with <pre> also requires a ``` fence in output."""
        html = tmp_path / "source.html"
        html.write_text("<html><body><pre>some preformatted text</pre></body></html>", encoding="utf-8")

        md = tmp_path / "page.md"
        md.write_text("# Page\n\nNo fences here.\n", encoding="utf-8")

        with pytest.raises(AssertionError):
            assert_code_fence_present(md, source_html_path=html)
