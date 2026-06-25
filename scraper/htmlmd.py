"""
HTML-to-markdown converter for Docusaurus page containers.

_strip_noise(container): removes nav/aside/footer/script/style and known
    chrome-bleed text nodes in-place. Must be called before markdownify.
_code_language(el): extracts language-<token> from a <pre> element and its
    child <code>. Corrected per S2 spike result (language class is on <code>).
to_markdown(container): strips noise then converts with markdownify using
    ATX headings and code_language_callback.
"""

from __future__ import annotations

import re

from markdownify import markdownify


# Text strings that exactly identify chrome-bleed elements to remove.
_NOISE_EXACT_STRINGS = frozenset([
    "Edit this page",
    "Table of Contents",
    "Skip to main content",
    "On this page",
])

# Regex for copyright elements like "© 2024"
_COPYRIGHT_RE = re.compile(r"©\s*\d{4}")

# Tags to unconditionally remove from the container
_NOISE_TAGS = {"nav", "aside", "footer", "script", "style"}


def _strip_noise(container) -> None:
    """
    Remove noise elements from a BeautifulSoup container in-place.

    Removes:
    - All nav, aside, footer, script, style elements.
    - Any element whose stripped text exactly matches a chrome-bleed string.
    - Any element matching the copyright pattern © YYYY.
    - Docusaurus heading-anchor links (class="hash-link") — the invisible
      zero-width-space anchors Docusaurus injects into every heading, e.g.:
      <a class="hash-link" href="#..." title="Direct link to ...">​</a>
      These must be stripped BEFORE markdownify so they never appear in output.
    """
    # Remove by tag name first (catches most nav/footer/aside chrome)
    for tag in _NOISE_TAGS:
        for el in container.find_all(tag):
            el.decompose()

    # Remove Docusaurus heading-anchor links before markdownify converts them
    # to markdown link noise like [​](/path "Direct link to …").
    # Primary selector: class="hash-link" (always present on these anchors).
    # Secondary guard: title/aria-label starting with "Direct link to" catches
    # any future Docusaurus variant that drops the class.
    for el in container.find_all("a", class_="hash-link"):
        el.decompose()
    for el in container.find_all(
        "a",
        attrs={"title": lambda v: v and v.startswith("Direct link to")},
    ):
        el.decompose()

    # Remove elements matching exact text strings or copyright pattern.
    # Walk a copy of the tag list because decompose modifies the tree.
    for el in container.find_all(True):
        text = el.get_text(strip=True)
        if text in _NOISE_EXACT_STRINGS:
            el.decompose()
            continue
        if _COPYRIGHT_RE.search(text):
            # Only decompose leaf-like elements (short text) to avoid
            # nuking a large container that merely contains a copyright notice.
            # If the element has no child tags, it is a direct text carrier.
            if not el.find(True):
                el.decompose()


def _code_language(el) -> str:
    """
    Return the language token for a <pre> element, or '' if none.

    el is always the <pre>; the language class lives on the child <code>
    (Prism.js convention: class="language-<token>"). The corrected version
    per S2 spike — the spec's draft only checked el.get("class") which is
    always None on the <pre> itself.
    """
    classes = list(el.get("class") or [])
    code_child = el.find("code")
    if code_child:
        classes += list(code_child.get("class") or [])
    for cls in classes:
        m = re.match(r"^language-(.+)$", cls)
        if m:
            return m.group(1)
    return ""


def to_markdown(container) -> str:
    """
    Convert a BeautifulSoup container to clean markdown.

    Steps:
    1. Strip noise elements in-place (_strip_noise).
    2. Convert with markdownify: ATX headings, language-tagged code fences,
       script/style stripped again as a safety net.
    """
    _strip_noise(container)
    return markdownify(
        str(container),
        heading_style="ATX",
        code_language_callback=_code_language,
        strip=["script", "style"],
    )
