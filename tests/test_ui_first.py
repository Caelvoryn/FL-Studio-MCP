"""Offline guard tests; not a substitute for real Windows acceptance."""
import hashlib
import json
import time
from types import SimpleNamespace

import pytest

from fl_studio_mcp import ui_first as ui
from fl_studio_mcp.workflow import WorkflowError, atomic_json


@pytest.mark.parametrize("point", [[float('nan'), .5], [float('inf'), .5], [-.1, 0], [1.1, 0], [0]])
def test_canvas_rejects_invalid_normalized_coordinates(point):
    with pytest.raises(WorkflowError):
        ui.normalized_point(point, SimpleNamespace(left=1, top=2, width=lambda: 100, height=lambda: 200))


def test_window_relative_coordinate_transform():
    rect = SimpleNamespace(left=200, top=100, width=lambda: 401, height=lambda: 201)
    assert ui.normalized_point([.5, .5], rect) == (400, 200)


def test_unexpected_observation_failure_is_structured(monkeypatch):
    from fl_studio_mcp.tools import desktop as module
    functions={}
    class Registry:
        def tool(self,**kwargs):
            def record(fn):functions[fn.__name__]=fn;return fn
            return record
    module.register(Registry())
    def fail():raise RuntimeError('UIA unavailable')
    monkeypatch.setattr(ui,'observe',fail)
    result=functions['fl_ui_observe']()
    assert result['ok'] is False and result['error']['code']=='UI_OBSERVATION_FAILED'


def test_unexpected_localization_failure_is_structured(monkeypatch):
    from fl_studio_mcp.tools import desktop as module
    functions={}
    class Registry:
        def tool(self,**kwargs):
            def record(fn):functions[fn.__name__]=fn;return fn
            return record
    module.register(Registry())
    def fail():raise RuntimeError('Native desktop unavailable')
    monkeypatch.setattr(module,'FLDesktop',fail)
    result=functions['fl_ui_locate_piano']()
    assert result['ok'] is False and result['error']['code']=='UI_LOCALIZATION_FAILED'


def test_calibrated_piano_targets_and_viewport_guard():
    rect = SimpleNamespace(left=938, top=177, width=lambda: 950, height=lambda: 760)
    grid = dict(tick_zero_x=78, tick_zero=0, pixels_per_tick=.5, pitch_zero_y=449,
                pitch_zero=72, pixels_per_semitone=18, grid_top=86, grid_bottom=614, grid_right=923)
    note = dict(tick=384, pitch=73, length_ticks=144)
    assert ui.normalized_point(ui.piano_point(grid,note,rect,'resize'),rect) == (938+340,177+431)
    assert ui.normalized_point(ui.piano_point(grid,dict(tick=24,pitch=76),rect,'draw'),rect) == (938+90,177+377)
    with pytest.raises(WorkflowError) as exc:
        ui.piano_point(grid,dict(tick=0,pitch=20),rect,'draw')
    assert exc.value.code == 'GUI_OUT_OF_VIEW'
    with pytest.raises(WorkflowError) as exc:
        ui.piano_point(grid,dict(tick=25,pitch=76),rect,'draw')
    assert exc.value.code == 'INSUFFICIENT_ZOOM'


def test_replay_returns_journal_without_opening_fl(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, 'state_dir', lambda: tmp_path)
    intent = hashlib.sha256(json.dumps(['abc', '123', 'click', [.1,.2], None, None, None, None], sort_keys=True).encode()).hexdigest()
    saved = dict(ok=False, phase='input_pending', intent_sha256=intent)
    atomic_json(tmp_path/'ui-operations'/'once.json', saved)
    monkeypatch.setattr(ui, 'FLDesktop', lambda: pytest.fail('Must not repeat uncertain input'))
    assert ui.act('abc','once','123','click',[.1,.2]) == saved
    with pytest.raises(WorkflowError) as exc:
        ui.act('abc','once','123','click',[.2,.2])
    assert exc.value.code == 'OPERATION_ID_CONFLICT'


