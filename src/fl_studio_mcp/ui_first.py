"""Observed-window GUI input. No bridge writes, MIDI writes or FLP writes."""
import hashlib
import json
import math
import time
import uuid
from pathlib import Path

from .desktop import FLDesktop, rectangle_values
from .workflow import WorkflowError, atomic_json, state_dir


def visible_windows(desktop):
    windows = [desktop.main]
    windows += desktop.main.descendants()
    windows += desktop.win32.windows(process=desktop.pid)
    return {str(w.handle): w for w in windows if w.is_visible() and w.rectangle().width() > 0 and w.rectangle().height() > 0}


def window_image(window):
    import pyautogui
    r = window.rectangle()
    im = pyautogui.screenshot(region=(r.left, r.top, r.width(), r.height()))
    return im, hashlib.sha256(im.tobytes()).hexdigest()


def desktop_context(desktop):
    import ctypes
    from ctypes import wintypes
    import pyautogui
    class GUIINFO(ctypes.Structure):
        _fields_=[('cbSize',wintypes.DWORD),('flags',wintypes.DWORD),
                  *[(name,wintypes.HWND) for name in ('hwndActive','hwndFocus','hwndCapture','hwndMenuOwner','hwndMoveSize','hwndCaret')],
                  ('rcCaret',wintypes.RECT)]
    api=ctypes.windll.user32
    api.GetDpiForWindow.argtypes=[wintypes.HWND];api.GetDpiForWindow.restype=wintypes.UINT
    info=GUIINFO();info.cbSize=ctypes.sizeof(info)
    api.GetGUIThreadInfo.argtypes=[wintypes.DWORD,ctypes.POINTER(GUIINFO)]
    context=dict(dpi=api.GetDpiForWindow(desktop.main.handle),screen_size=list(pyautogui.size()),active_editor=None)
    if api.GetGUIThreadInfo(0,ctypes.byref(info)) and info.hwndFocus:
        current=desktop.win32.window(handle=info.hwndFocus).wrapper_object()
        if current.process_id()==desktop.pid:
            for _ in range(20):
                if current.class_name() in ('TEventEditForm','TPluginForm','TFXForm','TStepSeqForm'):
                    context['active_editor']=dict(handle=str(current.handle),title=current.window_text(),class_name=current.class_name());break
                current=current.parent()
                if current is None:break
        else:context['foreground_other_application']=True
    return context


def observe(desktop=None):
    desktop = desktop or FLDesktop()
    token = uuid.uuid4().hex
    folder = state_dir() / "observations" / token
    folder.mkdir(parents=True)
    windows = []
    for handle, window in visible_windows(desktop).items():
        # Tiny transport components are included in the window tree, not imaged.
        r = window.rectangle()
        parent=window.parent()
        row = {"handle": handle, "parent_handle": str(parent.handle) if parent else None,
               "class": window.class_name(), "title": window.window_text(), "rect": rectangle_values(r)}
        if (r.width() > 180 and r.height() > 100) or (window.class_name().startswith('TQuickPopup') and r.width()>40 and r.height()>20):
            im, sha = window_image(window)
            path = folder / (handle + ".png")
            im.save(path)
            row.update(image=str(path), image_sha256=sha)
            controls = []
            try:
                for c in desktop.uia.window(handle=window.handle).descendants()[:150]:
                    info = c.element_info
                    if c.is_visible():
                        controls.append({"name": info.name, "type": info.control_type,
                                         "automation_id": info.automation_id, "rect": rectangle_values(c.rectangle())})
            except Exception as exc:
                row["accessibility_error"] = type(exc).__name__
            row["controls"] = controls
        windows.append(row)
    result = {"ok": True, "token": token, "time": time.time(), "process_id": desktop.pid,
              "title": desktop.main.window_text(), "enabled": desktop.main.is_enabled(), "windows": windows,
              "limitation": "Images and UIA expose current UI only; no automatic musical or target recognition"}
    result['desktop_context']=desktop_context(desktop)
    atomic_json(folder / "observation.json", result)
    return result


def normalized_point(point, rect):
    if len(point) != 2 or not all(math.isfinite(v) and 0 <= v <= 1 for v in point):
        raise WorkflowError("INVALID_ARGUMENT", "Point must be two finite window-relative fractions in 0..1")
    return (round(rect.left + point[0] * (rect.width() - 1)), round(rect.top + point[1] * (rect.height() - 1)))


