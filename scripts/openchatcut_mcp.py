#!/usr/bin/env python3
"""Discover and call the authenticated local OpenChatCut MCP endpoint."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests


APP_CANDIDATES = (
    Path("/Applications/OpenChatCut.app"),
    Path.home() / "Applications/OpenChatCut.app",
)
TOKEN_PATH = Path.home() / "Library/Application Support/openchatcut/external-mcp-token"
MCP_PATH = "/api/external-mcp/mcp"
HTTP = requests.Session()
HTTP.trust_env = False
MCP_SESSION_ID: str | None = None


def external_mcp_token() -> str:
    configured = os.environ.get("OPENCHATCUT_MCP_TOKEN", "").strip()
    if configured:
        return configured
    try:
        saved = TOKEN_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        saved = ""
    if saved:
        return saved
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    descriptor = os.open(TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(token)
    return token


def request_headers() -> dict[str, str]:
    return {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {external_mcp_token()}",
    }


def candidate_ports() -> list[int]:
    result = subprocess.run(
        ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-c", "OpenChatCut", "-Fn"],
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    ports: list[int] = []
    for line in result.stdout.splitlines():
        if line.startswith("n127.0.0.1:") or line.startswith("nlocalhost:"):
            try:
                ports.append(int(line.rsplit(":", 1)[1]))
            except ValueError:
                pass
    return list(dict.fromkeys(ports))


def parse_sse(response: requests.Response) -> dict[str, Any]:
    response.raise_for_status()
    data_lines = [
        line[5:].strip()
        for line in response.text.split("\n")
        if line.startswith("data:")
    ]
    if not data_lines:
        return response.json()
    return json.loads("\n".join(data_lines))


def rpc(port: int, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    global MCP_SESSION_ID
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    headers = request_headers()
    if method != "initialize" and MCP_SESSION_ID:
        headers["Mcp-Session-Id"] = MCP_SESSION_ID
    response = HTTP.post(
        f"http://127.0.0.1:{port}{MCP_PATH}",
        headers=headers,
        json=payload,
        timeout=120,
    )
    if method == "initialize":
        MCP_SESSION_ID = response.headers.get("Mcp-Session-Id")
    parsed = parse_sse(response)
    if "error" in parsed:
        raise RuntimeError(json.dumps(parsed["error"], ensure_ascii=False))
    return parsed


def initialize(port: int) -> dict[str, Any]:
    return rpc(
        port,
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "make-book-video", "version": "1.0"},
        },
    )


def discover(launch: bool = False, timeout: float = 45) -> tuple[int, dict[str, Any]]:
    deadline = time.time() + timeout
    launched = False
    while True:
        for port in candidate_ports():
            try:
                result = initialize(port)
                info = result.get("result", {}).get("serverInfo", {})
                if str(info.get("name", "")).lower() == "openchatcut":
                    return port, info
            except Exception:
                continue
        if not launch or time.time() >= deadline:
            break
        if not launched:
            app_path = next((path for path in APP_CANDIDATES if path.exists()), None)
            if app_path is None:
                searched = "、".join(str(path) for path in APP_CANDIDATES)
                raise RuntimeError(f"OpenChatCut 未安装；已检查：{searched}")
            executable = app_path / "Contents/MacOS/OpenChatCut"
            environment = os.environ.copy()
            environment["OPENCHATCUT_MCP_TOKEN"] = external_mcp_token()
            subprocess.Popen(
                [str(executable)],
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            launched = True
        time.sleep(0.5)
    raise RuntimeError("未发现可用的 OpenChatCut 本地 MCP；请确认应用已安装且可启动")


def tool_call(port: int, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = rpc(port, "tools/call", {"name": name, "arguments": arguments})
    tool_result = result.get("result", {})
    if tool_result.get("isError"):
        raise RuntimeError(json.dumps(tool_result, ensure_ascii=False))
    return tool_result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-launch", action="store_true", help="未运行时不自动启动 OpenChatCut"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("list-tools")
    call = sub.add_parser("call")
    call.add_argument("tool")
    group = call.add_mutually_exclusive_group()
    group.add_argument("--args-json", default="{}")
    group.add_argument("--args-file", type=Path)
    args = parser.parse_args()
    try:
        port, info = discover(launch=not args.no_launch)
        if args.command == "status":
            output = {
                "status": "ready",
                "baseUrl": f"http://127.0.0.1:{port}",
                "mcpUrl": f"http://127.0.0.1:{port}{MCP_PATH}",
                "serverInfo": info,
            }
        elif args.command == "list-tools":
            output = rpc(port, "tools/list").get("result", {})
        else:
            raw = (
                args.args_file.read_text(encoding="utf-8")
                if args.args_file
                else args.args_json
            )
            output = tool_call(port, args.tool, json.loads(raw))
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(
            json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
