# 1.2.0.dev1 real UI acceptance — 2026-10-27

Archived dev1 evidence. Current version and GitHub status are documented separately in [dev2 acceptance](DEV2_ACCEPTANCE.md) and the local delivery report; publication paragraph below is historical.

This is a bounded UI-first development candidate, not complete universal FL automation. Public source contains no private logs, screenshots, commercial presets or projects/audio. Local evidence records actual input/output, pre/post screenshots and saved artifacts.

## Actual UI workflow

| Input / action | Actual result | Independent readback |
|---|---|---|
| GUI Save As baseline | New isolated FLP | 809 original editable notes, existing synths/routing/automation |
| F7, canvas click C6 | Visible new note | 810 notes; tick408 / length48 / velocity100 |
| Note Properties knob and Accept | Visible velocity change | velocity90 |
| Drag note | C#6 at intended earlier start | pitch73 / tick384 / length48 |
| Drag right edge | Longer visible note | length144; remaining raw notes unchanged |
| Right-click delete | Note removed | 809 notes |
| Ctrl+Z | Note returned | Raw note set equals pre-delete version |
| F6 / instrument button | Actual existing Sytrus Smooth window | Screenshot and live Sytrus identity |
| Visible plugin master slider drag | Changed slider | Read-only .8→.75; saved/reopened persistence |
| F9 / Lead fader drag | Actual fader changed | Read-only .65→.6361; other Mixer controls unchanged |
| Pattern move | Track1→Track3, start0 | Native clip track3 / length15360 |
| Pattern copy | Adjacent copy at tick15360 on Track4 | Three native clips; no overlap |
| Copy delete | Copy removed | Two clips; original notes/plugin/routing preserved |
| Pattern trim | Original length3072 | Actual offsets and native fields verified |
| GUI Open checkpoint | Restores full-length edited arrangement | Strict all musical state equality |
| GUI render / reopen / render | Actual WAV files | Identical decoded PCM; no unintended long silent tail |
| Calibrated chord draws | C6/E6/G6 at same onset | Exact tick24, lengths48, velocity100, original notes retained |
| GUI restore final checkpoint | Removes separate chord diagnostic from delivered final | Native equality to accepted GUI-edited state |

Final primary workflow WAV: 75.375986 seconds, 44.1kHz stereo FLOAT, 3,324,081 frames; peak −14.389922 dBFS, RMS −32.387661 dBFS, zero clipped samples. WAV SHA256 `8802d3c6c784ea024a8cec065d96c03d582fd2ef57b78c450d8ba697b9f42111`. Reopened PCM maximum difference 0. Actual output differs from the protected original baseline. Native automation and routing vectors remain equal to baseline.

## Failures discovered and corrected

- Initial grid click was not at intended bar onset. Saved readback exposed tick408; GUI move corrected it to tick384. A mouse receipt was never accepted as precise placement.
- A +1pixel draw convenience offset produced tick26 instead of requested24 at medium zoom. Removed offset; three corrected notes independently verified at exact tick24. Subpixel tick requests now refuse and require zoom/recalibration.
- FL-owned modal's top-level-parent wrapper followed the owner to the disabled main window. Native GA_ROOT identifies the actual modal; explicit Note Properties operation then passed.
- Repeated foreground forcing generated unnecessary Alt/focus changes and safe pixel refusals. Already foreground FL windows now avoid synthetic Alt. Regression covers this. Pixel mismatches still refuse and retain difference screenshot/bounds.
- Concurrent observation during a Save As saw a different project title; PROJECT_CHANGED correctly refused. Acceptance driver now sequences dependent GUI calls.
- Old dev2 overlapping shared-voice Pattern rendering had unexpected silence. UI12's real negative test returns PLAYLIST_OVERLAP_RISK before writing checkpoint/output. Cross-lane overlaps are guarded; disjoint-channel policy is unit-tested only.
- Real stale-view test returns VIEW_CHANGED, same-ID different intent returns OPERATION_ID_CONFLICT, same-ID same intent returns journal without resending.

## Evidence categories and outstanding work

**GUI input:** all listed musical mutations and save/open/render. **Background auxiliary reads:** plugin/Mixer state. **Native file verification:** notes/clips/plugin/Mixer/route/automation hashes. **Actual audio verification:** decoding, duration, silent spans, peak, PCM. **Subjective listening:** not performed for this WAV.

Calibration remains explicit; Codex must inspect current screenshots, grid and editor before using adapters. Unverified functionality remains in the capability matrix: universal third-party plugins/presets, audio/automation clip editing, arbitrary routing/sends/effect insertion, all layouts/DPI, and arbitrary export format controls. Existing Smooth was observed; GUI preset loading was not accepted. Tested mutations being GUI does not mean all possible FL operations are supported.

## Publication status

Authenticated account rechecked as Caelvoryn. Target Caelvoryn/FL-Studio-MCP returns GitHub API404 (absent or inaccessible to this connection); available connector has no repository-creation entry point and local gh was not found. No publication performed, no other repository touched. Source package excludes development history/private state and is a review artifact, not a complete 1.2 release.
