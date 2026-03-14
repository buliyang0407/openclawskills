# BLY-main-router Coexistence Integration (Minimal Risk)

This note describes how to introduce `BLY-main-router` without replacing stable production paths.

## Phase 1: Shadow + gated execution

1. Keep hard rules as-is for:
- gold quote
- article ingest with explicit URL
- x/wechat monitor status
- fleet health checks

2. For all other requests:
- call `BLY-main-router`
- parse strict JSON output
- run existing workflow command by `intent`/`route`

3. If router output is invalid:
- fall back to legacy keyword router
- log incident with original request + raw router text

## Phase 2: Router-first for general NL requests

1. Keep only critical hard rules in front.
2. Route normal natural-language requests by `BLY-main-router`.
3. Keep legacy keyword logic as emergency fallback only.

## Suggested mapping in owner workflow

- `intent=info_query` -> `task_info_query`
- `intent=knowledge_query` -> `task_knowledge_query`
- `intent=write_request`:
  - route `knowledge->writer` -> `task_write_material` (default)
  - route includes `info` -> `task_write_material --force-info`
- `intent=ops_request` -> `task_fleet_status` or related status task
- `intent=article_ingest` -> `task_article_ingest`
- `intent=mixed_request` -> `task_write_material --force-info`
- `intent=uncertain` -> start from `task_info_query` with explicit caution

## Acceptance checks before production cutover

- Router output JSON parse success >= 98%
- No regression on hard-rule commands
- No cross-role boundary violations (router must not execute work)
- `uncertain` rate monitored and trending down
