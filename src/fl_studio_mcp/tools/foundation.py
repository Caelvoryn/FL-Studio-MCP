"""Structured project foundation over commands already in the installed bridge.

No controller replacement, arbitrary evaluation, images or musical FLP rewriting.
Saved Playlist/automation data is explicitly separate from live host state.
"""
import math
import time
from pathlib import Path

from ..connection import get_bridge,fetch_all_pages,FLBridgeError
from ..workflow import WorkflowError


def _error(code,message,**details):raise WorkflowError(code,message,**details)


def _numeric(v,low,high):
    return not isinstance(v,bool) and isinstance(v,(int,float)) and math.isfinite(v) and low<=v<=high


def project_state(bridge,checkpoint=None):
    before=bridge.call('get_project_state')
    result=dict(ok=True,verified=True,atomic=False,source='live FL MIDI bridge',project=before,
        channels=fetch_all_pages(bridge,'channel_list','channels'),
        channel_routing=fetch_all_pages(bridge,'channel_routing_summary','channels'),
        patterns=fetch_all_pages(bridge,'pattern_list','patterns'),
        mixer=fetch_all_pages(bridge,'mixer_list_tracks','tracks'),
        mixer_routing=fetch_all_pages(bridge,'mixer_get_routing_all','routing'))
    after=bridge.call('get_project_state')
    if before!=after:_error('PROJECT_CHANGED','Project summary changed during non-atomic read',before=before,after=after)
    result['playlist']=dict(source='not available from current live bridge',verified=False)
    result['automation']=dict(source='not available from current live bridge',verified=False)
    if checkpoint:
        from ..native import inspect
        state=inspect(Path(checkpoint).resolve())
        result['saved_checkpoint']=dict(source='saved FLP, NOT live memory',path=state['path'],sha256=state['sha256'],
            bpm=state.get('bpm'),ppq=state['ppq'],patterns=state['patterns'],channels=state['channels'],
            playlist=state['playlist'],automation=state['automation'],
            limitation='May be stale. Save As through FL first; no claim that saved clip data is live state.')
    return result


def validate_edits(edits):
    if not isinstance(edits,list) or not 1<=len(edits)<=32:_error('INVALID_ARGUMENT','1..32 edits required')
    seen=set()
    for e in edits:
        if not isinstance(e,dict) or e.get('kind') not in ('tempo','channel_volume','channel_pan','mixer_volume','mixer_pan','mixer_name'):
            _error('INVALID_ARGUMENT','Unsupported edit kind; no arbitrary bridge commands')
        kind=e['kind'];required={'kind','value','expected_value'}
        if kind!='tempo':required|={'index','expected_name'}
        if set(e)!=required:_error('INVALID_ARGUMENT','Exact edit fields required',required=sorted(required))
        if kind!='tempo' and (type(e['index']) is not int or e['index']<0 or not isinstance(e['expected_name'],str) or not e['expected_name']):
            _error('INVALID_ARGUMENT','Nonnegative index and exact name required')
        key=(kind,e.get('index',0))
        if key in seen:_error('INVALID_ARGUMENT','Duplicate edits are not allowed')
        seen.add(key)
        if kind=='mixer_name':
            if any(not isinstance(e[k],str) or not 1<=len(e[k])<=24 for k in ('value','expected_value')):
                _error('INVALID_ARGUMENT','Names must be1..24 characters')
        else:
            bounds=(20,300) if kind=='tempo' else (-1,1) if kind.endswith('pan') else (0,1)
            if any(not _numeric(e[k],*bounds) for k in ('value','expected_value')):_error('INVALID_ARGUMENT','Finite values outside supported range')
    # Keep identities stable during the batch: rename cannot share a target with
    # other mixer edits. Use a fresh observation and a separate batch afterwards.
    for e in edits:
        if e['kind']=='mixer_name' and any(x is not e and x['kind'].startswith('mixer_') and x['index']==e['index'] for x in edits):
            _error('INVALID_ARGUMENT','Separate mixer rename from other edits on that track')


