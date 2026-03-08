---
name: gold-rmb-realtime
description: Fetch realtime gold prices from Twelve Data (XAU/USD plus USD/CNY), convert to CNY per ounce and CNY per gram, and support fixed-time broadcasts, threshold alerts, and timer/threshold/delivery management.
homepage: https://twelvedata.com/docs
metadata: {"clawdbot":{"requires":{"bins":["python3","systemctl","openclaw"],"files":["/etc/openclaw/gold-rmb.env"]}}}
---

# Gold RMB Realtime

Use this skill when the user asks for realtime gold prices in:
- `人民币元/盎司`
- `人民币元/克`
- fixed-time scheduled broadcasts such as `08:00` and `20:00`
- threshold-based alerts for gold price moves
- changing the gold alert threshold or alert cooldown
- pausing or resuming the hourly or threshold timers
- checking whether the current gold automation is enabled
- switching the delivery channel or target
- optionally archiving pushed gold snapshots into a Feishu Bitable table

## Inputs

The runtime reads `/etc/openclaw/gold-rmb.env`:
- `TWELVEDATA_API_KEY`
- `DELIVERY_CHANNEL`
- `DELIVERY_TARGET`
- `MOVE_THRESHOLD_CNY_PER_GRAM`
- `MIN_PUSH_INTERVAL_SECONDS`

## Formula

```text
人民币/盎司 = XAU/USD * USD/CNY
人民币/克 = (XAU/USD * USD/CNY) / 31.1034768
```

## Canonical Script

Use the bundled script instead of improvising web lookups.

## Delivery management

Show current delivery config:

```bash
python3 /root/.openclaw/workspace/skills/gold-rmb-realtime/scripts/gold_rmb_quote.py --show-config
```

Switch alerts to Feishu DM:

```bash
python3 /root/.openclaw/workspace/skills/gold-rmb-realtime/scripts/gold_rmb_quote.py --set-delivery-channel feishu --set-delivery-target ou_xxx
```

## Fixed Broadcast Schedule

The current fixed broadcast timer is not an hourly timer in business meaning.

It is a fixed-time timer that currently runs at:

- `08:00`
- `20:00`

If the user says:

- `只在早上8点和晚上8点推`
- `不要每小时`

then keep threshold watch disabled unless explicitly requested, and keep only the fixed broadcast timer enabled.

## Rules

- Always use Twelve Data quotes for both `XAU/USD` and `USD/CNY`.
- Treat the fixed broadcast timer as `08:00 and 20:00`, not as a generic hourly schedule.
- Use `openclaw message send` for outbound delivery so the target channel can be changed without rewriting the script.
- If `FEISHU_BITABLE_APP_TOKEN` is configured, each pushed gold snapshot can also be appended to a Feishu Bitable table using the official `feishu-openclaw-plugin` user authorization.
- Never package `/etc/openclaw/gold-rmb.env` with the skill export.
- Never print or export the API key when showing config.
