---
name: article-knowledge-manager
description: Save articles into Feishu Bitable, search article knowledge, and generate structured reference packs for humans or other AI agents.
metadata: {"clawdbot":{"requires":{"bins":["python3","node"],"files":["/etc/openclaw/article-knowledge-manager-yangzai3.env"]}}}
---

# Article Knowledge Manager

Use this skill when the user wants to:

- collect an article link into the knowledge base
- save title, source, summary, keywords, and tags for an article
- search for article knowledge by topic, keyword, source, or use case
- generate a machine-readable reference pack for another agent

Typical triggers:

- "收藏这篇文章"
- "把这个链接收进知识库"
- "帮我找 banana 相关文章"
- "给我一包参考文章"
- "把这些文章整理给另一个 AI 用"

## Routing Priority

When the request is clearly article retrieval, run this skill first instead of generic Feishu tools.

- inspiration query (`找...相关知识`, `给我点启发`) -> run `--search`
- handoff to another AI (`给另一个AI`, `做参考包`) -> run `--reference-pack`
- direct save request with link (`收藏这篇`, `归档这个链接`) -> run `--save-article` or let `wechat-article-capture` ingest first

Fallback policy:

- only use generic Feishu search when this skill command fails or table fields are unavailable

## Portability

This skill is intentionally portable:

- logic lives in the shared skills repo
- runtime secrets live in an env file
- Feishu app credentials come from the active OpenClaw profile
- table names and table IDs can be reattached on another machine

Recommended env file:

```bash
/etc/openclaw/article-knowledge-manager-yangzai3.env
```

Portable template:

```bash
env.example
```

Recommended env values:

- `OPENCLAW_PROFILE=yangzai3`
- `ARTICLE_KNOWLEDGE_SOURCE_NAME='阳仔3号（知识库）'`
- `FEISHU_BITABLE_APP_TOKEN='<base app token>'`
- `FEISHU_BITABLE_TABLE_NAME='文章库'`
- `FEISHU_BITABLE_TABLE_ID='<article table id>'`
- `FEISHU_BITABLE_USER_OPEN_ID='<owner open id>'`
- `TOTAL_INDEX_TABLE_NAME='内容总表'`
- `TOTAL_INDEX_TABLE_ID='<total index table id>'`

## Main Commands

Show configuration and table reachability:

```bash
python3 scripts/article_knowledge_manager.py --env-path /etc/openclaw/article-knowledge-manager-yangzai3.env --show-status --json
```

Save one article and sync it into the total index:

```bash
python3 scripts/article_knowledge_manager.py \
  --env-path /etc/openclaw/article-knowledge-manager-yangzai3.env \
  --save-article \
  --url "https://example.com/post" \
  --title "Example article" \
  --summary "One paragraph summary" \
  --author "Nano Banana" \
  --keywords "banana,image,prompt" \
  --tags "AI,灵感" \
  --category "AI文章" \
  --use-cases "写文章,PPT,找灵感" \
  --reference-value 高 \
  --sync-to-total-index \
  --json
```

Search article knowledge for a human-readable answer:

```bash
python3 scripts/article_knowledge_manager.py --env-path /etc/openclaw/article-knowledge-manager-yangzai3.env --search "banana" --limit 5 --json
```

Generate a structured reference pack for another bot or agent:

```bash
python3 scripts/article_knowledge_manager.py --env-path /etc/openclaw/article-knowledge-manager-yangzai3.env --reference-pack "banana" --limit 5 --json
```

Fast inspiration lookup (owner-facing):

```bash
python3 scripts/article_knowledge_manager.py --env-path /etc/openclaw/article-knowledge-manager-yangzai3.env --search "banana" --limit 5 --json
```

## Output Modes

- Human mode:
  - title
  - short summary
  - tags or keywords
  - original link

- Machine mode:
  - `title`
  - `url`
  - `source`
  - `publishedAt`
  - `summary`
  - `corePoints`
  - `keywords`
  - `category`
  - `tags`
  - `useCases`
  - `referenceValue`
  - `relevanceReason`

## Behavioral Rules

- Prefer saving articles into `文章库` and syncing an index row into `内容总表`.
- When the user wants inspiration, return summaries first and links second.
- When another AI needs references, return a structured reference pack instead of prose.
- Never print or export app tokens, user tokens, or private API keys.
- Keep the workflow machine-portable so it can be reattached to a future Mac mini runtime.
