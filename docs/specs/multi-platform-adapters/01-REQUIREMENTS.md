# REQUIREMENTS — Multi-platform adapter architecture

| Field | Value |
|---|---|
| Author | scraper (fabric) |
| Date | 2026-06-25 |
| Governing DDR | DDR-02 (LORE `acd22c0f-7b80-440f-8b83-d3e19f5e2b72`) |
| Supersedes | REQUIREMENTS.md (draft — pre-QC) |
| Status | REVISED — QC findings C1, C2, C3, S1, S4 addressed |

Requirements are traceable to DDR-02. Each carries an ID; the REVIEW traceability matrix
maps DDR-02 clauses → these IDs.

**Renumbering note:** FR-4 and FR-5 from the draft are replaced by FR-4a and FR-4b to
resolve QC finding C1. All other IDs are stable.

---

## Functional requirements

### Adapter seam

- **FR-1** A `PlatformAdapter` interface decouples **discovery** and **extraction** from the
  shared core. Adding a platform = adding one adapter; adding a target of a known platform =
  adding one `targets/<name>.yaml` with **no code change**.
- **FR-2** A target config names its platform (`platform: readme_io | docusaurus | github_org`);
  the runner resolves the adapter from a registry.
- **FR-3** Adapters declare whether they need a browser. The runner provisions a Playwright
  page only for adapters that require it; HTTP/API adapters run without a browser.

### Core engine (lifted from seed, VERBATIM-protected trio)

- **FR-4a** `get_main`, `extract_sections`, and `render_sections` are the **verbatim-protected
  trio** (DDR-01 D2). They move into `core.py` unchanged; the ReadMe.io adapter is their
  only caller. These three functions are not parameterized, not modified, and not extended.
- **FR-4b** `discover_slugs` is **parameterized** from config and is NOT part of the
  verbatim-protected trio. The discovery behavior must be configurable via `link_pattern`
  (URL-path filter) and `slug_methods` / `slug_filter` (slug validation strategy), with the
  seed's current hardcoded values as defaults. `discovery_min_slugs` (fallback threshold)
  and `fallback_slugs` also come from config.

  *Rationale (resolves C1):* DDR-01 D2 states "Discovery is parameterized (`link_pattern`,
  `slug_methods`) from config." The verbatim protection in D2 applies only to `get_main`,
  `extract_sections`, and `render_sections`; `discover_slugs` is the function that
  generalizes across ReadMe.io targets and therefore cannot be hardcoded.

### ReadMe.io adapter (port of seed)

- **FR-5** Reproduces the seed: Playwright fetch (`networkidle` + settle), sidebar slug
  discovery using parameterized `discover_slugs` (FR-4b), fallback to `fallback_slugs`
  when discovered count < `discovery_min_slugs`, single-target behavior. Output for
  AskEdgar must satisfy the G1 characterization gate (see AC-3 / AC-3a / AC-3b).

### Docusaurus adapter

- **FR-6** Discovery via the target's `sitemap.xml`, with optional `include_patterns` /
  `exclude_patterns` (URL-path globs). Default: **acquire all** sitemap URLs.
- **FR-7** Fetch via plain HTTP (`urllib`), no browser (content is SSR'd).
- **FR-8** Extraction selects the content container (`article` / `.theme-doc-markdown` /
  `main`) and converts it with a **structure-preserving HTML→markdown** strategy that keeps
  fenced code blocks, tables, and heading hierarchy intact (see ARCHITECTURE §extraction).
- **FR-9** Derive `package` (from `/api/@scope/pkg/...`) and `breadcrumb` (from path segments).

### GitHub org adapter

- **FR-10** Enumerate the org's public repos via the GitHub API (auth from `gh auth token`,
  fallback `GITHUB_TOKEN`). Archived repos excluded by default (config-overridable).
- **FR-11** For each repo, read its **actual `default_branch`** (never hardcode `main`).
- **FR-12** Select documentation markdown only: `README*`, `*.md`/`*.mdx` under `docs/`
  (and `documentation/`), and top-level `*.md`. No source code.
- **FR-13** Fetch raw markdown; pass through (already markdown). Light normalization only
  (strip nothing semantic); add front-matter + heading where useful.

### Output

- **FR-14** Default output = **one markdown file per document** under `output/<target>/`.
- **FR-15** Output filenames must be **deterministic** and **collision-safe** (see FR-15a
  and FR-15b; scheme is an architecture/implementation decision).
  - **FR-15a** Deterministic: re-running the same target with the same document set must
    produce identical filenames.
  - **FR-15b** Collision-safe: across 504+ nested Docusaurus URLs and GitHub `repo:path`
    identifiers, no two distinct documents may map to the same filename (no silent
    overwrites). The scheme must be safe on case-insensitive filesystems and must not
    produce paths exceeding OS path-length limits (255 bytes per component; 4096 bytes
    total on Linux).

  *Note (resolves C2):* The filename derivation scheme itself is an architecture decision;
  this requirement states only what properties it must satisfy.

