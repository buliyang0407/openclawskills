#!/usr/bin/env python3
import json
import os
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_OPENCLAW_CONFIG_PATH = Path("/root/.openclaw/openclaw.json")
BITABLE_NODE_HELPER_PATH = Path(__file__).with_name("feishu_bitable_helper.mjs")


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
    if not app_id or not app_secret:
        return {}
    return {"app_id": app_id, "app_secret": app_secret, "domain": domain}


def derive_bitable_user_open_id(env_map: dict[str, str], delivery_channel: str, delivery_target: str) -> str:
    explicit = env_map.get("FEISHU_BITABLE_USER_OPEN_ID", "").strip()
    if explicit:
        return explicit
    if delivery_channel.strip().lower() == "feishu" and delivery_target.strip().startswith("ou_"):
        return delivery_target.strip()
    return ""


def run_command_with_input(args: list[str], payload: str, check: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = "/root/.nvm/versions/node/v22.22.0/bin:/usr/local/bin:" + env.get("PATH", "")
    proc = subprocess.run(args, input=payload, capture_output=True, text=True, env=env)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"command failed: {' '.join(args)} detail={detail}")
    return proc


class FeishuPluginBitableClient:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        app_token: str,
        table_id: str | None,
        user_open_id: str,
        *,
        table_name: str | None = None,
        domain: str = "feishu",
    ) -> None:
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.table_id = table_id or ""
        self.table_name = table_name or ""
        self.user_open_id = user_open_id
        self.domain = domain or "feishu"

    def append_record(self, fields: dict[str, str], field_names: tuple[str, ...]) -> str:
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
            "tableName": self.table_name,
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
        return str(data.get("recordId", "")).strip()


def bitable_client_from_env(
    env_map: dict[str, str],
    *,
    delivery_channel: str,
    delivery_target: str,
    default_table_name: str,
) -> FeishuPluginBitableClient | None:
    app_token = env_map.get("FEISHU_BITABLE_APP_TOKEN", "").strip()
    if not app_token:
        return None
    creds = load_openclaw_feishu_account()
    app_id = creds.get("app_id", "")
    app_secret = creds.get("app_secret", "")
    domain = creds.get("domain", "feishu")
    user_open_id = derive_bitable_user_open_id(env_map, delivery_channel, delivery_target)
    table_id = env_map.get("FEISHU_BITABLE_TABLE_ID", "").strip()
    table_name = env_map.get("FEISHU_BITABLE_TABLE_NAME", "").strip() or default_table_name
    if not app_id or not app_secret:
        raise RuntimeError("Feishu Bitable plugin mode requires Feishu app credentials in openclaw.json")
    if not user_open_id:
        raise RuntimeError(
            "Feishu Bitable plugin mode requires FEISHU_BITABLE_USER_OPEN_ID, "
            "or a Feishu DELIVERY_TARGET that is a user open_id"
        )
    return FeishuPluginBitableClient(
        app_id,
        app_secret,
        app_token,
        table_id,
        user_open_id,
        table_name=table_name,
        domain=domain,
    )
