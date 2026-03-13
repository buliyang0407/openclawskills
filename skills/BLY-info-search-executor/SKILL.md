---
name: BLY-info-search-executor
description: Use this skill whenever the info worker must actually execute open-web retrieval after planning queries. Trigger after BLY-info-search-planner produces a query pack, or whenever the user asks for external public information, latest developments, official docs, or source-backed background. Prefer built-in web_search first, then web_fetch for page reading, and use ddg-web-search only as a fallback when the stronger search path is unavailable or weak.
---

# BLY Info Search Executor

This skill is the execution layer for open-web retrieval.

It turns a query pack into usable candidate sources.

## Core rule

Use the strongest built-in search path first.

Default order:

1. `web_search`
2. `web_fetch`
3. `agent-browser` only when page interaction or rendered inspection is needed
4. `ddg-web-search` only as a fallback

## Why this order

- `web_search` is better for discovery and relevance than scraping a search-results page manually
- `web_fetch` is better for reading candidate pages once you know where to look
- `ddg-web-search` is useful as a resilient backup, not the preferred primary engine

## Execution workflow

### Step 1: Run the highest-value lanes first

Given a query pack, run in this order:

1. official
2. docs_or_repo
3. definition
4. trusted_media
5. release_or_news
6. disambiguation

Do not waste time on low-value lanes before checking official ones.

### Step 2: Use web_search for discovery

Use `web_search` on the first 2 to 4 highest-value queries.

What you want from discovery:

- official site
- official docs
- official repo
- official announcement
- clearly relevant trusted-media results

### Step 3: Use web_fetch to read likely candidates

Once candidate URLs exist, use `web_fetch` to read the actual pages.

Fetch selectively:

- official pages first
- then trusted media
- then one or two supporting pages if needed

Do not fetch a long tail of weak results just to pad evidence.

### Step 4: Use agent-browser only when needed

Use `agent-browser` only if:

- the page needs rendering or interaction
- a docs page hides content behind UI behavior
- the static fetch is incomplete or misleading

If `web_fetch` gives enough readable text, prefer it.

### Step 5: Fall back to ddg-web-search only if needed

Use `ddg-web-search` if:

- `web_search` is unavailable
- `web_search` returns weak or empty discovery
- you need a second discovery pass from a different route

Treat DDG results as discovery clues, not proof.

## Output format

Return a compact retrieval record:

```text
executed_queries:
- lane:
  query:
  method: web_search / ddg-web-search

candidate_sources:
- title:
  url:
  why_selected:
  fetch_status:

notes:
- ...
```

## Red lines

Do not:

- start with DDG if web_search is available
- fetch ten weak pages instead of three strong ones
- confuse search-result snippets with actual evidence
- use community pages before official pages for entity definition

## Templates and tests

Use [executor-record-template.md](templates/executor-record-template.md) as the standard scaffold.

The evaluation prompts for this skill live in [evals.json](evals/evals.json).
