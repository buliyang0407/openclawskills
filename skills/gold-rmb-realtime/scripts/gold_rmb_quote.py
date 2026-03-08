#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://api.twelvedata.com/quote"
OZ_TO_GRAMS = 31.1034768
DEFAULT_STATE_PATH = Path("/var/lib/openclaw/gold-rmb-watch-state.json")
DEFAULT_ENV_PATH = Path("/etc/openclaw/gold-rmb.env")
DEFAULT_WATCH_TIMER = "openclaw-gold-rmb-watch.timer"
DEFAULT_HOURLY_TIMER = "openclaw-gold-rmb-hourly.timer"
DEFAULT_OPENCLAW_CONFIG_PATH = Path("/root/.openclaw/openclaw.json")
BITABLE_NODE_HELPER_PATH = Path(__file__).with_name("feishu_bitable_uat.mjs")
FIXED_BROADCAST_TIMES = ["08:00", "20:00"]
DEFAULT_ENV = {
    "MOVE_THRESHOLD_CNY_PER_GRAM": "1.00",
    "MIN_PUSH_INTERVAL_SECONDS": "900",
    "DELIVERY_CHANNEL": "feishu",
}
BITABLE_FIELDS = (
    "时间",
    "国际金价",
    "汇率",
    "人民币/盎司",
    "人民币/克",
    "触发原因",
)


def current_env_path() -> Path:
    return Path(os.environ.get("GOLD_RMB_ENV_PATH", str(DEFAULT_ENV_PATH)))


def current_state_path() -> Path:
    return Path(os.environ.get("GOLD_RMB_STATE_PATH", str(DEFAULT_STATE_PATH)))


def current_watch_timer() -> str:
    return os.environ.get("GOLD_RMB_WATCH_TIMER_UNIT", DEFAULT_WATCH_TIMER).strip() or DEFAULT_WATCH_TIMER


def current_hourly_timer() -> str:
    return os.environ.get("GOLD_RMB_HOURLY_TIMER_UNIT", DEFAULT_HOURLY_TIMER).strip() or DEFAULT_HOURLY_TIMER


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
    lines = [f"{key}={value}" for key, value in env_map.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_command(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = "/root/.nvm/versions/node/v22.22.0/bin:" + env.get("PATH", "")
    proc = subprocess.run(args, capture_output=True, text=True, env=env)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"命令失败: {' '.join(args)} detail={detail}")
    return proc


def run_systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run_command(["systemctl", *args], check=check)


def run_command_with_input(args: list[str], payload: str, check: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = "/root/.nvm/versions/node/v22.22.0/bin:" + env.get("PATH", "")
    proc = subprocess.run(args, input=payload, capture_output=True, text=True, env=env)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"command failed: {' '.join(args)} detail={detail}")
    return proc


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


def request_json(url: str, *, data: bytes | None = None, headers: dict | None = None, retries: int = 3) -> dict:
    merged_headers = {"User-Agent": "openclaw-gold-rmb/1.0", "Accept": "application/json"}
    if headers:
        merged_headers.update(headers)
    last_error = None
    for attempt in range(1, retries + 1):
        req = Request(url, data=data, headers=merged_headers)
        try:
            with urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(attempt)
    raise RuntimeError(f"\u8bf7\u6c42\u5931\u8d25: {url} error={last_error}")


def td_quote(symbol: str, apikey: str) -> dict:
    params = urlencode({"symbol": symbol, "apikey": apikey})
    return request_json(f"{API_BASE}?{params}")


def get_float(data: dict, key: str) -> float:
    value = data.get(key)
    if value in (None, ""):
        raise ValueError(f"\u7f3a\u5c11\u5b57\u6bb5 {key}")
    return float(value)


def build_snapshot(apikey: str) -> dict:
    xau = td_quote("XAU/USD", apikey)
    usdcny = td_quote("USD/CNY", apikey)
    if xau.get("code") or usdcny.get("code"):
        raise ValueError(f"Twelve Data \u8fd4\u56de\u9519\u8bef: xau={xau} usdcny={usdcny}")

    usd_per_oz = get_float(xau, "close")
    cny_per_usd = get_float(usdcny, "close")
    cny_per_oz = usd_per_oz * cny_per_usd
    cny_per_g = cny_per_oz / OZ_TO_GRAMS

    ts_xau = int(xau.get("last_quote_at") or xau.get("timestamp") or 0)
    ts_fx = int(usdcny.get("last_quote_at") or usdcny.get("timestamp") or 0)
    if ts_xau <= 0 or ts_fx <= 0:
        raise ValueError("\u62a5\u4ef7\u65f6\u95f4\u6233\u7f3a\u5931")
    if abs(ts_xau - ts_fx) > 600:
        raise ValueError(f"\u4e24\u8def\u62a5\u4ef7\u65f6\u95f4\u5dee\u8fc7\u5927: {ts_xau} vs {ts_fx}")

    return {
        "observed_at": max(ts_xau, ts_fx),
        "usd_per_oz": usd_per_oz,
        "cny_per_usd": cny_per_usd,
        "cny_per_oz": cny_per_oz,
        "cny_per_g": cny_per_g,
    }


def format_message(s: dict, reason: str) -> str:
    local_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(s["observed_at"]))
    return (
        "\u3010\u5b9e\u65f6\u4eba\u6c11\u5e01\u91d1\u4ef7\u3011\n"
        f"\u65f6\u95f4\uff1a{local_time}\n"
        f"\u56fd\u9645\u91d1\u4ef7\uff1a{s['usd_per_oz']:.4f} \u7f8e\u5143/\u76ce\u53f8\n"
        f"\u7f8e\u5143\u6c47\u7387\uff1a{s['cny_per_usd']:.5f}\n\n"
        f"\u6298\u5408\uff1a{s['cny_per_oz']:.2f} \u4eba\u6c11\u5e01\u5143/\u76ce\u53f8\n"
        f"\u6298\u5408\uff1a{s['cny_per_g']:.2f} \u4eba\u6c11\u5e01\u5143/\u514b\n\n"
        f"\u89e6\u53d1\u539f\u56e0\uff1a{reason}\n"
        "\u6570\u636e\u6e90\uff1aTwelve Data\uff08XAU/USD + USD/CNY\uff09"
    )


