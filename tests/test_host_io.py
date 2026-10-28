"""Offline guards for no-image host file fallback."""
import json
from types import SimpleNamespace
import pytest
from fl_studio_mcp.host_io import HostFiles
from fl_studio_mcp.workflow import WorkflowError,digest


def host():
    obj=HostFiles.__new__(HostFiles)
    obj.pid=7;obj.main=SimpleNamespace(window_text=lambda:'Test.flp - FL Studio 2026')
    obj._playlist_keys=lambda *a:pytest.fail('No keys permitted')
    return obj


@pytest.mark.parametrize('suffix',['.flp','.wav'])
def test_existing_destination_never_overwritten(tmp_path,suffix):
    p=tmp_path/('existing'+suffix);p.write_bytes(b'preserve')
    with pytest.raises(WorkflowError):
        (host().save_as_no_image if suffix=='.flp' else host().export_wav_no_image)(p,'title')
    assert p.read_bytes()==b'preserve'


def test_no_owned_session_refuses_export_before_keys(tmp_path,monkeypatch):
    import fl_studio_mcp.host_io as module
    monkeypatch.setattr(module,'state_dir',lambda:tmp_path)
    with pytest.raises(WorkflowError,match='First Save As'):host().export_wav_no_image(tmp_path/'new.wav','title')


@pytest.mark.parametrize('changed',['process','title','file'])
def test_owned_identity_guards(tmp_path,monkeypatch,changed):
    import fl_studio_mcp.host_io as module
    monkeypatch.setattr(module,'state_dir',lambda:tmp_path)
    file=tmp_path/'Test.flp';file.write_bytes(b'original')
    session=dict(path=str(file),sha256=digest(file),title='Test.flp - FL Studio 2026',process_id=7)
    if changed=='process':session['process_id']=8
    if changed=='title':session['title']='Another.flp'
    if changed=='file':file.write_bytes(b'changed')
    (tmp_path/'host-file-session.json').write_text(json.dumps(session))
    with pytest.raises(WorkflowError,match='identity differs'):host()._require_owned('Test.flp - FL Studio 2026')


def test_reopen_distinct_paths_before_preservation(tmp_path,monkeypatch):
    import fl_studio_mcp.host_io as module
    monkeypatch.setattr(module,'inspect',lambda p:{})
    source=tmp_path/'original.flp';source.write_bytes(b'original')
    with pytest.raises(WorkflowError):host().reopen_copy(source,source,tmp_path/'preserved.flp','title')
    assert source.read_bytes()==b'original'


def test_no_image_or_mouse_calls_in_new_layer():
    # A regression contract for the user's explicit prohibition, alongside real acceptance.
    import inspect
    import fl_studio_mcp.host_io as files
    import fl_studio_mcp.accessible_presets as presets
    source=inspect.getsource(files)+inspect.getsource(presets)
    assert 'pyautogui' not in source and '.click(' not in source and '.screenshot(' not in source
    import ast
    forbidden={'set_focus','click_input','move_mouse_input','drag_mouse_input','screenshot','click'}
    assert not [n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in forbidden]


@pytest.mark.parametrize('process',['lockapp.exe','logonui.exe'])
def test_locked_desktop_stops_before_activation_or_keys(monkeypatch,process):
    import fl_studio_mcp.host_io as module
    monkeypatch.setattr(module,'_foreground_process_name',lambda:process)
    obj=HostFiles.__new__(HostFiles)  # no windows initialized: any access would fail
    with pytest.raises(WorkflowError,match='Windows is locked'):obj.focus('title')
    with pytest.raises(WorkflowError,match='Windows is locked'):obj._keys('{ENTER}')


@pytest.mark.parametrize('unicode_text',[False,True])
def test_active_picker_does_not_receive_activation_alt(monkeypatch,unicode_text):
    import ctypes
    import fl_studio_mcp.host_io as module
    import fl_studio_mcp.pyscript_trigger as trigger
    import pywinauto.keyboard as keyboard
    class Fn:
        def __init__(self,fn):self.fn=fn
        def __call__(self,*args):return self.fn(*args)
    def pid(handle,output):ctypes.cast(output,ctypes.POINTER(ctypes.c_ulong)).contents.value=7
    u=SimpleNamespace(GetForegroundWindow=Fn(lambda:2),GetWindowThreadProcessId=Fn(pid))
    monkeypatch.setattr(module.ctypes,'windll',SimpleNamespace(user32=u))
    monkeypatch.setattr(module,'require_interactive_desktop',lambda:None)
    monkeypatch.setattr(trigger,'force_focus',lambda *a:pytest.fail('Do not tap Alt into active picker'))
    sent=[];monkeypatch.setattr(keyboard,'send_keys',lambda keys,**kw:sent.append((keys,kw)))
    obj=HostFiles.__new__(HostFiles);obj.pid=7;obj.main=object()
    popup=SimpleNamespace(handle=2,is_visible=lambda:True,process_id=lambda:7,class_name=lambda:'TPlugListForm')
    obj._keys('Pianoteq',popup,unicode_text=unicode_text)
    assert len(sent)==1 and sent[0][1]['with_spaces'] and sent[0][1]['vk_packet']==unicode_text
