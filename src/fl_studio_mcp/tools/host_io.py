"""One opt-in, explicit keyboard/UIA fallback tool; no screenshot/mouse calls."""
from typing import Literal
from ..workflow import WorkflowError
from ..connection import get_bridge, FLBridgeError


def register(mcp):
    @mcp.tool(annotations=dict(readOnlyHint=False,destructiveHint=False,idempotentHint=False))
    def fl_host_project_file(action: Literal['save_as','reopen_copy','export_wav'],destination: str,
                             expected_title: str,source: str|None=None,preserve_current_to: str|None=None,
                             minimum_seconds: float=.05,maximum_seconds: float=3600) -> dict:
        """OPT-IN keyboard/UIA FALLBACK, not internal FL file API. No screenshots/mouse.
        Save As exclusively to a new independent FLP; reopen_copy first preserves current session
        then opens a fresh byte-for-byte copy; export_wav requires an owned saved session and
        verifies actual audio. Existing render settings inherited, not programmatically configured.
        Requires visible Playlist, stopped transport, supported native dialogs and exact FL title.
        Never overwrites. A timeout is uncertain: inspect state and choose fresh paths before retry.
        Reopen result alone does not prove plugin parameter persistence: reread through host."""
        try:
            if get_bridge().call('get_play_state').get('playing') is not False:
                raise WorkflowError('TRANSPORT_ACTIVE','Stop transport before host file operations')
            if action=='reopen_copy' and (not source or not preserve_current_to):
                raise WorkflowError('INVALID_ARGUMENT','Reopen requires source and preservation paths')
            if not 0<minimum_seconds<=maximum_seconds<=3600:
                raise WorkflowError('INVALID_ARGUMENT','Require 0<minimum_seconds<=maximum_seconds<=3600')
            from ..host_io import HostFiles
            host=HostFiles()
            if action=='save_as':return host.save_as_no_image(destination,expected_title)
            if action=='reopen_copy':return host.reopen_copy(source,destination,preserve_current_to,expected_title)
            return host.export_wav_no_image(destination,expected_title,minimum_seconds,maximum_seconds)
        except (WorkflowError,FLBridgeError,OSError) as exc:
            return exc.result() if isinstance(exc,WorkflowError) else WorkflowError('HOST_FILE_FAILED',str(exc)).result()
        except Exception as exc:
            return WorkflowError('HOST_UIA_UNAVAILABLE',str(exc),exception_type=type(exc).__name__,
                                 recovery='Inspect actual files and dialog state before retry; no automatic replay').result()
