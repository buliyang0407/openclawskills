#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

SOCIALDATA_BASE = "https://api.socialdata.tools/twitter"
TRANSLATE_BASE = "https://translate.googleapis.com/translate_a/single"
FEISHU_BASE = "https://open.feishu.cn/open-apis"
DEFAULT_ENV_PATH = Path("/etc/openclaw/x-monitor.env")
DEFAULT_STATE_PATH = Path("/var/lib/openclaw/x-monitor/state.json")
DEFAULT_OPENCLAW_CONFIG_PATH = Path("/root/.openclaw/openclaw.json")
DEFAULT_WATCH_TIMER = "openclaw-x-monitor.timer"
BITABLE_NODE_HELPER_PATH = Path(__file__).with_name("feishu_bitable_uat.mjs")
DEFAULT_ENV = {
    "DELIVERY_CHANNEL": "feishu",
    "POLL_LIMIT": "20",
    "MAX_NEW_PER_ACCOUNT": "20",
    "PUSH_MODE": "summary",
    "TRANSLATE_ENABLED": "true",
    "SUMMARY_WINDOW_HOURS": "4",
    "SUMMARY_INTERVAL_HOURS": "4",
    "SUMMARY_ACTIVE_START_HOUR": "8",
    "SUMMARY_ACTIVE_END_HOUR": "20",
}
UA = "Mozilla/5.0 (compatible; OpenClaw X Monitor/1.0; +https://docs.socialdata.tools/)"
TRANSLATE_AGENT_ID = "main"
BITABLE_TWEET_FIELDS = (
    "Tweet ID",
    "Account Name",
    "Screen Name",
    "Alias",
    "Type",
    "Created At",
    "Tweet URL",
    "Main Text",
    "Referenced Author",
    "Referenced URL",
    "Referenced Text",
    "Recorded At",
    "Data Source",
)
BITABLE_SUMMARY_FIELDS = (
    "时间",
    "账号",
    "发了什么",
    "核心意思",
)


def current_env_path() -> Path:
    return Path(os.environ.get("X_MONITOR_ENV_PATH", str(DEFAULT_ENV_PATH)))


def current_state_path() -> Path:
    return Path(os.environ.get("X_MONITOR_STATE_PATH", str(DEFAULT_STATE_PATH)))


def current_watch_timer() -> str:
    return os.environ.get("X_MONITOR_TIMER_UNIT", DEFAULT_WATCH_TIMER).strip() or DEFAULT_WATCH_TIMER


def current_openclaw_profile() -> str:
    return os.environ.get("OPENCLAW_PROFILE", "").strip()


def current_openclaw_config_path() -> Path:
    explicit = os.environ.get("OPENCLAW_CONFIG_PATH", "").strip()
    if explicit:
        return Path(explicit)
    profile = current_openclaw_profile()
    if profile:
        return Path(f"/root/.openclaw-{profile}/openclaw.json")
    return DEFAULT_OPENCLAW_CONFIG_PATH


def openclaw_cli_args() -> list[str]:
    args = ["openclaw"]
    profile = current_openclaw_profile()
    if profile:
        args.extend(["--profile", profile])
    return args


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


def run_command_with_input(args: list[str], payload: str, check: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = "/root/.nvm/versions/node/v22.22.0/bin:/usr/local/bin:" + env.get("PATH", "")
    proc = subprocess.run(args, input=payload, capture_output=True, text=True, env=env)
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
    method: str = "GET",
    data: bytes | None = None,
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
        req = Request(url, headers=merged_headers, data=data, method=method)
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
    method: str = "GET",
    payload: Any = None,
    retries: int = 3,
    timeout: int = 30,
) -> Any:
    data: bytes | None = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return json.loads(
        request_text(
            url,
            headers=headers,
            method=method,
            data=data,
            retries=retries,
            timeout=timeout,
        )
    )


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
    state_path = current_state_path()
    if not state_path.exists():
        return {"accounts": []}
    return json.loads(state_path.read_text(encoding="utf-8"))


def write_state(state: dict[str, Any]) -> None:
    state_path = current_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_openclaw_feishu_account() -> dict[str, str]:
    config_path = current_openclaw_config_path()
    if not config_path.exists():
        return {}
    config = json.loads(config_path.read_text(encoding="utf-8"))
    feishu = config.get("channels", {}).get("feishu", {})
    main = feishu.get("accounts", {}).get(feishu.get("defaultAccount", "main"), {})
    app_id = str(feishu.get("appId", "") or main.get("appId", "")).strip()
    app_secret = str(feishu.get("appSecret", "") or main.get("appSecret", "")).strip()
    domain = str(feishu.get("domain", "") or main.get("domain", "") or "feishu").strip()
    if not app_id or not app_secret:
        return {}
    return {"app_id": app_id, "app_secret": app_secret, "domain": domain}


def derive_bitable_user_open_id(env_map: dict[str, str]) -> str:
    explicit = env_map.get("FEISHU_BITABLE_USER_OPEN_ID", "").strip()
    if explicit:
        return explicit
    delivery_channel = env_map.get("DELIVERY_CHANNEL", DEFAULT_ENV["DELIVERY_CHANNEL"]).strip().lower()
    delivery_target = env_map.get("DELIVERY_TARGET", "").strip()
    if delivery_channel == "feishu" and delivery_target.startswith("ou_"):
        return delivery_target
    return ""


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


def local_now(ts: float | int | None = None) -> datetime:
    if ts is None:
        return datetime.now().astimezone()
    return datetime.fromtimestamp(ts).astimezone()


