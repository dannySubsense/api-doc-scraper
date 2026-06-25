"""
Unit tests for scraper/htmlmd.py.

Acceptance criteria covered (Slice 3, 01-REQUIREMENTS.md, 04-ROADMAP.md lines 418-431):
- _strip_noise: removes nav/aside/footer/script/style elements
- _strip_noise: removes denylist text elements (chrome-bleed strings)
- _strip_noise: keeps clean content elements intact
- _strip_noise REGRESSION: strips Docusaurus hash-link anchors (class="hash-link");
  heading text is preserved; "Direct link to" never appears in output
- _code_language: extracts language token from language-typescript class on child <code>
- _code_language: extracts language token from language-python class on child <code>
- _code_language: returns "" when no language class is present
- to_markdown: <pre><code class="language-typescript"> produces ```typescript fence (AC-1b)
- to_markdown: "Skip to main content" element is omitted from output (AC-1a)
- to_markdown: <table> is converted to GFM table
- to_markdown: h1/h2/h3 produce ATX #/##/### headings
"""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from scraper.htmlmd import _strip_noise, _code_language, to_markdown


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _soup(html: str) -> BeautifulSoup:
    """Parse HTML and return the top-level BeautifulSoup container."""
    return BeautifulSoup(html, "html.parser")


def _div(html: str) -> BeautifulSoup:
    """Wrap HTML in a <div> and return the <div> element — simulates a content container."""
    return _soup(f"<div>{html}</div>").find("div")


# ---------------------------------------------------------------------------
# _strip_noise: structural tag removal
# ---------------------------------------------------------------------------

class TestStripNoiseStructuralTags:
    def test_removes_nav_elements(self):
        """_strip_noise removes all <nav> elements."""
        container = _div("<nav>Navigation menu</nav><p>Real content</p>")
        _strip_noise(container)
        assert container.find("nav") is None
        assert "Navigation menu" not in container.get_text()

    def test_removes_aside_elements(self):
        """_strip_noise removes all <aside> elements."""
        container = _div("<aside>Sidebar</aside><p>Main text</p>")
        _strip_noise(container)
        assert container.find("aside") is None
        assert "Sidebar" not in container.get_text()

    def test_removes_footer_elements(self):
        """_strip_noise removes all <footer> elements."""
        container = _div("<footer>Footer content</footer><p>Body</p>")
        _strip_noise(container)
        assert container.find("footer") is None
        assert "Footer content" not in container.get_text()

    def test_removes_script_elements(self):
        """_strip_noise removes all <script> elements."""
        container = _div('<script>var x = 1;</script><p>Content</p>')
        _strip_noise(container)
        assert container.find("script") is None

    def test_removes_style_elements(self):
        """_strip_noise removes all <style> elements."""
        container = _div("<style>.foo { color: red; }</style><p>Content</p>")
        _strip_noise(container)
        assert container.find("style") is None

    def test_keeps_clean_content_paragraph(self):
        """_strip_noise does not remove clean <p> content elements."""
        container = _div("<p>This is legitimate documentation content.</p>")
        _strip_noise(container)
        assert "This is legitimate documentation content." in container.get_text()

    def test_keeps_clean_heading(self):
        """_strip_noise does not remove clean heading elements."""
        container = _div("<h2>Getting Started</h2><p>Follow these steps.</p>")
        _strip_noise(container)
        assert "Getting Started" in container.get_text()
        assert "Follow these steps." in container.get_text()


# ---------------------------------------------------------------------------
# _strip_noise: denylist text element removal
# ---------------------------------------------------------------------------

class TestStripNoiseDenylist:
    @pytest.mark.parametrize("text", [
        "Edit this page",
        "Table of Contents",
        "Skip to main content",
        "On this page",
    ])
    def test_removes_exact_denylist_string(self, text: str):
        """_strip_noise removes elements whose stripped text exactly matches a denylist string."""
        container = _div(f"<span>{text}</span><p>Real content</p>")
        _strip_noise(container)
        assert text not in container.get_text()

    def test_denylist_removal_keeps_adjacent_content(self):
        """_strip_noise removes only the denylist element, not surrounding content."""
        container = _div(
            "<p>Introduction paragraph.</p>"
            "<span>Skip to main content</span>"
            "<p>More content follows.</p>"
        )
        _strip_noise(container)
        assert "Introduction paragraph." in container.get_text()
        assert "More content follows." in container.get_text()
        assert "Skip to main content" not in container.get_text()

    def test_removes_copyright_element(self):
        """_strip_noise removes leaf elements matching the copyright pattern © YYYY."""
        container = _div("<span>© 2024 Example Corp.</span><p>Documentation</p>")
        _strip_noise(container)
        assert "© 2024" not in container.get_text()
        assert "Documentation" in container.get_text()


# ---------------------------------------------------------------------------
# _strip_noise REGRESSION: Docusaurus hash-link anchor stripping
# ---------------------------------------------------------------------------

