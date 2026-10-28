"""Regression for actual observed delayed wrapper/name/heartbeat during loading."""
from types import SimpleNamespace
import pytest
from fl_studio_mcp.connection import FLBridgeError


def test_loading_placeholder_and_read_timeout_do_not_reload(monkeypatch):
    from fl_studio_mcp.tools import vst
    import fl_studio_mcp.host_io as files
    import fl_studio_mcp.desktop as desktop
    tools={};keys=[]
    class Registry:
        def tool(self,**kwargs):
            def save(fn):tools[fn.__name__]=fn;return fn
            return save
    class Bridge:
        reads=0
        def call(self,cmd,args=None):
            if cmd=='get_play_state':return {'playing':False}
            if cmd=='channel_list':
                self.reads+=1
                channels=[dict(i=0,name='Sampler')]
                if self.reads==3:raise FLBridgeError('transient loading timeout')
                if self.reads>=2:channels.append(dict(i=1,name='Fruity Wrapper' if self.reads==2 else 'Pianoteq 9'))
                return dict(channels=channels,total=len(channels),next_start=None)
            if cmd=='plugin_get_params':return dict(plugin='Pianoteq 9',total=4240)
            raise AssertionError(cmd)
    def wait(predicate,**kw):
        for _ in range(6):
            result=predicate()
            if result:return result
        raise AssertionError('No progress')
    b=Bridge();picker=SimpleNamespace(is_visible=lambda:True)
    host=SimpleNamespace(pid=7,_require_owned=lambda t:None,focus=lambda t:None,
        _keys=lambda *args,**kwargs:keys.append((args,kwargs)),channel_rack=lambda:object(),win32=SimpleNamespace(windows=lambda **kw:[picker]))
    monkeypatch.setattr(vst,'get_bridge',lambda:b)
    monkeypatch.setattr(files,'HostFiles',lambda:host)
    monkeypatch.setattr(desktop,'wait_for',wait)
    vst.register(Registry())
    result=tools['fl_vst_keyboard_load']('Pianoteq','Pianoteq 9','Owned',expected_channel='Pianoteq 9')
    assert result['verified'] and result['readback']['parameter_count']==4240
    assert [k[0][0] for k in keys]==['{F8}','Pianoteq','{DOWN}{ENTER}']
    assert keys[1][1]=={'unicode_text':True}  # no Chinese IME composition


@pytest.mark.parametrize('case',['name','old_assignment'])
def test_stale_assignment_never_sends_keys_or_selects_channel(monkeypatch,case):
    from fl_studio_mcp.tools import vst
    import fl_studio_mcp.host_io as files
    registered={};calls=[]
    class Registry:
        def tool(self,**kwargs):
            def capture(fn):registered[fn.__name__]=fn;return fn
            return capture
    def call(cmd,args=None):
        calls.append(cmd)
        if cmd=='get_project_state':return dict(playing=False,recording=False,channel_count=2,mixer_track_count=18)
        if cmd=='channel_get':return dict(name='Other' if case=='name' else 'Piano',target_fx_track=1)
        raise AssertionError('No mutation allowed')
    monkeypatch.setattr(vst,'get_bridge',lambda:SimpleNamespace(call=call))
    monkeypatch.setattr(files,'HostFiles',lambda:SimpleNamespace(_require_owned=lambda title:None))
    vst.register(Registry())
    result=registered['fl_vst_assign_free_mixer'](1,'Piano',0,'Owned')
    assert not result['ok'] and result['error']['code']=='STALE_CHANNEL'
    assert 'channel_select' not in calls


def test_effect_picker_requires_actual_selected_mixer_caption(monkeypatch):
    from fl_studio_mcp.tools import vst
    import fl_studio_mcp.host_io as files
    registered={}
    class Registry:
        def tool(self,**kwargs):
            def capture(fn):registered[fn.__name__]=fn;return fn
            return capture
    def call(cmd,args=None):
        if cmd=='get_play_state':return dict(playing=False)
        if cmd=='channel_list':return dict(channels=[],total=0,next_start=None)
        if cmd=='get_project_state':return dict(mixer_track_count=18)
        if cmd=='mixer_get_track':return dict(name='Synth')
        if cmd=='plugin_list':return dict(slots=[])
        pytest.fail('No mutation allowed')
    host=SimpleNamespace(_require_owned=lambda title:None,focus=lambda title:None,
        main=SimpleNamespace(descendants=lambda:[]),_keys=lambda *a,**kw:pytest.fail('No keys allowed'))
    monkeypatch.setattr(vst,'get_bridge',lambda:SimpleNamespace(call=call))
    monkeypatch.setattr(files,'HostFiles',lambda:host)
    vst.register(Registry())
    result=registered['fl_vst_keyboard_load']('Fruity Compressor','Fruity Compressor','Owned','',mixer_track=2,expected_mixer_name='Synth')
    assert not result['ok'] and result['error']['code']=='MIXER_SELECTION_UNVERIFIED'
