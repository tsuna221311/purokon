"""The optional Style3D bridge must be safe and honest when unavailable."""

import io
import json
from email.message import Message

import pytest

from engine import style3d_mcp


class FakeResponse:
    def __init__(self, payload, content_type="application/json", session_id=None):
        self.buffer = io.BytesIO(payload.encode("utf-8"))
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        if session_id:
            self.headers["Mcp-Session-Id"] = session_id

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size):
        return self.buffer.read(size)


def test_discovery_handshake_session_pagination_and_no_generation(monkeypatch):
    calls = []

    def fake_open(req, timeout):
        message = json.loads(req.data)
        calls.append((message, dict(req.headers)))
        if message["method"] == "initialize":
            return FakeResponse(json.dumps({"jsonrpc": "2.0", "id": 1,
                                            "result": {"protocolVersion": "2025-03-26"}}),
                                session_id="session-test")
        if message["method"] == "notifications/initialized":
            return FakeResponse("")
        if message["id"] == 2:
            payload = {"jsonrpc": "2.0", "id": 2,
                       "result": {"tools": [{"name": "pattern_list"}], "nextCursor": "page2"}}
            return FakeResponse(f"event: message\ndata: {json.dumps(payload)}\n\n",
                                content_type="text/event-stream")
        return FakeResponse(json.dumps({"jsonrpc": "2.0", "id": 3,
                                        "result": {"tools": [{"name": "pattern_export"}]}}))

    client = style3d_mcp.Style3DMCPClient()
    monkeypatch.setattr(client._opener, "open", fake_open)
    tools = client.list_tools()
    assert [tool["name"] for tool in tools] == ["pattern_list", "pattern_export"]
    assert [message["method"] for message, _ in calls] == [
        "initialize", "notifications/initialized", "tools/list", "tools/list"]
    assert calls[2][1]["Mcp-session-id"] == "session-test"
    assert calls[3][0]["params"] == {"cursor": "page2"}


@pytest.mark.parametrize("url", [
    "http://example.com:57281/mcp", "http://localhost:57281/mcp",
    "https://127.0.0.1:57281/mcp", "http://127.0.0.1:57281/admin",
    "http://127.0.0.1:57281/mcp?secret=x",
])
def test_nonlocal_or_ambiguous_target_rejected(url):
    with pytest.raises(ValueError):
        style3d_mcp.Style3DMCPClient(url=url)


def test_wrong_request_id_is_not_treated_as_success(monkeypatch):
    client = style3d_mcp.Style3DMCPClient()
    monkeypatch.setattr(client._opener, "open", lambda *args, **kwargs: FakeResponse(
        '{"jsonrpc":"2.0","id":999,"result":{}}'))
    with pytest.raises(style3d_mcp.Style3DUnavailable, match="ID"):
        client.list_tools()
