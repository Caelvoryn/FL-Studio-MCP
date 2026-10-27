"""Source checkout entry point; does not modify any installed MCP configuration."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fl_studio_mcp.server import main

if __name__ == "__main__":
    import os
    if os.environ.get("FLSTUDIO_MCP_STACK_DIAGNOSTICS") == "1":
        import faulthandler
        from fl_studio_mcp.workflow import state_dir
        state_dir().mkdir(parents=True, exist_ok=True)
        stack_log = (state_dir() / "python-stack.log").open("a", encoding="utf8")
        faulthandler.dump_traceback_later(15, repeat=True, file=stack_log)
    main()
