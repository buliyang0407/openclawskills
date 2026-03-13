#!/usr/bin/env python3
import argparse
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


DEFAULT_ENV_PATH = Path("/etc/openclaw/wechat-article-capture.env")
DEFAULT_OPENCLAW_CONFIG_PATH = Path("/root/.openclaw/openclaw.json")
COMMON_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "common" / "scripts"
ARTICLE_MANAGER_PATH = Path(__file__).resolve().parents[2] / "article-knowledge-manager" / "scripts" / "article_knowledge_manager.py"
DEFAULT_ENV = {
    "OPENCLAW_PROFILE": "",
    "ARTICLE_ENV_PATH": "/etc/openclaw/article-knowledge-manager-yangzai3.env",
    "CAPTURE_ENGINE": "camoufox",
    "CAPTURE_TIMEOUT_MS": "45000",
    "CAPTURE_HEADED": "false",
    "CAPTURE_BROWSER_CHANNEL": "",
    "SUMMARY_ENGINE": "openclaw-agent",
    "SUMMARY_OPENCLAW_PROFILE": "",
    "SUMMARY_AGENT_ID": "main",
    "OPENAI_COMPAT_BASE_URL": "",
    "OPENAI_COMPAT_API_KEY": "",
    "OPENAI_COMPAT_MODEL": "qwen3.5-plus",
    "PENDING_TAG": "待补全",
    "PENDING_TITLE_PREFIX": "待补标题",
    "SOURCE_CHANNEL": "微信公众号",
}

if str(COMMON_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS_DIR))

from feishu_bitable_plugin import bitable_client_from_env  # noqa: E402


