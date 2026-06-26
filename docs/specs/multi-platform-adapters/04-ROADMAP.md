# ROADMAP — Multi-platform adapter architecture

| Field | Value |
|---|---|
| Author | scraper (fabric) |
| Date | 2026-06-25 |
| Governing DDR | DDR-02 (LORE `acd22c0f-7b80-440f-8b83-d3e19f5e2b72`) |
| Requirements | 01-REQUIREMENTS.md |
| Architecture | 02-ARCHITECTURE.md |
| UI Spec | 03-UI-SPEC.md |
| Supersedes | ROADMAP.md (draft — pre-QC) |
| Status | CANONICAL — post-QC |

Forge is sliced so each slice has a demonstrable exit tied to specific acceptance-criteria
IDs. Slices are ordered strictly by dependency; no slice begins until its blockers pass
their exit criteria.

The forge tracking artifact is `PROGRESS.md` in this directory. It is created at Slice 0
and updated at each slice boundary.

**Scope:** DDR-02 Mode-1 only. No snapshot store, no Mode-2 reconcile. See §Deferred.

---

## Dependency map

| Slice | Depends On |
|---|---|
| 0 — Scaffold + env | — |
| 1 — Core lift + shared infrastructure | Slice 0 |
| C2 — slugify.py | Slice 0 (before Slice 1 uses it; built in Slice 1) |
| C3 — Golden-fixture capture | Slice 0 (seed + Playwright present); blocks Slice 2 |
| 2 — ReadMe.io adapter + G1 offline regression | Slice 1, C3 |
| S2 — markdownify spike | Slice 0 (only needs venv + markdownify); blocks Slice 3 |
| S1 — Assertion harness | Slice 1 (needs emit + manifest schema); gates Slices 3 and 4 |
| 3 — htmlmd + Docusaurus adapter | Slice 1, S2 spike, S1 assertion harness |
| 4 — GitHub org adapter | Slice 1, S1 assertion harness |
| 5 — Generalization proof + cleanup | Slices 2, 3, 4 all passing their exits |

Slices 3 and 4 are independent of each other after their shared prerequisites (Slice 1,
S1, S2 for Slice 3 only). They may be worked in parallel by two engineers; a single
engineer works them sequentially (Slice 3 first, as it is the richer quality proof).

---

## Slice 0 — Scaffold + environment

**Goal:** Create the package skeleton, `pyproject.toml`, and a working venv with all
dependencies installed and Playwright's Chromium browser present.

**Depends on:** —

**Files:**
- `scraper/__init__.py` — create (empty package marker)
- `scraper/config.py` — create (stub: `pass`)
- `scraper/core.py` — create (stub: `pass`)
- `scraper/htmlmd.py` — create (stub: `pass`)
- `scraper/slugify.py` — create (stub: `pass`)
- `scraper/emit.py` — create (stub: `pass`)
- `scraper/runner.py` — create (stub: `pass`)
- `scraper/cli.py` — create (stub: `pass`)
- `scraper/adapters/__init__.py` — create (stub: `ADAPTERS = {}`)
- `scraper/adapters/base.py` — create (stub: `pass`)
- `scraper/adapters/readme_io.py` — create (stub: `pass`)
- `scraper/adapters/docusaurus.py` — create (stub: `pass`)
- `scraper/adapters/github_org.py` — create (stub: `pass`)
- `targets/askedgar.yaml` — create (stub: `platform: readme_io`)
- `targets/thatopen-docs.yaml` — create (stub: `platform: docusaurus`)
- `targets/thatopen-github.yaml` — create (stub: `platform: github_org`)
- `tests/__init__.py` — create (empty)
- `tests/fixtures/askedgar/.gitkeep` — create (placeholder; fixtures added in C3)
- `pyproject.toml` — create with `[project]` name/version, `[project.dependencies]`
  (`playwright`, `beautifulsoup4>=4.12`, `markdownify>=0.12`, `pyyaml>=6.0`), and
  `[build-system]` (setuptools)
- `.gitignore` — update to include `output/`, `.venv/`, `*.tmp`
- `PROGRESS.md` — create (forge tracking; first entry: Slice 0 in progress)

**Implementation notes:**
- Python 3.14 has no `pip` or `ensurepip` bundled. Bootstrap sequence:
  1. `python3 -m venv --without-pip .venv`
  2. `curl https://bootstrap.pypa.io/get-pip.py | .venv/bin/python3`
  3. `.venv/bin/pip install -e .`
  4. `.venv/bin/playwright install chromium`
- Document this sequence in `PROGRESS.md` for repeatability.
- All stub files are syntactically valid Python (`pass` or empty `__init__`).

**Exit criterion:**
Running the following command inside the venv exits 0 with no import errors:
```
.venv/bin/python -c "import scraper, bs4, markdownify, yaml, playwright"
```
Record the Python version and installed package versions in `PROGRESS.md`.

