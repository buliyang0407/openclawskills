#!/usr/bin/env python3
import argparse
import json
import os
import shlex
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_ENV_PATH = Path("/etc/openclaw/lobster-supervisor.env")
DEFAULT_STATE_PATH = Path("/var/lib/openclaw/lobster-supervisor/state.json")
DEFAULT_WATCH_TIMER = "openclaw-lobster-supervisor.timer"
DEFAULT_ENV = {
    "SUPERVISOR_NAME": "阳仔一号（主管虾）",
    "DELIVERY_PROFILE": "yangzai2",
    "DELIVERY_CHANNEL": "feishu",
    "AUTOHEAL": "true",
    "ALERT_REMIND_MINUTES": "60",
}


def current_env_path() -> Path:
    return Path(os.environ.get("SUPERVISOR_ENV_PATH", str(DEFAULT_ENV_PATH)))


def current_state_path() -> Path:
    return Path(os.environ.get("SUPERVISOR_STATE_PATH", str(DEFAULT_STATE_PATH)))


def current_watch_timer() -> str:
    return os.environ.get("SUPERVISOR_TIMER_UNIT", DEFAULT_WATCH_TIMER).strip() or DEFAULT_WATCH_TIMER


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
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), normalize_env_value(value))


def read_env_map(path: Path) -> dict[str, str]:
    env_map: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            env_map[key.strip()] = normalize_env_value(value)
    for key, value in DEFAULT_ENV.items():
        env_map.setdefault(key, value)
    return env_map


