import asyncio
import json
import struct
import time
from types import SimpleNamespace

import pytest
from fastmcp import Client

from fl_studio_mcp import safety
from fl_studio_mcp.desktop import FLDesktop, semantic_state, wait_for, guard_pattern_overlap
from fl_studio_mcp.native import inspect
from fl_studio_mcp.workflow import WorkflowError


def test_cross_lane_pattern_overlap_is_rejected_but_adjacent_copy_allowed():
    clips = [{"source_kind": "pattern", "position_ticks": 0, "length_ticks": 15360, "track": 1}]
    with pytest.raises(WorkflowError) as exc:
        guard_pattern_overlap(clips, 0, "copy", 6144)
    assert exc.value.code == "PLAYLIST_OVERLAP_RISK"
    guard_pattern_overlap(clips, 0, "copy", 15360)
    guard_pattern_overlap(clips, 0, "move", 0)
    guard_pattern_overlap(clips, 0, "delete")


def test_overlap_guard_uses_actual_instrument_channels():
    clips = [dict(source_kind='pattern', source_id=1, position_ticks=0, length_ticks=100, track=1),
             dict(source_kind='pattern', source_id=2, position_ticks=100, length_ticks=100, track=2)]
    patterns = {1: {'notes': [{'channel': 0}]}, 2: {'notes': [{'channel': 1}]}}
    guard_pattern_overlap(clips, 0, 'move', 100, patterns=patterns)
    patterns[2]['notes'][0]['channel'] = 0
    with pytest.raises(WorkflowError):
        guard_pattern_overlap(clips, 0, 'move', 100, patterns=patterns)


def minimal_flp(path, item=20481, track=499, start=0xFFFFFFFF, end=0xFFFFFFFF):
    clip = bytearray(88)
    struct.pack_into("<IHHIHH", clip, 0, 384, 20480, item, 768, track, 0)
    struct.pack_into("<II", clip, 24, start, end)
    payload = bytes([156]) + struct.pack("<I", 128000) + bytes([233, 88]) + bytes(clip)
    path.write_bytes(struct.pack("<4sIHHH4sI", b"FLhd", 6, 0, 8, 96, b"FLdt", len(payload)) + payload)
    return path


def test_pattern_offsets_do_not_leak_nan_to_mcp(tmp_path):
    state = inspect(minimal_flp(tmp_path / "full.flp"))
    clip = state["playlist"][0]
    assert clip["track"] == 1 and clip["source_id"] == 1
    assert clip["start_offset"] is None and clip["end_offset"] is None
    assert clip["start_offset_bits"] == 0xFFFFFFFF
    json.dumps(state, allow_nan=False)


def test_cropped_pattern_offsets_are_integer_ticks(tmp_path):
    state = inspect(minimal_flp(tmp_path / "crop.flp", track=496, start=0, end=3072))
    clip = state["playlist"][0]
    assert clip["track"] == 4 and clip["end_offset"] == 3072
    assert clip["end_offset_bits"] == 3072


def test_channel_float_offsets_remain_distinct(tmp_path):
    minus_one = struct.unpack("<I", struct.pack("<f", -1.))[0]
    clip = inspect(minimal_flp(tmp_path / "automation.flp", item=7, start=minus_one, end=minus_one))["playlist"][0]
    assert clip["source_kind"] == "channel" and clip["source_id"] == 7
    assert clip["start_offset"] == -1.


def test_semantic_comparison_never_ignores_real_mixer_changes(tmp_path):
    a = inspect(minimal_flp(tmp_path / "a.flp"))
    b = inspect(tmp_path / "a.flp")
    a["mixer_event_hashes"] = [{"event": 225, "sha256": "9051"}]
    b["mixer_event_hashes"] = [{"event": 225, "sha256": "9062"}]
    assert semantic_state(a) != semantic_state(b)


def test_semantic_comparison_ignores_only_opaque_clip_instance_hash(tmp_path):
    a = inspect(minimal_flp(tmp_path / "a.flp"))
    b = inspect(tmp_path / "a.flp")
    b["playlist"][0]["event_record_sha256"] = "regenerated-instance-id"
    assert semantic_state(a) == semantic_state(b)
    b["playlist"][0]["source_id"] = 2
    assert semantic_state(a) != semantic_state(b)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), 181])
def test_gui_wait_rejects_invalid_deadlines(timeout):
    with pytest.raises(WorkflowError) as exc:
        wait_for(lambda: False, timeout)
    assert exc.value.code == "INVALID_ARGUMENT"


def test_gui_wait_is_bounded():
    start = time.monotonic()
    with pytest.raises(WorkflowError) as exc:
        wait_for(lambda: False, .1, "blocked test dialog")
    assert exc.value.code == "GUI_TIMEOUT" and time.monotonic() - start < 1


def test_unknown_modal_and_title_change_refuse_before_keys():
    desktop = object.__new__(FLDesktop)
    desktop.main = SimpleNamespace(is_enabled=lambda: False)
    with pytest.raises(WorkflowError) as exc:
        desktop.focus("expected")
    assert exc.value.code == "GUI_BLOCKED"
    desktop.main = SimpleNamespace(is_enabled=lambda: True, window_text=lambda: "other project")
    with pytest.raises(WorkflowError) as exc:
        desktop.focus("expected")
    assert exc.value.code == "PROJECT_CHANGED"


def test_gui_save_cannot_overwrite_existing_file(tmp_path):
    desktop = object.__new__(FLDesktop)
    path = tmp_path / "original.flp"
    path.write_bytes(b"original")
    with pytest.raises(WorkflowError) as exc:
        desktop.save_as(path, "expected")
    assert exc.value.code == "OVERWRITE_REFUSED" and path.read_bytes() == b"original"


def test_project_save_rejects_mixer_preset_dialog_before_filename_write():
    desktop = object.__new__(FLDesktop)
    desktop.dialogs = lambda: [SimpleNamespace(handle=123)]
    combo = SimpleNamespace(exists=lambda timeout: True,
                            wrapper_object=lambda: SimpleNamespace(selected_text=lambda: "Mixer state (*.fst)"))
    ui = SimpleNamespace(child_window=lambda **kwargs: combo)
    desktop.uia = SimpleNamespace(window=lambda **kwargs: ui)
    with pytest.raises(WorkflowError) as exc:
        desktop.file_dialog("new-project.flp")
    assert exc.value.code == "GUI_WRONG_FILE_TYPE"


def test_plugin_stale_parameter_rejects_write_through_mcp(tmp_path, monkeypatch):
    from fl_studio_mcp.tools import plugin
    from fl_studio_mcp.server import build_server
    monkeypatch.setenv("FLSTUDIO_MCP_STATE_DIR", str(tmp_path / "state"))
    class Bridge:
        def __init__(self): self.calls = []
        def call(self, cmd, args):
            self.calls.append(cmd)
            return {"v": .8, "name": "actual parameter"}
    bridge = Bridge()
    monkeypatch.setattr(plugin, "get_bridge", lambda: bridge)
    async def run():
        async with Client(build_server()) as c:
            result = (await c.call_tool("fl_plugin_set_param", {"track": 0, "slot": -1, "param": 0, "value": .6, "expected_value": .7})).data
            assert not result["ok"] and result["error"]["code"] == "STALE_PARAMETER"
    asyncio.run(run())
    assert "plugin_set_param" not in bridge.calls
