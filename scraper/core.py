"""
Core engine functions for the documentation scraper.

get_main, extract_sections, and render_sections are the VERBATIM-PROTECTED TRIO
(FR-4a, DDR-01 D2). They are copied character-for-character from
seed/scrape_askedgar_reference.py. Do not modify them for any reason; any needed
behavior change requires a new DDR.

discover_slugs is parameterized (FR-4b) — the seed's hardcoded values become defaults.
"""

from bs4 import BeautifulSoup


# VERBATIM — do not modify (FR-4a, DDR-01 D2)
def get_main(soup: BeautifulSoup):
    """Return the primary content container, stripping nav/aside noise."""
    container = (
        soup.find("article")
        or soup.find("div", attrs={"role": "main"})
        or soup.find("main")
        or soup.body
    )
    if container:
        for noise in container.find_all(["nav", "aside", "footer", "script", "style"]):
            noise.decompose()
    return container


# VERBATIM — do not modify (FR-4a, DDR-01 D2)
def extract_sections(container) -> dict[str, list[str]]:
    """
    Walk the container and bucket text lines into named sections.
    Section boundaries are h1–h4 headings. Returns:
        {"_title": [...], "query params": [...], "response": [...], ...}
    """
    sections: dict[str, list[str]] = {"_title": []}
    current = "_title"

    for elem in container.find_all(True):
        tag = elem.name
        if tag in ("script", "style", "noscript"):
            continue

        if tag in ("h1", "h2", "h3", "h4"):
            heading = elem.get_text(" ", strip=True)
            if heading:
                key = heading.lower().strip()
                sections.setdefault(key, [])
                current = key
            continue

        # Leaf-ish elements: extract text and assign to current section
        if tag in ("p", "li", "td", "th", "dt", "dd", "span", "code", "pre"):
            # skip if a parent of the same meaningful tags already captured this
            if elem.find(["p", "li", "td", "th", "dt", "dd"]):
                continue
            text = elem.get_text(" ", strip=True)
            if text and len(text) > 1:
                sections[current].append(text)

    return sections


# VERBATIM — do not modify (FR-4a, DDR-01 D2)
def render_sections(sections: dict[str, list[str]], label: str, slug: str, url: str) -> str:
    lines: list[str] = [f"## {label}", "", f"**Slug:** `{slug}`", f"**URL:** {url}", ""]

    # Title section — first meaningful lines (description text)
    title_lines = [t for t in sections.get("_title", []) if len(t) > 10]
    if title_lines:
        lines.append("### Overview")
        lines.extend(title_lines[:6])  # cap at 6 lines to avoid sidebar bleed
        lines.append("")

    # Params sections — any section whose key contains "param"
    for key, body in sections.items():
        if "param" in key and body:
            lines.append(f"### {key.title()}")
            lines.extend(body)
            lines.append("")

    # Response / responses section
    for key, body in sections.items():
        if key.startswith("response") and body:
            lines.append(f"### {key.title()}")
            lines.extend(body)
            lines.append("")

    # Everything else that isn't noise
    noise_keys = {"_title", "on this page", "table of contents", "contents"}
    for key, body in sections.items():
        if key in noise_keys or "param" in key or key.startswith("response"):
            continue
        if body:
            lines.append(f"### {key.title()}")
            lines.extend(body)
            lines.append("")

    return "\n".join(lines)


def discover_slugs(
    html: str,
    link_pattern: str = "/reference/",
    slug_methods: list[str] | None = None,
    slug_filter: str | None = None,
) -> list[tuple[str, str]]:
    """
    Parse a rendered sidebar page and return [(label, slug), ...].

    Default slug_methods = ["get", "post", "put", "delete", "patch"] (seed values).
    The seed's hardcoded "/reference/" and method-suffix check become defaults (FR-4b).

    Args:
        html: Fully-rendered HTML of the seed/discovery page.
        link_pattern: URL-path substring filter (default: "/reference/").
        slug_methods: HTTP method suffixes to filter on. Default: all 5 REST methods.
        slug_filter: Optional extra substring that must be present in the slug.
    """
    if slug_methods is None:
        slug_methods = ["get", "post", "put", "delete", "patch"]

    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    results: list[tuple[str, str]] = []

    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        if link_pattern not in href:
            continue
        slug = href.split(link_pattern)[-1].split("#")[0].split("?")[0].strip("/")
        if not slug or slug in seen:
            continue
        # Filter by method suffix
        if not any(slug.endswith(f"_{m}") for m in slug_methods):
            continue
        # Optional additional filter
        if slug_filter is not None and slug_filter not in slug:
            continue
        seen.add(slug)
        label = a.get_text(" ", strip=True) or slug
        results.append((label, slug))

    return results
