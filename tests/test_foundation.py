"""Offline contracts only; actual FL acceptance is recorded separately."""
import pytest
from fl_studio_mcp.tools.foundation import batch_edit,validate_edits,guard_route,project_state
from fl_studio_mcp.workflow import WorkflowError
from fl_studio_mcp.connection import FLBridgeError


class Host:
    def __init__(self):self.value=.5;self.calls=[];self.ignore=False;self.fail=False;self.name='Piano';self.playing=False
    def call(self,cmd,args=None):
        self.calls.append(cmd)
        if cmd=='get_play_state':return {'playing':self.playing}
        if cmd=='get_project_state':return {'channel_count':2,'mixer_track_count':18}
        if cmd=='channel_get':return dict(i=1,name=self.name,vol_norm=self.value)
        if cmd=='channel_set_volume':
            if self.fail:raise FLBridgeError('timeout')
            if not self.ignore:self.value=args['value']
            return {'vol_norm':args['value']}
        raise AssertionError(cmd)


@pytest.mark.parametrize('ignore',[False,True])
def test_pattern_selection_checks_actual_number_and_never_retries(monkeypatch,ignore):
    from types import SimpleNamespace
    from fl_studio_mcp.tools import foundation
    import fl_studio_mcp.host_io as files
    registered={};sent=[];selected=[3]
    class Registry:
        def tool(self,**kwargs):
            def capture(fn):registered[fn.__name__]=fn;return fn
            return capture
    def call(cmd,args=None):
        if cmd=='get_play_state':return dict(playing=False,recording=False)
        if cmd=='get_project_state':return dict(pattern_number=selected[0])
        if cmd=='pattern_list':return dict(total=3,next_start=None,patterns=[dict(pattern=i,name=f'P{i}') for i in range(1,4)])
        pytest.fail('Pattern selection must not create/clone or edit notes')
    def keys(value,title):
        sent.append(value)
        if not ignore:selected[0]=1
    monkeypatch.setattr(foundation,'get_bridge',lambda:SimpleNamespace(call=call))
    monkeypatch.setattr(files,'HostFiles',lambda:SimpleNamespace(_require_owned=lambda t:None,_playlist_keys=keys))
    foundation.register(Registry())
    r=registered['fl_foundation_pattern']('select','P1',3,'Owned',1)
    assert r['verified']==(not ignore) and r['ok']==(not ignore)
    assert sent==['{VK_SUBTRACT}{VK_SUBTRACT}']


def edit():return [dict(kind='channel_volume',index=1,expected_name='Piano',expected_value=.5,value=.6)]


def test_independent_read_after_write():
    h=Host();r=batch_edit(h,edit())
    assert r['verified'] and r['changes'][0]['after']['vol_norm']==.6
    assert h.calls[-3:]==['channel_set_volume','get_project_state','channel_get']


def test_delayed_control_value_read_does_not_repeat_write():
    class Delayed(Host):
        pending=None
        reads=0
        def call(self,cmd,args=None):
            if cmd=='channel_set_volume':
                self.calls.append(cmd);self.pending=args['value'];return dict(vol_norm=self.pending)
            if cmd=='channel_get' and self.pending is not None:
                self.reads+=1
                if self.reads>=2:self.value=self.pending
            return super().call(cmd,args)
    h=Delayed();r=batch_edit(h,edit())
    assert r['verified'] and r['changes'][0]['readback_attempts']==2
    assert h.calls.count('channel_set_volume')==1


def test_false_ack_not_success():
    h=Host();h.ignore=True;r=batch_edit(h,edit())
    assert not r['ok'] and r['error']['code']=='READBACK_MISMATCH'


def test_write_timeout_never_replayed():
    h=Host();h.fail=True;r=batch_edit(h,edit())
    assert not r['ok'] and r['changes'][0]['write_attempted']
    assert h.calls.count('channel_set_volume')==1


@pytest.mark.parametrize('case',['playing','name','value'])
def test_preflight_failure_never_writes(case):
    h=Host()
    if case=='playing':h.playing=True
    if case=='name':h.name='Other'
    if case=='value':h.value=.9
    assert not batch_edit(h,edit())['ok']
    assert 'channel_set_volume' not in h.calls


