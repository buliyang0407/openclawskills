---
name: BLY-main-router
description: Use this skill whenever the main worker needs to classify a user request and produce a structured dispatch ticket without executing business work. Trigger for normal natural-language requests that may require info, knowledge, writer, rescue, article ingest, or mixed routing. Keep hard-coded high-stability workflows (gold quote, article ingest command, fleet/monitor checks) as first-pass guardrails, then use this skill for general routing.
---

# BLY Main Router

This skill is the routing brain for `main`.

It does one job only:

- classify intent
- choose route
- return a strict JSON dispatch ticket

It does not execute search, writing, archive, or ops checks.

## Role boundary

`BLY-main-router` must never:

- call `info` tools directly
- call `knowledge` storage directly
- write final article content
- perform ops recovery actions

It only decides who should do the work next.

## Allowed intent classes

Exactly one of:

- `info_query`
- `knowledge_query`
- `write_request`
- `ops_request`
- `article_ingest`
- `mixed_request`
- `uncertain`

## Allowed routes

Route must be one of:

- `["info"]`
- `["knowledge"]`
- `["writer"]`
- `["rescue"]`
- `["knowledge", "writer"]`
- `["info", "writer"]`
- `["knowledge", "info", "writer"]`

For `uncertain`, route should be the smallest safe starter route:

- default `["info"]` for open-web clarification
- or `["knowledge"]` if the user clearly asks "previously archived / historical"

## Router workflow

### Step 1: Apply hard-rule guardrails first

Before natural-language routing, detect high-stability command-style requests:

- gold quote / gold-rmb realtime
- article ingest by explicit URL
- x monitor status
- fleet health / rescue checks

If a hard rule matches, emit corresponding intent and route directly with high confidence.

### Step 2: Classify user intent

Identify the primary job to be done.

Heuristics:

- asks for latest/current/public info -> `info_query`
- asks for archived/history/internal memory -> `knowledge_query`
- asks to write/draft/rewrite/content produce -> `write_request`
- asks system health/recovery/status -> `ops_request`
- asks to ingest/archive a specific article URL -> `article_ingest`
- asks for both retrieval and writing in one request -> `mixed_request`
- cannot safely classify -> `uncertain`

### Step 3: Derive flags

Set boolean flags:

- `needs_latest`
- `needs_history`
- `needs_writing`
- `needs_ops`
- `needs_doc_output`
- `should_fallback_local`

`should_fallback_local` should be `true` only when the request is a known hard-rule path with a local fallback chain.

### Step 4: Choose route

Route by intent:

- `info_query` -> `["info"]`
- `knowledge_query` -> `["knowledge"]`
- `write_request`:
  - if needs history and latest -> `["knowledge", "info", "writer"]`
  - if only latest/public supplement -> `["info", "writer"]`
  - otherwise -> `["knowledge", "writer"]`
- `ops_request` -> `["rescue"]`
- `article_ingest` -> `["knowledge"]`
- `mixed_request` -> choose shortest complete chain, prefer:
  - `["knowledge", "info", "writer"]`
- `uncertain` -> smallest safe starter route

### Step 5: Emit strict JSON

Return a single JSON object. No markdown, no prose wrapper.

## Output schema

```json
{
  "intent": "info_query|knowledge_query|write_request|ops_request|article_ingest|mixed_request|uncertain",
  "route": ["info|knowledge|writer|rescue", "..."],
  "needs_latest": true,
  "needs_history": false,
  "needs_writing": false,
  "needs_ops": false,
  "needs_doc_output": false,
  "should_fallback_local": false,
  "confidence": 0.0,
  "reason": "short reason in Chinese"
}
```

Rules:

- `confidence` range: `0.00` to `1.00`
- keep `reason` within 40 Chinese characters when possible
- route must follow allowed-route list

## Coexistence policy (important)

This skill is for progressive rollout, not big-bang replacement.

Recommended mode:

1. keep existing hard-coded rules for critical stable commands
2. call `BLY-main-router` for all other natural-language requests
3. execute selected chain in existing workflow engine
4. log router output for audit and future tuning

## Red lines

Do not:

- return free-form explanation instead of JSON
- output unknown intent labels
- output unknown route roles
- bypass hard-rule paths when an explicit command match exists
- make this skill perform worker duties

## Templates and tests

Use [router-dispatch-template.json](templates/router-dispatch-template.json) as output scaffold.

Evaluation prompts live in [evals.json](evals/evals.json).
