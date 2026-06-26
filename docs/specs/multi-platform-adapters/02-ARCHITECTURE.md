# ARCHITECTURE — Multi-platform adapter architecture

| Field | Value |
|---|---|
| Author | scraper (fabric) |
| Date | 2026-06-25 |
| Governing DDR | DDR-02 (LORE `acd22c0f-7b80-440f-8b83-d3e19f5e2b72`) |
| Supersedes | ARCHITECTURE.md (draft — pre-QC) |
| Status | REVISED — QC findings C2, C3, S2, S3 resolved; G-1 (github_org single-item path) fixed |

---

## Package layout

```
scraper/
  __init__.py
  config.py          # TargetConfig dataclass + load_target(name); validates platform
  core.py            # VERBATIM-protected trio: get_main / extract_sections /
                     #   render_sections. Plus parameterized discover_slugs.
                     #   Caller of the trio: readme_io adapter only. PROTECTED.
  htmlmd.py          # structure-preserving HTML-container -> markdown (markdownify-based)
  slugify.py         # collision-safe path derivation (Document.slug -> relative path)
  emit.py            # Document dataclass; write_document / write_manifest (atomic);
                     #   single-file mode (AskEdgar regression parity)
  runner.py          # config load -> adapter resolve -> discover() -> render() each ->
                     #   emit; owns flags, politeness, browser lifecycle
  cli.py             # argparse: --target, --discover, --slug, --no-discover, --limit
  adapters/
    __init__.py      # ADAPTERS registry {platform_name: class}
    base.py          # PlatformAdapter ABC + Item / Document / RunContext dataclasses
    readme_io.py     # wraps core.py (Playwright); single-file output (seed parity)
    docusaurus.py    # sitemap discovery + path filters; urllib fetch; htmlmd extraction
    github_org.py    # GitHub API enumeration; per-repo default branch; markdown passthrough
targets/
  askedgar.yaml          # platform: readme_io
  thatopen-docs.yaml     # platform: docusaurus
  thatopen-github.yaml   # platform: github_org
tests/
  fixtures/
    askedgar/
      slugs.json         # golden: list of slug strings (set-equality baseline)
      headings.json      # golden: {slug: [heading_string, ...]} per slug
  test_g1_regression.py  # offline G1 gate: compares adapter output against fixtures
output/                  # gitignored; output/<target>/*.md + manifest.json
pyproject.toml           # deps: playwright, beautifulsoup4, markdownify, pyyaml
```

---

## The adapter contract

```python
# scraper/adapters/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

@dataclass
class Item:
    """One unit of work discovered from a target."""
    label: str          # human title / sidebar label
    identifier: str     # slug (readme_io) | URL (docusaurus) | "repo:path" (github_org)
    extra: dict = field(default_factory=dict)
    # readme_io: {}
    # docusaurus: {}
    # github_org: {"repo": str, "default_branch": str, "commit_sha": str | None}

@dataclass
class Document:
    """The render result; maps to exactly one output file."""
    slug: str           # relative output path (see §Filename derivation); no leading slash
    title: str
    body_markdown: str
    metadata: dict      # all fields from FR-16a; null values must be explicitly present

@dataclass
class RunContext:
    config: "TargetConfig"
    page: object        # playwright.sync_api.Page | None; None if not requires_browser
    http_get: Callable[[str], str]   # urllib GET with User-Agent + timeout; raises on non-2xx
    token: str | None   # gh auth token or GITHUB_TOKEN; None for non-github adapters

class PlatformAdapter(ABC):
    name: str
    requires_browser: bool = False

    @abstractmethod
    def discover(self, ctx: RunContext) -> list[Item]:
        """Return all items for the target. May use fallback list if needed."""
        ...

    @abstractmethod
    def render(self, ctx: RunContext, item: Item) -> Document:
        """Fetch + extract + return Document. Raises on unrecoverable error."""
        ...
```

The **runner** owns everything generic: config load, adapter resolution, optional Playwright
lifecycle, `--discover/--slug/--no-discover/--limit` flags, politeness delay, `emit` calls,
and per-item error capture (NFR-4). Adapters implement only `discover` + `render`.

---

## Core engine (FR-4a and FR-4b)

### Verbatim-protected trio (FR-4a)

`get_main`, `extract_sections`, and `render_sections` move into `core.py` **unchanged**
from the seed. They are not parameterized, not modified, not extended. The ReadMe.io
adapter is their only caller. Do not touch these three functions for any reason; any
needed behavior change requires a new DDR.