def load_article_module():
    spec = importlib.util.spec_from_file_location("article_knowledge_manager_runtime", ARTICLE_MANAGER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load article manager module from {ARTICLE_MANAGER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


article_module = load_article_module()

EXTRACT_EVAL_JS = r"""
() => {
  const html = document.documentElement.outerHTML;
  const bodyText = document.body ? document.body.innerText || "" : "";
  const riskMarkers = [
    "环境异常",
    "访问过于频繁",
    "请在微信客户端打开链接",
    "去验证",
    "链接已过期",
    "内容已被发布者删除",
    "此内容因违规无法查看",
  ];
  const riskMarker = riskMarkers.find((marker) => bodyText.includes(marker)) || "";
  const hasContent = Boolean(document.querySelector("#js_content"));
  const titleNode =
    document.querySelector("#activity-name") ||
    document.querySelector(".rich_media_title") ||
    document.querySelector("meta[property='og:title']");
  const accountNode =
    document.querySelector("#js_name") ||
    document.querySelector(".profile_nickname") ||
    document.querySelector(".wx_follow_nickname");
  const aliasNode = document.querySelector("#js_profile_qrcode > strong");
  const authorNode =
    document.querySelector("#js_author_name") ||
    document.querySelector("meta[name='author']");
  const publishNode =
    document.querySelector("#publish_time") ||
    document.querySelector("#post-date");
  const contentNode = document.querySelector("#js_content");
  const coverNode =
    document.querySelector("meta[property='og:image']") ||
    document.querySelector("meta[name='twitter:image']");
  const descNode =
    document.querySelector("meta[property='og:description']") ||
    document.querySelector("meta[name='description']");

  const matchPublishTime = (sourceHtml) => {
    const patterns = [
      /create_time\s*:\s*JsDecode\('([^']+)'\)/,
      /create_time\s*[:=]\s*["']?(\d{10})["']?/,
      /d\.ct\s*=\s*["']?(\d{10})["']?/,
    ];
    for (const pattern of patterns) {
      const matched = sourceHtml.match(pattern);
      if (matched && matched[1]) {
        const raw = matched[1];
        const seconds = Number(raw);
        if (Number.isFinite(seconds) && seconds > 0) {
          const date = new Date(seconds * 1000);
          const pad = (num) => String(num).padStart(2, "0");
          return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
            `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
        }
        return raw;
      }
    }
    return "";
  };

  const clean = (value) => String(value || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
  const title =
    titleNode?.getAttribute?.("content") ||
    titleNode?.textContent ||
    document.title ||
    "";
  const accountName = accountNode?.textContent || "";
  const accountAlias = aliasNode?.textContent || "";
  const author =
    authorNode?.getAttribute?.("content") ||
    authorNode?.textContent ||
    "";
  const publishedAt = clean(publishNode?.textContent || "") || matchPublishTime(html);
  const bodyHtml = contentNode ? contentNode.innerHTML : "";
  const contentText = clean(contentNode?.innerText || "");
  const description =
    descNode?.getAttribute?.("content") ||
    clean(contentText).slice(0, 220);
  const coverImage = coverNode?.getAttribute?.("content") || "";
  const excerpt = clean(contentText).slice(0, 1200);
  return {
    ok: hasContent && !riskMarker && Boolean(clean(title)) && Boolean(clean(contentText)),
    url: location.href,
    title: clean(title),
    accountName: clean(accountName),
    accountAlias: clean(accountAlias),
    author: clean(author),
    publishedAt: clean(publishedAt),
    description: clean(description),
    coverImage: clean(coverImage),
    excerpt,
    contentText,
    bodyHtml,
    pageTitle: clean(document.title || ""),
    riskMarker,
    hasContent,
    wordCount: clean(contentText).length,
  };
}
"""


def current_env_path() -> Path:
    return Path(os.environ.get("WECHAT_CAPTURE_ENV_PATH", str(DEFAULT_ENV_PATH)))


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


def read_env_map(path: Path) -> dict[str, str]:
    env_map = dict(DEFAULT_ENV)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env_map[key.strip()] = normalize_env_value(value)
    return env_map


def write_env_map(path: Path, env_map: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={format_env_value(value)}" for key, value in env_map.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), normalize_env_value(value))


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


def summary_openclaw_cli_args(env_map: dict[str, str]) -> list[str]:
    args = ["openclaw"]
    summary_profile = env_map.get("SUMMARY_OPENCLAW_PROFILE", "").strip()
    if not summary_profile:
        summary_profile = current_openclaw_profile()
    if summary_profile:
        args.extend(["--profile", summary_profile])
    return args


def capture_script_path() -> Path:
    return Path(__file__).with_suffix(".mjs")


def node_bin() -> str:
    explicit = os.environ.get("NODE_BIN", "").strip()
    if explicit:
        return explicit
    return "node"


def npm_bin() -> str:
    explicit = os.environ.get("NPM_BIN", "").strip()
    if explicit:
        return explicit
    return "npm"


def npx_bin() -> str:
    explicit = os.environ.get("NPX_BIN", "").strip()
    if explicit:
        return explicit
    return "npx"


def run_command(args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    linux_node_path = "/root/.nvm/versions/node/v22.22.0/bin:/usr/local/bin:"
    merged_env["PATH"] = linux_node_path + merged_env.get("PATH", "")
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=merged_env,
    )
    return proc


def command_is_ready(args: list[str], *, cwd: Path | None = None, success_stdout: str | None = None) -> bool:
    try:
        proc = run_command(args, cwd=cwd)
    except Exception:
        return False
    if proc.returncode != 0:
        return False
    if success_stdout is None:
        return True
    return proc.stdout.strip() == success_stdout


def parse_model_json(raw: str) -> Any:
    candidates: list[str] = []
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


def run_lobster_json(prompt: str, env_map: dict[str, str], timeout_seconds: int = 120) -> Any:
    agent_id = env_map.get("SUMMARY_AGENT_ID", DEFAULT_ENV["SUMMARY_AGENT_ID"]).strip() or DEFAULT_ENV["SUMMARY_AGENT_ID"]
    proc = run_command(
        [
            *summary_openclaw_cli_args(env_map),
            "--no-color",
            "agent",
            "--agent",
            agent_id,
            "--message",
            prompt,
            "--thinking",
            "off",
            "--timeout",
            str(timeout_seconds),
        ]
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(detail or "openclaw agent failed")
    return parse_model_json(proc.stdout)


def run_openai_compatible_json(prompt: str, env_map: dict[str, str], timeout_seconds: int = 120) -> Any:
    base_url = env_map.get("OPENAI_COMPAT_BASE_URL", "").strip().rstrip("/")
    api_key = env_map.get("OPENAI_COMPAT_API_KEY", "").strip()
    model = env_map.get("OPENAI_COMPAT_MODEL", "").strip()
    if not base_url or not api_key or not model:
        raise RuntimeError("missing OPENAI_COMPAT_BASE_URL, OPENAI_COMPAT_API_KEY, or OPENAI_COMPAT_MODEL")
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "Return strict JSON only."},
            {"role": "user", "content": prompt},
        ],
    }
    req = urlrequest.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"openai_compatible_http_error:{exc.code}:{detail}")
    except urlerror.URLError as exc:
        raise RuntimeError(f"openai_compatible_request_failed:{exc}") from exc
    raw = str((((data.get("choices") or [{}])[0]).get("message") or {}).get("content", "")).strip()
    if not raw:
        raise RuntimeError(f"openai_compatible_missing_content:{json.dumps(data, ensure_ascii=False)}")
    return parse_model_json(raw)


