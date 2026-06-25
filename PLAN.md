# api-doc-scraper — Generalization Plan & Hand-off

> **Status:** SEEDED. The working AskEdgar-specific scraper has been ported to
> `seed/scrape_askedgar_reference.py` as the worked example. The generalization
> described below has **not** been built yet — that is the job for the session
> that picks this up.
>
> **Origin:** Extracted from the `gap-lens-dilution` repo (agent: Dillon /
> `gaplens-dilution`) on 2026-06-25. The original stays gitignored in that repo
> for local AskEdgar gap-checks; **this repo is the canonical home** going forward.

---

## 1. What this tool is (the job, not just the mechanics)

The scraper exists to **detect documentation drift**: pull the live, rendered API
reference for a site, flatten it to markdown, and diff that against a locally
maintained source-of-truth doc to find where reality and your docs disagree.

It is *not* just "a scraper." The deliverable is a clean markdown snapshot of the
live docs that a human (or agent) can gap-check. When this was run against AskEdgar
on 2026-05-09 it caught real drift:

- A field swap — `research-reports-short` returns `tldr_text`, `research-reports-tldr`
  returns `report_text` (the local docs had them backwards).
- "Corporate Actions" in the sidebar was just `split_status` renamed — not a new
  endpoint (avoided a false alarm).
- ROFR and Offerings-Advanced are Institutional-tier-only — confirmed from the site.

Keep that framing in the README. A future user should understand *why* they'd reach
for this, not just how to run it.

## 2. Operational facts worth preserving (save the next agent a discovery cycle)

- **ReadMe.io reference pages are publicly readable without auth.** The
  "Log in to see full request history" banner only gates the interactive API
  playground — the parameter/response **schema** renders for anonymous visitors.
- **Auto-discovery from a single seed URL works.** Loading one `/reference/{slug}`
  page renders the full sidebar; every endpoint link is in the DOM. The hardcoded
  `FALLBACK_SLUGS` list is a safety net for when discovery returns suspiciously few
  results (the seed uses a `< 5` threshold).
- **The pages are SPA-hydrated.** `wait_until="networkidle"` plus a ~2.5s settle is
  required before the content container is populated. Don't remove the settle delay.
- **Be polite.** ~0.8s between pages. The full AskEdgar run is 30 endpoints; there is
  no reason to hammer.

## 3. Locked decisions (from the hand-off conversation, 2026-06-25)

| Decision | Choice |
|---|---|
| Generalization scope | **Config-driven, ReadMe.io only.** Lift the hard-coded constants into per-target YAML. Multi-platform adapters are a *later* growth task, NOT this pass. |
| Canonical repo | `github.com/dannySubsense/api-doc-scraper`, **public**. Push with `id_ed25519`. |
| Hand-off style | Self-contained folder + this plan. A fresh Claude Code session owns the build, agent identity, and repo creation. |

## 4. What's AskEdgar-specific vs. reusable (the coupling surface)

The engine is already mostly platform-agnostic. Only four things are hard-coded:

| Hard-coded in seed | Generalize to |
|---|---|
| `BASE_URL`, `SEED_URL` | `base_url`, `seed_url` in target config |
| `OUTPUT_PATH` + header text/date | `output_path` + a generated header from config |
| `FALLBACK_SLUGS` (30 AskEdgar slugs) | `fallback_slugs` list in target config (optional) |
| `/reference/` path + `_{method}` slug filter in `discover_slugs` | `link_pattern` + `slug_filter` in target config (defaults preserve current behavior) |

**Verbatim-reusable, do not touch:** `get_main`, `extract_sections`, `render_sections`.
These already work off generic `<article>` / `<main>` / `role=main` containers and
`h1–h4` sectioning. They are the value; protect them.

## 5. Target structure to build

```
api-doc-scraper/
  scraper/
    __init__.py
    core.py        # fetch, get_main, extract_sections, render_sections (lift verbatim)
    discover.py    # discover_slugs, with link_pattern + slug_filter parameterized
    config.py      # TargetConfig dataclass + YAML loader
    cli.py         # argparse entry: --target, --discover, --slug, --no-discover
  targets/
    askedgar.yaml  # the worked example (see §6)
  seed/
    scrape_askedgar_reference.py   # original — keep until askedgar.yaml reproduces it
  output/          # gitignored scrape output
  README.md
  pyproject.toml   # deps: playwright, beautifulsoup4
  PLAN.md          # this file
```

`TargetConfig` fields: `name`, `base_url`, `seed_url`, `output_path`,
`link_pattern` (default `/reference/`), `slug_methods` (default
`[get, post, put, delete, patch]`), `content_selectors` (default
`[article, div[role=main], main, body]`), `fallback_slugs` (optional list of
`{label, slug}`), and timings (`page_timeout_ms`, `settle_seconds`,
`polite_delay_seconds`) with the seed's values as defaults.

CLI shape to preserve: `python -m scraper.cli --target askedgar [--discover | --slug SLUG | --no-discover]`.

## 6. `targets/askedgar.yaml` — the acceptance fixture

A first-cut config is already written (see the file). It encodes the seed's exact
constants. It is also the **regression fixture**: the generalization is correct only
when it reproduces the seed's behavior on this target.

## 7. Build phases for the new session

- **Phase A — scaffold.** Create the package layout, `pyproject.toml`, `.gitignore`
  (already present), install Playwright (`pip install playwright beautifulsoup4 &&
  playwright install chromium`).
- **Phase B — lift the engine.** Move `fetch` / `get_main` / `extract_sections` /
  `render_sections` into `core.py` unchanged. Move discovery into `discover.py` with
  `link_pattern` + `slug_methods` injected from config.
- **Phase C — config layer.** `config.py` loads `targets/*.yaml` into `TargetConfig`.
  `cli.py` wires it up, preserving all four existing flags.
- **Phase D — sanity check (the gate).** `--target askedgar --discover` must list the
  **same 30 slugs** the seed produces (`python seed/scrape_askedgar_reference.py
  --discover`). A full `--target askedgar` run must produce output structurally
  equivalent to the seed's 69 KB / 30-endpoint markdown. Only then delete `seed/`.
- **Phase E — second target (proof of generalization).** Add one more ReadMe.io site
  as `targets/<name>.yaml` with no code changes. If it needs code changes, the config
  abstraction is leaking — fix the abstraction, not the target.
- **Phase F — README + identity.** Write the README around §1's framing. Run
  `/new-project` (or `/init`) to establish this repo's own agent identity + CLAUDE.md,
  then create the public GitHub repo under `dannySubsense` and push.

## 8. Known boundary (state it honestly in the README)

This generalizes across **ReadMe.io-hosted docs only**. Swagger/OpenAPI, GitBook,
Mintlify, Docusaurus, and Stripe-style hand-built docs have different DOM and
different discovery models. Supporting them means a per-platform **adapter**
(discovery + extraction strategy) behind the same config interface — a real second
project, explicitly out of scope for this pass. Do not pretend the config-driven
version is platform-agnostic; it isn't, and a user pointing it at a Swagger page will
get garbage. The `slug_methods` / `content_selectors` knobs give a little headroom,
but the discovery model is ReadMe.io-shaped.

## 9. Dependencies

- Python 3.11+ (the seed uses PEP 604 `list[tuple[...]]` / `X | None` syntax).
- `playwright` (+ `playwright install chromium`)
- `beautifulsoup4`