def parse_datetime_text(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.astimezone()
        return parsed.astimezone()
    except ValueError:
        return None


def tweet_created_at(tweet: dict[str, Any]) -> datetime | None:
    return parse_datetime_text(str(tweet.get("tweet_created_at", "")))


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


def parse_int_env(env_map: dict[str, str], key: str, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    raw = str(env_map.get(key, default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"{key} must be an integer") from exc
    if value < minimum:
        raise SystemExit(f"{key} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise SystemExit(f"{key} must be <= {maximum}")
    return value


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


def tweet_text(tweet: dict[str, Any]) -> str:
    return truncate_text(tweet.get("full_text") or tweet.get("text") or "", 4000)


def referenced_tweet_context(tweet: dict[str, Any]) -> tuple[str, str, str]:
    if tweet.get("retweeted_status"):
        referenced = tweet["retweeted_status"]
        author = referenced.get("user", {})
        author_label = f"{author.get('name', '')} (@{author.get('screen_name', '')})".strip()
        link = (
            f"https://x.com/{author.get('screen_name')}/status/"
            f"{referenced.get('id_str') or referenced.get('id')}"
        )
        return (author_label, link, tweet_text(referenced))
    if tweet.get("quoted_status"):
        referenced = tweet["quoted_status"]
        author = referenced.get("user", {})
        author_label = f"{author.get('name', '')} (@{author.get('screen_name', '')})".strip()
        link = (
            f"https://x.com/{author.get('screen_name')}/status/"
            f"{referenced.get('id_str') or referenced.get('id')}"
        )
        return (author_label, link, tweet_text(referenced))
    return ("", "", "")


def summarise_overflow(account: dict[str, Any], skipped_count: int, delivered_count: int, newest_id: str) -> str:
    return "\n".join([
        "【X 监控】发现新帖过多，已限流推送",
        f"账号：{account['name']} (@{account['screen_name']})",
        f"本轮新帖：{skipped_count + delivered_count}",
        f"已推送：最新 {delivered_count} 条",
        f"已跳过：较早的 {skipped_count} 条",
        f"最新帖子 ID：{newest_id}",
        "",
        "说明：为了控制单账号单轮消息量，系统会只发送最新几条。",
    ]).strip()


def compact_time(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    try:
        normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime("%m-%d %H:%M")
    except ValueError:
        pass
    if len(text) >= 16 and "T" in text:
        return text[5:16].replace("T", " ")
    if len(text) >= 16 and " " in text:
        return text[5:16]
    return text[:16]


def type_label(tweet_type: str) -> str:
    return {
        "tweet": "原创",
        "quote": "引用",
        "repost": "转发",
        "reply": "回复",
    }.get(tweet_type, tweet_type)


def compact_summary_text(tweet: dict[str, Any]) -> str:
    source = tweet
    if tweet.get("retweeted_status"):
        source = tweet["retweeted_status"]
    text = tweet_text(source)
    text = re.sub(r"\s+", " ", text).strip()
    return truncate_text(text, 48) or "-"


def normalize_text_block(text: str) -> str:
    value = (text or "").strip()
    value = re.sub(r"(?:\s+https?://\S+)+\s*$", "", value)
    return re.sub(r"\s+", " ", value).strip()


def fallback_translate_to_chinese(text: str, enabled: bool) -> str:
    value = normalize_text_block(text)
    if not value:
        return ""
    if is_chinese_text(value):
        return value
    if not enabled:
        return value
    return translate_text(value, "zh-CN", True) or value


def digest_main_text(tweet: dict[str, Any]) -> str:
    if tweet.get("retweeted_status"):
        return ""
    return normalize_text_block(tweet_text(tweet))


def digest_referenced_text(tweet: dict[str, Any]) -> str:
    if tweet.get("retweeted_status"):
        return normalize_text_block(tweet_text(tweet["retweeted_status"]))
    if tweet.get("quoted_status"):
        return normalize_text_block(tweet_text(tweet["quoted_status"]))
    return ""


def digest_summary_source(tweet: dict[str, Any]) -> str:
    main_text = digest_main_text(tweet)
    referenced_text = digest_referenced_text(tweet)
    parts: list[str] = []
    if main_text:
        parts.append(f"post: {main_text}")
    if referenced_text:
        parts.append(f"referenced: {referenced_text}")
    if parts:
        return "\n".join(parts)
    return normalize_text_block(tweet_text(tweet))


def parse_json_object(text: str) -> Any:
    value = (text or "").strip()
    if not value:
        raise ValueError("empty model response")
    candidates = [value]
    fenced = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", value, flags=re.DOTALL)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    start = min([idx for idx in [value.find("{"), value.find("[")] if idx != -1], default=-1)
    end = max(value.rfind("}"), value.rfind("]"))
    if start != -1 and end != -1 and end > start:
        candidates.append(value[start:end + 1])
    last_error: Exception | None = None
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception as exc:
            last_error = exc
    raise ValueError(f"failed to parse model JSON: {last_error}")


def run_lobster_json(prompt: str, timeout_seconds: int = 120) -> Any:
    proc = run_command([
        *openclaw_cli_args(),
        "--no-color",
        "agent",
        "--agent",
        TRANSLATE_AGENT_ID,
        "--message",
        prompt,
        "--thinking",
        "off",
        "--timeout",
        str(timeout_seconds),
        "--json",
    ])
    payload = json.loads(proc.stdout)
    texts = [
        item.get("text", "")
        for item in payload.get("result", {}).get("payloads", [])
        if isinstance(item, dict)
    ]
    return parse_json_object("\n".join(texts).strip())


def lobster_enrich_rows(rows: list[dict[str, str]], translate_enabled: bool) -> list[dict[str, str]]:
    if not rows:
        return rows
    model_map: dict[str, dict[str, str]] = {}
    if translate_enabled:
        prompt = (
            "\u4f60\u662f X \u5e16\u5b50\u76d1\u63a7\u52a9\u624b\u3002\u4f60\u8981\u5bf9\u6bcf\u6761\u5e16\u5b50\u505a\u4e24\u4ef6\u4e8b\uff1a"
            "\u7528\u81ea\u7136\u4e2d\u6587\u603b\u7ed3\u8fd9\u6761\u5e16\u5b50\u5728\u8bf4\u4ec0\u4e48\uff0c\u5e76\u7ffb\u8bd1\u9700\u8981\u663e\u793a\u7684\u82f1\u6587\u5185\u5bb9\u3002\n"
            "\u89c4\u5219\uff1a\n"
            "1. \u53ea\u8fd4\u56de JSON\uff0c\u4e0d\u8981\u89e3\u91ca\uff0c\u4e0d\u8981 markdown\u3002\n"
            "2. summary \u662f 32-80 \u5b57\u7684\u4e2d\u6587\u5185\u5bb9\u6458\u8981\uff0c\u8981\u50cf\u4eba\u5199\u7684\u4fe1\u606f\u6458\u8981\uff0c"
            "\u8981\u62bd\u53d6\u4e3b\u65e8\u3001\u884c\u4e3a\u548c\u610f\u56fe\uff0c\u4e0d\u8981\u590d\u8ff0\u88c5\u9970\u6027 emoji\u3001\u611f\u53f9\u8bcd\u6216\u65e0\u5173\u7ec6\u8282\u3002\n"
            "3. \u5bf9 repost\uff08\u8f6c\u53d1\uff09\uff0csummary \u8981\u603b\u7ed3\u88ab\u8f6c\u53d1\u5185\u5bb9\u5728\u8bf4\u4ec0\u4e48\uff0c"
            "\u4ee5\u53ca\u53d1\u5e16\u4eba\u5728\u4f20\u8fbe/\u653e\u5927\u4ec0\u4e48\u4fe1\u606f\uff1b\u4e0d\u8981\u5199\u201c\u5e26\u4e86\u67d0\u4e2a emoji\u201d\u8fd9\u79cd\u4f4e\u4ef7\u503c\u5185\u5bb9\u3002\n"
            "4. \u5bf9 quote\uff08\u5f15\u7528\uff09\uff0csummary \u8981\u540c\u65f6\u6982\u62ec\u4ed6\u7684\u8bc4\u8bba\u548c\u88ab\u5f15\u7528\u7684\u5185\u5bb9\u3002\n"
            "5. main_translation \u548c referenced_translation \u90fd\u8981\u662f\u81ea\u7136\u7b80\u4f53\u4e2d\u6587\uff0c"
            "\u5bf9\u6781\u77ed\u53e3\u53f7\u3001\u7b80\u77ed\u8868\u8fbe\u8981\u610f\u8bd1\uff0c\u4e0d\u8981\u751f\u786c\u76f4\u8bd1\u3002\n"
            "6. \u5982\u679c\u67d0\u9879\u6ca1\u6709\u5185\u5bb9\uff0c\u5bf9\u5e94\u5b57\u6bb5\u8fd4\u56de\u7a7a\u5b57\u7b26\u4e32\u3002\n"
            "7. \u8fd4\u56de\u683c\u5f0f\uff1a"
            "{\"items\":[{\"id\":\"...\",\"summary\":\"...\",\"main_translation\":\"...\",\"referenced_translation\":\"...\"}]}\n"
            "\u8f93\u5165 JSON\uff1a\n"
            f"{json.dumps(rows, ensure_ascii=False)}"
        )
        try:
            result = run_lobster_json(prompt, timeout_seconds=180)
            items = result.get("items", []) if isinstance(result, dict) else result
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    key = str(item.get('id', '')).strip()
                    if not key:
                        continue
                    model_map[key] = {
                        "summary": str(item.get("summary", "")).strip(),
                        "main_translation": str(item.get("main_translation", "")).strip(),
                        "referenced_translation": str(item.get("referenced_translation", "")).strip(),
                    }
        except Exception:
            model_map = {}
    for row in rows:
        enriched = model_map.get(row["tweet_id"], {})
        fallback_summary = fallback_translate_to_chinese(row["summary_source"], translate_enabled)
        row["summary"] = enriched.get("summary", "") or truncate_text(fallback_summary, 96)
        row["main_translation"] = enriched.get("main_translation", "") or fallback_translate_to_chinese(row["main_text"], translate_enabled)
        row["referenced_translation"] = enriched.get("referenced_translation", "") or fallback_translate_to_chinese(row["referenced_text"], translate_enabled)
    return rows


def summary_schedule(env_map: dict[str, str], now_ts: float | int | None = None) -> dict[str, Any]:
    window_hours = parse_int_env(env_map, "SUMMARY_WINDOW_HOURS", int(DEFAULT_ENV["SUMMARY_WINDOW_HOURS"]), minimum=1, maximum=12)
    interval_hours = parse_int_env(env_map, "SUMMARY_INTERVAL_HOURS", int(DEFAULT_ENV["SUMMARY_INTERVAL_HOURS"]), minimum=1, maximum=12)
    start_hour = parse_int_env(env_map, "SUMMARY_ACTIVE_START_HOUR", int(DEFAULT_ENV["SUMMARY_ACTIVE_START_HOUR"]), minimum=0, maximum=23)
    end_hour = parse_int_env(env_map, "SUMMARY_ACTIVE_END_HOUR", int(DEFAULT_ENV["SUMMARY_ACTIVE_END_HOUR"]), minimum=1, maximum=23)
    if end_hour <= start_hour:
        raise SystemExit("SUMMARY_ACTIVE_END_HOUR must be greater than SUMMARY_ACTIVE_START_HOUR")
    if window_hours > (end_hour - start_hour):
        raise SystemExit("SUMMARY_WINDOW_HOURS must fit inside the active daytime window")
    now_dt = local_now(now_ts)
    day_start = now_dt.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    day_end = now_dt.replace(hour=end_hour, minute=0, second=0, microsecond=0)
    slot_hours = list(range(start_hour, end_hour + 1, interval_hours))
    slot_hour = next((hour for hour in reversed(slot_hours) if now_dt >= now_dt.replace(hour=hour, minute=0, second=0, microsecond=0)), None)
    if slot_hour is None:
        return {
            "should_run": False,
            "reason": "before_first_slot",
            "window_hours": window_hours,
            "interval_hours": interval_hours,
            "start_hour": start_hour,
            "end_hour": end_hour,
        }
    slot_end = now_dt.replace(hour=slot_hour, minute=0, second=0, microsecond=0)
    if slot_hour - start_hour < window_hours:
        return {
            "should_run": False,
            "reason": "window_not_ready",
            "slot_end": slot_end.isoformat(),
            "window_hours": window_hours,
            "interval_hours": interval_hours,
            "start_hour": start_hour,
            "end_hour": end_hour,
        }
    window_start = max(day_start, slot_end - timedelta(hours=window_hours))
    return {
        "should_run": True,
        "window_hours": window_hours,
        "interval_hours": interval_hours,
        "start_hour": start_hour,
        "end_hour": end_hour,
        "slot_key": slot_end.strftime("%Y-%m-%d %H:%M:%S"),
        "window_start": window_start,
        "window_end": slot_end,
        "window_label": f"{window_start.strftime('%m-%d %H:%M')} - {slot_end.strftime('%m-%d %H:%M')}",
        "day_start": day_start,
        "day_end": day_end,
    }


def tweet_in_window(tweet: dict[str, Any], window_start: datetime, window_end: datetime) -> bool:
    created_at = tweet_created_at(tweet)
    if created_at is None:
        return False
    return window_start <= created_at <= window_end


def summary_dedupe_key(tweet: dict[str, Any]) -> str:
    source = normalize_text_block(digest_main_text(tweet) or digest_referenced_text(tweet) or tweet_text(tweet))
    if source:
        return source.lower()[:400]
    return str(tweet.get("id_str") or tweet.get("id") or "")


def dedupe_summary_tweets(tweets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for tweet in sort_tweets_descending(tweets):
        key = summary_dedupe_key(tweet)
        if key in seen:
            continue
        seen.add(key)
        unique.append(tweet)
    return unique


def build_summary_row(tweet: dict[str, Any], account: dict[str, Any]) -> dict[str, str]:
    return {
        "account_name": account.get("name", ""),
        "screen_name": account.get("screen_name", ""),
        "tweet_id": str(tweet.get("id_str") or tweet.get("id") or ""),
        "type": classify_tweet(tweet),
        "type_label": type_label(classify_tweet(tweet)),
        "created_at": compact_time(str(tweet.get("tweet_created_at", ""))),
        "summary_source": digest_summary_source(tweet),
        "main_text": digest_main_text(tweet),
        "referenced_text": digest_referenced_text(tweet),
    }


def lobster_summarize_accounts(accounts: list[dict[str, Any]], window_hours: int, translate_enabled: bool) -> list[dict[str, Any]]:
    if not accounts:
        return accounts
    model_map: dict[str, dict[str, Any]] = {}
    if translate_enabled:
        prompt = (
            f"你是 X 账号监控摘要助手。请阅读每个账号最近 {window_hours} 小时内的推文集合，并输出按账号汇总的中文摘要。\n"
            "规则：\n"
            "1. 只返回 JSON，不要解释，不要 markdown。\n"
            "2. 返回格式：{\"items\":[{\"screen_name\":\"...\",\"overview\":\"...\",\"points\":[\"...\",\"...\"]}]}\n"
            "3. overview 用 24-60 字中文，直接概括这个账号这段时间主要在干什么。\n"
            "4. points 返回 1-5 条中文要点，每条 18-60 字，去重，不要互相重复，不要照抄原文。\n"
            "5. 如果内容大多是转发，要总结它主要在转传、放大什么信息。\n"
            "6. 不要编造输入里没有的信息，不要输出链接、emoji、时间戳。\n"
            f"输入 JSON：\n{json.dumps(accounts, ensure_ascii=False)}"
        )
        try:
            result = run_lobster_json(prompt, timeout_seconds=180)
            items = result.get("items", []) if isinstance(result, dict) else result
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    screen_name = str(item.get("screen_name", "")).strip()
                    if not screen_name:
                        continue
                    points = item.get("points", [])
                    if not isinstance(points, list):
                        points = []
                    model_map[screen_name.lower()] = {
                        "overview": str(item.get("overview", "")).strip(),
                        "points": [str(point).strip() for point in points if str(point).strip()],
                    }
        except Exception:
            model_map = {}
    for account in accounts:
        enriched = model_map.get(str(account.get("screen_name", "")).lower(), {})
        overview = enriched.get("overview", "")
        points = enriched.get("points", [])
        if not overview:
            overview = f"最近 {window_hours} 小时主要围绕以下几件事发声或转发。"
        if not points:
            fallback_points: list[str] = []
            for row in account.get("rows", [])[:5]:
                text = fallback_translate_to_chinese(row.get("summary_source", ""), translate_enabled)
                text = truncate_text(normalize_text_block(text), 60)
                if text and text not in fallback_points:
                    fallback_points.append(text)
            points = fallback_points
        account["overview"] = overview
        account["points"] = points[:5]
    return accounts


def format_summary_notification(schedule: dict[str, Any], accounts: list[dict[str, Any]]) -> str:
    lines = [f"X 账号摘要（{schedule['window_label']}）"]
    for account in accounts:
        lines.extend([
            "",
            f"{account['account_name']}：最近 {schedule['window_hours']} 小时发了 {account['raw_count']} 条推特。",
            account.get("overview", "") or "这段时间没有可摘要的新内容。",
        ])
        for index, point in enumerate(account.get("points", [])[:5], start=1):
            lines.append(f"{index}. {point}")
    return "\n".join(lines).strip()


def format_detailed_notification(row: dict[str, str]) -> str:
    row_type = row["type"]
    lines = [
        f"{row['account_name']} {row['type_label']}",
        f"\u65f6\u95f4\uff1a{row['created_at']}",
        "",
        "\u5185\u5bb9\u6458\u8981\uff1a",
        row["summary"] or "-",
    ]
    if row_type in {"tweet", "reply"}:
        lines.extend([
            "",
            "\u539f\u6587\uff1a",
            row["main_text"] or "-",
            "",
            row["main_translation"] or "-",
        ])
    elif row_type == "repost":
        lines.extend([
            "",
            "\u539f\u6587\uff1a",
            row["referenced_text"] or "-",
            "",
            row["referenced_translation"] or "-",
        ])
    elif row_type == "quote":
        lines.extend([
            "",
            "\u4ed6\u7684\u8bc4\u8bba\u539f\u6587\uff1a",
            row["main_text"] or "-",
            "",
            row["main_translation"] or "-",
            "",
            "\u5f15\u7528\u5185\u5bb9\u539f\u6587\uff1a",
            row["referenced_text"] or "-",
            "",
            row["referenced_translation"] or "-",
        ])
    return "\n".join(lines).strip()


def table_cell(text: str) -> str:
    value = normalize_text_block(text)
    if not value:
        return "-"
    return value.replace("|", "/")


def compact_summary_points(points: list[str]) -> str:
    cleaned = [normalize_text_block(item) for item in points if normalize_text_block(item)]
    if not cleaned:
        return ""
    return "；".join(cleaned[:5])


def format_grouped_digest_table(
    rows: list[dict[str, str]],
    overflow_rows: list[dict[str, str]],
) -> str:
    grouped: dict[str, list[dict[str, str]]] = {}
    account_labels: dict[str, str] = {}
    for row in rows:
        key = row["screen_name"]
        grouped.setdefault(key, []).append(row)
        account_labels[key] = f"{row['account_name']} (@{row['screen_name']})"
    lines = [
        "\u3010X \u76d1\u63a7\u3011\u6309\u8d26\u53f7\u5206\u7ec4\u6c47\u603b",
        f"\u65f6\u95f4\uff1a{local_timestamp()}",
        f"\u8d26\u53f7\u6570\uff1a{len(grouped)}",
        f"\u65b0\u5e16\u6570\uff1a{len(rows)}",
        "",
        "\u8bf4\u660e\uff1a\u6bcf\u4e2a\u8d26\u53f7\u53ea\u4fdd\u7559\u6700\u65b0 3 \u6761\uff0c\u5185\u5bb9\u6309\u4f60\u8981\u7684\u5b57\u6bb5\u8f93\u51fa\u3002",
    ]
    for screen_name, items in grouped.items():
        lines.extend([
            "",
            f"\u8d26\u53f7\uff1a{account_labels[screen_name]}",
            "\u5e8f\u53f7 | \u65f6\u95f4 | \u4e00\u53e5\u8bdd\u7b80\u4ecb | \u539f\u6587\uff08\u82f1\u8bed\uff09 | \u4e2d\u6587\u7ffb\u8bd1 | \u8f6c\u53d1\u5185\u5bb9 | \u8f6c\u53d1\u5185\u5bb9\u4e2d\u6587",
            "--- | --- | --- | --- | --- | --- | ---",
        ])
        for index, item in enumerate(items, start=1):
            lines.append(
                " | ".join([
                    str(index),
                    table_cell(item["created_at"]),
                    table_cell(item["summary"]),
                    table_cell(item["main_text"]),
                    table_cell(item["main_translation"]),
                    table_cell(item["referenced_text"]),
                    table_cell(item["referenced_translation"]),
                ])
            )
        note = next((entry for entry in overflow_rows if entry["screen_name"] == screen_name), None)
        if note:
            lines.append(
                f"\u5907\u6ce8\uff1a\u672c\u8f6e\u53d1\u73b0 {note['total']} \u6761\uff0c\u4ec5\u5c55\u793a\u6700\u65b0 {note['shown']} \u6761\uff0c"
                f"\u8df3\u8fc7 {note['skipped']} \u6761\u3002"
            )
    return "\n".join(lines).strip()


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
        *openclaw_cli_args(),
        "message",
        "send",
        "--channel", channel,
        "--target", target,
        "--message", text,
    ])


class FeishuTenantBitableClient:
    def __init__(self, app_id: str, app_secret: str, app_token: str, table_id: str | None = None) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.table_id = table_id or ""
        self._tenant_access_token = ""
        self._token_expiry = 0.0
        self._prepared_field_sets: set[tuple[str, ...]] = set()

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.tenant_access_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def tenant_access_token(self) -> str:
        now = time.time()
        if self._tenant_access_token and now < self._token_expiry - 60:
            return self._tenant_access_token
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret,
        }
        data = request_json(
            f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
            method="POST",
            payload=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            retries=2,
            timeout=20,
        )
        if data.get("code") != 0:
            raise RuntimeError(f"failed to get Feishu tenant token: {data}")
        self._tenant_access_token = str(data.get("tenant_access_token", "")).strip()
        self._token_expiry = now + int(data.get("expire", 7200))
        if not self._tenant_access_token:
            raise RuntimeError("Feishu tenant token missing in auth response")
        return self._tenant_access_token

    def ensure_fields(self, field_names: tuple[str, ...]) -> None:
        self.ensure_table_id()
        if field_names in self._prepared_field_sets:
            return
        data = request_json(
            f"{FEISHU_BASE}/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/fields?page_size=500",
            headers=self._auth_headers(),
            timeout=20,
        )
        if data.get("code") != 0:
            raise RuntimeError(f"failed to list Feishu Bitable fields: {data}")
        existing = {
            str(item.get("field_name", "")).strip()
            for item in data.get("data", {}).get("items", [])
            if item.get("field_name")
        }
        for field_name in field_names:
            if field_name in existing:
                continue
            created = request_json(
                f"{FEISHU_BASE}/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/fields",
                method="POST",
                payload={
                    "field_name": field_name,
                    "type": 1,
                },
                headers=self._auth_headers(),
                timeout=20,
            )
            if created.get("code") != 0:
                raise RuntimeError(f"failed to create Feishu Bitable field '{field_name}': {created}")
        self._prepared_field_sets.add(field_names)

    def ensure_table_id(self) -> str:
        if self.table_id:
            return self.table_id
        data = request_json(
            f"{FEISHU_BASE}/bitable/v1/apps/{self.app_token}/tables?page_size=200",
            headers=self._auth_headers(),
            timeout=20,
        )
        if data.get("code") != 0:
            raise RuntimeError(f"failed to list Feishu Bitable tables: {data}")
        items = data.get("data", {}).get("items", [])
        if len(items) == 1:
            self.table_id = str(items[0].get("table_id", "")).strip()
            if not self.table_id:
                raise RuntimeError(f"Feishu Bitable returned a table without table_id: {data}")
            return self.table_id
        if not items:
            raise RuntimeError("Feishu Bitable has no tables; create one table first")
        names = [str(item.get("name", "")).strip() for item in items]
        raise RuntimeError(
            "FEISHU_BITABLE_TABLE_ID is required when multiple tables exist. "
            f"Available tables: {names}"
        )

    def append_tweet(self, tweet: dict[str, Any], account: dict[str, Any]) -> None:
        self.ensure_fields(BITABLE_TWEET_FIELDS)
        referenced_author, referenced_url, referenced_text = referenced_tweet_context(tweet)
        payload = {
            "fields": {
                "Tweet ID": str(tweet.get("id_str") or tweet.get("id") or ""),
                "Account Name": account.get("name", ""),
                "Screen Name": account.get("screen_name", ""),
                "Alias": account.get("alias", ""),
                "Type": classify_tweet(tweet),
                "Created At": str(tweet.get("tweet_created_at", "")),
                "Tweet URL": f"https://x.com/{account['screen_name']}/status/{tweet['id_str']}",
                "Main Text": tweet_text(tweet),
                "Referenced Author": referenced_author,
                "Referenced URL": referenced_url,
                "Referenced Text": referenced_text,
                "Recorded At": local_timestamp(),
                "Data Source": "SocialData",
            }
        }
        data = request_json(
            f"{FEISHU_BASE}/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records",
            method="POST",
            payload=payload,
            headers=self._auth_headers(),
            timeout=20,
        )
        if data.get("code") != 0:
            raise RuntimeError(f"failed to append Feishu Bitable record: {data}")

    def append_summary(self, account_summary: dict[str, Any], schedule: dict[str, Any]) -> None:
        self.ensure_fields(BITABLE_SUMMARY_FIELDS)
        points_text = compact_summary_points(list(account_summary.get("points", [])))
        payload = {
            "fields": {
                "时间": schedule.get("window_end", local_now()).strftime("%m-%d %H:%M"),
                "账号": f"{account_summary.get('account_name', '')} (@{account_summary.get('screen_name', '')})".strip(),
                "发了什么": points_text or account_summary.get("overview", ""),
                "核心意思": account_summary.get("overview", ""),
            }
        }
        data = request_json(
            f"{FEISHU_BASE}/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records",
            method="POST",
            payload=payload,
            headers=self._auth_headers(),
            timeout=20,
        )
        if data.get("code") != 0:
            raise RuntimeError(f"failed to append Feishu Bitable summary record: {data}")


class FeishuPluginBitableClient:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        app_token: str,
        table_id: str | None,
        user_open_id: str,
        domain: str = "feishu",
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.table_id = table_id or ""
        self.user_open_id = user_open_id
        self.domain = domain or "feishu"

    def _helper_request(self, fields: dict[str, str], field_names: tuple[str, ...]) -> None:
        if not BITABLE_NODE_HELPER_PATH.exists():
            raise RuntimeError(f"Feishu Bitable helper not found: {BITABLE_NODE_HELPER_PATH}")
        payload = {
            "action": "append_record",
            "appId": self.app_id,
            "appSecret": self.app_secret,
            "domain": self.domain,
            "userOpenId": self.user_open_id,
            "appToken": self.app_token,
            "tableId": self.table_id,
            "fieldNames": list(field_names),
            "fields": fields,
        }
        proc = run_command_with_input(
            ["node", str(BITABLE_NODE_HELPER_PATH)],
            json.dumps(payload, ensure_ascii=False),
        )
        data = json.loads(proc.stdout.strip() or "{}")
        table_id = str(data.get("tableId", "")).strip()
        if table_id:
            self.table_id = table_id

    def append_tweet(self, tweet: dict[str, Any], account: dict[str, Any]) -> None:
        referenced_author, referenced_url, referenced_text = referenced_tweet_context(tweet)
        self._helper_request(
            {
                "Tweet ID": str(tweet.get("id_str") or tweet.get("id") or ""),
                "Account Name": account.get("name", ""),
                "Screen Name": account.get("screen_name", ""),
                "Alias": account.get("alias", ""),
                "Type": classify_tweet(tweet),
                "Created At": str(tweet.get("tweet_created_at", "")),
                "Tweet URL": f"https://x.com/{account['screen_name']}/status/{tweet['id_str']}",
                "Main Text": tweet_text(tweet),
                "Referenced Author": referenced_author,
                "Referenced URL": referenced_url,
                "Referenced Text": referenced_text,
                "Recorded At": local_timestamp(),
                "Data Source": "SocialData",
            },
            BITABLE_TWEET_FIELDS,
        )

    def append_summary(self, account_summary: dict[str, Any], schedule: dict[str, Any]) -> None:
        points_text = compact_summary_points(list(account_summary.get("points", [])))
        self._helper_request(
            {
                "时间": schedule.get("window_end", local_now()).strftime("%m-%d %H:%M"),
                "账号": f"{account_summary.get('account_name', '')} (@{account_summary.get('screen_name', '')})".strip(),
                "发了什么": points_text or account_summary.get("overview", ""),
                "核心意思": account_summary.get("overview", ""),
            },
            BITABLE_SUMMARY_FIELDS,
        )


def sort_tweets_ascending(tweets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(tweets, key=lambda item: int(item.get("id_str") or item.get("id") or 0))


def sort_tweets_descending(tweets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(tweets, key=lambda item: int(item.get("id_str") or item.get("id") or 0), reverse=True)


def newest_tweet_id(tweets: list[dict[str, Any]]) -> str:
    if not tweets:
        return ""
    newest = max(tweets, key=lambda item: int(item.get("id_str") or item.get("id") or 0))
    return str(newest.get("id_str") or newest.get("id") or "")


def bitable_client_from_env(env_map: dict[str, str]) -> FeishuTenantBitableClient | FeishuPluginBitableClient | None:
    app_token = env_map.get("FEISHU_BITABLE_APP_TOKEN", "").strip()
    table_id = env_map.get("FEISHU_BITABLE_TABLE_ID", "").strip()
    if not app_token:
        return None
    auth_mode = env_map.get("FEISHU_BITABLE_AUTH_MODE", "plugin").strip().lower()
    if auth_mode in {"plugin", "official", "user"}:
        creds = load_openclaw_feishu_account()
        app_id = creds.get("app_id", "")
        app_secret = creds.get("app_secret", "")
        domain = creds.get("domain", "feishu")
        user_open_id = derive_bitable_user_open_id(env_map)
        if not app_id or not app_secret:
            raise RuntimeError("Feishu Bitable plugin mode requires Feishu app credentials in openclaw.json")
        if not user_open_id:
            raise RuntimeError(
                "Feishu Bitable plugin mode requires FEISHU_BITABLE_USER_OPEN_ID, "
                "or a Feishu DELIVERY_TARGET that is a user open_id"
            )
        return FeishuPluginBitableClient(app_id, app_secret, app_token, table_id, user_open_id, domain)
    app_id = env_map.get("FEISHU_APP_ID", "").strip()
    app_secret = env_map.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        creds = load_openclaw_feishu_account()
        app_id = creds.get("app_id", "")
        app_secret = creds.get("app_secret", "")
    if not app_id or not app_secret:
        raise RuntimeError("Feishu Bitable is configured but app credentials are unavailable")
    return FeishuTenantBitableClient(app_id, app_secret, app_token, table_id)


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
        "poll_limit": parse_int_env(env_map, "POLL_LIMIT", int(DEFAULT_ENV["POLL_LIMIT"]), minimum=1, maximum=20),
        "max_new_per_account": parse_int_env(env_map, "MAX_NEW_PER_ACCOUNT", int(DEFAULT_ENV["MAX_NEW_PER_ACCOUNT"]), minimum=1, maximum=20),
        "push_mode": env_map.get("PUSH_MODE", DEFAULT_ENV["PUSH_MODE"]).strip(),
        "translate_enabled": env_map.get("TRANSLATE_ENABLED", DEFAULT_ENV["TRANSLATE_ENABLED"]).lower() == "true",
        "summary_window_hours": parse_int_env(env_map, "SUMMARY_WINDOW_HOURS", int(DEFAULT_ENV["SUMMARY_WINDOW_HOURS"]), minimum=1, maximum=12),
        "summary_interval_hours": parse_int_env(env_map, "SUMMARY_INTERVAL_HOURS", int(DEFAULT_ENV["SUMMARY_INTERVAL_HOURS"]), minimum=1, maximum=12),
        "summary_active_start_hour": parse_int_env(env_map, "SUMMARY_ACTIVE_START_HOUR", int(DEFAULT_ENV["SUMMARY_ACTIVE_START_HOUR"]), minimum=0, maximum=23),
        "summary_active_end_hour": parse_int_env(env_map, "SUMMARY_ACTIVE_END_HOUR", int(DEFAULT_ENV["SUMMARY_ACTIVE_END_HOUR"]), minimum=1, maximum=23),
        "api_key_configured": bool(env_map.get("SOCIALDATA_API_KEY", "")),
        "bitable_enabled": bool(env_map.get("FEISHU_BITABLE_APP_TOKEN", "").strip()),
        "bitable_table_id_configured": bool(env_map.get("FEISHU_BITABLE_TABLE_ID", "").strip()),
        "bitable_auth_mode": env_map.get("FEISHU_BITABLE_AUTH_MODE", "plugin").strip().lower(),
        "bitable_user_open_id_configured": bool(derive_bitable_user_open_id(env_map)),
    }


def show_status(state: dict[str, Any], env_map: dict[str, str]) -> dict[str, Any]:
    payload = public_config(env_map)
    payload["watch_timer"] = timer_state(current_watch_timer())
    payload["openclaw_profile"] = current_openclaw_profile() or "default"
    payload["openclaw_config_path"] = str(current_openclaw_config_path())
    payload["last_summary_slot"] = state.get("summary", {}).get("last_slot_end", "")
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


def preview_all_accounts(
    state: dict[str, Any],
    apikey: str,
    limit: int,
    translate_enabled: bool,
) -> str:
    accounts = [item for item in state.get("accounts", []) if item.get("enabled", True)]
    if not accounts:
        return "No monitored accounts configured."
    sections: list[str] = []
    for account in accounts:
        try:
            tweets = socialdata_user_tweets(str(account["user_id"]), apikey, max(limit, 5))
        except Exception as exc:
            sections.append(
                "\n".join([
                    f"【测试预览】{account['name']} (@{account['screen_name']})",
                    f"抓取失败：{exc}",
                ])
            )
            continue
        if not tweets:
            sections.append(
                "\n".join([
                    f"【测试预览】@{account['screen_name']}",
                    "没有取到最近帖子。",
                ])
            )
            continue
        latest = sort_tweets_descending(tweets)[:limit]
        rendered = [
            format_notification(tweet, account, translate_enabled)
            for tweet in sort_tweets_ascending(latest)
        ]
        header = f"【测试预览】{account['name']} (@{account['screen_name']})"
        sections.append(header + "\n\n" + ("\n\n" + ("-" * 48) + "\n\n").join(rendered))
    return "\n\n" + ("=" * 64) + "\n\n".join([""] + sections)


def set_config(
    env_map: dict[str, str],
    *,
    delivery_channel: str | None,
    delivery_target: str | None,
    poll_limit: int | None,
    max_new_per_account: int | None,
    push_mode: str | None,
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
    if max_new_per_account is not None:
        if max_new_per_account < 1 or max_new_per_account > 20:
            raise SystemExit("MAX_NEW_PER_ACCOUNT must be between 1 and 20")
        env_map["MAX_NEW_PER_ACCOUNT"] = str(max_new_per_account)
        changed = True
    if push_mode is not None:
        normalized = push_mode.strip().lower()
        if normalized not in {"detail", "table", "summary"}:
            raise SystemExit("PUSH_MODE must be detail, table, or summary")
        env_map["PUSH_MODE"] = normalized
        changed = True
    if translate_enabled is not None:
        normalized = translate_enabled.strip().lower()
        if normalized not in {"true", "false"}:
            raise SystemExit("TRANSLATE_ENABLED must be true or false")
        env_map["TRANSLATE_ENABLED"] = normalized
        changed = True
    if not changed:
        raise SystemExit("no config changes requested")
    write_env_map(current_env_path(), env_map)
    return public_config(env_map)


def check_and_push(state: dict[str, Any], env_map: dict[str, str], apikey: str) -> dict[str, Any]:
    poll_limit = parse_int_env(env_map, "POLL_LIMIT", int(DEFAULT_ENV["POLL_LIMIT"]), minimum=1, maximum=20)
    max_new_per_account = parse_int_env(
        env_map,
        "MAX_NEW_PER_ACCOUNT",
        int(DEFAULT_ENV["MAX_NEW_PER_ACCOUNT"]),
        minimum=1,
        maximum=20,
    )
    push_mode = env_map.get("PUSH_MODE", DEFAULT_ENV["PUSH_MODE"]).strip().lower()
    translate_enabled = env_map.get("TRANSLATE_ENABLED", DEFAULT_ENV["TRANSLATE_ENABLED"]).lower() == "true"
    bitable_client = bitable_client_from_env(env_map)
    delivered: list[dict[str, Any]] = []
    bitable_errors: list[dict[str, str]] = []
    overflow_rows: list[dict[str, str]] = []
    grouped_rows: list[dict[str, str]] = []
    summary_accounts: list[dict[str, Any]] = []
    summary_meta: dict[str, Any] | None = None
    summary_state = state.setdefault("summary", {})
    if push_mode == "summary":
        summary_meta = summary_schedule(env_map)
        if not summary_meta.get("should_run", False):
            write_state(state)
            return {
                "delivered_count": 0,
                "delivered": [],
                "checked_accounts": len([item for item in state.get("accounts", []) if item.get("enabled", True)]),
                "bitable_errors": [],
                "push_mode": push_mode,
                "skipped_reason": summary_meta.get("reason", "inactive_window"),
            }
        if summary_state.get("last_slot_end") == summary_meta["slot_key"]:
            write_state(state)
            return {
                "delivered_count": 0,
                "delivered": [],
                "checked_accounts": len([item for item in state.get("accounts", []) if item.get("enabled", True)]),
                "bitable_errors": [],
                "push_mode": push_mode,
                "skipped_reason": "already_sent_for_slot",
                "slot_key": summary_meta["slot_key"],
            }
    for account in state.get("accounts", []):
        if not account.get("enabled", True):
            continue
        tweets = socialdata_user_tweets(str(account["user_id"]), apikey, poll_limit)
        if not tweets:
            account["last_checked_at"] = local_timestamp()
            continue
        newest_id = newest_tweet_id(tweets) or account.get("last_seen_id", "")
        if push_mode == "summary" and summary_meta is not None:
            window_tweets = [
                item for item in tweets
                if tweet_in_window(item, summary_meta["window_start"], summary_meta["window_end"])
            ]
            unique_tweets = dedupe_summary_tweets(window_tweets)
            if unique_tweets:
                summary_accounts.append({
                    "account_name": account.get("name", ""),
                    "screen_name": account.get("screen_name", ""),
                    "raw_count": len(window_tweets),
                    "unique_count": len(unique_tweets),
                    "rows": [build_summary_row(tweet, account) for tweet in unique_tweets],
                })
            account["last_seen_id"] = newest_id
            account["last_checked_at"] = local_timestamp()
            continue
        latest_seen = int(account.get("last_seen_id") or 0)
        new_tweets = [
            item for item in sort_tweets_ascending(tweets)
            if int(item.get("id_str") or item.get("id") or 0) > latest_seen
        ]
        deliver_tweets = sort_tweets_descending(new_tweets)[:max_new_per_account]
        skipped_count = max(0, len(new_tweets) - len(deliver_tweets))
        if skipped_count:
            overflow_rows.append({
                "account_name": account.get("name", ""),
                "screen_name": account.get("screen_name", ""),
                "total": str(len(new_tweets)),
                "shown": str(len(deliver_tweets)),
                "skipped": str(skipped_count),
            })
        for tweet in deliver_tweets:
            url = f"https://x.com/{account['screen_name']}/status/{tweet['id_str']}"
            if bitable_client is not None:
                try:
                    bitable_client.append_tweet(tweet, account)
                except Exception as exc:
                    bitable_errors.append({
                        "screen_name": account.get("screen_name", ""),
                        "tweet_id": str(tweet.get("id_str") or tweet.get("id") or ""),
                        "error": str(exc),
                    })
            delivered.append({
                "account_name": account.get("name", ""),
                "screen_name": account.get("screen_name", ""),
                "tweet_id": str(tweet.get("id_str") or tweet.get("id") or ""),
                "type": classify_tweet(tweet),
                "type_label": type_label(classify_tweet(tweet)),
                "created_at": compact_time(str(tweet.get("tweet_created_at", ""))),
                "summary": compact_summary_text(tweet),
                "url": url,
            })
            grouped_rows.append({
                "account_name": account.get("name", ""),
                "screen_name": account.get("screen_name", ""),
                "tweet_id": str(tweet.get("id_str") or tweet.get("id") or ""),
                "type": classify_tweet(tweet),
                "type_label": type_label(classify_tweet(tweet)),
                "created_at": compact_time(str(tweet.get("tweet_created_at", ""))),
                "summary_source": digest_summary_source(tweet),
                "main_text": digest_main_text(tweet),
                "referenced_text": digest_referenced_text(tweet),
                "url": url,
            })
        account["last_seen_id"] = newest_id
        account["last_checked_at"] = local_timestamp()
    if push_mode == "summary" and summary_meta is not None:
        summary_state["last_slot_end"] = summary_meta["slot_key"]
        summary_state["last_window_label"] = summary_meta["window_label"]
        active_accounts = [item for item in summary_accounts if item.get("raw_count", 0) > 0]
        if active_accounts:
            active_accounts = lobster_summarize_accounts(active_accounts, int(summary_meta["window_hours"]), translate_enabled)
            push_text(format_summary_notification(summary_meta, active_accounts), env_map)
            if bitable_client is not None:
                for item in active_accounts:
                    try:
                        bitable_client.append_summary(item, summary_meta)
                    except Exception as exc:
                        bitable_errors.append({
                            "screen_name": item.get("screen_name", ""),
                            "slot_key": str(summary_meta.get("slot_key", "")),
                            "error": str(exc),
                        })
        write_state(state)
        return {
            "delivered_count": 1 if active_accounts else 0,
            "delivered": [
                {
                    "account_name": item["account_name"],
                    "screen_name": item["screen_name"],
                    "raw_count": item["raw_count"],
                    "unique_count": item["unique_count"],
                }
                for item in active_accounts
            ],
            "checked_accounts": len([item for item in state.get("accounts", []) if item.get("enabled", True)]),
            "bitable_errors": bitable_errors,
            "push_mode": push_mode,
            "slot_key": summary_meta["slot_key"],
            "window_label": summary_meta["window_label"],
        }
    if delivered:
        grouped_rows = lobster_enrich_rows(grouped_rows, translate_enabled)
    if push_mode == "table" and delivered:
        push_text(format_grouped_digest_table(grouped_rows, overflow_rows), env_map)
    elif push_mode == "detail":
        row_by_tweet_id = {row["tweet_id"]: row for row in grouped_rows}
        for item in delivered:
            row = row_by_tweet_id.get(item["tweet_id"])
            if row is None:
                continue
            push_text(format_detailed_notification(row), env_map)
        for item in overflow_rows:
            account_stub = {
                "name": item.get("account_name", item["screen_name"]),
                "screen_name": item["screen_name"],
            }
            push_text(
                summarise_overflow(
                    account_stub,
                    int(item["skipped"]),
                    int(item["shown"]),
                    "",
                ),
                env_map,
            )
    write_state(state)
    return {
        "delivered_count": len(delivered),
        "delivered": delivered,
        "checked_accounts": len([item for item in state.get("accounts", []) if item.get("enabled", True)]),
        "bitable_errors": bitable_errors,
        "push_mode": push_mode,
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
    parser.add_argument("--preview-all", action="store_true", help="Preview recent tweets for all monitored accounts")
    parser.add_argument("--limit", type=int, default=3, help="Preview limit for --preview-account")
    parser.add_argument("--check-and-push", action="store_true", help="Run one monitoring pass and send new tweet notifications")
    parser.add_argument("--pause-watch", action="store_true")
    parser.add_argument("--resume-watch", action="store_true")
    parser.add_argument("--set-delivery-channel", help="Set DELIVERY_CHANNEL")
    parser.add_argument("--set-delivery-target", help="Set DELIVERY_TARGET")
    parser.add_argument("--set-poll-limit", type=int, help="Set POLL_LIMIT")
    parser.add_argument("--set-max-new-per-account", type=int, help="Set MAX_NEW_PER_ACCOUNT")
    parser.add_argument("--set-push-mode", help="Set PUSH_MODE to detail, table, or summary")
    parser.add_argument("--set-translate-enabled", help="Set TRANSLATE_ENABLED to true or false")
    return parser.parse_args()


def main() -> int:
    load_env_file(current_env_path())
    args = parse_args()
    env_map = read_env_map(current_env_path())
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
        print(json.dumps(control_timer(current_watch_timer(), "pause"), ensure_ascii=False, indent=2))
        return 0
    if args.resume_watch:
        print(json.dumps(control_timer(current_watch_timer(), "resume"), ensure_ascii=False, indent=2))
        return 0
    if any(v is not None for v in [
        args.set_delivery_channel,
        args.set_delivery_target,
        args.set_poll_limit,
        args.set_max_new_per_account,
        args.set_push_mode,
        args.set_translate_enabled,
    ]):
        print(json.dumps(set_config(
            env_map,
            delivery_channel=args.set_delivery_channel,
            delivery_target=args.set_delivery_target,
            poll_limit=args.set_poll_limit,
            max_new_per_account=args.set_max_new_per_account,
            push_mode=args.set_push_mode,
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
    if args.preview_all:
        translate_enabled = env_map.get("TRANSLATE_ENABLED", DEFAULT_ENV["TRANSLATE_ENABLED"]).lower() == "true"
        print(preview_all_accounts(state, apikey, args.limit, translate_enabled).strip())
        return 0
    if args.check_and_push:
        print(json.dumps(check_and_push(state, env_map, apikey), ensure_ascii=False, indent=2))
        return 0

    raise SystemExit("no action specified")


if __name__ == "__main__":
    raise SystemExit(main())