def write_env_map(path: Path, env_map: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={format_env_value(value)}" for key, value in env_map.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def read_state() -> dict[str, Any]:
    path = current_state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def write_state(state: dict[str, Any]) -> None:
    path = current_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(path, 0o600)


def run_command(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PATH"] = "/root/.nvm/versions/node/v22.22.0/bin:/usr/local/bin:" + env.get("PATH", "")
    proc = subprocess.run(args, capture_output=True, text=True, env=env)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"command failed: {' '.join(args)} detail={detail}")
    return proc


def run_shell(command: str, check: bool = True) -> subprocess.CompletedProcess:
    return run_command(["bash", "-lc", command], check=check)


def run_systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run_command(["systemctl", *args], check=check)


def systemd_snapshot(unit: str) -> dict[str, str]:
    active_proc = run_systemctl("is-active", unit, check=False)
    enabled_proc = run_systemctl("is-enabled", unit, check=False)
    return {
        "active": (active_proc.stdout.strip() or active_proc.stderr.strip() or "unknown"),
        "enabled": (enabled_proc.stdout.strip() or enabled_proc.stderr.strip() or "unknown"),
    }


def timer_state(unit: str) -> dict[str, str]:
    return systemd_snapshot(unit)


def control_timer(unit: str, action: str) -> dict[str, str]:
    if action == "pause":
        run_systemctl("disable", "--now", unit)
    elif action == "resume":
        run_systemctl("enable", "--now", unit)
    else:
        raise ValueError("unsupported action")
    state = timer_state(unit)
    return {"unit": unit, "enabled": state["enabled"], "active": state["active"]}


def parse_bool_env(env_map: dict[str, str], key: str, default: bool) -> bool:
    value = env_map.get(key, "true" if default else "false").strip().lower()
    return value not in {"0", "false", "no", "off", ""}


def parse_int_env(env_map: dict[str, str], key: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = env_map.get(key, "").strip()
    value = default
    if raw:
        value = int(raw)
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def check_tcp(host: str, port: int, timeout_seconds: float = 2.0) -> tuple[bool, str]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout_seconds)
    try:
        sock.connect((host, port))
        return True, f"{host}:{port} reachable"
    except OSError as exc:
        return False, f"{host}:{port} unreachable ({exc})"
    finally:
        sock.close()


def default_targets() -> list[dict[str, Any]]:
    return [
        {
            "id": "yangzai-watchdog-timer",
            "kind": "systemd",
            "label": "阳仔 watchdog.timer",
            "unit": "openclaw-watchdog.timer",
            "require_enabled": True,
            "repairs": [["systemctl", "enable", "--now", "openclaw-watchdog.timer"]],
        },
        {
            "id": "yangzai-gateway",
            "kind": "tcp",
            "label": "阳仔 gateway",
            "host": "127.0.0.1",
            "port": 18789,
            "repairs": [["systemctl", "restart", "openclaw-watchdog.service"]],
        },
        {
            "id": "yangzai2-service",
            "kind": "systemd",
            "label": "阳仔二号 service",
            "unit": "openclaw-yangzai2.service",
            "repairs": [["systemctl", "restart", "openclaw-yangzai2.service"]],
        },
        {
            "id": "yangzai2-wechat-timer",
            "kind": "systemd",
            "label": "阳仔二号公众号 timer",
            "unit": "openclaw-wechat-official-monitor-yangzai2.timer",
            "require_enabled": True,
            "repairs": [["systemctl", "enable", "--now", "openclaw-wechat-official-monitor-yangzai2.timer"]],
        },
        {
            "id": "yangzai2-gateway",
            "kind": "tcp",
            "label": "阳仔二号 gateway",
            "host": "127.0.0.1",
            "port": 19011,
            "repairs": [["systemctl", "restart", "openclaw-yangzai2.service"]],
        },
        {
            "id": "yangzai3-service",
            "kind": "systemd",
            "label": "阳仔三号 service",
            "unit": "openclaw-yangzai3.service",
            "repairs": [["systemctl", "restart", "openclaw-yangzai3.service"]],
        },
        {
            "id": "yangzai3-gateway",
            "kind": "tcp",
            "label": "阳仔三号 gateway",
            "host": "127.0.0.1",
            "port": 19031,
            "repairs": [["systemctl", "restart", "openclaw-yangzai3.service"]],
        },
        {
            "id": "yangzai-admin-service",
            "kind": "systemd",
            "label": "主管虾 service",
            "unit": "openclaw-yangzai-admin.service",
            "repairs": [["systemctl", "restart", "openclaw-yangzai-admin.service"]],
        },
        {
            "id": "yangzai-admin-gateway",
            "kind": "tcp",
            "label": "主管虾 gateway",
            "host": "127.0.0.1",
            "port": 19021,
            "repairs": [["systemctl", "restart", "openclaw-yangzai-admin.service"]],
        },
        {
            "id": "wechat2rss",
            "kind": "tcp",
            "label": "Wechat2RSS",
            "host": "127.0.0.1",
            "port": 18080,
            "repairs": [["bash", "-lc", "cd /opt/wechat2rss && docker compose up -d"]],
        },
    ]


def get_targets(env_map: dict[str, str]) -> list[dict[str, Any]]:
    raw = env_map.get("SUPERVISOR_TARGETS_JSON", "").strip()
    if not raw:
        return default_targets()
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise SystemExit("SUPERVISOR_TARGETS_JSON must be a JSON array")
    return payload


def evaluate_target(target: dict[str, Any]) -> dict[str, Any]:
    kind = target.get("kind", "").strip().lower()
    label = str(target.get("label", target.get("id", ""))).strip() or "unnamed target"
    result = {
        "id": str(target.get("id", "")).strip(),
        "label": label,
        "kind": kind,
        "ok": False,
        "detail": "",
        "repair_attempted": False,
        "repair_ok": False,
        "repair_steps": [],
    }
    if kind == "systemd":
        unit = str(target.get("unit", "")).strip()
        snapshot = systemd_snapshot(unit)
        result["unit"] = unit
        result["detail"] = f"active={snapshot['active']} enabled={snapshot['enabled']}"
        ok = snapshot["active"] == "active"
        if target.get("require_enabled", False):
            ok = ok and snapshot["enabled"] == "enabled"
        result["ok"] = ok
        return result
    if kind == "tcp":
        host = str(target.get("host", "127.0.0.1")).strip()
        port = int(target.get("port", 0))
        ok, detail = check_tcp(host, port)
        result["host"] = host
        result["port"] = port
        result["ok"] = ok
        result["detail"] = detail
        return result
    raise RuntimeError(f"unsupported target kind: {kind}")


def attempt_repairs(target: dict[str, Any]) -> list[dict[str, str]]:
    steps: list[dict[str, str]] = []
    for command in target.get("repairs", []):
        if isinstance(command, list):
            proc = run_command([str(part) for part in command], check=False)
            rendered = " ".join(str(part) for part in command)
        else:
            rendered = str(command)
            proc = run_shell(rendered, check=False)
        steps.append({
            "command": rendered,
            "returncode": str(proc.returncode),
            "detail": (proc.stderr or proc.stdout).strip(),
        })
        if proc.returncode == 0:
            return steps
    return steps


def run_checks(env_map: dict[str, str], *, autoheal: bool) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for target in get_targets(env_map):
        result = evaluate_target(target)
        if not result["ok"] and autoheal and target.get("repairs"):
            result["repair_attempted"] = True
            result["repair_steps"] = attempt_repairs(target)
            repaired = evaluate_target(target)
            result["ok"] = repaired["ok"]
            result["detail"] = repaired["detail"]
            result["repair_ok"] = repaired["ok"]
        results.append(result)
    return results


def unhealthy_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in results if not item.get("ok", False)]


