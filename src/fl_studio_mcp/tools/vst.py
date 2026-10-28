"""Bounded host control plus explicit, independently checked native-picker fallback."""
from __future__ import annotations

import math
import time

from ..connection import get_bridge, fetch_all_pages, FLBridgeError
from ..workflow import WorkflowError


def _fail(code, message, **details):
    raise WorkflowError(code, message, **details)


def _number(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and 0 <= value <= 1)


def _identity(bridge, track, slot, expected_plugin, expected_channel=None):
    if type(track) is not int or track < 0 or type(slot) is not int or not -1 <= slot <= 9:
        _fail('INVALID_TARGET', 'Use channel/filter index with slot=-1, or Mixer index/slot0..9')
    if not expected_plugin:
        _fail('INVALID_TARGET', 'An exact observed plugin name is required')
    if slot == -1:
        if not expected_channel:
            _fail('INVALID_TARGET', 'Generator requires exact observed channel name')
        channels = fetch_all_pages(bridge, 'channel_list', 'channels')['channels']
        matches = [c for c in channels if c['i'] == track]
        if len(matches) != 1 or matches[0]['name'] != expected_channel:
            _fail('TARGET_CHANGED', 'Current Channel Rack filter/name differs', actual=matches)
    page = bridge.call('plugin_get_params', dict(track=track, slot=slot, start=0))
    if page.get('plugin') != expected_plugin:
        _fail('TARGET_CHANGED', 'Host plugin name differs', actual=page.get('plugin'))
    return page


def parameter_page(bridge, track, slot, expected_plugin, expected_channel=None, start=0):
    if type(start) is not int or start < 0:
        _fail('INVALID_ARGUMENT', 'start must be a nonnegative integer')
    first = _identity(bridge, track, slot, expected_plugin, expected_channel)
    page = first if start == 0 else bridge.call('plugin_get_params', dict(track=track, slot=slot, start=start))
    after = _identity(bridge, track, slot, expected_plugin, expected_channel)
    if page.get('plugin') != expected_plugin or page.get('total') != after.get('total'):
        _fail('TARGET_CHANGED', 'Plugin/count changed while reading')
    return dict(ok=True, host_scope='FL Studio', readback=page,
                preset_identity=None, limitation='Named parameters only; page may be sparse. Not full plugin state or preset identity.')


def batch_parameters(bridge, track, slot, expected_plugin, changes, expected_channel=None, timeout=20):
    """Preflight entire batch, then sequential read/write/read. Never retry a write."""
    if not isinstance(changes, list) or not 1 <= len(changes) <= 32:
        _fail('INVALID_ARGUMENT', 'Batch requires 1..32 changes')
    seen = set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != {'param', 'name', 'expected_value', 'value', 'tolerance'}:
            _fail('INVALID_ARGUMENT', 'Each change requires param,name,expected_value,value,tolerance')
        i = change['param']
        if type(i) is not int or i < 0 or i in seen or not change['name']:
            _fail('INVALID_ARGUMENT', 'Parameter indices must be unique, nonnegative and named')
        seen.add(i)
        if not all(_number(change[k]) for k in ('expected_value', 'value', 'tolerance')) or not .0001 <= change['tolerance'] <= .01:
            _fail('INVALID_ARGUMENT', 'Finite normalized values and explicit tolerance .0001.. .01 required')
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 1 <= timeout <= 60:
        _fail('INVALID_ARGUMENT', 'timeout must be 1..60 seconds')
    began = time.monotonic()
    records = []
    def deadline():
        if time.monotonic() - began > timeout:
            _fail('DEADLINE', 'Batch deadline exceeded; no automatic retry')
    def read(change):
        deadline()
        value = bridge.call('plugin_get_param', dict(track=track, slot=slot, param=change['param']))
        if value.get('param') != change['param'] or value.get('name') != change['name'] or not _number(value.get('v')):
            _fail('PARAMETER_CHANGED', 'Parameter identity/value does not match', actual=value)
        return value
    try:
        if bridge.call('get_play_state').get('playing') is not False:
            _fail('TRANSPORT_ACTIVE', 'Stop transport before batch writes')
        page = _identity(bridge, track, slot, expected_plugin, expected_channel)
        for change in changes:
            if change['param'] >= page['total']:
                _fail('INVALID_ARGUMENT', 'Parameter index outside host count')
            current = read(change)
            if abs(current['v'] - change['expected_value']) > .00011:
                _fail('STALE_PARAMETER', 'Preflight value differs', actual=current)
        for change in changes:
            deadline()
            _identity(bridge, track, slot, expected_plugin, expected_channel)
            before = read(change)
            if abs(before['v'] - change['expected_value']) > .00011:
                _fail('STALE_PARAMETER', 'Parameter changed after preflight', actual=before)
            entry = dict(param=change['param'], name=change['name'], before=before,
                         requested=change['value'], write_attempted=True, verified=False)
            records.append(entry)  # retain uncertain write if response times out
            bridge.call('plugin_set_param', dict(track=track, slot=slot, param=change['param'], value=change['value']))
            after = read(change)  # independent command, not the write acknowledgement
            entry['after'] = after
            _identity(bridge, track, slot, expected_plugin, expected_channel)
            if abs(after['v'] - change['value']) > change['tolerance']:
                _fail('READBACK_MISMATCH', 'Host did not retain requested value', actual=after)
            entry['verified'] = True
        return dict(ok=True, verified=True, atomic=False, host_scope='FL Studio', changes=records,
                    preset_switch_verified=False, persistence_verified=False)
    except (WorkflowError, FLBridgeError) as exc:
        result = exc.result() if isinstance(exc, WorkflowError) else WorkflowError('BRIDGE_FAILED', str(exc)).result()
        result.update(atomic=False, changes=records, recovery='Observe actual state before retry; no automatic rollback to a possibly replaced plugin')
        return result


