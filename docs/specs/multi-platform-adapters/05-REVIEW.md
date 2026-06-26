# REVIEW — Multi-platform adapter architecture (spec package)

| Field | Value |
|---|---|
| Author | scraper (fabric) |
| Date | 2026-06-25 |
| Governing DDR | DDR-02 (LORE `acd22c0f-7b80-440f-8b83-d3e19f5e2b72`) |
| Reviews | 01-REQUIREMENTS.md, 02-ARCHITECTURE.md, 03-UI-SPEC.md, 04-ROADMAP.md |
| Purpose | Completeness/consistency review ahead of Frank (binding QC) + human approval |
| Status | READY FOR FRANK — with 0 blockers, 2 minor gaps, 1 watch item |

This is an independent completeness/consistency review. It does not approve the package;
it prepares it for the binding QC engineer (Frank) and human sign-off. Findings are
reported, not fixed.

---

## Verdict at a glance

- **Prior QC findings C1, C2, C3, S1, S2, S3, S4: all CLOSED.** Each is confirmed below
  with a doc citation, not merely claimed.
- **No blocking gaps.** Implementation is possible from these documents as written.
- **2 minor gaps** (G-1, G-2) and **1 watch item** (W-1) — none gate forge; all recorded
  in the gaps table.
- **No DDR-02 scope creep.** Mode-2 / snapshot-store boundary is honored across all four
  docs and the DDR-01 G2 gate is correctly deferred.

---

## Part 1 — Prior QC findings: closure verification

Each finding is rated CLOSED / PARTIAL / OPEN with the specific evidence.

### C1 — FR-4 split (verbatim trio vs. parameterized discover_slugs) — CLOSED

- 01 §Core engine splits the requirement cleanly: **FR-4a** names the verbatim-protected
  trio (`get_main`, `extract_sections`, `render_sections`) as "not parameterized, not
  modified, and not extended"; **FR-4b** parameterizes `discover_slugs` (`link_pattern`,
  `slug_methods`/`slug_filter`, `discovery_min_slugs`, `fallback_slugs`) with seed values
  as defaults. The renumbering note (01 lines 14–15) documents the FR-4/FR-5 → FR-4a/FR-4b
  replacement.
- 02 §Core engine mirrors the split: separate "Verbatim-protected trio (FR-4a)" and
  "Parameterized discover_slugs (FR-4b)" subsections; the latter shows the parameterized
  signature with seed defaults; explicit text "`discover_slugs` is **not** part of the
  verbatim-protected trio."
- 04 Slice 1 codes both: trio "lifted unchanged" + `discover_slugs(html, link_pattern=...,
  slug_methods=None, slug_filter=None)`.
- **Residual-text check (adversarial):** grep across `docs/specs` for any phrasing that
  would re-protect `discover_slugs` (`unchanged|remains|stays|verbatim|not modified|
  untouched` adjacent to `discover_slugs`) returns **no matches**. No residual
  "discover_slugs unchanged" text exists anywhere in the package. CLOSED.

### C2 — Collision-safe filename scheme fully specified + built/tested — CLOSED

- 01 FR-15/FR-15a/FR-15b state the *properties* (deterministic; collision-safe across 504+
  Docusaurus URLs and `repo:path` ids; case-insensitive-FS safe; within OS path limits)
  and explicitly defer the *scheme* to architecture.
- 02 §Filename derivation specifies the full scheme in `slugify.py`: per-segment split per
  platform, 6-rule sanitization (lowercase, strip leading dots, illegal→`_`, collapse runs,
  80-byte cap with SHA-256 suffix, Windows reserved-name suffix), `.md`/`.mdx` handling,
  Step-4 collision detection via 8-hex SHA-256 suffix in discovery order, and a Step-5
  total-path-length guard (200-byte bound). Public interface (`identifier_to_slug`,
  `resolve_collisions`) is given. Worked examples cover the case-collision and `repo:path`
  cases.
- 04 builds and tests it: file owned by Slice 1 (C2 designation), Slice 1 exit criterion #4
  and #6 require `pytest tests/test_slugify.py` green covering case-collision detection,
  hash suffix, reserved names, length-cap, all three platform splits, `.mdx`→`.md`. CLOSED.

