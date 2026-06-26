# PROGRESS — Multi-platform adapter forge sprint

| Field | Value |
|---|---|
| Branch | feature/multi-platform |
| Spec dir | docs/specs/multi-platform-adapters/ |
| Started | 2026-06-25 |
| Last updated | 2026-06-25 |

---

## Slice checklist

| Slice | Name | Status |
|---|---|---|
| 0 | Scaffold + environment bootstrap | DONE |
| 1 | Core lift + config + slugify + emit + adapter base + runner + CLI | DONE |
| 2 | ReadMe.io adapter (seed parity) + G1 fixture capture | TODO |
| 3 | htmlmd + slugify + emit layers | TODO |
| 4 | Docusaurus adapter | TODO |
| 5 | GitHub org adapter | TODO |

---

## Slice 3 — Fix Attempts

### Fix Attempt 2 (2026-06-25) — safety guard (BLOCKING)

**Issue — inadequate rmtree guard (QC FAIL)**

Root cause: the original guard in runner.py only blocked literal `"/"` and `"."` string
comparisons on an already-resolved path (the `"."` check was dead code); there was no
containment check. config.py read `output_dir` with zero validation. A hostile
`output_dir` of `""`, `"."`, `".."`, `"/etc"`, or any absolute path would cause rmtree to
delete the repo root or an arbitrary directory.

Fix — defence in depth, two layers:

**Layer 1 — config.py (fast-fail at load time):**

In `load_target`, after reading `output_dir` (~line 81), added validation that rejects
the value with `sys.exit(1)` if it is:
- Empty or whitespace-only
- An absolute path (`Path(output_dir).is_absolute()`)
- Exactly `"."`
- Contains any `".."` path component

Error messages are styled the same as existing `load_target` errors (print to stderr,
exit 1). This guarantees `output_dir` is always a clean relative path before any
downstream code runs.

**Layer 2 — runner.py (belt-and-suspenders, before rmtree):**

Replaced the old inadequate string comparison with a containment check:
1. `_cwd = Path.cwd().resolve()` — canonical cwd
2. `_resolved = (_cwd / cfg.output_dir).resolve()` — resolve against cwd
3. Guard: `if _resolved == _cwd or not _resolved.is_relative_to(_cwd)` → `return 1`
4. Only if guard passes: `shutil.rmtree(_resolved)` (if exists) then `mkdir`.

The `shutil` import was moved inside the guard block. `--discover` placement unchanged
(still read-only; guard fires after discover, before render, per spec).

**Regression tests (tests/test_config_safety.py):**

- config rejects: `""`, `"."`, `"/abs/path"`, `"../escape"`, `"a/../../b"` — each raises
  `SystemExit(1)`.
- config accepts: `"output/x"` (loads fine, `cfg.output_dir == "output/x"`).
- config default: absent `output_dir` yields `"output/{name}"`.
- runner guard: monkeypatched cfg with `output_dir="../escape"` → `run()` returns 1,
  `shutil.rmtree` not called.

**Verification results:**

1. `pytest -q` → `162 passed, 2 deselected, 0 failed` (154 prior + 8 new safety tests).
2. `pytest -m network tests/test_docusaurus_ac1.py -v` → `1 passed` (AC-1 still green;
   regeneration still works for a legitimate relative output_dir).
3. Rejection demonstration:
   - `output_dir: "."` → `Error: ... must not be "." (would wipe the working directory)`
     then `SystemExit(1)`.
   - `output_dir: "/tmp/x"` → `Error: ... must be a relative path, got absolute: "/tmp/x"`
     then `SystemExit(1)`.

---

### Fix Attempt 1 (2026-06-25)

**Issue — output directory accumulates files across runs (AC-1d)**

Root cause: the runner wrote new documents and a new manifest into the target output
directory without first clearing it. A prior `--slug` run could leave extra `.md`
files behind, so the manifest `document_count` from the current run no longer matched
the actual `.md` file count on disk (AC-1d violation).

Fix: in `scraper/runner.py`, immediately before the render loop (after the
`--discover` exit point, so `--discover` remains non-destructive), added a
regeneration block that:
1. Resolves `cfg.output_dir` to an absolute path under the project root.
2. Guards against operating on `.` or `/` (safety check on the resolved path).
3. If the directory exists, calls `shutil.rmtree` on it (scoped to the target's
   own output dir only).
4. Recreates the directory with `mkdir(parents=True, exist_ok=True)`.

This ensures every write-mode run (full, `--limit`, `--slug`) starts with a clean
slate. The `--discover` path returns before this block and is unaffected.

**Verification results:**

1. Clean slate then `--limit 5`:
   - Removed `output/thatopen-docs/`, ran `--limit 5` → 3 documents, 2 failures.
   - `pytest -m network tests/test_docusaurus_ac1.py -v` → `1 passed` (AC-1d passes).

