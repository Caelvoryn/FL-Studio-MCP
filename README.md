# FL Studio MCP 1.2.0.dev2 — UI-first development candidate

**Latest checkpoint: [coordinate-free prerequisite acceptance, 2026-10-29](docs/STAGE3_20261029_ACCEPTANCE.md).**
After unlock, real stdio MCP loaded Pianoteq9/Sylenth1, imported basic notes into separate
Patterns, assigned free Mixer tracks, inserted EQ/Compressor/Reeverb and verified saved/reopened
state and actual WAVs.194 offline tests pass. Full16-bar arrangement remains **incomplete**:
Playlist placement and automation in this direct-first workflow are not accepted. PCM repeats
differ. The [locked-desktop report](docs/STAGE3_ACCEPTANCE.md) is historical.

**Latest development checkpoint:** [direct-control foundation acceptance](docs/FOUNDATION_ACCEPTANCE.md)
records real BPM/channel/Mixer edits, guarded sends, Pattern creation/cloning, native persistence
and WAV tests.164 regression tests pass; channel/Score/Playlist/automation CRUD remain incomplete.

**`codex/pianoteq-direct` development branch:** real FL-hosted Pianoteq9 parameter control,
named presets through explicit no-image UIA fallback, editable MIDI and native save/reopen/WAV
acceptance are documented in [Pianoteq host acceptance](docs/PIANOTEQ_HOST_ACCEPTANCE.md).
Direct VST writes are opt-in; the stable UI-first implementation/default configuration is preserved.
Preset/file fallbacks are not internal FL APIs. Repeated WAV PCM is not bit-identical.

**Current matrix: [dev2 acceptance and limits](docs/DEV2_ACCEPTANCE.md).** Older dev1 reports are retained as history. Native/visual/OCR automatic grid measurement covers tested Piano Roll and Playlist layouts. This is not universal coordinate-free automation.

**Security release gate remains open:** tested dependencies have3 deduplicated known advisories; see [security review](docs/SECURITY_REVIEW.md). Local GUI/audio acceptance does not imply a clean security audit. Do not use as a production or public-network deployment.

Windows / Python 3.12 / FL Studio 26.1.5 build 5618. Based on rosasynthesiz/flstudio-mcp; MIT retained. **Development preview, not universal desktop automation.** No running MCP configuration/controller is replaced.

The preserved UI-first workflow uses GUI input and calibrated canvas targets. The opt-in direct
branch instead prefers structured official host operations; missing loading/file/score operations
use explicitly labeled keyboard/UIA fallbacks. New accepted operations use no coordinates.
Three diagnostic screenshots identified IME interference during development; they are not needed
by the accepted picker path. Neither architecture is universal control of all FL features.

Default mode hides legacy background music writers. Explicit `FLSTUDIO_MCP_ENABLE_LEGACY_WRITES=1` exposes compatibility tools; never describe those writes as GUI actions.

See [capabilities](docs/CAPABILITIES.md), [real acceptance](docs/UI12_ACCEPTANCE.md), [workflow](docs/WORKFLOW.md), [profiles](docs/UI_PROFILES.md). GUI input receipts deliberately return `verified=false`: observe post-state, save and independently verify the musical target.

## Isolated installation

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -r requirements-system-tested.txt
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple --no-deps -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest tests/test_ui_first.py -q
```

Full inherited regression explicitly exercises legacy writers against unit fakes, not real FL:

```powershell
$env:FLSTUDIO_MCP_ENABLE_LEGACY_WRITES = '1'
try { .\.venv\Scripts\python.exe -m pytest tests -q }
finally { Remove-Item Env:FLSTUDIO_MCP_ENABLE_LEGACY_WRITES }
```

GUI operations require an interactive Windows desktop. Use an isolated preserved test project, stop transport, avoid simultaneous manual input, and retain checkpoints. `fl_gui_save_as` first establishes owned project identity. Existing compatible controller/loopMIDI bridge is needed for read-only verification and Playlist transport checks. Do not reinstall or overwrite an existing controller automatically. Review the example configuration separately; it is not merged into running configuration.

Bridge and candidate must share the private state directory for cooperating OS locks. Unrelated processes/manual edits cannot be locked. Unknown modals/layouts fail safely. Dev2 verifies one Sytrus factory-preset path, automation creation/move/curve-value edit, and strict saved/audio readback. No universal third-party, all-DPI, audio-clip or arbitrary routing/FX support. Private logs, screenshots, FLPs/WAVs and commercial content stay outside public source. A local ZIP is not GitHub publication.

Install Windows OCR language capabilities for the actual UI (tested zh-Hans and en-US). If OCR is unavailable or ambiguous, operations stop and retain diagnostics. Generator readback indices follow the current Channel Rack filter: select All through GUI and pass `expected_channel` to `fl_plugin_state`.
