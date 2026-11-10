"""Call the platform MCP server from a shell, for agents without MCP support (pi) and for humans.

  python tools/mcp_call.py                         # list tools, one line each
  python tools/mcp_call.py <tool> '{"arg": "..."}'  # call a tool, print its result

Needs DEEPSET_API_KEY. DEEPSET_MCP_URL overrides the server (default https://api.cloud.deepset.ai/mcp).
"""

import json
import os
import sys
import urllib.request

URL = os.environ.get("DEEPSET_MCP_URL", "https://api.cloud.deepset.ai/mcp")


def post(body: dict, session: str | None) -> tuple[dict | None, str | None]:
    headers = {
        "Authorization": f"Bearer {os.environ['DEEPSET_API_KEY']}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session:
        headers["Mcp-Session-Id"] = session
    req = urllib.request.Request(URL, json.dumps(body).encode(), headers)
    with urllib.request.urlopen(req, timeout=300) as resp:
        session = resp.headers.get("Mcp-Session-Id") or session
        text = resp.read().decode()
    return parse(text, body.get("id")), session


def parse(text: str, want_id) -> dict | None:
    """The JSON-RPC reply with id `want_id`, from a plain JSON body or a server-sent-events stream."""
    if want_id is None or not text.strip():
        return None
    chunks = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")] or [text]
    for chunk in chunks:
        msg = json.loads(chunk)
        if msg.get("id") == want_id:
            if "error" in msg:
                sys.exit(f"error: {msg['error']}")
            return msg["result"]
    sys.exit(f"no reply with id {want_id}:\n{text[:2000]}")


def main(argv: list[str]) -> None:
    _, session = post({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "platform-cli", "version": "1"}}}, None)
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
    if not argv:
        tools, _ = post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, session)
        for tool in tools["tools"]:
            print(f"{tool['name']}: {(tool.get('description') or '').strip().splitlines()[0][:120]}")
        return
    args = json.loads(argv[1]) if len(argv) > 1 else {}
    result, _ = post({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": argv[0], "arguments": args}}, session)
    for item in result.get("content", []):
        print(item.get("text", json.dumps(item)))
    if result.get("isError"):
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