def batch_edit(bridge,edits):
    validate_edits(edits)
    records=[];began=time.monotonic()
    def read(e):
        if time.monotonic()-began>30:_error('DEADLINE','Batch exceeded30s; no automatic retry')
        kind=e['kind']
        if kind=='tempo':return bridge.call('get_tempo'), 'bpm'
        project=bridge.call('get_project_state')
        count=project.get('channel_count' if kind.startswith('channel_') else 'mixer_track_count')
        if type(count)is not int or not 0<=e['index']<count:
            _error('INVALID_TARGET','Index outside current live host count; native item reader not called',index=e['index'],count=count)
        row=bridge.call('channel_get' if kind.startswith('channel_') else 'mixer_get_track',{'index':e['index']})
        if row.get('i')!=e['index'] or row.get('name')!=e['expected_name']:
            _error('TARGET_CHANGED','Live target identity differs',actual=row)
        return row, 'vol_norm' if kind.endswith('volume') else 'pan' if kind.endswith('pan') else 'name'
    def equal(a,b):
        return a==b if isinstance(b,str) else _numeric(a,-1000,1000) and abs(a-b)<=.00011
    try:
        transport=bridge.call('get_play_state')
        if transport.get('playing') is not False or transport.get('recording',False):_error('TRANSPORT_ACTIVE','Stop transport/recording before batch')
        for e in edits:
            row,key=read(e)
            if not equal(row.get(key),e['expected_value']):_error('STALE_VALUE','Preflight current value differs',actual=row)
        for e in edits:
            before,key=read(e)
            if not equal(before.get(key),e['expected_value']):_error('STALE_VALUE','Value changed after preflight',actual=before)
            kind=e['kind'];params={'bpm':e['value']} if kind=='tempo' else {
                ('channel' if kind.startswith('channel_') else 'track'):e['index'],
                ('name' if kind.endswith('name') else 'value'):e['value']}
            if kind.endswith('volume'):params['unit']='normalized'
            record=dict(edit=e,before=before,write_attempted=True,verified=False);records.append(record)
            bridge.call('set_tempo' if kind=='tempo' else kind.split('_')[0]+'_set_'+kind.split('_')[1],params)
            check=dict(e,expected_name=e['value']) if kind=='mixer_name' else e
            after,key=read(check);record['after']=after
            if not equal(after.get(key),e['value']):_error('READBACK_MISMATCH','Independent host read differs',actual=after)
            record['verified']=True
        return dict(ok=True,verified=True,atomic=False,execution_kind='direct_host_API',changes=records,persistence_verified=False)
    except (WorkflowError,FLBridgeError) as exc:
        result=exc.result() if isinstance(exc,WorkflowError) else WorkflowError('BRIDGE_FAILED',str(exc)).result()
        result.update(changes=records,atomic=False,recovery='Inspect actual state before retry; no automatic replay/rollback')
        return result


def guard_route(rows,src,dst,enabled):
    graph={r['i']:{d['dst'] for d in r['routes_to']} for r in rows}
    if type(src)is not int or type(dst)is not int or src<=0 or src==dst or src not in graph or dst not in graph:
        _error('INVALID_ROUTE','No Master source, self route or nonexistent track')
    def reaches(start,target):
        pending=[start];seen=set()
        while pending:
            node=pending.pop()
            if node==target:return True
            if node in seen:continue
            seen.add(node);pending.extend(graph.get(node,set())-seen)
        return False
    if enabled:
        if reaches(dst,src):_error('ROUTING_FEEDBACK','Route would create feedback')
        graph[src].add(dst)
    else:
        graph[src].discard(dst)
        if not reaches(src,0):_error('ROUTING_DISCONNECT','Disabling would remove every path to Master')


