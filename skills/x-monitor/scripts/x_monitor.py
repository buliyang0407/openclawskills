#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

SOCIALDATA_BASE = "https://api.socialdata.tools/twitter"
TRANSLATE_BASE = "https://translate.googleapis.com/translate_a/single"
ENV_PATH = Path("/etc/openclaw/x-monitor.env")
STATE_PATH = Path("/var/lib/openclaw/x-monitor/state.json")
WATCH_TIMER = "openclaw-x-monitor.timer"
DEFAULT_ENV = {
    "DELIVERY_CHANNEL": "feishu",
    "POLL_LIMIT": "5",
    "TRANSLATE_ENABLED": "true",
}
UA = "Mozilla/5.0 (compatible; OpenClaw X Monitor/1.0; +https://docs.socialdata.tools/)"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def read_env_map(path: Path) -> dict[str, str]:
    env_map: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env_map[key.strip()] = value.strip()
    for key, value in DEFAULT_ENV.items():
        env_map.setdefault(key, value)
    return env_map


def write_env_map(path: Path, env_map: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={value}" for key, value in env_map.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def run_command(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = "/root/.nvm/versions/node/v22.22.0/bin:/usr/local/bin:" + env.get("PATH", "")
    proc = subprocess.run(args, capture_output=True, text=True, env=env)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"command failed: {' '.join(args)} detail={detail}")
    return proc


def run_systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run_command(["systemctl", *args], check=check)


def timer_state(unit: str) -> dict[str, str]:
    enabled_proc = run_systemctl("is-enabled", unit, check=False)
    active_proc = run_systemctl("is-active", unit, check=False)
    return {
        "enabled": (enabled_proc.stdout.strip() or enabled_proc.stderr.strip() or "unknown"),
        "active": (active_proc.stdout.strip() or active_proc.stderr.strip() or "unknown"),
    }


def control_timer(unit: str, action: str) -> dict[str, str]:
    if action == "pause":
        run_systemctl("disable", "--now", unit)
    elif action == "resume":
        run_systemctl("enable", "--now", unit)
    else:
        raise ValueError("unsupported action")
    state = timer_state(unit)
    return {"unit": unit, "enabled": state["enabled"], "active": state["active"]}


def request_text(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    retries: int = 3,
    timeout: int = 30,
) -> str:
    merged_headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
    }
    if headers:
        merged_headers.update(headers)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        req = Request(url, headers=merged_headers)
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(attempt)
    raise RuntimeError(f"request failed: {url} error={last_error}")


def request_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    retries: int = 3,
    timeout: int = 30,
) -> Any:
    return json.loads(request_text(url, headers=headers, retries=retries, timeout=timeout))


def socialdata_headers(apikey: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {apikey}",
        "Accept": "application/json",
    }


def strip_identifier(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise SystemExit("account identifier cannot be empty")
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        parts = [p for p in parsed.path.split("/") if p]
        if not parts:
            raise SystemExit("could not extract X handle from URL")
        value = parts[0]
    value = value.lstrip("@").strip()
    if value.endswith("/"):
        value = value[:-1]
    if re.search(r"\s", value):
        raise SystemExit("please provide an exact X handle, URL, or numeric user id")
    return value


def normalize_key(raw: str) -> str:
    return strip_identifier(raw).lower()


def is_numeric_identifier(value: str) -> bool:
    return value.isdigit()


def socialdata_user_lookup(identifier: str, apikey: str) -> dict[str, Any]:
    ident = strip_identifier(identifier)
    url = f"{SOCIALDATA_BASE}/user/{quote(ident)}"
    data = request_json(url, headers=socialdata_headers(apikey))
    if not isinstance(data, dict) or not data.get("id_str"):
        raise RuntimeError(f"unexpected SocialData user payload for {identifier}: {data}")
    return data


def socialdata_user_tweets(user_id: str, apikey: str, limit: int) -> list[dict[str, Any]]:
    params = urlencode({"limit": limit})
    url = f"{SOCIALDATA_BASE}/user/{quote(str(user_id))}/tweets?{params}"
    data = request_json(url, headers=socialdata_headers(apikey))
    tweets = data.get("tweets", [])
    if not isinstance(tweets, list):
        raise RuntimeError(f"unexpected tweets payload: {data}")
    return tweets


def read_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"accounts": []}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def write_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def find_account(state: dict[str, Any], identifier: str) -> dict[str, Any] | None:
    key = normalize_key(identifier)
    for account in state.get("accounts", []):
        if str(account.get("user_id", "")).lower() == key:
            return account
        if str(account.get("screen_name", "")).lower() == key:
            return account
        if str(account.get("alias", "")).lower() == key:
            return account
    return None