- **FR-16** Every output file carries **YAML front-matter** with the schema defined in
  FR-16a. The front-matter must parse as valid YAML and contain all required fields before
  the file is written.

  **FR-16a — Front-matter schema:**

  | Field | Type | Required | Nullable | Notes |
  |---|---|---|---|---|
  | `source_url` | string (URL) | all platforms | no | canonical URL of the document |
  | `title` | string | all platforms | no | document title |
  | `platform` | string | all platforms | no | `readme_io`, `docusaurus`, or `github_org` |
  | `target` | string | all platforms | no | target name from config |
  | `package` | string | docusaurus only | yes | derived from `/api/@scope/pkg/` path |
  | `repo` | string | github_org only | yes | repository name |
  | `breadcrumb` | string | docusaurus, github_org | yes | derived from URL/path segments |
  | `fetched_at` | string (ISO-8601) | all platforms | no | UTC timestamp of acquisition |
  | `content_hash` | string (sha256) | all platforms | no | sha256 hex digest of the markdown body |
  | `git_ref` | string | github_org only | yes | `"{branch}@{commit_sha}"` for provenance/dedup |

  For `readme_io` targets: `package`, `repo`, `breadcrumb`, and `git_ref` are null.
  For `docusaurus` targets: `repo` and `git_ref` are null.
  For `github_org` targets: `package` is null; `git_ref` is required (not null).

  *Note (resolves S4):* `git_ref` enables dedup of the `engine_docs` ↔ `docs.thatopen.com`
  overlap; its interpretation is a downstream pipeline concern, not this tool's.

- **FR-17** Each run writes a `manifest.json` at `output/<target>/`: run metadata
  (`target`, `platform`, `generated_at`, counts) + a per-document array
  (`slug`/filename, `title`, `source_url`, `content_hash`).
- **FR-18** ReadMe.io/AskEdgar retains a **single-file** output mode for G1 regression parity;
  per-doc is the default for the new adapters. Mode is config-selectable.

### CLI

- **FR-19** `python -m scraper.cli --target <name>` runs a target. Preserve the seed's flags:
  `--discover` (list discovered items, no fetch), `--slug/--single <id>` (one document),
  `--no-discover` (use fallback list). Add `--limit N` (cap documents — for smoke tests).

---

## Non-functional requirements

- **NFR-1 Quality gate (binding, DDR-02):** output must be clean and consistent. The
  mechanizable, automatable assertions that constitute this gate are defined in AC-1a through
  AC-1d below. Spot-check human judgment (AC-1e) supplements but does not replace them.
- **NFR-2 Politeness:** configurable inter-request delay (default 0.8 s, per seed). HTTP/API
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

---

## Acceptance criteria

### AC-1 — NFR-1 quality gate: mechanizable assertions (→ NFR-1, FR-6..FR-17)

The following assertions are automatable and must all pass. They apply to the output of any
adapter run (ThatOpen proving target for Docusaurus and GitHub org adapters):

- **AC-1a Chrome-bleed denylist:** No output markdown file may contain any of the
  following strings (case-insensitive): `"Skip to main content"`, `"Edit this page"`,
  `"On this page"`, `"Table of Contents"`, or any footer copyright string (e.g. text
  matching the pattern `"© \d{4}"`). Given any produced markdown file, when scanned for
  these strings, the result is zero matches.
