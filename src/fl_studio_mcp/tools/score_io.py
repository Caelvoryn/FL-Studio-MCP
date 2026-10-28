"""Explicitly opt-in, verified basic MIDI importer, not internal Score API."""
from ..workflow import WorkflowError
from ..connection import get_bridge


def register(mcp):
    @mcp.tool(annotations=dict(readOnlyHint=False,destructiveHint=True,idempotentHint=False))
    def fl_score_replace_basic(channel:int,expected_channel:str,pattern:int,expected_notes:list[dict],notes:list[dict],
                                midi_path:str,before_path:str,after_path:str,expected_title:str)->dict:
        """Replace known basic score through real FL MIDI importer using keyboard/UIA, no screenshots/mouse.
        Notes/expected_notes use pitch,time_ticks,length_ticks,velocity_raw integers. Supports chords.
        Fresh native before/after FLPs independently verify exact target notes and unchanged other note
        records. Separate-Pattern multi-instrument workflow tested. Imported notes on OTHER channels
        in the same Pattern cause a preflight refusal because FL can clear their import marker.
        Requires owned test session and selected Pattern. Advanced note properties are refused;
        empty desired score clears the basic score without importing an empty MIDI. A failed postcheck
        means possible partial live edits: inspect
        preserved checkpoints, never retry blindly. NOT a direct Piano Roll scripting API."""
        try:
            from ..host_io import HostFiles
            from ..score_io import replace_basic
            if type(channel)is not int or channel<0 or type(pattern)is not int or pattern<1:
                raise WorkflowError('INVALID_ARGUMENT','Valid nonnegative channel and positive Pattern required')
            return replace_basic(HostFiles(),get_bridge(),channel,expected_channel,pattern,expected_notes,notes,
                                 midi_path,before_path,after_path,expected_title)
        except WorkflowError as exc:return exc.result()
        except Exception as exc:
            return WorkflowError('SCORE_IMPORT_FAILED',str(exc),exception_type=type(exc).__name__,
                recovery='May have partially edited live score; inspect actual before/after checkpoints before retry').result()