---

## C2 — slugify.py (built within Slice 1; described separately for clarity)

`slugify.py` is part of Slice 1's file set. It is called out separately because it is
a prerequisite consumed by both the emit layer and the runner, and its unit tests must
pass before those callers are considered done.

See Slice 1 for file ownership. The C2 designation tracks the QC finding; the
implementation lands in Slice 1.

---

## C3 — Golden-fixture capture (precondition for Slice 2)

**Goal:** Capture the three fixture files that the offline G1 regression test requires,
committing them to the repo before the seed is deleted.

**Depends on:** Slice 0 (venv + Playwright functional)

**Blocks:** Slice 2 (the G1 regression test cannot be written or run without the fixture)

**Files:**
- `tests/fixtures/askedgar/slugs.json` — create via capture script
- `tests/fixtures/askedgar/headings.json` — create via capture script
- `tests/fixtures/askedgar/seed_page.html` — create via capture script
- `seed/capture_fixtures.py` — create (one-time capture script; deleted in Slice 5 with
  the rest of `seed/`)

**Implementation notes:**
- The capture script runs `seed/scrape_askedgar_reference.py --discover` to obtain slugs,
  then runs a full single-page fetch (or iterates the slug list) to obtain heading sets.
- `seed_page.html`: save the rendered HTML of the seed URL (the sidebar/index page that
  `discover_slugs` parses) — this is the HTML that the offline regression test feeds to
  `discover_slugs` in place of a live network call.
- `slugs.json`: a JSON array of slug strings, one per discovered endpoint.
- `headings.json`: a JSON object `{slug: [heading_string, ...]}` using the keys produced
  by `extract_sections` (all keys except `_title`), lowercased and stripped exactly as
  the function produces them.
- **Network dependency:** this step requires a live connection to `askedgar.readme.io`
  and a working Playwright + Chromium installation. If the site is unreachable at capture
  time, document the dependency in `PROGRESS.md` and proceed to Slice 1 (all shared
  infrastructure can be built). Slice 2's offline regression component can still be
  scaffolded (the comparison logic is built regardless); it will simply require the
  fixture to be populated before the test can fully pass.
- Once captured, commit all three files. They are the permanent offline baseline; do not
  regenerate them on normal runs.
- **Fallback:** if `askedgar.readme.io` remains unreachable through the forge sprint,
  create minimal synthetic fixtures (2–3 slugs, matching headings) and note them as
  synthetic in a `tests/fixtures/askedgar/README.md` comment. The offline comparison
  logic is still built and tested; only the live-parity assertion is deferred.

**Exit criterion:**
All three files exist at the committed paths. Running `python -c "import json; json.load(open('tests/fixtures/askedgar/slugs.json'))"` succeeds. `seed_page.html` is a non-empty HTML file. The files are committed (not just present on disk).

---

## Slice 1 — Core lift + config + slugify + emit + adapter base + runner + CLI

**Goal:** Build all shared infrastructure: the verbatim-protected core functions lifted
from the seed, the config layer, collision-safe slug derivation, the atomic emit layer,
the adapter interface, the runner orchestration, and the CLI entry point. This slice
contains no adapter implementations but wires enough that `python -m scraper.cli --help`
runs and the runner's execution path is walkable end-to-end.

**Depends on:** Slice 0

**Files:**
- `scraper/core.py` — implement:
  - Verbatim-protected trio lifted unchanged from `seed/scrape_askedgar_reference.py`:
    `get_main`, `extract_sections`, `render_sections`. Zero modification (FR-4a).
  - Parameterized `discover_slugs(html, link_pattern="/reference/", slug_methods=None, slug_filter=None)` (FR-4b). Seed's hardcoded values become defaults.
- `scraper/config.py` — implement:
  - `TargetConfig` dataclass with all fields from architecture §Config layer.
  - `load_target(name: str) -> TargetConfig`: reads `targets/{name}.yaml`, validates
    platform against `ADAPTERS` registry, raises on unknown platform (exit 1 path).
- `scraper/slugify.py` — implement (C2):
  - `identifier_to_slug(identifier: str, platform: str) -> str`: full 5-step derivation
    per architecture §Filename derivation (lowercase, strip leading dots, replace illegal
    chars, collapse runs, 80-byte length cap with hash suffix, reserved-name suffix,
    `.md` extension, `.mdx` replacement).
  - `resolve_collisions(slugs: list[tuple[str, str]]) -> dict[str, str]`: hash-suffix
    collision resolution in discovery order per architecture §Step 4.
  - Unit tests in `tests/test_slugify.py` covering: basic sanitization, `@scope` segment,
    case-collision detection and resolution, reserved-name suffixing, length-cap with hash,
    total-path-length guard, all three platform split strategies, `.mdx` → `.md` extension
    replacement.
