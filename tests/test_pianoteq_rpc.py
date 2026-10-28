"""Offline adapter contracts; independent real RPC evidence is separately recorded."""
import pytest
from fl_studio_mcp.pianoteq import PianoteqStandalone
from fl_studio_mcp.workflow import WorkflowError


class Stub(PianoteqStandalone):
    def __init__(self):
        super().__init__(18091)
        self.preset='Warm';self.value=.5;self.calls=[];self.ignore=False
    def _call(self,method,params=None):
        self.calls.append(method)
        if method=='getInfo':return [dict(vendor_name='Modartt',plugin_type='sta',current_preset=dict(name=self.preset,bank='',instrument='B'))]
        if method=='getListOfPresets':return [dict(name='Warm',bank='',instr='B',license_status='ok'),dict(name='Bright',bank='',instr='B',license_status='ok')]
        if method=='getParameters':return [dict(id='reverb_mix',normalized_value=self.value)]
        if method=='loadPreset':
            if not self.ignore:self.preset=params['name']
            return None
        if method=='setParameters':
            if not self.ignore:self.value=params['list'][0]['normalized_value']
            return None
        raise AssertionError(method)


def test_exact_name_readback_and_scope():
    result=Stub().load_preset('Bright')
    assert result['verified'] and not result['FL_plugin_acceptance'] and not result['persistence_verified']
    assert result['after']['name']=='Bright'


def test_preset_ack_is_not_verification():
    api=Stub();api.ignore=True
    assert not api.load_preset('Bright')['verified']


def test_missing_preset_never_writes():
    api=Stub()
    with pytest.raises(WorkflowError):api.load_preset('Unknown')
    assert 'loadPreset' not in api.calls


def test_stale_parameter_never_writes():
    api=Stub()
    with pytest.raises(WorkflowError):api.set_parameters([dict(id='reverb_mix',expected_value=.6,normalized_value=.4)])
    assert 'setParameters' not in api.calls


@pytest.mark.parametrize('ignore',[False,True])
def test_independent_parameter_readback(ignore):
    api=Stub();api.ignore=ignore
    result=api.set_parameters([dict(id='reverb_mix',expected_value=.5,normalized_value=.4)])
    assert result['verified'] is (not ignore)


def test_rpc_rejects_non_standalone_identity(monkeypatch):
    api=Stub();monkeypatch.setattr(api,'_call',lambda *a:[dict(vendor_name='Modartt',plugin_type='vst3')])
    with pytest.raises(WorkflowError):api.info()


@pytest.mark.parametrize('port',[80,True,65536])
def test_explicit_nonprivileged_loopback_port(port):
    with pytest.raises(ValueError):PianoteqStandalone(port)
