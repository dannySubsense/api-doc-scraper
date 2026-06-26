# DDR-02 — Multi-platform adapter architecture for api-doc-scraper

| Field | Value |
|---|---|
| Status | LOCKED |
| Date | 2026-06-25 |
| Author | meridian (architect) |
| Composer | Danny Clarke |
| LORE | `projectId: api-doc-scraper`, `documentId: acd22c0f-7b80-440f-8b83-d3e19f5e2b72` |
| Supersedes | — (authorized extension of DDR-01's out-of-scope items) |

> Repo transcription of the record authored and locked in LORE by Meridian, to satisfy
> the dual-surface rule (a DDR is complete only when both repo and LORE hold it). Content
> is faithful to the locked LORE document; the LORE record is canonical.

---

## Decision

Generalize api-doc-scraper beyond ReadMe.io by introducing a platform adapter
architecture. This is the authorized extension of DDR-01's out-of-scope items, now
explicitly greenlit as a separate build on branch `feature/multi-platform`.

## What is being built

A thin adapter interface that decouples discovery + extraction strategy from the core
engine (`get_main` / `extract_sections` / `render_sections`). Two adapters for this pass:

- **Docusaurus adapter** — targets `docs.thatopen.com` (Docusaurus v3.4.0). Discovery via
  `sitemap.xml` (~504 URLs). Plain HTTP fetch, no Playwright required. Content extracted
  from `<article>` / `.theme-doc-markdown`.
- **GitHub org adapter** — targets `github.com/ThatOpen` (15 public repos). Must read each
  repo's actual default branch — not hardcoded. `gh` CLI authenticated in environment.

## Output shape

Per-doc markdown files + `manifest.json` + YAML front-matter per document. Single-file-
per-target was a seed constraint, not a design goal. This shape is cleaner for downstream
consumption.

## Scope boundary

Mode-1 acquisition only: adapters → markdown on disk. Stateful snapshot store (Mode-2
reconcile) is explicitly out of scope for this pass.

## Acceptance gate

Adapters must produce clean, consistent markdown output equivalent in quality to the
existing ReadMe.io engine output. ThatOpen is the proving target.

## Repo

`dannySubsense/api-doc-scraper`, branch `feature/multi-platform`

## Authors

- Composer: Danny Clarke
- Architect: Meridian