def test_expired_observation_refuses_before_accessing_desktop(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, 'state_dir', lambda: tmp_path)
    atomic_json(tmp_path/'observations'/'old'/'observation.json', dict(time=time.time()-181))
    monkeypatch.setattr(ui, 'FLDesktop', lambda: pytest.fail('Expired view must not act'))
    with pytest.raises(WorkflowError) as exc:
        ui.act('old','once','123','click',[.1,.2])
    assert exc.value.code == 'OBSERVATION_EXPIRED'


@pytest.mark.parametrize('token,operation', [('../bad','ok'),('ok','../bad')])
def test_journal_paths_cannot_escape(token, operation):
    with pytest.raises(WorkflowError):
        ui.act(token,operation,'123','click',[.1,.2])


def test_ui_first_default_hides_background_music_writers(monkeypatch):
    import asyncio
    from fastmcp import Client
    from fl_studio_mcp.server import build_server
    monkeypatch.delenv('FLSTUDIO_MCP_ENABLE_LEGACY_WRITES', raising=False)
    async def check():
        async with Client(build_server()) as client:
            names = {t.name for t in await client.list_tools()}
            assert {'fl_ui_observe', 'fl_ui_act', 'fl_gui_save_as', 'fl_plugin_state'} <= names
            assert not {'fl_plugin_set_param', 'fl_write_piano_roll_notes', 'fl_arrange_new_pattern'} & names
    asyncio.run(check())


def test_existing_fl_foreground_does_not_inject_alt(monkeypatch):
    import ctypes
    from fl_studio_mcp import pyscript_trigger
    def foreground(): return 456
    def pid(handle, value): value._obj.value = 42
    api = SimpleNamespace(GetForegroundWindow=foreground, GetWindowThreadProcessId=pid)
    monkeypatch.setattr(ctypes,'windll',SimpleNamespace(user32=api),raising=False)
    monkeypatch.setattr(pyscript_trigger,'force_focus',lambda handle: pytest.fail('Already foreground FL must not receive synthetic Alt'))
    desktop = object.__new__(ui.FLDesktop)
    desktop.pid=42
    desktop.main=SimpleNamespace(is_enabled=lambda:True,window_text=lambda:'owned',handle=123)
    desktop.focus('owned')


def test_click_on_embedded_menu_does_not_refocus_parent(tmp_path,monkeypatch):
    import ctypes
    import pyautogui
    rect=SimpleNamespace(left=10,top=20,right=410,bottom=320,width=lambda:400,height=lambda:300)
    def bad_focus():pytest.fail('Refocus would dismiss the embedded menu before clicking')
    window=SimpleNamespace(handle=1,rectangle=lambda:rect,class_name=lambda:'TFXForm',set_focus=bad_focus)
    desktop=SimpleNamespace(pid=7,main=SimpleNamespace(is_enabled=lambda:True,window_text=lambda:'Owned'),
                            session=lambda **kw:None,focus=lambda title:None)
    obs=dict(time=time.time(),process_id=7,title='Owned',windows=[dict(handle='1',rect=[10,20,410,320],image_sha256='same')])
    atomic_json(tmp_path/'observations'/'fresh'/'observation.json',obs)
    monkeypatch.setattr(ui,'state_dir',lambda:tmp_path)
    monkeypatch.setattr(ui,'FLDesktop',lambda:desktop)
    monkeypatch.setattr(ui,'visible_windows',lambda d:{'1':window})
    monkeypatch.setattr(ui,'window_image',lambda w:(None,'same'))
    monkeypatch.setattr(ui,'observe',lambda d:obs)
    def hit(point):return 1
    def child(parent,hwnd):return False
    monkeypatch.setattr(ctypes,'windll',SimpleNamespace(user32=SimpleNamespace(WindowFromPoint=hit,IsChild=child)))
    clicks=[];monkeypatch.setattr(pyautogui,'click',lambda *args,**kwargs:clicks.append(args))
    result=ui.act('fresh','once','1','click',point=[.5,.5])
    assert result['phase']=='input_sent' and clicks==[(210,170)]