def capture_with_camoufox(url: str, env_map: dict[str, str]) -> dict[str, Any]:
    import asyncio
    from camoufox.async_api import AsyncCamoufox

    timeout_ms = max(int(env_map.get("CAPTURE_TIMEOUT_MS", DEFAULT_ENV["CAPTURE_TIMEOUT_MS"]) or "45000"), 5000)
    headed = env_map.get("CAPTURE_HEADED", DEFAULT_ENV["CAPTURE_HEADED"]).strip().lower() in {"1", "true", "yes", "on"}

    async def _run() -> dict[str, Any]:
        async with AsyncCamoufox(headless=not headed) as browser:
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                await page.wait_for_selector("#js_content", timeout=min(timeout_ms, 15000))
            except Exception:
                pass
            await page.wait_for_timeout(2500)
            return await page.evaluate(EXTRACT_EVAL_JS)

    return asyncio.run(_run())


def normalize_list(value: Any, minimum: int = 0, fallback: list[str] | None = None) -> list[str]:
    result: list[str] = []
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = value.replace("，", ",").split(",")
    else:
        items = []
    for item in items:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    if len(result) < minimum and fallback:
        for item in fallback:
            if item and item not in result:
                result.append(item)
    return result


def compact_text(value: str, limit: int) -> str:
    value = " ".join(str(value or "").split())
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def fallback_analysis(capture: dict[str, Any]) -> dict[str, Any]:
    title = str(capture.get("title", "")).strip()
    account_name = str(capture.get("accountName", "")).strip()
    excerpt = str(capture.get("excerpt", "")).strip() or compact_text(str(capture.get("contentText", "")).strip(), 180)
    keywords = [item for item in [account_name, "微信文章"] if item]
    return {
        "summary": compact_text(excerpt or f"{title}，建议查看原文。", 180),
        "corePoints": compact_text(excerpt, 280),
        "keywords": keywords,
        "tags": keywords,
        "category": "公众号文章",
        "useCases": ["找灵感", "写文章参考"],
        "referenceValue": "中",
    }