### Parameterized discover_slugs (FR-4b)

`discover_slugs` is **not** part of the verbatim-protected trio. It is lifted from the
seed and parameterized to accept config values so that a second ReadMe.io target works
without a code change:

```python
# scraper/core.py

def discover_slugs(
    html: str,
    link_pattern: str = "/reference/",      # URL-path substring filter
    slug_methods: list[str] | None = None,  # HTTP method suffixes; default: see below
    slug_filter: str | None = None,         # optional extra substring filter on the slug
) -> list[tuple[str, str]]:
    """
    Parse a rendered sidebar page and return [(label, slug), ...].
    Default slug_methods = ["get", "post", "put", "delete", "patch"] (seed values).
    """
    if slug_methods is None:
        slug_methods = ["get", "post", "put", "delete", "patch"]
    ...
```

The seed's hardcoded `/reference/` and method-suffix check become defaults. `askedgar.yaml`
omits these keys and picks up the defaults, preserving exact seed behavior for the G1 gate.

---

## Extraction strategies

DDR-02 decouples extraction strategy from the core; DDR-01 D2 protects the verbatim trio.
Both hold because each adapter selects a strategy; none modifies `core.py`:

- **ReadMe.io** — verbatim `core.extract_sections` + `core.render_sections`. Tuned for
  ReadMe's param/response prose; required for G1 parity. Untouched (FR-4a).
- **Docusaurus** — `htmlmd.to_markdown(container)`: structure-preserving converter (built
  on `markdownify`) that keeps fenced code blocks (language-tagged), tables, and heading
  hierarchy intact. See §htmlmd configuration (S2 resolution) below.
- **GitHub org** — no HTML extraction; the source is already markdown. `render` prepends
  front-matter and adds an `# Title` heading only if none is present.

`htmlmd.to_markdown` first strips noise elements from the chosen container (`nav`, `aside`,
`footer`, `script`, `style`, edit-links, "On this page" TOC, "Skip to main content"
elements, any element whose text is exactly "Edit this page" or "Table of Contents")
then converts with markdownify.

### htmlmd configuration — code language callback (S2)

markdownify's `code_language_callback` must be configured to emit fenced code blocks with
the language identifier extracted from the `<pre>`/`<code>` element's CSS class. The
expected class patterns on Docusaurus/TypeDoc pages are `language-ts`, `language-js`,
`language-python`, etc. (Prism.js convention).

```python
# scraper/htmlmd.py

import re
from markdownify import markdownify, MarkdownConverter

def _code_language(el) -> str:
    """
    Return the language token for a <pre> or <code> element, or '' if none.
    Matches class="language-<token>" (Prism.js convention).
    """
    classes = el.get("class") or []
    for cls in classes:
        m = re.match(r"^language-(.+)$", cls)
        if m:
            return m.group(1)
    return ""

def to_markdown(container) -> str:
    """
    Convert a BeautifulSoup container to markdown.
    Strips noise, then converts with code-language fences.
    """
    _strip_noise(container)
    return markdownify(
        str(container),
        heading_style="ATX",
        code_language_callback=_code_language,
        strip=["script", "style"],
    )
```

**Assumption to validate (spike required before full Docusaurus adapter build):**
`markdownify`'s `code_language_callback` kwarg is available in the version pinned in
`pyproject.toml`. If the installed version does not expose this callback, the adapter must
subclass `MarkdownConverter` and override `convert_pre`/`convert_code` to achieve the same
effect. The roadmap schedules a spike to confirm this before the Docusaurus adapter forge
sprint begins.

---

## Filename derivation (C2 — FR-15a / FR-15b)

### Problem

504 Docusaurus URLs like `/api/@thatopen/components-front/classes/Angle` and GitHub
identifiers like `engine:docs/README.md` must map to deterministic, collision-safe
filenames that are safe on case-insensitive filesystems and within OS path-length limits.

### Design: path-preserving tree with per-segment sanitization

`Document.slug` is a **relative path** (no leading slash) that becomes the output file
path under `output/<target>/`. It is derived by `scraper/slugify.py` from the document's
`identifier` (URL path for Docusaurus; `repo:path` for GitHub org; slug string for
ReadMe.io).

#### Step 1 — Split into segments

- **Docusaurus:** URL path (strip scheme+host, strip query+fragment). Split on `/`.
  Example: `/api/@thatopen/components-front/classes/Angle` →
  `["api", "@thatopen", "components-front", "classes", "Angle"]`
