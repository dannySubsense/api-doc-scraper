# UI SPEC — Multi-platform adapter architecture (CLI)

| Field | Value |
|---|---|
| Author | scraper (fabric) |
| Date | 2026-06-25 |
| Governing DDR | DDR-02 (LORE `acd22c0f-7b80-440f-8b83-d3e19f5e2b72`) |
| Requirements | 01-REQUIREMENTS.md |
| Architecture | 02-ARCHITECTURE.md |
| Status | DRAFT |

---

## No graphical interface — rationale

This tool has no GUI, TUI, or interactive prompt. It is a headless, non-interactive
command-line tool and Python package whose only user-facing surface is the CLI invocation,
stdout/stderr streams, exit code, and output files written to disk.

This is an explicit design decision: the tool is intended for scripted and CI use (drift
detection, doc ingestion pipelines). Interactive prompts or config wizards are out of scope
per NFR-6 and DDR-02. All configuration is file-driven (`targets/<name>.yaml`).

The "UI" specification below therefore covers: invocation syntax, flag semantics, output
streams, progress format, exit codes, and error reporting — the full contract between the
tool and any human or script that invokes it.

---

## Invocation

```
python -m scraper.cli --target <name> [flags]
```

`<name>` is a target name that must correspond to an existing `targets/<name>.yaml` file.
There is no default target; `--target` is always required.

---

## Flags

### --target NAME (required)

Selects the target to run. Resolves to `targets/<name>.yaml` via `config.load_target`.

- **Type:** string
- **Required:** yes; the CLI fails immediately (exit 2) if omitted
- **Effect:** determines platform adapter, output directory, and all config values

### --discover

Runs discovery only: prints the discovered item list to stdout and exits. No documents are
fetched or written. No output files are produced.

- **Type:** boolean flag (no argument)
- **Mutually exclusive with:** `--slug` / `--single`
- **Interaction with `--no-discover`:** `--discover` and `--no-discover` may be combined;
  `--no-discover` instructs the adapter to skip live discovery and use the configured
  `fallback_slugs` list instead, then `--discover` prints that fallback list and exits.
  This combination is useful to inspect what the fallback list contains without fetching.
- **Interaction with `--limit`:** `--limit` is applied after discovery and before printing;
  it caps the number of items printed. This is consistent with the normal-run behavior.

### --slug NAME / --single NAME

Fetches and renders exactly one document identified by `NAME`. For ReadMe.io targets,
`NAME` is a slug string. For Docusaurus targets, `NAME` is a URL path. For GitHub org
targets, `NAME` is a `repo:path` identifier.

- **Type:** string (takes an argument)
- **Aliases:** `--slug` and `--single` are equivalent names for the same flag (preserved
  from seed; both accepted)
- **Mutually exclusive with:** `--discover`
- **Effect:** the runner creates a single synthetic `Item` with `label=NAME, identifier=NAME`
  and skips the discovery phase entirely. The polite delay is not applied (single item).
- **Output:** writes one `.md` file and one `manifest.json` to `output/<target>/`

### --no-discover

Skips live discovery and uses the target's configured `fallback_slugs` list instead.
Applies to ReadMe.io targets only (the only platform with a fallback list concept).

- **Type:** boolean flag (no argument)
- **Mutually exclusive with:** `--slug` / `--single` (if `--slug` is given, discovery is
  bypassed entirely; `--no-discover` has no additional effect and is silently ignored)
- **Effect:** the runner passes `no_discover=True` to the adapter; the ReadMe.io adapter
  uses `fallback_slugs` from config instead of calling `discover_slugs`

### --limit N

Caps the number of documents processed in a run at N (after discovery, before rendering).

- **Type:** positive integer
- **Optional:** omit to process all discovered items
- **Effect:** after discovery (or fallback), the item list is truncated to the first N items
  in discovery order. Items beyond N are neither rendered nor recorded in the manifest.
- **Intended use:** smoke tests and development runs against a large target

### Flag interaction matrix

| --discover | --slug | --no-discover | --limit | Result |
|---|---|---|---|---|
| — | — | — | — | Full run: discover all, render all, write output |
| yes | — | — | — | Discover all, print list, exit 0. No files written. |
| yes | — | yes | — | Use fallback list, print it, exit 0. No files written. |
| yes | — | — | N | Discover all, truncate to N, print list, exit 0. |
| — | SLUG | — | — | Render one document, write output. Discovery skipped. |
| — | — | yes | — | Use fallback list, render all, write output. |
| — | — | — | N | Discover all, render first N, write output. |
| yes | SLUG | — | — | **Error:** mutually exclusive. Exit 2, message to stderr. |

