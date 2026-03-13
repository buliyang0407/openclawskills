---
name: wechat-official-monitor
description: Monitor selected WeChat official accounts through Wechat2RSS, summarize recent new articles, deliver scheduled Feishu digests, and archive pushed article summaries into Feishu Bitable.
homepage: https://wechat2rss.xlab.app/readme
metadata: {"clawdbot":{"requires":{"bins":["python3","systemctl","openclaw"],"files":["/etc/openclaw/wechat-official-monitor.env"]}}}
---

# WeChat Official Monitor

Use this skill when the user wants to:
- monitor specific 微信公众号 for newly published articles
- add or remove monitored public accounts
- preview recent articles for one monitored account
- trigger one immediate collection pass
- receive one clean digest instead of noisy link spam
- archive pushed article summaries into a Feishu Bitable for later lookup
- keep公众号 monitoring isolated to a dedicated OpenClaw profile such as `yangzai2`

## Runtime Files

Environment file:

```bash
/etc/openclaw/wechat-official-monitor.env
```

Canonical script:

```bash
python3 /root/.openclaw/workspace/skills/wechat-official-monitor/scripts/wechat_official_monitor.py
```

## Source Model

This skill is designed around a Wechat2RSS-compatible source.

Recommended source:

- Wechat2RSS private deployment

The source is expected to provide:

- a subscription list API
- a way to add one account from a public article URL
- feed URLs for subscribed accounts
- article title, link, publish time, and summary or full content in the feed

## Main Commands

Show monitored accounts, source config, and timer state:

```bash
python3 /root/.openclaw/workspace/skills/wechat-official-monitor/scripts/wechat_official_monitor.py --env-path /etc/openclaw/wechat-official-monitor-yangzai2.env --show-status
```

Add one monitored account directly from a public article URL:

```bash
python3 /root/.openclaw/workspace/skills/wechat-official-monitor/scripts/wechat_official_monitor.py --env-path /etc/openclaw/wechat-official-monitor-yangzai2.env --add-account "宝玉AI" --article-url "https://mp.weixin.qq.com/s/xxxxx"
```

Register one monitored account from an already-existing upstream subscription:

```bash
python3 /root/.openclaw/workspace/skills/wechat-official-monitor/scripts/wechat_official_monitor.py --env-path /etc/openclaw/wechat-official-monitor-yangzai2.env --add-account "宝玉AI"
```

List monitored accounts:

```bash
python3 /root/.openclaw/workspace/skills/wechat-official-monitor/scripts/wechat_official_monitor.py --env-path /etc/openclaw/wechat-official-monitor-yangzai2.env --list-accounts
```

Remove one monitored account:

```bash
python3 /root/.openclaw/workspace/skills/wechat-official-monitor/scripts/wechat_official_monitor.py --env-path /etc/openclaw/wechat-official-monitor-yangzai2.env --remove-account "宝玉AI"
```

Preview recent articles for one monitored account:

```bash
python3 /root/.openclaw/workspace/skills/wechat-official-monitor/scripts/wechat_official_monitor.py --env-path /etc/openclaw/wechat-official-monitor-yangzai2.env --preview-account "宝玉AI" --limit 3
```

Run one monitoring pass immediately:

```bash
python3 /root/.openclaw/workspace/skills/wechat-official-monitor/scripts/wechat_official_monitor.py --env-path /etc/openclaw/wechat-official-monitor-yangzai2.env --check-and-push
```

Pause or resume the timer:

```bash
python3 /root/.openclaw/workspace/skills/wechat-official-monitor/scripts/wechat_official_monitor.py --env-path /etc/openclaw/wechat-official-monitor-yangzai2.env --pause-watch
python3 /root/.openclaw/workspace/skills/wechat-official-monitor/scripts/wechat_official_monitor.py --env-path /etc/openclaw/wechat-official-monitor-yangzai2.env --resume-watch
```

Switch the delivery target:

```bash
python3 /root/.openclaw/workspace/skills/wechat-official-monitor/scripts/wechat_official_monitor.py --env-path /etc/openclaw/wechat-official-monitor-yangzai2.env --set-delivery-channel feishu --set-delivery-target ou_xxx
```

## Required Environment

- `WECHAT2RSS_BASE_URL`
- `WECHAT2RSS_TOKEN`
- `DELIVERY_CHANNEL`
- `DELIVERY_TARGET`

Optional environment:

- `OPENCLAW_PROFILE`
- `OPENCLAW_CONFIG_PATH`
- `WECHAT_MONITOR_ENV_PATH`
- `WECHAT_MONITOR_STATE_PATH`
- `WECHAT_MONITOR_TIMER_UNIT`
- `SUMMARY_MODE`
- `SUMMARY_MAX_ARTICLES`
- `FETCH_LIMIT_PER_ACCOUNT`
- `PUSH_WINDOW_HOURS`
- `FEISHU_BITABLE_APP_TOKEN`
- `FEISHU_BITABLE_TABLE_ID`
- `FEISHU_BITABLE_TABLE_NAME`
- `FEISHU_BITABLE_USER_OPEN_ID`

## Output Rules

- Only push articles published within the configured recent window, currently `24` hours.
- If no monitored account has a qualifying new article, send nothing.
- Do not include article links in the Feishu message digest.
- Format digests as numbered items:

```text
1. 标题：xxx
发布时间：xxx
内容概述：xxx
```

- Prefer AI summaries when the dedicated profile is configured and healthy; fall back to a short excerpt if summarization fails.
- The state file is authoritative for deduplication. Do not repeat the same article after it has been pushed once.

## Feishu Bitable Archive

When `FEISHU_BITABLE_APP_TOKEN` is configured, every pushed article summary can also be appended into a Feishu Bitable table.

Recommended archive table fields:

- `Source Type`
- `Source Name`
- `Title`
- `Published At`
- `Summary`
- `Source URL`
- `Archived At`
- `Summary Model`
- `Data Source`

The preferred production setup is the official `feishu-openclaw-plugin` with `/feishu auth` completed by the owner. The helper can auto-create missing fields and can create the target table when `FEISHU_BITABLE_TABLE_NAME` is provided and `FEISHU_BITABLE_TABLE_ID` is absent.

## Behavioral Rules

- Keep the existing production bot untouched; second-bot usage must run with its own `OPENCLAW_PROFILE`.
- Do not treat source subscription management as part of OpenClaw pairing; Wechat2RSS login must already be completed.
- Adding a monitored account from an article URL is the preferred workflow because upstream subscription names may be blank or delayed.
- Removing an account should stop local monitoring immediately even if the upstream source still keeps the subscription.
- Never print or export `WECHAT2RSS_TOKEN`.
- Never package `/etc/openclaw/wechat-official-monitor.env` with the skill export.

## Scope Guardrails (Yangzai2)

Yangzai2 is a dedicated WeChat-official-account monitor bot.
Its own recurring work is only:

- `openclaw-wechat-official-monitor-yangzai2.timer` (`08:30`, `21:30`)
- the always-on gateway service `openclaw-yangzai2.service` (not a timer task)

When user asks "你现在有哪些定时任务/计划任务":

1. run `wechat_official_monitor.py --show-status` with `--env-path /etc/openclaw/wechat-official-monitor-yangzai2.env`
2. answer only Yangzai2-owned tasks and schedule
3. explicitly say global jobs below are not Yangzai2's own tasks:
   - `openclaw-x-monitor.timer`
   - `openclaw-gold-rmb-hourly.timer`
   - `openclaw-lobster-supervisor.timer`
   - `openclaw-watchdog.timer`

Do not enumerate global timers as "my tasks" for Yangzai2.
