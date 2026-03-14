# openclawskills

Personal but reusable OpenClaw skills repository for a multi-agent "lobster team" setup.

Chinese version:

- [README.zh-CN.md](README.zh-CN.md)

## What this repo is

This repository stores the portable parts of an OpenClaw production setup:

- reusable skills under `skills/`
- shared operating context under `shared-awareness/`
- workspace seed files under `workspace-seeds/`

It is meant to support a role-based OpenClaw architecture where:

- `main` orchestrates
- `info` retrieves current public information
- `knowledge` stores and retrieves long-term material
- `writer` produces content
- `rescue` handles health checks and recovery

## Naming convention

Skills prefixed with `BLY-` are custom skills built for this architecture.

Examples:

- `BLY-info-search-planner`
- `BLY-info-search-executor`
- `BLY-info-source-verifier`
- `BLY-info-news-verifier`
- `BLY-info-evidence-pack`

That prefix makes it easy to distinguish:

- custom in-house skills
- imported or adapted external skills

## Current skills

### Main orchestration

- `BLY-main-router`
  - intent classification and structured dispatch ticket for `main`; routing only, no execution

### Info and retrieval

- `BLY-info-search-planner`
  - turns vague retrieval requests into structured query packs
- `BLY-info-search-executor`
  - prefers Metaso discovery (if configured), then `web_fetch`, with DDG only as fallback
- `BLY-info-source-verifier`
  - grades sources by authority and decides whether evidence is strong enough
- `BLY-info-news-verifier`
  - checks publish date vs event date for latest/current/news queries
- `BLY-info-evidence-pack`
  - hands structured evidence to `main` or `writer`
- `gold-rmb-realtime`
  - gold quote workflow with RMB conversion and alert-friendly output
- `x-monitor`
  - X/Twitter account monitoring workflow

### Knowledge and archive

- `wechat-article-capture`
  - captures and archives article content into the knowledge layer
- `article-knowledge-manager`
  - article-level retrieval and archive management
- `knowledge-base-manager`
  - general knowledge-base maintenance and retrieval support

### Writing and delivery

- `general-material-pack`
  - concise practical material-pack and short-article writing workflow
- `feishu-cloud-doc`
  - Feishu cloud document creation and update workflow
- `runninghub-image`
  - image generation workflow for the writer role

### Operations

- `lobster-supervisor`
  - health checks, service checks, timer checks, and recovery support

### Shared helpers

- `common/`
  - shared helper scripts used by multiple skills

## Repository layout

```text
openclawskills/
├─ skills/
│  ├─ BLY-info-search-planner/
│  ├─ BLY-info-search-executor/
│  ├─ BLY-info-source-verifier/
│  ├─ BLY-info-news-verifier/
│  ├─ BLY-info-evidence-pack/
│  ├─ BLY-main-router/
│  ├─ general-material-pack/
│  ├─ feishu-cloud-doc/
│  ├─ runninghub-image/
│  ├─ article-knowledge-manager/
│  ├─ knowledge-base-manager/
│  ├─ wechat-article-capture/
│  ├─ gold-rmb-realtime/
│  ├─ x-monitor/
│  ├─ lobster-supervisor/
│  └─ common/
├─ shared-awareness/
└─ workspace-seeds/
```

## Architecture notes

### Recommended role split

- `main`: routing, orchestration, final answer assembly
- `info`: current external search only, no archiving
- `knowledge`: archive, deduplication, long-term memory
- `writer`: drafting, rewriting, document/image delivery
- `rescue`: watchdog, health, repair

### Recommended retrieval chain for `info`

Use this order for open-web retrieval:

1. `BLY-info-search-planner`
2. `BLY-info-search-executor`
3. `BLY-info-source-verifier`
4. `BLY-info-news-verifier` for date-sensitive requests
5. `BLY-info-evidence-pack`

### Recommended execution policy

- prefer built-in `web_search` first
- use `web_fetch` to read the selected candidate pages
- use DDG only as fallback
- do not use domestic general search engines as default sources
- prefer official docs, official repos, official announcements, and strong international media
- when evidence is weak, say so explicitly

## How to use this repo on a new machine

### Option 1: clone the whole repo

```bash
git clone https://github.com/buliyang0407/openclawskills.git
```

Then copy the needed skills into your OpenClaw workspace:

```bash
mkdir -p /path/to/openclaw/workspace/skills
cp -r openclawskills/skills/BLY-info-search-planner /path/to/openclaw/workspace/skills/
cp -r openclawskills/skills/BLY-info-search-executor /path/to/openclaw/workspace/skills/
cp -r openclawskills/skills/BLY-info-source-verifier /path/to/openclaw/workspace/skills/
cp -r openclawskills/skills/BLY-info-news-verifier /path/to/openclaw/workspace/skills/
cp -r openclawskills/skills/BLY-info-evidence-pack /path/to/openclaw/workspace/skills/
```

### Option 2: use only selected skills

Example:

```bash
mkdir -p /path/to/openclaw/workspace/skills/BLY-info-search-planner
cp -r skills/BLY-info-search-planner/* /path/to/openclaw/workspace/skills/BLY-info-search-planner/
```

## Portable vs non-portable parts

This repository intentionally keeps the portable layer only.

Included:

- `SKILL.md`
- `scripts/`
- `templates/`
- `references/`
- workspace seeds
- shared awareness files

Excluded:

- `/etc/openclaw/*.env`
- tokens, secrets, app secrets, private keys
- host-specific delivery targets
- production-only runtime state

## Validation

Some custom info skills include lightweight local evals and self-tests.

Example:

```bash
python skills/BLY-info-suite-selftest.py
```

This checks:

- frontmatter name consistency
- presence of workflow/output sections
- template presence
- minimum eval coverage

## Suggested roadmap

- keep adding `BLY-*` skills for routing, retrieval, writing, and review
- keep production-specific secrets outside the repo
- prefer small, composable skills over one giant universal skill

## Why this repo exists

The goal is simple:

- make a real OpenClaw production setup portable
- make custom skills easy to reuse on future hardware
- make the "lobster team" architecture understandable to others

If any part of this is useful, a star is always appreciated.