- **GitHub org:** `{repo}:{path}`. Split on `:` first (repo / path), then path on `/`.
  Example: `engine:docs/README.md` → `["engine", "docs", "README.md"]`
- **ReadMe.io:** single slug string; treat as a single segment (no nesting).
  Example: `dilution_rating_v1_dilution_rating_get` → `["dilution_rating_v1_dilution_rating_get"]`

#### Step 2 — Sanitize each segment

Apply the following rules to each segment **independently**:

1. **Lowercase:** convert the entire segment to lowercase. This prevents
   case-insensitive collisions (e.g. `/Foo` and `/foo` → same segment after lowercasing,
   which is a collision candidate that step 4 catches).
2. **Strip leading dots:** remove leading `.` characters (hidden file prevention).
3. **Replace illegal characters:** replace any character not in `[a-z0-9._-]` with `_`.
   This covers `@`, spaces, colons, parentheses, and all other non-ASCII.
   Example: `@thatopen` → `_thatopen`; `components-front` → `components-front` (unchanged).
4. **Collapse runs:** replace two or more consecutive `_` with a single `_`.
5. **Length cap per segment:** if a sanitized segment exceeds **80 bytes** (UTF-8),
   truncate to 72 bytes and append `_` + the first 7 hex characters of the SHA-256 of the
   **original** (pre-sanitize) segment. This preserves readability while bounding length.
   Example: a 100-char segment `abcdef...` → `abcdefg...(72 bytes)_a3f9c12`.
6. **Reserved names (Windows safety):** if the lowercased segment matches a Windows
   reserved name (`con`, `prn`, `aux`, `nul`, `com0`–`com9`, `lpt0`–`lpt9`), append `_x`.

#### Step 3 — Append `.md` to the final segment

The last segment in the path becomes the filename with `.md` appended.
If the last segment already ends with `.md` or `.mdx`, replace the extension with `.md`.
Example: `["engine", "docs", "README.md"]` → final segment becomes `readme.md` (after
lowercase), so the path is `engine/docs/readme.md`.

#### Step 4 — Collision detection and resolution

After sanitization, check for identifier-level collisions within the run's collected
`Document` set. Two distinct identifiers that produce the same sanitized path are a
collision. Resolve by **appending a hash suffix** to the filename stem:

- Compute `SHA-256` of the full original identifier string (UTF-8 encoded).
- Take the first **8 hex characters** of the digest.
- Replace the final segment's stem with `{stem}_{hash8}.md`.

Example: if `/Foo/Bar` and `/foo/bar` both sanitize to `foo/bar.md`, the first (in
discovery order) retains `foo/bar.md` and the second becomes `foo/bar_<hash8>.md`.
Since the hash is derived from the original identifier, the assignment is **deterministic**
(discovery order breaks ties, but both outputs are always reproducible from the same
identifier set).

#### Step 5 — Total path-length guard

After building the full relative path (segments joined with `/` + `.md`), measure its
byte length. If it exceeds **200 bytes** (a conservative bound below Linux's 255-byte
component limit and well within the 4096-byte total), truncate the **last segment's stem**
(before the `.md`) to fit within the limit, then apply the hash-suffix rule from step 4
to avoid collisions introduced by the truncation.

#### Full example

| Original identifier | Sanitized path |
|---|---|
| `/api/@thatopen/components-front/classes/Angle` | `api/_thatopen/components-front/classes/angle.md` |
| `/api/@thatopen/components-front/classes/angle` | `api/_thatopen/components-front/classes/angle.md` — collision with above; second gets `angle_<hash8>.md` |
| `engine:docs/README.md` | `engine/docs/readme.md` |
| `engine:docs/readme.md` | `engine/docs/readme.md` — collision with above; second gets `readme_<hash8>.md` |
| `dilution_rating_v1_dilution_rating_get` | `dilution_rating_v1_dilution_rating_get.md` |

#### Document.slug and the output path

`Document.slug` carries the sanitized relative path (e.g.
`api/_thatopen/components-front/classes/angle.md`). The emit layer writes to
`output/<target>/<slug>`, creating parent directories as needed. `manifest.json` records
this same `slug` value in each per-document entry. The slug is therefore the stable,
deterministic identifier for downstream consumers.

#### slugify.py public interface

```python
# scraper/slugify.py

def identifier_to_slug(identifier: str, platform: str) -> str:
    """
    Derive a sanitized relative output path from a document identifier.
    platform: "readme_io" | "docusaurus" | "github_org"
    Returns a relative path string (no leading slash) ending in ".md".
    Does NOT check for collisions — collision detection is the runner's concern.
    """
    ...

def resolve_collisions(slugs: list[tuple[str, str]]) -> dict[str, str]:
    """
    Given [(identifier, candidate_slug), ...] in discovery order,
    return {identifier: final_slug} with hash suffixes applied where needed.
    """
    ...
```

