"""FastMCP entry point for the FL Studio MCP server.

Run with::

    python -m fl_studio_mcp.server

or, after ``pip install -e .``, with::

    fl-studio-mcp

To see what MIDI ports the host OS exposes (useful when troubleshooting the
loopMIDI / IAC Driver setup)::

    fl-studio-mcp --list-ports
"""

from __future__ import annotations

import logging
import os
import sys

from fastmcp import FastMCP

from . import __version__
from .connection import list_ports
from .protocol import port_from_fl_name, port_to_fl_name
from .tools import arrange as arrange_tools
from .tools import audio as audio_tools
from .tools import bulk as bulk_tools
from .tools import chains as chains_tools
from .tools import color as color_tools
from .tools import compose as compose_tools
from .tools import export as export_tools
from .tools import mix_doctor as mix_doctor_tools
from .tools import mixing as mixing_tools
from .tools import phase1 as phase1_tools
from .tools import pianoroll as pianoroll_tools
from .tools import plugin as plugin_tools
from .tools import presets as presets_tools
from .tools import resources as resource_defs
from .tools import routing as routing_tools
from .tools import transport as transport_tools
from .tools import workflow as workflow_tools
from .tools import desktop as desktop_tools
from .workflow import mutation_lock, trace_mutation, WorkflowError


logger = logging.getLogger("fl_studio_mcp")


SERVER_INSTRUCTIONS = """\
FL Studio MCP server -- control FL Studio from an AI assistant.

REQUIREMENTS
  1. FL Studio 20.7 or newer must be running.
  2. Two virtual MIDI ports must exist (one in each direction):
       - 'FLStudioMCP RX' (server -> FL)
       - 'FLStudioMCP TX' (FL -> server)
     Windows: create both in loopMIDI. macOS: enable two buses in IAC Driver
     (Audio MIDI Setup). Linux: use snd-virmidi.
  3. The FLStudioMCP controller script must be installed under
     Documents/Image-Line/FL Studio/Settings/Hardware/FLStudioMCP/
  4. In FL Studio: Options > MIDI Settings,
       - Enable 'FLStudioMCP RX' in the Input list, set Controller type to
         FLStudioMCP, give it a Port number (any value, e.g. 42).
       - Enable 'FLStudioMCP TX' in the Output list, set Port to the SAME
         number. This is how FL routes the script's outgoing SysEx back to
         the MCP server.
  5. Call fl_ping first to verify the bridge is healthy.

LIMITS YOU SHOULD KNOW ABOUT (these are FL API limitations, not server bugs)
  - Cannot load new VST/AU plugin instances. You can only control plugins
    that already exist in the project.
  - Pattern creation/cloning uses available controller commands. Playlist placement,
    arbitrary plugin loading, native save/open and rendering still need GUI assistance.
  - Channel Rack filtering changes indices. channel_select does not retarget an
    already-open Piano Roll. Explicitly open the desired channel and verify saved notes.
  - Note delivery/keyboard shortcuts are unverified until native project readback.
  - Pattern tempo events may override a successful tempo write. Verify actual playback
    and render duration; a global BPM read alone does not prove persistence.
  - Tempo writes are sometimes ignored if FL is in a modal dialog.

When the user asks for something outside these limits, explain the limit
clearly rather than retrying.
"""