def summarize_capture(capture: dict[str, Any], env_map: dict[str, str]) -> dict[str, Any]:
    body = compact_text(str(capture.get("contentText", "")).strip(), 10000)
    if not body:
        return fallback_analysis(capture)
    prompt = (
        "你是知识库管理员，请为一篇微信公众号文章生成结构化知识卡片。\n"
        "只返回严格 JSON 对象，不要解释。\n"
        "字段必须包含：summary, corePoints, keywords, tags, category, useCases, referenceValue。\n"
        "要求：\n"
        "1. summary: 80-180 字中文概要。\n"
        "2. corePoints: 1-3 句中文核心观点，字符串形式。\n"
        "3. keywords: 3-8 个关键词数组。\n"
        "4. tags: 3-6 个标签数组。\n"
        "5. category: 简短类别，例如 公众号文章 / AI工具 / NAS / 提示词 / 资产观察。\n"
        "6. useCases: 2-4 个适用场景数组，例如 写文章参考、做PPT、找选题、产品灵感。\n"
        "7. referenceValue: 只能是 高、中、低。\n"
        f"标题: {capture.get('title', '')}\n"
        f"公众号: {capture.get('accountName', '')}\n"
        f"作者: {capture.get('author', '')}\n"
        f"发布时间: {capture.get('publishedAt', '')}\n"
        f"正文: {body}"
    )
    engine = env_map.get("SUMMARY_ENGINE", DEFAULT_ENV["SUMMARY_ENGINE"]).strip().lower()
    payload: Any
    try:
        if engine == "openai-compatible":
            payload = run_openai_compatible_json(prompt, env_map)
        else:
            payload = run_lobster_json(prompt, env_map)
        if not isinstance(payload, dict):
            raise RuntimeError("summary payload is not an object")
        fallback = fallback_analysis(capture)
        return {
            "summary": str(payload.get("summary", "")).strip() or fallback["summary"],
            "corePoints": compact_text(str(payload.get("corePoints", "")).strip() or fallback["corePoints"], 400),
            "keywords": normalize_list(payload.get("keywords"), minimum=2, fallback=fallback["keywords"]),
            "tags": normalize_list(payload.get("tags"), minimum=2, fallback=fallback["tags"]),
            "category": str(payload.get("category", "")).strip() or fallback["category"],
            "useCases": normalize_list(payload.get("useCases"), minimum=1, fallback=fallback["useCases"]),
            "referenceValue": str(payload.get("referenceValue", "")).strip() or fallback["referenceValue"],
        }
    except Exception:
        return fallback_analysis(capture)


def build_pending_payload(url: str, env_map: dict[str, str], existing_fields: dict[str, Any] | None = None) -> dict[str, Any]:
    slug = url.rstrip("/").rsplit("/", 1)[-1][:8] or "wechat"
    source_name = str((existing_fields or {}).get("作者/来源", "")).strip()
    prefix = env_map.get("PENDING_TITLE_PREFIX", DEFAULT_ENV["PENDING_TITLE_PREFIX"]).strip() or DEFAULT_ENV["PENDING_TITLE_PREFIX"]
    title = str((existing_fields or {}).get("标题", "")).strip()
    if not title or not title.startswith(prefix):
        title = f"{prefix}｜{source_name or '公众号文章'}｜{slug}"
    return {
        "title": title,
        "summary": "微信页面当前无法稳定抓取，已先保存链接，等待后续补全。",
        "corePoints": "待补全",
        "keywords": ["微信文章", env_map.get("PENDING_TAG", DEFAULT_ENV["PENDING_TAG"]).strip()],
        "tags": ["微信文章", env_map.get("PENDING_TAG", DEFAULT_ENV["PENDING_TAG"]).strip()],
        "category": "公众号文章",
        "useCases": ["待补全"],
        "referenceValue": "中",
        "author": source_name,
    }


def article_env_path(env_map: dict[str, str]) -> Path:
    return Path(env_map.get("ARTICLE_ENV_PATH", DEFAULT_ENV["ARTICLE_ENV_PATH"]).strip() or DEFAULT_ENV["ARTICLE_ENV_PATH"])