- `scraper/emit.py` — implement:
  - `Document` dataclass: `slug`, `title`, `body_markdown`, `metadata`.
  - `_atomic_write(path: Path, content: str) -> None`: write-to-temp-then-`os.replace`
    pattern (S3, NFR-4). See architecture §Emit layer.
  - `write_document(doc: Document, cfg: TargetConfig) -> None`: validate all non-nullable
    FR-16a fields (raise/record failure if missing), render YAML front-matter block,
    call `_atomic_write`.
  - `write_manifest(docs: list[Document], failures: list[dict], cfg: TargetConfig) -> None`:
    build manifest dict per architecture schema, call `_atomic_write` once at the end.
  - `write_all(docs, failures, cfg)`: convenience wrapper that calls `write_document`
    for each doc then `write_manifest` once.
  - Single-file mode (FR-18): when `cfg.output_mode == "single_file"`, concatenate all
    document bodies into one file (AskEdgar regression parity).
- `scraper/adapters/base.py` — implement: `Item`, `Document` (re-export from emit),
  `RunContext`, `PlatformAdapter` ABC with `discover` and `render` abstract methods
  per architecture §Adapter contract.
- `scraper/adapters/__init__.py` — implement: `ADAPTERS: dict[str, type[PlatformAdapter]]`
  registry (populated with platform name → class as adapters are built; starts empty or
  with stubs).
- `scraper/runner.py` — implement: full control flow per architecture §Control flow:
  config load, adapter resolution, optional Playwright lifecycle (`browser_if_needed`
  context manager), `discover` call with fallback handling, `resolve_collisions` call,
  `--discover` exit point (prints to stdout), `--limit` truncation, render loop with
  per-item error capture (NFR-4), stderr progress output per 03-UI-SPEC.md, `write_all`
  call.
- `scraper/cli.py` — implement: `argparse` entry point with `--target`, `--discover`,
  `--slug`/`--single` (aliases), `--no-discover`, `--limit N`; mutual exclusion
  enforcement (`--discover` + `--slug` → exit 2); delegates to `runner.run(args)`.
  Exit code mapping per 03-UI-SPEC.md §Exit codes.
- `targets/askedgar.yaml` — implement with all `readme_io` options from architecture
  §Config layer (seed_url, base_url, link_pattern defaults, fallback_slugs, etc.).
- `tests/test_slugify.py` — create: unit tests for all slugify cases listed above.
- `tests/test_emit.py` — create: unit tests for `_atomic_write` (interruption safety,
  parent mkdir), `write_document` (front-matter validation, YAML roundtrip), and
  `write_manifest` (count equality, JSON validity).
- `PROGRESS.md` — update: Slice 1 entry.

**Implementation notes:**
- `scraper/adapters/__init__.py` ADAPTERS registry starts empty in this slice. The
  runner will fail at `ADAPTERS[cfg.platform]` until the adapter slices populate it. This
  is acceptable; the CLI and runner code paths are fully implemented.
- `get_main`, `extract_sections`, and `render_sections` are copied character-for-character
  from the seed. Add a comment `# VERBATIM — do not modify (FR-4a, DDR-01 D2)` above each.
  Do not refactor, rename, or alter signatures.
- For `emit.write_document`, the front-matter block is rendered as YAML using `pyyaml`
  (`yaml.dump(metadata, default_flow_style=False, allow_unicode=True)`), wrapped in
  `---\n...\n---\n`.
- The runner's `browser_if_needed` context manager: if `adapter.requires_browser` is
  False, it yields `None` for `page`.

**Exit criteria (all must pass):**
1. `python -m scraper.cli --help` exits 0 and shows all flags.
2. `python -m scraper.cli` (no args) exits 2.
3. `python -m scraper.cli --target nonexistent` exits 1 with the expected error message.
4. `pytest tests/test_slugify.py` passes — all slugify unit tests green.
5. `pytest tests/test_emit.py` passes — all emit unit tests green (atomic write, manifest
   count equality, front-matter YAML round-trip).
6. C2 satisfied: `identifier_to_slug` and `resolve_collisions` pass their full test suite
   including collision detection, hash suffix, reserved names, and path-length guard.

---

## S2 — markdownify `code_language_callback` spike (precondition for Slice 3)