class TestStripNoiseHashLinkRegression:
    def test_hash_link_removed_from_heading(self):
        """
        REGRESSION: <a class="hash-link" title="Direct link to Foo">​</a>
        inside <h2> must be removed by _strip_noise.
        """
        container = _div(
            '<h2>Foo<a class="hash-link" href="#foo" '
            'title="Direct link to Foo">​</a></h2>'
        )
        _strip_noise(container)
        assert container.find("a", class_="hash-link") is None

    def test_output_does_not_contain_direct_link_to(self):
        """
        REGRESSION: after _strip_noise, 'Direct link to' must not appear
        anywhere in the container text.
        """
        container = _div(
            '<h2>My Section<a class="hash-link" href="#my-section" '
            'title="Direct link to My Section">​</a></h2>'
        )
        _strip_noise(container)
        assert "Direct link to" not in container.get_text()

    def test_heading_text_preserved_after_hash_link_strip(self):
        """
        REGRESSION: the heading text ('My Section') must survive after the
        hash-link anchor is removed.
        """
        container = _div(
            '<h2>My Section<a class="hash-link" href="#my-section" '
            'title="Direct link to My Section">​</a></h2>'
        )
        _strip_noise(container)
        assert "My Section" in container.get_text()

    def test_secondary_guard_title_attribute_also_stripped(self):
        """
        REGRESSION secondary guard: an <a> with title="Direct link to …" but
        no class="hash-link" is also removed.
        """
        container = _div(
            '<h3>Other Heading<a href="#other" '
            'title="Direct link to Other Heading">​</a></h3>'
        )
        _strip_noise(container)
        assert "Direct link to" not in container.get_text()
        assert "Other Heading" in container.get_text()


# ---------------------------------------------------------------------------
# _code_language
# ---------------------------------------------------------------------------

class TestCodeLanguage:
    def test_returns_typescript_from_code_child(self):
        """_code_language returns 'typescript' when <code class="language-typescript"> is child of <pre>."""
        pre = _soup('<pre><code class="language-typescript">const x = 1;</code></pre>').find("pre")
        assert _code_language(pre) == "typescript"

    def test_returns_python_from_code_child(self):
        """_code_language returns 'python' when <code class="language-python"> is child of <pre>."""
        pre = _soup('<pre><code class="language-python">print("hello")</code></pre>').find("pre")
        assert _code_language(pre) == "python"

    def test_returns_empty_string_when_no_language_class(self):
        """_code_language returns '' when neither <pre> nor <code> has a language-* class."""
        pre = _soup("<pre><code>plain code block</code></pre>").find("pre")
        assert _code_language(pre) == ""

    def test_returns_empty_string_when_no_code_child(self):
        """_code_language returns '' for a bare <pre> with no <code> child."""
        pre = _soup("<pre>raw preformatted text</pre>").find("pre")
        assert _code_language(pre) == ""

    def test_language_class_on_pre_itself_also_works(self):
        """_code_language checks the <pre> element's own classes too (defensive)."""
        pre = _soup('<pre class="language-typescript"><code>const x=1;</code></pre>').find("pre")
        assert _code_language(pre) == "typescript"


# ---------------------------------------------------------------------------
# to_markdown: acceptance criteria preconditions
# ---------------------------------------------------------------------------

class TestToMarkdown:
    def test_ac1b_typescript_fence_produced(self):
        """
        AC-1b precondition: HTML with <pre><code class="language-typescript">
        produces a ```typescript fenced code block.
        """
        container = _div('<pre><code class="language-typescript">const x = 1;</code></pre>')
        result = to_markdown(container)
        assert "```typescript" in result
        assert "const x = 1;" in result

    def test_ac1a_skip_to_main_content_omitted(self):
        """
        AC-1a precondition: HTML with a 'Skip to main content' element
        produces output that does not contain that string.
        """
        container = _div(
            "<span>Skip to main content</span>"
            "<h1>Page Title</h1>"
            "<p>Page body content.</p>"
        )
        result = to_markdown(container)
        assert "Skip to main content" not in result
        assert "Page Title" in result

    def test_table_converted_to_gfm(self):
        """
        to_markdown converts an HTML <table> to a GFM markdown table
        (pipe-delimited rows with a separator row).
        """
        container = _div(
            "<table>"
            "<thead><tr><th>Name</th><th>Value</th></tr></thead>"
            "<tbody>"
            "<tr><td>foo</td><td>bar</td></tr>"
            "<tr><td>baz</td><td>qux</td></tr>"
            "</tbody>"
            "</table>"
        )
        result = to_markdown(container)
        # GFM table: at least three pipe characters per row
        assert "| Name |" in result or "|Name|" in result
        assert "foo" in result
        assert "bar" in result

    def test_h1_produces_atx_heading(self):
        """to_markdown converts <h1> to ATX # heading."""
        container = _div("<h1>Top Level</h1><p>Content.</p>")
        result = to_markdown(container)
        assert "# Top Level" in result

    def test_h2_produces_atx_heading(self):
        """to_markdown converts <h2> to ATX ## heading."""
        container = _div("<h2>Second Level</h2><p>Content.</p>")
        result = to_markdown(container)
        assert "## Second Level" in result

    def test_h3_produces_atx_heading(self):
        """to_markdown converts <h3> to ATX ### heading."""
        container = _div("<h3>Third Level</h3><p>Content.</p>")
        result = to_markdown(container)
        assert "### Third Level" in result

    def test_ac1a_edit_this_page_omitted(self):
        """
        AC-1a precondition: HTML with 'Edit this page' element produces
        output that does not contain that string.
        """
        container = _div(
            "<p>Real documentation.</p>"
            "<a>Edit this page</a>"
        )
        result = to_markdown(container)
        assert "Edit this page" not in result
        assert "Real documentation." in result

    def test_to_markdown_returns_string(self):
        """to_markdown always returns a str (not bytes or None)."""
        container = _div("<p>Simple content.</p>")
        result = to_markdown(container)
        assert isinstance(result, str)