def utc_now_text() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")


def delivery_openclaw_args(env_map: dict[str, str]) -> list[str]:
    args = ["openclaw"]
    profile = env_map.get("DELIVERY_PROFILE", DEFAULT_ENV["DELIVERY_PROFILE"]).strip()
    if profile:
        args.extend(["--profile", profile])
    return args


def push_text(text: str, env_map: dict[str, str]) -> None:
    target = env_map.get("DELIVERY_TARGET", "").strip()
    if not target:
        raise SystemExit("DELIVERY_TARGET not configured")
    channel = env_map.get("DELIVERY_CHANNEL", DEFAULT_ENV["DELIVERY_CHANNEL"]).strip()
    run_command([
        *delivery_openclaw_args(env_map),
        "message",
        "send",
        "--channel",
        channel,
        "--target",
        target,
        "--message",
        text,
    ])


def render_notification(kind: str, env_map: dict[str, str], results: list[dict[str, Any]]) -> str:
    name = env_map.get("SUPERVISOR_NAME", DEFAULT_ENV["SUPERVISOR_NAME"]).strip()
    lines = [f"【{name}巡检】"]
    lines.append(f"时间：{utc_now_text()}")
    if kind == "recovered":
        lines.append("状态：已恢复")
        lines.append("以下项目已恢复正常：")
        items = [item for item in results if item.get("ok", False)]
    elif kind == "healthy":
        lines.append("状态：全部正常")
        items = results
    else:
        lines.append("状态：发现异常")
        items = unhealthy_results(results)
    for index, item in enumerate(items, start=1):
        lines.append("")
        lines.append(f"{index}. {item['label']}")
        lines.append(f"结果：{'正常' if item.get('ok') else '异常'}")
        lines.append(f"详情：{item.get('detail', '')}")
        if item.get("repair_attempted"):
            lines.append(f"自动处理：{'已恢复' if item.get('repair_ok') else '已尝试但仍异常'}")
    return "\n".join(lines).strip()


def should_notify(env_map: dict[str, str], state: dict[str, Any], results: list[dict[str, Any]], force_notify: bool) -> tuple[bool, str]:
    if force_notify:
        return True, "healthy" if not unhealthy_results(results) else "alert"
    prev_status = str(state.get("overall_status", "unknown"))
    remind_minutes = parse_int_env(env_map, "ALERT_REMIND_MINUTES", 60, minimum=5, maximum=1440)
    last_alert_at = str(state.get("last_alert_at", "")).strip()
    unhealthy = unhealthy_results(results)
    if not unhealthy:
        if prev_status == "unhealthy":
            return True, "recovered"
        return False, "healthy"
    if prev_status != "unhealthy":
        return True, "alert"
    if not last_alert_at:
        return True, "alert"
    try:
        last_dt = datetime.fromisoformat(last_alert_at)
    except ValueError:
        return True, "alert"
    delta_minutes = (datetime.now(timezone.utc) - last_dt.astimezone(timezone.utc)).total_seconds() / 60.0
    return delta_minutes >= remind_minutes, "alert"


