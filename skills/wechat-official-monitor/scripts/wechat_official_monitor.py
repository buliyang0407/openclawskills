#!/usr/bin/env python3
import argparse
import json
import os
import shlex
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_ENV_PATH = Path("/etc/openclaw/wechat-official-monitor.env")
DEFAULT_STATE_PATH = Path("/var/lib/openclaw/wechat-official-monitor/state.json")
DEFAULT_WATCH_TIMER = "openclaw-wechat-official-monitor.timer"
DEFAULT_OPENCLAW_CONFIG_PATH = Path("/root/.openclaw/openclaw.json")
COMMON_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "common" / "scripts"
UA = "Mozilla/5.0 (compatible; OpenClaw WeChat Official Monitor/1.0)"
SUMMARY_AGENT_ID = "main"
DEFAULT_ENV = {
    "DELIVERY_CHANNEL": "feishu",
    "SUMMARY_MODE": "ai",
    "SUMMARY_MAX_ARTICLES": "6",
    "FETCH_LIMIT_PER_ACCOUNT": "5",
    "FETCH_FULL_CONTENT": "true",
    "PUSH_WINDOW_HOURS": "24",
}
BITABLE_ARTICLE_FIELDS = (
    "Source Type",
    "Source Name",
    "Title",
    "Published At",
    "Summary",
    "Source URL",
    "Archived At",
    "Summary Model",
    "Data Source",
)
BITABLE_DEFAULT_TABLE_NAME = "Content Archive"

if str(COMMON_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS_DIR))

from feishu_bitable_plugin import bitable_client_from_env


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if cleaned:
            self.parts.append(cleaned)

    def text(self) -> str:
        return " ".join(self.parts).strip()


def current_env_path() -> Path:
    return Path(os.environ.get("WECHAT_MONITOR_ENV_PATH", str(DEFAULT_ENV_PATH)))


def current_state_path() -> Path:
    return Path(os.environ.get("WECHAT_MONITOR_STATE_PATH", str(DEFAULT_STATE_PATH)))


def current_watch_timer() -> str:
    return os.environ.get("WECHAT_MONITOR_TIMER_UNIT", DEFAULT_WATCH_TIMER).strip() or DEFAULT_WATCH_TIMER


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
        os.environ.setdefault(key.strip(), normalize_env_value(value))


def read_env_map(path: Path) -> dict[str, str]:
    env_map: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env_map[key.strip()] = normalize_env_value(value)
    for key, value in DEFAULT_ENV.items():
        env_map.setdefault(key, value)
    return env_map


def write_env_map(path: Path, env_map: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={format_env_value(value)}" for key, value in env_map.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def normalize_env_value(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    try:
        parts = shlex.split(stripped, posix=True)
        if len(parts) == 1:
            return parts[0]
    except ValueError:
        pass
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def format_env_value(value: str) -> str:
    return shlex.quote(str(value))


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
    method: str = "GET",
    retries: int = 3,
    timeout: int = 30,
) -> str:
    merged_headers = {"User-Agent": UA, "Accept": "application/json, text/xml, application/xml, */*;q=0.8"}
    if headers:
        merged_headers.update(headers)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        req = Request(url, headers=merged_headers, method=method)
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(attempt)
    raise RuntimeError(f"request failed: {url} error={last_error}")


def request_json(url: str) -> Any:
    return json.loads(request_text(url))