**Goal:** Confirm whether the installed version of `markdownify` exposes
`code_language_callback` as a kwarg to `markdownify()` and emits `` ```lang `` fenced
blocks from `class="language-x"` elements. If it does not, confirm that subclassing
`MarkdownConverter` and overriding `convert_pre`/`convert_code` achieves the same result.
Record the finding so Slice 3's `htmlmd.py` build uses the confirmed approach from the
start.

**Depends on:** Slice 0 (venv + markdownify installed)

**Blocks:** Slice 3 (htmlmd.py must not be written until the approach is confirmed)

**Files:**
- `docs/specs/multi-platform-adapters/S2-spike-result.md` — create: record markdownify
  version, whether `code_language_callback` is available, test HTML used, rendered output,
  and the confirmed approach (direct kwarg or subclass). One page; not a full spec.

**Implementation notes:**
- Spike test: construct a minimal BeautifulSoup snippet with `<pre><code class="language-typescript">const x = 1;</code></pre>` and call `markdownify(str(snippet), code_language_callback=...)`. If `TypeError: unexpected keyword argument`, fall back to the subclass approach.
- The subclass fallback: override `convert_pre` (or `convert_code`) in a `MarkdownConverter` subclass to inspect `el.get("class")` and emit the language token in the fence opening.
- **Time-box:** 30 minutes. This is a confirmation step, not an investigation. One of the two approaches will work; record which one.

**Exit criterion:**
`S2-spike-result.md` exists and states one of:
- "confirmed: `code_language_callback` kwarg works in markdownify X.Y.Z" — with sample
  output showing `` ```typescript `` in the rendered markdown, OR
- "confirmed: subclass approach required; see `convert_pre` override snippet" — with the
  override code snippet committed in the spike result file.

Slice 3 must not begin until this file exists and states a confirmed approach.

---

## S1 — Assertion harness (gates Slices 3 and 4)

**Goal:** Implement the mechanizable AC-1 quality-gate checks as a runnable test module
that can be applied to any adapter's output directory. This harness is what proves AC-1a,
AC-1b, AC-1c, and AC-1d are satisfied by the Docusaurus and GitHub org adapter outputs.

**Depends on:** Slice 1 (needs the manifest schema and front-matter format to be settled)

**Blocks:** Slice 3 exit criterion, Slice 4 exit criterion (both require the harness to
pass over their output)

**Files:**
- `tests/test_output_quality.py` — create: parametrizable assertion harness with:
  - `assert_no_chrome_bleed(md_path)`: scans a markdown file for AC-1a denylist strings
    (case-insensitive): `"Skip to main content"`, `"Edit this page"`, `"On this page"`,
    `"Table of Contents"`, and `© \d{4}` pattern. Fails on any match.
  - `assert_code_fence_present(md_path, source_html_path=None)`: if the corresponding
    source HTML contained a `<code>` or `<pre>` element, the output markdown must contain
    at least one triple-backtick fence. When `source_html_path` is not provided (typical
    for Docusaurus), checks only that the output file contains at least one fence if any
    `<code>` hint can be inferred from the content.
  - `assert_frontmatter_valid(md_path, platform)`: parses the YAML front-matter block,
    asserts parsing succeeds, asserts all non-nullable FR-16a fields for the given platform
    are present and non-empty. Nullable fields must be present (not absent).
  - `assert_manifest_consistent(output_dir)`: loads `manifest.json`, asserts valid JSON,
    asserts `document_count == len(documents) == count of .md files in output_dir`.
  - A pytest fixture `output_dir_checker(output_dir, platform)` that calls all four
    assertions over every file in the directory. Used by Slice 3 and Slice 4 tests.
- `PROGRESS.md` — update.

**Implementation notes:**
- The harness does not run a scraper target itself; it operates on an existing
  `output/<target>/` directory. It is invoked by test functions in Slice 3 and Slice 4
  that run a limited scrape (`--limit 5`) and then call the checker.
- AC-1e (human spot-check) is not automated; it is noted in `PROGRESS.md` by the engineer
  as a manual verification step.

**Exit criterion:**
`pytest tests/test_output_quality.py` passes on a known-good fixture directory (use any
small set of hand-crafted markdown files with valid front-matter and no chrome bleed).
The harness must also correctly fail on a file that contains `"Skip to main content"` and
on a file with missing front-matter fields. These negative tests must be included.

---

## Slice 2 — ReadMe.io adapter + G1 offline regression

**Goal:** Implement the `readme_io` adapter (wrapping `core.py`), complete the
`askedgar.yaml` target config, and build the offline G1 regression test that proves
AC-3a, AC-3b, and AC-3c against the committed fixture.

**Depends on:** Slice 1 (core, runner, emit all functional), C3 (golden fixture committed)

**Files:**
- `scraper/adapters/readme_io.py` — implement:
  - `ReadMeIoAdapter(PlatformAdapter)` with `requires_browser = True`.
  - `discover(ctx)`: calls `core.discover_slugs` with `link_pattern`, `slug_methods`,
    `slug_filter` from `ctx.config.options`; applies `discovery_min_slugs` threshold and
    `fallback_slugs` fallback; raises on zero slugs with no fallback (fast-fail per
    03-UI-SPEC.md §Fast-fail).
  - `render(ctx, item)`: Playwright fetch (`networkidle` + settle), calls
    `core.get_main` → `core.extract_sections` → `core.render_sections`; assembles
    `Document` with FR-16a metadata (platform-specific nullable fields set to `None`).
