# ROADMAP — Multi-platform adapter architecture

| Field | Value |
|---|---|
| Author | scraper (fabric) |
| Date | 2026-06-25 |
| Governing DDR | DDR-02 (LORE `acd22c0f-7b80-440f-8b83-d3e19f5e2b72`) |
| Status | DRAFT — for Frank QC |

Forge is sliced so each slice has a demonstrable exit. Slices are ordered by dependency.
A `PROGRESS.md` in this folder tracks slice status during forge.

## Slice 0 — Scaffold + environment
- Create `scraper/` package skeleton + `pyproject.toml` (deps: playwright, beautifulsoup4,
  markdownify, pyyaml).
- Bootstrap venv: `python3 -m venv --without-pip .venv` → `get-pip.py` → `pip install -e .`
  → `playwright install chromium`. (`.venv/` already gitignored.)
- **Exit:** `python -c "import scraper, bs4, markdownify, yaml, playwright"` succeeds in venv.

## Slice 1 — Core lift + config + emit + runner + CLI (base generalization)
- Lift seed `fetch/get_main/extract_sections/render_sections/discover_slugs` into `core.py`
  **verbatim** (constants → params).
- `config.py` (`TargetConfig` + `load_target`), `emit.py` (per-doc front-matter + manifest +
  single-file mode), `adapters/base.py` (interface + dataclasses), `runner.py`, `cli.py`.
- **Exit:** CLI parses; `--target askedgar --discover` reaches discovery (engine wired) even
  before the adapter is finalized.

## Slice 2 — ReadMe.io adapter + G1 characterization (binding regression)
- `adapters/readme_io.py` delegates to `core.py`; `targets/askedgar.yaml` gains
  `platform: readme_io` + `output_mode: single_file`.
- **Exit (AC-3 / DDR-01 G1):** `--target askedgar --discover` lists the seed's slug set;
  a single-slug render matches the seed structurally (if `askedgar.readme.io` reachable —
  otherwise document the dependency and proceed). Seed retained until this passes.

## Slice 3 — `htmlmd` + Docusaurus adapter (proving target, part 1)
- `htmlmd.py` (noise-strip + structure-preserving conversion: fenced code, tables, headings).
- `adapters/docusaurus.py` (sitemap discovery + path filters; urllib fetch; htmlmd extraction;
  `package`/`breadcrumb` derivation); `targets/thatopen-docs.yaml`.
- **Exit (AC-1):** `--target thatopen-docs --limit 5` → 5 per-doc files + manifest; a TypeDoc
  `/api/` page and a `/Tutorials/` page show intact code fences, tables, headings, clean
  front-matter, no chrome bleed. Then a full ~504-doc run completes politely.

## Slice 4 — GitHub org adapter (proving target, part 2)
- `adapters/github_org.py` (repo enumeration; per-repo default branch; markdown selection;
  raw fetch; passthrough + front-matter); `targets/thatopen-github.yaml`.
- **Exit (AC-2):** `--target thatopen-github` → per-repo doc markdown across the 15 repos
  using each repo's real default branch; repo/path in front-matter + manifest.

## Slice 5 — Generalization proof + cleanup + README
- Demonstrate AC-4: add a second target of an existing platform via YAML only (no code).
- Reframe `README.md` to the generalized, adapter-based, two-mode framing (acquisition is
  this pass) + honest platform-boundary note. Delete `seed/` only after Slice 2 passes.
- **Exit:** all acceptance criteria (AC-1..AC-4) demonstrated; spec package + outputs ready
  for Frank's forge-side QC and the architect PR review.

## Sequencing notes
- Slices 1–2 are the base generalization PLAN.md described but never built; they are
  prerequisites for the adapters, not optional.
- Slices 3 and 4 are independent after Slice 1 and could parallelize, but Slice 3 (Docusaurus)
  is the richer quality proof, so it goes first.
- QC gate (Frank) runs on the spec package now, and again after forge — mechanics to be
  confirmed with Meridian.