---

## Output streams

### Convention

- **stderr** — all human-readable progress, status, warnings, and error messages.
  This stream is for operators watching a run; it is not machine-parseable and its
  exact format may change between releases.
- **stdout** — machine-parseable output only. Currently: the `--discover` item list.
  In all other modes stdout is silent (nothing is written to stdout).

This separation ensures `--discover` output can be piped or redirected without capturing
progress noise:

```
python -m scraper.cli --target thatopen-docs --discover > items.txt
```

---

## Progress output (stderr)

### Startup messages

Emitted to stderr before the render loop begins.

For a full run (no `--discover`, no `--slug`):

```
Loading target: thatopen-docs  (platform: docusaurus)
Discovering items...
Discovered 504 items
```

For `--no-discover` on a ReadMe.io target:

```
Loading target: askedgar  (platform: readme_io)
Using fallback list: 30 items
```

For `--slug`:

```
Loading target: askedgar  (platform: readme_io)
Single-item mode: dilution_rating_v1_dilution_rating_get
```

### Per-item progress (render loop)

Emitted to stderr as each item is processed. Format mirrors the seed's style:

```
[i/N] <label>
```

Where `i` is the 1-based index and `N` is the total count of items being rendered.

Example:

```
[1/30] Health Check
[2/30] Endpoint Listing
[3/30] Reverse Splits
```

On per-item failure (NFR-4), an error line is emitted immediately after the item line:

```
[7/30] Offerings — Funds & Underwriters
  ERROR: HTTP 503 — https://askedgar.readme.io/reference/offerings_advanced_v1_offerings_advanced_get
```

The run continues; the item is recorded as a failure in the manifest.

### Completion summary

Emitted to stderr after all items are processed and output is written:

```
Wrote 29 documents, 1 failure
Output: output/askedgar/
Manifest: output/askedgar/manifest.json
```

If there are no failures:

```
Wrote 30 documents
Output: output/askedgar/
Manifest: output/askedgar/manifest.json
```

If `--limit` was applied:

```
Wrote 5 documents (limited to 5 of 30 discovered)
Output: output/askedgar/
Manifest: output/askedgar/manifest.json
```

---

## --discover mode output (stdout)

When `--discover` is given, each discovered item is printed to stdout, one per line, in
the format:

```
  <identifier>  →  <sanitized-slug>
```

Where `<identifier>` is the platform-native identifier (slug for ReadMe.io, URL path for
Docusaurus, `repo:path` for GitHub org) and `<sanitized-slug>` is the collision-resolved
relative output path that would be written if a full run were executed.

Example output for a ReadMe.io target:

```
  health_check_health_get  →  health_check_health_get.md
  list_endpoints_endpoints_get  →  list_endpoints_endpoints_get.md
  dilution_rating_v1_dilution_rating_get  →  dilution_rating_v1_dilution_rating_get.md
```

Example output for a Docusaurus target (partial):

```
  /api/@thatopen/components-front/classes/Angle  →  api/_thatopen/components-front/classes/angle.md
  /Tutorials/Getting-Started  →  tutorials/getting-started.md
```

The identifier field is left-padded with two spaces. The arrow `  →  ` is a fixed
separator (two spaces, arrow, two spaces). No trailing newline after the last entry.

A header line is NOT emitted to stdout; the list is clean for piping. A startup message
is emitted to stderr before the list (see above), and a count line is emitted to stderr
after:

```
Discovered 504 items  [stderr]
```

---

## Output files

All output files are written under `output/<target>/` relative to the project root.
This directory is gitignored. Each run overwrites the directory contents; no run history
is retained.

### Per-document markdown files

Path: `output/<target>/<slug>` where `<slug>` is the collision-resolved relative path
from `Document.slug` (e.g. `api/_thatopen/components-front/classes/angle.md`).

Each file contains:
1. A YAML front-matter block (delimited by `---`) with all fields from FR-16a.
2. The markdown body.

Files are written atomically (write-to-temp-then-replace). A kill mid-run leaves only
complete files; no partial files.

### manifest.json

Path: `output/<target>/manifest.json`

Written once, atomically, after the render loop completes. Schema (from architecture):

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

`document_count` equals `len(documents)` equals the number of `.md` files written.
`failure_count` equals `len(failures)`. The `documents` array contains only successfully
written files. Failed items appear only in `failures`.

