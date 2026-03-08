---
name: lobster-supervisor
description: Monitor OpenClaw bots, timers, local ports, and supporting services; try safe auto-heal steps first and notify the owner when issues remain or recover.
metadata: {"clawdbot":{"requires":{"bins":["python3","systemctl","openclaw","ss"],"files":["/etc/openclaw/lobster-supervisor.env"]}}}
---

# Lobster Supervisor

Use this skill when the user wants to:
- monitor whether the other lobster bots are healthy
- receive alerts only when something is broken or recovered
- let a supervisor job attempt safe restarts before escalating
- inspect current runtime health from the server

## Runtime Files

Environment file:

```bash
/etc/openclaw/lobster-supervisor.env
```

Canonical script:

```bash
python3 /root/.openclaw-yangzai2/workspace/skills/lobster-supervisor/scripts/lobster_supervisor.py
```

## Main Commands

Show current supervisor config:

```bash
python3 /root/.openclaw-yangzai2/workspace/skills/lobster-supervisor/scripts/lobster_supervisor.py --env-path /etc/openclaw/lobster-supervisor.env --show-config
```

Show live health status:

```bash
python3 /root/.openclaw-yangzai2/workspace/skills/lobster-supervisor/scripts/lobster_supervisor.py --env-path /etc/openclaw/lobster-supervisor.env --show-status
```

Run one supervisor pass immediately:

```bash
python3 /root/.openclaw-yangzai2/workspace/skills/lobster-supervisor/scripts/lobster_supervisor.py --env-path /etc/openclaw/lobster-supervisor.env --check-once
```

Force one notification for testing:

```bash
python3 /root/.openclaw-yangzai2/workspace/skills/lobster-supervisor/scripts/lobster_supervisor.py --env-path /etc/openclaw/lobster-supervisor.env --check-once --force-notify
```

Pause or resume the timer:

```bash
python3 /root/.openclaw-yangzai2/workspace/skills/lobster-supervisor/scripts/lobster_supervisor.py --env-path /etc/openclaw/lobster-supervisor.env --pause-watch
python3 /root/.openclaw-yangzai2/workspace/skills/lobster-supervisor/scripts/lobster_supervisor.py --env-path /etc/openclaw/lobster-supervisor.env --resume-watch
```

## Default Coverage

The first production version checks:

- `openclaw-watchdog.timer`
- default OpenClaw gateway port `127.0.0.1:18789`
- `openclaw-yangzai2.service`
- `openclaw-wechat-official-monitor-yangzai2.timer`
- second OpenClaw gateway port `127.0.0.1:19011`
- `Wechat2RSS` on `127.0.0.1:18080`

## Delivery Model

Until a dedicated third Feishu app exists, the supervisor can use an existing bot profile as its delivery transport.

Recommended current transport:

- `DELIVERY_PROFILE=yangzai2`
- `DELIVERY_CHANNEL=feishu`
- `DELIVERY_TARGET=<owner open id>`

The supervisor logic stays independent even if the transport bot is temporary.

## Behavioral Rules

- Attempt only safe local repair actions first, such as restarting a known service or timer.
- Never stop the default bot as a test.
- Prefer state-change alerts over noisy repeated healthy messages.
- Send a recovery message when a previously unhealthy system returns to normal.
- Keep all checks read-only unless a repair action is explicitly defined for that target.