def register(mcp):
    @mcp.tool(annotations=dict(readOnlyHint=True,idempotentHint=True))
    def fl_foundation_state(checkpoint_path: str|None=None)->dict:
        """Live BPM/channel/Pattern/Mixer/routing state. Optional FLP notes/Playlist/automation are SAVED
        checkpoint data, never mislabeled live state. Non-atomic, Channel Rack filter applies."""
        try:return project_state(get_bridge(),checkpoint_path)
        except (WorkflowError,FLBridgeError,OSError,ValueError) as exc:
            return exc.result() if isinstance(exc,WorkflowError) else WorkflowError('STATE_READ_FAILED',str(exc)).result()

    @mcp.tool(annotations=dict(readOnlyHint=False,destructiveHint=False,idempotentHint=False))
    def fl_foundation_batch(edits:list[dict],expected_title:str)->dict:
        """Opt-in direct-host batch for BPM, channel volume/pan, mixer volume/pan/name. Max32.
        Exact old value/name guards and independent reads. Requires owned independent saved session
        from fl_host_project_file; stopped transport. Sequential/partial on failure, never retried.
        Normalized volume only, not assumed exact dB. No channel creation, routing or automation claim."""
        try:
            validate_edits(edits)
            from ..host_io import HostFiles
            HostFiles()._require_owned(expected_title)
            return batch_edit(get_bridge(),edits)
        except (WorkflowError,FLBridgeError,OSError) as exc:
            return exc.result() if isinstance(exc,WorkflowError) else WorkflowError('FOUNDATION_FAILED',str(exc)).result()

    @mcp.tool(annotations=dict(readOnlyHint=False,destructiveHint=False,idempotentHint=False))
    def fl_foundation_pattern(action:str,name:str,expected_count:int,expected_title:str,source:int|None=None)->dict:
        """Direct host new/clone Pattern with count/name readback. Does not arrange Playlist or write notes.
        Clone source must exist. Non-idempotent: never replay on timeout; read state first.
        Save As and inspect native notes separately to establish actual clone contents."""
        try:
            if action not in ('new','clone') or not isinstance(name,str) or not 1<=len(name)<=24 or type(expected_count)is not int or expected_count<0:
                _error('INVALID_ARGUMENT','new/clone, name1..24 and exact expected count required')
            from ..host_io import HostFiles
            HostFiles()._require_owned(expected_title)
            b=get_bridge()
            if b.call('get_play_state').get('playing') is not False:_error('TRANSPORT_ACTIVE','Stop transport')
            before=fetch_all_pages(b,'pattern_list','patterns')
            if before['total']!=expected_count:_error('STALE_VALUE','Pattern count differs',actual=before)
            if action=='clone' and (type(source)is not int or source not in [p['pattern'] for p in before['patterns']]):
                _error('INVALID_SOURCE','Clone source does not exist')
            ack=b.call('arrange_new_pattern',{'name':name}) if action=='new' else b.call('arrange_clone_pattern',{'src':source,'new_name':name})
            after=fetch_all_pages(b,'pattern_list','patterns')
            selected=b.call('get_project_state')['pattern_number']
            matches=[p for p in after['patterns'] if p['pattern']==selected and p['name']==name]
            verified=after['total']==expected_count+1 and len(matches)==1
            return dict(ok=verified,verified=verified,execution_kind='direct_host_API',acknowledgement=ack,before=before,after=after,
                selected_pattern=selected,notes_verified=False,
                index_stability='Clone may insert after source and renumber existing Patterns; reobserve all indices, never assume append',
                limitation='Count/name checked, not note content; no Playlist edits')
        except (WorkflowError,FLBridgeError,OSError) as exc:
            return exc.result() if isinstance(exc,WorkflowError) else WorkflowError('PATTERN_FAILED',str(exc)).result()

    @mcp.tool(annotations=dict(readOnlyHint=False,destructiveHint=False,idempotentHint=False))
    def fl_foundation_route(src:int,dst:int,enabled:bool,expected_enabled:bool,
                             expected_source_name:str,expected_destination_name:str,expected_title:str)->dict:
        """Direct Mixer send on/off with live graph checks, feedback and Master-disconnect protection.
        Requires exact observed names/old route and owned stopped test session. Reads actual route after
        write. Does NOT assign instrument channels, set send amount or insert effects. No blind retry."""
        attempted=False;before=None
        try:
            from ..host_io import HostFiles
            HostFiles()._require_owned(expected_title)
            b=get_bridge()
            if b.call('get_play_state').get('playing') is not False:_error('TRANSPORT_ACTIVE','Stop transport')
            rows=fetch_all_pages(b,'mixer_get_routing_all','routing')['routing']
            guard_route(rows,src,dst,enabled)
            names={r['i']:r['name'] for r in rows}
            if names[src]!=expected_source_name or names[dst]!=expected_destination_name:_error('TARGET_CHANGED','Mixer names differ')
            before=b.call('mixer_get_routing',{'track':src})
            old=any(r['dst']==dst for r in before['routes_to'])
            if old!=expected_enabled:_error('STALE_ROUTE','Route differs',actual=before)
            attempted=True;b.call('mixer_set_route',dict(src=src,dst=dst,enabled=enabled))
            after=b.call('mixer_get_routing',{'track':src})
            actual=any(r['dst']==dst for r in after['routes_to'])
            verified=actual==enabled
            return dict(ok=verified,verified=verified,execution_kind='direct_host_API',before=before,after=after,persistence_verified=False)
        except (WorkflowError,FLBridgeError,OSError) as exc:
            result=exc.result() if isinstance(exc,WorkflowError) else WorkflowError('ROUTE_FAILED',str(exc)).result()
            return dict(result,write_attempted=attempted,before=before,recovery='Read actual route before retry; no automatic replay')