def piano_point(grid, note, rect, action, time_marks=None, snap_bar=False):
    """Explicit screenshot calibration, not automatic note/grid recognition."""
    required = {'tick_zero_x', 'tick_zero', 'pixels_per_tick', 'pitch_zero_y', 'pitch_zero', 'pixels_per_semitone', 'grid_top', 'grid_bottom', 'grid_right'}
    if set(grid) != required or not all(math.isfinite(v) for v in grid.values()):
        raise WorkflowError('INVALID_ARGUMENT', 'Complete finite Piano Roll grid calibration required')
    if grid['pixels_per_tick'] <= 0 or grid['pixels_per_semitone'] <= 0 or not 0 <= note.get('pitch', -1) <= 131 or note.get('tick', -1) < 0:
        raise WorkflowError('INVALID_ARGUMENT', 'Invalid calibrated scale or musical target')
    x = (time_marks or {}).get(note['tick'],grid['tick_zero_x'] + (note['tick'] - grid['tick_zero']) * grid['pixels_per_tick'])
    y = grid['pitch_zero_y'] - (note['pitch'] - grid['pitch_zero']) * grid['pixels_per_semitone']
    if action == 'draw' and abs(x-round(x)) > 1e-6:
        raise WorkflowError('INSUFFICIENT_ZOOM', 'Requested tick is between screen pixels; zoom/recalibrate before exact drawing')
    if action == 'resize':
        if note.get('length_ticks', 0) <= 0:
            raise WorkflowError('INVALID_ARGUMENT', 'Resize requires actual note length')
        x += note['length_ticks'] * grid['pixels_per_tick'] - 2
    else:
        x += (2 if snap_bar else 0) if action == 'draw' else min(8, note.get('length_ticks', 16) * grid['pixels_per_tick'] / 3)
    if not grid['tick_zero_x'] <= x < grid['grid_right'] or not grid['grid_top'] < y < grid['grid_bottom']:
        raise WorkflowError('GUI_OUT_OF_VIEW', 'Musical target outside observed calibrated note grid')
    return [x / (rect.width()-1), y / (rect.height()-1)]


