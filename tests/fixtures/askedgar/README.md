# AskEdgar Fixture Files — SYNTHETIC

**Status: SYNTHETIC**

These fixture files were NOT captured from the live askedgar.readme.io site.
They were generated synthetically during the Slice 2 forge sprint.

## Why synthetic?

Live capture was attempted via `seed/capture_fixtures.py` on 2026-06-25 and failed
for two reasons:

1. **Browser launch failure:** Playwright Chromium shell (`chrome-headless-shell-linux64`)
   failed to start with `error while loading shared libraries: libnspr4.so: cannot
   open shared object file: No such file or directory`. The host WSL2 environment is
   missing NSS/NSPR libraries required by the Chromium headless shell.

2. **Site drift (known):** The seed URL `askedgar.readme.io/reference/health_check_health_get`
   was known to be 404-prone at forge time per the task brief.

Per the Slice 2 task brief: "Give live capture exactly ONE short attempt; if it fails
or drifts, fall back to synthetic fixtures, document the limitation, and MOVE ON."

## What the files contain

- `seed_page.html` — a minimal hand-crafted HTML page containing exactly the 3 synthetic
  `/reference/` links. `core.discover_slugs` parses this and returns the 3 canonical slugs.
- `slugs.json` — a 3-element JSON array of slug strings derived from the synthetic seed page.
- `headings.json` — heading sets derived by running `core.extract_sections` against
  per-slug stub HTML pages that mirror the ReadMe.io endpoint page structure
  (h1 title + h2 "Query Params" + h2 "Response/Responses").

## Test implications

- `test_slug_set_identity`: fully valid — the test feeds `seed_page.html` to
  `core.discover_slugs` and compares against `slugs.json`. Both are derived from the
  same HTML, so exact set equality is guaranteed.
- `test_heading_sets_match`: valid for structural consistency — the test compares
  `extract_sections` output against `headings.json`. Since headings.json was derived
  by running the same `extract_sections` function on equivalent stub HTML, structural
  shape is confirmed. Live parity against the real askedgar.readme.io pages is deferred.

## Recapture procedure

When Playwright is functional on this host (libnspr4.so available):
1. Run `PLAYWRIGHT_HOST_PLATFORM_OVERRIDE=ubuntu24.04-x64 python seed/capture_fixtures.py`
2. Replace these synthetic files with the captured files
3. Re-run `pytest tests/test_g1_regression.py` to confirm
4. Commit the real fixtures

G1 is designated NON-BLOCKING per the architect (Slice 2 task brief, 2026-06-25).