def load_article_env_map(env_map: dict[str, str]) -> tuple[Path, dict[str, str]]:
    path = article_env_path(env_map)
    article_env_map = article_module.read_env_map(path)
    article_module.load_env_file(path)
    return path, article_env_map


def list_records_for_client(client: Any, table_name: str, limit: int = 200) -> list[dict[str, Any]]:
    creds = article_module.load_openclaw_feishu_account()
    data = article_module.run_helper(
        {
            "action": "list_records",
            "appId": client.app_id,
            "appSecret": client.app_secret,
            "domain": creds.get("domain", "feishu"),
            "userOpenId": client.user_open_id,
            "appToken": client.app_token,
            "tableId": client.table_id,
            "tableName": table_name,
            "pageSize": min(max(limit, 1), 500),
        }
    )
    return list(data.get("items", []))


def is_pending_record(fields: dict[str, Any], env_map: dict[str, str]) -> bool:
    title = str(fields.get("标题", "")).strip()
    summary = str(fields.get("文章摘要", "")).strip()
    tags = str(fields.get("标签", "")).strip()
    pending_tag = env_map.get("PENDING_TAG", DEFAULT_ENV["PENDING_TAG"]).strip()
    prefix = env_map.get("PENDING_TITLE_PREFIX", DEFAULT_ENV["PENDING_TITLE_PREFIX"]).strip()
    return (
        title.startswith(prefix)
        or pending_tag in tags
        or "待补全" in summary
        or "无法稳定抓取" in summary
    )


def find_article_records_by_url(article_env_map: dict[str, str], env_map: dict[str, str], url: str) -> list[dict[str, Any]]:
    items = article_module.list_records(article_env_map, 300)
    matches = []
    for item in items:
        fields = item.get("fields", {})
        if str(fields.get("链接", "")).strip() == url.strip():
            matches.append(item)
    return matches


def build_article_fields(
    url: str,
    capture: dict[str, Any],
    analysis: dict[str, Any],
    *,
    pending: bool,
) -> dict[str, str]:
    title = str(analysis.get("title") or capture.get("title") or "").strip()
    author = str(analysis.get("author") or capture.get("accountName") or capture.get("author") or "").strip()
    summary = str(analysis.get("summary", "")).strip()
    fields = {
        "标题": title,
        "链接": url.strip(),
        "作者/来源": author,
        "发布时间": str(capture.get("publishedAt", "")).strip(),
        "文章摘要": summary,
        "核心观点": str(analysis.get("corePoints", "")).strip(),
        "关键词": article_module.join_csv_like(",".join(analysis.get("keywords", []))),
        "类别": str(analysis.get("category", "")).strip(),
        "标签": article_module.join_csv_like(",".join(analysis.get("tags", []))),
        "我的备注": "自动抓取补全" if not pending else "自动保存待补全条目",
        "阅读状态": "未读",
        "收藏等级": "普通",
        "关联项目": "",
        "是否已入总表": "是",
        "去重指纹": article_module.dedupe_fingerprint(url, title),
        "录入时间": article_module.now_str(),
        "适用场景": article_module.join_csv_like(",".join(analysis.get("useCases", []))),
        "引用价值": str(analysis.get("referenceValue", "")).strip() or "中",
    }
    return fields


def build_total_index_fields(article_env_map: dict[str, str], article_record_id: str, article_fields: dict[str, str]) -> dict[str, str]:
    recorded_at = article_module.now_str()
    read_status = article_fields.get("阅读状态", "未读")
    return {
        "标题": article_fields.get("标题", ""),
        "摘要": article_fields.get("文章摘要", ""),
        "内容类型": "文章",
        "来源渠道": article_env_map.get("SOURCE_CHANNEL", DEFAULT_ENV["SOURCE_CHANNEL"]).strip() or DEFAULT_ENV["SOURCE_CHANNEL"],
        "来源账号": article_fields.get("作者/来源", ""),
        "时间": article_fields.get("发布时间", "") or recorded_at,
        "标签": article_fields.get("标签", "") or article_fields.get("关键词", ""),
        "重要度": article_fields.get("引用价值", "中"),
        "是否收藏": "是",
        "是否已读": "否" if read_status == "未读" else "是",
        "原链接": article_fields.get("链接", ""),
        "来源表": article_env_map.get("FEISHU_BITABLE_TABLE_NAME", article_module.DEFAULT_TABLE_NAME),
        "来源记录ID": article_record_id,
        "去重指纹": article_fields.get("去重指纹", ""),
        "归档时间": recorded_at,
        "状态": "待补全" if "待补全" in article_fields.get("标签", "") else "有效",
    }


