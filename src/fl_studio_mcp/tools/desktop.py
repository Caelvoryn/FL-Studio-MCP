"""Verified GUI/Playlist tools; all mutations use the server's transaction guard."""
from typing import Annotated, Literal

from pydantic import Field

from ..desktop import FLDesktop
from ..workflow import WorkflowError


def invoke(method, *args, **kwargs):
    try:
        return getattr(FLDesktop(), method)(*args, **kwargs)
    except WorkflowError as exc:
        return exc.result()
    except Exception as exc:
        return WorkflowError("GUI_FAILURE", str(exc), exception_type=type(exc).__name__,
                             recovery="Inspect actual windows and saved checkpoints; no blind retry").result()


def register(mcp):
    ro = {"readOnlyHint": True, "idempotentHint": True}
    wr = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False}

    @mcp.tool(annotations=ro)
    def fl_ui_observe() -> dict:
        """Observe actual FL windows, UIA controls and screenshots. No bridge or project writes. Returns expiring tokens for UI input."""
        from ..ui_first import observe
        try:
            return observe()
        except WorkflowError as exc:
            return exc.result()

        except Exception as exc:
            return WorkflowError('UI_OBSERVATION_FAILED',str(exc),exception_type=type(exc).__name__,recovery='Inspect current desktop; no input performed').result()

    @mcp.tool(annotations=ro)
    def fl_ui_locate_piano() -> dict:
        """Automatically measure visible Piano Roll using native anchors, screenshot grid lines and Windows OCR octave/time labels. No GUI input. Unknown grid/language/scale fails with diagnostic images; success requires independent saved-note verification after editing."""
        from ..ui_first import observe
        from ..vision import locate_piano
        try:
            desktop = FLDesktop()
            observation = observe(desktop)
            editors = [w for w in observation['windows'] if w['class']=='TEventEditForm' and w['title'].startswith(('钢琴卷帘','Piano roll'))]
            if len(editors)!=1:
                raise WorkflowError('EDITOR_UNRECOGNIZED','Exactly one visible Piano Roll required')
            handle=editors[0]['handle']
            measured=locate_piano(desktop,observation,handle)
            return dict(ok=True,verified=False,token=observation['token'],handle=handle,**measured)
        except WorkflowError as exc:
            return exc.result()
        except Exception as exc:
            return WorkflowError('UI_LOCALIZATION_FAILED',str(exc),exception_type=type(exc).__name__,recovery='Inspect retained observation; no input performed').result()

    @mcp.tool(annotations=wr)
    def fl_ui_act(token: str, operation_id: str, handle: str, action: str,
                  point: list[float] | None = None, target: list[float] | None = None,
                  keys: list[str] | None = None, text: str | None = None,
                  selector: dict[str, str] | None = None,
                  piano_grid: dict[str, float] | None = None,
                  piano_note: dict[str, int] | None = None,
                  piano_target: dict[str, int] | None = None,
                  wheel: Annotated[int, Field(ge=-12,le=12)] = 0,
                  piano_snap_bar: bool = False,
                  automation_edit: dict | None = None) -> dict:
        """Real GUI input on an unchanged observed FL window and owned project. UIA invoke/set_value/select require an exact observed selector; raw click/right_click/drag use normalized window fractions. piano_draw/move/resize/delete use piano_note/target and automatically measured grid when piano_grid is omitted. Bar snap must be selected/verified in GUI before piano_snap_bar=true. text_click selects unique actual OCR text, optionally handle=active_popup. activate raises a visible editor/plugin. sytrus_presets_menu/master_menu require tested stock profile. automation_move_value takes automation_edit={channel,point_index,value}: existing visible non-flat purple curve only, no timing edit. Draw inherits FL length/velocity. Single-use journal; input_sent and screenshot change are not musical success. Save NEW checkpoint and verify native/live/audio results. Never writes FLP/MIDI/bridge parameters."""
        from ..ui_first import act
        try:
            return act(token, operation_id, handle, action, point, target, keys, text, selector, piano_grid, piano_note, piano_target, wheel,piano_snap_bar,automation_edit)
        except WorkflowError as exc:
            return exc.result()
        except Exception as exc:
            return WorkflowError('UI_INTERNAL_ERROR',str(exc),exception_type=type(exc).__name__,
                                 recovery='Inspect saved observation and operation journal before retrying').result()

    @mcp.tool(annotations=ro)
    def fl_desktop_state() -> dict:
        """Read real FL process/window title, enabled state, modal dialogs and geometry. Does not close windows. Dirty-state is unknown."""
        return invoke("state")

    @mcp.tool(annotations=wr)
    def fl_gui_save_as(destination: str, expected_title: str) -> dict:
        """Save current actual FL project to a NEW FLP via UIA; reject title mismatch/overwrite, parse actual saved bytes and establish owned GUI session. Captures unsaved changes without overwriting original."""
        return invoke("save_as", destination, expected_title)

    @mcp.tool(annotations=wr)
    def fl_gui_open_project(path: str, preserve_current_to: str, verify_to: str, expected_title: str) -> dict:
        """Preserve current FL state by Save As to NEW path, open existing FLP via UIA, save to another NEW path and compare native semantics. Missing plugin/modal dialogs are NOT dismissed automatically."""
        return invoke("open_project", path, preserve_current_to, verify_to, expected_title)

    @mcp.tool(annotations=wr)
    def fl_gui_render_wav(destination: str, expected_title: str,
                          minimum_seconds: Annotated[float, Field(gt=0, le=3600)],
                          maximum_seconds: Annotated[float, Field(gt=0, le=3600)],
                          timeout: Annotated[float, Field(gt=0, le=180)] = 90.) -> dict:
        """Render actual FL audio to a NEW WAV: UIA file chooser, verified FL26 render form, clear time selection, Cut remainder, bounded completion and full PCM integrity. Unknown window layouts fail; output format is reported from actual audio."""
        return invoke("render", destination, expected_title, minimum_seconds, maximum_seconds, timeout)

    @mcp.tool(annotations=wr)
    def fl_playlist_calibrate(grid_left: float | None = None, first_track_top: float | None = None,
                              pixels_per_bar: float | None = None, track_height: float | None = None) -> dict:
        """With no arguments, measure native anchors plus OCR ruler/Track labels. Or supply all four explicit screenshot measurements. Requires owned project, bar1/track1, uniform tracks and 4/4. Calibration alone is not musical verification."""
        if all(v is None for v in (grid_left,first_track_top,pixels_per_bar,track_height)):
            from ..vision import locate_playlist
            try:
                desktop=FLDesktop()
                measured=locate_playlist(desktop)
                result=desktop.calibrate(**{k:measured[k] for k in ('grid_left','first_track_top','pixels_per_bar','track_height')})
                result['automatic_measurement']=measured
                return result
            except WorkflowError as exc:
                return exc.result()
        if any(v is None for v in (grid_left,first_track_top,pixels_per_bar,track_height)):
            return WorkflowError('INVALID_ARGUMENT','Supply no calibration arguments or all four').result()
        return invoke("calibrate", grid_left, first_track_top, pixels_per_bar, track_height)

    @mcp.tool(annotations=wr)
    def fl_playlist_edit(action: Literal["copy", "move", "trim", "delete"], clip_index: Annotated[int, Field(ge=0)],
                         output_path: str, position_ticks: Annotated[int | None, Field(ge=0)] = None,
                         track: Annotated[int | None, Field(ge=1, le=500)] = None,
                         length_ticks: Annotated[int | None, Field(gt=0)] = None) -> dict:
        """Edit an existing Pattern clip through real calibrated FL GUI. Makes a NEW native pre-checkpoint, refuses stale/overlapped/out-of-view state, saves NEW result and verifies clip/source/track/offset plus all other musical state. Failed artifacts retained; no FLP byte mutation."""
        return invoke("edit_playlist", action, clip_index, output_path, position_ticks, track, length_ticks)