@pytest.mark.parametrize('value',[True,float('nan'),float('inf'),-1,2])
def test_invalid_edit_before_any_host_call(value):
    h=Host();e=edit();e[0]['value']=value
    with pytest.raises(WorkflowError):batch_edit(h,e)
    assert not h.calls


def test_unsupported_commands_rejected():
    with pytest.raises(WorkflowError):validate_edits([dict(kind='eval',value='anything')])


def test_out_of_bounds_never_reaches_native_item_reader():
    h=Host();e=edit();e[0]['index']=999
    result=batch_edit(h,e)
    assert not result['ok'] and result['error']['code']=='INVALID_TARGET'
    assert 'channel_get' not in h.calls and 'channel_set_volume' not in h.calls


def test_rename_and_other_write_must_be_separate():
    with pytest.raises(WorkflowError):validate_edits([
        dict(kind='mixer_name',index=1,expected_name='Old',expected_value='Old',value='New'),
        dict(kind='mixer_pan',index=1,expected_name='Old',expected_value=0,value=.1)])


def rows():return [dict(i=0,routes_to=[]),dict(i=1,routes_to=[{'dst':0}]),dict(i=2,routes_to=[{'dst':0}])]


def test_safe_send_accepted():guard_route(rows(),1,2,True)


def test_feedback_rejected():
    r=rows();r[2]['routes_to'].append({'dst':1})
    with pytest.raises(WorkflowError,match='feedback'):guard_route(r,1,2,True)


def test_master_disconnect_rejected():
    with pytest.raises(WorkflowError,match='Master'):guard_route(rows(),1,0,False)


@pytest.mark.parametrize('src,dst',[(0,1),(1,1),(1,99),(-1,1)])
def test_invalid_routing(src,dst):
    with pytest.raises(WorkflowError):guard_route(rows(),src,dst,True)


def test_unknown_playlist_not_filled_with_fake_empty_state():
    class ReadHost:
        def call(self,cmd,args=None):
            if cmd=='get_project_state':return {'tempo_bpm':140}
            key={'channel_list':'channels','channel_routing_summary':'channels','pattern_list':'patterns',
                 'mixer_list_tracks':'tracks','mixer_get_routing_all':'routing'}[cmd]
            return {key:[], 'total':0,'next_start':None}
    result=project_state(ReadHost())
    assert not result['playlist']['verified'] and 'saved_checkpoint' not in result


def test_clone_returns_inserted_index_not_new_count(monkeypatch):
    # Matches the real FL insert-after-source behavior that stopped acceptance.
    from types import SimpleNamespace
    from fl_studio_mcp.tools import foundation
    import fl_studio_mcp.host_io as files
    registry={}
    class Registry:
        def tool(self,**kw):
            def capture(fn):registry[fn.__name__]=fn;return fn
            return capture
    class Bridge:
        cloned=False
        def call(self,cmd,args=None):
            if cmd=='get_play_state':return {'playing':False}
            if cmd=='get_project_state':return {'pattern_number':2}
            if cmd=='arrange_clone_pattern':self.cloned=True;return {'new_index':2,'count_after':4}
            if cmd=='pattern_list':
                names=['Source','Target','Old Clone','Empty'] if self.cloned else ['Source','Old Clone','Empty']
                return dict(total=len(names),next_start=None,patterns=[dict(pattern=i+1,name=n) for i,n in enumerate(names)])
            raise AssertionError(cmd)
    b=Bridge()
    monkeypatch.setattr(foundation,'get_bridge',lambda:b)
    monkeypatch.setattr(files,'HostFiles',lambda:SimpleNamespace(_require_owned=lambda title:None))
    foundation.register(Registry())
    result=registry['fl_foundation_pattern']('clone','Target',3,'Owned',1)
    assert result['verified'] and result['selected_pattern']==2 and result['after']['total']==4
    assert not result['notes_verified'] and 'renumber' in result['index_stability']
