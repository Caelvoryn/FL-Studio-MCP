"""Offline contract/failure tests, never evidence of actual plugin compatibility."""
import copy
import pytest
from fl_studio_mcp.tools.vst import batch_parameters, parameter_page
from fl_studio_mcp.workflow import WorkflowError
from fl_studio_mcp.connection import FLBridgeError


class Host:
    def __init__(self):
        self.value = .4
        self.calls = []
        self.plugin = 'Pianoteq 9'
        self.playing = False
        self.ignore = False
        self.fail_write = False

    def call(self, command, args=None):
        self.calls.append((command, args))
        if command == 'get_play_state': return dict(playing=self.playing)
        if command == 'channel_list': return dict(channels=[dict(i=0, name='Piano')], next_start=None)
        if command == 'plugin_get_params':
            return dict(plugin=self.plugin, total=4240, params=[], next_start=150)
        if command == 'plugin_get_param': return dict(param=args['param'], name='Brightness', v=self.value, s='display')
        if command == 'plugin_set_param':
            if self.fail_write: raise FLBridgeError('timeout')
            if not self.ignore: self.value = args['value']
            return dict(v=args['value'])
        raise AssertionError(command)


def changes():
    return [dict(param=2, name='Brightness', expected_value=.4, value=.6, tolerance=.0001)]


def run(host, edits=None):
    return batch_parameters(host, 0, -1, 'Pianoteq 9', changes() if edits is None else edits, 'Piano')


def test_independent_read_after_write():
    host=Host(); result=run(host)
    assert result['verified'] and not result['persistence_verified'] and not result['preset_switch_verified']
    commands=[c for c,a in host.calls]
    assert commands[commands.index('plugin_set_param')+1]=='plugin_get_param'


def test_lying_acknowledgement_not_success():
    host=Host();host.ignore=True;result=run(host)
    assert not result['ok'] and result['error']['code']=='READBACK_MISMATCH'
    assert result['changes'][0]['after']['v']==.4


def test_timeout_preserves_uncertain_write():
    host=Host();host.fail_write=True;result=run(host)
    assert not result['ok'] and result['changes'][0]['write_attempted'] and not result['changes'][0]['verified']
    assert len([c for c,a in host.calls if c=='plugin_set_param'])==1


@pytest.mark.parametrize('case', ['playing','plugin','channel','stale','name'])
def test_no_write_when_preflight_fails(case):
    host=Host();edit=changes();channel='Piano'
    if case=='playing': host.playing=True
    if case=='plugin': host.plugin='Other'
    if case=='channel': channel='Other'
    if case=='stale': host.value=.7
    if case=='name': edit[0]['name']='Other'
    result=batch_parameters(host,0,-1,'Pianoteq 9',edit,channel)
    assert not result['ok']
    assert all(c!='plugin_set_param' for c,a in host.calls)


@pytest.mark.parametrize('value', [float('nan'),float('inf'),True,-.1,1.1])
def test_bad_normalized_values_rejected_before_io(value):
    host=Host();edit=changes();edit[0]['value']=value
    with pytest.raises(WorkflowError):run(host,edit)
    assert not host.calls


def test_duplicate_indices_rejected():
    host=Host();edit=changes()
    with pytest.raises(WorkflowError):run(host,edit+copy.deepcopy(edit))
    assert not host.calls


def test_large_sparse_page_not_false_complete_snapshot():
    result=parameter_page(Host(),0,-1,'Pianoteq 9','Piano')
    assert result['readback']['total']==4240 and result['readback']['next_start']==150
    assert result['preset_identity'] is None


@pytest.mark.parametrize('mode,expected', [('default',47),('direct',48),('legacy',87)])
def test_registry_write_opt_in(monkeypatch,mode,expected):
    import asyncio
    from fastmcp import Client
    from fl_studio_mcp.server import build_server
    monkeypatch.delenv('FLSTUDIO_MCP_ENABLE_LEGACY_WRITES',raising=False)
    monkeypatch.delenv('FLSTUDIO_MCP_ENABLE_DIRECT_VST_WRITES',raising=False)
    if mode=='direct':monkeypatch.setenv('FLSTUDIO_MCP_ENABLE_DIRECT_VST_WRITES','1')
    if mode=='legacy':monkeypatch.setenv('FLSTUDIO_MCP_ENABLE_LEGACY_WRITES','1')
    async def verify():
        async with Client(build_server()) as client:
            names={t.name for t in await client.list_tools()}
            assert len(names)==expected
            assert ('fl_vst_batch_parameters' in names)==(mode!='default')
            assert ('fl_plugin_set_param' in names)==(mode=='legacy')
    asyncio.run(verify())