The runner calls `resolve_collisions` after `discover()` returns the full item list,
before the render loop begins. Each `Item.identifier` maps to a final slug that is
passed into the `render` call (or the adapter receives it via the `Item.extra` dict).

---

## Fetch strategies

| Adapter | Fetch | Why |
|---|---|---|
| readme_io | Playwright (`networkidle` + settle) | SPA-hydrated; required by seed |
| docusaurus | `urllib` GET | content is SSR'd (verified assumption — see Constraints) |
| github_org | GitHub REST API + raw.githubusercontent | enumerate repos/trees, fetch raw md |

GitHub adapter call sequence:
1. `GET /orgs/{org}/repos?per_page=100` (paginated) — filter `archived: false` unless `include_archived: true` in config.
2. Per repo: read `default_branch` from API response (never hardcode `main`).
3. `GET /repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1` — filter paths matching `README*`, `*.md`/`*.mdx` under `docs/` or `documentation/`, and top-level `*.md`. No source code files.
4. `GET https://raw.githubusercontent.com/{owner}/{repo}/{default_branch}/{path}` — fetch raw markdown.
5. Per repo: `GET /repos/{owner}/{repo}/commits/{default_branch}` (head commit) for `git_ref`.

`git_ref` value: `"{default_branch}@{commit_sha}"`. If the commits endpoint fails, set `git_ref` to `null` but keep the `git_ref` key present in front-matter.

### github_org render — self-sufficiency on the --slug path (G-1)

The `--slug` flag bypasses `discover()` and the runner creates a synthetic `Item` with
`label=NAME, identifier=NAME` and an empty `extra` dict. For the github_org adapter this
means `Item.extra` will not contain `default_branch` or `commit_sha`, which are normally
populated by `discover()`.

**Identifier format for github_org.** The `--slug` value is `repo:path`, for example
`engine_components:docs/getting-started.md`. The adapter parses this as:
- `org` — from `ctx.config.options["org"]` (the target config; never from the slug).
- `repo` — the substring before the first `:`.
- `path` — the substring after the first `:`.

**render() must be self-sufficient.** When `Item.extra` lacks `default_branch` (the
`--slug` entry path), `github_org.render()` fetches the missing values on demand before
fetching raw content:
1. `GET /repos/{owner}/{repo}` — read `default_branch` from the response (satisfies FR-11).
2. `GET /repos/{owner}/{repo}/commits/{default_branch}` — read `sha` from the first commit
   entry for `commit_sha`.

When `Item.extra` already contains `default_branch` (the normal `discover()` path), render
uses the cached values and makes no additional API calls.

**Consequence.** `git_ref` is always populated for github_org regardless of whether the
item entered via `discover()` or `--slug`, preserving the FR-16a requirement that
`git_ref` is required (not null) for github_org and the AC-2 assertion that `git_ref` is
present and non-null in every output file's front-matter.

---

## Config layer

`TargetConfig` (dataclass) carries common fields plus a raw `options: dict` for
adapter-specific keys:

```python
# scraper/config.py

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
    """Read targets/{name}.yaml, validate platform against ADAPTERS registry."""
    ...
```

---

## Front-matter schema (FR-16a)

Every `Document.metadata` dict must contain **all** of the following keys before
`write_document` is called. Nullable fields must be present with an explicit `null`
value — they must not be absent.

```python
# Required key set (FR-16a)
{
    "source_url":    str,           # required, non-null for all platforms
    "title":         str,           # required, non-null for all platforms
    "platform":      str,           # required, non-null: "readme_io"|"docusaurus"|"github_org"
    "target":        str,           # required, non-null: target name from config
    "package":       str | None,    # docusaurus only (from /api/@scope/pkg/ path); null otherwise
    "repo":          str | None,    # github_org only; null otherwise
    "breadcrumb":    str | None,    # docusaurus + github_org; null for readme_io
    "fetched_at":    str,           # ISO-8601 UTC; required, non-null
    "content_hash":  str,           # sha256 hex digest of body_markdown; required, non-null
    "git_ref":       str | None,    # github_org only ("{branch}@{sha}"); null otherwise
}
```