def read_state() -> dict | None:
    state_path = current_state_path()
    if not state_path.exists():
        return None
    return json.loads(state_path.read_text(encoding="utf-8"))


def write_state(state: dict) -> None:
    state_path = current_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


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


def derive_bitable_user_open_id(env_map: dict[str, str]) -> str:
    explicit = env_map.get("FEISHU_BITABLE_USER_OPEN_ID", "").strip()
    if explicit:
        return explicit
    delivery_channel = env_map.get("DELIVERY_CHANNEL", DEFAULT_ENV["DELIVERY_CHANNEL"]).strip().lower()
    delivery_target = env_map.get("DELIVERY_TARGET", "").strip()
    if delivery_channel == "feishu" and delivery_target.startswith("ou_"):
        return delivery_target
    return ""


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

    def append_snapshot(self, snapshot: dict, reason: str) -> None:
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
            "fieldNames": list(BITABLE_FIELDS),
            "fields": {
                "时间": time.strftime("%m-%d %H:%M", time.localtime(snapshot["observed_at"])),
                "国际金价": f"{snapshot['usd_per_oz']:.4f} 美元/盎司",
                "汇率": f"{snapshot['cny_per_usd']:.5f}",
                "人民币/盎司": f"{snapshot['cny_per_oz']:.2f}",
                "人民币/克": f"{snapshot['cny_per_g']:.2f}",
                "触发原因": reason,
            },
        }
        proc = run_command_with_input(
            ["node", str(BITABLE_NODE_HELPER_PATH)],
            json.dumps(payload, ensure_ascii=False),
        )
        data = json.loads(proc.stdout.strip() or "{}")
        table_id = str(data.get("tableId", "")).strip()
        if table_id:
            self.table_id = table_id


