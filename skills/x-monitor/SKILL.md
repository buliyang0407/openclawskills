---
name: x-monitor
description: Monitor selected X.com accounts using SocialData, fetch new tweets on a schedule, deliver bilingual notifications, and manage the monitored account list by adding, removing, pausing, or previewing accounts.
homepage: https://docs.socialdata.tools/
metadata: {"clawdbot":{"requires":{"bins":["python3","systemctl","openclaw"],"files":["/etc/openclaw/x-monitor.env"]}}}
---

# X Monitor

Use this skill when the user wants to:
- monitor specific X.com accounts such as `@elonmusk`
- add or remove monitored accounts
- ask which X accounts are currently monitored
- preview the latest posts from an account
- pause or resume X monitoring
- receive bilingual post notifications

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

## Behavioral Rules

- Use SocialData as the only X data source.
- Deliver notifications through `openclaw message send`.
- New accounts must be seeded with the current latest post so historical tweets do not flood the user.
- Prefer exact handles when adding accounts. Common names are only aliases, not canonical identifiers.
- Bilingual notifications should keep the original post text and add a translated section.
- Quote tweets and retweets should preserve the referenced original content when available.
- Never print or export the SocialData API key.
- Never package `/etc/openclaw/x-monitor.env` with the skill export.

## Translation

The script uses a no-key translation fallback for bilingual output. It is suitable for hourly monitoring and lightweight usage.

If translation fails, keep the original text and continue delivery rather than failing the whole monitoring pass.