- `scraper/adapters/__init__.py` — update: add `"readme_io": ReadMeIoAdapter` to
  `ADAPTERS` registry.
- `targets/askedgar.yaml` — finalize: all options from architecture §Config layer
  (`seed_url`, `base_url`, `link_pattern: /reference/`, `discovery_min_slugs`,
  `fallback_slugs`, `output_mode: single_file`, `polite_delay_seconds: 0.8`).
- `tests/test_g1_regression.py` — implement:
  - `test_slug_set_identity`: loads `tests/fixtures/askedgar/slugs.json`, instantiates
    `ReadMeIoAdapter`, calls `discover_slugs` against the committed
    `tests/fixtures/askedgar/seed_page.html` (no network call), compares discovered slug
    set to fixture set: exact set equality (AC-3a). Order differences permitted.
  - `test_heading_sets_match`: loads `tests/fixtures/askedgar/headings.json`. For each
    slug in the fixture, asserts the heading set produced by `extract_sections` (on a
    locally-stored or minimal stub HTML for each slug) matches the fixture's heading set
    for that slug (AC-3b). If full per-slug HTML is not in the fixture, this test uses a
    mock approach for the heading comparison.
  - Both tests have **zero network dependency** (AC-3c). Mark any test that would require
    network access with `pytest.mark.network` and exclude from the default run.
- `PROGRESS.md` — update.

**Implementation notes:**
- The offline `test_slug_set_identity` test passes `seed_page.html`'s contents directly
  to `discover_slugs`; it does not call `adapter.discover(ctx)` with a live Playwright
  page. This is the offline contract.
- For `test_heading_sets_match`: if the fixture capture in C3 produced per-slug heading
  sets from the seed's actual output, use those. If the fixture is minimal/synthetic,
  the test asserts structural consistency of `extract_sections`' output shape only; note
  this limitation in `PROGRESS.md`.
- The live site check (does `--target askedgar --discover` match the fixture?) is a
  manual verification step documented in `PROGRESS.md`, not an automated CI test. CI runs
  only the offline test.

**Exit criteria (all must pass):**
1. `pytest tests/test_g1_regression.py` passes offline (no network). Both
   `test_slug_set_identity` and `test_heading_sets_match` green. (AC-3a, AC-3b, AC-3c)
2. `python -m scraper.cli --target askedgar --discover` runs and lists slugs (requires
   live `askedgar.readme.io` and Playwright; document result in `PROGRESS.md`).
3. If the live site is reachable: `python -m scraper.cli --target askedgar --limit 1`
   produces a valid `.md` file and `manifest.json`; front-matter validates per FR-16a.
   Document result in `PROGRESS.md`. If unreachable, this exit item is satisfied by
   the offline test alone.

---

## Slice 3 — htmlmd + Docusaurus adapter + AC-1 assertion harness run

**Goal:** Build `htmlmd.py` (structure-preserving HTML-to-markdown converter) and the
`docusaurus` adapter. Run the AC-1 assertion harness over the Docusaurus proving target.

**Depends on:** Slice 1, S2 spike (confirmed approach), S1 assertion harness

**Files:**
- `scraper/htmlmd.py` — implement:
  - `_strip_noise(container)`: removes from the container in-place: `nav`, `aside`,
    `footer`, `script`, `style` elements; elements with text exactly matching
    `"Edit this page"` or `"Table of Contents"` or `"Skip to main content"`; any element
    matching `"© \d{4}"`. (AC-1a precondition.)
  - `_code_language(el) -> str`: extracts `language-<token>` from element CSS classes
    (Prism.js `language-*` convention).
  - `to_markdown(container) -> str`: calls `_strip_noise`, then calls `markdownify` with
    `heading_style="ATX"`, the confirmed `code_language_callback` approach (from S2 spike),
    and `strip=["script", "style"]`. Returns clean markdown.
  - If the S2 spike determined subclassing is required, the `MarkdownConverter` subclass
    lives in this file.
- `scraper/adapters/docusaurus.py` — implement:
  - `DocusaurusAdapter(PlatformAdapter)` with `requires_browser = False`.
  - `discover(ctx)`: fetches `ctx.config.options["sitemap_url"]` via `ctx.http_get`,
    parses `<loc>` URLs from XML, applies `include_patterns`/`exclude_patterns` glob
    filtering (default: acquire all). Returns `list[Item]` with `identifier = URL path`.
    Fast-fail on zero URLs (exit 1 path per 03-UI-SPEC.md §Fast-fail).
  - `render(ctx, item)`: fetches the full URL via `ctx.http_get`, parses with
    BeautifulSoup (`html.parser`), selects content container in priority order
    (`article`, `.theme-doc-markdown`, `main`), calls `htmlmd.to_markdown(container)`.
    On missing container: raises (recorded as failure, NFR-4). Derives `package` from
    `/api/@scope/pkg/` path pattern, `breadcrumb` from URL path segments. Assembles
    `Document` with FR-16a metadata.