`emit.write_document` validates all required (non-nullable) fields are present and
non-empty before writing. If validation fails, the document is recorded as a failure
in the manifest and the run continues (NFR-4).

---

## Emit layer — atomic writes (S3 — NFR-4)

`emit.write_document(doc, cfg)` and `emit.write_manifest(docs, failures, cfg)` both write
**atomically** using the write-to-temp-then-replace pattern:

```python
# scraper/emit.py (pattern for both write_document and write_manifest)

import os, tempfile
from pathlib import Path

def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically. Safe against interrupted runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)   # atomic on POSIX; best-effort on Windows
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
```

`write_manifest` is called **once** after the render loop completes. The manifest is
never written incrementally — a process killed mid-loop leaves no manifest file at all
(which is a clean failure state), not a partial one. Individual document files are also
written atomically, so a kill mid-run leaves only complete files (plus a missing
manifest, which is detectable).

`manifest.json` schema:

```json
{
  "target": "<name>",
  "platform": "<platform>",
  "generated_at": "<ISO-8601 UTC>",
  "document_count": 42,
  "failure_count": 0,
  "documents": [
    {
      "slug": "relative/path/to/file.md",
      "title": "...",
      "source_url": "...",
      "content_hash": "..."
    }
  ],
  "failures": [
    {
      "identifier": "...",
      "error": "..."
    }
  ]
}
```

The `documents` array contains only successfully written files. `document_count` equals
`len(documents)` equals the number of `.md` files written to `output/<target>/` (AC-1d).
`failure_count` equals `len(failures)`.

---

## G1 golden fixture and offline regression gate (C3 — AC-3a / AC-3b / AC-3c)

### What the fixture contains

Two JSON files committed to `tests/fixtures/askedgar/`:

**`slugs.json`** — a JSON array of slug strings, one per discovered endpoint:
```json
["health_check_health_get", "list_endpoints_endpoints_get", ...]
```

**`headings.json`** — a JSON object mapping slug → array of heading strings (the section
heading keys from `extract_sections`, i.e. all keys except `_title`):
```json
{
  "health_check_health_get": ["query params", "response"],
  "dilution_rating_v1_dilution_rating_get": ["query params", "responses"],
  ...
}
```

The heading strings are the lowercased, stripped heading text exactly as
`extract_sections` produces them (the `sections` dict keys, minus `_title`).

### How the fixture is captured (precondition)

The fixture is captured by running the seed (`seed/scrape_askedgar_reference.py --discover`
for slugs, and a full run for headings) against live `askedgar.readme.io` **before the seed
is deleted**. This requires Playwright and live site access — it is a one-time capture step
scheduled in the roadmap before the forge sprint for the ReadMe.io adapter. The capture
script writes the two JSON files to `tests/fixtures/askedgar/` and they are committed to
the repo.

### How the regression test works (offline — AC-3c)

`tests/test_g1_regression.py` runs the `readme_io` adapter against the adapter's own
output (not the live site) by:

1. Loading the committed fixture (`slugs.json`, `headings.json`).
2. Running `adapter.discover(ctx)` against a locally-saved copy of the seed HTML page
   (also committed as `tests/fixtures/askedgar/seed_page.html`) — no network call.
3. Comparing the discovered slug set against `slugs.json`: **exact set equality** (AC-3a).
   Order differences are ignored; any missing or extra slug is a failure.
4. For a representative subset of slugs (or all, if fixture includes rendered output),
   comparing the section heading sets (keys of `extract_sections` output, minus `_title`)
   against `headings.json`: **exact set equality per slug** (AC-3b).

The test has **zero network dependency**: `seed_page.html` is the committed HTML snapshot
that `discover_slugs` parses; heading comparison uses committed heading sets. No
`askedgar.readme.io` call is made during the test.

### Fixture files summary

| File | Content | Used in |
|---|---|---|
| `tests/fixtures/askedgar/slugs.json` | JSON array of slug strings | AC-3a comparison |
| `tests/fixtures/askedgar/headings.json` | JSON object: slug → [heading strings] | AC-3b comparison |
| `tests/fixtures/askedgar/seed_page.html` | Rendered HTML of the seed URL sidebar page | offline discover_slugs input |

All three files are committed to the repo. They are the offline baseline; the live site
is not consulted by the test suite.

---

## Control flow (runner)

