"""Read-only discovery of a locally running Style3D Studio MCP server.

This module intentionally does not infer a garment-generation tool schema.
Style3D must advertise its tools before an image or a paid request is sent.
"""

import json
import os
from urllib import error, request
from urllib.parse import urlsplit


DEFAULT_URL = "http://127.0.0.1:57281/mcp"
PROTOCOL_VERSION = "2025-03-26"


class Style3DUnavailable(RuntimeError):
    """The local Style3D MCP service is unavailable or malformed."""


def _local_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path != "/mcp" or not parsed.port):
        raise ValueError("Style3D MCP URL must be http://127.0.0.1:<port>/mcp")
    return url


def _decode_response(body, content_type):
    if "text/event-stream" in content_type:
        # Streamable HTTP may return a finite SSE response for a JSON-RPC call.
        for event in body.decode("utf-8").replace("\r\n", "\n").split("\n\n"):
            data = "\n".join(line[5:].strip() for line in event.splitlines()
                             if line.startswith("data:"))
            if data:
                message = json.loads(data)
                if isinstance(message, dict) and ("result" in message or "error" in message):
                    return message
        raise Style3DUnavailable("MCP response contained no JSON-RPC result")
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Style3DUnavailable("MCP response was not valid JSON") from exc


class Style3DMCPClient:
    def __init__(self, url=None, timeout=5):
        self.url = _local_url(url or os.environ.get("STYLE3D_MCP_URL", DEFAULT_URL))
        self.timeout = timeout
        self.session_id = None
        self.protocol_version = PROTOCOL_VERSION
        self._next_id = 1
        # This client only talks to loopback; never route it through HTTP_PROXY.
        self._opener = request.build_opener(request.ProxyHandler({}))

    def _post(self, message):
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
            headers["MCP-Protocol-Version"] = self.protocol_version
        data = json.dumps(message).encode("utf-8")
        req = request.Request(self.url, data=data, headers=headers, method="POST")
        try:
            with self._opener.open(req, timeout=self.timeout) as response:
                session_id = response.headers.get("Mcp-Session-Id")
                if session_id:
                    self.session_id = session_id
                body = response.read(4 * 1024 * 1024 + 1)
                if len(body) > 4 * 1024 * 1024:
                    raise Style3DUnavailable("MCP response exceeded 4 MiB")
                if "id" not in message:
                    return None
                result = _decode_response(body, response.headers.get("Content-Type", ""))
        except (error.URLError, TimeoutError, OSError) as exc:
            raise Style3DUnavailable(f"Cannot connect to local Style3D MCP: {exc}") from exc
        if not isinstance(result, dict) or result.get("id") != message["id"]:
            raise Style3DUnavailable("MCP response ID does not match request")
        if "error" in result:
            raise Style3DUnavailable(f"MCP error: {result['error']}")
        if "result" not in result:
            raise Style3DUnavailable("MCP response contained no result")
        return result["result"]

    def _request(self, method, params=None):
        request_id = self._next_id
        self._next_id += 1
        return self._post({"jsonrpc": "2.0", "id": request_id,
                           "method": method, "params": params or {}})

    def list_tools(self):
        initialized = self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "forma-style3d-probe", "version": "1.0"},
        })
        if not isinstance(initialized, dict) or not initialized.get("protocolVersion"):
            raise Style3DUnavailable("MCP initialization did not negotiate a protocol")
        self.protocol_version = initialized["protocolVersion"]
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = []
        cursor = None
        for _ in range(100):
            result = self._request("tools/list", {"cursor": cursor} if cursor else {})
            if not isinstance(result, dict) or not isinstance(result.get("tools"), list):
                raise Style3DUnavailable("MCP tools/list response was malformed")
            tools.extend(result["tools"])
            cursor = result.get("nextCursor")
            if not cursor:
                return tools
        raise Style3DUnavailable("MCP tools/list pagination exceeded 100 pages")
