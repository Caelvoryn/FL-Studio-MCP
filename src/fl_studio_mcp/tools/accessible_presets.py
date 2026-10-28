from typing import Literal
from ..connection import get_bridge,FLBridgeError
from ..workflow import WorkflowError
from .vst import _identity


def register(mcp):
    @mcp.tool(annotations=dict(readOnlyHint=False,destructiveHint=False,idempotentHint=False))
    def fl_vst_accessible_preset(action: Literal['read','select'],track: int,expected_plugin: str,
                                 expected_channel: str,expected_title: str,
                                 menu_path: list[str]|None=None,expected_current: str|None=None) -> dict:
        """Explicit no-image/no-mouse UIA FALLBACK for hosted Pianoteq9 preset names/menu selection.
        Parameters still use direct host bridge. Does not claim host internal preset API support.
        Requires one visible hosted plugin window and owned independent saved session established
        by fl_host_project_file. Select requires exact observed model/preset menu path and current
        name; selecting a preset resets its parameters. Does not blindly retry on failure.
        Other VSTs have no verified accessibility profile; no generic compatibility inference."""
        try:
            if action=='select' and (not menu_path or not expected_current):
                raise WorkflowError('INVALID_ARGUMENT','Selection requires exact menu path and current preset')
            bridge=get_bridge()
            if bridge.call('get_play_state').get('playing') is not False:
                raise WorkflowError('TRANSPORT_ACTIVE','Stop transport before preset operations')
            _identity(bridge,track,-1,expected_plugin,expected_channel)
            from ..host_io import HostFiles
            from ..accessible_presets import AccessiblePresets
            host=HostFiles();host._require_owned(expected_title)
            if action=='select':
                # JUCE popups created while another app owns foreground were
                # observed to expand the wrong submenu. Activate/verify FL first.
                host.focus(expected_title)
            adapter=AccessiblePresets(host,expected_channel,expected_plugin)
            result=(dict(ok=True,verified=True,readback=adapter.read(),execution_kind='UIA_NameProperty_fallback')
                    if action=='read' else adapter.select(menu_path,expected_current))
            _identity(bridge,track,-1,expected_plugin,expected_channel)
            return result
        except (WorkflowError,FLBridgeError,OSError) as exc:
            return exc.result() if isinstance(exc,WorkflowError) else WorkflowError('PRESET_ACCESSIBILITY_FAILED',str(exc)).result()
        except Exception as exc:
            return WorkflowError('ACCESSIBILITY_UNAVAILABLE',str(exc),exception_type=type(exc).__name__,
                                 recovery='Observe the current preset/menu before retry; no automatic replay').result()
