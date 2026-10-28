# 1.2 UI-first capability matrix

**Current direct-first delta, 2026-10-29:** see [actual acceptance](STAGE3_20261029_ACCEPTANCE.md).
Pianoteq9/Sylenth1 native picker loading, separate-Pattern basic-note import, free Mixer assignment
and selected-track EQ2/Compressor/Reeverb2 insertion now have real coordinate-free host evidence.
Parameters use direct host reads/writes; loading and file operations are keyboard/UIA fallbacks.
Same-Pattern imported-note interference is refused, not normalized away. Direct-first Playlist
placement and automation remain unaccepted. The following table describes the retained UI-first
version, not a claim that all branch mutations use GUI or that all plugins are supported.

Latest stage3 status: [blocked full-arrangement acceptance](STAGE3_ACCEPTANCE.md).
Experimental score/picker source is not a verified capability and is hidden by default.

**Latest branch matrix:** [direct-control foundation](FOUNDATION_ACCEPTANCE.md), including
four real-tested tools and all remaining channel/notes/Playlist/automation restrictions.

**Direct-control development branch update:** [Pianoteq host acceptance](PIANOTEQ_HOST_ACCEPTANCE.md)
records verified host parameter control and explicit no-image UIA preset/file fallbacks.
The UI-first tables below remain historical; other VSTs do not inherit the Pianoteq UIA profile.

**Historical dev1 table below. Current dev2 matrix: [DEV2_ACCEPTANCE.md](DEV2_ACCEPTANCE.md).** Automatic measurement, bounded automation and one factory-preset path are now separately validated there; no universal support claim.

Status applies only to recorded Windows FL26.1.5 tests.

| Module | Actual GUI / independent verification | Status and limits |
|---|---|---|
| Observation | Win32 windows, screenshots, UIA tree | Verified; no automatic semantic grid recognition |
| Piano Roll | F7; draw, move, resize, delete; saved raw note comparison | Verified calibrated grid; other zoom/scroll positions need fresh calibration |
| Note velocity | Note Properties visible knob, Accept; native 100→90 | Verified FL modal; not generic UIA slider |
| Recovery | Ctrl+Z after deletion; all raw notes restored | Verified single deletion; no generic automatic undo assumption |
| Chords | Independent GUI note draws on calibrated tick/pitch grid | See acceptance; draw inherits FL length/velocity, requiring readback |
| Channel Rack | F6, actual existing instrument button/window | Verified existing Sytrus; arbitrary instrument insertion/replacement unaccepted |
| Plugin | Visible Sytrus master slider; actual .8→.75 read-only state | Verified Sytrus only; no universal third-party adapter |
| Presets | Actual existing Smooth UI and saved plugin state | Existing preset confirmed; generalized GUI preset loading unaccepted |
| Mixer | F9, real Lead fader; .65→.6361 read-only state | Volume verified; pan/mute/send/routing/effect creation unaccepted |
| Playlist Pattern | GUI move/copy/trim/delete; native source/track/position/length/offset plus other musical state | Verified bounded calibrated uniform canvas; changed viewport refuses |
| Overlap safety | Shared-instrument overlap blocked across lanes; real negative/no artifact | Verified same Pattern; disjoint-channel policy unit-tested only |
| Audio/automation clips | Existing state retained | GUI editing unimplemented |
| Save/Open | UIA file type/filename/Invoke; actual native hashes/semantics | Verified NEW paths only; unknown modals stop |
| Export | Real render window; decoded WAV/duration/silence/peaks/reopened PCM | Verified tested form/current WAV format; arbitrary rate/depth selection unaccepted |
| General UIA | Exact unique observed selector, invoke/value/select | Primitive implemented; not all FL controls expose UIA |
| Failures | Expiry/pixel/geometry/title/process/occlusion guards; durable intent journal | Real stale-view/ID-conflict negatives; offline guard tests; safe false refusals possible |
| Listening | Real WAV for user review | No subjective UI12 listening feedback yet |

All tested musical mutations use GUI input. This is not the percentage of all possible FL operations. Backend reads, native parsing and audio analysis are separate evidence categories. Unimplemented rows are never silently filled by legacy background writers.
