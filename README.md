# api-doc-scraper

A config-driven scraper for **ReadMe.io-hosted API documentation**. It renders each
endpoint's reference page with a headless browser, flattens the parameter and
response schema to markdown, and writes a single snapshot file you can diff against
a locally maintained source-of-truth doc.

## Why this exists

The point is **documentation drift detection**, not scraping for its own sake. You
keep a hand-maintained API doc; APIs change; this tool produces a clean markdown
snapshot of the *live* docs so you can gap-check the two and catch what moved. In its
first use (against AskEdgar) it surfaced a swapped response-field pair, a renamed
endpoint masquerading as a new one, and tier-gated endpoints.

## Status

**Seeded, not yet built.** The original working AskEdgar-specific scraper is in
`seed/scrape_askedgar_reference.py`. The generalization into a config-driven
`scraper/` package is described in **[PLAN.md](./PLAN.md)** — start there.

## Quick start (seed, today)

```bash
pip install playwright beautifulsoup4
playwright install chromium

python seed/scrape_askedgar_reference.py --discover   # list endpoint slugs
python seed/scrape_askedgar_reference.py              # full scrape -> docs/askedgar-reference-raw.md
```

## Intended usage (after generalization — see PLAN.md)

```bash
python -m scraper.cli --target askedgar --discover
python -m scraper.cli --target askedgar
```

Add a new ReadMe.io site by dropping a `targets/<name>.yaml` file — see
`targets/askedgar.yaml` for the shape. No code change needed for another ReadMe.io
site.

## Scope boundary

Works for **ReadMe.io docs only**. Swagger/OpenAPI, GitBook, Mintlify, and
hand-built doc sites have different DOM and discovery models; supporting them means
adding per-platform adapters — out of scope for the current pass. See PLAN.md §8.