def sync_total_index(article_env_map: dict[str, str], article_record_id: str, article_fields: dict[str, str]) -> dict[str, str]:
    client = article_module.total_index_client(article_env_map)
    if client is None:
        raise RuntimeError("missing total index client")
    items = list_records_for_client(client, article_env_map.get("TOTAL_INDEX_TABLE_NAME", article_module.DEFAULT_TOTAL_INDEX_TABLE_NAME), 300)
    matched = None
    for item in items:
        fields = item.get("fields", {})
        if str(fields.get("来源记录ID", "")).strip() == article_record_id:
            matched = item
            break
    index_fields = build_total_index_fields(article_env_map, article_record_id, article_fields)
    if matched:
        record_id = str(matched.get("recordId", "")).strip()
        client.update_record(record_id, index_fields, article_module.TOTAL_INDEX_FIELDS)
        return {"action": "updated", "recordId": record_id}
    record_id = client.append_record(index_fields, article_module.TOTAL_INDEX_FIELDS)
    return {"action": "created", "recordId": record_id}


def upsert_article_record(
    article_env_map: dict[str, str],
    env_map: dict[str, str],
    url: str,
    capture: dict[str, Any],
    analysis: dict[str, Any],
    existing_item: dict[str, Any] | None,
) -> dict[str, Any]:
    client = article_module.ensure_client(article_env_map)
    pending = "待补全" in ",".join(analysis.get("tags", []))
    article_fields = build_article_fields(url, capture, analysis, pending=pending)
    if existing_item:
        record_id = str(existing_item.get("recordId", "")).strip()
        current_fields = existing_item.get("fields", {})
        if current_fields:
            article_fields["录入时间"] = str(current_fields.get("录入时间", "")).strip() or article_fields["录入时间"]
            if str(current_fields.get("关联项目", "")).strip():
                article_fields["关联项目"] = str(current_fields.get("关联项目", "")).strip()
        client.update_record(record_id, article_fields, article_module.ARTICLE_FIELDS)
        sync_info = sync_total_index(article_env_map, record_id, article_fields)
        return {"action": "updated", "recordId": record_id, "fields": article_fields, "indexSync": sync_info}
    record_id = client.append_record(article_fields, article_module.ARTICLE_FIELDS)
    sync_info = sync_total_index(article_env_map, record_id, article_fields)
    return {"action": "created", "recordId": record_id, "fields": article_fields, "indexSync": sync_info}


