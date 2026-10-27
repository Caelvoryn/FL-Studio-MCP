"""Read-only stdio MCP acceptance against actual local FLP and audio files."""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport


async def run(args):
    script = Path(__file__).with_name("run_server.py")
    results = []
    async with Client(PythonStdioTransport(script, env=dict(os.environ), python_cmd=sys.executable), timeout=20, init_timeout=15) as client:
        tools = await client.list_tools()
        async def call(name, inputs):
            print("Checking " + name, flush=True)
            value = (await client.call_tool(name, inputs, timeout=20)).data
            results.append({"tool": name, "input": inputs, "output": value})
            return value
        health = await call("fl_system_health", {})
        assert health["ok"], "Actual FL connection failed"
        project = await call("fl_inspect_native_project", {"path": args.project})
        assert project["ok"], "Native project could not be inspected"
        state = project["saved_state"]
        assert state["bpm"] == args.bpm
        assert health["connection"]["project"]["tempo_bpm"] == args.bpm
        assert sum(len(p["notes"]) for p in state["patterns"].values()) == args.notes
        for audio in (args.first, args.second):
            verified = await call("fl_verify_render", {"path": audio, "minimum_seconds": 60, "maximum_seconds": 90})
            assert verified["ok"] and verified["verified"]
        comparison = await call("fl_compare_renders", {"first": args.first, "second": args.second})
        assert comparison["classification"] == "exact_pcm"
    # A new stdio subprocess must reconnect to the same unmodified bridge.
    async with Client(PythonStdioTransport(script, env=dict(os.environ), python_cmd=sys.executable), timeout=20, init_timeout=15) as client:
        restarted = (await client.call_tool("fl_system_health", {})).data
        assert restarted["ok"]
    report = {"passed": True, "registered_tools": len(tools), "results": results,
              "stdio_restart_reconnected": restarted["ok"], "model_listened": False,
              "scope": "These specific inputs only. Does not validate every inherited tool or generic GUI CRUD"}
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"passed": True, "tools": len(tools), "audio_comparison": comparison["classification"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--first", required=True)
    parser.add_argument("--second", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--bpm", type=float, default=128)
    parser.add_argument("--notes", type=int, default=809)
    asyncio.run(run(parser.parse_args()))