If the run is killed before the render loop completes, no `manifest.json` is written.
A missing manifest is a clean, detectable failure state.

---

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. All items rendered (or `--discover` completed). Partial failures (per-item errors) are logged and recorded in the manifest; exit 0 still applies. |
| 1 | Runtime error: network failure during discovery, unknown platform in registry, discovery returned zero items with no fallback, `manifest.json` write failure, or any unhandled exception. |
| 2 | Usage error: missing required flag (`--target`), mutually exclusive flags combined (`--discover` + `--slug`), unrecognized flag, or `--limit` given a non-positive integer. Argparse emits the error message to stderr and the usage hint. |

### Partial failure policy (NFR-4)

A single document fetch or render failure does NOT cause a non-zero exit. The failed item
is:
1. Logged to stderr with its identifier and error message.
2. Recorded in the manifest `failures` array.
3. Excluded from the `documents` array and the file count.

The run continues with the next item. Exit 0 is returned when the run completes, even if
some items failed.

This policy means a caller that needs to detect partial failures must inspect
`manifest.json`'s `failure_count` field; exit code alone is insufficient for this.

### Fast-fail conditions (exit 1)

The following conditions abort the run before any output is written:

| Condition | Error message (stderr) | Exit |
|---|---|---|
| `targets/<name>.yaml` not found | `Error: target "<name>" not found. Expected targets/<name>.yaml` | 1 |
| Platform in YAML not in adapter registry | `Error: unknown platform "<platform>" in targets/<name>.yaml` | 1 |
| Discovery returns zero items AND no fallback available | `Error: discovery returned 0 items for target "<name>" — no fallback configured` | 1 |
| `fallback_slugs` is empty AND `discovery_min_slugs` threshold not met | `Error: discovery returned <N> items (below threshold <M>) and fallback_slugs is empty` | 1 |
| Docusaurus sitemap unreachable or returns zero URLs | `Error: sitemap fetch failed for "<url>": <reason>` | 1 |

These abort before any `.md` files or `manifest.json` are written, leaving the output
directory unchanged.

---

## Error reporting

### Config errors

Reported to stderr before the run begins. Format:

```
Error: <description>
```

Followed by a blank line and the usage hint (for usage errors / exit 2) or no usage hint
(for runtime config errors / exit 1).

### Per-item errors (during render loop)

Reported inline with the progress output on stderr:

```
[7/30] Offerings — Funds & Underwriters
  ERROR: HTTP 503 — https://askedgar.readme.io/reference/offerings_advanced_v1_offerings_advanced_get
```

Full traceback is not printed to stderr by default; the error string is the exception
message. A `--verbose` flag for full tracebacks is not in scope for this spec (not in
FR-19; deferred).

The same error string is written to `manifest.json` `failures[].error`.

### Front-matter validation failure

If `emit.write_document` finds that a `Document.metadata` dict is missing a required
field (non-nullable field absent or empty), this is treated as a per-item failure:

```
  ERROR: front-matter validation failed for <identifier>: missing required field "title"
```

The item is recorded in `failures`; the run continues.

### Manifest write failure

If `emit.write_manifest` fails (e.g. disk full), the error is reported to stderr and the
run exits 1:

```
Error: failed to write manifest: [Errno 28] No space left on device
```

Individual document files already written are not rolled back; the missing manifest is the
signal that the run did not complete cleanly.

---

## User flows

### Flow 1: Full run (normal use)

1. Operator invokes: `python -m scraper.cli --target thatopen-docs`
2. stderr: startup message, discovery progress
3. stderr: per-item progress lines as each document is rendered
4. Output files written atomically to `output/thatopen-docs/`
5. stderr: completion summary with document count, output dir, manifest path
6. Exit 0

Error path: if one or more documents fail, error lines appear inline in step 3. On
completion, summary shows failure count. Exit 0. Operator inspects `manifest.json`
`failures` for details.

### Flow 2: Discover only (pipe-friendly)

1. Operator invokes: `python -m scraper.cli --target thatopen-docs --discover`
2. stderr: "Loading target: thatopen-docs  (platform: docusaurus)"
3. stderr: "Discovering items..."
4. stdout: item list (one line per item, `identifier  →  slug` format)
5. stderr: "Discovered 504 items"
6. Exit 0; no files written

### Flow 3: Single-document smoke test

1. Operator invokes: `python -m scraper.cli --target askedgar --slug health_check_health_get`
2. stderr: startup message with single-item mode notice
3. Document fetched and rendered
4. `output/askedgar/health_check_health_get.md` written
5. `output/askedgar/manifest.json` written (1 document entry)
6. stderr: "Wrote 1 document\nOutput: output/askedgar/\nManifest: output/askedgar/manifest.json"
7. Exit 0

