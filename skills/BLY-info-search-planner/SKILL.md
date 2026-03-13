---
name: BLY-info-search-planner
description: Use this skill whenever the info worker needs to turn a vague external-information request into a disciplined search plan. Trigger for requests like "查一下这是什么", "搜搜最近有没有消息", "帮我找官方资料", "看看网上怎么说", product/project/person/company lookups, and any case where the first search query is likely too shallow. Prefer this skill before web-search so the info worker searches with intent instead of guessing.
---

# BLY Info Search Planner

This skill is the planning brain for the info worker.

Use it before running web search when the task is not a simple one-shot factual lookup.

The goal is to produce a compact query pack that:

- identifies what kind of thing we are looking for
- expands the query into better search angles
- prioritizes official sources
- prevents shallow "search once and improvise" behavior

## When to use it

Use this skill for:

- product / tool / model introductions
- company / team / project lookups
- person / organization background checks
- recent-news or trend summaries
- ambiguous topics that may have multiple meanings
- any request where "just search the phrase once" is likely to fail

Skip this skill only for:

- direct local workflows with dedicated skills, such as gold quote or X monitor status
- trivial one-line factual lookups where the entity is already unambiguous and stable

## Core rule

The first query is almost never enough.

Always produce a query pack before external search unless a local dedicated workflow already answers the request.

## Planner workflow

### Step 1: Classify the lookup

First decide which lookup pattern fits best:

- `product_or_tool`
- `person`
- `company_or_org`
- `project_or_repo`
- `news_or_event`
- `technical_doc`
- `ambiguous_unknown`

If unsure, choose `ambiguous_unknown` and widen the search pack.

### Step 2: Extract the search core

Write down:

- canonical topic string
- possible English form
- possible Chinese form
- abbreviations or aliases
- context clues from the user request

Do not invent aliases. Only include plausible variants.

### Step 3: Build query lanes

Create queries in lanes instead of one flat list.

Always include these lanes when relevant:

1. `official`
2. `definition`
3. `release_or_news`
4. `docs_or_repo`
5. `trusted_media`
6. `disambiguation`

For example, a product/tool query pack should usually include:

- `<topic> official`
- `<topic> docs`
- `<topic> github`
- `<topic> release`
- `<topic> what is`
- `<topic> announcement`
- `site:github.com <topic>`
- `site:docs.* <topic>`

For news/event topics, prefer:

- `<topic> latest`
- `<topic> statement`
- `<topic> official`
- `<topic> timeline`
- `<topic> Reuters`
- `<topic> AP News`

### Step 4: Decide source priorities

Set the intended priority before search:

- first: official site / docs / official repo / official account
- second: trusted media or technical publications
- third: community discussion and low-trust discussion

Search engines are discovery tools, not final evidence.

### Step 5: Define stop conditions

Before search begins, decide what counts as "not enough evidence".

Typical stop conditions:

- no official source found
- only vague aggregator hits
- search results are about multiple unrelated meanings
- no page clearly answers "what is it"

If stop conditions are hit, the info worker must return a low-confidence result instead of pretending to know.

## Output format

Always return a compact query pack using this structure:

```text
topic:
lookup_type:
goal:

query_lanes:
- official:
  - ...
- definition:
  - ...
- release_or_news:
  - ...
- docs_or_repo:
  - ...
- trusted_media:
  - ...
- disambiguation:
  - ...

source_priority:
- official
- trusted_media
- community

stop_conditions:
- ...
- ...
```

If a lane does not apply, omit it instead of padding.

## Anti-patterns

Do not:

- run only one literal query
- treat search engines as evidence
- skip official-source discovery
- search only Chinese aggregators
- jump straight to writing assumptions

## Good outcome

A good query pack makes the next search step feel obvious:

- fast to execute
- easy to verify
- hard to hallucinate from

## Templates and tests

Use [query-pack-template.md](templates/query-pack-template.md) when you want a clean scaffold.

The test prompts for this skill live in [evals.json](evals/evals.json).