def run_capture(url: str, env_map: dict[str, str]) -> dict[str, Any]:
    engine = env_map.get("CAPTURE_ENGINE", DEFAULT_ENV["CAPTURE_ENGINE"]).strip().lower()
    if engine == "camoufox":
        payload = capture_with_camoufox(url, env_map)
        if not payload.get("ok", False):
            detail = str(payload.get("riskMarker", "") or payload.get("error", "")).strip()
            raise RuntimeError(detail or "wechat capture failed")
        return payload
    if engine != "playwright":
        raise RuntimeError(f"unsupported CAPTURE_ENGINE: {engine}")
    args = [
        node_bin(),
        str(capture_script_path()),
        "--url",
        url,
        "--timeout-ms",
        env_map.get("CAPTURE_TIMEOUT_MS", DEFAULT_ENV["CAPTURE_TIMEOUT_MS"]),
        "--json",
    ]
    channel = env_map.get("CAPTURE_BROWSER_CHANNEL", DEFAULT_ENV["CAPTURE_BROWSER_CHANNEL"]).strip()
    if channel:
        args.extend(["--channel", channel])
    if env_map.get("CAPTURE_HEADED", DEFAULT_ENV["CAPTURE_HEADED"]).strip().lower() in {"1", "true", "yes", "on"}:
        args.append("--headed")
    proc = run_command(
        args,
        cwd=capture_script_path().parent.parent,
    )
    if not proc.stdout.strip():
        raise RuntimeError((proc.stderr or "").strip() or "capture returned empty output")
    payload = json.loads(proc.stdout)
    if proc.returncode != 0 or not payload.get("ok", False):
        detail = str(payload.get("riskMarker", "") or payload.get("error", "") or proc.stderr).strip()
        raise RuntimeError(detail or "wechat capture failed")
    return payload


def save_pending(article_env_map: dict[str, str], env_map: dict[str, str], url: str, existing_item: dict[str, Any] | None, reason: str) -> dict[str, Any]:
    existing_fields = (existing_item or {}).get("fields", {})
    analysis = build_pending_payload(url, env_map, existing_fields)
    capture = {
        "title": analysis["title"],
        "accountName": analysis.get("author", ""),
        "author": analysis.get("author", ""),
        "publishedAt": "",
    }
    result = upsert_article_record(article_env_map, env_map, url, capture, analysis, existing_item)
    result["pending"] = True
    result["reason"] = reason
    return result


def ingest_url(env_map: dict[str, str], url: str) -> dict[str, Any]:
    article_env_path_value, article_env_map = load_article_env_map(env_map)
    existing = find_article_records_by_url(article_env_map, env_map, url)
    existing_item = existing[0] if existing else None
    try:
        capture = run_capture(url, env_map)
        analysis = summarize_capture(capture, env_map)
        analysis["title"] = str(capture.get("title", "")).strip()
        analysis["author"] = str(capture.get("accountName", "") or capture.get("author", "")).strip()
        result = upsert_article_record(article_env_map, env_map, url, capture, analysis, existing_item)
        return {
            "ok": True,
            "pending": False,
            "articleEnvPath": str(article_env_path_value),
            "capture": {
                "title": capture.get("title", ""),
                "accountName": capture.get("accountName", ""),
                "publishedAt": capture.get("publishedAt", ""),
                "wordCount": capture.get("wordCount", 0),
            },
            "analysis": analysis,
            **result,
        }
    except Exception as exc:
        if existing_item and not is_pending_record(existing_item.get("fields", {}), env_map):
            return {
                "ok": False,
                "pending": False,
                "articleEnvPath": str(article_env_path_value),
                "captureError": str(exc),
                "skipped": True,
                "reason": "existing_record_already_complete",
                "recordId": str(existing_item.get("recordId", "")).strip(),
            }
        result = save_pending(article_env_map, env_map, url, existing_item, str(exc))
        return {
            "ok": True,
            "pending": True,
            "articleEnvPath": str(article_env_path_value),
            "captureError": str(exc),
            **result,
        }


