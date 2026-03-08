---
name: x-monitor
description: Monitor selected X.com accounts using SocialData, fetch recent tweets on a schedule, deliver either detailed notifications or AI-written summary digests, and manage the monitored account list by adding, removing, pausing, or previewing accounts.
homepage: https://docs.socialdata.tools/
metadata: {"clawdbot":{"requires":{"bins":["python3","systemctl","openclaw"],"files":["/etc/openclaw/x-monitor.env"]}}}
---

# X Monitor

Use this skill when the user wants to:
- monitor specific X.com accounts such as `@elonmusk`
- add or remove monitored accounts
- ask which X accounts are currently monitored
- preview the latest posts from an account
- preview the latest full post bodies from all monitored accounts
- pause or resume X monitoring
- receive detailed tweet notifications or periodic AI summary digests
- optionally archive pushed tweets into a Feishu Bitable for later review

## Canonical Input Rule

Prefer exact X handles as the input:
- good: `@elonmusk`
- good: `elonmusk`
- good: `https://x.com/elonmusk`
- risky: `Musk`, `White House`, `CCTV`

If the user gives a vague common name, resolve only if it is obviously unambiguous. Otherwise ask for the exact handle.

The script stores canonical identity as:
- `user_id`
- `screen_name`
- optional human alias

## Runtime Files

Environment file:

```bash
/etc/openclaw/x-monitor.env
```

Canonical script:

```bash
python3 /root/.openclaw/workspace/skills/x-monitor/scripts/x_monitor.py
```

## Main Commands

Show monitored accounts and timer state:

```bash
python3 /root/.openclaw/workspace/skills/x-monitor/scripts/x_monitor.py --show-status
```

Add one account:

```bash
python3 /root/.openclaw/workspace/skills/x-monitor/scripts/x_monitor.py --add-account @elonmusk --alias 马斯克
```

Remove one account:

```bash
python3 /root/.openclaw/workspace/skills/x-monitor/scripts/x_monitor.py --remove-account @elonmusk
```

List monitored accounts:

```bash
python3 /root/.openclaw/workspace/skills/x-monitor/scripts/x_monitor.py --list-accounts
```

Preview recent posts without changing state:

```bash
python3 /root/.openclaw/workspace/skills/x-monitor/scripts/x_monitor.py --preview-account @elonmusk --limit 3
```

Preview recent full posts for all monitored accounts:

```bash
python3 /root/.openclaw/workspace/skills/x-monitor/scripts/x_monitor.py --preview-all --limit 1
```

Run one monitoring pass immediately:

```bash
python3 /root/.openclaw/workspace/skills/x-monitor/scripts/x_monitor.py --check-and-push
```

Pause or resume the timer:

```bash
python3 /root/.openclaw/workspace/skills/x-monitor/scripts/x_monitor.py --pause-watch
python3 /root/.openclaw/workspace/skills/x-monitor/scripts/x_monitor.py --resume-watch
```

Switch the delivery target:

```bash
python3 /root/.openclaw/workspace/skills/x-monitor/scripts/x_monitor.py --set-delivery-channel feishu --set-delivery-target ou_xxx
```

Fetch more recent tweets when summary mode needs a wider window:

```bash
python3 /root/.openclaw/workspace/skills/x-monitor/scripts/x_monitor.py --set-poll-limit 20 --set-max-new-per-account 20
```

Switch between detailed per-tweet delivery, table digests, and account summaries:

```bash
python3 /root/.openclaw/workspace/skills/x-monitor/scripts/x_monitor.py --set-push-mode summary
```

Current daytime summary schedule is controlled by:

- `/etc/systemd/system/openclaw-x-monitor.timer`
- `/etc/openclaw/x-monitor.env`

The active production setup summarizes only the latest 4 hours, skips nighttime delivery, and can be adjusted later if the user asks to change the summary times.

## Behavioral Rules

- Use SocialData as the only X data source.
- Deliver notifications through `openclaw message send`.
- New accounts must be seeded with the current latest post so historical tweets do not flood the user.
- Prefer exact handles when adding accounts. Common names are only aliases, not canonical identifiers.
- Detailed mode keeps original text and adds translation when useful.
- Quote tweets and retweets should preserve the referenced original content when available.
- `PUSH_MODE=summary` is the preferred production mode when the user wants one digest message instead of per-tweet spam.
- In summary mode, only summarize tweets inside the configured recent time window and avoid repeating the same slot twice.
- In summary mode, summarize by account, count the tweets in the window, and list only the main themes or events rather than every single tweet.
- The user may later ask to change summary time slots or add/remove monitored accounts; this skill should support both.
- If `FEISHU_BITABLE_APP_TOKEN` is configured, delivered tweets may also be appended to a Feishu Bitable table. `FEISHU_BITABLE_TABLE_ID` is optional when the Base contains only one table.
- When the user asks for a test run or asks to see recent monitored content, prefer full post previews rather than headline-only summaries.
- Never print or export the SocialData API key.
- Never package `/etc/openclaw/x-monitor.env` with the skill export.

## Translation

The script uses a no-key translation fallback for bilingual output. It is suitable for hourly monitoring and lightweight usage.

If translation fails, keep the original text and continue delivery rather than failing the whole monitoring pass.
