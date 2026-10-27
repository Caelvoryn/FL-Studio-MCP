"""Windows UIA dialogs + guarded FL canvas operations. Never edits FLP bytes."""
from __future__ import annotations

import math
import time
from pathlib import Path

from .native import inspect
from .workflow import WorkflowError, atomic_json, audio_integrity, digest, state_dir


def rectangle_values(rect):
    return [rect.left, rect.top, rect.right, rect.bottom]


def guard_pattern_overlap(clips, clip_index, action, position_ticks=None, length_ticks=None, patterns=None):
    """Conservative playback guard: overlapping Pattern instances are unverified.

    Native structural equality does not prove overlapping voices render correctly.
    Reject across all lanes before creating a checkpoint or sending input.
    """
    if action == "delete":
        return
    source = clips[clip_index]
    def channels(clip):
        if patterns is None:
            return None
        pattern = patterns.get(clip.get("source_id"), patterns.get(str(clip.get("source_id"))))
        return None if pattern is None else {n["channel"] for n in pattern["notes"]}
    source_channels = channels(source)
    start = position_ticks if action in ("copy", "move") else source["position_ticks"]
    length = length_ticks if action == "trim" else source["length_ticks"]
    for index, other in enumerate(clips):
        if index == clip_index and action != "copy":
            continue
        if other["source_kind"] != "pattern":
            continue
        other_channels = channels(other)
        if source_channels is not None and other_channels is not None and source_channels.isdisjoint(other_channels):
            continue
        if max(start, other["position_ticks"]) < min(start + length, other["position_ticks"] + other["length_ticks"]):
            raise WorkflowError("PLAYLIST_OVERLAP_RISK", "Overlapping Patterns sharing instrument channels are not verified, including across lanes; use non-overlapping placement")


def wait_for(predicate, timeout=10., description="state"):
    if not math.isfinite(timeout) or not 0 < timeout <= 180:
        raise WorkflowError("INVALID_ARGUMENT", "Timeout must be finite and 0..180 seconds")
    deadline = time.monotonic() + timeout
    while True:
        value = predicate()
        if value:
            return value
        if time.monotonic() >= deadline:
            raise WorkflowError("GUI_TIMEOUT", "Timed out waiting for " + description)
        time.sleep(.1)


def semantic_state(state):
    """Exclude timestamps, GUI selections and regenerated clip instance IDs."""
    clips = [{k: c[k] for k in ("position_ticks", "length_ticks", "track", "source_kind", "source_id", "start_offset", "end_offset", "start_offset_bits", "end_offset_bits")}
             for c in state["playlist"]]
    return {"ppq": state["ppq"], "bpm": state["bpm"], "patterns": state["patterns"],
            "channels": state["channels"], "automation": state["automation"],
            "all_plugin_states": state.get("plugin_state_hashes", []),
            "mixer": state["mixer_event_hashes"], "playlist": clips}


