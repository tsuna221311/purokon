"""Check Style3D Studio's local MCP service without generating or uploading."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.style3d_mcp import Style3DMCPClient, Style3DUnavailable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Local Style3D MCP URL (default: port 57281)")
    args = parser.parse_args()
    try:
        client = Style3DMCPClient(url=args.url)
        tools = client.list_tools()
    except (Style3DUnavailable, ValueError) as exc:
        print(json.dumps({"connected": False, "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"connected": True, "protocol_version": client.protocol_version,
                      "tools": [{"name": tool.get("name"),
                                 "description": tool.get("description", ""),
                                 "input_schema": tool.get("inputSchema")}
                                for tool in tools]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
