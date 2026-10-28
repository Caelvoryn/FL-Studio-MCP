import asyncio
import copy
import json
import multiprocessing
import sys
import types
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastmcp import Client

from fl_studio_mcp import pianoroll, safety
from fl_studio_mcp.pyscript_gen import render_apply_script, render_quantize_script
from fl_studio_mcp.workflow import Journal, WorkflowError, audio_integrity, compare_audio, copy_exclusive, mutation_lock


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("FLSTUDIO_MCP_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(safety, "_DIR", tmp_path / "safety")
    monkeypatch.setattr(safety, "_PATH", tmp_path / "safety" / "log.jsonl")
    monkeypatch.setattr(safety, "_log", safety.ChangeLog())
    monkeypatch.setattr(safety, "_dry_run", False)


def test_backup_restore_and_overwrite(tmp_path):
    a, b, restored = [tmp_path / x for x in ("a.flp", "b.flp", "restored.flp")]
    a.write_bytes(b"FLhd" + bytes(range(255)))
    assert copy_exclusive(a, b)["verified"]
    with pytest.raises(WorkflowError, match="already exists"):
        copy_exclusive(a, b)
    copy_exclusive(b, restored)
    assert a.read_bytes() == restored.read_bytes()
    with pytest.raises(WorkflowError):
        copy_exclusive(tmp_path / "missing", b)


def test_journal_idempotency_stale_and_recovery(tmp_path):
    output = tmp_path / "output"
    calls = []
    def action():
        calls.append(1)
        output.write_text("verified")
        return {"ok": True}
    verify = lambda r: output.exists()
    assert Journal("test").step("save", {"v": 1}, action, verify)["ok"]
    assert Journal("test").step("save", {"v": 1}, action, verify)["cached"]
    assert calls == [1]
    with pytest.raises(WorkflowError) as exc:
        Journal("test").step("save", {"v": 2}, action, verify)
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"
    output.unlink()
    with pytest.raises(WorkflowError) as exc:
        Journal("test").step("save", {"v": 1}, action, verify)
    assert exc.value.code == "STALE_EVIDENCE"
    def fail():
        raise TimeoutError("blocked dialog")
    with pytest.raises(TimeoutError):
        Journal("interrupted").step("gui", {}, fail, verify)
    with pytest.raises(WorkflowError) as exc:
        Journal("interrupted").step("gui", {}, action, verify)
    assert exc.value.code == "RECOVERY_REQUIRED" and calls == [1]


def _try_lock(queue):
    try:
        with mutation_lock(.15):
            queue.put("acquired")
    except WorkflowError as exc:
        queue.put(exc.code)


def test_cross_process_lock_and_release():
    ctx = multiprocessing.get_context("spawn")
    queue = ctx.Queue()
    with mutation_lock():
        proc = ctx.Process(target=_try_lock, args=(queue,))
        proc.start()
        assert queue.get(timeout=15) == "BUSY"
        proc.join(10)
        assert proc.exitcode == 0
    with mutation_lock(.1):
        pass


def test_audio_rejects_bad_outputs_and_compares_pcm(tmp_path):
    sr = 8000
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    samples = .1 * np.sin(2 * np.pi * 440 * np.arange(sr) / sr)
    sf.write(a, samples, sr, subtype="FLOAT")
    sf.write(b, samples, sr, subtype="PCM_24")
    assert audio_integrity(a)["duration_seconds"] == 1
    assert compare_audio(a, a)["classification"] == "exact_pcm"
    assert compare_audio(a, b)["classification"] == "numeric_difference"
    with pytest.raises(WorkflowError) as exc:
        audio_integrity(a, 2, 3)
    assert exc.value.code == "AUDIO_DURATION"
    sf.write(b, np.zeros(sr), sr)
    with pytest.raises(WorkflowError) as exc:
        audio_integrity(b)
    assert exc.value.code == "AUDIO_SILENT"
    sf.write(b, np.full(sr, np.nan), sr, subtype="FLOAT")
    with pytest.raises(WorkflowError) as exc:
        audio_integrity(b)
    assert exc.value.code == "AUDIO_NONFINITE"
    b.write_bytes(b"not a wave")
    with pytest.raises(WorkflowError) as exc:
        audio_integrity(b)
    assert exc.value.code == "AUDIO_DECODE"


def test_quantize_executes_and_preserves_extended_note_properties(monkeypatch):
    class Note:
        def __init__(self):
            self.number, self.time, self.length, self.velocity = 60, 13, 29, .7
            self.release, self.color, self.pan, self.slide, self.modX = .2, 5, .3, True, .8
        def clone(self):
            return copy.deepcopy(self)
    class Score:
        PPQ = 96
        def __init__(self): self.notes = [Note()]
        @property
        def noteCount(self): return len(self.notes)
        def getNote(self, i): return self.notes[i]
        def clearNotes(self, *args): self.notes.clear()
        def addNote(self, note): self.notes.append(note)
    score = Score()
    original = vars(score.notes[0]).copy()
    monkeypatch.setitem(sys.modules, "flpianoroll", types.SimpleNamespace(Note=Note, score=score))
    exec(compile(render_quantize_script(.0625, True), "generated.pyscript", "exec"), {})
    result = vars(score.notes[0])
    assert result["time"] == 24 and result["length"] == 24
    assert {k: v for k, v in result.items() if k not in ("time", "length")} == {k: v for k, v in original.items() if k not in ("time", "length")}


@pytest.mark.parametrize("grid", [0, -1, float("nan"), float("inf")])
def test_quantize_invalid(grid):
    with pytest.raises(ValueError): render_quantize_script(grid)


def test_trigger_failure_is_not_execution_success(monkeypatch):
    from fl_studio_mcp import pyscript_trigger
    monkeypatch.setattr(pianoroll, "write_apply_script", lambda *a: "script")
    monkeypatch.setattr(pyscript_trigger, "trigger_run_last_script", lambda: {"sent_hotkey": False, "focused": False})
    res = pianoroll.apply_notes([], trigger=True)
    assert not res["verified"] and not res["triggered"]
    assert res["status"] == "script_prepared_not_verified"


def test_windows_focus_loss_never_sends_keys(monkeypatch):
    from fl_studio_mcp import pyscript_trigger
    import pyautogui
    calls = []
    monkeypatch.setattr(pyscript_trigger, "find_fl_hwnd", lambda: 123)
    monkeypatch.setattr(pyscript_trigger, "_windows_api", lambda: (types.SimpleNamespace(IsWindowEnabled=lambda h: True), None))
    monkeypatch.setattr(pyscript_trigger, "force_focus", lambda h: False)
    monkeypatch.setattr(pyautogui, "hotkey", lambda *args: calls.append(args))
    result = pyscript_trigger._trigger_windows(settle=0)
    assert not result["sent_hotkey"] and not calls


def test_failed_rollback_retains_recovery_journal():
    safety._log.append({"tool": "test", "scope": "plugin_param:0:-1:0",
                        "restore": {"command": "plugin_set_param", "params": {"value": .8}}})
    class Bridge:
        def call(self, cmd, args): return {"v": .6}
    assert not safety.rollback_last_change(Bridge())["verified"]
    assert len(safety._log.recent()) == 1


def test_partial_group_failure_keeps_all_restore_values():
    class Bridge:
        def call(self, cmd, args):
            if cmd == "plugin_set_param": raise TimeoutError("blocked plugin window")
            return {"v": .8}
    write = {"snap_scope": "plugin_param:0:-1:0", "command": "plugin_set_param", "params": {"value": .6},
             "restore": lambda b: {"command": "plugin_set_param", "params": {"value": b["v"]}}}
    result = safety.safe_write_group(Bridge(), tool="group", scope="plugin", writes=[write, write])
    assert not result["ok"]
    assert len(safety._log.recent()[0]["restores"]) == 2


def test_native_parser_rejects_truncated_input(tmp_path):
    from fl_studio_mcp.native import inspect
    path = tmp_path / "bad.flp"
    path.write_bytes(b"FLhd")
    with pytest.raises(ValueError, match="truncated"):
        inspect(path)


@pytest.mark.parametrize("failure", ["ignored", "read_timeout", "write_timeout", "ok"])
def test_safe_write_requires_independent_read_and_keeps_recovery(failure):
    class Bridge:
        changed = False
        def call(self, command, params):
            if command == "plugin_set_param":
                if failure == "write_timeout": raise TimeoutError("write timed out")
                self.changed = True
                return {"v": .6}  # optimistic echo does not prove anything
            if self.changed and failure == "read_timeout": raise TimeoutError("read timed out")
            return {"v": .6 if self.changed and failure == "ok" else .8}
    result = safety.safe_write(Bridge(), tool="param", scope="plugin_param:0:-1:0", command="plugin_set_param",
        params={"value": .6}, build_restore=lambda before: {"command": "plugin_set_param", "params": {"value": before["v"]}})
    assert result["ok"] == (failure == "ok")
    assert result["verified"] == (failure == "ok")
    assert safety.get_changelog().recent()[0]["restore"]["params"]["value"] == .8


def test_mcp_schema_new_tools_and_checkpoint_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("FLSTUDIO_MCP_ENABLE_LEGACY_WRITES", "1")
    from fl_studio_mcp.server import build_server
    async def run():
        async with Client(build_server()) as client:
            tools = await client.list_tools()
            assert len(tools) == 96  # three bounded fallbacks promoted after independent 2026-10-29 host acceptance
            assert {"fl_ui_observe", "fl_ui_act"} <= {t.name for t in tools}
            source, dest = tmp_path / "source.flp", tmp_path / "dest.flp"
            source.write_bytes(b"FLhd-test")
            args = {"source": str(source), "destination": str(dest), "job_id": "mcp"}
            result = (await client.call_tool("fl_project_checkpoint", args)).data
            assert result["verified"] and dest.read_bytes() == source.read_bytes()
            assert (await client.call_tool("fl_project_checkpoint", args)).data["cached"]
            missing = (await client.call_tool("fl_verify_render", {"path": str(tmp_path / "missing.wav")})).data
            assert not missing["ok"] and missing["error"]["code"] == "FILE_NOT_FOUND"
    asyncio.run(run())