def build_server() -> FastMCP:
    mcp = FastMCP(
        name="fl-studio-mcp",
        version=__version__,
        instructions=SERVER_INSTRUCTIONS,
    )
    # Wrap registered mutating tools at their outer boundary. One lock covers
    # snapshot/write/readback, including grouped calls. Other legacy servers do
    # not cooperate with this lock and must not edit the same project.
    import functools
    import inspect
    register_tool = mcp.tool

    def finish(result, entry):
        if isinstance(result, dict):
            result.setdefault("verified", False)
            if not result["verified"]:
                result.setdefault("status", "execution_unverified")
            result["request_id"] = entry["request_id"]
            entry["output"] = result
        return result

    def guarded_tool(*args, **kwargs):
        if args and callable(args[0]):
            return register_tool(*args, **kwargs)
        decorator = register_tool(*args, **kwargs)
        readonly = (kwargs.get("annotations") or {}).get("readOnlyHint", False)
        def attach(fn):
            # UI-first is the candidate default. Keep original implementations
            # intact, but require explicit opt-in to expose background writers.
            gui_write = fn.__name__.startswith(("fl_ui_", "fl_gui_", "fl_playlist_"))
            backup = fn.__name__ == "fl_project_checkpoint"
            if not readonly and not gui_write and not backup and os.environ.get("FLSTUDIO_MCP_ENABLE_LEGACY_WRITES") != "1":
                return fn
            if readonly or fn.__name__ == "fl_project_checkpoint":
                return decorator(fn)  # checkpoint journal already locks its transaction
            if inspect.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def guarded(*a, **kw):
                    try:
                        with mutation_lock(), trace_mutation(fn.__name__, {"args": a, "kwargs": kw}) as entry:
                            return finish(await fn(*a, **kw), entry)
                    except WorkflowError as exc:
                        return exc.result()
            else:
                @functools.wraps(fn)
                def guarded(*a, **kw):
                    try:
                        with mutation_lock(), trace_mutation(fn.__name__, {"args": a, "kwargs": kw}) as entry:
                            return finish(fn(*a, **kw), entry)
                    except WorkflowError as exc:
                        return exc.result()
            return decorator(guarded)
        return attach
    mcp.tool = guarded_tool
    transport_tools.register(mcp)
    phase1_tools.register(mcp)      # project/mixer/channel read+write + safety
    pianoroll_tools.register(mcp)   # Phase 2: write notes into the piano roll
    plugin_tools.register(mcp)      # Phase 1B: plugin param read/write (name or index)
    mixing_tools.register(mcp)      # Slice B: high-level EQ mixing intents
    routing_tools.register(mcp)     # Routing/cleanup Slice 1: read-only
    bulk_tools.register(mcp)        # Bulk mute/solo: server-side group orchestration
    color_tools.register(mcp)       # Track/channel coloring: name/hex -> FL RGB, one rollback unit
    arrange_tools.register(mcp)     # Arrangement Slice 1: pattern create/clone + markers
    resource_defs.register(mcp)     # MCP resources: fl://status, fl://project, ...
    audio_tools.register(mcp)       # Integration 2/3: audio analysis (tempo/key)
    compose_tools.register(mcp)     # Raga/scale composer: write Claude notes via the bridge
    chains_tools.register(mcp)      # Genre chain setup: map recipes to existing plugins
    export_tools.register(mcp)      # MIDI export: arrangement spec -> type-1 .mid on disk
    presets_tools.register(mcp)     # Preset suggester: read preset names from disk
    mix_doctor_tools.register(mcp)  # Mix Doctor: diagnose whole mix + gated apply-fixes
    # Later tool packs register here as they ship:
    #   pattern_tools.register(mcp)
    workflow_tools.register(mcp)
    desktop_tools.register(mcp)
    mcp.tool = register_tool
    return mcp


def _print_ports() -> int:
    ports = list_ports()
    expected_out = port_to_fl_name()
    expected_in = port_from_fl_name()
    print("Expected port names (override via FLSTUDIO_MCP_PORT_TO_FL / _FROM_FL):")
    print("  server output (commands -> FL):  %r" % expected_out)
    print("  server input  (responses <- FL): %r" % expected_in)
    print()
    print("MIDI output ports visible to this Python process:")
    for name in ports["outputs"]:
        marker = "  -> " if expected_out.lower() in name.lower() else "     "
        print(marker + repr(name))
    print()
    print("MIDI input ports visible to this Python process:")
    for name in ports["inputs"]:
        marker = "  <- " if expected_in.lower() in name.lower() else "     "
        print(marker + repr(name))
    return 0


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("FLSTUDIO_MCP_LOG", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if "--list-ports" in sys.argv:
        sys.exit(_print_ports())

    logger.info(
        "fl-studio-mcp %s; ports: out=%r, in=%r",
        __version__, port_to_fl_name(), port_from_fl_name(),
    )
    # Windows stdio acceptance exposed a native-extension import stall when
    # NumPy was first loaded inside the running MCP event loop. Initialize
    # optional audio DLLs before starting that loop; absence remains optional.
    try:
        import numpy  # noqa: F401
        import soundfile  # noqa: F401
    except ImportError:
        logger.info("Optional audio dependencies unavailable; install the audio extra for audio tools")
    if sys.platform == "win32":
        # Initialize COM/UIA before the MCP event loop, just as native audio DLLs.
        import pywinauto  # noqa: F401
    server = build_server()
    server.run()  # stdio transport by default


if __name__ == "__main__":
    main()
