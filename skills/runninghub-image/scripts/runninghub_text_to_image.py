#!/usr/bin/env python3
"""Submit and poll a RunningHub text-to-image task."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_BASE_URL = "https://www.runninghub.cn/openapi/v2"
DEFAULT_MODEL = "rhart-image-n-g31-flash"
VALID_RESOLUTIONS = {"1k", "2k", "4k"}


def load_env_file(env_path: Optional[str]) -> None:
    if not env_path:
        return
    path = Path(env_path)
    if not path.exists():
        raise FileNotFoundError(f"env file not found: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def build_headers(api_key: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {exc}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON response: {body[:500]}") from exc


def extract_image_url(result: Dict[str, Any]) -> Optional[str]:
    results = result.get("results") or []
    if not isinstance(results, list):
        return None
    for item in results:
        if isinstance(item, dict) and item.get("url"):
            return str(item["url"])
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RunningHub text-to-image helper")
    parser.add_argument("--prompt", help="Prompt text for image generation")
    parser.add_argument("--task-id", default=None, help="Existing RunningHub task id to query instead of submitting a new task")
    parser.add_argument("--aspect-ratio", default=None, help="Optional aspect ratio such as 16:9")
    parser.add_argument("--resolution", default="1k", help="One of 1k, 2k, 4k")
    parser.add_argument("--timeout-seconds", type=int, default=180, help="Polling timeout in seconds")
    parser.add_argument("--poll-interval", type=float, default=3.0, help="Polling interval in seconds")
    parser.add_argument("--env-path", default=None, help="Optional env file to load before reading env vars")
    parser.add_argument("--json", action="store_true", help="Emit JSON result")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.prompt and not args.task_id:
        raise SystemExit("either --prompt or --task-id is required")
    if args.prompt and args.task_id:
        raise SystemExit("use either --prompt or --task-id, not both")
    if args.resolution not in VALID_RESOLUTIONS:
        raise SystemExit(f"unsupported resolution: {args.resolution}")

    load_env_file(args.env_path)

    api_key = os.environ.get("WRITER_IMAGE_API_KEY") or os.environ.get("RUNNINGHUB_API_KEY")
    if not api_key:
        raise SystemExit("missing WRITER_IMAGE_API_KEY or RUNNINGHUB_API_KEY")

    base_url = (os.environ.get("WRITER_IMAGE_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("WRITER_IMAGE_MODEL") or DEFAULT_MODEL
    submit_url = f"{base_url}/{model}/text-to-image"
    query_url = f"{base_url}/query"
    headers = build_headers(api_key)

    if args.task_id:
        task_id = args.task_id
        final_result = post_json(query_url, {"taskId": task_id}, headers)
    else:
        submit_payload = {
            "prompt": args.prompt,
            "resolution": args.resolution,
        }
        if args.aspect_ratio:
            submit_payload["aspectRatio"] = args.aspect_ratio

        submitted = post_json(submit_url, submit_payload, headers)
        task_id = submitted.get("taskId")
        if not task_id:
            raise SystemExit(f"submission returned no taskId: {submitted}")
        final_result = dict(submitted)

    started_at = time.time()

    while True:
        status = str(final_result.get("status") or "").upper()
        if status in {"SUCCESS", "FAILED"}:
            break
        elapsed = time.time() - started_at
        if elapsed >= args.timeout_seconds:
            final_result["status"] = status or "TIMEOUT"
            final_result["timedOut"] = True
            break
        time.sleep(max(args.poll_interval, 0.5))
        final_result = post_json(query_url, {"taskId": task_id}, headers)

    image_url = extract_image_url(final_result)
    output = {
        "taskId": task_id,
        "status": final_result.get("status"),
        "errorCode": final_result.get("errorCode") or "",
        "errorMessage": final_result.get("errorMessage") or "",
        "timedOut": bool(final_result.get("timedOut")),
        "imageUrl": image_url,
        "results": final_result.get("results"),
        "usage": final_result.get("usage"),
        "raw": final_result,
    }

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"taskId: {task_id}")
        print(f"status: {output['status']}")
        if image_url:
            print(f"imageUrl: {image_url}")
        if output["errorMessage"]:
            print(f"errorMessage: {output['errorMessage']}")

    if str(output["status"]).upper() != "SUCCESS":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
