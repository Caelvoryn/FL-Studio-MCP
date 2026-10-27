"""Phase 1B MCP tools: plugin parameter control.

- fl_plugin_list(track)              -> filled effect slots on a mixer track
- fl_plugin_get_params(track, slot)  -> every named param (name, value, string)
- fl_plugin_set_param(track, slot, param, value)
       ``param`` may be an int index OR a param name (e.g. "Decay time").
       Names are resolved server-side from the live param list. The write
       routes through ``safety.safe_write`` so it is logged + rollback-able.

Native FL plugins (Fruity Parametric EQ 2, Reeverb 2, ...) expose real param
names and small counts, so name-based addressing is reliable for them. VST/AU
wrappers can report thousands of generic slots; for those prefer int indices.

Values are NORMALISED 0..1 (FL's setParamValue domain). The display string
from fl_plugin_get_params (e.g. '3.6dB', '500Hz') tells you what a given
normalised value maps to -- there is no generic unit->normalised conversion.
"""

from __future__ import annotations

from typing import Annotated, Union

from fastmcp import FastMCP
from pydantic import Field

from .. import protocol, safety
from ..connection import FLBridgeError, fetch_all_pages, get_bridge
from ..workflow import WorkflowError


class ParamNotFound(ValueError):
    """Raised when a param name cannot be resolved to a single index."""


def _norm(s) -> str:
    """Lowercase + strip non-alphanumerics, for forgiving name matching."""
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def resolve_param_index(bridge, track: int, slot: int, param):
    """Resolve ``param`` (int index or str name) to a concrete ``(index, name)``.

    Integer (or integer-like) params are used directly, with the name looked
    up for the response. String params are matched against the live param
    list: exact normalised match first, then a unique substring match.
    Ambiguous or missing names raise :class:`ParamNotFound` with the candidate
    list, so the caller can correct the spelling rather than poke a wrong knob.
    """
    if isinstance(param, bool):                       # guard: bool is an int subclass
        raise ParamNotFound("param must be an index or a name, not a bool")
    if isinstance(param, int) or (isinstance(param, str) and param.lstrip("-").isdigit()):
        idx = int(param)
        one = bridge.call(protocol.CMD_PLUGIN_GET_PARAM,
                          {"track": track, "slot": slot, "param": idx})
        return idx, one.get("name", "")

    want = _norm(param)
    if not want:
        raise ParamNotFound("empty param name")

    dump = fetch_all_pages(bridge, protocol.CMD_PLUGIN_GET_PARAMS, "params",
                           {"track": track, "slot": slot})
    params = dump.get("params", [])

    exact = [p for p in params if _norm(p["name"]) == want]
    if len(exact) == 1:
        return exact[0]["i"], exact[0]["name"]
    if len(exact) > 1:
        raise ParamNotFound("param name %r is ambiguous: %s"
                            % (param, [p["name"] for p in exact]))

    subs = [p for p in params if want in _norm(p["name"])]
    if len(subs) == 1:
        return subs[0]["i"], subs[0]["name"]
    if len(subs) > 1:
        raise ParamNotFound("param name %r matches several: %s"
                            % (param, [p["name"] for p in subs][:12]))

    raise ParamNotFound("no param named %r on track %d slot %d; available: %s"
                        % (param, track, slot, [p["name"] for p in params][:20]))