def act(token, operation_id, handle, action, point=None, target=None, keys=None, text=None, selector=None,
        piano_grid=None, piano_note=None, piano_target=None, wheel=0, piano_snap_bar=False, automation_edit=None):
    """Single-use intent journal: a failed/uncertain action cannot replay inputs."""
    import pyautogui as p
    if not token.isalnum() or not operation_id.isalnum():
        raise WorkflowError("INVALID_ARGUMENT", "Use alphanumeric observation and operation IDs")
    intent_items = [token, handle, action, point, target, keys, text, selector]
    if piano_grid is not None or piano_note is not None or piano_target is not None:
        intent_items += [piano_grid, piano_note, piano_target]
    if wheel:
        intent_items += [wheel]
    if piano_snap_bar:
        intent_items += ['requested_bar_snap']
    if automation_edit is not None:
        intent_items += [automation_edit]
    intent = hashlib.sha256(json.dumps(intent_items, sort_keys=True).encode()).hexdigest()
    journal = state_dir() / "ui-operations" / (operation_id + ".json")
    if journal.exists():
        previous = json.loads(journal.read_text(encoding="utf8"))
        if previous.get("intent_sha256") != intent:
            raise WorkflowError("OPERATION_ID_CONFLICT", "Operation ID already belongs to another input; no input replayed")
        return previous
    observation = json.loads((state_dir() / "observations" / token / "observation.json").read_text(encoding="utf8"))
    if time.time() - observation["time"] > 180:
        raise WorkflowError("OBSERVATION_EXPIRED", "Observe the current interface again")
    desktop = FLDesktop()
    desktop.session(focus=False)  # GUI input is limited to a preserved, owned project copy
    if desktop.pid != observation["process_id"]:
        raise WorkflowError("PROCESS_CHANGED", "FL process changed")
    if desktop.main.window_text() != observation["title"]:
        raise WorkflowError("PROJECT_CHANGED", "Observed FL project title changed")
    if handle=='active_popup':
        if action!='text_click' or not text:
            raise WorkflowError('INVALID_ARGUMENT','Active popup targeting requires exact visible text click')
        from .vision import locate_text
        from PIL import Image
        matches=[]
        for row in observation['windows']:
            if row['class'].startswith('TQuickPopup') and row.get('image'):
                try:
                    locate_text(Image.open(row['image']),text,Path(row['image']).parent/('text-'+row['handle']))
                    matches.append(row['handle'])
                except WorkflowError as exc:
                    if exc.code!='TEXT_UNRECOGNIZED':raise
        if len(matches)!=1:
            raise WorkflowError('AMBIGUOUS_POPUP','Need one actually recognized popup item',matches=matches,text=text)
        handle=matches[0]
    old = next((w for w in observation["windows"] if w["handle"] == str(handle)), None)
    window = visible_windows(desktop).get(str(handle))
    if not old or not window or rectangle_values(window.rectangle()) != old["rect"]:
        raise WorkflowError("WINDOW_CHANGED", "Observed target is no longer visible at the same geometry")
    popups=[w for w in visible_windows(desktop).values() if w.class_name().startswith('TQuickPopup')]
    if popups and all(w.handle!=window.handle for w in popups) and not (action=='keys' and keys==['escape']):
        raise WorkflowError('GUI_POPUP_BLOCKED','An actual FL popup owns interaction; inspect/operate that popup before editor input')
    if desktop.main.is_enabled():
        desktop.focus(observation["title"])
    else:
        # Explicitly observed owned FL modal may be operated; hidden main panes may not.
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        root = desktop.win32.window(handle=user32.GetAncestor(window.handle, 2)).wrapper_object()
        if root.handle == desktop.main.handle or not root.is_enabled():
            raise WorkflowError("GUI_BLOCKED", "Target is behind an FL modal dialog")
        from .pyscript_trigger import force_focus
        if not force_focus(root.handle):
            raise WorkflowError("FOCUS_LOST", "Observed FL modal could not receive focus")
    current_image, current_sha = window_image(window)
    navigation=action=='activate' or (action=='keys' and keys in (['f5'],['f6'],['f7'],['f9']))
    if not old.get("image_sha256") or (current_sha != old["image_sha256"] and not navigation):
        from PIL import Image, ImageChops
        changed = state_dir() / 'observations' / token / (operation_id + '-changed.png')
        current_image.save(changed)
        bbox = ImageChops.difference(Image.open(old['image']).convert('RGB'), current_image.convert('RGB')).getbbox() if old.get('image') else None
        raise WorkflowError("VIEW_CHANGED", "Target pixels changed; observe and identify the target again", actual_image=str(changed), changed_bounds=bbox)
    automation_location=None
    if action=='automation_move_value':
        from .native import inspect
        from .vision import locate_playlist, automation_value_target
        from PIL import Image
        if not old['title'].startswith(('播放列表','Playlist')) or point is not None or target is not None or not automation_edit or set(automation_edit)!={'channel','point_index','value'}:
            raise WorkflowError('INVALID_ARGUMENT','Observed Playlist and channel/point_index/value only required')
        state=inspect(desktop.session(focus=False)['path'])
        matches=[c for c in state['playlist'] if c['source_kind']=='channel' and c['source_id']==automation_edit['channel']]
        curves=[a for a in state['automation'] if a['channel']==automation_edit['channel']]
        if len(matches)!=1 or len(curves)!=1:
            raise WorkflowError('AMBIGUOUS_AUTOMATION','Exactly one actual clip and saved curve required')
        layout=locate_playlist(desktop,observation,window)
        automation_location=automation_value_target(Image.open(old['image']),layout,matches[0],curves[0]['points'],automation_edit['point_index'],automation_edit['value'],state['ppq'])
        point=automation_location['point'];target=automation_location['target'];action='drag'
        atomic_json(Path(old['image']).parent/'automation-location.json',automation_location)
    if action in ('sytrus_presets_menu','sytrus_master_menu'):
        from .native import inspect
        state=inspect(desktop.session(focus=False)['path'])
        known=any(c.get('plugin')=='Sytrus' and old['title'].startswith(c.get('name','\0')) for c in state['channels'].values())
        synth=next((c.rectangle() for c in window.descendants() if c.class_name()=='TSynthEditorForm'),None)
        if old['class']!='TPluginForm' or not known or synth is None or (synth.width(),synth.height())!=(850,450):
            raise WorkflowError('UNSUPPORTED_PLUGIN_UI','Only observed native Sytrus 850x450 UI profile is accepted')
        r=window.rectangle()
        if action=='sytrus_presets_menu':
            point=[(r.width()-99)/(r.width()-1),14/(r.height()-1)];action='click'
        else:
            from PIL import Image
            import numpy as np
            sx,sy=synth.left-r.left,synth.top-r.top
            tab=np.asarray(Image.open(old['image']).convert('RGB').crop((sx+6,sy+4,sx+70,sy+25))).astype(float)
            selected=((tab[:,:,0]-tab[:,:,1]>20)&(tab[:,:,1]-tab[:,:,2]>30)).mean()>.4
            if not selected:
                raise WorkflowError('PLUGIN_PAGE_CHANGED','Sytrus Main tab must be visibly selected before master control')
            point=[(sx+33)/(r.width()-1),(sy+70)/(r.height()-1)];action='right_click'
    if action=='piano_snap_menu':
        if not old['title'].startswith(('钢琴卷帘','Piano roll')):
            raise WorkflowError('EDITOR_UNRECOGNIZED','Piano Roll snap menu requires actual editor')
        caption=next((c.rectangle() for c in window.children() if c.class_name()=='TNewCaption'),None)
        if caption is None:
            raise WorkflowError('ANCHOR_UNRECOGNIZED','Native Piano toolbar unavailable')
        scale=caption.height()/23
        r=window.rectangle()
        point=[(caption.left-r.left+54*scale)/(r.width()-1),(caption.top-r.top+10*scale)/(r.height()-1)]
        action='click'
    if action.startswith('piano_'):
        time_marks=None
        if piano_grid is None:
            from .vision import locate_piano
            location=locate_piano(desktop,observation,handle)
            piano_grid=location['grid']
            time_marks={(bar-1)*location['ticks_per_bar']:pixel for bar,pixel in location['time_anchors']}
        if action=='piano_draw' and not piano_snap_bar:
            time_marks=None  # Raster ruler marks do not prove subpixel note precision without snap.
        if piano_snap_bar and (not time_marks or not piano_note or piano_note.get('tick') not in time_marks):
            raise WorkflowError('SNAP_VERIFICATION_REQUIRED','Bar-snap draw requires an actually recognized bar and GUI-selected Bar snap; verify saved note afterward')
        if not old['title'].startswith(('钢琴卷帘', 'Piano roll')) or piano_note is None or point is not None or target is not None:
            raise WorkflowError('INVALID_ARGUMENT', 'Piano actions require observed Piano Roll, explicit grid and note; no raw points')
        musical_action = action.removeprefix('piano_')
        if musical_action not in {'draw', 'move', 'resize', 'delete'}:
            raise WorkflowError('INVALID_ARGUMENT', 'Unsupported Piano Roll action')
        if musical_action == 'draw' and set(piano_note) != {'tick', 'pitch'}:
            raise WorkflowError('INVALID_ARGUMENT', 'Draw sets position/pitch only; FL supplies current length/velocity. Read back, then resize/adjust through GUI')
        point = piano_point(piano_grid, piano_note, window.rectangle(), musical_action,time_marks,piano_snap_bar)
        if musical_action in {'move', 'resize'}:
            if piano_target is None:
                raise WorkflowError('INVALID_ARGUMENT', 'Musical move/resize requires target note')
            if musical_action == 'resize':
                if any(piano_target.get(k) != piano_note.get(k) for k in ('tick', 'pitch')):
                    raise WorkflowError('INVALID_ARGUMENT', 'Resize must retain note start and pitch')
                target = piano_point(piano_grid, piano_target, window.rectangle(), 'resize',time_marks)
            else:
                if piano_target.get('length_ticks') != piano_note.get('length_ticks'):
                    raise WorkflowError('INVALID_ARGUMENT', 'Move must retain actual note length')
                target = piano_point(piano_grid, piano_target, window.rectangle(), 'move',time_marks)
        action = {'draw':'click', 'move':'drag', 'resize':'drag', 'delete':'right_click'}[musical_action]
    if action=='text_click':
        if not text or point is not None:
            raise WorkflowError('INVALID_ARGUMENT','Text click requires visible text and no guessed point')
        from .vision import locate_text
        from PIL import Image
        point=locate_text(Image.open(old['image']),text,Path(old['image']).parent)
        action='click'
    if action not in {"activate", "click", "double_click", "right_click", "drag", "scroll", "keys", "invoke", "set_value", "select"}:
        raise WorkflowError("INVALID_ARGUMENT", "Unsupported GUI action")
    xy = normalized_point(point, window.rectangle()) if point is not None else None
    end = normalized_point(target, window.rectangle()) if target is not None else None
    if action in {"click", "double_click", "right_click", "drag", "scroll"} and xy is None or action == "drag" and end is None:
        raise WorkflowError("INVALID_ARGUMENT", "Canvas actions require observed window-relative points")
    if action=='scroll' and (not isinstance(wheel,int) or not 0<abs(wheel)<=12):
        raise WorkflowError('INVALID_ARGUMENT','Scroll requires nonzero integer wheel count within -12..12')
    if xy is not None:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.WindowFromPoint.argtypes = [wintypes.POINT]
        user32.WindowFromPoint.restype = wintypes.HWND
        user32.IsChild.argtypes = [wintypes.HWND, wintypes.HWND]
        for location in (xy,end) if end is not None else (xy,):
            hit = user32.WindowFromPoint(wintypes.POINT(*location))
            if hit != window.handle and not user32.IsChild(window.handle, hit):
                raise WorkflowError("TARGET_OCCLUDED", "Another window covers an observed drag endpoint/target; no input sent")
    if action == "keys" and (not keys or len(keys) > 4 or any(k not in {"f5", "f6", "f7", "f9", "escape", "enter", "delete", "home", "end", "left", "right", "up", "down", "pageup", "pagedown", "ctrl", "shift", "alt", "a", "d", "z", "y", "1", "2", "3", "4", "5"} for k in keys)):
        raise WorkflowError("INVALID_ARGUMENT", "Unsupported shortcut; use explicit UIA controls")
    control = None
    if action in {"invoke", "set_value", "select"}:
        if not selector or set(selector) - {"automation_id", "name", "type"}:
            raise WorkflowError("INVALID_ARGUMENT", "UIA requires an exact observed selector")
        if not any(all(c.get(k) == v for k, v in selector.items()) for c in old.get("controls", [])):
            raise WorkflowError("CONTROL_NOT_OBSERVED", "Selector was not observed in this window")
        matches = [c for c in desktop.uia.window(handle=window.handle).descendants()
                   if all(getattr(c.element_info, {"type": "control_type"}.get(k, k)) == v for k, v in selector.items())]
        if len(matches) != 1:
            raise WorkflowError("AMBIGUOUS_CONTROL", "Selector must resolve exactly one actual control")
        control = matches[0]
    result = {"ok": False, "operation_id": operation_id, "token": token, "action": action,
              "intent_sha256": intent,
              "handle": str(handle), "phase": "input_pending", "verified": False,
              "retry": "Inspect post-observation; use a new operation ID only after checking actual state"}
    if automation_location is not None:
        result['automation_location']=automation_location
    if not navigation and window_image(window)[1] != old['image_sha256']:
        raise WorkflowError('VIEW_CHANGED','Target changed during automatic localization; no input sent')
    atomic_json(journal, result)  # crash after here is explicitly uncertain, never replayed
    try:
        if action=='activate':
            import ctypes
            from ctypes import wintypes
            api=ctypes.windll.user32
            api.BringWindowToTop.argtypes=[wintypes.HWND]
            parent=window.parent()
            if parent and parent.class_name()=='TWPControl':api.BringWindowToTop(parent.handle)
            api.BringWindowToTop(window.handle)
        window.set_focus()
        if action == "click": p.click(*xy)
        elif action == "double_click": p.doubleClick(*xy, interval=.12)
        elif action == "right_click": p.click(*xy, button="right")
        elif action == 'scroll': p.moveTo(*xy); p.scroll(wheel)
        elif action == "drag":
            p.moveTo(*xy); p.mouseDown()
            try:
                p.moveTo(*end, duration=.7); time.sleep(.3)
            finally: p.mouseUp()
        elif action == "keys": p.hotkey(*keys)
        elif action == "invoke": control.invoke()
        elif action == "set_value": control.set_edit_text(text)
        elif action == "select": control.select()
        time.sleep(.25)
        result.update(ok=True, phase="input_sent", after=observe(desktop),
                      verification_required="Input sent only. Inspect GUI and native/audio readback before claiming success")
        if navigation:
            result['guard_scope']='Editor navigation: owned project, native window/geometry and modal/popup checks; unrelated pixels need not remain identical'
        after_row=next((r for r in result['after']['windows'] if r['handle']==str(handle)),None)
        result['gui_change_observed']=after_row is None or after_row.get('rect')!=old['rect'] or after_row.get('image_sha256')!=old['image_sha256']
    except Exception as exc:
        result.update(phase="uncertain", error={"type": type(exc).__name__, "message": str(exc)})
        try:
            result["after"] = observe(desktop)
        except Exception as capture:
            result["observation_error"] = type(capture).__name__
    atomic_json(journal, result)
    return result