### Flow 4: Limited smoke run

1. Operator invokes: `python -m scraper.cli --target thatopen-docs --limit 5`
2. Discovers all 504 items
3. Renders and writes first 5 items
4. stderr completion: "Wrote 5 documents (limited to 5 of 504 discovered)"
5. Exit 0

### Flow 5: Fallback-only run (ReadMe.io)

1. Operator invokes: `python -m scraper.cli --target askedgar --no-discover`
2. stderr: "Loading target: askedgar  (platform: readme_io)"
3. stderr: "Using fallback list: 30 items"
4. Renders all 30 fallback items
5. Normal completion
6. Exit 0

### Flow 6: Config error

1. Operator invokes: `python -m scraper.cli --target nonexistent`
2. stderr: `Error: target "nonexistent" not found. Expected targets/nonexistent.yaml`
3. No files written
4. Exit 1

### Flow 7: Usage error (mutually exclusive flags)

1. Operator invokes: `python -m scraper.cli --target askedgar --discover --slug foo`
2. stderr: `Error: --discover and --slug are mutually exclusive`
3. stderr: usage hint (argparse format)
4. Exit 2

---

## Component hierarchy (CLI layer)

```
cli.py  (argparse entry point)
  └── runner.py  (orchestration)
        ├── config.load_target()         reads targets/<name>.yaml
        ├── ADAPTERS[platform]()         resolves adapter instance
        ├── browser_if_needed()          Playwright lifecycle (readme_io only)
        ├── adapter.discover()           returns list[Item]
        ├── slugify.resolve_collisions() assigns final slugs
        ├── [--discover exit point]      prints to stdout, exits
        ├── adapter.render()  ×N         per-item render loop
        │     └── log_failure()          stderr ERROR line on exception
        └── emit.write_all()
              ├── emit.write_document()  ×N  atomic per-doc write
              └── emit.write_manifest()      atomic manifest write
```

`cli.py` owns argument parsing and translates parsed args into runner call parameters.
`runner.py` owns all orchestration logic including the progress output to stderr. Neither
`cli.py` nor `runner.py` implement adapter or extraction logic.

---

## State visibility (what appears where)

| Data | Where visible |
|---|---|
| Target name | stderr startup line; manifest `target` field |
| Platform | stderr startup line; manifest `platform` field; every document front-matter |
| Discovered item count | stderr after discovery; `--discover` stderr count line |
| Per-item identifier + slug | stdout (--discover mode only) |
| Per-item label + index | stderr progress line during render loop |
| Per-item error message | stderr inline error line; manifest `failures[].error` |
| Document count written | stderr completion summary; manifest `document_count` |
| Failure count | stderr completion summary (only if > 0); manifest `failure_count` |
| Output directory | stderr completion summary |
| Manifest path | stderr completion summary |
| Per-document metadata | output `<slug>.md` front-matter block; manifest `documents[]` entry |
| Run timestamp | manifest `generated_at`; every document front-matter `fetched_at` |

---

## Consistency notes and flag gaps

The following observations are flagged for the implementation team; none are blockers.

1. **`--single` alias:** FR-19 names the flag `--slug/--single`. The architecture
   (`cli.py` comment) lists only `--slug`. Both names should be accepted (argparse
   `add_argument("--slug", "--single", ...)`), consistent with the seed's `--slug` usage.

2. **`--discover` + `--no-discover` combination:** FR-19 preserves both flags from the
   seed. The seed processes them sequentially (no-discover sets the slug list; discover
   prints it). This spec formalizes that combination as valid and useful (inspect fallback
   list without fetching). The runner must handle this: set items from fallback, then check
   `--discover` and exit.

3. **`--limit` not in seed:** `--limit N` is a new flag (FR-19 "Add --limit N"). It is
   applied after discovery and before the render loop. It does not affect `--discover`
   output conceptually but this spec includes it for consistency (see §Flags above).

4. **No `--output` flag:** output directory is config-driven (`output/<target>/` default,
   overridable in `targets/<name>.yaml`). There is no CLI flag to override the output dir.
   This is consistent with FR-14 and the architecture; flagged here so it is explicit.

5. **No `--verbose` / `--quiet` flags:** not in FR-19. Full tracebacks are not printed
   by default. This is the specified behavior; a future revision of FR-19 could add these.
