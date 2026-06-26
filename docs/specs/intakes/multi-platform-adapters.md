# Intake — Multi-platform adapter architecture

| Field | Value |
|---|---|
| Author | scraper (fabric) |
| Date | 2026-06-25 |
| Governing DDR | [DDR-02](../api-doc-scraper-ddrs/DDR-02-multi-platform-adapter-architecture.md) (LORE `acd22c0f-7b80-440f-8b83-d3e19f5e2b72`) |
| Context DDR | [DDR-01](../api-doc-scraper-ddrs/DDR-01-generalized-stateful-readmeio-doc-scraper.md) (PROPOSED) |
| Branch | `feature/multi-platform` |
| Proving target | ThatOpen (`docs.thatopen.com`, `github.com/ThatOpen`) |

This is my internalization of DDR-02 before the spec sprint — scope as I read it, the
success criteria I'll be held to, and the open questions REQUIREMENTS/ARCHITECTURE must
close. It is a scoping document, not a committed design.

## 1. What I'm building (in my words)

A **platform adapter** seam in front of the existing scraper so the tool can acquire
clean markdown from doc sources that are *not* ReadMe.io-shaped. An adapter owns two
strategies — **discovery** (how to enumerate the documents of a target) and **extraction**
(how to turn one fetched document into clean markdown) — behind one interface. The core
engine (`get_main` / `extract_sections` / `render_sections`, lifted from the seed) stays
the shared HTML→markdown value; adapters that don't fit it bring their own extraction
strategy rather than modifying it.

Two adapters this pass:
- **Docusaurus** → `docs.thatopen.com`
- **GitHub org** → `github.com/ThatOpen`

Plus the base generalization the seed never grew: a config/adapter-driven runner and CLI,
since none of `scraper/` exists yet (the repo is still SEEDED — only the seed script runs).

## 2. Scope (as I read DDR-02)

**In:**
- Adapter interface + a runner/CLI that selects an adapter per target config.
- Docusaurus adapter (sitemap discovery, plain HTTP, structure-preserving extraction).
- GitHub org adapter (repo enumeration via `gh`/API, per-repo default branch, markdown docs).
- Per-doc markdown output + `manifest.json` + YAML front-matter per document.
- Porting the seed's ReadMe.io engine into the package as the first adapter (so AskEdgar
  still works and remains the characterization reference).

**Out (explicit):**
- Mode-2 reconcile / drift report / stateful versioned snapshot store (DDR-02 scope boundary).
- Anything downstream of the markdown on disk — the embedding/chunking pipeline is a
  separate tool and not my concern (Meridian, kickoff).
- Other platforms (Swagger/OpenAPI, GitBook, Mintlify) — not this pass.
- Source-code scraping from GitHub repos — documentation markdown only.

## 3. Success criteria

1. **Binding acceptance gate (DDR-02):** the Docusaurus and GitHub adapters produce clean,
   consistent markdown *equivalent in quality* to the ReadMe.io engine's output, proven on
   ThatOpen. "Quality" concretely = correct content container (no nav/aside/footer bleed),
   intact heading hierarchy, **code blocks preserved as fenced code** (not flattened to
   prose), tables preserved, and uniform per-doc front-matter + a valid `manifest.json`.
2. **AskEdgar characterization (DDR-01 G1):** the ported ReadMe.io adapter reproduces the
   seed's discovered slug set and structurally-equivalent output, so the lift is verifiably
   non-breaking. The seed stays until this passes, then is deleted.
3. **No-code-change generalization:** a new target of an existing platform is added by
   dropping a `targets/<name>.yaml` — no code edit. (DDR-01 G2 in spirit, across platforms.)

## 4. Evidentiary basis (recon already done, 2026-06-25)

- **Docusaurus** (`docs.thatopen.com`): Docusaurus v3.4.0; **SSRs full content** → plain
  HTTP, no Playwright. `sitemap.xml` = **504 URLs** (~14 human docs: `/intro`,
  `/components/*`, `/fragments/*`, `/Tutorials/**`; ~490 auto-generated TypeDoc pages under
  `/api/@thatopen/*`). Content lives in `<article>` / `main.docMainContainer` /
  `.theme-doc-markdown.markdown`; prose **and** code present in the SSR HTML.
- **GitHub org** (`ThatOpen`): **15 public repos**; `default_branch` varies (`main` vs
  `master`) → adapter must read each repo's actual default branch. `gh` authed as
  `danny-island`. `engine_docs` is the *source* of `docs.thatopen.com` (the two targets
  overlap — rendered HTML + generated TypeDoc vs. raw `.mdx` source; dedup is the
  downstream pipeline's concern, not mine).
- **Environment:** only Python 3.14 present, **no pip / no `ensurepip`** → bootstrap a venv
  with `--without-pip` + `get-pip.py`. Playwright ships `py3` wheels (installs on 3.14).
  bs4 uses stdlib `html.parser` (no lxml). HTTP via stdlib `urllib` (no `requests`).

## 5. Open questions for the spec sprint

1. **Extraction strategy vs. the protected core.** DDR-02 says adapters "decouple
   extraction strategy from the core engine," and the gate demands code-block fidelity. The
   seed's `render_sections` *flattens* text and would mangle code. PROPOSED RESOLUTION (to
   confirm in ARCHITECTURE): HTML adapters select an extraction strategy behind the
   interface — ReadMe.io keeps the verbatim core (DDR-01 D2); Docusaurus uses a new
   structure-preserving HTML→markdown converter. This *adds* a strategy, doesn't modify the
   core — respecting D2. Dependency: `markdownify` or a small custom bs4 converter.
2. **Adapter interface shape.** What exactly crosses the seam — `discover() -> [Item]` and
   `render(item) -> Document`? Where does fetch live (browser vs HTTP vs API) — a per-adapter
   `requires_browser` flag on a shared runner? ARCHITECTURE to lock the contract + dataclasses.
3. **Front-matter schema.** Exact fields and their derivation per platform (`source_url`,
   `title`, `platform`, `target`, `package`/`repo`, `breadcrumb`/`category`, `fetched_at`,
   `content_hash`). Must be uniform enough for a downstream consumer yet faithfully derivable
   from each source. REQUIREMENTS to fix the schema; ARCHITECTURE the per-adapter derivation.
4. **Output layout + manifest schema.** Directory tree under `output/<target>/`, filename
   derivation from identifier, and the `manifest.json` shape (per-doc entries + run metadata).
5. **Docusaurus discovery filtering.** All 504 by default (DDR-02 implies full acquisition),
   with optional include/exclude path patterns so a user can scope (e.g. exclude `/api/`).
   Confirm default = everything.
6. **GitHub doc selection.** README + `/docs/**.md(x)` + top-level `*.md` per repo (per
   Danny's planning). Confirm archived-repo handling and the markdown glob set in REQUIREMENTS.
7. **QC gate mechanics.** How Frank's review is invoked here is unresolved — route to Meridian
   when the spec package is drafted. Not a blocker for authoring the specs.

## 6. References

- DDR-02 (governing), DDR-01 (context, esp. D2 protect-the-core + G1/G2 gates).
- `PLAN.md` §8 (adapter-boundary framing), §4 (coupling surface), §5 (package layout).
- `seed/scrape_askedgar_reference.py` (the ReadMe.io engine + characterization ground truth).
- `targets/askedgar.yaml` (target-config fixture pattern the new targets follow).
