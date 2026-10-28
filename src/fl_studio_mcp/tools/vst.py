"""Bounded host control; no plugin loading, images, or preset-name guesses."""
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
