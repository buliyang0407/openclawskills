---
name: wechat-article-capture
description: Capture WeChat official-account articles with a real browser, enrich them with AI summaries and tags, and save or backfill them into Yangzai3's article knowledge base.
metadata: {"clawdbot":{"requires":{"bins":["python3","node"],"files":["/etc/openclaw/wechat-article-capture-yangzai3.env","/etc/openclaw/article-knowledge-manager-yangzai3.env"]}}}
---

# WeChat Article Capture

Use this skill when the user wants to:

- save a `mp.weixin.qq.com` article into the knowledge base
- enrich a pending WeChat article record with the real title and summary
- fetch article body content with a browser instead of ordinary HTTP
- avoid spending model calls just to read the article page

Typical triggers:

- "把这篇公众号文章收进知识库"
- "收藏这个微信文章链接"
- "把待补全的公众号文章补齐"
- "重新抓一下这篇微信文章"

## Why This Skill Exists

- Tencent Cloud server-side HTTP fetching is not stable against WeChat risk control.
- A browser-based capture path is more reliable than plain requests.
- Yangzai3 should spend model cost on understanding and tagging, not on trying to open blocked pages.

## Runtime Files

Capture env:

```bash
/etc/openclaw/wechat-article-capture-yangzai3.env
```

Article env:

```bash
/etc/openclaw/article-knowledge-manager-yangzai3.env
```

Portable template:

```bash
env.example
```

## One-Time Dependency Setup

From the skill directory:

```bash
export PATH=/root/.nvm/versions/node/v22.22.0/bin:$PATH
python3 -m pip install "camoufox[geoip]" beautifulsoup4 markdownify httpx
python3 -m camoufox fetch
npm install --omit=dev
npx playwright install chromium
```

## Main Commands

Show capture/runtime status:

```bash
python3 /root/.openclaw-yangzai3/workspace/skills/wechat-article-capture/scripts/wechat_article_capture.py --env-path /etc/openclaw/wechat-article-capture-yangzai3.env --show-status --json
```

Capture one WeChat article without saving:

```bash
python3 /root/.openclaw-yangzai3/workspace/skills/wechat-article-capture/scripts/wechat_article_capture.py --env-path /etc/openclaw/wechat-article-capture-yangzai3.env --capture-url "https://mp.weixin.qq.com/s/xxxx" --json
```

Ingest one WeChat article into the article table and total index:

```bash
python3 /root/.openclaw-yangzai3/workspace/skills/wechat-article-capture/scripts/wechat_article_capture.py --env-path /etc/openclaw/wechat-article-capture-yangzai3.env --ingest-url "https://mp.weixin.qq.com/s/xxxx" --json
```

Backfill pending WeChat article rows:

```bash
python3 /root/.openclaw-yangzai3/workspace/skills/wechat-article-capture/scripts/wechat_article_capture.py --env-path /etc/openclaw/wechat-article-capture-yangzai3.env --enrich-pending --limit 5 --json
```

## Engines

- `CAPTURE_ENGINE=camoufox`
  - preferred path
  - stronger anti-detection browser capture

- `CAPTURE_ENGINE=playwright`
  - fallback path
  - useful when Camoufox is unavailable

- `SUMMARY_ENGINE=openclaw-agent`
  - preferred on the server
  - reuses the active Yangzai3 model path
  - to avoid nested same-session lane blocking, set `SUMMARY_OPENCLAW_PROFILE` to a helper profile such as `yangzai-admin`

- `SUMMARY_ENGINE=openai-compatible`
  - optional portable fallback
  - use when running on another machine with only API credentials

## Behavioral Rules

- Prefer browser capture first; do not use the model just to fetch article HTML.
- If capture succeeds, save a full article record with summary, keywords, tags, and total-index sync.
- If capture fails, save or keep a pending row instead of dropping the link.
- When enriching pending rows, update the existing row rather than creating duplicate article records.
- Never print app tokens, user tokens, or private API keys.
- Keep the workflow portable so the same skill can run on a future Mac mini with the same env files.
