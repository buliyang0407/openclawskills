#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_ENV_PATH = Path("/etc/openclaw/article-knowledge-manager.env")
COMMON_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "common" / "scripts"
DEFAULT_OPENCLAW_CONFIG_PATH = Path("/root/.openclaw/openclaw.json")
DEFAULT_TABLE_NAME = "文章库"
DEFAULT_SOURCE_NAME = "阳仔3号（知识库）"
DEFAULT_TOTAL_INDEX_TABLE_NAME = "内容总表"

ARTICLE_FIELDS = (
    "标题",
    "链接",
    "作者/来源",
    "发布时间",
    "文章摘要",
    "核心观点",
    "关键词",
    "类别",
    "标签",
    "我的备注",
    "阅读状态",
    "收藏等级",
    "关联项目",
    "是否已入总表",
    "去重指纹",
    "录入时间",
    "适用场景",
    "引用价值",
)

TOTAL_INDEX_FIELDS = (
    "标题",
    "摘要",
    "内容类型",
    "来源渠道",
    "来源账号",
    "时间",
    "标签",
    "重要度",
    "是否收藏",
    "是否已读",
    "原链接",
    "来源表",
    "来源记录ID",
    "去重指纹",
    "归档时间",
    "状态",
)

DEFAULT_ENV = {
    "OPENCLAW_PROFILE": "",
    "ARTICLE_KNOWLEDGE_SOURCE_NAME": DEFAULT_SOURCE_NAME,
    "FEISHU_BITABLE_TABLE_NAME": DEFAULT_TABLE_NAME,
    "TOTAL_INDEX_TABLE_NAME": DEFAULT_TOTAL_INDEX_TABLE_NAME,
}

if str(COMMON_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS_DIR))

from feishu_bitable_plugin import bitable_client_from_env  # noqa: E402


def current_env_path() -> Path:
    return Path(os.environ.get("ARTICLE_KNOWLEDGE_ENV_PATH", str(DEFAULT_ENV_PATH)))


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


def load_openclaw_feishu_account() -> dict[str, str]:
    config_path = current_openclaw_config_path()
    if not config_path.exists():
        return {}
    config = json.loads(config_path.read_text(encoding="utf-8"))
    feishu = config.get("channels", {}).get("feishu", {})
    default_account = feishu.get("defaultAccount", "main")
    account_cfg = feishu.get("accounts", {}).get(default_account, {})
    app_id = str(feishu.get("appId", "") or account_cfg.get("appId", "")).strip()
    app_secret = str(feishu.get("appSecret", "") or account_cfg.get("appSecret", "")).strip()
    domain = str(feishu.get("domain", "") or account_cfg.get("domain", "") or "feishu").strip()
    return {"app_id": app_id, "app_secret": app_secret, "domain": domain}


def helper_path() -> Path:
    return COMMON_SCRIPTS_DIR / "feishu_bitable_helper.mjs"


