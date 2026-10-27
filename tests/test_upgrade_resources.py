import asyncio
from pathlib import Path

from fastmcp import Client, FastMCP
from fl_studio_mcp.music import plugin_library, preset_library, resource_paths
from fl_studio_mcp.tools import chains


def test_redirected_documents(monkeypatch, tmp_path):
    docs = tmp_path / "文档"
    db = docs / "Image-Line/FL Studio/Presets/Plugin database/Installed"
    db.mkdir(parents=True)
    monkeypatch.delenv("FLSTUDIO_MCP_PLUGIN_DB", raising=False)
    monkeypatch.setattr(resource_paths, "documents_dirs", lambda: [docs])
    assert Path(plugin_library.find_plugin_db()) == db


def test_typed_and_legacy_presets_keep_duplicate_files(tmp_path):
    paths = ["Generators/Sytrus/Bass/Deep.fst", "Generators/Sytrus/Lead/Deep.fst",
             "Effects/EQ/Neutral.fst", "Legacy/Simple.fst"]
    for rel in paths:
        p = tmp_path / "Plugin presets" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fixture")
    records = preset_library.preset_records(tmp_path)
    assert len(records) == 4
    assert {r["plugin"] for r in records} == {"Sytrus", "EQ", "Legacy"}
    assert {r["category"] for r in records if r["plugin"] == "Sytrus"} == {"Bass", "Lead"}
    assert all(Path(r["path"]).is_file() for r in records)
    assert preset_library.plugin_presets(tmp_path)["Sytrus"] == ["Deep"]


def test_factory_and_user_merged(monkeypatch, tmp_path):
    user, factory = tmp_path / "User", tmp_path / "Factory"
    for root in (user, factory):
        p = root / "Plugin presets/Generators/Sytrus" / (root.name + ".fst")
        p.parent.mkdir(parents=True)
        p.write_bytes(b"fixture")
    monkeypatch.setattr(preset_library, "fl_preset_roots", lambda: [str(user), str(factory)])
    monkeypatch.setattr(preset_library, "find_serum_presets", lambda: None)
    result = preset_library.list_presets("Sytrus")
    assert result["presets"]["Sytrus"] == ["Factory", "User"]
    assert len(result["records"]) == 2


def test_setup_chain_tool_is_read_only(monkeypatch):
    class Bridge:
        def __init__(self):
            self.calls = []

        def call(self, cmd, args):
            self.calls.append((cmd, args))
            return {"slots": []}

    bridge = Bridge()
    monkeypatch.setattr(chains, "get_bridge", lambda: bridge)
    monkeypatch.setattr(plugin_library, "list_installed", lambda: {"found": False})

    async def run():
        mcp = FastMCP("regression")
        chains.register(mcp)
        async with Client(mcp) as client:
            result = await client.call_tool("fl_setup_chain", {"track": 0, "chain_type": "master"})
            data = result.data
            assert data["ok"] and not data["executed"]
            assert data["mode"] == "plan_only"
            assert data["configure_now"] == [] and data["missing_roles"]
    asyncio.run(run())
    assert len(bridge.calls) == 1
