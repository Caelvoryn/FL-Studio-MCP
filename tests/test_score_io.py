"""Offline basic-score contracts; separate real MCP records establish actual FL behavior."""
import pytest
from fl_studio_mcp.score_io import canonical,basic_score,write_midi,untouched,state_invariants
from fl_studio_mcp.workflow import WorkflowError


def note(pitch=60,time=0,length=96,velocity=80):
    return dict(pitch=pitch,time_ticks=time,length_ticks=length,velocity_raw=velocity)


@pytest.mark.parametrize('field,value',[('pitch',128),('time_ticks',-1),('length_ticks',0),('velocity_raw',0),('pitch',True),('length_ticks',float('nan'))])
def test_invalid_note_rejected(field,value):
    n=note();n[field]=value
    with pytest.raises(WorkflowError):canonical([n])


def test_chords_and_deterministic_order():
    assert [n['pitch'] for n in canonical([note(67),note(60),note(64)])]==[60,64,67]


def test_extra_properties_never_silently_discarded():
    n=note();n['slide']=True
    with pytest.raises(WorkflowError):canonical([n])


def test_midi_chord_roundtrip_and_no_overwrite(tmp_path):
    import mido
    p=tmp_path/'score.mid';write_midi(p,[note(60),note(64),note(67)],96)
    mid=mido.MidiFile(p)
    assert mid.ticks_per_beat==96
    assert [(m.note,m.velocity) for m in mid.tracks[0] if m.type=='note_on']==[(60,80),(64,80),(67,80)]
    with pytest.raises(WorkflowError):write_midi(p,[],96)


@pytest.mark.parametrize('offset,value',[(4,1),(18,64),(19,129),(20,40),(22,64)])
def test_nonbasic_existing_style_refused(offset,value):
    raw=bytearray.fromhex('0000000000400100600000003c0000007800008040508080');raw[offset]=value
    n=dict(note(),channel=1,raw_record_hex=raw.hex())
    with pytest.raises(WorkflowError):basic_score({'patterns':{1:{'notes':[n]}}},1,1)


@pytest.mark.parametrize('marker',[0,128])
def test_basic_existing_style_read_and_other_records_preserved(marker):
    data=bytearray.fromhex('0000000000400100600000003c0000007800008040508080');data[19]=marker
    raw=data.hex()
    n=dict(note(),channel=1,raw_record_hex=raw)
    other=dict(note(72),channel=0,raw_record_hex=raw)
    state={'patterns':{1:{'notes':[n,other]}}}
    assert basic_score(state,1,1)==[note()]
    assert untouched(state,1,1)=={1:[other]}


@pytest.mark.parametrize('changed',['plugin_state_hashes','mixer_event_hashes','playlist','automation'])
def test_other_musical_state_changes_are_not_accepted(changed):
    before=dict(plugin_state_hashes=['actual'],mixer_event_hashes=['actual'],playlist=[],automation=[])
    after=dict(before);after[changed]=['changed']
    assert not all(state_invariants(before,after).values())


def test_import_marker_on_other_channel_refuses_before_any_input(tmp_path):
    from types import SimpleNamespace
    from fl_studio_mcp.score_io import replace_basic
    n=dict(note(),channel=1,raw_record_hex='0000000000400100600000003c0000007800008040508080')
    state={'patterns':{1:{'notes':[n]}}}
    calls=[]
    host=SimpleNamespace(_require_owned=lambda t:None,
        save_as_no_image=lambda *a:dict(saved_state=state,path='checkpoint',title='new title'))
    def call(cmd,args=None):
        calls.append(cmd)
        if cmd=='get_project_state':return dict(playing=False,recording=False,pattern_number=1,channel_count=3)
        if cmd=='channel_get':return dict(name='Synth')
        pytest.fail('No mutation allowed')
    with pytest.raises(WorkflowError,match='exact preservation'):
        replace_basic(host,SimpleNamespace(call=call),2,'Synth',1,[],[note()],
            tmp_path/'new.mid',tmp_path/'before.flp',tmp_path/'after.flp','title')
    assert not (tmp_path/'new.mid').exists()
    assert calls==['get_project_state','channel_get']