def run_helper(payload: dict[str, Any]) -> dict[str, Any]:
    helper = helper_path()
    if not helper.exists():
        raise RuntimeError(f"Feishu Bitable helper not found: {helper}")
    env = dict(os.environ)
    env["PATH"] = "/root/.nvm/versions/node/v22.22.0/bin:/usr/local/bin:" + env.get("PATH", "")
    last_error = "bitable helper returned empty output"
    for _ in range(2):
        proc = subprocess.run(
            ["node", str(helper)],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        if proc.returncode != 0:
            last_error = stderr or stdout or "bitable helper failed"
            continue
        if not stdout:
            last_error = stderr or "bitable helper returned empty output"
            continue
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            preview = stdout[:500]
            last_error = f"bitable helper returned non-json output: {preview}"
            continue
    raise RuntimeError(last_error)


def ensure_client(env_map: dict[str, str]):
    client = bitable_client_from_env(
        env_map,
        delivery_channel="feishu",
        delivery_target=env_map.get("FEISHU_BITABLE_USER_OPEN_ID", ""),
        default_table_name=env_map.get("FEISHU_BITABLE_TABLE_NAME", DEFAULT_TABLE_NAME),
    )
    if client is None:
        raise RuntimeError("missing FEISHU_BITABLE_APP_TOKEN in env")
    return client


def total_index_client(env_map: dict[str, str]):
    total_env = dict(env_map)
    table_id = env_map.get("TOTAL_INDEX_TABLE_ID", "").strip()
    table_name = env_map.get("TOTAL_INDEX_TABLE_NAME", "").strip() or DEFAULT_TOTAL_INDEX_TABLE_NAME
    if table_id:
        total_env["FEISHU_BITABLE_TABLE_ID"] = table_id
    else:
        total_env.pop("FEISHU_BITABLE_TABLE_ID", None)
    total_env["FEISHU_BITABLE_TABLE_NAME"] = table_name
    client = bitable_client_from_env(
        total_env,
        delivery_channel="feishu",
        delivery_target=env_map.get("FEISHU_BITABLE_USER_OPEN_ID", ""),
        default_table_name=table_name,
    )
    return client


def list_records(env_map: dict[str, str], limit: int = 200) -> list[dict[str, Any]]:
    client = ensure_client(env_map)
    creds = load_openclaw_feishu_account()
    data = run_helper(
        {
            "action": "list_records",
            "appId": client.app_id,
            "appSecret": client.app_secret,
            "domain": creds.get("domain", "feishu"),
            "userOpenId": client.user_open_id,
            "appToken": client.app_token,
            "tableId": client.table_id,
            "tableName": client.table_name,
            "pageSize": min(max(limit, 1), 500),
        }
    )
    return list(data.get("items", []))


def status_payload(env_path: Path, env_map: dict[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "envPath": str(env_path),
        "envExists": env_path.exists(),
        "openclawProfile": env_map.get("OPENCLAW_PROFILE", ""),
        "openclawConfigPath": str(current_openclaw_config_path()),
        "tableName": env_map.get("FEISHU_BITABLE_TABLE_NAME", ""),
        "tableId": env_map.get("FEISHU_BITABLE_TABLE_ID", ""),
        "totalIndexTableName": env_map.get("TOTAL_INDEX_TABLE_NAME", ""),
        "totalIndexTableId": env_map.get("TOTAL_INDEX_TABLE_ID", ""),
        "hasAppToken": bool(env_map.get("FEISHU_BITABLE_APP_TOKEN", "").strip()),
        "hasUserOpenId": bool(env_map.get("FEISHU_BITABLE_USER_OPEN_ID", "").strip()),
    }
    try:
        client = ensure_client(env_map)
        creds = load_openclaw_feishu_account()
        tables = run_helper(
            {
                "action": "list_tables",
                "appId": client.app_id,
                "appSecret": client.app_secret,
                "domain": creds.get("domain", "feishu"),
                "userOpenId": client.user_open_id,
                "appToken": client.app_token,
            }
        )
        result["bitableReachable"] = True
        result["tables"] = tables.get("items", [])
    except BaseException as exc:
        result["bitableReachable"] = False
        result["bitableError"] = str(exc)
    return result


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def dedupe_fingerprint(url: str, title: str) -> str:
    basis = f"{url.strip()}|{title.strip()}".encode("utf-8")
    return hashlib.sha256(basis).hexdigest()[:24]


def join_csv_like(value: str) -> str:
    parts = [part.strip() for part in value.split(",")]
    parts = [part for part in parts if part]
    return ", ".join(parts)


def save_article(env_map: dict[str, str], args: argparse.Namespace) -> dict[str, Any]:
    client = ensure_client(env_map)
    title = args.title.strip()
    url = args.url.strip()
    summary = args.summary.strip()
    author = args.author.strip() or args.source.strip() or env_map.get("ARTICLE_KNOWLEDGE_SOURCE_NAME", DEFAULT_SOURCE_NAME)
    fingerprint = dedupe_fingerprint(url, title)
    recorded_at = now_str()
    fields = {
        "标题": title,
        "链接": url,
        "作者/来源": author,
        "发布时间": args.published_at.strip(),
        "文章摘要": summary,
        "核心观点": args.core_points.strip(),
        "关键词": join_csv_like(args.keywords),
        "类别": args.category.strip(),
        "标签": join_csv_like(args.tags),
        "我的备注": args.notes.strip(),
        "阅读状态": args.read_status.strip() or "未读",
        "收藏等级": args.favorite_level.strip() or "普通",
        "关联项目": args.related_project.strip(),
        "是否已入总表": "是" if args.sync_to_total_index else "否",
        "去重指纹": fingerprint,
        "录入时间": recorded_at,
        "适用场景": join_csv_like(args.use_cases),
        "引用价值": args.reference_value.strip() or "中",
    }
    record_id = client.append_record(fields, ARTICLE_FIELDS)

    index_sync = None
    if args.sync_to_total_index:
        index_client = total_index_client(env_map)
        index_fields = {
            "标题": title,
            "摘要": summary,
            "内容类型": "文章",
            "来源渠道": args.source.strip() or "手动收藏",
            "来源账号": author,
            "时间": args.published_at.strip() or recorded_at,
            "标签": join_csv_like(args.tags or args.keywords),
            "重要度": args.reference_value.strip() or "中",
            "是否收藏": "是",
            "是否已读": "否" if (args.read_status.strip() or "未读") == "未读" else "是",
            "原链接": url,
            "来源表": env_map.get("FEISHU_BITABLE_TABLE_NAME", DEFAULT_TABLE_NAME),
            "来源记录ID": record_id,
            "去重指纹": fingerprint,
            "归档时间": recorded_at,
            "状态": "有效",
        }
        index_record_id = index_client.append_record(index_fields, TOTAL_INDEX_FIELDS)
        index_sync = {
            "tableName": env_map.get("TOTAL_INDEX_TABLE_NAME", DEFAULT_TOTAL_INDEX_TABLE_NAME),
            "recordId": index_record_id,
            "fields": index_fields,
        }

    return {
        "ok": True,
        "recordId": record_id,
        "fields": fields,
        "indexSync": index_sync,
    }


def sort_key(item: dict[str, Any]) -> tuple[str, str]:
    fields = item.get("fields", {})
    return (
        str(fields.get("发布时间", "") or ""),
        str(fields.get("录入时间", "") or ""),
    )


def score_record(item: dict[str, Any], query: str) -> int:
    haystack_parts = []
    fields = item.get("fields", {})
    for value in fields.values():
        haystack_parts.append(str(value))
    haystack = " ".join(haystack_parts).lower()
    query_lower = query.lower().strip()
    if not query_lower:
        return 0
    score = 0
    if query_lower in haystack:
        score += 5
    for token in query_lower.replace(",", " ").split():
        if token and token in haystack:
            score += 2
    return score


def search_records(env_map: dict[str, str], query: str, limit: int) -> list[dict[str, Any]]:
    items = list_records(env_map, max(limit * 10, 50))
    scored = []
    for item in items:
        score = score_record(item, query)
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda pair: (pair[0], sort_key(pair[1])), reverse=True)
    return [item for _, item in scored[:limit]]


def record_to_reference(item: dict[str, Any], query: str) -> dict[str, Any]:
    fields = item.get("fields", {})
    return {
        "title": str(fields.get("标题", "")).strip(),
        "url": str(fields.get("链接", "")).strip(),
        "source": str(fields.get("作者/来源", "")).strip(),
        "publishedAt": str(fields.get("发布时间", "")).strip(),
        "summary": str(fields.get("文章摘要", "")).strip(),
        "corePoints": str(fields.get("核心观点", "")).strip(),
        "keywords": str(fields.get("关键词", "")).strip(),
        "category": str(fields.get("类别", "")).strip(),
        "tags": str(fields.get("标签", "")).strip(),
        "useCases": str(fields.get("适用场景", "")).strip(),
        "referenceValue": str(fields.get("引用价值", "")).strip(),
        "relevanceReason": f"Matched query '{query}' across title, summary, keywords, or tags.",
    }


def print_records(items: list[dict[str, Any]]) -> None:
    if not items:
        print("No matching article records found.")
        return
    for idx, item in enumerate(items, start=1):
        fields = item.get("fields", {})
        print(f"{idx}. {fields.get('标题', '')}")
        print(f"   摘要: {fields.get('文章摘要', '')}")
        print(f"   关键词: {fields.get('关键词', '')}")
        print(f"   标签: {fields.get('标签', '')}")
        print(f"   链接: {fields.get('链接', '')}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Portable article knowledge manager")
    parser.add_argument("--env-path", default=str(current_env_path()))
    parser.add_argument("--init-env", action="store_true")
    parser.add_argument("--show-status", action="store_true")
    parser.add_argument("--save-article", action="store_true")
    parser.add_argument("--search")
    parser.add_argument("--reference-pack")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--url", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--summary", default="")
    parser.add_argument("--author", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--published-at", default="")
    parser.add_argument("--core-points", default="")
    parser.add_argument("--keywords", default="")
    parser.add_argument("--category", default="文章")
    parser.add_argument("--tags", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--read-status", default="未读")
    parser.add_argument("--favorite-level", default="普通")
    parser.add_argument("--related-project", default="")
    parser.add_argument("--use-cases", default="")
    parser.add_argument("--reference-value", default="中")
    parser.add_argument("--sync-to-total-index", action="store_true")
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

    if args.save_article:
        if not args.url or not args.title or not args.summary:
            raise SystemExit("--save-article requires --url, --title, and --summary")
        payload = save_article(env_map, args)
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else json.dumps(payload, ensure_ascii=False))
        return 0

    if args.search:
        items = search_records(env_map, args.search, args.limit)
        if args.json:
            print(json.dumps(items, ensure_ascii=False, indent=2))
        else:
            print_records(items)
        return 0

    if args.reference_pack:
        items = search_records(env_map, args.reference_pack, args.limit)
        payload = {
            "query": args.reference_pack,
            "count": len(items),
            "items": [record_to_reference(item, args.reference_pack) for item in items],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else json.dumps(payload, ensure_ascii=False))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
