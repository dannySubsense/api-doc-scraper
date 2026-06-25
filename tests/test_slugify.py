"""
Unit tests for scraper/slugify.py.

Acceptance criteria covered (FR-15a, FR-15b, ARCHITECTURE §Filename derivation):
- Basic sanitization (lowercase, illegal char replacement, underscore collapse)
- @scope segment handling (e.g. /api/@thatopen/components-front/classes/Angle)
- Case-collision detection and resolution (/Foo vs /foo)
- Reserved-name suffixing (con, prn, aux, nul, com*, lpt*)
- 80-byte length cap with hash suffix
- Total-path-length guard (200 bytes)
- All three platform split strategies (readme_io, docusaurus, github_org)
- .mdx -> .md extension replacement
- resolve_collisions is deterministic and injective
"""

import hashlib

import pytest

from scraper.slugify import identifier_to_slug, resolve_collisions


# ---------------------------------------------------------------------------
# Basic sanitization
# ---------------------------------------------------------------------------

class TestBasicSanitization:
    def test_lowercase_conversion(self):
        """Step 2.1: uppercase letters are lowercased."""
        slug = identifier_to_slug("MyDocument", "readme_io")
        assert slug == "mydocument.md"

    def test_illegal_chars_replaced_with_underscore(self):
        """Step 2.3: characters outside [a-z0-9._-] become _."""
        slug = identifier_to_slug("hello world", "readme_io")
        # space -> _
        assert slug == "hello_world.md"

    def test_consecutive_underscores_collapsed(self):
        """Step 2.4: runs of underscores are collapsed to one."""
        slug = identifier_to_slug("hello   world", "readme_io")
        # three spaces -> three underscores -> one underscore
        assert slug == "hello_world.md"

    def test_leading_dots_stripped(self):
        """Step 2.2: leading dots removed from segment."""
        slug = identifier_to_slug(".hidden", "readme_io")
        assert slug == "hidden.md"

    def test_existing_md_extension_preserved(self):
        """Step 3: segment already ending in .md stays .md (not double-extended)."""
        slug = identifier_to_slug("readme.md", "readme_io")
        assert slug == "readme.md"

    def test_md_appended_when_absent(self):
        """Step 3: .md is appended when not already present."""
        slug = identifier_to_slug("somepage", "readme_io")
        assert slug.endswith(".md")


# ---------------------------------------------------------------------------
# @scope segment
# ---------------------------------------------------------------------------

class TestAtScopeSegment:
    def test_at_sign_replaced_with_underscore(self):
        """@ is not in [a-z0-9._-]; becomes _."""
        slug = identifier_to_slug(
            "/api/@thatopen/components-front/classes/Angle", "docusaurus"
        )
        assert "_thatopen" in slug

    def test_full_scope_path_example_from_architecture(self):
        """ARCHITECTURE full example: /api/@thatopen/components-front/classes/Angle."""
        slug = identifier_to_slug(
            "/api/@thatopen/components-front/classes/Angle", "docusaurus"
        )
        assert slug == "api/_thatopen/components-front/classes/angle.md"

    def test_scope_path_lowercased(self):
        """Segment 'Angle' is lowercased to 'angle'."""
        slug = identifier_to_slug(
            "/api/@thatopen/components-front/classes/Angle", "docusaurus"
        )
        assert slug.endswith("angle.md")


# ---------------------------------------------------------------------------
# Case-collision detection and resolution
# ---------------------------------------------------------------------------

class TestCaseCollision:
    def test_foo_and_foo_produce_same_candidate(self):
        """/Foo and /foo both produce foo.md before collision resolution."""
        s1 = identifier_to_slug("/Foo", "docusaurus")
        s2 = identifier_to_slug("/foo", "docusaurus")
        assert s1 == s2

    def test_collision_first_retains_original(self):
        """Discovery-order first keeps the slug; second gets hash suffix."""
        pairs = [
            ("/Foo", "foo.md"),
            ("/foo", "foo.md"),
        ]
        result = resolve_collisions(pairs)
        assert result["/Foo"] == "foo.md"

    def test_collision_second_gets_hash_suffix(self):
        """Second collider has 8-hex SHA-256 suffix derived from its identifier."""
        pairs = [
            ("/Foo", "foo.md"),
            ("/foo", "foo.md"),
        ]
        result = resolve_collisions(pairs)
        hash8 = hashlib.sha256("/foo".encode()).hexdigest()[:8]
        assert result["/foo"] == f"foo_{hash8}.md"

    def test_collision_nested_path(self):
        """Collision in nested path: only the filename part gets the suffix."""
        pairs = [
            ("/Foo/Bar", "foo/bar.md"),
            ("/foo/bar", "foo/bar.md"),
        ]
        result = resolve_collisions(pairs)
        hash8 = hashlib.sha256("/foo/bar".encode()).hexdigest()[:8]
        assert result["/foo/bar"] == f"foo/bar_{hash8}.md"
        assert result["/Foo/Bar"] == "foo/bar.md"

    def test_no_collision_unchanged(self):
        """Identifiers with distinct slugs are returned unchanged."""
        pairs = [
            ("alpha", "alpha.md"),
            ("beta", "beta.md"),
        ]
        result = resolve_collisions(pairs)
        assert result == {"alpha": "alpha.md", "beta": "beta.md"}