### C3 — G1 as concrete offline checks against committed golden fixtures — CLOSED

- 01 AC-3a (slug-set exact equality), AC-3b (per-slug heading-set equality, diffs confined
  to run header + `fetched_at`), AC-3c (offline reproducibility; fixture committed; no
  `askedgar.readme.io` call). The resolves-C3 note (01 lines 206–209) ties this directly
  to the prior vague "structurally equivalent."
- 02 §G1 golden fixture specifies the three committed fixture files
  (`slugs.json`, `headings.json`, `seed_page.html`) and an offline test that feeds
  `seed_page.html` to `discover_slugs` with **zero network dependency**.
- 04 C3 is a named precondition that **blocks Slice 2**, with capture scheduled after
  Slice 0 (Playwright present) and **before the seed is deleted** (Slice 5 precondition:
  "seed must not be deleted until Slice 2's G1 exit criterion is confirmed"). CLOSED.
- *See watch item W-1:* the roadmap's synthetic-fixture fallback (04 C3 "Fallback") and the
  AC-3b mock note (04 Slice 2 notes) can weaken live-parity if the live site is unreachable
  at capture time. The *offline mechanism* is still closed; the *parity guarantee* degrades
  gracefully. This is a watch item, not a re-open.

### S1 — Mechanizable AC assertions + gating harness — CLOSED

- 01 AC-1a (chrome-bleed denylist with concrete strings + `© \d{4}`), AC-1b (code-fence
  fidelity), AC-1c (front-matter validity, all required FR-16a keys non-empty), AC-1d
  (manifest count == file count) are all stated as automatable assertions; NFR-1 binds them
  as the quality gate and demotes the human spot-check (AC-1e) to a non-sufficient
  supplement.
- 04 S1 is a named slice ("Assertion harness") building `tests/test_output_quality.py` with
  one function per assertion plus an `output_dir_checker` fixture; it **gates Slice 3 and
  Slice 4** (both list S1 in Depends-On and in their exit criteria). S1 exit requires
  negative tests (must fail on chrome bleed + missing front-matter). CLOSED.

### S2 — markdownify `code_language_callback` spike before Docusaurus — CLOSED

- 02 §htmlmd configuration flags the assumption and states the subclass fallback
  (`MarkdownConverter` override of `convert_pre`/`convert_code`).