def register(mcp):
    ro = dict(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

    @mcp.tool(annotations=dict(readOnlyHint=False,destructiveHint=False,idempotentHint=False))
    def fl_vst_assign_free_mixer(channel:int,expected_channel:str,expected_old_target:int,expected_title:str)->dict:
        """Explicit no-image KEYBOARD fallback: Channel Rack Ctrl+L assigns selected generator to
        a free Mixer track. Requires exact observed old assignment/name, stopped owned test project.
        Calls documented native shortcut once, independently reads actual assignment. Does not
        promise a specified destination, insert FX or create a reverb send. Never blindly replay."""
        try:
            from ..host_io import HostFiles
            from ..desktop import wait_for
            host=HostFiles();host._require_owned(expected_title);b=get_bridge()
            project=b.call('get_project_state')
            if project['playing'] or project['recording'] or type(channel)is not int or not 0<=channel<project['channel_count']:
                _fail('INVALID_ROUTING_STATE','Stopped transport and valid channel required')
            before=b.call('channel_get',{'index':channel})
            if before['name']!=expected_channel or before['target_fx_track']!=expected_old_target:
                _fail('STALE_CHANNEL','Channel name or old assignment differs',actual=before)
            b.call('channel_select',{'channel':channel})
            host.focus(expected_title)
            def rack():
                rows=[w for w in host.main.descendants() if w.class_name()=='TStepSeqForm' and w.is_visible()]
                return rows[0] if len(rows)==1 else None
            if rack() is None:host._keys('{F6}')
            target=wait_for(rack,description='unique visible Channel Rack')
            host._keys('^l',target)
            def assigned():
                current=b.call('channel_get',{'index':channel})
                if current['name']!=expected_channel:_fail('TARGET_CHANGED','Channel identity changed')
                return current if current['target_fx_track']!=expected_old_target else None
            after=wait_for(assigned,timeout=10,description='actual new channel-to-Mixer assignment')
            dst=after['target_fx_track']
            if type(dst)is not int or not 0<dst<project['mixer_track_count']:_fail('INVALID_ROUTING_STATE','Unexpected destination',actual=after)
            mixer=b.call('mixer_get_track',{'index':dst})
            return dict(ok=True,verified=True,execution_kind='native_ChannelRack_shortcut_fallback',before=before,after=after,
                        mixer=mixer,screenshots=0,mouse_operations=0,persistence_verified=False)
        except (WorkflowError,FLBridgeError) as exc:
            return exc.result() if isinstance(exc,WorkflowError) else WorkflowError('ASSIGNMENT_UNVERIFIED',str(exc)).result()
        except Exception as exc:return WorkflowError('ASSIGNMENT_UNVERIFIED',str(exc),exception_type=type(exc).__name__).result()

    @mcp.tool(annotations=dict(readOnlyHint=False,destructiveHint=False,idempotentHint=False))
    def fl_vst_keyboard_load(search:str,expected_plugin:str,expected_title:str,expected_channel:str,action:str='load',
                            mixer_track:int|None=None,expected_mixer_name:str|None=None)->dict:
        """Explicit native F8 picker KEYBOARD FALLBACK, not internal VST instantiation API.
        No screenshots/mouse. Requires owned saved test session, stopped transport, no existing
        matching channel. Accepts plain ASCII search only. Verifies exactly one added channel,
        existing indices/names unchanged, actual plugin name and real parameter page. Variant
        (VST2/3) not established by name; save FLP and inspect actual plugin path separately.
        action='cancel' cancels exactly one identified native plugin picker without loading anything.
        Generator acceptance: Pianoteq9 and Sylenth1. Optional mixer_track loads an effect only
        when the visible Mixer caption matches expected_mixer_name; verifies additive slots and
        unchanged channels. EQ2/Compressor/Reeverb2 tested on one selected track. No arbitrary
        Mixer selection, slot placement or universal plugin compatibility. No blind retry."""
        try:
            import re
            from ..host_io import HostFiles
            from ..desktop import wait_for
            if not re.fullmatch(r'[A-Za-z0-9 _.-]{1,48}',search) or not expected_plugin or (mixer_track is None and not expected_channel):
                _fail('INVALID_ARGUMENT','Plain ASCII picker search and exact expected names required')
            host=HostFiles();host._require_owned(expected_title)
            if action not in {'load','cancel'}:_fail('INVALID_ARGUMENT','load or cancel required')
            if action=='cancel':
                if host.main.window_text()!=expected_title:_fail('TARGET_CHANGED','Project title differs')
                rows=[w for w in host.win32.windows(process=host.pid,class_name='TPlugListForm') if w.is_visible()]
                if len(rows)!=1:_fail('PICKER_NOT_UNIQUE','Exactly one owned native plugin picker required')
                host._keys('{ESC}',rows[0])
                wait_for(lambda:host.main.is_enabled() and not rows[0].is_visible(),description='owned picker cancelled')
                return dict(ok=True,verified=True,operation='cancel_picker',execution_kind='native_picker_keyboard_fallback',screenshots=0,mouse_operations=0)
            bridge=get_bridge()
            if bridge.call('get_play_state').get('playing') is not False:_fail('TRANSPORT_ACTIVE','Stop transport')
            before=fetch_all_pages(bridge,'channel_list','channels')['channels']
            if mixer_track is not None:
                state=bridge.call('get_project_state')
                if type(mixer_track)is not int or not 0<=mixer_track<state['mixer_track_count']:
                    _fail('INVALID_TARGET','Mixer track outside live count')
                track=bridge.call('mixer_get_track',{'index':mixer_track})
                if not expected_mixer_name or track['name']!=expected_mixer_name:
                    _fail('TARGET_CHANGED','Mixer name differs')
                slots=bridge.call('plugin_list',{'track':mixer_track})['slots']
                if len(slots)>=10:_fail('EFFECT_CHAIN_FULL','No free effect slot')
                host.focus(expected_title)
                mixers=[w for w in host.main.descendants() if w.class_name()=='TFXForm' and w.is_visible()]
                if len(mixers)!=1 or not mixers[0].window_text().endswith(' - '+expected_mixer_name):
                    _fail('MIXER_SELECTION_UNVERIFIED','Visible Mixer caption must identify the selected track; no guessing')
                host._keys('{F8}',mixers[0])
                def fx_picker():
                    rows=[w for w in host.win32.windows(process=host.pid,class_name='TPlugListForm') if w.is_visible()]
                    return rows[0] if len(rows)==1 else None
                picker=wait_for(fx_picker,description='native effect picker')
                host._keys(search,picker,unicode_text=True)
                time.sleep(.4)
                host._keys('{DOWN}{ENTER}',picker)
                pending={}
                def effect_loaded():
                    try:
                        after=bridge.call('plugin_list',{'track':mixer_track})['slots']
                        chans=fetch_all_pages(bridge,'channel_list','channels')['channels']
                    except FLBridgeError as exc:pending['read_error']=str(exc);return None
                    pending['slots']=after
                    if [(c['i'],c['name']) for c in before]!=[(c['i'],c['name']) for c in chans]:
                        _fail('WRONG_PLUGIN_CONTEXT','Effect picker changed Channel Rack',actual=chans)
                    previous={s['slot']:s['name'] for s in slots};actual={s['slot']:s['name'] for s in after}
                    if actual==previous:return None
                    if any(actual.get(i)!=name for i,name in previous.items()) or len(actual)!=len(previous)+1:
                        _fail('EFFECT_CHAIN_CHANGED','Expected additive effect load only',actual=after)
                    added=[s for s in after if s['slot'] not in previous]
                    if added[0]['name']=='Fruity Wrapper':return None
                    if added[0]['name']!=expected_plugin:_fail('WRONG_PLUGIN_LOADED','Unexpected effect',actual=added)
                    return dict(track=mixer_track,slot=added[0]['slot'],plugin=expected_plugin,
                        parameter_page=bridge.call('plugin_get_params',dict(track=mixer_track,slot=added[0]['slot'],start=0)))
                try:result=wait_for(effect_loaded,timeout=45,description='actual additive Mixer effect')
                except WorkflowError as exc:exc.details['last_observation']=pending;raise
                return dict(ok=True,verified=True,execution_kind='native_picker_keyboard_fallback',readback=result,
                            screenshots=0,mouse_operations=0,persistence_verified=False)
            if len(before)>32 or any(c['name']==expected_channel for c in before):
                _fail('AMBIGUOUS_LOAD','At most32 existing channels and no duplicate expected channel')
            host.focus(expected_title)
            host._keys('{F8}',host.channel_rack())
            def picker():
                windows=[w for w in host.win32.windows(process=host.pid,class_name='TPlugListForm') if w.is_visible()]
                return windows[0] if len(windows)==1 else None
            window=wait_for(picker,description='native FL plugin picker')
            # Validate characters above: send_keys metacharacters are never accepted.
            host._keys(search,window,unicode_text=True)
            time.sleep(.4)  # let native type-to-filter settle before selecting
            host._keys('{DOWN}{ENTER}',window)
            pending={}
            def loaded():
                try:
                    after=fetch_all_pages(bridge,'channel_list','channels')['channels']
                except FLBridgeError as exc:
                    pending['read_error']=str(exc);return None  # read-only retry while plugin initializes
                if len(after)==len(before):return None
                if len(after)!=len(before)+1 or [(c['i'],c['name']) for c in before]!=[(c['i'],c['name']) for c in after[:len(before)]]:
                    _fail('CHANNEL_TOPOLOGY_CHANGED','Unexpected channel topology after picker load',actual=after)
                new=after[-1]
                pending['channel']=new
                if new['name']=='Fruity Wrapper':return None  # observed loading placeholder, NOT success
                if new['name']!=expected_channel:_fail('WRONG_PLUGIN_LOADED','Added channel name differs',actual=new)
                try:
                    page=bridge.call('plugin_get_params',dict(track=new['i'],slot=-1,start=0))
                except FLBridgeError as exc:
                    pending['read_error']=str(exc);return None
                if page['plugin']!=expected_plugin:_fail('WRONG_PLUGIN_LOADED','Actual hosted plugin differs',actual=page)
                return dict(channel=new,plugin=page['plugin'],parameter_count=page['total'])
            try:result=wait_for(loaded,timeout=45,description='actual added hosted plugin')
            except WorkflowError as exc:
                exc.details['last_observation']=pending
                exc.details['recovery']='Loading command was sent once; observe actual channels before retry, never reload blindly'
                raise
            return dict(ok=True,verified=True,execution_kind='native_picker_keyboard_fallback',readback=result,
                        binary_variant_verified=False,screenshots=0,mouse_operations=0)
        except (WorkflowError,FLBridgeError) as exc:
            return exc.result() if isinstance(exc,WorkflowError) else WorkflowError('PLUGIN_LOAD_UNVERIFIED',str(exc)).result()
        except Exception as exc:
            return WorkflowError('PLUGIN_LOAD_UNVERIFIED',str(exc),exception_type=type(exc).__name__,
                                 recovery='Inspect actual channels before retry; no automatic replay').result()

    @mcp.tool(annotations=ro)
    def fl_vst_find_generators(plugin_contains: str = "Pianoteq", start: int = 0, limit: int = 16) -> dict:
        """Discover actual loaded generators, including renamed channels. Bounded scan of CURRENT
        Channel Rack filter only; does not prove absence from hidden groups. Effects are not scanned.
        Failed reads are reported, not treated as successful discovery."""
        try:
            if type(start) is not int or start < 0 or type(limit) is not int or not 1 <= limit <= 32 or not plugin_contains.strip():
                _fail('INVALID_ARGUMENT', 'Nonempty search, nonnegative start and limit1..32 required')
            bridge = get_bridge()
            channels = fetch_all_pages(bridge, 'channel_list', 'channels')['channels']
            subset = channels[start:start + limit]
            found, errors = [], []
            for channel in subset:
                try:
                    page = bridge.call('plugin_get_params', dict(track=channel['i'], slot=-1, start=0))
                    if plugin_contains.casefold() in page.get('plugin', '').casefold():
                        found.append(dict(track=channel['i'], slot=-1, channel=channel['name'],
                                          plugin=page['plugin'], total_parameters=page['total']))
                except FLBridgeError as exc:
                    errors.append(dict(track=channel['i'], error=str(exc)))
            after = fetch_all_pages(bridge, 'channel_list', 'channels')['channels']
            if [(c['i'], c['name']) for c in channels] != [(c['i'], c['name']) for c in after]:
                _fail('TARGET_CHANGED', 'Channel list changed during discovery')
            return dict(ok=True, instances=found, read_errors=errors,
                        next_start=start + limit if start + limit < len(channels) else None,
                        scope='Current Channel Rack filter; generators only', scanned=len(subset))
        except (WorkflowError, FLBridgeError) as exc:
            return exc.result() if isinstance(exc, WorkflowError) else WorkflowError('BRIDGE_FAILED', str(exc)).result()

    @mcp.tool(annotations=ro)
    def fl_vst_parameter_page(track: int, slot: int, expected_plugin: str,
                              expected_channel: str | None = None, start: int = 0) -> dict:
        """Bounded real host parameter page. Generator index respects current Channel Rack filter.
        Exact names guard against stale targets but cannot distinguish identical duplicate instances.
        No preset switching, UI interaction, or plugin creation."""
        try:
            return parameter_page(get_bridge(), track, slot, expected_plugin, expected_channel, start)
        except (WorkflowError, FLBridgeError) as exc:
            return exc.result() if isinstance(exc, WorkflowError) else WorkflowError('BRIDGE_FAILED', str(exc)).result()

    @mcp.tool(annotations=ro)
    def fl_vst_preset_info(track: int, slot: int, expected_plugin: str,
                           expected_channel: str | None = None) -> dict:
        """Read raw host preset candidates. Names are NOT proven Pianoteq internal preset/model names.
        Does not send Program Change or navigate presets."""
        try:
            bridge = get_bridge()
            _identity(bridge, track, slot, expected_plugin, expected_channel)
            info = bridge.call('plugin_preset', dict(track=track, slot=slot, op='info'))
            _identity(bridge, track, slot, expected_plugin, expected_channel)
            return dict(ok=True, host_scope='FL Studio', raw_host_info=info,
                        internal_preset_name=None, internal_preset_verified=False)
        except (WorkflowError, FLBridgeError) as exc:
            return exc.result() if isinstance(exc, WorkflowError) else WorkflowError('BRIDGE_FAILED', str(exc)).result()

    @mcp.tool(annotations=dict(readOnlyHint=False, destructiveHint=False, idempotentHint=False))
    def fl_vst_batch_parameters(track: int, slot: int, expected_plugin: str, changes: list[dict],
                                expected_channel: str | None = None, timeout: float = 20) -> dict:
        """Opt-in DIRECT_VST_WRITES batch (max32). Requires observed index/name/value and explicit tolerance.
        Separate real reads verify each write. Sequential, non-atomic; failure reports partial/uncertain writes.
        No persistence/preset claims. Use only an independent test project; ensure one responding FL instance."""
        try:
            return batch_parameters(get_bridge(), track, slot, expected_plugin, changes, expected_channel, timeout)
        except (WorkflowError, FLBridgeError) as exc:
            return exc.result() if isinstance(exc, WorkflowError) else WorkflowError('BRIDGE_FAILED', str(exc)).result()