def show_config(env_map: dict[str, str]) -> dict[str, Any]:
    return {
        "supervisor_name": env_map.get("SUPERVISOR_NAME", DEFAULT_ENV["SUPERVISOR_NAME"]),
        "delivery_profile": env_map.get("DELIVERY_PROFILE", DEFAULT_ENV["DELIVERY_PROFILE"]),
        "delivery_channel": env_map.get("DELIVERY_CHANNEL", DEFAULT_ENV["DELIVERY_CHANNEL"]),
        "delivery_target": env_map.get("DELIVERY_TARGET", ""),
        "autoheal": parse_bool_env(env_map, "AUTOHEAL", True),
        "alert_remind_minutes": parse_int_env(env_map, "ALERT_REMIND_MINUTES", 60, minimum=5, maximum=1440),
        "watch_timer": current_watch_timer(),
        "targets": get_targets(env_map),
    }


def show_status(env_map: dict[str, str], state: dict[str, Any]) -> dict[str, Any]:
    results = run_checks(env_map, autoheal=False)
    return {
        "overall_status": "healthy" if not unhealthy_results(results) else "unhealthy",
        "checked_at": utc_now_text(),
        "watch_timer": timer_state(current_watch_timer()),
        "state": state,
        "results": results,
    }


def check_once(env_map: dict[str, str], *, force_notify: bool) -> dict[str, Any]:
    state = read_state()
    autoheal = parse_bool_env(env_map, "AUTOHEAL", True)
    results = run_checks(env_map, autoheal=autoheal)
    overall_status = "healthy" if not unhealthy_results(results) else "unhealthy"
    notify, notify_kind = should_notify(env_map, state, results, force_notify)
    if notify:
        push_text(render_notification(notify_kind, env_map, results), env_map)
        state["last_alert_at"] = datetime.now(timezone.utc).isoformat()
        state["last_notify_kind"] = notify_kind
    state["overall_status"] = overall_status
    state["last_checked_at"] = datetime.now(timezone.utc).isoformat()
    state["last_results"] = results
    write_state(state)
    return {
        "overall_status": overall_status,
        "checked_at": utc_now_text(),
        "notify_sent": notify,
        "notify_kind": notify_kind if notify else "",
        "results": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Supervisor for OpenClaw lobster services")
    parser.add_argument("--env-path", help="Use an explicit env file instead of SUPERVISOR_ENV_PATH")
    parser.add_argument("--show-config", action="store_true")
    parser.add_argument("--show-status", action="store_true")
    parser.add_argument("--check-once", action="store_true")
    parser.add_argument("--force-notify", action="store_true")
    parser.add_argument("--pause-watch", action="store_true")
    parser.add_argument("--resume-watch", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.env_path:
        os.environ["SUPERVISOR_ENV_PATH"] = args.env_path
    load_env_file(current_env_path())
    env_map = read_env_map(current_env_path())
    state = read_state()
    if args.show_config:
        print(json.dumps(show_config(env_map), ensure_ascii=False, indent=2))
        return 0
    if args.show_status:
        print(json.dumps(show_status(env_map, state), ensure_ascii=False, indent=2))
        return 0
    if args.pause_watch:
        print(json.dumps(control_timer(current_watch_timer(), "pause"), ensure_ascii=False, indent=2))
        return 0
    if args.resume_watch:
        print(json.dumps(control_timer(current_watch_timer(), "resume"), ensure_ascii=False, indent=2))
        return 0
    if args.check_once:
        print(json.dumps(check_once(env_map, force_notify=args.force_notify), ensure_ascii=False, indent=2))
        return 0
    raise SystemExit("no action specified")


if __name__ == "__main__":
    raise SystemExit(main())