- `scraper/adapters/__init__.py` — update: add `"docusaurus": DocusaurusAdapter`.
- `targets/thatopen-docs.yaml` — finalize: `platform: docusaurus`, `sitemap_url`,
  `base_url: https://docs.thatopen.com`, `content_selectors` defaults, `polite_delay_seconds: 0.8`.
- `tests/test_htmlmd.py` — create: unit tests for:
  - `_strip_noise`: verifies denylist elements are removed; clean elements are kept.
  - `_code_language`: extracts language token from `language-ts`, `language-python`;
    returns `""` when no matching class.
  - `to_markdown`: given a minimal HTML snippet with a `<pre><code class="language-typescript">`,
    output contains `` ```typescript `` fence (AC-1b precondition).
  - `to_markdown`: given HTML with `"Skip to main content"` element, output does not
    contain that string (AC-1a precondition).
- `tests/test_docusaurus_ac1.py` — create:
  - `test_ac1_limited_run`: runs `python -m scraper.cli --target thatopen-docs --limit 5`
    as a subprocess (or calls runner directly), then calls the S1 assertion harness
    `output_dir_checker("output/thatopen-docs", "docusaurus")`. Asserts AC-1a, AC-1b,
    AC-1c, AC-1d all pass. Mark with `pytest.mark.network`.
  - Note for AC-1e (human spot-check): documented in `PROGRESS.md` as a manual step.
- `PROGRESS.md` — update.

**Implementation notes:**
- `htmlmd.py` uses the approach confirmed by the S2 spike. If the spike confirmed the
  direct `code_language_callback` kwarg, use it exactly as shown in architecture §htmlmd.
  If the spike confirmed subclassing, use the subclass. Do not attempt both.
- `_strip_noise` must be applied before `markdownify` converts the container, because
  markdownify will otherwise convert noise elements to markdown text before they can be
  stripped.
- For `breadcrumb` derivation: join the non-empty URL path segments (excluding the first
  empty segment from the leading `/`) with ` / ` as separator. Strip query and fragment.

**Exit criteria (all must pass):**
1. `pytest tests/test_htmlmd.py` passes (AC-1a and AC-1b preconditions confirmed in
   isolation).
2. `pytest tests/test_docusaurus_ac1.py -m network` passes (requires live
   `docs.thatopen.com`): 5-document limited run produces output that clears AC-1a, AC-1b,
   AC-1c, AC-1d. Document result in `PROGRESS.md`. (AC-1a, AC-1b, AC-1c, AC-1d)
3. A full run `python -m scraper.cli --target thatopen-docs` completes politely (~504
   documents at 0.8 s delay). Document completion in `PROGRESS.md`. (AC-1e manual
   spot-check recorded.)
4. S1 assertion harness passes over full output: `output_dir_checker` green on the
   complete `output/thatopen-docs/` directory.

---

## Slice 4 — GitHub org adapter

**Goal:** Implement the `github_org` adapter targeting `github.com/ThatOpen`. Run the
AC-1 and AC-2 assertion checks.

**Depends on:** Slice 1, S1 assertion harness (Slice 3 is not a strict dependency but
should be complete or in progress; Slice 4 is independent of Slice 3)

**Files:**
- `scraper/adapters/github_org.py` — implement:
  - `GitHubOrgAdapter(PlatformAdapter)` with `requires_browser = False`.
  - `discover(ctx)`: GitHub API pagination over `/orgs/{org}/repos?per_page=100`;
    filters `archived: false` unless `ctx.config.options.get("include_archived")`;
    per repo: reads `default_branch` from API response (never hardcode `main`, FR-11);
    calls Git Trees API `GET /repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1`;
    filters paths per FR-12 (`README*`, `*.md`/`*.mdx` under `docs/`/`documentation/`,
    top-level `*.md`); fetches head commit SHA via `/repos/{owner}/{repo}/commits/{default_branch}`;
    returns `list[Item]` with `identifier = "repo:path"` and
    `extra = {"repo": str, "default_branch": str, "commit_sha": str | None}`.
  - `render(ctx, item)`: fetches raw markdown via
    `https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}`;
    prepends front-matter (FR-16a: `repo`, `git_ref = "{branch}@{sha}"` or `null` if
    `commit_sha` is None, `breadcrumb` from path segments); adds `# Title` heading if
    none present; returns `Document`.
  - Token source: `ctx.token` (from `gh auth token` subprocess or `GITHUB_TOKEN` env var,
    resolved in runner); passed as `Authorization: Bearer {token}` header on all API calls.
    If both sources unavailable, continue without auth (rate-limited to 60 req/hr);
    log warning to stderr.