```
cfg = load_target(name)
adapter = ADAPTERS[cfg.platform]()
with browser_if_needed(adapter.requires_browser) as page:
    ctx = RunContext(cfg, page, http_get, token)

    # Discovery
    if args.slug:
        raw_items = [Item(label=args.slug, identifier=args.slug)]
        # NOTE: synthetic Item has empty extra dict. For github_org, render() fetches
        # default_branch and commit_sha on demand (see §github_org render — G-1).
    else:
        raw_items = adapter.discover(ctx)   # includes fallback logic internally

    # Collision-safe slug assignment (before render loop)
    id_to_slug = resolve_collisions(
        [(it.identifier, identifier_to_slug(it.identifier, cfg.platform))
         for it in raw_items]
    )
    items = [Item(it.label, it.identifier, {**it.extra, "_slug": id_to_slug[it.identifier]})
             for it in raw_items]

    if args.discover:
        for it in items:
            print(f"  {it.identifier}  →  {id_to_slug[it.identifier]}")
        return

    if args.limit:
        items = items[:args.limit]

    docs, failures = [], []
    for it in items:
        try:
            doc = adapter.render(ctx, it)
            docs.append(doc)
        except Exception as e:
            failures.append({"identifier": it.identifier, "error": str(e)})
            log_failure(it, e)
        sleep(cfg.polite_delay_seconds)

    emit.write_all(docs, failures, cfg)   # atomic per-doc writes + atomic manifest
```

---

## Patterns and rationale

| Pattern | Usage | Rationale |
|---|---|---|
| Adapter interface (ABC) | `PlatformAdapter` | isolates per-platform logic; adding a platform = one new file (FR-1) |
| Strategy pattern | Extraction (extract_sections vs htmlmd) | different DOM structures need different converters; the core is unchanged (FR-4a) |
| Options bag in config | `TargetConfig.options: dict` | avoids a new dataclass per platform; adapter reads its own keys |
| Atomic write (write-then-replace) | emit layer | prevents corrupt partial manifests and partial doc files (NFR-4, S3) |
| Committed golden fixture | G1 regression | makes the characterization gate reproducible offline, independent of live site (AC-3c) |
| Slug-before-render | runner resolves collisions before the render loop | deterministic assignment independent of render order; slugs stable across re-runs (FR-15a) |
| Self-sufficient render (github_org) | github_org.render() fetches default_branch/commit_sha when Item.extra is empty | guarantees git_ref is always populated regardless of entry path — --slug or discover() (FR-16a, AC-2, G-1) |

### Anti-patterns (do not use)

- **Modify `get_main`, `extract_sections`, `render_sections`:** forbidden (FR-4a, DDR-01 D2).
- **Hardcode `main` as default branch:** forbidden (FR-11).
- **Incremental manifest writes:** the manifest is written once atomically at the end of
  the run; never written document-by-document (prevents partial manifests).
- **Lazy collision detection (detect at write time):** collisions are resolved before the
  render loop, not at emit time, so `Document.slug` is stable and deterministic.

---

## Dependencies

| Library | Version | Purpose |
|---|---|---|
| `playwright` | latest stable | Playwright browser automation (readme_io adapter only) |
| `beautifulsoup4` | >=4.12 | HTML parsing (all adapters; `html.parser` backend) |
| `markdownify` | >=0.12 | HTML→markdown conversion (htmlmd.py; code_language_callback needed — verify in spike) |
| `pyyaml` | >=6.0 | YAML front-matter serialization |

All HTTP done via stdlib `urllib.request`. HTML parsing uses stdlib `html.parser` backend
(no `lxml` or `html5lib` dependency). No other third-party dependencies are permitted
(NFR-5).

---

## Integration points

| Integration | How |
|---|---|
| `seed/scrape_askedgar_reference.py` | Source of truth for G1 fixture capture; deleted after fixture is committed and G1 passes |
| `targets/*.yaml` | Loaded by `config.load_target`; the only place per-target configuration lives |
| `output/<target>/` | Written by emit layer; gitignored; regenerated each run |
| `tests/fixtures/askedgar/` | Committed baseline for offline G1 regression; not regenerated by normal runs |
| GitHub API (`api.github.com`) | github_org adapter; authenticated via `gh auth token` or `GITHUB_TOKEN` env var |
| `raw.githubusercontent.com` | github_org adapter; unauthenticated raw markdown fetch |

---

## What this does NOT add (DDR-02 scope boundary)

No snapshot store, no prior-scrape pointer, no reconcile/diff pass, no Mode-2 anything.
`output/` is regenerated each run; history is not retained. No downstream embedding,
chunking, or vector store logic. No dedup of the `engine_docs` ↔ `docs.thatopen.com`
overlap (downstream concern enabled by `git_ref`; not performed here).
