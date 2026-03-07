# SocialData Notes

Current implementation assumptions:

- User lookup works with:
  - `/twitter/user/<screen_name>`
  - `/twitter/user/<user_id>`
- Tweets endpoint works with:
  - `/twitter/user/<user_id>/tweets?limit=<n>`

Observed useful fields in tweet payloads:

- `id_str`
- `tweet_created_at`
- `full_text`
- `lang`
- `type`
- `user.screen_name`
- `user.name`
- `retweeted_status`
- `quoted_status`

Observed routing behavior:

- Requests should send a realistic `User-Agent`.
- Server-side plain `urllib` without headers was once blocked with `403`.
- Requests with a browser-like `User-Agent` succeeded.

Cost discipline:

- Polling is intentionally hourly by default.
- Per-account fetch size is intentionally small.
- The script only notifies on posts newer than the stored `last_seen_id`.