# ---------------------------------------------------------------------------
# Reserved-name suffixing
# ---------------------------------------------------------------------------

class TestReservedNames:
    @pytest.mark.parametrize("name", ["con", "prn", "aux", "nul"])
    def test_basic_reserved_names_suffixed(self, name):
        """Windows reserved base names get _x suffix."""
        slug = identifier_to_slug(name, "readme_io")
        assert slug == f"{name}_x.md"

    @pytest.mark.parametrize("n", range(10))
    def test_com_series_suffixed(self, n):
        """com0-com9 are reserved; each gets _x suffix."""
        name = f"com{n}"
        slug = identifier_to_slug(name, "readme_io")
        assert slug == f"{name}_x.md"

    @pytest.mark.parametrize("n", range(10))
    def test_lpt_series_suffixed(self, n):
        """lpt0-lpt9 are reserved; each gets _x suffix."""
        name = f"lpt{n}"
        slug = identifier_to_slug(name, "readme_io")
        assert slug == f"{name}_x.md"

    def test_reserved_name_uppercase_also_caught(self):
        """CON uppercase is lowercased first; then caught as reserved."""
        slug = identifier_to_slug("CON", "readme_io")
        assert slug == "con_x.md"

    def test_non_reserved_name_unchanged(self):
        """A segment like 'console' is not reserved and has no _x suffix."""
        slug = identifier_to_slug("console", "readme_io")
        assert slug == "console.md"


# ---------------------------------------------------------------------------
# 80-byte segment length cap with hash suffix
# ---------------------------------------------------------------------------

class TestSegmentLengthCap:
    def test_long_segment_truncated_with_hash(self):
        """A segment exceeding 80 bytes is trimmed to <=80 bytes with _<7hex> suffix."""
        # 100-char lowercase-safe identifier
        long_id = "a" * 100
        slug = identifier_to_slug(long_id, "readme_io")
        stem = slug[:-3]  # strip .md
        # Must end with _<7hex>
        parts = stem.rsplit("_", 1)
        assert len(parts) == 2
        assert len(parts[1]) == 7
        # Full stem must be at most 80 bytes
        assert len(stem.encode("utf-8")) <= 80

    def test_short_segment_not_modified(self):
        """Segments within 80 bytes are not truncated."""
        slug = identifier_to_slug("short_name", "readme_io")
        assert slug == "short_name.md"

    def test_segment_hash_derived_from_original(self):
        """The 7-hex suffix is SHA-256 of the original pre-sanitize segment."""
        long_id = "A" * 100  # original segment before lower() etc.
        # For readme_io, identifier == segment
        slug = identifier_to_slug(long_id, "readme_io")
        stem = slug[:-3]
        _, hash_part = stem.rsplit("_", 1)
        expected_hash = hashlib.sha256(long_id.encode("utf-8")).hexdigest()[:7]
        assert hash_part == expected_hash


# ---------------------------------------------------------------------------
# Total path-length guard (200 bytes)
# ---------------------------------------------------------------------------

class TestTotalPathLengthGuard:
    def test_long_path_truncated_to_200_bytes(self):
        """A constructed path exceeding 200 bytes is truncated to <=200 bytes."""
        # Construct a deeply nested docusaurus URL that would exceed 200 bytes
        segment = "a" * 40
        long_url = "/" + "/".join([segment] * 6)  # 6 * 41 chars deep
        slug = identifier_to_slug(long_url, "docusaurus")
        assert len(slug.encode("utf-8")) <= 200

    def test_short_path_not_affected_by_guard(self):
        """Normal-length paths are not modified by the total path guard."""
        slug = identifier_to_slug("short/path", "docusaurus")
        assert slug == "short/path.md"


# ---------------------------------------------------------------------------
# Platform split strategies
# ---------------------------------------------------------------------------