def parse_int_env(env_map: dict[str, str], key: str, fallback: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    raw = env_map.get(key, str(fallback)).strip()
    value = int(raw)
    if value < minimum:
        raise SystemExit(f"{key} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise SystemExit(f"{key} must be <= {maximum}")
    return value


def strip_html(raw: str) -> str:
    parser = TextExtractor()
    parser.feed(raw or "")
    return parser.text()


def iso_to_local_text(value: str) -> str:
    dt = parse_datetime(value)
    if dt is None:
        return value
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        return datetime.fromisoformat(text)
    except ValueError:
        try:
            return parsedate_to_datetime(text)
        except Exception:
            return None


def child_text(element: ET.Element, *names: str) -> str:
    lowered = {name.lower() for name in names}
    for child in list(element):
        local_name = child.tag.split("}")[-1].lower()
        if local_name in lowered and (child.text or "").strip():
            return (child.text or "").strip()
    return ""


def parse_feed(feed_xml: str, limit: int) -> list[dict[str, str]]:
    root = ET.fromstring(feed_xml)
    articles: list[dict[str, str]] = []

    def add_article(entry: ET.Element) -> None:
        title = child_text(entry, "title")
        link = child_text(entry, "link")
        guid = child_text(entry, "guid", "id")
        summary = child_text(entry, "description", "summary", "content")
        published = child_text(entry, "pubDate", "published", "updated")
        if not link:
            for child in list(entry):
                local_name = child.tag.split("}")[-1].lower()
                if local_name == "link":
                    href = child.attrib.get("href", "").strip()
                    if href:
                        link = href
                        break
        article_id = guid or link or f"{published}|{title}"
        if not title or not article_id:
            return
        articles.append({
            "id": article_id,
            "title": title,
            "link": link,
            "summary": strip_html(summary),
            "published": published,
        })

    local_root = root.tag.split("}")[-1].lower()
    if local_root == "rss":
        channel = root.find("channel")
        if channel is not None:
            for item in channel.findall("item")[:limit]:
                add_article(item)
    elif local_root == "feed":
        for entry in root.findall("{*}entry")[:limit]:
            add_article(entry)
    else:
        raise RuntimeError(f"unsupported feed root: {root.tag}")
    return articles


def read_state() -> dict[str, Any]:
    state_path = current_state_path()
    if not state_path.exists():
        return {"accounts": []}
    return json.loads(state_path.read_text(encoding="utf-8"))


def write_state(state: dict[str, Any]) -> None:
    state_path = current_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def build_wechat2rss_url(base_url: str, path: str, token: str, **params: str) -> str:
    base = base_url.rstrip("/")
    query = dict(params)
    query["k"] = token
    return f"{base}{path}?{urlencode(query)}"


def wechat2rss_list(base_url: str, token: str, *, name: str | None = None) -> list[dict[str, Any]]:
    params: dict[str, str] = {"page": "1", "size": "100"}
    if name:
        params["name"] = name
    payload = request_json(build_wechat2rss_url(base_url, "/list", token, **params))
    data = payload.get("data", [])
    if not isinstance(data, list):
        raise RuntimeError(f"unexpected Wechat2RSS list payload: {payload}")
    return data


def wechat2rss_addurl(base_url: str, token: str, article_url: str) -> str:
    payload = request_json(build_wechat2rss_url(base_url, "/addurl", token, url=article_url.strip()))
    feed_url = str(payload.get("data", "")).strip()
    if not feed_url:
        raise RuntimeError(f"unexpected Wechat2RSS addurl payload: {payload}")
    return feed_url


def find_registered_account(state: dict[str, Any], name: str) -> dict[str, Any] | None:
    needle = name.strip().lower()
    for item in state.get("accounts", []):
        if item.get("name", "").strip().lower() == needle or item.get("alias", "").strip().lower() == needle:
            return item
    return None


def register_account(state: dict[str, Any], base_url: str, token: str, name: str, alias: str | None = None) -> dict[str, Any]:
    candidates = wechat2rss_list(base_url, token, name=name)
    exact = [item for item in candidates if str(item.get("name", "")).strip() == name.strip()]
    if not exact:
        raise SystemExit(f"upstream Wechat2RSS subscription not found for: {name}")
    chosen = exact[0]
    existing = find_registered_account(state, name)
    if existing is None:
        existing = {"seen_ids": [], "enabled": True}
        state.setdefault("accounts", []).append(existing)
    existing["name"] = str(chosen.get("name", "")).strip() or name.strip()
    existing["alias"] = alias.strip() if alias else existing.get("alias", "")
    existing["biz_id"] = str(chosen.get("id", "")).strip()
    existing["feed_url"] = str(chosen.get("link", "")).strip()
    existing["enabled"] = True
    write_state(state)
    return {
        "name": existing["name"],
        "alias": existing.get("alias", ""),
        "biz_id": existing["biz_id"],
        "feed_url": existing["feed_url"],
        "registered": True,
    }


def register_account_direct(
    state: dict[str, Any],
    *,
    name: str,
    feed_url: str,
    biz_id: str | None = None,
    alias: str | None = None,
) -> dict[str, Any]:
    normalized_name = name.strip()
    normalized_feed_url = feed_url.strip()
    if not normalized_name:
        raise SystemExit("register name cannot be empty")
    if not normalized_feed_url:
        raise SystemExit("register feed_url cannot be empty")
    existing = find_registered_account(state, normalized_name)
    if existing is None:
        existing = {"seen_ids": [], "enabled": True}
        state.setdefault("accounts", []).append(existing)
    existing["name"] = normalized_name
    existing["alias"] = alias.strip() if alias else existing.get("alias", "")
    existing["biz_id"] = (biz_id or existing.get("biz_id", "")).strip()
    existing["feed_url"] = normalized_feed_url
    existing["enabled"] = True
    write_state(state)
    return {
        "name": existing["name"],
        "alias": existing.get("alias", ""),
        "biz_id": existing.get("biz_id", ""),
        "feed_url": existing["feed_url"],
        "registered": True,
        "mode": "direct",
    }


def add_account_from_article_url(
    state: dict[str, Any],
    base_url: str,
    token: str,
    name: str,
    article_url: str,
    alias: str | None = None,
) -> dict[str, Any]:
    feed_url = wechat2rss_addurl(base_url, token, article_url)
    matched: dict[str, Any] | None = None
    for item in wechat2rss_list(base_url, token):
        if str(item.get("link", "")).strip() == feed_url:
            matched = item
            break
    return register_account_direct(
        state,
        name=name,
        feed_url=feed_url,
        biz_id=str((matched or {}).get("id", "")).strip(),
        alias=alias,
    )


def list_accounts(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": item.get("name", ""),
            "alias": item.get("alias", ""),
            "biz_id": item.get("biz_id", ""),
            "feed_url": item.get("feed_url", ""),
            "enabled": item.get("enabled", True),
            "seen_count": len(item.get("seen_ids", [])),
        }
        for item in state.get("accounts", [])
    ]


def remove_account(state: dict[str, Any], name: str) -> dict[str, Any]:
    needle = name.strip().lower()
    before = len(state.get("accounts", []))
    state["accounts"] = [
        item for item in state.get("accounts", [])
        if item.get("name", "").strip().lower() != needle and item.get("alias", "").strip().lower() != needle
    ]
    changed = len(state["accounts"]) != before
    if changed:
        write_state(state)
    return {"removed": changed, "name": name}


def fetch_articles(account: dict[str, Any], limit: int) -> list[dict[str, str]]:
    feed_url = str(account.get("feed_url", "")).strip()
    if not feed_url:
        raise RuntimeError(f"account {account.get('name', '')} has no feed_url")
    feed_xml = request_text(feed_url)
    return parse_feed(feed_xml, limit)


def fallback_summary(article: dict[str, str]) -> str:
    body = (article.get("summary", "") or "").strip()
    if not body:
        return "新文章已发布，建议点开原文查看。"
    return body[:140].rstrip() + ("..." if len(body) > 140 else "")


def parse_model_json(raw: str) -> Any:
    candidates = []
    text = raw.strip()
    if text:
        candidates.append(text)
    if "```json" in raw:
        for chunk in raw.split("```json")[1:]:
            candidates.append(chunk.split("```", 1)[0].strip())
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue
    raise ValueError("failed to parse model JSON")


def run_lobster_json(prompt: str, timeout_seconds: int = 120) -> Any:
    proc = run_command([
        *openclaw_cli_args(),
        "--no-color",
        "agent",
        "--agent",
        SUMMARY_AGENT_ID,
        "--message",
        prompt,
        "--thinking",
        "off",
        "--timeout",
        str(timeout_seconds),
    ])
    return parse_model_json(proc.stdout)


def summarize_articles(account_name: str, articles: list[dict[str, str]], summary_mode: str) -> list[dict[str, str]]:
    if not articles:
        return []
    if summary_mode != "ai":
        return [{"title": item["title"], "summary": fallback_summary(item)} for item in articles]
    compact_articles = [
        {
            "title": item["title"],
            "published": item.get("published", ""),
            "summary": item.get("summary", "")[:1200],
            "link": item.get("link", ""),
        }
        for item in articles
    ]
    prompt = (
        "You are preparing a concise Chinese digest for one WeChat official account.\n"
        "Return strict JSON as an array. Each item must contain title and summary.\n"
        "Keep each summary to one short sentence in Chinese.\n"
        f"Account: {account_name}\n"
        f"Articles: {json.dumps(compact_articles, ensure_ascii=False)}"
    )
    try:
        payload = run_lobster_json(prompt)
        if isinstance(payload, list) and payload:
            normalized: list[dict[str, str]] = []
            for src, item in zip(articles, payload):
                normalized.append({
                    "title": str(item.get("title", src["title"])).strip() or src["title"],
                    "summary": str(item.get("summary", "")).strip() or fallback_summary(src),
                })
            return normalized
    except Exception:
        pass
    return [{"title": item["title"], "summary": fallback_summary(item)} for item in articles]


def render_digest(digests: list[dict[str, Any]]) -> str:
    entries: list[dict[str, str]] = []
    for digest in digests:
        for article in digest["articles"]:
            entries.append({
                "title": article["title"],
                "summary": article["summary"],
                "published": article.get("published", ""),
                "account": digest["account"],
            })
    entries.sort(key=lambda item: parse_datetime(item.get("published", "")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    lines = ["【阳仔二号公众号简报】"]
    for index, article in enumerate(entries, start=1):
        lines.append("")
        lines.append(f"{index}. 标题：{article['title']}")
        lines.append(f"发布时间：{iso_to_local_text(article.get('published', '')) if article.get('published') else '未知'}")
        lines.append(f"内容概述：{article['summary']}")
    return "\n".join(lines).strip()
    lines = ["【阳仔二号公众号简报】"]
    for index, article in enumerate(entries, start=1):
        lines.append("")
        lines.append(f"{index}. 标题：{article['title']}")
        lines.append(f"发布时间：{iso_to_local_text(article.get('published', '')) if article.get('published') else '未知'}")
        lines.append(f"内容概述：{article['summary']}")
    return "\n".join(lines).strip()


def append_bitable_articles(env_map: dict[str, str], digests: list[dict[str, Any]]) -> list[dict[str, str]]:
    delivery_channel = env_map.get("DELIVERY_CHANNEL", DEFAULT_ENV["DELIVERY_CHANNEL"]).strip()
    delivery_target = env_map.get("DELIVERY_TARGET", "").strip()
    client = bitable_client_from_env(
        env_map,
        delivery_channel=delivery_channel,
        delivery_target=delivery_target,
        default_table_name=BITABLE_DEFAULT_TABLE_NAME,
    )
    if client is None:
        return []
    errors: list[dict[str, str]] = []
    summary_model = "kimi-coding" if env_map.get("SUMMARY_MODE", DEFAULT_ENV["SUMMARY_MODE"]).strip().lower() == "ai" else "brief"
    for digest in digests:
        for article in digest["articles"]:
            try:
                client.append_record(
                    {
                        "Source Type": "wechat_official_account",
                        "Source Name": digest["account"],
                        "Title": article["title"],
                        "Published At": iso_to_local_text(article.get("published", "")) if article.get("published") else "",
                        "Summary": article["summary"],
                        "Source URL": article.get("link", ""),
                        "Archived At": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
                        "Summary Model": summary_model,
                        "Data Source": "Wechat2RSS",
                    },
                    BITABLE_ARTICLE_FIELDS,
                )
            except Exception as exc:
                errors.append({
                    "account": digest["account"],
                    "title": article["title"],
                    "error": str(exc),
                })
    return errors


def push_text(text: str, env_map: dict[str, str]) -> None:
    channel = env_map.get("DELIVERY_CHANNEL", DEFAULT_ENV["DELIVERY_CHANNEL"]).strip()
    target = env_map.get("DELIVERY_TARGET", "").strip()
    if not target:
        raise SystemExit("DELIVERY_TARGET not configured")
    run_command([
        *openclaw_cli_args(),
        "message",
        "send",
        "--channel",
        channel,
        "--target",
        target,
        "--message",
        text,
    ])


def check_and_push(state: dict[str, Any], env_map: dict[str, str]) -> dict[str, Any]:
    fetch_limit = parse_int_env(env_map, "FETCH_LIMIT_PER_ACCOUNT", int(DEFAULT_ENV["FETCH_LIMIT_PER_ACCOUNT"]), minimum=1, maximum=20)
    summary_max_articles = parse_int_env(env_map, "SUMMARY_MAX_ARTICLES", int(DEFAULT_ENV["SUMMARY_MAX_ARTICLES"]), minimum=1, maximum=20)
    summary_mode = env_map.get("SUMMARY_MODE", DEFAULT_ENV["SUMMARY_MODE"]).strip().lower()
    digests: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    window_hours = parse_int_env(env_map, "PUSH_WINDOW_HOURS", 24, minimum=1, maximum=168)
    for account in state.get("accounts", []):
        if not account.get("enabled", True):
            continue
        articles = fetch_articles(account, fetch_limit)
        seen_ids = list(account.get("seen_ids", []))
        new_articles = []
        for item in articles:
            if item["id"] in seen_ids:
                continue
            published_at = parse_datetime(item.get("published"))
            if published_at is None:
                continue
            age_seconds = (now - published_at.astimezone(timezone.utc)).total_seconds()
            if age_seconds < 0 or age_seconds > window_hours * 3600:
                continue
            new_articles.append(item)
        if not new_articles:
            account["seen_ids"] = [item["id"] for item in articles[:50]]
            continue
        trimmed = list(reversed(new_articles[:summary_max_articles]))
        summaries = summarize_articles(account.get("name", ""), trimmed, summary_mode)
        rendered_articles = []
        for raw_item, summary_item in zip(trimmed, summaries):
            rendered_articles.append({
                "title": summary_item["title"],
                "summary": summary_item["summary"],
                "link": raw_item.get("link", ""),
                "published": raw_item.get("published", ""),
            })
        digests.append({"account": account.get("name", ""), "articles": rendered_articles})
        account["seen_ids"] = [item["id"] for item in articles[:50]]
        account["last_pushed_at"] = datetime.now().isoformat()
    if not digests:
        write_state(state)
        return {"delivered_count": 0, "accounts_checked": len(state.get("accounts", []))}
    bitable_errors = append_bitable_articles(env_map, digests)
    push_text(render_digest(digests), env_map)
    write_state(state)
    return {
        "delivered_count": sum(len(item["articles"]) for item in digests),
        "accounts_with_updates": len(digests),
        "accounts_checked": len(state.get("accounts", [])),
        "bitable_errors": bitable_errors,
    }


def preview_account(state: dict[str, Any], name: str, limit: int) -> str:
    account = find_registered_account(state, name)
    if account is None:
        raise SystemExit(f"account not registered: {name}")
    articles = fetch_articles(account, limit)
    if not articles:
        return "No recent articles found."
    lines = [f"【预览】{account.get('name', '')}"]
    for article in articles[:limit]:
        lines.append("")
        lines.append(article["title"])
        if article.get("published"):
            lines.append(iso_to_local_text(article["published"]))
        if article.get("summary"):
            lines.append(article["summary"])
    return "\n".join(lines).strip()
    lines = [f"【预览】{account.get('name', '')}"]
    for article in articles[:limit]:
        lines.append("")
        lines.append(article["title"])
        if article.get("published"):
            lines.append(iso_to_local_text(article["published"]))
        if article.get("summary"):
            lines.append(article["summary"][:200])
        if article.get("link"):
            lines.append(article["link"])
    return "\n".join(lines).strip()


def render_digest(digests: list[dict[str, Any]]) -> str:
    entries: list[dict[str, str]] = []
    for digest in digests:
        for article in digest["articles"]:
            entries.append({
                "title": article["title"],
                "summary": article["summary"],
                "published": article.get("published", ""),
                "account": digest["account"],
            })
    entries.sort(
        key=lambda item: parse_datetime(item.get("published", "")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    lines = ["【阳仔二号公众号简报】"]
    for index, article in enumerate(entries, start=1):
        lines.append("")
        lines.append(f"{index}. 标题：{article['title']}")
        lines.append(
            f"发布时间：{iso_to_local_text(article.get('published', '')) if article.get('published') else '未知'}"
        )
        lines.append(f"内容概述：{article['summary']}")
    return "\n".join(lines).strip()


def preview_account(state: dict[str, Any], name: str, limit: int) -> str:
    account = find_registered_account(state, name)
    if account is None:
        raise SystemExit(f"account not registered: {name}")
    articles = fetch_articles(account, limit)
    if not articles:
        return "No recent articles found."
    lines = [f"【预览】{account.get('name', '')}"]
    for article in articles[:limit]:
        lines.append("")
        lines.append(article["title"])
        if article.get("published"):
            lines.append(iso_to_local_text(article["published"]))
        if article.get("summary"):
            lines.append(article["summary"])
    return "\n".join(lines).strip()


def public_config(env_map: dict[str, str]) -> dict[str, Any]:
    return {
        "delivery_channel": env_map.get("DELIVERY_CHANNEL", DEFAULT_ENV["DELIVERY_CHANNEL"]),
        "delivery_target": env_map.get("DELIVERY_TARGET", ""),
        "summary_mode": env_map.get("SUMMARY_MODE", DEFAULT_ENV["SUMMARY_MODE"]),
        "summary_max_articles": env_map.get("SUMMARY_MAX_ARTICLES", DEFAULT_ENV["SUMMARY_MAX_ARTICLES"]),
        "fetch_limit_per_account": env_map.get("FETCH_LIMIT_PER_ACCOUNT", DEFAULT_ENV["FETCH_LIMIT_PER_ACCOUNT"]),
        "push_window_hours": env_map.get("PUSH_WINDOW_HOURS", "24"),
        "wechat2rss_base_url": env_map.get("WECHAT2RSS_BASE_URL", ""),
        "wechat2rss_token_configured": bool(env_map.get("WECHAT2RSS_TOKEN", "").strip()),
        "bitable_enabled": bool(env_map.get("FEISHU_BITABLE_APP_TOKEN", "").strip()),
        "bitable_table_id_configured": bool(env_map.get("FEISHU_BITABLE_TABLE_ID", "").strip()),
        "bitable_table_name": env_map.get("FEISHU_BITABLE_TABLE_NAME", BITABLE_DEFAULT_TABLE_NAME),
        "openclaw_profile": current_openclaw_profile() or "default",
        "openclaw_config_path": str(current_openclaw_config_path()),
    }


def show_status(state: dict[str, Any], env_map: dict[str, str]) -> dict[str, Any]:
    payload = public_config(env_map)
    payload["watch_timer"] = timer_state(current_watch_timer())
    payload["accounts"] = list_accounts(state)
    payload["account_count"] = len(payload["accounts"])
    return payload


def set_config(env_map: dict[str, str], *, delivery_channel: str | None, delivery_target: str | None, summary_mode: str | None) -> dict[str, Any]:
    changed = False
    if delivery_channel is not None:
        env_map["DELIVERY_CHANNEL"] = delivery_channel.strip()
        changed = True
    if delivery_target is not None:
        env_map["DELIVERY_TARGET"] = delivery_target.strip()
        changed = True
    if summary_mode is not None:
        normalized = summary_mode.strip().lower()
        if normalized not in {"ai", "brief"}:
            raise SystemExit("SUMMARY_MODE must be ai or brief")
        env_map["SUMMARY_MODE"] = normalized
        changed = True
    if not changed:
        raise SystemExit("no config changes requested")
    write_env_map(current_env_path(), env_map)
    return public_config(env_map)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor WeChat official accounts via Wechat2RSS")
    parser.add_argument("--env-path", help="Use an explicit env file instead of WECHAT_MONITOR_ENV_PATH")
    parser.add_argument("--show-config", action="store_true")
    parser.add_argument("--show-status", action="store_true")
    parser.add_argument("--list-accounts", action="store_true")
    parser.add_argument("--add-account", help="Add one monitored account")
    parser.add_argument("--article-url", help="Use a public WeChat article URL to create upstream subscription for --add-account")
    parser.add_argument("--register-account", help="Register one monitored account by exact upstream subscription name")
    parser.add_argument("--register-feed-url", help="Register one monitored account directly by feed URL")
    parser.add_argument("--register-biz-id", help="Optional biz_id when using --register-feed-url")
    parser.add_argument("--alias", help="Optional local alias for --register-account")
    parser.add_argument("--remove-account", help="Remove a monitored account by name or alias")
    parser.add_argument("--preview-account", help="Preview recent articles for one monitored account")
    parser.add_argument("--limit", type=int, default=3, help="Preview limit")
    parser.add_argument("--check-and-push", action="store_true")
    parser.add_argument("--pause-watch", action="store_true")
    parser.add_argument("--resume-watch", action="store_true")
    parser.add_argument("--set-delivery-channel", help="Set DELIVERY_CHANNEL")
    parser.add_argument("--set-delivery-target", help="Set DELIVERY_TARGET")
    parser.add_argument("--set-summary-mode", help="Set SUMMARY_MODE to ai or brief")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.env_path:
        os.environ["WECHAT_MONITOR_ENV_PATH"] = args.env_path
    load_env_file(current_env_path())
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
    if any(v is not None for v in [args.set_delivery_channel, args.set_delivery_target, args.set_summary_mode]):
        print(json.dumps(set_config(
            env_map,
            delivery_channel=args.set_delivery_channel,
            delivery_target=args.set_delivery_target,
            summary_mode=args.set_summary_mode,
        ), ensure_ascii=False, indent=2))
        return 0

    base_url = env_map.get("WECHAT2RSS_BASE_URL", "").strip()
    token = env_map.get("WECHAT2RSS_TOKEN", "").strip()
    if not base_url or not token:
        raise SystemExit("WECHAT2RSS_BASE_URL and WECHAT2RSS_TOKEN must be configured")

    if args.register_account:
        if args.register_feed_url:
            print(json.dumps(register_account_direct(
                state,
                name=args.register_account,
                feed_url=args.register_feed_url,
                biz_id=args.register_biz_id,
                alias=args.alias,
            ), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(register_account(state, base_url, token, args.register_account, args.alias), ensure_ascii=False, indent=2))
        return 0
    if args.add_account:
        if args.article_url:
            print(json.dumps(add_account_from_article_url(state, base_url, token, args.add_account, args.article_url, args.alias), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(register_account(state, base_url, token, args.add_account, args.alias), ensure_ascii=False, indent=2))
        return 0
    if args.remove_account:
        print(json.dumps(remove_account(state, args.remove_account), ensure_ascii=False, indent=2))
        return 0
    if args.preview_account:
        print(preview_account(state, args.preview_account, args.limit))
        return 0
    if args.check_and_push:
        print(json.dumps(check_and_push(state, env_map), ensure_ascii=False, indent=2))
        return 0

    raise SystemExit("no action specified")


if __name__ == "__main__":
    raise SystemExit(main())
