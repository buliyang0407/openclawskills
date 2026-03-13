---
name: knowledge-base-manager
description: Manage a lightweight Feishu Bitable knowledge base for archived summaries, manual saves, recent lookups, and keyword retrieval across Yangzai bots.
metadata: {"clawdbot":{"requires":{"bins":["python3","openclaw","node"],"files":["/etc/openclaw/knowledge-base-manager-yangzai3.env"]}}}
---

# Knowledge Base Manager

Use this skill when the user wants to:
- manage a shared knowledge base for X summaries, WeChat summaries, manual saves, and ops notes
- add one manual knowledge item into Feishu Bitable
- search recent archived content by keyword, source, or date
- inspect whether the knowledge-base bot is configured correctly
- archive a public-article link the user just sent

## Runtime Files

Environment file:

```bash
/etc/openclaw/knowledge-base-manager-yangzai3.env
```

Portable template:

```bash
env.example
```

Canonical script:

```bash
python3 /root/.openclaw-yangzai3/workspace/skills/knowledge-base-manager/scripts/knowledge_base_manager.py
```

## Main Commands

Show current configuration and table reachability:

```bash
python3 /root/.openclaw/workspace/skills/knowledge-base-manager/scripts/knowledge_base_manager.py --env-path /etc/openclaw/knowledge-base-manager-yangzai3.env --show-status
```

Add one manual entry:

```bash
python3 /root/.openclaw/workspace/skills/knowledge-base-manager/scripts/knowledge_base_manager.py --env-path /etc/openclaw/knowledge-base-manager-yangzai3.env --add-manual --title "某条结论" --summary "为什么重要" --source-type 资产 --source-channel 手工录入 --source-name 步力阳 --tags AI,知识库 --importance 高 --source-url "https://example.com"
```

List the newest entries:

```bash
python3 /root/.openclaw/workspace/skills/knowledge-base-manager/scripts/knowledge_base_manager.py --env-path /etc/openclaw/knowledge-base-manager-yangzai3.env --recent --limit 10
```

Search by keyword:

```bash
python3 /root/.openclaw/workspace/skills/knowledge-base-manager/scripts/knowledge_base_manager.py --env-path /etc/openclaw/knowledge-base-manager-yangzai3.env --search "gold"
```

## Routing Rule For Public Articles

If the user sends a `mp.weixin.qq.com` article link or clearly asks to archive a public WeChat article:

- prefer `wechat-article-capture`
- let it fetch the body, summarize, tag, and save
- then keep `knowledge-base-manager` focused on total-index compatibility and cross-source retrieval

Do not ask the user to paste the article body first if `wechat-article-capture` is available in the current session.

## Required Environment

- `FEISHU_BITABLE_APP_TOKEN`
- `FEISHU_BITABLE_TABLE_ID` or `FEISHU_BITABLE_TABLE_NAME`

Optional environment:

- `OPENCLAW_PROFILE`
- `OPENCLAW_CONFIG_PATH`
- `KNOWLEDGE_BASE_ENV_PATH`
- `KNOWLEDGE_BASE_SOURCE_NAME`
- `FEISHU_BITABLE_USER_OPEN_ID`

## Recommended Main Table Fields

- `时间`
- `标题`
- `摘要`
- `来源类型`
- `来源渠道`
- `来源账号`
- `主题标签`
- `重要度`
- `是否已读`
- `是否收藏`
- `原链接`
- `归档时间`
- `摘要模型`
- `数据来源`

## Behavioral Rules

- Keep knowledge-base v1 lightweight: Bitable first, no local vector database.
- Reuse the official `feishu-openclaw-plugin` user authorization path.
- Never print or export app tokens, user tokens, or private API keys.
- Prefer shared schema compatibility so Yangzai, Yangzai2, and Yangzai3 can write to the same archive structure over time.
