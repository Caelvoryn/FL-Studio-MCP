"""Small public surface for independently verified local workflow operations."""
from __future__ import annotations

import importlib.metadata
import os
import platform
from pathlib import Path

from .. import __version__
from ..connection import TCPBridge
from ..workflow import Journal, WorkflowError, audio_integrity, compare_audio, copy_exclusive, digest


def register(mcp):
    ro = {"readOnlyHint": True, "idempotentHint": True}

    @mcp.tool(annotations=ro)
    def fl_system_health() -> dict:
        """Check dependency versions and existing local daemon using bounded reads; never starts or reconfigures FL."""
        deps = {}
        for package in ("fastmcp", "pydantic", "mido", "numpy", "soundfile", "librosa", "pyautogui"):
            try:
                deps[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                deps[package] = None
        bridge = TCPBridge(default_timeout=3.)
        try:
            ping = bridge.call("ping", timeout=3.)
            project = bridge.call("get_project_state", timeout=3.)
            connection = {"ok": True, "ping": ping, "project": project}
        except Exception as exc:
            connection = {"ok": False, "error": type(exc).__name__, "message": str(exc),
                          "remedy": "Start FL Studio, loopMIDI and the existing local daemon; check controller and paired ports"}
        return {"ok": connection["ok"], "server_version": __version__, "python": platform.python_version(), "dependencies": deps,
                "connection": connection, "configuration_management": "Read-only health check; does not edit client configuration",
                "gui_automation": "historical machine-specific helpers; general UIA adapter not verified",
                "legacy_tools": "not all independently verified; consult docs/inherited_tools.json"}

    @mcp.tool(annotations={"readOnlyHint": False, "idempotentHint": True, "destructiveHint": False})
    def fl_project_checkpoint(source: str, destination: str, job_id: str) -> dict:
        """Copy an existing saved FLP to a NEW path and verify SHA256. Does not save unsaved FL state or open a project. Existing destinations are never overwritten; same job inputs reuse verified evidence."""
        try:
            source, destination = Path(source).resolve(), Path(destination).resolve()
            if source.suffix.lower() != ".flp" or destination.suffix.lower() != ".flp":
                raise WorkflowError("INVALID_ARGUMENT", "Both paths must end in .flp")
            if not source.is_file():
                raise WorkflowError("FILE_NOT_FOUND", "Source FLP is missing")
            with source.open("rb") as stream:
                if stream.read(4) != b"FLhd":
                    raise WorkflowError("INVALID_FLP", "Missing native FLhd header")
            inputs = {"source": str(source), "destination": str(destination), "source_sha256": digest(source)}
            return Journal(job_id).step("checkpoint", inputs,
                lambda: copy_exclusive(source, destination),
                lambda r: destination.is_file() and digest(destination) == r["sha256"])
        except WorkflowError as exc:
            return exc.result()
        except OSError as exc:
            return WorkflowError("FILESYSTEM", str(exc)).result()

    @mcp.tool(annotations=ro)
    def fl_verify_render(path: str, minimum_seconds: float = .05, maximum_seconds: float = 3600.) -> dict:
        """Decode actual audio; reject missing, corrupt, nonfinite, empty, silent or unexpected-duration output. Report actual format/sample peak/RMS/clipping. This does not render or listen."""
        try:
            return audio_integrity(path, minimum_seconds, maximum_seconds)
        except WorkflowError as exc:
            return exc.result()

    @mcp.tool(annotations=ro)
    def fl_compare_renders(first: str, second: str) -> dict:
        """Compare decoded audio including all samples; classify exact PCM, numeric difference or format/duration change. Never infer aesthetic quality from numbers."""
        try:
            return compare_audio(first, second)
        except WorkflowError as exc:
            return exc.result()

    @mcp.tool(annotations=ro)
    def fl_workflow_status(job_id: str) -> dict:
        """Read persistent step evidence. Interrupted/failed mutations require inspection and a new version; no blind retry or automatic replay."""
        try:
            journal = Journal(job_id)
            return {"ok": True, "exists": journal.path.exists(), **journal.load()}
        except WorkflowError as exc:
            return exc.result()

    @mcp.tool(annotations=ro)
    def fl_inspect_native_project(path: str) -> dict:
        """Read a saved FL26.1.5 FLP: full note records, instrument state hashes, sample references, Playlist extents and automation. Never opens, rewrites, or claims to inspect unsaved state. Unknown event layouts fail explicitly."""
        from ..native import inspect
        try:
            return {"ok": True, "verified": True, "saved_state": inspect(path)}
        except FileNotFoundError as exc:
            return WorkflowError("FILE_NOT_FOUND", str(exc)).result()
        except (ValueError, IndexError, KeyError, UnicodeError) as exc:
            return WorkflowError("UNSUPPORTED_FLP", str(exc)).result()