2. Re-run idempotency (`--limit 5` again):
   - Dir still has exactly 3 `.md` files (same docs, no accumulation).
   - AC-1d test → `1 passed`.

3. `--slug` after `--limit` run:
   - `--slug https://docs.thatopen.com/api/@thatopen/components-front/classes/Angle`
   - Dir regenerated to 1 `.md` file; manifest `document_count=1`. No accumulation.

4. Offline suite: `pytest -q` → `154 passed, 2 deselected` (0 failures).

---

## Slice 1 — Fix Attempts

### Fix Attempt 1 (2026-06-25)

**Issue 1 — total-path 200-byte guard not implemented correctly (slugify.py)**

Root cause: the guard's `available` calculation set a minimum of 1 byte for the
last segment's stem, but when prefix segments alone already exceeded the 200-byte
budget, the resulting path (`prefix + "/" + 1_char + "_hash.md"`) was still 217
bytes. The degenerate case (prefix > 189 bytes) was not handled.

Fix: rewrote Step 5 in `identifier_to_slug` to handle both the normal case
(available >= 0: truncate stem to fit) and the degenerate case (prefix already
exceeds budget: truncate the prefix itself to leave room for the hash suffix).
Result is always <= 200 bytes. All 58 slugify tests pass.

**Issue 2 — git_ref non-null enforcement missing for github_org (emit.py)**

Root cause: `_REQUIRED_KEYS` (which includes `git_ref`) was defined but never
used in the validation loop; only `_REQUIRED_NON_NULLABLE` was checked, and
`git_ref` was absent from that set. A `github_org` Document with `git_ref=None`
passed `write_document` silently.

Fix: added a platform-specific check in `write_document` — after the
`_REQUIRED_NON_NULLABLE` loop, raises `ValueError('missing required field
"git_ref"')` if `platform == "github_org"` and `git_ref` is None. Added comment
noting that the Slice 4 github_org adapter must record commits-endpoint failures
as NFR-4 FAILURE items rather than passing null git_ref to emit.

**Coupled test marker update (tests/test_emit.py)**

Removed `@pytest.mark.xfail(strict=True)` from
`TestWriteDocumentValidation::test_github_org_requires_git_ref_non_null`. The
test now runs as a live assertion and passes.

**Pytest result:** 93 passed, 0 failed, 0 xfail, 0 xpass.

**CLI exit codes:** --help=0, no-args=2, --target nonexistent=1. All confirmed.

---

## Slice 1 — Core lift + config + slugify + emit + adapter base + runner + CLI

**Status:** DONE

**Completed:** 2026-06-25

### Files created / modified

- `scraper/core.py` — verbatim-protected trio (`get_main`, `extract_sections`, `render_sections`) copied character-for-character from seed, each preceded by `# VERBATIM — do not modify (FR-4a, DDR-01 D2)` comment. Parameterized `discover_slugs(html, link_pattern, slug_methods, slug_filter)` with seed defaults (FR-4b).
- `scraper/config.py` — `TargetConfig` dataclass (all fields per ARCH §Config layer); `load_target(name)` reads `targets/{name}.yaml`, validates platform against ADAPTERS, raises on unknown (exit 1 path).
- `scraper/slugify.py` — `identifier_to_slug(identifier, platform)` full 5-step derivation (lowercase, strip dots, illegal char replace, collapse runs, 80-byte cap + hash suffix, reserved names, `.md` extension, `.mdx` replacement). `resolve_collisions(list[(identifier, base_slug)]) -> dict` 8-hex SHA-256 suffix on collision.
- `scraper/emit.py` — `Document` dataclass; `_atomic_write` (tempfile.mkstemp + os.replace); `write_document` (FR-16a field validation, YAML front-matter via `yaml.dump`, `---\n...\n---\n`); `write_manifest` (per ARCH schema, written once atomically); `write_all`; single_file mode (FR-18).
- `scraper/adapters/base.py` — `Item`, `RunContext`, `PlatformAdapter` ABC (`name`, `requires_browser=False`, abstract `discover`/`render`); re-exports `Document` from emit.
- `scraper/adapters/__init__.py` — `ADAPTERS: dict[str, type[PlatformAdapter]] = {}` registry; starts empty this slice (acceptable per spec).
- `scraper/runner.py` — full control flow per ARCH §Control flow: config load, adapter resolve, `_browser_if_needed` context manager, discover with fallback, `resolve_collisions`, `--discover` stdout exit, `--limit` truncation, render loop with per-item try/except failure capture (NFR-4), stderr progress per UI-SPEC, `write_all`.
- `scraper/cli.py` — argparse: `--target` (required), `--discover`, `--slug`/`--single` (alias), `--no-discover`, `--limit N`; mutual exclusion (`--discover` + `--slug` → exit 2); exit-code mapping per UI-SPEC; delegates to `runner.run(args)`.
- `targets/askedgar.yaml` — added `platform: readme_io`, `output_dir`, `output_mode: single_file`; moved all platform-specific keys under `options:`; all 30 fallback_slugs and all original values preserved loss-free.

