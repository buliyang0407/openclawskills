# openclawskills

Personal OpenClaw skills repository.

## Included Skills

### `gold-rmb-realtime`

- Fetches `XAU/USD` and `USD/CNY`
- Converts to `CNY/oz` and `CNY/g`
- Supports fixed-time broadcasts and threshold alerts
- Uses `openclaw message send` for delivery

### `x-monitor`

- Monitors selected X.com accounts with SocialData
- Supports add/remove/list/preview operations
- Sends bilingual notifications
- Distinguishes original posts, replies, quotes, and reposts

## Important

- Secret files are intentionally excluded.
- Runtime env files such as `/etc/openclaw/*.env` are not part of this repository.
- These skills are designed for an OpenClaw server environment.