def local_timestamp(ts: float | int | None = None) -> str:
    if ts is None:
        ts = time.time()
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def is_chinese_text(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def translate_text(text: str, target_lang: str, enabled: bool) -> str | None:
    if not enabled:
        return None
    value = text.strip()
    if not value:
        return None
    params = urlencode({
        "client": "gtx",
        "sl": "auto",
        "tl": target_lang,
        "dt": "t",
        "q": value[:1800],
    })
    try:
        payload = request_json(
            f"{TRANSLATE_BASE}?{params}",
            headers={"Accept": "application/json"},
            retries=2,
            timeout=20,
        )
    except Exception:
        return None
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        return None
    parts: list[str] = []
    for item in payload[0]:
        if isinstance(item, list) and item and isinstance(item[0], str):
            parts.append(item[0])
    translated = "".join(parts).strip()
    if not translated or translated == value:
        return None
    return translated


def choose_translation_target(text: str, lang: str | None) -> tuple[str, str]:
    source = (lang or "").lower()
    if source.startswith("zh") or is_chinese_text(text):
        return ("en", "English translation")
    return ("zh-CN", "\u4e2d\u6587\u7ffb\u8bd1")


def truncate_text(text: str, limit: int = 1200) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def format_text_block(label: str, text: str, lang: str | None, translate_enabled: bool) -> list[str]:
    value = truncate_text(text)
    if not value:
        return []
    target_lang, translated_label = choose_translation_target(value, lang)
    translated = translate_text(value, target_lang, translate_enabled)
    lines = [f"{label}:", value]
    if translated:
        lines.extend(["", f"{translated_label}:", truncate_text(translated, 1200)])
    return lines


def classify_tweet(tweet: dict[str, Any]) -> str:
    if tweet.get("retweeted_status"):
        return "repost"
    if tweet.get("quoted_status"):
        return "quote"
    if tweet.get("in_reply_to_status_id_str"):
        return "reply"
    return "tweet"


def format_notification(tweet: dict[str, Any], account: dict[str, Any], translate_enabled: bool) -> str:
    tweet_type = classify_tweet(tweet)
    created_at = tweet.get("tweet_created_at", "")
    link = f"https://x.com/{account['screen_name']}/status/{tweet['id_str']}"
    type_label = {
        "tweet": "\u539f\u521b",
        "quote": "\u8bc4\u8bba/\u5f15\u7528",
        "repost": "\u8f6c\u53d1",
        "reply": "\u56de\u590d",
    }.get(tweet_type, tweet_type)
    lines = [
        "\u3010X \u76d1\u63a7\u3011\u53d1\u73b0\u65b0\u5e16\u5b50",
        f"\u8d26\u53f7\uff1a{account['name']} (@{account['screen_name']})",
        f"\u7c7b\u578b\uff1a{type_label}",
        f"\u65f6\u95f4\uff1a{created_at}",
        f"\u94fe\u63a5\uff1a{link}",
        "",
    ]
    main_text = tweet.get("full_text") or tweet.get("text") or ""

    if tweet.get("retweeted_status"):
        original = tweet["retweeted_status"]
        original_author = original["user"]
        original_link = (
            f"https://x.com/{original_author['screen_name']}/status/"
            f"{original.get('id_str') or original.get('id')}"
        )
        lines.extend([
            "\u52a8\u4f5c\uff1a\u8f6c\u53d1\u4ed6\u4eba\u5e16\u5b50\uff08\u65e0\u5355\u72ec\u8bc4\u8bba\uff09",
            f"\u539f\u5e16\u4f5c\u8005\uff1a{original_author['name']} (@{original_author['screen_name']})",
            f"\u539f\u5e16\u94fe\u63a5\uff1a{original_link}",
            "",
        ])
        lines.extend(
            format_text_block(
                "\u539f\u5e16\u5185\u5bb9",
                original.get("full_text") or original.get("text") or "",
                original.get("lang"),
                translate_enabled,
            )
        )
    elif tweet.get("quoted_status"):
        quoted = tweet["quoted_status"]
        quoted_author = quoted["user"]
        quoted_link = (
            f"https://x.com/{quoted_author['screen_name']}/status/"
            f"{quoted.get('id_str') or quoted.get('id')}"
        )
        lines.extend([
            "\u52a8\u4f5c\uff1a\u53d1\u8868\u4e86\u81ea\u5df1\u7684\u8bc4\u8bba\uff0c\u540c\u65f6\u5f15\u7528\u4e86\u522b\u4eba\u7684\u5e16\u5b50",
            "",
        ])
        lines.extend(format_text_block("\u4ed6\u7684\u8bc4\u8bba", main_text, tweet.get("lang"), translate_enabled))
        lines.extend([
            "",
            f"\u88ab\u5f15\u7528\u4f5c\u8005\uff1a{quoted_author['name']} (@{quoted_author['screen_name']})",
            f"\u88ab\u5f15\u7528\u94fe\u63a5\uff1a{quoted_link}",
            "",
        ])
        lines.extend(
            format_text_block(
                "\u88ab\u5f15\u7528\u539f\u5e16",
                quoted.get("full_text") or quoted.get("text") or "",
                quoted.get("lang"),
                translate_enabled,
            )
        )
    elif tweet_type == "reply":
        reply_to = tweet.get("in_reply_to_screen_name")
        if reply_to:
            lines.append(f"\u52a8\u4f5c\uff1a\u56de\u590d @{reply_to}")
            lines.append("")
        lines.extend(format_text_block("\u4ed6\u7684\u56de\u590d", main_text, tweet.get("lang"), translate_enabled))
    else:
        lines.extend(format_text_block("\u4ed6\u7684\u539f\u5e16", main_text, tweet.get("lang"), translate_enabled))

    lines.extend([
        "",
        "\u6570\u636e\u6e90\uff1aSocialData",
    ])
    return "\n".join([line for line in lines if line is not None]).strip()


def push_text(text: str, env_map: dict[str, str]) -> None:
    channel = env_map.get("DELIVERY_CHANNEL", DEFAULT_ENV["DELIVERY_CHANNEL"]).strip()
    target = env_map.get("DELIVERY_TARGET", "").strip()
    if not target:
        raise SystemExit("DELIVERY_TARGET not configured")
    run_command([
        "openclaw", "message", "send",
        "--channel", channel,
        "--target", target,
        "--message", text,
    ])


def sort_tweets_ascending(tweets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(tweets, key=lambda item: int(item.get("id_str") or item.get("id") or 0))


def sort_tweets_descending(tweets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(tweets, key=lambda item: int(item.get("id_str") or item.get("id") or 0), reverse=True)


def newest_tweet_id(tweets: list[dict[str, Any]]) -> str:
    if not tweets:
        return ""
    newest = max(tweets, key=lambda item: int(item.get("id_str") or item.get("id") or 0))
    return str(newest.get("id_str") or newest.get("id") or "")


def add_account(state: dict[str, Any], apikey: str, identifier: str, alias: str | None, poll_limit: int) -> dict[str, Any]:
    profile = socialdata_user_lookup(identifier, apikey)
    account = find_account(state, profile["id_str"]) or find_account(state, profile["screen_name"])
    tweets = socialdata_user_tweets(profile["id_str"], apikey, max(5, poll_limit))
    baseline_id = newest_tweet_id(tweets)
    if account is None:
        account = {
            "user_id": profile["id_str"],
            "screen_name": profile["screen_name"],
            "name": profile["name"],
            "alias": alias or "",
            "enabled": True,
            "added_at": local_timestamp(),
            "last_seen_id": baseline_id,
            "last_checked_at": "",
        }
        state.setdefault("accounts", []).append(account)
        action = "added"
    else:
        account["screen_name"] = profile["screen_name"]
        account["name"] = profile["name"]
        if alias is not None:
            account["alias"] = alias
        if not account.get("last_seen_id"):
            account["last_seen_id"] = baseline_id
        action = "updated"
    write_state(state)
    return {
        "action": action,
        "user_id": account["user_id"],
        "screen_name": account["screen_name"],
        "name": account["name"],
        "alias": account.get("alias", ""),
        "seed_last_seen_id": account.get("last_seen_id", ""),
    }


def remove_account(state: dict[str, Any], identifier: str) -> dict[str, Any]:
    account = find_account(state, identifier)
    if account is None:
        raise SystemExit(f"account not found: {identifier}")
    state["accounts"] = [item for item in state.get("accounts", []) if item is not account]
    write_state(state)
    return {
        "removed": True,
        "user_id": account["user_id"],
        "screen_name": account["screen_name"],
        "name": account["name"],
        "alias": account.get("alias", ""),
    }


def list_accounts(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "count": len(state.get("accounts", [])),
        "accounts": state.get("accounts", []),
    }


def public_config(env_map: dict[str, str]) -> dict[str, Any]:
    return {
        "delivery_channel": env_map.get("DELIVERY_CHANNEL", DEFAULT_ENV["DELIVERY_CHANNEL"]),
        "delivery_target": env_map.get("DELIVERY_TARGET", ""),
        "poll_limit": int(env_map.get("POLL_LIMIT", DEFAULT_ENV["POLL_LIMIT"])),
        "translate_enabled": env_map.get("TRANSLATE_ENABLED", DEFAULT_ENV["TRANSLATE_ENABLED"]).lower() == "true",
        "api_key_configured": bool(env_map.get("SOCIALDATA_API_KEY", "")),
    }


def show_status(state: dict[str, Any], env_map: dict[str, str]) -> dict[str, Any]:
    payload = public_config(env_map)
    payload["watch_timer"] = timer_state(WATCH_TIMER)
    payload["monitored_accounts"] = [
        {
            "user_id": item.get("user_id", ""),
            "screen_name": item.get("screen_name", ""),
            "name": item.get("name", ""),
            "alias": item.get("alias", ""),
            "enabled": item.get("enabled", True),
            "last_seen_id": item.get("last_seen_id", ""),
        }
        for item in state.get("accounts", [])
    ]
    payload["monitored_count"] = len(payload["monitored_accounts"])
    return payload


def preview_account(apikey: str, identifier: str, limit: int, translate_enabled: bool) -> str:
    profile = socialdata_user_lookup(identifier, apikey)
    account = {
        "user_id": profile["id_str"],
        "screen_name": profile["screen_name"],
        "name": profile["name"],
    }
    tweets = socialdata_user_tweets(profile["id_str"], apikey, max(limit, 5))
    if not tweets:
        return "No recent tweets found."
    latest = sort_tweets_descending(tweets)[:limit]
    chunks = []
    for tweet in sort_tweets_ascending(latest):
        chunks.append(format_notification(tweet, account, translate_enabled))
    return "\n\n" + ("\n\n" + ("-" * 48) + "\n\n").join(chunks)


def set_config(
    env_map: dict[str, str],
    *,
    delivery_channel: str | None,
    delivery_target: str | None,
    poll_limit: int | None,
    translate_enabled: str | None,
) -> dict[str, Any]:
    changed = False
    if delivery_channel is not None:
        env_map["DELIVERY_CHANNEL"] = delivery_channel.strip()
        changed = True
    if delivery_target is not None:
        env_map["DELIVERY_TARGET"] = delivery_target.strip()
        changed = True
    if poll_limit is not None:
        if poll_limit < 1 or poll_limit > 20:
            raise SystemExit("POLL_LIMIT must be between 1 and 20")
        env_map["POLL_LIMIT"] = str(poll_limit)
        changed = True
    if translate_enabled is not None:
        normalized = translate_enabled.strip().lower()
        if normalized not in {"true", "false"}:
            raise SystemExit("TRANSLATE_ENABLED must be true or false")
        env_map["TRANSLATE_ENABLED"] = normalized
        changed = True
    if not changed:
        raise SystemExit("no config changes requested")
    write_env_map(ENV_PATH, env_map)
    return public_config(env_map)


def check_and_push(state: dict[str, Any], env_map: dict[str, str], apikey: str) -> dict[str, Any]:
    poll_limit = int(env_map.get("POLL_LIMIT", DEFAULT_ENV["POLL_LIMIT"]))
    translate_enabled = env_map.get("TRANSLATE_ENABLED", DEFAULT_ENV["TRANSLATE_ENABLED"]).lower() == "true"
    delivered: list[dict[str, Any]] = []
    for account in state.get("accounts", []):
        if not account.get("enabled", True):
            continue
        tweets = socialdata_user_tweets(str(account["user_id"]), apikey, poll_limit)
        if not tweets:
            account["last_checked_at"] = local_timestamp()
            continue
        latest_seen = int(account.get("last_seen_id") or 0)
        new_tweets = [
            item for item in sort_tweets_ascending(tweets)
            if int(item.get("id_str") or item.get("id") or 0) > latest_seen
        ]
        for tweet in new_tweets:
            push_text(format_notification(tweet, account, translate_enabled), env_map)
            account["last_seen_id"] = str(tweet.get("id_str") or tweet.get("id") or account.get("last_seen_id", ""))
            delivered.append({
                "screen_name": account.get("screen_name", ""),
                "tweet_id": str(tweet.get("id_str") or tweet.get("id") or ""),
                "type": classify_tweet(tweet),
            })
        if not new_tweets:
            account["last_seen_id"] = newest_tweet_id(tweets) or account.get("last_seen_id", "")
        account["last_checked_at"] = local_timestamp()
    write_state(state)
    return {
        "delivered_count": len(delivered),
        "delivered": delivered,
        "checked_accounts": len([item for item in state.get("accounts", []) if item.get("enabled", True)]),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor selected X accounts with SocialData")
    parser.add_argument("--show-config", action="store_true")
    parser.add_argument("--show-status", action="store_true")
    parser.add_argument("--list-accounts", action="store_true")
    parser.add_argument("--resolve-account", help="Resolve an X handle or URL to canonical account data")
    parser.add_argument("--add-account", help="Add an account to the monitored list")
    parser.add_argument("--alias", help="Optional human alias when adding an account")
    parser.add_argument("--remove-account", help="Remove a monitored account by handle, user id, or alias")
    parser.add_argument("--preview-account", help="Preview recent tweets for one account without changing state")
    parser.add_argument("--limit", type=int, default=3, help="Preview limit for --preview-account")
    parser.add_argument("--check-and-push", action="store_true", help="Run one monitoring pass and send new tweet notifications")
    parser.add_argument("--pause-watch", action="store_true")
    parser.add_argument("--resume-watch", action="store_true")
    parser.add_argument("--set-delivery-channel", help="Set DELIVERY_CHANNEL")
    parser.add_argument("--set-delivery-target", help="Set DELIVERY_TARGET")
    parser.add_argument("--set-poll-limit", type=int, help="Set POLL_LIMIT")
    parser.add_argument("--set-translate-enabled", help="Set TRANSLATE_ENABLED to true or false")
    return parser.parse_args()


def main() -> int:
    load_env_file(ENV_PATH)
    args = parse_args()
    env_map = read_env_map(ENV_PATH)
    state = read_state()

    if args.show_config:
        print(json.dumps(public_config(env_map), ensure_ascii=False, indent=2))
        return 0
    if args.show_status:
        print(json.dumps(show_status(state, env_map), ensure_ascii=False, indent=2))
        return 0
    if args.list_accounts:
        print(json.dumps(list_accounts(state), ensure_ascii=False, indent=2))
        return 0
    if args.pause_watch:
        print(json.dumps(control_timer(WATCH_TIMER, "pause"), ensure_ascii=False, indent=2))
        return 0
    if args.resume_watch:
        print(json.dumps(control_timer(WATCH_TIMER, "resume"), ensure_ascii=False, indent=2))
        return 0
    if any(v is not None for v in [args.set_delivery_channel, args.set_delivery_target, args.set_poll_limit, args.set_translate_enabled]):
        print(json.dumps(set_config(
            env_map,
            delivery_channel=args.set_delivery_channel,
            delivery_target=args.set_delivery_target,
            poll_limit=args.set_poll_limit,
            translate_enabled=args.set_translate_enabled,
        ), ensure_ascii=False, indent=2))
        return 0

    apikey = env_map.get("SOCIALDATA_API_KEY", "").strip()
    if not apikey:
        raise SystemExit("SOCIALDATA_API_KEY not configured")

    if args.resolve_account:
        profile = socialdata_user_lookup(args.resolve_account, apikey)
        print(json.dumps({
            "user_id": profile["id_str"],
            "screen_name": profile["screen_name"],
            "name": profile["name"],
            "verified": bool(profile.get("verified", False)),
        }, ensure_ascii=False, indent=2))
        return 0
    if args.add_account:
        result = add_account(state, apikey, args.add_account, args.alias, int(env_map.get("POLL_LIMIT", DEFAULT_ENV["POLL_LIMIT"])))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.remove_account:
        print(json.dumps(remove_account(state, args.remove_account), ensure_ascii=False, indent=2))
        return 0
    if args.preview_account:
        translate_enabled = env_map.get("TRANSLATE_ENABLED", DEFAULT_ENV["TRANSLATE_ENABLED"]).lower() == "true"
        print(preview_account(apikey, args.preview_account, args.limit, translate_enabled).strip())
        return 0
    if args.check_and_push:
        print(json.dumps(check_and_push(state, env_map, apikey), ensure_ascii=False, indent=2))
        return 0

    raise SystemExit("no action specified")


if __name__ == "__main__":
    raise SystemExit(main())
