#!/usr/bin/env python3
import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_ENV_PATH = Path("/etc/openclaw/knowledge-base-manager.env")
DEFAULT_OPENCLAW_CONFIG_PATH = Path("/root/.openclaw/openclaw.json")
COMMON_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "common" / "scripts"
BITABLE_DEFAULT_TABLE_NAME = "内容总表"
BITABLE_FIELDS = (
    "时间",
    "标题",
    "摘要",
    "来源类型",
    "来源渠道",
    "来源账号",
    "主题标签",
    "重要度",
    "是否已读",
    "是否收藏",
    "原链接",
    "归档时间",
    "摘要模型",
    "数据来源",
)
DEFAULT_ENV = {
    "OPENCLAW_PROFILE": "",
    "KNOWLEDGE_BASE_SOURCE_NAME": "阳仔3号（知识库）",
    "FEISHU_BITABLE_TABLE_NAME": BITABLE_DEFAULT_TABLE_NAME,
}

if str(COMMON_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_SCRIPTS_DIR))

from feishu_bitable_plugin import bitable_client_from_env


def current_env_path() -> Path:
    return Path(os.environ.get("KNOWLEDGE_BASE_ENV_PATH", str(DEFAULT_ENV_PATH)))


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


def ensure_client(env_map: dict[str, str]):
    client = bitable_client_from_env(
        env_map,
        delivery_channel="feishu",
        delivery_target=env_map.get("FEISHU_BITABLE_USER_OPEN_ID", ""),
        default_table_name=env_map.get("FEISHU_BITABLE_TABLE_NAME", BITABLE_DEFAULT_TABLE_NAME),
    )
    if client is None:
        raise RuntimeError("missing FEISHU_BITABLE_APP_TOKEN in env")
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


def sort_key(item: dict[str, Any]) -> tuple[str, str]:
    fields = item.get("fields", {})
    return (
        str(fields.get("时间", "") or ""),
        str(fields.get("归档时间", "") or ""),
    )


def print_records(items: list[dict[str, Any]]) -> None:
    if not items:
        print("没有找到记录。")
        return
    for idx, item in enumerate(items, start=1):
        fields = item.get("fields", {})
        print(f"{idx}. {fields.get('标题', '')}")
        print(f"   时间: {fields.get('时间', '')}")
        print(f"   来源: {fields.get('来源渠道', '')} / {fields.get('来源账号', '')}")
        print(f"   类型: {fields.get('来源类型', '')}")
        print(f"   标签: {fields.get('主题标签', '')}")
        print(f"   摘要: {fields.get('摘要', '')}")
        print(f"   链接: {fields.get('原链接', '')}")


def add_manual(env_map: dict[str, str], args: argparse.Namespace) -> dict[str, Any]:
    client = ensure_client(env_map)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fields = {
        "时间": args.time or now,
        "标题": args.title,
        "摘要": args.summary,
        "来源类型": args.source_type,
        "来源渠道": args.source_channel,
        "来源账号": args.source_name or env_map.get("KNOWLEDGE_BASE_SOURCE_NAME", "阳仔3号（知识库）"),
        "主题标签": args.tags or "",
        "重要度": args.importance or "中",
        "是否已读": "否",
        "是否收藏": "是" if args.favorite else "否",
        "原链接": args.source_url or "",
        "归档时间": now,
        "摘要模型": args.summary_model or "manual",
        "数据来源": args.data_source or "manual",
    }
    record_id = client.append_record(fields, BITABLE_FIELDS)
    return {"ok": True, "recordId": record_id, "fields": fields}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Yangzai3 knowledge base manager")
    parser.add_argument("--env-path", default=str(current_env_path()))
    parser.add_argument("--init-env", action="store_true")
    parser.add_argument("--show-status", action="store_true")
    parser.add_argument("--recent", action="store_true")
    parser.add_argument("--search")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--add-manual", action="store_true")
    parser.add_argument("--title")
    parser.add_argument("--summary")
    parser.add_argument("--source-type", default="资产")
    parser.add_argument("--source-channel", default="手工录入")
    parser.add_argument("--source-name", default="")
    parser.add_argument("--tags", default="")
    parser.add_argument("--importance", default="中")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--time", default="")
    parser.add_argument("--summary-model", default="manual")
    parser.add_argument("--data-source", default="manual")
    parser.add_argument("--favorite", action="store_true")
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

    if args.add_manual:
        if not args.title or not args.summary:
            raise SystemExit("--add-manual requires --title and --summary")
        payload = add_manual(env_map, args)
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else json.dumps(payload, ensure_ascii=False))
        return 0

    if args.recent or args.search:
        items = list_records(env_map, max(args.limit * 5, 50))
        items = sorted(items, key=sort_key, reverse=True)
        if args.search:
            needle = args.search.lower()
            items = [
                item
                for item in items
                if needle
                in " ".join(str(v) for v in item.get("fields", {}).values()).lower()
            ]
        items = items[: args.limit]
        if args.json:
            print(json.dumps(items, ensure_ascii=False, indent=2))
        else:
            print_records(items)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