- `scraper/adapters/__init__.py` — update: add `"github_org": GitHubOrgAdapter`.
- `targets/thatopen-github.yaml` — finalize: `platform: github_org`, `org: ThatOpen`,
  `include_archived: false`, `polite_delay_seconds: 0.8`.
- `tests/test_github_org_ac2.py` — create:
  - `test_ac2_full_run`: runs `--target thatopen-github` (or a limited run with
    `--limit 10`), then asserts: `repo` and `git_ref` keys present and non-null in every
    output file's front-matter; `output_dir_checker` (S1 harness) passes for AC-1a,
    AC-1c, AC-1d; manifest `document_count == file_count`. Mark with `pytest.mark.network`.
  - Note: AC-1b (code-fence) is less applicable to raw markdown passthrough; test asserts
    that files containing triple-backtick fences in source retain them (no regression).
- `PROGRESS.md` — update.

**Implementation notes:**
- `git_ref`: if the commits endpoint fails or returns no SHA, set `git_ref = None` in
  front-matter. The key must still be present (not absent).
- Path filter for FR-12: `README*` matches `README.md`, `README.rst`, `README` etc. at
  any depth. `docs/` and `documentation/` are case-sensitive matches. Top-level `*.md`
  means depth == 1 (no `/` in the path).
- `breadcrumb` for GitHub org: `"{repo} / {path segments joined with ' / '}"`. Strip
  the filename extension from the last segment in the breadcrumb.
- The runner resolves the GitHub token before constructing `RunContext`: try
  `subprocess.run(["gh", "auth", "token"], capture_output=True)` first; fall back to
  `os.environ.get("GITHUB_TOKEN")`. Store result in `RunContext.token`.

**Exit criteria (all must pass):**
1. `pytest tests/test_github_org_ac2.py -m network` passes (requires GitHub API access
   and `gh` auth or `GITHUB_TOKEN`): `repo` and `git_ref` present and non-null in every
   output file; AC-1a, AC-1c, AC-1d pass; manifest count equals file count. (AC-2)
2. Full run `python -m scraper.cli --target thatopen-github` completes and produces
   per-repo documentation markdown using each repo's actual `default_branch`. Document
   result in `PROGRESS.md`. (AC-2)
3. S1 assertion harness `output_dir_checker` passes over complete output directory.

---

## Slice 5 — Generalization proof + README reframe + seed deletion

**Goal:** Demonstrate AC-4 (no-code-change generalization), reframe the README to the
adapter-based framing, and delete the seed once G1 is confirmed passing.

**Depends on:** Slices 2, 3, and 4 all at their exit criteria. The seed must not be
deleted until Slice 2's G1 exit criterion is confirmed.

**Files:**
- `targets/<second-target>.yaml` — create: a second target of an existing platform using
  only a YAML file with no code change. Suggested: a second ReadMe.io target (e.g. a
  different public readme.io-hosted API reference), or a narrowed Docusaurus target with
  different `include_patterns`. Name is at the engineer's discretion.
- `README.md` — update: reframe from "ReadMe.io scraper" to "multi-platform documentation
  scraper" with the adapter-based framing per DDR-02. Include: supported platforms
  (readme_io, docusaurus, github_org), invocation pattern, target config location,
  venv bootstrap sequence (from Slice 0 notes in `PROGRESS.md`), and the honest scope
  boundary note (Mode-1 acquisition only; no snapshot/drift).
- `seed/` — delete entire directory (all files). Precondition: Slice 2 G1 exit criterion
  confirmed passing and documented in `PROGRESS.md`. The golden fixtures in
  `tests/fixtures/askedgar/` survive; only `seed/` is removed.
- `PROGRESS.md` — final update: all slice entries complete; manual AC-1e and AC-2
  spot-check results recorded.

**Implementation notes:**
- The AC-4 demonstration: add `targets/<second-target>.yaml`, run
  `python -m scraper.cli --target <second-target> --limit 3`, show it works without any
  `.py` file change. Commit the YAML. The commit diff must show only the new YAML file.
- The README reframe does not need to document every flag in detail — the CLI spec
  (`03-UI-SPEC.md`) is the authoritative reference. The README covers purpose, setup, and
  the key invocation patterns.

**Exit criteria (all must pass):**
1. Adding `targets/<second-target>.yaml` and running a limited scrape against it requires
   zero code changes. The diff shows only the YAML file. (AC-4)
2. `README.md` accurately describes the adapter-based tool; the seed framing is removed.
3. `seed/` directory is absent from the repo. All tests still pass without it.
4. All acceptance criteria satisfied:
   - AC-1a, AC-1b, AC-1c, AC-1d: S1 harness passes on Docusaurus + GitHub org outputs.
   - AC-1e: human spot-check recorded in `PROGRESS.md`.
   - AC-2: recorded in `PROGRESS.md`.
   - AC-3a, AC-3b, AC-3c: `pytest tests/test_g1_regression.py` green offline.
   - AC-4: demonstrated in this slice.
