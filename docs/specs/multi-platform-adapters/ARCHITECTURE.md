# ARCHITECTURE — Multi-platform adapter architecture

| Field | Value |
|---|---|
| Author | scraper (fabric) |
| Date | 2026-06-25 |
| Governing DDR | DDR-02 (LORE `acd22c0f-7b80-440f-8b83-d3e19f5e2b72`) |
| Status | DRAFT — for Frank QC |

## Package layout

```
scraper/
  __init__.py
  config.py          # TargetConfig + load_target(name); `platform` selects the adapter
  core.py            # VERBATIM seed engine: fetch / get_main / extract_sections /
                     #   render_sections / discover_slugs. Caller: readme_io only. PROTECTED.
  htmlmd.py          # structure-preserving HTML-container -> markdown (markdownify-based)
  emit.py            # Document dataclass; per-doc front-matter writer; manifest.json;
                     #   single-file mode (AskEdgar regression)
  runner.py          # load config -> resolve adapter -> discover() -> render() each -> emit;
                     #   owns flags, politeness, browser lifecycle (only if requires_browser)
  cli.py             # argparse: --target, --discover, --slug, --no-discover, --limit
  adapters/
    __init__.py      # ADAPTERS registry {name: class}
    base.py          # PlatformAdapter ABC + Item / Document / RunContext dataclasses
    readme_io.py     # wraps core.py (Playwright); single-file output (seed parity)
    docusaurus.py    # sitemap discovery + path filters; urllib fetch; htmlmd extraction
    github_org.py    # GitHub API enumeration; per-repo default branch; markdown passthrough
targets/
  askedgar.yaml          # platform: readme_io  (existing; gains `platform` + output mode)
  thatopen-docs.yaml     # platform: docusaurus
  thatopen-github.yaml   # platform: github_org
output/                  # gitignored; output/<target>/*.md + manifest.json
pyproject.toml           # deps: playwright, beautifulsoup4, markdownify, pyyaml
```

## The adapter contract (resolves intake Q2)

```python
# adapters/base.py
@dataclass
class Item:                 # one unit of work discovered on a target
    label: str              # human title / sidebar label
    identifier: str         # slug (readme), URL (docusaurus), or "repo:path" (github)
    extra: dict             # adapter-specific payload (e.g. repo default_branch)

@dataclass
class Document:             # the render result -> one output file
    slug: str               # output filename stem (deterministic from identifier)
    title: str
    body_markdown: str
    metadata: dict          # becomes YAML front-matter (schema in REQUIREMENTS FR-16)

@dataclass
class RunContext:
    config: TargetConfig
    page: "playwright Page | None"   # provisioned only if adapter.requires_browser
    http_get: Callable[[str], str]   # urllib-backed GET with UA + timeout
    token: str | None                # gh/GITHUB_TOKEN for github_org

class PlatformAdapter(ABC):
    name: str
    requires_browser: bool = False
    @abstractmethod
    def discover(self, ctx: RunContext) -> list[Item]: ...
    @abstractmethod
    def render(self, ctx: RunContext, item: Item) -> Document: ...
```

The **runner** owns everything generic: config load, adapter resolution, optional Playwright
lifecycle, the `--discover/--slug/--no-discover/--limit` flags, politeness delay, calling
`emit`, and per-item error capture (NFR-4). Adapters implement only `discover` + `render`.

## Extraction strategies (resolves intake Q1 — the protected core)

DDR-02 decouples extraction strategy from the core; DDR-01 D2 protects the core verbatim.
Both hold because each adapter *selects* a strategy; none *modifies* the core:

- **ReadMe.io** → the verbatim `core.extract_sections` + `render_sections`. Tuned for
  ReadMe's param/response prose; required for G1 parity. Untouched.
- **Docusaurus** → `htmlmd.to_markdown(container)`: a structure-preserving converter (built
  on `markdownify`) that keeps `<pre><code>` as fenced blocks (language from `class`),
  `<table>` as markdown tables, and `h1–h6` hierarchy. Rationale: the seed's renderer
  flattens code to prose, which fails NFR-1 on code-heavy TypeDoc/tutorial pages. This is an
  *additional* strategy behind the interface, not a change to `core.py`.
- **GitHub org** → no HTML extraction; the source is already markdown. `render` wraps it with
  front-matter + an H1 if missing.

`htmlmd` first strips noise (`nav`, `aside`, `footer`, `script`, `style`, edit-links, the
"On this page" TOC) from the chosen container, then converts.

## Fetch strategies

| Adapter | Fetch | Why |
|---|---|---|
| readme_io | Playwright (`networkidle` + settle) | SPA-hydrated; required by seed |
| docusaurus | `urllib` GET | content is SSR'd (verified) — no browser |
| github_org | GitHub REST API + raw.githubusercontent | enumerate repos/trees, fetch raw md |

GitHub adapter calls: `GET /orgs/{org}/repos` → per repo `default_branch` →
`GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1` → filter paths (FR-13) →
fetch each via `raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}`.

## Config layer

`TargetConfig` (dataclass) carries the common fields (`name`, `platform`, `base_url`,
`output_dir`, `output_mode`, `header`, `polite_delay_seconds`, timings) plus a raw
`options: dict` that each adapter reads for its platform-specific keys (readme: `seed_url`,
`link_pattern`, `slug_methods`, `fallback_slugs`; docusaurus: `sitemap_url`,
`include_patterns`, `exclude_patterns`, `content_selectors`; github: `org`, `include_globs`,
`include_archived`). `load_target(name)` reads `targets/<name>.yaml` and validates `platform`
against the registry. This keeps one loader while letting adapters own their knobs (FR-2).

## Emit layer

`emit.write_document(doc, cfg)` renders `metadata` → YAML front-matter (PyYAML) + body to
`output/<target>/<slug>.md`. `emit.write_manifest(docs, cfg)` writes `manifest.json`
(FR-17). `single_file` mode concatenates documents into one file with a header (AskEdgar/G1).
`content_hash` = sha256 of `body_markdown`; `fetched_at` stamped at render time.

## Control flow (runner)

```
cfg = load_target(name)
adapter = ADAPTERS[cfg.platform]()
with browser_if_needed(adapter.requires_browser) as page:
    ctx = RunContext(cfg, page, http_get, token)
    items = [Item(slug,slug)] if --slug else adapter.discover(ctx)   # fallback if < min
    if --discover: print(items); return
    if --limit: items = items[:N]
    docs = []
    for it in items:
        try: docs.append(adapter.render(ctx, it))
        except Exception as e: record_failure(it, e)         # NFR-4
        sleep(cfg.polite_delay_seconds)
    emit.write_all(docs, cfg)        # per-doc + manifest, or single-file
```

## What this does NOT add (DDR-02 scope boundary)
No snapshot store, no prior-scrape pointer, no reconcile/diff pass, no Mode-2 anything.
`output/` is regenerated each run; history is not retained.
