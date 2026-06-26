# api-doc-scraper

A config-driven tool that pulls live, rendered API and reference documentation and
flattens it to clean, consistent markdown on disk. One paragraph on why: the
deliverable is a clean markdown snapshot of the live docs so a human or agent can
gap-check it against a locally maintained source-of-truth and catch where reality and
your docs disagree. When this was run against AskEdgar it caught a swapped response
field pair, a renamed endpoint masquerading as a new one, and tier-gated endpoints. The
tool handles Mode-1 acquisition only — fetching and writing; drift reconciliation and
snapshot storage are out of scope and not implemented.

## Supported platforms

Three platform adapters are registered. Adding a target on an existing platform requires
only a new `targets/<name>.yaml` — no code change.

| Platform | Key | Discovery | Extraction | Browser |
|---|---|---|---|---|
| ReadMe.io | `readme_io` | Playwright loads a seed page; sidebar links found in DOM | `get_main` + `extract_sections` + `render_sections` (verbatim seed engine) | Required (SPA-hydrated content) |
| Docusaurus | `docusaurus` | Fetches `sitemap.xml`, parses `<loc>` URLs, applies optional include/exclude glob filters | Selects `article` / `.theme-doc-markdown` / `main` container; converts with `htmlmd.to_markdown` | Not required (SSR content) |
| GitHub org | `github_org` | GitHub API: paginates org repos, reads each repo's actual `default_branch`, walks Git Trees API for doc paths | Fetches raw markdown from `raw.githubusercontent.com`; pass-through with light normalization | Not required (API-based) |

Platform support is limited to the three above. Swagger/OpenAPI, GitBook, Mintlify,
and other doc platforms are not supported and are explicitly out of scope for this pass.

## Output shape

Each run writes its output under `output/<target>/`. The directory is cleared at the
start of every write-mode run; no run history is retained.

**Per-document markdown files** — one file per document, at a deterministic,
collision-safe path (e.g. `api/_thatopen/components-front/classes/angle.md`).

Each file contains a YAML front-matter block followed by the markdown body:

```
---
source_url: https://docs.thatopen.com/api/@thatopen/components-front/classes/Angle
title: Angle
platform: docusaurus
target: thatopen-docs
package: "@thatopen/components-front"   # docusaurus only; null for others
repo: null                              # github_org only
breadcrumb: "api / @thatopen / components-front / classes / Angle"
fetched_at: "2026-06-25T14:00:00Z"
content_hash: "a3f9..."                 # sha256 hex of the markdown body
git_ref: null                           # github_org only: "{branch}@{commit_sha}"
---
```

Front-matter field presence by platform:

| Field | `readme_io` | `docusaurus` | `github_org` |
|---|---|---|---|
| `source_url`, `title`, `platform`, `target`, `fetched_at`, `content_hash` | required | required | required |
| `package` | null | derived from `/api/@scope/pkg/` path, or null | null |
| `repo` | null | null | repo name |
| `breadcrumb` | null | derived from path segments | `repo / path / stem` |
| `git_ref` | null | null | `"{branch}@{commit_sha}"` — required non-null |

**`output/<target>/manifest.json`** — written once atomically after the render loop.
Contains run metadata (`target`, `platform`, `generated_at`, `document_count`,
`failure_count`) and a per-document array (`slug`, `title`, `source_url`,
`content_hash`). `document_count` equals the number of `.md` files written.

**Single-file mode** — the `askedgar` (ReadMe.io) target uses `output_mode:
single_file`, which concatenates all sections into one file for G1 regression parity
with the seed scraper. Per-doc is the default for all other targets.

## Setup

Ubuntu 26.04 ships Python 3.14 without bundled pip. Use this bootstrap sequence:

```sh
# 1. Create venv without pip
python3 -m venv --without-pip .venv

# 2. Bootstrap pip
curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python3

# 3. Install the package and dependencies
.venv/bin/pip install -e .

# 4. Install Playwright Chromium
#    Ubuntu 26.04 is not yet in Playwright 1.60's supported platform list.
#    Use PLAYWRIGHT_HOST_PLATFORM_OVERRIDE to download the ubuntu24.04 build.
PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 .venv/bin/playwright install chromium
```

The `PLAYWRIGHT_HOST_PLATFORM_OVERRIDE` env var must be set whenever
`playwright install` is re-run on this host. The browser is only invoked for
`readme_io` targets; the other adapters run without it.

Dependencies: `playwright`, `beautifulsoup4`, `markdownify`, `pyyaml`, plus stdlib
(`urllib`, `html.parser`, `xml.etree.ElementTree`).

## Usage

```
python -m scraper.cli --target <name> [--discover] [--slug ID] [--no-discover] [--limit N]
```

`<name>` resolves to `targets/<name>.yaml`. The flag `--target` is always required.

### Flags

| Flag | Effect |
|---|---|
| `--discover` | Print discovered items to stdout and exit; no files written |
| `--slug ID` / `--single ID` | Fetch one document; skip discovery |
| `--no-discover` | Skip live discovery; use `fallback_slugs` from config (readme_io only) |
| `--limit N` | Cap documents processed to the first N after discovery |

`--discover` and `--slug` are mutually exclusive (exit 2 if combined).

### Examples

```sh
# List all discoverable slugs for AskEdgar without fetching
python -m scraper.cli --target askedgar --discover

# Full scrape of AskEdgar reference docs
python -m scraper.cli --target askedgar

# Smoke-test 5 pages of docs.thatopen.com
python -m scraper.cli --target thatopen-docs --limit 5

# Full scrape of docs.thatopen.com
python -m scraper.cli --target thatopen-docs

# Full scrape of ThatOpen GitHub org documentation
python -m scraper.cli --target thatopen-github

# Single document from ThatOpen docs
python -m scraper.cli --target thatopen-docs --slug https://docs.thatopen.com/api/@thatopen/components-front/classes/Angle
```

For the full flag reference, exit codes, output stream contract (`--discover` writes
to stdout; all progress and errors go to stderr), and error reporting format, see
[`docs/specs/multi-platform-adapters/03-UI-SPEC.md`](docs/specs/multi-platform-adapters/03-UI-SPEC.md).

## Adding a target

Drop a `targets/<name>.yaml` alongside the existing ones. No code change is needed for
a new target on a supported platform. Use an existing file as the template:

- ReadMe.io: copy `targets/askedgar.yaml` — set `platform: readme_io`, `options.base_url`,
  `options.seed_url`, and update `options.fallback_slugs`.
- Docusaurus: copy `targets/thatopen-docs.yaml` — set `options.sitemap_url` and
  `options.base_url`. Add `include_patterns` / `exclude_patterns` to filter by URL path
  (see `targets/thatopen-tutorials.yaml` for an example).
- GitHub org: copy `targets/thatopen-github.yaml` — set `options.org`. Requires `gh`
  CLI authenticated in the environment, or `GITHUB_TOKEN` set.

## Scope boundary

This tool performs **Mode-1 acquisition only**: adapters fetch live docs and write
markdown to disk. The following are explicitly out of scope and not implemented:

- Drift detection, reconciliation, or any stateful snapshot store (Mode-2).
- Downstream concerns: embedding, chunking, vector store ingestion.
- Platform adapters beyond `readme_io`, `docusaurus`, and `github_org` (no
  Swagger/OpenAPI, GitBook, Mintlify, or other platforms this pass).
- Private GitHub repos — public repos via GitHub API only.
- Run history — each run overwrites `output/<target>/`.

The `engine_docs` ↔ `docs.thatopen.com` content overlap (some ThatOpen repos contain
docs that also appear on the Docusaurus site) is surfaced via `git_ref` in front-matter
for a downstream consumer to deduplicate; this tool does not deduplicate.
