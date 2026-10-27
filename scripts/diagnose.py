"""Read-only health check. Exit nonzero when the existing bridge is unavailable."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fastmcp import Client
from fl_studio_mcp.server import build_server

async def run():
    async with Client(build_server()) as client:
        result = (await client.call_tool("fl_system_health", {})).data
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["ok"] else 1

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
