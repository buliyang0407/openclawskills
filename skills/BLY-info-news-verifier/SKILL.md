---
name: BLY-info-news-verifier
description: Use this skill whenever the info worker handles date-sensitive information such as latest news, current events, recent developments, breaking updates, geopolitical changes, or anything the user phrases as "现在", "最近", "今天", "最新", or "new". Trigger after source verification and before the final evidence pack so stale or mismatched timelines do not slip into the answer.
---

# BLY Info News Verifier

This skill protects date-sensitive retrieval from stale or mismatched timelines.

Use it for:

- current events
- latest news
- recent developments
- timelines
- geopolitical and market updates
- anything where publish date matters

## Core rule

For news, source quality is not enough.

You must also verify time relevance.

## Verification workflow

### Step 1: Extract dates

For each surviving source, capture:

- publish date if visible
- event date if visible
- whether the page is clearly recent or just indexed recently

If the date is unclear, mark it as unclear instead of assuming.

### Step 2: Distinguish article date from event date

Do not confuse:

- when the article was published
- when the event actually happened

If a source describes older background in a newly published article, say so.

### Step 3: Cross-check recency

For "latest" or "recent" requests, prefer:

- multiple independent recent sources
- at least one official statement when available
- a timeline that makes chronological sense

### Step 4: Detect stale or misleading coverage

Flag the result if:

- only old articles are available
- dates conflict
- the supposed "latest" point is actually background
- a source recycles older reporting without a new event

### Step 5: Produce a timeline-safe judgment

Return one of:

- `time_safe`
- `time_sensitive_use_caution`
- `time_not_safe`

Use `time_not_safe` when the answer risks presenting stale material as current.

## Output format

Always return:

```text
topic:

dated_sources:
- title:
  domain:
  published_at:
  event_date:
  recency_status:
  note:

timeline_summary:
- ...

time_judgment:
- time_safe / time_sensitive_use_caution / time_not_safe

date_risks:
- ...
```

## Red lines

Do not:

- present undated material as current
- turn background context into breaking news
- answer a "latest" request with old evidence without warning

## Templates and tests

Use [news-timeline-template.md](templates/news-timeline-template.md) for structured output.

The evaluation prompts for this skill live in [evals.json](evals/evals.json).