def enrich_pending(env_map: dict[str, str], limit: int) -> dict[str, Any]:
    _, article_env_map = load_article_env_map(env_map)
    items = article_module.list_records(article_env_map, 400)
    pending_items = []
    for item in items:
        fields = item.get("fields", {})
        url = str(fields.get("链接", "")).strip()
        if "mp.weixin.qq.com" not in url:
            continue
        if is_pending_record(fields, env_map):
            pending_items.append(item)
        if len(pending_items) >= limit:
            break
    results = []
    for item in pending_items:
        fields = item.get("fields", {})
        url = str(fields.get("链接", "")).strip()
        try:
            capture = run_capture(url, env_map)
            analysis = summarize_capture(capture, env_map)
            analysis["title"] = str(capture.get("title", "")).strip()
            analysis["author"] = str(capture.get("accountName", "") or capture.get("author", "")).strip()
            result = upsert_article_record(article_env_map, env_map, url, capture, analysis, item)
            results.append(
                {
                    "ok": True,
                    "pending": False,
                    "url": url,
                    "title": capture.get("title", ""),
                    **result,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "ok": False,
                    "url": url,
                    "recordId": str(item.get("recordId", "")).strip(),
                    "error": str(exc),
                }
            )
    return {
        "ok": True,
        "count": len(results),
        "items": results,
    }


def status_payload(env_path: Path, env_map: dict[str, str]) -> dict[str, Any]:
    article_path = article_env_path(env_map)
    article_env_exists = article_path.exists()
    has_node = command_is_ready([node_bin(), "--version"])
    has_openclaw = command_is_ready([*openclaw_cli_args(), "--version"])
    has_camoufox = importlib.util.find_spec("camoufox") is not None
    playwright_ready = False
    if has_node:
        playwright_ready = command_is_ready(
            [node_bin(), "-e", "import('playwright').then(() => console.log('ok')).catch(() => process.exit(1))"],
            cwd=capture_script_path().parent.parent,
            success_stdout="ok",
        )
    payload = {
        "envPath": str(env_path),
        "envExists": env_path.exists(),
        "articleEnvPath": str(article_path),
        "articleEnvExists": article_env_exists,
        "openclawProfile": env_map.get("OPENCLAW_PROFILE", ""),
        "openclawConfigPath": str(current_openclaw_config_path()),
        "captureEngine": env_map.get("CAPTURE_ENGINE", ""),
        "summaryEngine": env_map.get("SUMMARY_ENGINE", ""),
        "summaryOpenclawProfile": env_map.get("SUMMARY_OPENCLAW_PROFILE", ""),
        "captureScriptPath": str(capture_script_path()),
        "hasNode": has_node,
        "hasOpenClaw": has_openclaw,
        "hasCamoufox": has_camoufox,
        "playwrightReady": playwright_ready,
        "nodeBin": node_bin(),
        "npmBin": npm_bin(),
        "npxBin": npx_bin(),
    }
    try:
        _, article_env_map = load_article_env_map(env_map)
        client = article_module.ensure_client(article_env_map)
        payload["articleTableName"] = client.table_name
        payload["articleTableId"] = client.table_id
        payload["bitableReachable"] = True
    except Exception as exc:
        payload["bitableReachable"] = False
        payload["bitableError"] = str(exc)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Portable WeChat article capture and enrichment")
    parser.add_argument("--env-path", default=str(current_env_path()))
    parser.add_argument("--init-env", action="store_true")
    parser.add_argument("--show-status", action="store_true")
    parser.add_argument("--capture-url", default="")
    parser.add_argument("--ingest-url", default="")
    parser.add_argument("--enrich-pending", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    env_path = Path(args.env_path)
    env_map = read_env_map(env_path)

    if args.init_env:
        write_env_map(env_path, env_map)
        print(json.dumps({"ok": True, "envPath": str(env_path)}, ensure_ascii=False))
        return 0

    load_env_file(env_path)

    if args.show_status:
        payload = status_payload(env_path, env_map)
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else json.dumps(payload, ensure_ascii=False))
        return 0

    if args.capture_url:
        payload = run_capture(args.capture_url.strip(), env_map)
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else json.dumps(payload, ensure_ascii=False))
        return 0

    if args.ingest_url:
        payload = ingest_url(env_map, args.ingest_url.strip())
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else json.dumps(payload, ensure_ascii=False))
        return 0

    if args.enrich_pending:
        payload = enrich_pending(env_map, max(args.limit, 1))
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else json.dumps(payload, ensure_ascii=False))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