- **AC-1b Code block fidelity:** For any page whose source HTML contains a `<code>` or
  `<pre>` element, the corresponding output markdown file must contain at least one fenced
  code block (` ``` ` delimiter). Given a known-code page, when the output file is
  inspected, then at least one triple-backtick fence is present.
- **AC-1c Front-matter validity:** Every output file must parse as valid YAML front-matter
  and contain all required fields defined in FR-16a for its platform (i.e., all non-nullable
  fields are present and non-empty). Given any output file, when the front-matter block is
  parsed with a YAML parser, then parsing succeeds and all required keys are present with
  non-null, non-empty values.
- **AC-1d Manifest consistency:** `manifest.json` must parse as valid JSON, and its
  per-document entry count must equal the number of markdown files written to
  `output/<target>/`. Given a completed run, when the manifest entry count is compared to
  the file count, they are equal.
- **AC-1e Human spot-check (subjective supplement):** A full `--target thatopen-docs` run is
  spot-checked on representative TypeDoc `/api/` and `/Tutorials/` pages; output is judged
  to preserve structure equivalent to the ReadMe.io engine's output quality. This criterion
  is not independently sufficient but confirms holistic quality beyond the mechanical checks.

### AC-2 — GitHub org adapter (→ FR-10..FR-13, FR-15, FR-16, FR-17)

A full `--target thatopen-github` run:
- Produces per-repo documentation markdown using each repo's actual default branch (not
  hardcoded `main`).
- `repo` and `git_ref` fields are present and non-null in every output file's front-matter.
- `manifest.json` entry count equals file count (AC-1d holds).
- AC-1a, AC-1c, AC-1d pass over the full output set.

### AC-3 — AskEdgar G1 characterization gate (→ FR-4a, FR-4b, FR-5, DDR-01 G1)

The G1 gate is run against a **committed golden fixture** (a captured baseline from the
seed), not only against the live site, so that the criterion is reproducible offline.

- **AC-3a Slug set identity:** Given a `--discover` run against the AskEdgar target, the
  discovered slug set must be **set-identical** to the golden fixture's slug set. The
  comparison is exact set equality (no missing slugs, no extra slugs). Order differences
  are permitted; content differences are not.
- **AC-3b Section heading sets match per slug:** For each slug in the intersection, the set
  of section headings present in the rendered output must match the golden fixture's heading
  set for that slug. Differences are permitted only in the run header and `fetched_at` date
  line. No other structural differences are acceptable.
- **AC-3c Offline reproducibility:** The G1 gate must be runnable against the committed
  baseline without network access to `askedgar.readme.io`. The golden fixture is committed
  to the repo; the comparison tool operates on the fixture, not the live site.

  *Note (resolves C3):* "Structurally equivalent" in the draft AC-3 is now defined
  concretely as set-identical slugs (AC-3a) and matching per-slug heading sets (AC-3b),
  with differences confined to the run header/date. The offline reproducibility requirement
  (AC-3c) means a CI run does not require live site access to gate the lift.

### AC-4 — No-code-change generalization (→ FR-1, FR-2)

Adding a second target of an existing platform requires only a new `targets/<name>.yaml`
file — demonstrated by adding a second target without any code change.

---

## Edge cases

| Case | Expected behavior |
|---|---|
| Docusaurus sitemap URL count is zero or unreachable | Fail fast with a clear error; do not write an empty manifest |
| Docusaurus page has no `<article>` / `.theme-doc-markdown` / `<main>` container | Log the failure, record in manifest as error, continue run (NFR-4) |
| GitHub API returns a repo whose `default_branch` is absent or null | Log and skip that repo; record as error in manifest |
| Two Docusaurus URLs differ only by case (e.g. `/Foo` and `/foo`) | Filename scheme must produce distinct, non-colliding names (FR-15b) |
| A Docusaurus URL path is deeply nested and would exceed OS path-length limit | Filename scheme must handle via truncation or hashing (FR-15b); no silent truncation that produces collisions |
| `discovery_min_slugs` threshold not met and `fallback_slugs` is empty | Fail fast on the ReadMe.io target; do not proceed with zero slugs |
| A single document fetch fails mid-run (network timeout, HTTP 4xx/5xx) | Log, record error in manifest, continue (NFR-4); manifest entry count still equals file count for successfully written files |
| `manifest.json` write interrupted mid-run | Must not leave a partially-written manifest that passes JSON parse (NFR-4) |
| GitHub org has archived repos | Excluded by default; config flag `include_archived: true` re-enables |
| `git_ref` unavailable for a GitHub document (API does not return commit SHA) | Field is null but must be explicitly present in front-matter; not omitted |

---

## Out of scope

- NOT: Mode-2 reconcile, drift reporting, or stateful versioned snapshot store (DDR-02 scope boundary; NFR-6).
- NOT: Downstream concerns — embedding, chunking, vector store ingestion (separate tool).
- NOT: Dedup of the `engine_docs` ↔ `docs.thatopen.com` overlap — `git_ref` enables a downstream consumer to perform dedup; this tool does not.
- NOT: Other platform adapters (Swagger/OpenAPI, GitBook, Mintlify, Docusaurus-other) — not this pass.
- NOT: Source-code scraping from GitHub repos — documentation markdown only (FR-12).
- NOT: Private repo access — public repos only via GitHub API.
- NOT: Snapshot retention or run history — each run overwrites `output/<target>/`.
- NOT: Filename collision scheme design — that is an architecture decision; FR-15 states the required properties only.
- NOT: Hand-maintained-doc reconciliation mode (DDR-01 D4).
- Deferred: G2 gate (second structurally-different ReadMe.io target) — DDR-01 scope; AC-4 tests the no-code-change property across platforms instead.

---

## Constraints

- Must: Python 3.11+ (NFR-5); no dependency outside `playwright`, `beautifulsoup4`, `markdownify`, `pyyaml`, and stdlib.
- Must: Filenames deterministic and collision-safe on case-insensitive filesystems and within OS path-length limits (FR-15b).
- Must: Front-matter schema exactly as specified in FR-16a; no extra required fields added without a requirements revision.
- Must not: Modify `get_main`, `extract_sections`, or `render_sections` (FR-4a, DDR-01 D2).
- Must not: Hardcode `main` as the default branch for any GitHub repo (FR-11).
- Must not: Acquire source code from GitHub repos — documentation markdown only (FR-12).
- Assumes: `docs.thatopen.com` SSR-renders full content without JavaScript execution; if this changes, FR-7 requires revision.
- Assumes: `sitemap.xml` at `docs.thatopen.com/sitemap.xml` remains the authoritative URL enumeration source for the Docusaurus adapter.
- Assumes: `gh` CLI is authenticated in the environment or `GITHUB_TOKEN` is set; no interactive auth flow is in scope.
- Assumes: The committed AskEdgar golden fixture (AC-3c) is captured from the seed before the seed is deleted.
