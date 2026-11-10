"""parse() reads JSON-RPC replies from plain JSON and from server-sent events. Run: python -m pytest"""

import json

import pytest

from tools.mcp_call import parse


def test_plain_json():
    assert parse(json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}), 1) == {"ok": True}


def test_sse_skips_other_messages():
    text = "\n".join([
        "event: message",
        'data: {"jsonrpc": "2.0", "method": "notifications/progress"}',
        'data: {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}',
    ])
    assert parse(text, 1) == {"tools": []}


def test_error_exits():
    with pytest.raises(SystemExit):
        parse(json.dumps({"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "bad"}}), 1)


def test_notification_has_no_reply():
    assert parse("", None) is None
