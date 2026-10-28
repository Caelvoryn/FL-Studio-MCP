"""Offline UIA profile failure contracts, not actual FL acceptance."""
from types import SimpleNamespace
import pytest
from fl_studio_mcp.accessible_presets import parse_current_label,unique_named,AccessiblePresets
from fl_studio_mcp.workflow import WorkflowError


@pytest.mark.parametrize('label,name,modified',[
    ('Current preset: Steinway B Warm','Steinway B Warm',False),
    ('Current preset: Steinway B Bright (modified)','Steinway B Bright',True)])
def test_actual_label_parsing(label,name,modified):
    assert parse_current_label(label)==dict(name=name,modified=modified,raw_label=label)


@pytest.mark.parametrize('label',['Program 0','Current preset: ',None])
def test_never_guess_current_preset_from_program_or_empty_label(label):
    with pytest.raises(WorkflowError):parse_current_label(label)


@pytest.mark.parametrize('count',[0,2])
def test_menu_ambiguity_fails(count):
    controls=[SimpleNamespace(window_text=lambda:'Warm') for _ in range(count)]
    with pytest.raises(WorkflowError):unique_named(controls,'Warm')


def test_other_plugins_are_not_assumed_accessible():
    with pytest.raises(WorkflowError,match='Only Pianoteq9'):AccessiblePresets(None,'Serum 2','Serum 2')


def test_stale_preset_does_not_invoke():
    adapter=AccessiblePresets.__new__(AccessiblePresets)
    adapter.read=lambda:dict(name='Actual')
    adapter._button=lambda:pytest.fail('No UI action permitted')
    with pytest.raises(WorkflowError,match='differs'):adapter.select(['Target'],'Old')


def test_existing_menu_does_not_invoke_again():
    adapter=AccessiblePresets.__new__(AccessiblePresets)
    adapter.read=lambda:dict(name='Actual')
    adapter._menu_items=lambda:[object()]
    adapter._button=lambda:pytest.fail('No repeated UI action permitted')
    with pytest.raises(WorkflowError,match='Existing preset popup'):adapter.select(['Target'],'Actual')


def test_host_activation_precedes_popup_selection(monkeypatch):
    # Regression for the real wrong-submenu failure when JUCE was invoked while
    # another application owned foreground. No claim of real UIA compatibility.
    from fl_studio_mcp.tools import accessible_presets as tool
    import fl_studio_mcp.host_io as files
    import fl_studio_mcp.accessible_presets as presets
    functions={};state={'focused':False}
    class Registry:
        def tool(self,**kw):
            def capture(fn):functions[fn.__name__]=fn;return fn
            return capture
    class Host:
        def _require_owned(self,title):assert title=='Owned'
        def focus(self,title):state['focused']=True
    class Adapter:
        def __init__(self,*a):assert state['focused']
        def select(self,*a):return dict(ok=True,verified=True)
    monkeypatch.setattr(tool,'get_bridge',lambda:SimpleNamespace(call=lambda *a:{'playing':False}))
    monkeypatch.setattr(tool,'_identity',lambda *a:None)
    monkeypatch.setattr(files,'HostFiles',Host)
    monkeypatch.setattr(presets,'AccessiblePresets',Adapter)
    tool.register(Registry())
    result=functions['fl_vst_accessible_preset']('select',1,'Pianoteq 9','Piano','Owned',['Model','Target'],'Before')
    assert result['verified']