### Exit criteria results

```
1. .venv/bin/python -m scraper.cli --help     → exit 0, shows all flags
2. .venv/bin/python -m scraper.cli            → exit 2 (missing --target)
3. .venv/bin/python -m scraper.cli --target nonexistent → exit 1: Error: target "nonexistent" not found. Expected targets/nonexistent.yaml
4. .venv/bin/python -c "import scraper.core, scraper.config, ..." → exit 0
```

All 4 source-only exit criteria pass.

### Deviations from spec

1. **ADAPTERS empty**: `askedgar` target fails with `Error: unknown platform "readme_io" in targets/askedgar.yaml` (exit 1) when run. Expected and acceptable per roadmap note: adapters are populated in subsequent slices.
2. **Exit criteria 4 and 5** (pytest tests) are test-writer scope — not implemented here per task scope.

---

## Slice 0 — Scaffold + environment bootstrap

**Status:** IN_PROGRESS

**Completed:** 2026-06-25

### Files created

- `scraper/__init__.py` — empty package marker
- `scraper/config.py` — stub (`pass`)
- `scraper/core.py` — stub (`pass`)
- `scraper/htmlmd.py` — stub (`pass`)
- `scraper/slugify.py` — stub (`pass`)
- `scraper/emit.py` — stub (`pass`)
- `scraper/runner.py` — stub (`pass`)
- `scraper/cli.py` — stub (`pass`)
- `scraper/adapters/__init__.py` — stub (`ADAPTERS = {}`)
- `scraper/adapters/base.py` — stub (`pass`)
- `scraper/adapters/readme_io.py` — stub (`pass`)
- `scraper/adapters/docusaurus.py` — stub (`pass`)
- `scraper/adapters/github_org.py` — stub (`pass`)
- `targets/thatopen-docs.yaml` — stub (`platform: docusaurus`)
- `targets/thatopen-github.yaml` — stub (`platform: github_org`)
- `tests/__init__.py` — empty
- `tests/fixtures/askedgar/.gitkeep` — placeholder
- `pyproject.toml` — project config + deps
- `.gitignore` — added `*.tmp`

**Note:** `targets/askedgar.yaml` was NOT touched (contains ground-truth values).

### Bootstrap sequence

Ubuntu 26.04 LTS ships Python 3.14.4, which has no bundled `pip` or `ensurepip`.
The following sequence was used and must be repeated to recreate the venv:

```sh
# 1. Create venv without pip
python3 -m venv --without-pip .venv

# 2. Bootstrap pip via get-pip.py
curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python3

# 3. Install the package and all dependencies
.venv/bin/pip install -e .

# 4. Install Playwright Chromium browser
#    IMPORTANT: Ubuntu 26.04 is not yet officially supported by Playwright 1.60.
#    Use PLAYWRIGHT_HOST_PLATFORM_OVERRIDE to download the ubuntu24.04 fallback build.
PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 .venv/bin/playwright install chromium
```

### Python version

```
Python 3.14.4
```

### Installed packages (.venv/bin/pip list)

```
Package           Version Editable project location
----------------- ------- -----------------------------------------------------
api-doc-scraper   0.1.0   /home/dclarke/projects/api-doc-scraper-multi-platform
beautifulsoup4    4.15.0
greenlet          3.5.2
markdownify       1.2.2
pip               26.1.2
playwright        1.60.0
pyee              13.0.1
PyYAML            6.0.3
six               1.17.0
soupsieve         2.8.4
typing_extensions 4.15.0
```

### Exit criterion result

```
.venv/bin/python -c "import scraper, bs4, markdownify, yaml, playwright"
Exit code: 0  (no output — all imports succeeded)
```

### Deviations from spec

1. **Playwright Chromium install:** Ubuntu 26.04 is not in Playwright 1.60's supported
   platform list (only ubuntu20.04, ubuntu22.04, ubuntu24.04 are listed). The
   `PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64` env var was used to download
   the ubuntu24.04 fallback build. Browser is functional; this override must be set
   whenever `playwright install` is re-run on this machine.

2. **pyproject.toml build-backend:** Spec says `setuptools`; the correct string for
   pip/PEP 517 is `setuptools.build_meta` (not `setuptools.backends.legacy:build`).
   Used `setuptools.build_meta` with `requires = ["setuptools>=68"]`.