- 04 S2 is a named, time-boxed (30 min) spike that **blocks Slice 3** ("htmlmd.py must not
  be written until the approach is confirmed"); output `S2-spike-result.md` must state a
  confirmed approach; Slice 3 Depends-On lists "S2 spike (confirmed approach)." CLOSED.

### S3 — Atomic manifest/doc write (os.replace) — CLOSED

- 02 §Emit layer specifies `_atomic_write` (mkstemp → write → `os.replace`), single
  end-of-run `write_manifest`, and the anti-pattern "Incremental manifest writes." NFR-4
  in 01 requires "No partial-write corruption of the manifest."
- 04 Slice 1 owns `emit.py` (S3 designation), implements `_atomic_write`, and Slice 1 exit
  #5 requires `pytest tests/test_emit.py` covering interruption safety + manifest count
  equality. Sequencing summary confirms S3 lands in Slice 1. CLOSED.

### S4 — Front-matter schema locked incl. git_ref (required for github_org) — CLOSED

- 01 FR-16a is a full schema table (10 fields, type/required/nullable/notes), with explicit
  per-platform null rules: `git_ref` **required (not null) for github_org**, null elsewhere.
  Edge-case table covers `git_ref` unavailable → present-but-null. Resolves-S4 note present.
- 02 §Front-matter schema repeats the required key set as a typed dict and states nullable
  fields "must be present with an explicit `null`." GitHub call sequence derives
  `git_ref = "{default_branch}@{commit_sha}"` with the null-on-failure rule.
- 04 Slice 4 sets `git_ref` and AC-2 (01 + 04 exit) asserts `repo` and `git_ref` non-null
  in every github_org file. CLOSED.

---

## Part 2 — DDR-02 → spec traceability matrix

| DDR-02 clause | Spec coverage | Status |
|---|---|---|
| Decision: platform adapter architecture decoupling discovery+extraction from core | FR-1, FR-2, FR-3; 02 §Adapter contract (`PlatformAdapter` ABC) | ✅ |
| Docusaurus adapter — sitemap (~504), HTTP no-Playwright, `<article>`/`.theme-doc-markdown` | FR-6, FR-7, FR-8, FR-9; 02 §docusaurus.py; Slice 3 | ✅ |
| GitHub org adapter — 15 repos, actual default branch (not hardcoded), `gh` auth | FR-10, FR-11, FR-12, FR-13; 02 §GitHub call sequence; Slice 4 | ✅ |
| Output shape: per-doc md + manifest.json + YAML front-matter | FR-14, FR-16, FR-16a, FR-17; 02 §Emit/Front-matter; Slice 1 | ✅ |
| Single-file-per-target was a seed constraint (per-doc is the goal) | FR-18 (single-file retained for G1 parity only; per-doc default); 02 emit single-file mode | ✅ |
| Scope boundary: Mode-1 only; no Mode-2 / snapshot store | NFR-6; 01 Out of scope; 02 §What this does NOT add; 04 §Deferred | ✅ |
| Acceptance gate: clean/consistent markdown equivalent to ReadMe.io quality; ThatOpen is proving target | NFR-1 + AC-1a..AC-1e; ThatOpen named in AC-1/AC-2; Slices 3,4 | ✅ |
| (Inherited) DDR-01 D2 verbatim trio | FR-4a; 02 §Verbatim-protected trio | ✅ |
| (Inherited) DDR-01 D2 parameterized discovery | FR-4b; 02 §Parameterized discover_slugs | ✅ |
| (Inherited) DDR-01 G1 characterization gate | AC-3a/b/c; 02 §G1 fixture; Slice 2 + C3 | ✅ |
| (Inherited) DDR-01 G2 binding gate | **Deferred** — 01 Out-of-scope + 04 §Deferred; AC-4 substitutes cross-platform no-code-change proof | ⚠️ (intentional defer — see note) |

**Note on G2:** DDR-01 names G2 (second structurally-different ReadMe.io target) as the
*binding* gate. This package defers G2 and substitutes AC-4 (no-code-change generalization
across platforms). This is a deliberate, documented scope choice consistent with DDR-02's
platform focus, but G2 is DDR-01's binding gate — Frank/human should explicitly ratify the
substitution. Recorded as G-2 below (minor, decision-acknowledgment item, not a build gap).

---

## Part 3 — Requirements → Architecture coverage

| Requirement | Architecture coverage | Status |
|---|---|---|
| FR-1/FR-2/FR-3 adapter seam + registry + browser opt-in | `PlatformAdapter` ABC, `ADAPTERS` registry, `requires_browser` flag, `RunContext.page` | ✅ |
| FR-4a verbatim trio | §Verbatim-protected trio (PROTECTED, caller = readme_io only) | ✅ |
| FR-4b parameterized discover_slugs | §Parameterized discover_slugs (signature + seed defaults) | ✅ |
| FR-5 ReadMe.io port | §readme_io adapter + Extraction strategies + control flow | ✅ |
| FR-6..FR-9 Docusaurus | §docusaurus adapter, §htmlmd, §Filename derivation (package/breadcrumb) | ✅ |
| FR-10..FR-13 GitHub org | §GitHub call sequence (repos, default_branch, trees filter, raw fetch, commit) | ✅ |
| FR-14/FR-15/FR-15a/FR-15b output + filenames | §Filename derivation (5 steps, slugify.py) | ✅ |
| FR-16/FR-16a front-matter | §Front-matter schema (typed dict, null rules) | ✅ |
| FR-17 manifest | §Emit layer manifest schema | ✅ |
| FR-18 single-file mode | §emit single-file mode (TargetConfig.output_mode) | ✅ |
| FR-19 CLI flags | §cli.py + §Control flow flag handling | ✅ |
| NFR-2 politeness | §config polite_delay_seconds; control-flow `sleep` | ✅ |
| NFR-3 determinism | §Slug-before-render pattern; content_hash | ✅ |
| NFR-4 resilience / atomic | §Emit layer atomic writes; per-item error capture in control flow | ✅ |
| NFR-5 deps/env | §Dependencies table; stdlib urllib/html.parser | ✅ |
| AC-3a/b/c G1 | §G1 golden fixture + offline regression | ✅ |

**Gap G-1 (minor): `--slug` single-item path bypasses collision resolution + slug
assignment.** In 02 §Control flow, the `args.slug` branch builds
`raw_items = [Item(label=args.slug, identifier=args.slug)]` and then falls through to
`resolve_collisions` — good. But the single-item synthetic `Item` does not pass through any
adapter-specific discovery enrichment (e.g. github_org's `extra={"repo","default_branch",
"commit_sha"}`). For a `--slug repo:path` github_org invocation, `render` needs `repo`,
`default_branch`, and `commit_sha` in `Item.extra`, which the synthetic item lacks. 03 §--slug
says it works for all three platforms, but the architecture does not specify how a single
github_org item acquires its `default_branch`/`commit_sha` without the discovery pass.
Affected: 02 (control flow), 03 (--slug semantics), 04 (Slice 4 render contract).
Severity: **MINOR** — `--slug` is a smoke-test path; readme_io and docusaurus are unaffected;
github_org `--slug` is an edge use. Recommend a one-line spec note: github_org `--slug` must
do a lightweight per-repo API lookup, or `--slug` is documented as readme_io/docusaurus-only.

---

## Part 4 — Requirements → UI (CLI) coverage

03 correctly establishes there is no GUI; the CLI contract is the UI surface.

| User-facing requirement | CLI coverage | Status |
|---|---|---|
| FR-19 `--target` | §Flags --target (required, exit 2 if absent) | ✅ |
| FR-19 `--discover` | §Flags --discover + Flow 2 + stdout format | ✅ |
| FR-19 `--slug`/`--single` | §Flags --slug/--single (aliases) + Flow 3 | ✅ (see G-1 for github_org) |
| FR-19 `--no-discover` | §Flags --no-discover + Flow 5 | ✅ |
| FR-19 `--limit N` (new) | §Flags --limit + Flow 4 | ✅ |
| NFR-4 partial-failure visibility | §Partial failure policy + per-item error lines + exit codes | ✅ |
| FR-17 manifest surfacing | §manifest.json + §State visibility | ✅ |
| Fast-fail edge cases (01 edge table) | §Fast-fail conditions (sitemap, zero items, empty fallback) | ✅ |

**Flag-consistency cross-check (01 FR-19 ↔ 03 ↔ 02 cli.py):** All five flags
(`--target`, `--discover`, `--slug`/`--single`, `--no-discover`, `--limit`) appear in all
three docs. 03 §Consistency note #1 itself flags that 02's `cli.py` comment lists only
`--slug` (not the `--single` alias) and instructs argparse to accept both — this is a
self-caught doc-comment nit, already resolved in 04 Slice 1 (`--slug`/`--single` (aliases)).
Consistent. No new gap.

---

## Part 5 — Architecture/UI → Roadmap coverage

| Component (02/03) | Slice | Status |
|---|---|---|
| `config.py` (TargetConfig, load_target) | Slice 1 | ✅ |
| `core.py` trio + discover_slugs | Slice 1 | ✅ |
| `slugify.py` (C2) | Slice 1 | ✅ |
| `emit.py` atomic writes (S3) + single-file | Slice 1 | ✅ |
| `adapters/base.py` ABC + dataclasses | Slice 1 | ✅ |
| `adapters/__init__.py` registry | Slice 1 (stub); 2/3/4 add entries | ✅ |
| `runner.py` control flow | Slice 1 | ✅ |
| `cli.py` argparse + exit codes | Slice 1 | ✅ |
| `htmlmd.py` | Slice 3 (after S2 spike) | ✅ |
| `adapters/readme_io.py` | Slice 2 | ✅ |
| `adapters/docusaurus.py` | Slice 3 | ✅ |
| `adapters/github_org.py` | Slice 4 | ✅ |
| G1 fixtures + offline test | C3 (capture) + Slice 2 (test) | ✅ |
| AC-1 assertion harness | S1 | ✅ |
| Second-target AC-4 proof | Slice 5 | ✅ |
| Seed deletion (after G1) | Slice 5 | ✅ |

**Roadmap slice-exit AC-ID check (adversarial):** every cited AC ID is real and matches 01.
- Slice 1 → C2 (slugify), S3 (emit) — infra, no AC claim beyond unit tests. ✅
- Slice 2 → AC-3a/3b/3c, FR-16a. ✅
- Slice 3 → AC-1a/1b/1c/1d, AC-1e (manual). ✅
- Slice 4 → AC-2, AC-1a/1c/1d. ✅
- Slice 5 → AC-4 + roll-up of AC-1*, AC-2, AC-3*. ✅
No phantom AC IDs; no AC ID is orphaned (every AC-1..AC-4, including sub-IDs, is exercised by
a slice). Dependency map has no cycles; C3 blocks Slice 2, S1 gates 3/4, S2 blocks 3, seed
deletion gated on G1.

---

## Part 6 — Scope-creep audit (Mode-2 / snapshot-store)

No creep found. Affirmative scope-boundary statements exist in all four docs:
- 01 NFR-6 + Out-of-scope (Mode-2, snapshot store, dedup, downstream).
- 02 §What this does NOT add (no snapshot store, no reconcile, output regenerated each run).
- 03 explicitly states config-driven, no interactive/stateful surface; each run overwrites.
- 04 §Deferred (Mode-2, G2, downstream, snapshot retention).
`git_ref` and `content_hash` are present but correctly framed as *enablers for a downstream
consumer*, not as in-tool dedup/diff. This is the right side of the boundary.

---

## Part 7 — New gaps introduced by the revision

The revision (FR-4a/4b split, slugify scheme, fixtures, atomic emit) introduced no
structural regressions. Two items below are the only newly-surfaced gaps; both minor.

- **G-1** (above) — github_org `--slug` single-item path lacks discovery enrichment.
- **W-1** (below) — AC-3b heading-parity may degrade to a shape-only / synthetic check.

---

## Gaps table

| # | Gap | Affected doc(s) | Severity | Recommended owner |
|---|---|---|---|---|
| G-1 | github_org `--slug repo:path` single-item path bypasses discovery; synthetic `Item` lacks `default_branch`/`commit_sha` needed by `render`. No spec for how it acquires them. | 02 (control flow), 03 (--slug), 04 (Slice 4) | MINOR | architecture (one-line note) or fabric (restrict `--slug` to readme_io/docusaurus) |
| G-2 | DDR-01's *binding* G2 gate is deferred; AC-4 substitutes a cross-platform no-code-change proof. Substitution is reasonable and documented but should be explicitly ratified, since G2 is the binding gate in DDR-01. | 01 Out-of-scope, 04 Deferred | MINOR | human/architect ratification |
| W-1 | AC-3b/C3 live-parity can degrade: roadmap permits synthetic fixtures + a "mock approach"/"shape-only" heading comparison if `askedgar.readme.io` is unreachable at capture. Offline *mechanism* is intact, but the *parity guarantee* (verbatim lift didn't break the core) weakens to a smoke check in that branch. | 04 C3 fallback, Slice 2 notes; 01 AC-3b assumption | WATCH | fabric — must record in PROGRESS.md whether fixtures are live-captured or synthetic; if synthetic, flag G1 as not fully discharged |

No HIGH or BLOCKING gaps.

---

## Identified risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `askedgar.readme.io` unreachable before seed deletion → G1 captured synthetically, parity unproven | M | H | Roadmap fallback exists; W-1 requires PROGRESS.md disclosure. Capture fixtures (C3) as early as possible (right after Slice 0); do NOT delete seed (Slice 5) until live G1 confirmed. |
| markdownify version lacks `code_language_callback` | M | M | S2 spike (time-boxed) confirms approach before Slice 3; subclass fallback specified. Closed by design. |
| Docusaurus drops SSR / requires JS (FR-7 assumption) | L | H | 01 Constraints flags it as a revision trigger; AC-1b/AC-1e would surface empty content; would require adding browser to docusaurus adapter. |
| `docs.thatopen.com/sitemap.xml` not authoritative / paginated sitemap index | L | M | 01 assumption stated; edge case "zero/unreachable sitemap" fast-fails. Watch for sitemap-index (nested) format not handled by simple `<loc>` parse. |
| GitHub unauthenticated 60 req/hr limit hit (no gh/GITHUB_TOKEN) | M | M | 04 Slice 4 logs warning + continues; 15 repos × few calls may fit, but trees+commits per repo can approach the limit. Acceptable for proving target; note in PROGRESS.md. |
| Path-length guard (200-byte) interaction with deeply nested `/api/@scope/...` TypeDoc URLs producing many collisions | L | M | slugify Step-4/Step-5 handle via hash suffix; covered by Slice 1 unit tests. |

---

## Assumptions

| Assumption | Impact if wrong |
|---|---|
| Seed `get_main`/`extract_sections`/`render_sections` are lift-clean (no hidden askedgar coupling) | G1 may pass while core stays coupled; DDR-01 itself warns G1 is necessary-not-sufficient. AC-4 partially compensates. |
| `docs.thatopen.com` is SSR (no JS) | FR-7 (urllib, no browser) breaks; docusaurus adapter would need Playwright. |
| `gh` CLI authenticated or `GITHUB_TOKEN` present | github_org runs rate-limited; full-org run may not complete in one pass. |
| AskEdgar fixture captured live before seed deletion | W-1: G1 parity becomes a shape-only check. |
| markdownify ≥0.12 exposes the code-language callback | S2 spike resolves; subclass fallback ready. |
| Single sitemap (not a sitemap index) at the configured URL | Discovery undercounts; simple `<loc>` parse may miss nested sitemaps. |

---

## Open questions

| Question | Status | Resolution needed from |
|---|---|---|
| Is deferring DDR-01's binding G2 gate (substituting AC-4) acceptable for this pass? | Open | human / architect (Meridian) |
| Should github_org support `--slug`, or is single-item mode readme_io/docusaurus-only? (G-1) | Open | architect / fabric |
| If AskEdgar is unreachable at capture, is a synthetic-fixture G1 acceptable to ship, or is live capture a hard precondition? (W-1) | Open | human / Frank |
| Does the Docusaurus sitemap need sitemap-index (nested) handling, or is it a single flat sitemap? | Open | fabric (verify during S2/Slice 3) |

---

## Approval checklist

### Requirements (01)
- [ ] Reviewed by human
- [ ] Acceptance criteria testable (AC-1a..d mechanizable; AC-3a..c offline — confirmed)
- [ ] Out-of-scope acceptable (Mode-2/G2 deferral ratified — see open questions)

### Architecture (02)
- [ ] Reviewed by human
- [ ] Patterns appropriate (adapter ABC, strategy, atomic write, slug-before-render)
- [ ] Schemas correct (front-matter FR-16a, manifest, slugify interface)
- [ ] G-1 (github_org `--slug` enrichment) resolved or scoped out

### UI Spec (03)
- [ ] Reviewed by human
- [ ] Flag set matches FR-19 and cli.py (confirmed; `--single` alias noted)
- [ ] Exit-code + partial-failure policy acceptable

### Roadmap (04)
- [ ] Reviewed by human
- [ ] Sequence correct (no cycles; C3→Slice2, S1→3/4, S2→3, G1→seed deletion)
- [ ] Slices appropriately sized; every AC ID traced to a slice exit

### Overall
- [ ] G-2 (G2-vs-AC-4) ratified
- [ ] W-1 (live-vs-synthetic G1) policy decided
- [ ] All open questions resolved
- [ ] Ready for forge

---

## Readiness statement

The spec package is **internally consistent, fully traceable to DDR-02, and free of
blocking gaps**. All seven prior QC findings (C1–C3, S1–S4) are independently confirmed
CLOSED with doc citations — not merely asserted. There is no Mode-2 / snapshot-store scope
creep; the DDR-01 G1 gate is concretely defined and offline-reproducible; the DDR-01 G2
gate is deferred with a documented AC-4 substitute.

Two MINOR gaps (G-1 github_org `--slug` enrichment; G-2 G2-gate substitution ratification)
and one WATCH item (W-1 live-vs-synthetic G1 fixture) remain. None blocks forge; all are
recorded above with severity and owner. **This package is READY FOR FRANK** (binding QC),
with the four open questions surfaced for human decision before "proceed to forge."