class TestPlatformSplitStrategies:
    def test_readme_io_single_segment(self):
        """readme_io: identifier treated as a single segment (no splitting)."""
        slug = identifier_to_slug(
            "dilution_rating_v1_dilution_rating_get", "readme_io"
        )
        assert slug == "dilution_rating_v1_dilution_rating_get.md"

    def test_docusaurus_splits_on_slash(self):
        """docusaurus: URL path split on / produces hierarchical path."""
        slug = identifier_to_slug("/docs/getting-started", "docusaurus")
        assert slug == "docs/getting-started.md"

    def test_docusaurus_strips_scheme_and_host(self):
        """docusaurus: full URL with scheme+host is stripped before splitting."""
        slug = identifier_to_slug(
            "https://docs.example.com/docs/intro", "docusaurus"
        )
        assert slug == "docs/intro.md"

    def test_docusaurus_strips_query_and_fragment(self):
        """docusaurus: query string and fragment are stripped."""
        slug = identifier_to_slug("/docs/page?tab=1#section", "docusaurus")
        assert slug == "docs/page.md"

    def test_github_org_splits_on_colon_then_slash(self):
        """github_org: 'repo:path' splits to repo / path segments."""
        slug = identifier_to_slug("engine:docs/README.md", "github_org")
        assert slug == "engine/docs/readme.md"

    def test_github_org_single_level_path(self):
        """github_org: 'repo:file.md' at repo root."""
        slug = identifier_to_slug("myrepo:README.md", "github_org")
        assert slug == "myrepo/readme.md"


# ---------------------------------------------------------------------------
# .mdx -> .md extension replacement
# ---------------------------------------------------------------------------

class TestMdxExtension:
    def test_mdx_replaced_with_md(self):
        """.mdx extension on the final segment is replaced with .md."""
        slug = identifier_to_slug("engine:docs/guide.mdx", "github_org")
        assert slug.endswith(".md")
        assert not slug.endswith(".mdx")
        assert slug == "engine/docs/guide.md"

    def test_mdx_docusaurus(self):
        """.mdx in a docusaurus path is replaced with .md."""
        slug = identifier_to_slug("/docs/guide.mdx", "docusaurus")
        assert slug == "docs/guide.md"


# ---------------------------------------------------------------------------
# resolve_collisions: determinism and injectivity
# ---------------------------------------------------------------------------

class TestResolveCollisionsDeterminismAndInjectivity:
    def test_deterministic_same_input_same_output(self):
        """Same input list always produces the same result (FR-15a)."""
        pairs = [
            ("id_a", "foo/bar.md"),
            ("id_b", "foo/bar.md"),
            ("id_c", "baz.md"),
        ]
        result1 = resolve_collisions(pairs)
        result2 = resolve_collisions(pairs)
        assert result1 == result2

    def test_injective_no_two_identifiers_map_to_same_slug(self):
        """Two distinct identifiers never map to the same final slug (FR-15b)."""
        # Build a set with intentional collision
        pairs = [
            ("id_a", "foo.md"),
            ("id_b", "foo.md"),
            ("id_c", "bar.md"),
            ("id_d", "bar.md"),
        ]
        result = resolve_collisions(pairs)
        values = list(result.values())
        # All final slugs must be distinct
        assert len(values) == len(set(values))

    def test_hash_suffix_derived_from_identifier_not_slug(self):
        """
        The 8-hex suffix appended to a colliding slug is SHA-256 of the
        colliding identifier, not of the candidate slug.
        """
        pairs = [
            ("first_id", "same.md"),
            ("second_id", "same.md"),
        ]
        result = resolve_collisions(pairs)
        hash8 = hashlib.sha256("second_id".encode()).hexdigest()[:8]
        assert result["second_id"] == f"same_{hash8}.md"

    def test_triple_collision_all_distinct(self):
        """Three identifiers sharing a slug all receive distinct final slugs."""
        pairs = [
            ("id1", "dup.md"),
            ("id2", "dup.md"),
            ("id3", "dup.md"),
        ]
        result = resolve_collisions(pairs)
        values = list(result.values())
        assert len(values) == len(set(values))
        # First retains original
        assert result["id1"] == "dup.md"

    def test_architecture_example_foo_bar(self):
        """
        ARCHITECTURE worked example: /Foo/Bar and /foo/bar both sanitize to
        foo/bar.md; first retains it, second gets hash suffix.
        """
        pairs = [
            ("/Foo/Bar", "foo/bar.md"),
            ("/foo/bar", "foo/bar.md"),
        ]
        result = resolve_collisions(pairs)
        hash8 = hashlib.sha256("/foo/bar".encode()).hexdigest()[:8]
        assert result["/Foo/Bar"] == "foo/bar.md"
        assert result["/foo/bar"] == f"foo/bar_{hash8}.md"
