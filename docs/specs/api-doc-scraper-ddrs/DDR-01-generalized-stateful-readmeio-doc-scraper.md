# DDR-01 — Generalize to a config-driven, stateful ReadMe.io documentation scraper

| Field | Value |
|---|---|
| Status | PROPOSED |
| Date | 2026-06-25 |
| Author | vellum |
| Composer | Danny |
| GitHub issue | [#1](https://github.com/dannySubsense/api-doc-scraper/issues/1) |
| Supersedes | — |

---

## Context

The repo was extracted from `gap-lens-dilution` as a working single-app scraper plus a
generalization plan (`PLAN.md`). That plan and the seed framing both center the original
app and treat "documentation drift detection" as the whole purpose. Two corrections from
the bootstrap session reframe the project before any code is written:

1. **It is a generalized tool, not a single-app scraper.** The original app is one target
   among many — target-zero in `targets/`, not the project's identity. Carrying its proper
   noun into the framing risks over-fitting the generalization to it.
2. **The purpose is two-fold, not just drift.** "Drift detection" describes only the
   second-and-onward run. The first run against any target is a full-fidelity acquisition
   that stands on its own.

The seed is stateless (writes one markdown file and forgets). Reconciling across runs
(Mode 2) requires retained history, so the tool becomes stateful. That gap, plus the
reframing above, is what this DDR locks.

> **Naming:** this is a documentation **scraper** that produces versioned snapshots.
> Acquisition (Mode 1) is first-class, co-equal with reconciliation — not a preamble to it.
> "Drift" names what Mode 2 *reports*, never what the tool *is*. Do not call it a "drift scraper."

## Decision

### D1 — Scope: config-driven, ReadMe.io only

Lift the seed's hard-coded constants into per-target YAML. A new ReadMe.io site is added by
dropping a `targets/<name>.yaml` file with **no code change**. Scope is ReadMe.io-hosted
docs only; Swagger/OpenAPI, GitBook, Mintlify, and hand-built doc sites are explicitly out
of scope (different DOM + discovery models → a per-platform adapter is a separate project).

### D2 — Preserve the reusable core verbatim

`get_main`, `extract_sections`, `render_sections` already work off generic
`<article>`/`<main>`/`role=main` containers and `h1–h4` sectioning. They are the value and
move into `core.py` **unchanged**. Discovery is parameterized (`link_pattern`,
`slug_methods`) from config. The engine is platform-agnostic; only the four hard-coded
constants (base/seed URL, output path + header, fallback slug list, discovery link/slug
filter) generalize to config.

### D3 — Two modes over one engine

- **Mode 1 — acquire (cold / first pass).** No prior exists. Scrape the full target and
  write a baseline snapshot. Pure acquisition; no reconciliation. The snapshot is the
  deliverable and the one-time day-one correctness read.
- **Mode 2 — reconcile (warm / subsequent passes).** A baseline exists. Scrape again and
  diff against the prior snapshot, emitting a **drift report** as a first-class output
  (not an ad-hoc `git diff`).

Same scrape engine both modes; the difference is the post-scrape step (nothing vs. reconcile).

### D4 — Reconcile against the prior scrape only

Mode 2's baseline is **the immediately prior authoritative capture** (the last scrape of
the same target). There is **no** hand-maintained-source-of-truth reconciliation mode.

Rationale: a hand doc is *derivative* — downstream of the live docs, a human transcription
of the very thing being checked. Anointing it "source of truth" inverts the authority
hierarchy (live docs = primary source → faithful scrape = authoritative capture → hand doc
= derivative) and would flag transcription errors as drift. A hand-doc baseline only ever
existed as a crutch for the absence of scrape history; once history exists, the prior scrape
is the correct, ground-truth baseline. Versioned API change (scrape v1, later scrape v2, diff
them) is exactly what this catches.

### D5 — Statefulness: per-target versioned snapshot store

The tool persists versioned snapshots per target so Mode 2 has a baseline to diff against.
Scrape output (`output/`) and the legacy `docs/*-reference-raw.md` are git-ignored — live
captures are regenerated, not tracked. (Exact store layout — file naming, retention, where
the "prior" pointer lives — is a downstream implementation decision, not locked here.)

## Acceptance gates

Two **distinct** gates with distinct purposes. The plan conflated them; they prove different
things and the second is the binding one.

| Gate | Proves | Binding? |
|---|---|---|
| **G1 — Characterization** | The lifted engine reproduces target-zero's known-good output (same discovered slug set, structurally equivalent markdown). Confirms the verbatim lift didn't break the reusable core. | Necessary, not sufficient |
| **G2 — Generalization** | A second, structurally different ReadMe.io target works through the same config interface with **zero code changes** (ideally ≥2 independent targets). | **Yes — binding** |

G1 can be passed by code still secretly coupled to target-zero, so it cannot stand alone.
Once G2 holds, target-zero loses privileged status — it is one row in the target table.

## Out of scope (YAGNI)

Explicitly **not** building until a real need appears:

- Hand-maintained-doc / external-contract reconciliation mode (see D4 — inverted hierarchy).
- Multi-platform adapters (Swagger/OpenAPI, GitBook, Mintlify, Docusaurus).
- Any reference-selection flags, fallbacks, or "swap-in baseline" capability beyond
  prior-scrape reconciliation.

## Consequences

- The seed stays until G1 passes (it is the characterization ground truth), then is deleted.
- The legacy app name in `targets/<app>.yaml` and `seed/scrape_<app>_reference.py` is
  carry-over to normalize during the build, not to preserve.
- The package grows a snapshot store + a reconcile pass beyond the seed's single-file write —
  the main net-new surface over `PLAN.md`'s scaffold.
- `README.md` and `PLAN.md` should be reframed to the two-fold, generalized framing
  (they currently over-index on drift and the single app).

## References

- `PLAN.md` — original generalization scaffold (package layout, build phases, coupling surface).
- `seed/scrape_askedgar_reference.py` — characterization ground truth for G1.
- LORE: project memories under `projectId: api-doc-scraper` (framing, gates, two-fold purpose).