class FLDesktop:
    def __init__(self):
        import sys
        if sys.platform != "win32":
            raise WorkflowError("UNSUPPORTED_PLATFORM", "Windows desktop automation only")
        from pywinauto import Desktop
        from .pyscript_trigger import find_fl_hwnd
        self.win32, self.uia = Desktop(backend="win32"), Desktop(backend="uia")
        hwnd = find_fl_hwnd()
        if not hwnd:
            raise WorkflowError("FL_NOT_RUNNING", "No FL Studio main window")
        self.main = self.win32.window(handle=hwnd).wrapper_object()
        self.pid = self.main.process_id()

    def dialogs(self, class_name="#32770"):
        # Owned common dialogs are omitted from some UIA desktop enumerations.
        # Locate handles with Win32, then use UIA Value/Invoke patterns.
        return [w for w in self.win32.windows(process=self.pid, class_name=class_name)
                if w.is_visible()]

    def focus(self, expected_title=None):
        from .pyscript_trigger import force_focus
        if not self.main.is_enabled():
            raise WorkflowError("GUI_BLOCKED", "FL is blocked by a modal window; nothing dismissed automatically")
        if expected_title and self.main.window_text() != expected_title:
            raise WorkflowError("PROJECT_CHANGED", "Current FL title differs", actual=self.main.window_text())
        import ctypes
        from ctypes import wintypes
        ctypes.windll.user32.GetForegroundWindow.restype = wintypes.HWND
        foreground = ctypes.windll.user32.GetForegroundWindow()
        foreground_pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        ctypes.windll.user32.GetWindowThreadProcessId(foreground, ctypes.byref(foreground_pid))
        if foreground_pid.value == self.pid:
            return
        if not force_focus(self.main.handle):
            raise WorkflowError("FOCUS_LOST", "Could not verify FL foreground; no keys sent")

    def state(self):
        panes = [{"class": w.class_name(), "title": w.window_text(), "rect": rectangle_values(w.rectangle())}
                 for w in self.main.descendants()
                 if w.class_name() in {"TEventEditForm", "TStepSeqForm", "TFXForm", "TQuickScroller"} and w.is_visible()]
        owned = [{"class": w.class_name(), "title": w.window_text(), "rect": rectangle_values(w.rectangle())}
                 for w in self.win32.windows(process=self.pid) if w.is_visible()
                 and w.class_name() not in {"TFruityLoopsMainForm", "TApplication", "tooltips_class32", "TFLHintBarForm"}]
        return {"process_id": self.pid, "title": self.main.window_text(),
                "enabled": self.main.is_enabled(), "rect": rectangle_values(self.main.rectangle()),
                "dialogs": [{"title": w.window_text(), "class": w.class_name()} for w in self.dialogs()],
                "visible_panes": panes, "owned_windows": owned,
                "backend": "Win32 window identity + UIA common dialog controls",
                "dirty_state": "unknown; open always preserves current state by Save As first"}

    def file_dialog(self, path):
        window = wait_for(lambda: next(iter(self.dialogs()), None), description="FL file dialog")
        uia = self.uia.window(handle=window.handle)
        types = [uia.child_window(auto_id=i, control_type="ComboBox") for i in ("FileTypeControlHost", "1136")]
        file_type = next((c for c in types if c.exists(timeout=.2)), None)
        if file_type is None:
            raise WorkflowError("GUI_LAYOUT", "File type control unavailable; refusing to guess dialog purpose")
        selected_type = file_type.wrapper_object().selected_text()
        if Path(path).suffix.lower() not in selected_type.lower():
            raise WorkflowError("GUI_WRONG_FILE_TYPE", "Dialog belongs to a different save/open operation; no filename submitted",
                                expected_suffix=Path(path).suffix, actual_type=selected_type)
        # Save uses modern common dialog 1001; Open can use classic 1148.
        edits = [uia.child_window(auto_id=identifier, control_type="Edit") for identifier in ("1001", "1148")]
        editor = next((e for e in edits if e.exists(timeout=.2)), None)
        if editor is None:
            raise WorkflowError("GUI_LAYOUT", "No supported filename ValuePattern control")
        edit = editor.wrapper_object()
        edit.set_edit_text(str(path))
        if edit.get_value() != str(path):
            raise WorkflowError("GUI_VALUE_MISMATCH", "Filename edit did not retain requested path")
        uia.child_window(auto_id="1", control_type="Button").wrapper_object().invoke()

    def save_as(self, destination, expected_title):
        import pyautogui
        path = Path(destination).expanduser().resolve()
        if path.suffix.lower() != ".flp":
            raise WorkflowError("INVALID_ARGUMENT", "Save target must be .flp")
        if path.exists():
            raise WorkflowError("OVERWRITE_REFUSED", "Save As destination already exists", path=str(path))
        path.parent.mkdir(parents=True, exist_ok=True)
        self.focus(expected_title)
        # Ctrl+Shift+S in the Mixer saves an FST, not an FLP. Establish Playlist
        # keyboard context explicitly and validate the dialog file type below.
        playlist = self.show_playlist()
        rect = playlist.rectangle()
        pyautogui.click(rect.left + 68, rect.top + 12)
        pyautogui.hotkey("ctrl", "shift", "s")
        self.file_dialog(path)
        wait_for(lambda: self.main.is_enabled() and path.is_file() and path.stat().st_size > 22,
                 description="saved native project")
        wait_for(lambda: path.name.lower() in self.main.window_text().lower(), description="saved project title")
        state = inspect(path)  # parse actual bytes, not setter or GUI echo
        atomic_json(state_dir() / "desktop-session.json", {"path": str(path), "sha256": state["sha256"],
                    "title": self.main.window_text(), "process_id": self.pid})
        return {"ok": True, "verified": True, "path": str(path), "sha256": state["sha256"],
                "title": self.main.window_text(), "saved_state": state}

    def open_project(self, path, preserve_current_to, verify_to, expected_title):
        import pyautogui
        path = Path(path).resolve()
        expected = inspect(path)  # fail before any GUI action for missing/unsupported input
        new_paths = [Path(new).resolve() for new in (preserve_current_to, verify_to)]
        if len({path, *new_paths}) != 3 or any(p.suffix.lower() != ".flp" for p in new_paths):
            raise WorkflowError("INVALID_ARGUMENT", "Open source, preservation and native readback must be three distinct FLP paths")
        for new in (preserve_current_to, verify_to):
            if Path(new).resolve().exists():
                raise WorkflowError("OVERWRITE_REFUSED", "Preservation/readback path already exists")
        preservation = self.save_as(preserve_current_to, expected_title)
        self.focus(preservation["title"])
        pyautogui.hotkey("ctrl", "o")
        self.file_dialog(path)
        wait_for(lambda: self.main.is_enabled() and path.name.lower() in self.main.window_text().lower(),
                 description="opened FLP; missing-plugin dialogs are not dismissed")
        readback = self.save_as(verify_to, self.main.window_text())
        matched = semantic_state(expected) == semantic_state(readback["saved_state"])
        if not matched:
            raise WorkflowError("REOPEN_MISMATCH", "FL native re-save differs from expected semantic state",
                                actual=str(verify_to), preserved=str(preserve_current_to))
        return {"ok": True, "verified": True, "opened": str(path), "preserved": preservation["path"],
                "readback": readback["path"], "title": readback["title"], "semantic_state_equal": True}

    def playlist(self):
        from pywinauto import findwindows
        for handle in findwindows.find_windows(parent=self.main.handle, class_name="TEventEditForm", top_level_only=False):
            window = self.win32.window(handle=handle).wrapper_object()
            if window.is_visible() and window.window_text().startswith(("播放列表", "Playlist")):
                return window
        raise WorkflowError("GUI_LAYOUT", "Visible Playlist window not found")

    def show_playlist(self):
        import pyautogui
        try:
            window = self.playlist()
        except WorkflowError:
            pyautogui.press("f5")  # toggle only when actually hidden
            def visible_playlist():
                try:
                    return self.playlist()
                except WorkflowError as exc:
                    if exc.code == "GUI_LAYOUT":
                        return None
                    raise
            window = wait_for(visible_playlist, description="Playlist visibility")
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        u.BringWindowToTop.argtypes = [wintypes.HWND]
        outer = window.parent()
        if outer.class_name() == "TWPControl":
            u.BringWindowToTop(outer.handle)
        u.BringWindowToTop(window.handle)
        window.set_focus()
        return window

    def screenshot(self, name):
        import pyautogui
        path = state_dir() / "screenshots" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        pyautogui.screenshot().save(path)
        return str(path)

    def viewport_stamp(self, profile, rect):
        import hashlib
        import pyautogui
        time.sleep(.15)
        left = round(rect.left + profile["grid_left"] + 56)
        ruler = pyautogui.screenshot(region=(left, rect.top + 50, rect.right - left - 24, 13))
        lanes = pyautogui.screenshot(region=(rect.left + 250, round(rect.top + profile["first_track_top"]),
                                             2, round(rect.height() - profile["first_track_top"] - 24)))
        return {"ruler": hashlib.sha256(ruler.tobytes()).hexdigest(),
                "lanes": hashlib.sha256(lanes.tobytes()).hexdigest()}

    def session(self, focus=True):
        import json
        path = state_dir() / "desktop-session.json"
        if not path.is_file():
            raise WorkflowError("NO_GUI_SESSION", "First Save As to establish an owned test project")
        session = json.loads(path.read_text(encoding="utf8"))
        if session["process_id"] != self.pid or digest(session["path"]) != session["sha256"]:
            raise WorkflowError("STALE_STATE", "Saved project identity changed")
        if self.main.window_text() != session["title"]:
            raise WorkflowError("PROJECT_CHANGED", "Current FL project differs from owned saved session")
        if focus:
            self.focus(session["title"])
        return session

    def calibrate(self, grid_left, first_track_top, pixels_per_bar, track_height):
        """Canvas calibration is explicit; it is not falsely described as UIA clip access."""
        self.session()
        window = self.show_playlist()
        rect = window.rectangle()
        values = (grid_left, first_track_top, pixels_per_bar, track_height)
        if not all(math.isfinite(v) for v in values) or not (0 < grid_left < rect.width() and 0 < first_track_top < rect.height()
                and 8 <= pixels_per_bar <= 1000 and 20 <= track_height <= 400):
            raise WorkflowError("INVALID_ARGUMENT", "Invalid window-relative canvas calibration")
        profile = {"process_id": self.pid, "window_rect": rectangle_values(rect), "grid_left": grid_left,
                   "first_track_top": first_track_top, "pixels_per_bar": pixels_per_bar, "track_height": track_height,
                   "origin_tick": 0, "first_visible_track": 1,
                   "screenshot": self.screenshot("playlist-calibration.png")}
        profile["viewport_stamp"] = self.viewport_stamp(profile, rect)
        atomic_json(state_dir() / "playlist-profile.json", profile)
        return {"ok": True, "verified": False, "status": "calibration_requires_native_postcondition",
                "profile": profile, "limitation": "Uniform visible tracks, bar1 origin, 4/4, tested DPI; any viewport changes require recalibration"}

    def edit_playlist(self, action, clip_index, output_path, position_ticks=None, track=None, length_ticks=None):
        import json
        import pyautogui as p
        session = self.session()
        from .connection import get_bridge
        if get_bridge().call("get_play_state").get("playing"):
            raise WorkflowError("TRANSPORT_BUSY", "Stop playback before changing the Playlist")
        profile_path = state_dir() / "playlist-profile.json"
        if not profile_path.is_file():
            raise WorkflowError("GUI_LAYOUT", "Explicit Playlist calibration required")
        profile = json.loads(profile_path.read_text(encoding="utf8"))
        window = self.show_playlist()
        rect = window.rectangle()
        if profile["process_id"] != self.pid or rectangle_values(rect) != profile["window_rect"]:
            raise WorkflowError("GUI_LAYOUT", "Playlist window changed; recalibration required")
        if profile.get("viewport_stamp") != self.viewport_stamp(profile, rect):
            raise WorkflowError("VIEWPORT_CHANGED", "Timeline zoom/scroll or lane layout changed; recalibrate before editing")
        expected = inspect(session["path"])
        clips = semantic_state(expected)["playlist"]
        if not 0 <= clip_index < len(clips):
            raise WorkflowError("INVALID_ARGUMENT", "Clip index outside actual saved Playlist")
        clip = clips[clip_index]
        automation_move=clip['source_kind']=='channel' and action=='move' and any(a['channel']==clip['source_id'] for a in expected['automation'])
        if clip["source_kind"] != "pattern" and not automation_move:
            raise WorkflowError("UNSUPPORTED_CLIP", "Pattern CRUD and recognized automation-clip move only; audio/automation trim-copy-delete not accepted")
        if action not in ("copy", "move", "trim", "delete"):
            raise WorkflowError("INVALID_ARGUMENT", "Unknown Playlist action")
        if action in ("copy", "move") and (position_ticks is None or position_ticks < 0 or track is None or not 1 <= track <= 500):
            raise WorkflowError("INVALID_ARGUMENT", "Move/copy requires nonnegative ticks and track 1..500")
        if action == "trim" and (length_ticks is None or not 0 < length_ticks < clip["length_ticks"]):
            raise WorkflowError("INVALID_ARGUMENT", "Trim must shorten an existing Pattern clip")
        if clip['source_kind']=='pattern':
            guard_pattern_overlap(clips, clip_index, action, position_ticks, length_ticks, expected["patterns"])
        elif automation_move and any(i!=clip_index and c['source_kind']=='channel' and c['source_id']==clip['source_id']
                                    and max(position_ticks,c['position_ticks'])<min(position_ticks+clip['length_ticks'],c['position_ticks']+c['length_ticks'])
                                    for i,c in enumerate(clips)):
            raise WorkflowError('AUTOMATION_OVERLAP_RISK','Same automation source would overlap another instance')
        if any(c["track"] == clip["track"] and c is not clip and
               max(c["position_ticks"], clip["position_ticks"]) < min(c["position_ticks"] + c["length_ticks"], clip["position_ticks"] + clip["length_ticks"])
               for c in clips):
            raise WorkflowError("AMBIGUOUS_CLIP", "Overlapped source clips cannot be targeted safely")
        output = Path(output_path).resolve()
        before_path = output.with_name(output.stem + "__before.flp")
        if output.exists() or before_path.exists():
            raise WorkflowError("OVERWRITE_REFUSED", "New edit and checkpoint paths required")
        ppbar = expected["ppq"] * 4
        def x(tick): return rect.left + profile["grid_left"] + tick / ppbar * profile["pixels_per_bar"]
        def y(lane): return rect.top + profile["first_track_top"] + (lane - 1) * profile["track_height"] + 12
        start_x, end_x = x(clip["position_ticks"]), x(clip["position_ticks"] + clip["length_ticks"])
        source_x = start_x + min(18, (end_x - start_x) / 3)
        source_y = y(clip["track"])
        if action in ("copy", "move"):
            target_x = source_x + x(position_ticks) - x(clip["position_ticks"])
            target_y = y(track)
        elif action == "trim":
            target_x, target_y = x(clip["position_ticks"] + length_ticks), source_y
        else:
            target_x, target_y = source_x, source_y
        horizontal_points = (source_x, target_x, end_x - 2) if action == "trim" else (source_x, target_x)
        if not all(rect.left + profile["grid_left"] + 4 <= v <= rect.right - 24 for v in horizontal_points) or not all(rect.top + profile["first_track_top"] <= v <= rect.bottom - 24 for v in (source_y, target_y)):
            raise WorkflowError("GUI_OUT_OF_VIEW", "Source/target outside calibrated viewport; no edit performed")
        actual_before = self.save_as(before_path, session["title"])
        if semantic_state(actual_before["saved_state"]) != semantic_state(expected):
            raise WorkflowError("STALE_STATE", "Unsaved changes detected by native checkpoint; no canvas edit performed", preserved=str(before_path))
        self.focus(actual_before["title"])
        self.show_playlist()
        # FL custom popup has no UIA children. Use the tested window-relative
        # magnet anchor and reject a changed menu layout before selecting Bar.
        p.click(rect.left + 34, rect.top + 12)
        menu = wait_for(lambda: next((w for w in self.win32.windows(process=self.pid, class_name="TQuickPopupMenuWindow") if w.is_visible()), None),
                        description="Playlist snap menu")
        menu_rect = menu.rectangle()
        if not 60 <= menu_rect.width() <= 180 or menu_rect.height() != 348:
            raise WorkflowError("GUI_LAYOUT", "Unsupported FL snap menu layout")
        p.click(menu_rect.left + 30, menu_rect.top + 291)
        p.click(rect.left + 68, rect.top + 12)  # Draw icon: avoids Shift+P entering a Chinese IME composition
        p.hotkey("ctrl", "d")
        if action == "delete":
            p.keyDown("ctrl"); p.click(source_x, source_y); p.keyUp("ctrl")
            p.press("delete")
            del clips[clip_index]
        elif action == "trim":
            p.moveTo(end_x - 2, source_y)
            p.mouseDown()
            p.moveTo(target_x, target_y, duration=1.)
            time.sleep(.3)  # allow FL's canvas thread to consume the final mouse move
            p.mouseUp()
            clip["length_ticks"] = length_ticks
            clip["start_offset"] = clip["start_offset"] or 0
            clip["end_offset"] = clip["start_offset"] + length_ticks
            clip["start_offset_bits"] = clip["start_offset"]
            clip["end_offset_bits"] = clip["end_offset"]
        else:
            p.moveTo(source_x, source_y)
            if action == "copy": p.keyDown("shift")
            p.mouseDown()
            p.moveRel(5, 0, duration=.1)
            if action == "copy": p.keyUp("shift")  # release vertical-axis constraint after clone starts
            p.moveTo(target_x, target_y, duration=.6)
            time.sleep(.25)
            p.mouseUp()
            if action == "copy":
                clip = dict(clip)
                clips.append(clip)
            clip.update(position_ticks=position_ticks, track=track)
        time.sleep(.15)
        result = self.save_as(output, self.main.window_text())
        expected_state = semantic_state(expected)
        expected_state["playlist"] = clips
        actual_state = semantic_state(result["saved_state"])
        order = lambda c: (c["track"], c["position_ticks"], c["source_kind"], c["source_id"], c["length_ticks"])
        expected_state["playlist"] = sorted(expected_state["playlist"], key=order)
        actual_state["playlist"] = sorted(actual_state["playlist"], key=order)
        if actual_state != expected_state:
            raise WorkflowError("PLAYLIST_VERIFY_FAILED", "Saved native state differs from requested edit; failed output retained",
                                expected_playlist=expected_state["playlist"], actual_playlist=actual_state["playlist"],
                                checkpoint=str(before_path), actual=str(output))
        profile["viewport_stamp"] = self.viewport_stamp(profile, rect)
        atomic_json(profile_path, profile)
        return {"ok": True, "verified": True, "action": action, "path": str(output),
                "before": str(before_path), "playlist": result["saved_state"]["playlist"], "other_native_state_preserved": True,
                "verified_fields": ["notes", "plugin_states", "mixer_and_routing", "automation", "BPM/PPQ", "clip_sources_and_offsets"],
                "limitation": "Observed FL26 fields only; not a complete semantic decoder of every proprietary project field",
                "screenshot": self.screenshot(output.stem + "-verified.png")}

    def render(self, destination, expected_title, minimum_seconds, maximum_seconds, timeout=90.):
        """UIA file dialog; FL26 render canvas uses its verified window-relative profile."""
        import pyautogui
        path = Path(destination).resolve()
        if path.suffix.lower() != ".wav" or path.exists():
            raise WorkflowError("OVERWRITE_REFUSED", "Render requires a new .wav path")
        if not 0 < minimum_seconds <= maximum_seconds <= 3600:
            raise WorkflowError("INVALID_ARGUMENT", "Invalid expected render duration")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.focus(expected_title)
        playlist = self.show_playlist()
        # The upper scrollbar and timeline are native child anchors, not fixed screen coordinates.
        scrollbars = [c for c in playlist.children() if c.class_name() == "TQuickScroller"]
        if not scrollbars:
            raise WorkflowError("GUI_LAYOUT", "Playlist timeline anchor unavailable")
        r = scrollbars[0].rectangle()
        pyautogui.doubleClick(r.left + 12, r.bottom + 12, interval=.12)  # official clear time selection
        pyautogui.hotkey("ctrl", "r")
        self.file_dialog(path)
        render = wait_for(lambda: next(iter(self.dialogs("TWAVRenderForm")), None), description="FL render settings")
        rect = render.rectangle()
        # Refuse unknown layouts. These offsets are calibrated against FL26.1.5 at 100% DPI.
        if (rect.width(), rect.height()) != (433, 611):
            raise WorkflowError("GUI_LAYOUT", "Render form size does not match tested profile", rect=rectangle_values(rect))
        self.screenshot(path.stem + "-render-settings.png")
        # Tail combo: choose Cut remainder, then verify output length independently.
        pyautogui.click(rect.left + 269, rect.top + 67)
        pyautogui.click(rect.left + 250, rect.top + 90)
        pyautogui.click(rect.left + 391, rect.top + 587)
        wait_for(lambda: not any(w.is_visible() for w in self.dialogs("TWAVRenderForm")), timeout, "render completion")
        wait_for(lambda: path.is_file() and path.stat().st_size > 44, 5, "actual WAV")
        result = audio_integrity(path, minimum_seconds, maximum_seconds)
        if not result["ok"]:
            raise WorkflowError("AUDIO_CLIPPED", "Actual output has clipped samples", readback=result)
        return {"ok": True, "verified": True, "path": str(path), "audio": result,
                "render_profile": "FL26.1.5 100% DPI verified form; arbitrary layouts refused"}
