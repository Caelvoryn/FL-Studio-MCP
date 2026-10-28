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


@pytest.mark.parametrize('process',['lockapp.exe','logonui.exe'])
def test_locked_desktop_stops_before_activation_or_keys(monkeypatch,process):
    import fl_studio_mcp.host_io as module
    monkeypatch.setattr(module,'_foreground_process_name',lambda:process)
    obj=HostFiles.__new__(HostFiles)  # no windows initialized: any access would fail
    with pytest.raises(WorkflowError,match='Windows is locked'):obj.focus('title')
    with pytest.raises(WorkflowError,match='Windows is locked'):obj._keys('{ENTER}')