5. `pytest` (full suite, excluding `pytest.mark.network`) passes with no failures.

---

## Sequencing summary

```
Slice 0 (scaffold/env)
  ├── C3 (fixture capture) ──────────────────────┐
  ├── S2 (markdownify spike) ────────────────┐   │
  └── Slice 1 (core + infra + C2 slugify)   │   │
        ├── S1 (assertion harness)           │   │
        │     ├── Slice 3 (htmlmd + Docu) ←─┘   │
        │     └── Slice 4 (GitHub org)           │
        └── Slice 2 (ReadMe.io + G1) ←──────────┘
              └── [G1 confirmed] → Slice 5 (proof + cleanup)
                    ← also needs Slices 3 and 4 at exit
```

Parallelizable after Slice 1 + S1 + S2 (spike): Slices 3 and 4 are independent of each
other. A two-engineer team can work them simultaneously. A single engineer works Slice 3
then Slice 4 (Slice 3 is the richer quality proof).

C2 (slugify) is built inside Slice 1 and does not add a separate slice. Its unit tests
must pass before Slice 1 is considered done.

S3 (atomic emit via `os.replace`) is implemented inside Slice 1 (`emit.py`) and tested
in `tests/test_emit.py`. It does not add a separate slice.

---

## Deferred (not this roadmap — DDR-02 scope boundary)

- Mode-2 reconcile: stateful snapshot store, drift detection, prior-scrape pointer.
- G2 gate: second structurally-different ReadMe.io target (DDR-01 scope; AC-4 covers
  no-code-change generalization across platforms instead).
- Downstream concerns: chunking, embedding, vector store ingestion (separate tool).
- Dedup of `engine_docs` ↔ `docs.thatopen.com` overlap (`git_ref` enables this
  downstream; not performed here).
- Other platform adapters: Swagger/OpenAPI, GitBook, Mintlify, other Docusaurus instances.
- Private GitHub repo access.
- Snapshot retention or run history (each run overwrites `output/<target>/`).
- `--verbose` / `--quiet` CLI flags (not in FR-19).
- Hand-maintained-doc reconciliation mode (DDR-01 D4).
- Any Mode-2 or Mode-3 capability (DDR-02 scope boundary; NFR-6).

---

## File ownership matrix

| File | Slice |
|---|---|
| `scraper/__init__.py` | Slice 0 |
| `pyproject.toml` | Slice 0 |
| `.gitignore` | Slice 0 |
| `PROGRESS.md` | Slice 0 (created); all slices (updated) |
| `scraper/core.py` | Slice 1 |
| `scraper/config.py` | Slice 1 |
| `scraper/slugify.py` | Slice 1 (C2) |
| `scraper/emit.py` | Slice 1 (S3) |
| `scraper/adapters/base.py` | Slice 1 |
| `scraper/adapters/__init__.py` | Slice 1 (stub); Slice 2, 3, 4 (add entry each) |
| `scraper/runner.py` | Slice 1 |
| `scraper/cli.py` | Slice 1 |
| `tests/test_slugify.py` | Slice 1 |
| `tests/test_emit.py` | Slice 1 |
| `targets/askedgar.yaml` | Slice 0 (stub); Slice 1 (full draft); Slice 2 (finalize) |
| `targets/thatopen-docs.yaml` | Slice 0 (stub); Slice 3 (finalize) |
| `targets/thatopen-github.yaml` | Slice 0 (stub); Slice 4 (finalize) |
| `tests/fixtures/askedgar/slugs.json` | C3 |
| `tests/fixtures/askedgar/headings.json` | C3 |
| `tests/fixtures/askedgar/seed_page.html` | C3 |
| `seed/capture_fixtures.py` | C3 (created); Slice 5 (deleted with `seed/`) |
| `scraper/adapters/readme_io.py` | Slice 2 |
| `tests/test_g1_regression.py` | Slice 2 |
| `docs/specs/multi-platform-adapters/S2-spike-result.md` | S2 |
| `tests/test_output_quality.py` | S1 |
| `scraper/htmlmd.py` | Slice 3 |
| `scraper/adapters/docusaurus.py` | Slice 3 |
| `tests/test_htmlmd.py` | Slice 3 |
| `tests/test_docusaurus_ac1.py` | Slice 3 |
| `scraper/adapters/github_org.py` | Slice 4 |
| `tests/test_github_org_ac2.py` | Slice 4 |
| `targets/<second-target>.yaml` | Slice 5 |
| `README.md` | Slice 5 |
| `seed/` (entire directory) | Slice 5 (deleted) |
