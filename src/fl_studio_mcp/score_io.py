"""Basic-note replacement through FL's real MIDI importer; explicit keyboard fallback.

No screenshots, canvas coordinates, controller replacement or FLP rewriting.
This is NOT the Piano Roll Score scripting API and cannot preserve arbitrary note styles.
"""
from pathlib import Path

from .workflow import WorkflowError
from .desktop import wait_for


def canonical(notes):
    fields={'pitch','time_ticks','length_ticks','velocity_raw'}
    if not isinstance(notes,list) or len(notes)>4096:
        raise WorkflowError('INVALID_SCORE','At most4096 basic notes')
    result=[]
    for n in notes:
        if not isinstance(n,dict) or set(n)!=fields or any(type(v)is not int for v in n.values()):
            raise WorkflowError('INVALID_SCORE','Exact integer pitch,time_ticks,length_ticks,velocity_raw fields required')
        if not (0<=n['pitch']<=127 and 0<=n['time_ticks']<=10000000 and 1<=n['length_ticks']<=1000000 and 1<=n['velocity_raw']<=127):
            raise WorkflowError('INVALID_SCORE','Basic note outside supported bounds')
        result.append(dict(n))
    return sorted(result,key=lambda n:(n['time_ticks'],n['pitch'],n['length_ticks'],n['velocity_raw']))


def basic_score(state,pattern,channel):
    notes=state['patterns'].get(pattern,state['patterns'].get(str(pattern),{})).get('notes',[])
    result=[]
    for n in notes:
        if n['channel']!=channel:continue
        raw=bytes.fromhex(n['raw_record_hex'])
        # The observed simple MIDI-import style only. Refuse slide/group/pan/
        # release/microtuning/custom controls instead of silently flattening them.
        if len(raw)!=24 or raw[4:6]!=b'\x00\x40' or raw[14:21]!=b'\x00\x00\x78\x00\x00\x80\x40' or raw[22:24]!=b'\x80\x80':
            raise WorkflowError('UNSUPPORTED_NOTE_STYLE','Existing score has non-basic properties; no MIDI replacement permitted')
        result.append({k:n[k] for k in ('pitch','time_ticks','length_ticks','velocity_raw')})
    return canonical(result)


def write_midi(path,notes,ppq):
    import mido
    path=Path(path).resolve()
    if path.suffix.lower()!='.mid' or path.exists():raise WorkflowError('OVERWRITE_REFUSED','Fresh .mid path required')
    file=mido.MidiFile(ticks_per_beat=ppq);track=mido.MidiTrack();file.tracks.append(track)
    events=[]
    for n in canonical(notes):
        events += [(n['time_ticks'],1,n['pitch'],n['velocity_raw']),
                   (n['time_ticks']+n['length_ticks'],0,n['pitch'],0)]
    previous=0
    for tick,on,pitch,velocity in sorted(events):
        track.append(mido.Message('note_on' if on else 'note_off',note=pitch,velocity=velocity,time=tick-previous));previous=tick
    track.append(mido.MetaMessage('end_of_track',time=0))
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:file.save(file=stream)
    return path


def untouched(state,pattern,channel):
    result={}
    for p,row in state['patterns'].items():
        notes=[n for n in row['notes'] if int(p)!=pattern or n['channel']!=channel]
        if notes:result[int(p)]=notes
    return result


def state_invariants(before,after):
    return dict(plugin_states=before['plugin_state_hashes']==after['plugin_state_hashes'],
                mixer_state=before['mixer_event_hashes']==after['mixer_event_hashes'],
                playlist=before['playlist']==after['playlist'],automation=before['automation']==after['automation'])


def replace_basic(host,bridge,channel,expected_channel,pattern,expected_notes,notes,midi_path,before_path,after_path,expected_title):
    expected_notes=canonical(expected_notes);notes=canonical(notes)
    paths=[Path(p).resolve() for p in (midi_path,before_path,after_path)]
    if len(set(paths))!=3 or any(p.exists() for p in paths):raise WorkflowError('OVERWRITE_REFUSED','Three fresh distinct paths required')
    host._require_owned(expected_title)
    def guard():
        state=bridge.call('get_project_state')
        if state.get('playing') or state.get('recording') or state['pattern_number']!=pattern or not 0<=channel<state['channel_count']:
            raise WorkflowError('SCORE_TARGET_CHANGED','Stopped transport and exact existing selected Pattern/channel required')
        actual=bridge.call('channel_get',{'index':channel})
        if actual['name']!=expected_channel:raise WorkflowError('SCORE_TARGET_CHANGED','Channel name differs')
    guard()
    saved=host.save_as_no_image(before_path,expected_title)
    state=saved['saved_state']
    if basic_score(state,pattern,channel)!=expected_notes:
        raise WorkflowError('STALE_SCORE','Actual fresh native score differs; only checkpoint was saved, no note edits')
    midi=write_midi(midi_path,notes,state['ppq'])
    guard();bridge.call('channel_select',{'channel':channel});bridge.call('ensure_piano_roll')
    def piano():
        candidates=[w for w in host.main.descendants() if w.class_name()=='TEventEditForm' and w.is_visible()
                    and w.window_text().startswith(('钢琴卷帘','Piano roll'))]
        return candidates[0] if len(candidates)==1 else None
    roll=wait_for(piano,description='unique Piano Roll window')
    host._keys('^a{DELETE}',roll)  # clear only inside identified editor; independent FLP post-check is mandatory
    if notes:
        host._keys('^m',roll);host.file_dialog(midi)
    guard()
    result=host.save_as_no_image(after_path,saved['title'])
    actual=result['saved_state']
    invariants=state_invariants(state,actual)
    matched=(basic_score(actual,pattern,channel)==notes and untouched(state,pattern,channel)==untouched(actual,pattern,channel)
             and state.get('bpm')==actual.get('bpm') and all(invariants.values()))
    return dict(ok=matched,verified=matched,execution_kind='native_MIDI_import_keyboard_UIA_fallback',
        actual_notes=basic_score(actual,pattern,channel),before_checkpoint=saved['path'],after_checkpoint=result['path'],title=result['title'],
        unchanged_other_note_records=untouched(state,pattern,channel)==untouched(actual,pattern,channel),
        unchanged_state=invariants,
        screenshots=0,mouse_operations=0,
        limitation='Only observed basic MIDI style. Not direct Score API, full proprietary-note CRUD or Playlist arrangement. On mismatch preserve checkpoints and inspect before retry.')
