---
name: gold-rmb-realtime
description: Fetch realtime gold prices from Twelve Data (XAU/USD plus USD/CNY), convert to CNY per ounce and CNY per gram, and support fixed-time broadcasts, threshold alerts, and timer/threshold/delivery management.
homepage: https://twelvedata.com/docs
metadata: {"clawdbot":{"requires":{"bins":["python3","systemctl","openclaw"],"files":["/etc/openclaw/gold-rmb.env"]}}}
---

# Gold RMB Realtime

Use this skill when the user asks for:

- realtime gold prices in `CNY/oz`
- realtime gold prices in `CNY/g`
- fixed-time scheduled broadcasts such as `08:00` and `20:00`
- threshold-based alerts for gold price moves
- changing the gold alert threshold or cooldown
- pausing or resuming the fixed broadcast timer or threshold timer
- checking whether the current gold automation is enabled
- switching the delivery channel or target

## Inputs

The runtime reads:

```bash
/etc/openclaw/gold-rmb.env
```

Expected keys:

- `TWELVEDATA_API_KEY`
- `DELIVERY_CHANNEL`
- `DELIVERY_TARGET`
- `MOVE_THRESHOLD_CNY_PER_GRAM`
- `MIN_PUSH_INTERVAL_SECONDS`

## Formula

```text
CNY/oz = XAU/USD * USD/CNY
CNY/g  = (XAU/USD * USD/CNY) / 31.1034768
```

## Canonical Script

```bash
python3 /root/.openclaw/workspace/skills/gold-rmb-realtime/scripts/gold_rmb_quote.py
```

## Fixed Broadcast Schedule

The current fixed broadcast timer is not a generic hourly schedule.

It is intended to run at:

- `08:00`
- `20:00`

If the user says:

- `only at 8am and 8pm`
- `do not send every hour`

then keep threshold watch disabled unless explicitly requested, and keep only the fixed broadcast timer enabled.

## Common Commands

Show current config:

```bash
python3 /root/.openclaw/workspace/skills/gold-rmb-realtime/scripts/gold_rmb_quote.py --show-config
```

Show current status:

```bash
python3 /root/.openclaw/workspace/skills/gold-rmb-realtime/scripts/gold_rmb_quote.py --show-status
```

Switch alerts to Feishu:

```bash
python3 /root/.openclaw/workspace/skills/gold-rmb-realtime/scripts/gold_rmb_quote.py --set-delivery-channel feishu --set-delivery-target ou_xxx
```

## Rules

- Always use Twelve Data quotes for both `XAU/USD` and `USD/CNY`.
- Treat the fixed broadcast timer as `08:00 and 20:00`, not as a generic hourly schedule.
- Use `openclaw message send` for outbound delivery so the target channel can be changed without rewriting the script.
- Never package `/etc/openclaw/gold-rmb.env` with the skill export.
- Never print or export the API key when showing config.
