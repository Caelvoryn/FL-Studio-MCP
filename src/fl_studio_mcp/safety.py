"""Safety layer: snapshot / changelog / rollback / dry-run for write tools.

Lives on the MCP-SERVER side -- the server can do file I/O, the FL controller
script cannot. Supported scalar writes route through :func:`safe_write`, which
snapshots the affected scope, logs the change, executes, reads back, and
returns before+after so the caller (and a human) can see exactly what changed.
"""

from __future__ import annotations

import os
import json
import threading
import time
from collections import deque
from pathlib import Path

from .protocol import (
    CMD_MIXER_GET_TRACK,
    CMD_CHANNEL_GET,
    CMD_MIXER_LIST_TRACKS,
    CMD_CHANNEL_LIST,
    CMD_PLUGIN_GET_PARAM,
    CMD_MIXER_GET_ROUTING,
)


_DIR = Path(os.environ.get("FLSTUDIO_MCP_STATE_DIR", str(Path.home() / ".flstudio-mcp-system")))
_PATH = _DIR / "changelog.jsonl"
_MAX = 50


class ChangeLog:
    """Rolling deque of the last ``_MAX`` writes, persisted to a jsonl file."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._dq: deque = deque(maxlen=_MAX)
        self._load()

    def _load(self) -> None:
        try:
            if _PATH.exists():
                for line in _PATH.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line:
                        self._dq.append(json.loads(line))
        except Exception:
            pass

    def _persist(self) -> None:
        from .workflow import atomic_json
        # Existing JSONL format retained; atomic replace prevents torn journal.
        import uuid
        _DIR.mkdir(parents=True, exist_ok=True)
        temp = _PATH.with_name(_PATH.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temp.open("x", encoding="utf8") as stream:
                stream.write("".join(json.dumps(e) + "\n" for e in self._dq))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, _PATH)
        finally:
            temp.unlink(missing_ok=True)

    def append(self, entry: dict) -> None:
        with self._lock:
            self._dq.append(entry)
            self._persist()

    def pop_last(self):
        with self._lock:
            if not self._dq:
                return None
            entry = self._dq.pop()
            self._persist()
            return entry

    def recent(self, n: int = 10) -> list:
        with self._lock:
            return list(self._dq)[-n:]


_log = ChangeLog()
_dry_run = False


def set_dry_run(enabled) -> dict:
    global _dry_run
    _dry_run = bool(enabled)
    return {"dry_run": _dry_run}


def is_dry_run() -> bool:
    return _dry_run


def get_changelog() -> ChangeLog:
    return _log


def take_snapshot(bridge, scope):
    """Read current state for a scope so it can be restored or recorded.

    scope: "mixer_track:N" | "channel:N" | "mixer_all" | "channels_all"
           | "plugin_param:TRACK:SLOT:PARAM"
    """
    kind, _, arg = str(scope).partition(":")
    if kind == "mixer_track":
        return bridge.call(CMD_MIXER_GET_TRACK, {"index": int(arg)})
    if kind == "channel":
        return bridge.call(CMD_CHANNEL_GET, {"index": int(arg)})
    if kind == "plugin_param":
        track, slot, idx = (int(x) for x in arg.split(":"))
        return bridge.call(CMD_PLUGIN_GET_PARAM,
                           {"track": track, "slot": slot, "param": idx})
    if kind == "route":
        src, dst = (int(x) for x in arg.split(":"))
        info = bridge.call(CMD_MIXER_GET_ROUTING, {"track": src})
        enabled = any(d.get("dst") == dst for d in info.get("routes_to", []))
        return {"src": src, "dst": dst, "enabled": enabled}
    if kind == "mixer_all":
        from .connection import fetch_all_pages
        return fetch_all_pages(bridge, CMD_MIXER_LIST_TRACKS, "tracks")
    if kind == "channels_all":
        from .connection import fetch_all_pages
        return fetch_all_pages(bridge, CMD_CHANNEL_LIST, "channels")
    raise ValueError("unknown snapshot scope: %r" % (scope,))


def _verify_retry(bridge, command, params, result, verify, attempts=4, delay=0.06):
    """Re-issue a toggle-style command until its reported state sticks.

    FL occasionally drops a mute/solo toggle when it lands too close to other
    writes (it coalesces these over a short window). Each re-issue is a fresh
    SysEx = a fresh FL script-tick + latency = spacing, so it lands.
    """
    if verify is None:
        return result
    field, expected = verify
    n = 0
    while result.get(field) != expected and n < attempts:
        time.sleep(delay)
        result = bridge.call(command, params)
        n += 1
    return result


def _expected(command, params):
    if command.endswith("set_volume"):
        if params.get("unit", "normalized") == "normalized":
            return "vol_norm", params["value"]
        return None  # FL dB mapping has not been calibrated
    if command.endswith("set_pan"):
        return "pan", params["value"]
    if command.endswith("set_mute"):
        return "mute", params["state"]
    if command.endswith("set_solo"):
        return "solo", params["state"]
    if command.endswith("set_name"):
        return "name", params["name"]
    if command == "mixer_set_route":
        return "enabled", params["enabled"]
    if command == "plugin_set_param":
        return "v", params["value"]
    return None


def _matches(after, expected):
    if expected is None:
        return False
    field, target = expected
    actual = after.get(field)
    if isinstance(target, (float, int)) and not isinstance(target, bool):
        return isinstance(actual, (float, int)) and abs(actual - target) <= 1e-5
    return actual == target


def safe_write(bridge, *, tool, scope, command, params, build_restore, verify=None):
    """Snapshot, persist recovery intent, mutate once, independently read back.

    No setter echo fallback and no blind retry on a timeout. A non-matching or
    unreadable state returns failure while preserving a recovery action.
    """
    if _dry_run:
        return {"ok": True, "verified": False, "dry_run": True,
                "planned": {"tool": tool, "command": command, "params": params}}
    before = take_snapshot(bridge, scope)
    restore = build_restore(before)
    entry = {"tool": tool, "scope": scope, "command": command, "params": params,
             "before": before, "restore": restore, "status": "pending", "ts": time.time()}
    _log.append(entry)
    try:
        echo = bridge.call(command, params)
        expected = verify or _expected(command, params)
        after = take_snapshot(bridge, scope)
        # Read-only bounded polling allows FL's asynchronous commit. Never retry writes.
        for _ in range(3):
            if _matches(after, expected):
                break
            time.sleep(.06)
            after = take_snapshot(bridge, scope)
        matched = _matches(after, expected)
        entry.update(after=after, echo=echo, status="verified" if matched else "verification_failed")
        _log._persist()
        return {"ok": matched, "verified": matched, "before": before, "after": after,
                "error": None if matched else {"code": "VERIFY_FAILED", "message": "Independent readback does not confirm requested value"}}
    except Exception as exc:
        entry.update(status="execution_unknown", error=str(exc))
        _log._persist()
        return {"ok": False, "verified": False, "before": before,
                "error": {"code": "EXECUTION_UNKNOWN", "message": str(exc)},
                "recovery": "Inspect project and persisted restore action; do not blindly retry"}


def safe_write_group(bridge, *, tool, scope, writes):
    """One recovery unit with all pre-states persisted before the first write."""
    if _dry_run:
        return {"ok": True, "verified": False, "dry_run": True,
                "planned": {"tool": tool, "scope": scope, "writes": [
                    {"command": w["command"], "params": w["params"]} for w in writes]}}
    befores = [take_snapshot(bridge, w["snap_scope"]) for w in writes]
    restores = [w["restore"](before) for w, before in zip(writes, befores)]
    scopes = [w["snap_scope"] for w in writes]
    entry = {"tool": tool, "scope": scope, "group": True, "befores": befores,
             "restores": restores, "snap_scopes": scopes, "status": "pending", "ts": time.time()}
    _log.append(entry)
    try:
        echoes = [bridge.call(w["command"], w["params"]) for w in writes]
        afters = [take_snapshot(bridge, s) for s in scopes]
        verified = all(_matches(a, _expected(w["command"], w["params"])) for a, w in zip(afters, writes))
        entry.update(afters=afters, echoes=echoes, status="verified" if verified else "verification_failed")
        _log._persist()
        return {"ok": verified, "verified": verified, "before": befores, "after": afters,
                "error": None if verified else {"code": "VERIFY_FAILED", "message": "Group independent readback failed"}}
    except Exception as exc:
        entry.update(status="execution_unknown", error=str(exc))
        _log._persist()
        return {"ok": False, "verified": False, "error": {"code": "EXECUTION_UNKNOWN", "message": str(exc)}}


def rollback_last_change(bridge):
    entries = _log.recent(1)
    if not entries:
        return {"ok": False, "verified": False, "error": {"code": "EMPTY_HISTORY", "message": "No recovery actions"}}
    entry = entries[0]
    restores = entry.get("restores", []) if entry.get("group") else [entry.get("restore")]
    scopes = entry.get("snap_scopes", []) if entry.get("group") else [entry["scope"]]
    if not restores or not all(restores) or len(scopes) != len(restores):
        return {"ok": False, "verified": False, "error": {"code": "RECOVERY_REQUIRED", "message": "Missing independent recovery scope"}}
    states = []
    try:
        for restore, scope in zip(restores, scopes):
            bridge.call(restore["command"], restore.get("params") or {})
            after = take_snapshot(bridge, scope)
            expected = _expected(restore["command"], restore.get("params") or {})
            for _ in range(3):
                if _matches(after, expected): break
                time.sleep(.06)
                after = take_snapshot(bridge, scope)
            states.append(after)
            if not _matches(after, expected):
                return {"ok": False, "verified": False, "error": {"code": "RESTORE_VERIFY_FAILED", "message": "Recovery remains in journal"}, "readback": states}
        _log.pop_last()  # remove only after every independent recovery postcondition
        return {"ok": True, "verified": True, "rolled_back": entry["tool"], "restored": states}
    except Exception as exc:
        return {"ok": False, "verified": False, "error": {"code": "RECOVERY_REQUIRED", "message": str(exc)}}