def register(mcp: FastMCP) -> None:
    _RO = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True}
    _WR = {"readOnlyHint": False, "destructiveHint": False,
           "idempotentHint": True, "openWorldHint": True}

    @mcp.tool(annotations={"title": "List plugins on a mixer track", **_RO})
    def fl_plugin_list(
        track: Annotated[int, Field(ge=0, description="Mixer track index (0 = Master).")],
    ) -> dict:
        """List the filled effect slots (0-9) on a mixer track, with plugin names.

        We cannot load NEW plugins (FL API limit) -- this only reports plugins
        already present in the project."""
        return get_bridge().call(protocol.CMD_PLUGIN_LIST, {"track": track})

    @mcp.tool(annotations={"title": "Get plugin parameters", **_RO})
    def fl_plugin_get_params(
        track: Annotated[int, Field(ge=0)],
        slot: Annotated[int, Field(ge=-1, le=9, description="Effect slot 0-9; -1 addresses generator on channel index track.")],
    ) -> dict:
        """Every named parameter of the plugin in this slot: index, name,
        normalised value (0..1) and FL's display string (e.g. '3.6dB',
        '500Hz'). Returns {"total", "params":[{"i","name","v","s"}, ...]}."""
        return fetch_all_pages(get_bridge(), protocol.CMD_PLUGIN_GET_PARAMS, "params",
                               {"track": track, "slot": slot})

    @mcp.tool(annotations={"title": "Set plugin parameter", **_WR})
    def fl_plugin_set_param(
        track: Annotated[int, Field(ge=0)],
        slot: Annotated[int, Field(ge=-1, le=9)],
        param: Annotated[Union[int, str],
                         Field(description="Param index (int) or name (str, e.g. 'Decay time').")],
        value: Annotated[float, Field(ge=0.0, le=1.0, description="Normalised 0..1.")],
        expected_value: Annotated[float | None, Field(ge=0.0, le=1.0, description="Optional stale-state guard: refuse unless independent current value matches within 1e-5.")] = None,
    ) -> dict:
        """Set one plugin parameter (normalised 0..1). ``param`` may be an
        index or a name; names are resolved from the live param list. The
        change is logged and undo-able via fl_rollback_last_change. Returns
        before/after plus the resolved {index, name}."""
        bridge = get_bridge()
        idx, name = resolve_param_index(bridge, track, slot, param)
        if expected_value is not None:
            current = bridge.call(protocol.CMD_PLUGIN_GET_PARAM, {"track": track, "slot": slot, "param": idx})
            if abs(current["v"] - expected_value) > 1e-5:
                return WorkflowError("STALE_PARAMETER", "Live plugin parameter changed; no write performed", current=current).result()
        scope = "plugin_param:%d:%d:%d" % (track, slot, idx)
        result = safety.safe_write(
            bridge, tool="plugin_set_param", scope=scope,
            command=protocol.CMD_PLUGIN_SET_PARAM,
            params={"track": track, "slot": slot, "param": idx, "value": value},
            build_restore=lambda b: {"command": protocol.CMD_PLUGIN_SET_PARAM,
                                     "params": {"track": track, "slot": slot,
                                                "param": idx, "value": b["v"]}})
        if isinstance(result, dict):
            result["resolved_param"] = {"index": idx, "name": name}
        return result

    @mcp.tool(annotations={"title": "Read bounded live plugin state", **_RO})
    def fl_plugin_state(track: Annotated[int, Field(ge=0)], slot: Annotated[int, Field(ge=-1, le=9)],
                        start: Annotated[int, Field(ge=0)] = 0, complete: bool = False,
                        expected_channel: str | None = None) -> dict:
        """Read actual plugin values/display strings. slot=-1 addresses current Channel Rack FILTER index, not necessarily native FLP global channel: select All through GUI and pass expected_channel for pre/post name guards. Effects use Mixer track/slot. complete=true reads at most4096 parameters within60s on stopped transport, with real single-parameter fallback if a page fails; it is non-atomic. Missing/mismatched values fail, never filled. Not preset identity or full proprietary state."""
        try:
            bridge=get_bridge()
            def verify_channel():
                if expected_channel is None:return
                if slot!=-1:
                    raise WorkflowError('INVALID_ARGUMENT','expected_channel is for Channel Rack generators only')
                channels=fetch_all_pages(bridge,protocol.CMD_CHANNEL_LIST,'channels')['channels']
                matches=[c for c in channels if c['i']==track]
                if len(matches)!=1 or matches[0]['name']!=expected_channel:
                    raise WorkflowError('CHANNEL_FILTER_MISMATCH','Live Channel Rack filter/index does not address expected generator; select All through GUI and reobserve',expected=expected_channel,actual=matches)
            verify_channel()
            if complete and (start!=0 or bridge.call('get_play_state').get('playing')):
                return WorkflowError('INVALID_READ_STATE','Complete snapshot requires start0 and stopped transport').result()
            result = bridge.call(protocol.CMD_PLUGIN_GET_PARAMS, {"track": track, "slot": slot, "start": start})
            if complete:
                import time
                began=time.monotonic();total=result['total'];params=list(result['params']);cursor=start
                if not 0<=total<=4096:
                    return WorkflowError('PARAMETER_LIMIT','At most 4096 live parameters per snapshot').result()
                while len(params)<total:
                    following=result.get('next_start')
                    if time.monotonic()-began>60 or following is None or following<=cursor:
                        return WorkflowError('PARAMETER_SNAPSHOT_INCOMPLETE','Parameter pages exceeded deadline or stopped progressing',read=len(params),total=total).result()
                    cursor=following
                    time.sleep(.03)  # let FL's MIDI/UI idle queue drain between read-only pages
                    try:
                        page=bridge.call(protocol.CMD_PLUGIN_GET_PARAMS,{'track':track,'slot':slot,'start':cursor})
                    except FLBridgeError as page_error:
                        # Some installed controller pages are not received.
                        # Single reads are idempotent and use smaller replies;
                        # no controller replacement or guessed values required.
                        result=dict(result,snapshot_mode='single_parameter_fallback',failed_page=cursor,page_failure=str(page_error))
                        known={p['i'] for p in params}
                        for index in range(total):
                            if index in known:continue
                            if time.monotonic()-began>60:
                                return WorkflowError('PARAMETER_SNAPSHOT_INCOMPLETE','Single-read fallback exceeded 60 seconds',read=len(params),total=total).result()
                            one=bridge.call(protocol.CMD_PLUGIN_GET_PARAM,{'track':track,'slot':slot,'param':index})
                            if one.get('param')!=index or 'v' not in one:
                                return WorkflowError('PLUGIN_RESPONSE_MISMATCH','Single parameter response does not match requested index').result()
                            params.append(dict(i=index,name=one.get('name',''),v=one['v'],s=one.get('s','')))
                            time.sleep(.005)
                        break
                    if page['total']!=total or page['plugin']!=result['plugin']:
                        return WorkflowError('PLUGIN_CHANGED','Plugin identity/count changed during snapshot').result()
                    params.extend(page['params']);result=dict(result,next_start=page.get('next_start'))
                if sorted(p['i'] for p in params)!=list(range(total)):
                    return WorkflowError('PARAMETER_SNAPSHOT_INCOMPLETE','Live parameter indices are not complete and unique').result()
                import math
                if any(not isinstance(p.get('v'),(int,float)) or not math.isfinite(p['v']) or not 0<=p['v']<=1 for p in params):
                    return WorkflowError('PLUGIN_RESPONSE_MISMATCH','Parameter values must be actual finite normalized readings').result()
                result=dict(result,params=sorted(params,key=lambda p:p['i']),next_start=None,duration_seconds=time.monotonic()-began,snapshot_atomic=False)
            verify_channel()
        except WorkflowError as exc:
            return exc.result()
        except FLBridgeError as exc:
            return WorkflowError("PLUGIN_READ_FAILED", str(exc), track=track, slot=slot,
                                 page_start=locals().get('cursor',start),completed_parameters=len(locals().get('params',[]))).result()
        return {"ok": True, "verified": True, "state_kind": "live_parameter_snapshot" if complete else "live_parameter_page", "track": track, "slot": slot,
                "readback": result, "index_scope": "Current Channel Rack filter for generators; Mixer track for effects",
                "limitation": "Use expected_channel for generator identity. Parameter names may be mojibake; not a preset identity or complete proprietary-state dump"}