def bitable_client_from_env(env_map: dict[str, str]) -> FeishuPluginBitableClient | None:
    app_token = env_map.get("FEISHU_BITABLE_APP_TOKEN", "").strip()
    if not app_token:
        return None
    creds = load_openclaw_feishu_account()
    app_id = creds.get("app_id", "")
    app_secret = creds.get("app_secret", "")
    domain = creds.get("domain", "feishu")
    user_open_id = derive_bitable_user_open_id(env_map)
    table_id = env_map.get("FEISHU_BITABLE_TABLE_ID", "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("Feishu Bitable plugin mode requires Feishu app credentials in openclaw.json")
    if not user_open_id:
        raise RuntimeError(
            "Feishu Bitable plugin mode requires FEISHU_BITABLE_USER_OPEN_ID, "
            "or a Feishu DELIVERY_TARGET that is a user open_id"
        )
    return FeishuPluginBitableClient(app_id, app_secret, app_token, table_id, user_open_id, domain)


def should_push(curr: dict, prev: dict | None, threshold_g: float, min_interval: int) -> tuple[bool, str]:
    if prev is None:
        return True, "\u9996\u6b21\u4e0a\u7ebf\u64ad\u62a5"
    if curr["observed_at"] <= int(prev.get("observed_at", 0)):
        return False, "\u884c\u60c5\u65f6\u95f4\u672a\u66f4\u65b0"
    delta_g = abs(curr["cny_per_g"] - float(prev.get("cny_per_g", 0)))
    elapsed = curr["observed_at"] - int(prev.get("last_pushed_at", 0))
    if delta_g >= threshold_g and elapsed >= min_interval:
        return True, f"\u6bcf\u514b\u53d8\u52a8 {delta_g:.2f} \u5143"
    return False, f"\u6bcf\u514b\u53d8\u52a8 {delta_g:.2f} \u5143\uff0c\u672a\u8fbe\u9608\u503c {threshold_g:.2f}"


def push_text(text: str) -> None:
    env_map = read_env_map(current_env_path())
    channel = env_map.get("DELIVERY_CHANNEL", DEFAULT_ENV["DELIVERY_CHANNEL"]).strip()
    target = env_map.get("DELIVERY_TARGET", "").strip()
    if not target:
        raise SystemExit("DELIVERY_TARGET \u672a\u914d\u7f6e")
    run_command([
        *openclaw_cli_args(),
        "message",
        "send",
        "--channel", channel,
        "--target", target,
        "--message", text,
    ])


def push_snapshot(snapshot: dict, reason: str) -> None:
    snapshot["last_pushed_at"] = snapshot["observed_at"]
    env_map = read_env_map(current_env_path())
    bitable_client = bitable_client_from_env(env_map)
    if bitable_client is not None:
        bitable_client.append_snapshot(snapshot, reason)
    push_text(format_message(snapshot, reason))
    write_state(snapshot)


def show_config() -> int:
    env_map = read_env_map(current_env_path())
    public_view = {
        "delivery_channel": env_map.get("DELIVERY_CHANNEL", DEFAULT_ENV["DELIVERY_CHANNEL"]),
        "delivery_target": env_map.get("DELIVERY_TARGET", ""),
        "move_threshold_cny_per_gram": env_map.get("MOVE_THRESHOLD_CNY_PER_GRAM", DEFAULT_ENV["MOVE_THRESHOLD_CNY_PER_GRAM"]),
        "min_push_interval_seconds": env_map.get("MIN_PUSH_INTERVAL_SECONDS", DEFAULT_ENV["MIN_PUSH_INTERVAL_SECONDS"]),
        "api_key_configured": bool(env_map.get("TWELVEDATA_API_KEY", "")),
        "bitable_enabled": bool(env_map.get("FEISHU_BITABLE_APP_TOKEN", "").strip()),
        "bitable_table_id_configured": bool(env_map.get("FEISHU_BITABLE_TABLE_ID", "").strip()),
        "bitable_user_open_id_configured": bool(derive_bitable_user_open_id(env_map)),
        "openclaw_profile": current_openclaw_profile() or "default",
        "openclaw_config_path": str(current_openclaw_config_path()),
    }
    print(json.dumps(public_view, ensure_ascii=False, indent=2))
    return 0


def show_status() -> int:
    env_map = read_env_map(current_env_path())
    status = {
        "delivery_channel": env_map.get("DELIVERY_CHANNEL", DEFAULT_ENV["DELIVERY_CHANNEL"]),
        "delivery_target": env_map.get("DELIVERY_TARGET", ""),
        "move_threshold_cny_per_gram": env_map.get("MOVE_THRESHOLD_CNY_PER_GRAM", DEFAULT_ENV["MOVE_THRESHOLD_CNY_PER_GRAM"]),
        "min_push_interval_seconds": env_map.get("MIN_PUSH_INTERVAL_SECONDS", DEFAULT_ENV["MIN_PUSH_INTERVAL_SECONDS"]),
        "watch_timer": timer_state(current_watch_timer()),
        "fixed_broadcast_timer": timer_state(current_hourly_timer()),
        "fixed_broadcast_times": FIXED_BROADCAST_TIMES,
        "api_key_configured": bool(env_map.get("TWELVEDATA_API_KEY", "")),
        "bitable_enabled": bool(env_map.get("FEISHU_BITABLE_APP_TOKEN", "").strip()),
        "bitable_table_id_configured": bool(env_map.get("FEISHU_BITABLE_TABLE_ID", "").strip()),
        "bitable_user_open_id_configured": bool(derive_bitable_user_open_id(env_map)),
    }
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


def set_config(*, threshold: float | None, min_interval: int | None, delivery_channel: str | None, delivery_target: str | None) -> int:
    env_map = read_env_map(current_env_path())
    changed = False
    if threshold is not None:
        if threshold < 0:
            raise SystemExit("\u9608\u503c\u4e0d\u80fd\u4e3a\u8d1f\u6570")
        env_map["MOVE_THRESHOLD_CNY_PER_GRAM"] = f"{threshold:.2f}"
        changed = True
    if min_interval is not None:
        if min_interval < 0:
            raise SystemExit("\u95f4\u9694\u4e0d\u80fd\u4e3a\u8d1f\u6570")
        env_map["MIN_PUSH_INTERVAL_SECONDS"] = str(min_interval)
        changed = True
    if delivery_channel is not None:
        env_map["DELIVERY_CHANNEL"] = delivery_channel.strip()
        changed = True
    if delivery_target is not None:
        env_map["DELIVERY_TARGET"] = delivery_target.strip()
        changed = True
    if not changed:
        raise SystemExit("\u6ca1\u6709\u4f20\u5165\u9700\u8981\u4fee\u6539\u7684\u914d\u7f6e")
    env_path = current_env_path()
    write_env_map(env_path, env_map)
    os.chmod(env_path, 0o600)
    print(json.dumps({
        "delivery_channel": env_map.get("DELIVERY_CHANNEL", DEFAULT_ENV["DELIVERY_CHANNEL"]),
        "delivery_target": env_map.get("DELIVERY_TARGET", ""),
        "move_threshold_cny_per_gram": env_map["MOVE_THRESHOLD_CNY_PER_GRAM"],
        "min_push_interval_seconds": env_map["MIN_PUSH_INTERVAL_SECONDS"],
    }, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    load_env_file(current_env_path())
    parser = argparse.ArgumentParser(description="Realtime gold RMB quote watcher")
    parser.add_argument("--json", action="store_true", help="Print current snapshot as JSON")
    parser.add_argument("--push-once", action="store_true", help="Force one outbound push and update state")
    parser.add_argument("--check-and-push", action="store_true", help="Push only when threshold is crossed")
    parser.add_argument("--reason", default="\u624b\u52a8\u63a8\u9001", help="Reason used when --push-once sends a message")
    parser.add_argument("--show-config", action="store_true", help="Show alert configuration without exposing the API key")
    parser.add_argument("--show-status", action="store_true", help="Show alert config and timer status")
    parser.add_argument("--set-threshold", type=float, help="Set MOVE_THRESHOLD_CNY_PER_GRAM")
    parser.add_argument("--set-min-interval", type=int, help="Set MIN_PUSH_INTERVAL_SECONDS")
    parser.add_argument("--set-delivery-channel", help="Set DELIVERY_CHANNEL")
    parser.add_argument("--set-delivery-target", help="Set DELIVERY_TARGET")
    parser.add_argument("--pause-watch", action="store_true", help="Disable threshold-based watch timer")
    parser.add_argument("--resume-watch", action="store_true", help="Enable threshold-based watch timer")
    parser.add_argument("--pause-hourly", action="store_true", help="Disable the fixed broadcast timer (currently 08:00 and 20:00)")
    parser.add_argument("--resume-hourly", action="store_true", help="Enable the fixed broadcast timer (currently 08:00 and 20:00)")
    args = parser.parse_args()

    if args.show_config:
        return show_config()
    if args.show_status:
        return show_status()
    if any(v is not None for v in [args.set_threshold, args.set_min_interval, args.set_delivery_channel, args.set_delivery_target]):
        return set_config(
            threshold=args.set_threshold,
            min_interval=args.set_min_interval,
            delivery_channel=args.set_delivery_channel,
            delivery_target=args.set_delivery_target,
        )
    if args.pause_watch:
        print(json.dumps(control_timer(current_watch_timer(), "pause"), ensure_ascii=False, indent=2))
        return 0
    if args.resume_watch:
        print(json.dumps(control_timer(current_watch_timer(), "resume"), ensure_ascii=False, indent=2))
        return 0
    if args.pause_hourly:
        print(json.dumps(control_timer(current_hourly_timer(), "pause"), ensure_ascii=False, indent=2))
        return 0
    if args.resume_hourly:
        print(json.dumps(control_timer(current_hourly_timer(), "resume"), ensure_ascii=False, indent=2))
        return 0

    apikey = os.environ.get("TWELVEDATA_API_KEY", "").strip()
    if not apikey:
        raise SystemExit("TWELVEDATA_API_KEY \u672a\u914d\u7f6e")

    snapshot = build_snapshot(apikey)
    if args.json:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        return 0

    if not args.push_once and not args.check_and_push:
        parser.error("\u9700\u8981\u6307\u5b9a有效动作")

    if args.push_once:
        push_snapshot(snapshot, args.reason)
        return 0

    prev = read_state()
    threshold_g = float(os.environ.get("MOVE_THRESHOLD_CNY_PER_GRAM", DEFAULT_ENV["MOVE_THRESHOLD_CNY_PER_GRAM"]))
    min_interval = int(os.environ.get("MIN_PUSH_INTERVAL_SECONDS", DEFAULT_ENV["MIN_PUSH_INTERVAL_SECONDS"]))
    should, reason = should_push(snapshot, prev, threshold_g, min_interval)
    if should:
        push_snapshot(snapshot, reason)
    else:
        snapshot["last_pushed_at"] = int((prev or {}).get("last_pushed_at", 0))
        write_state(snapshot)
        print(reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
