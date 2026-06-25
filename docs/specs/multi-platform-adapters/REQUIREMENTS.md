# REQUIREMENTS — Multi-platform adapter architecture

| Field | Value |
|---|---|
| Author | scraper (fabric) |
| Date | 2026-06-25 |
| Governing DDR | DDR-02 (LORE `acd22c0f-7b80-440f-8b83-d3e19f5e2b72`) |
| Status | DRAFT — for Frank QC |

Requirements are traceable to DDR-02. Each carries an ID; the REVIEW traceability matrix
maps DDR-02 clauses → these IDs.

## Functional requirements

### Adapter seam
- **FR-1** A `PlatformAdapter` interface decouples **discovery** and **extraction** from the
  shared core. Adding a platform = adding one adapter; adding a target of a known platform =
  adding one `targets/<name>.yaml` with **no code change**.
- **FR-2** A target config names its platform (`platform: readme_io | docusaurus | github_org`);
  the runner resolves the adapter from a registry.
- **FR-3** Adapters declare whether they need a browser. The runner provisions a Playwright
  page only for adapters that require it; HTTP/API adapters run without a browser.

### Core engine (lifted from seed, protected)
- **FR-4** `get_main`, `extract_sections`, `render_sections`, `discover_slugs` move into the
  package **unchanged** (DDR-01 D2). The ReadMe.io adapter is their only caller.
- **FR-5** Discovery knobs (`link_pattern`, `slug_methods`, `discovery_min_slugs`,
  `fallback_slugs`) and timings come from config, preserving the seed's defaults.

### ReadMe.io adapter (port of seed)
- **FR-6** Reproduces the seed: Playwright fetch (`networkidle` + settle), sidebar slug
  discovery with fallback threshold, single-target behavior. Output for AskEdgar must be
  structurally equivalent to the seed (DDR-01 G1).

### Docusaurus adapter
- **FR-7** Discovery via the target's `sitemap.xml`, with optional `include_patterns` /
  `exclude_patterns` (URL-path globs). Default: **acquire all** sitemap URLs.
- **FR-8** Fetch via plain HTTP (`urllib`), no browser (content is SSR'd).
- **FR-9** Extraction selects the content container (`article` / `.theme-doc-markdown` /
  `main`) and converts it with a **structure-preserving HTML→markdown** strategy that keeps
  fenced code blocks, tables, and heading hierarchy intact (see ARCHITECTURE §extraction).
- **FR-10** Derive `package` (from `/api/@scope/pkg/...`) and `breadcrumb` (from path segments).

### GitHub org adapter
- **FR-11** Enumerate the org's public repos via the GitHub API (auth from `gh auth token`,
  fallback `GITHUB_TOKEN`). Archived repos excluded by default (config-overridable).
- **FR-12** For each repo, read its **actual `default_branch`** (never hardcode `main`).
- **FR-13** Select documentation markdown only: `README*`, `*.md`/`*.mdx` under `docs/`
  (and `documentation/`), and top-level `*.md`. No source code.
- **FR-14** Fetch raw markdown; pass through (already markdown). Light normalization only
  (strip nothing semantic); add front-matter + heading where useful.

### Output
- **FR-15** Default output = **one markdown file per document** under `output/<target>/`,
  filename derived deterministically from the document identifier.
- **FR-16** Every output file carries **YAML front-matter** with a uniform schema:
  `source_url`, `title`, `platform`, `target`, `package` (nullable), `repo` (nullable),
  `breadcrumb` (nullable), `fetched_at` (ISO-8601), `content_hash` (sha256 of body).
- **FR-17** Each run writes a `manifest.json` at `output/<target>/`: run metadata
  (`target`, `platform`, `generated_at`, counts) + a per-document array
  (`slug`/filename, `title`, `source_url`, `content_hash`).
- **FR-18** ReadMe.io/AskEdgar retains a **single-file** output mode for G1 regression parity;
  per-doc is the default for the new adapters. Mode is config-selectable.

### CLI
- **FR-19** `python -m scraper.cli --target <name>` runs a target. Preserve the seed's flags:
  `--discover` (list discovered items, no fetch), `--slug/--single <id>` (one document),
  `--no-discover` (use fallback list). Add `--limit N` (cap documents — for smoke tests).

## Non-functional requirements

- **NFR-1 Quality gate (binding, DDR-02):** output must be clean and consistent —
  no nav/aside/footer/script bleed; intact heading hierarchy; **code as fenced blocks**;
  tables preserved; uniform front-matter; valid `manifest.json`. Proven on ThatOpen,
  judged equivalent to the ReadMe.io engine output.
- **NFR-2 Politeness:** configurable inter-request delay (default 0.8s, per seed). HTTP/API
  adapters identify with a descriptive User-Agent. No hammering (504 Docusaurus pages OK at
  the polite delay).
- **NFR-3 Determinism/idempotency:** re-running a target yields stable filenames and stable
  output (modulo `fetched_at`); `content_hash` lets a consumer detect changes.
- **NFR-4 Resilience:** a single document failure is logged and recorded in the manifest;
  the run continues. No partial-write corruption of the manifest.
- **NFR-5 Environment:** Python 3.11+ (runs on the 3.14 present here). Dependencies limited
  to `playwright`, `beautifulsoup4`, `markdownify`, `pyyaml`. HTTP via stdlib `urllib`;
  HTML parsing via stdlib `html.parser`.
- **NFR-6 Scope guard:** no Mode-2 reconcile, no snapshot store, no downstream concern
  (DDR-02 scope boundary).

## Acceptance criteria

- **AC-1 (→ NFR-1, FR-7..FR-17):** A full `--target thatopen-docs` run produces per-doc
  markdown + manifest; spot-checked TypeDoc `/api/` and `/Tutorials/` pages show intact code
  fences, tables, headings, clean front-matter, no chrome bleed.
- **AC-2 (→ FR-11..FR-17):** A full `--target thatopen-github` run produces per-repo doc
  markdown using each repo's real default branch, with repo/path in front-matter + manifest.
- **AC-3 (→ FR-4..FR-6, DDR-01 G1):** `--target askedgar --discover` lists the same slug set
  as the seed; a single-slug render matches the seed structurally (when site reachable).
- **AC-4 (→ FR-1, FR-2):** Adding a second target of an existing platform requires only a new
  YAML file — demonstrated, no code change.
