# REVIEW — Multi-platform adapter architecture

| Field | Value |
|---|---|
| Author | scraper (fabric) |
| Date | 2026-06-25 |
| Governing DDR | DDR-02 (LORE `acd22c0f-7b80-440f-8b83-d3e19f5e2b72`) |
| Status | DRAFT — fabric self-review, for Frank QC |

Fabric's own review of the spec package before the QC gate: risks, alternatives weighed,
traceability to DDR-02, and how each acceptance criterion gets validated end-to-end.

## Traceability (DDR-02 clause → spec)

| DDR-02 clause | Where satisfied |
|---|---|
| Adapter interface decoupling discovery + extraction from core | ARCH adapter contract; FR-1..FR-3 |
| Docusaurus: sitemap, HTTP, `<article>`/`.theme-doc-markdown` | FR-7..FR-10; ARCH fetch/extraction |
| GitHub org: 15 repos, real default branch, gh auth | FR-11..FR-14; ARCH GitHub calls |
| Output: per-doc md + manifest.json + YAML front-matter | FR-15..FR-18; ARCH emit |
| Mode-1 acquisition only; no snapshot store | NFR-6; ARCH "what this does NOT add" |
| Acceptance: clean markdown equivalent to ReadMe.io engine; ThatOpen proving target | NFR-1; AC-1/AC-2 |
| Core engine protected (DDR-01 D2 carried forward) | FR-4; ARCH extraction strategies |

## Risks & mitigations

- **R1 — Extraction strategy vs. protected core.** Using a new converter for Docusaurus
  instead of `render_sections` could read as violating DDR-01 D2. *Mitigation:* the converter
  is an additional strategy behind the adapter interface; `core.py` is unchanged and remains
  ReadMe.io's path. Documented in ARCH. **Flag for Frank/Meridian to bless explicitly.**
- **R2 — Quality-gate subjectivity.** "Equivalent in quality" is a judgment. *Mitigation:*
  NFR-1 makes it concrete (no chrome bleed, fenced code, tables, headings, front-matter,
  valid manifest); validated on specific ThatOpen pages (AC-1).
- **R3 — AskEdgar reachability for G1.** The regression needs `askedgar.readme.io` live and
  Playwright working. *Mitigation:* G1 is run if reachable; otherwise the dependency is
  documented and the seed retained — does not block the adapter deliverable.
- **R4 — TypeDoc volume/noise.** ~490 auto-generated API pages may convert noisily.
  *Mitigation:* htmlmd noise-stripping; include/exclude path filters let a user scope; default
  is full acquisition per DDR-02. Spot-check a TypeDoc page in AC-1.
- **R5 — Python 3.14 / no pip.** *Mitigation:* venv `--without-pip` + get-pip bootstrap
  (Slice 0); Playwright py3 wheels confirmed compatible.
- **R6 — GitHub rate limits / large repos.** *Mitigation:* authenticated `gh` token (5000/hr);
  recursive tree filtered to markdown before fetching; politeness delay.
- **R7 — engine_docs/site overlap.** The GitHub and Docusaurus targets overlap content.
  *Mitigation:* out of my scope — dedup is the downstream pipeline's concern; noted in README.

## Alternatives considered & rejected

- **Reuse `render_sections` for all HTML adapters** (honor D2 literally). Rejected: flattens
  code blocks → fails NFR-1 for a code-heavy site. (See R1 resolution.)
- **Playwright for Docusaurus too** (uniform fetch). Rejected: content is SSR'd; a browser is
  needless cost and fragility.
- **Single concatenated file per target** (match seed exactly). Rejected by DDR-02: per-doc +
  manifest is the chosen shape; single-file kept only for G1 parity.
- **GitHub source-code ingestion.** Rejected: out of scope (docs markdown only).

## Validation plan

| Criterion | How validated |
|---|---|
| AC-1 Docusaurus quality | `--target thatopen-docs --limit 5` then full run; manual read of a TypeDoc + a Tutorial page for code/table/heading fidelity + front-matter; confirm manifest validity |
| AC-2 GitHub | `--target thatopen-github`; verify each repo's default branch honored; check repo/path metadata + manifest across 15 repos |
| AC-3 G1 regression | `--target askedgar --discover` vs `seed --discover` (slug-set equality); single-slug structural diff (if reachable) |
| AC-4 generalization | add a second YAML target of an existing platform; run; confirm zero code change |
| NFR-1 quality (binding) | side-by-side a Docusaurus + a GitHub render against a ReadMe.io render; architect/Frank judgment |

## Open items for Frank
1. Bless R1 (structure-preserving converter as an added strategy, core untouched).
2. Confirm the front-matter schema (FR-16) is sufficient and stable for a downstream consumer.
3. Confirm QC gate mechanics for the forge-side review.
