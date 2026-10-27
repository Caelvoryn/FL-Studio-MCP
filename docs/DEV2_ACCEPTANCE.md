# 1.2.0.dev2 — bounded UI-first candidate

Current-version matrix; archived dev1 documents remain historical. Tested Windows/Python3.12/FL26.1.5 build5618,1920×1080,96DPI. Not universal coordinate-free automation. Musical changes below were real GUI input through stdio MCP; native and bridge access were read-only verification.

| Module | Status | Evidence / limits |
|---|---|---|
| Window/editor/plugin identity | GUI verified, bounded | HWND/class/parent/focus, UIA where present, screenshots/DPI; changed/modal/occluded targets stop |
| Piano automatic location | GUI verified, bounded | Native anchors, actual grid pixels and OCR octave/three ruler labels; actual draw/move survived window movement, zoom, scrolling and maximize/restore without manually supplying a new grid |
| Note precision | Partial | Exact saved ticks verified. Subpixel unsnapped draw refuses; GUI Bar snap plus recognized onset passed. Arbitrary microtiming/high zoom without sufficient anchors unsupported |
| Length/velocity/chords/delete/undo | Inherited GUI verified | dev1 evidence retained; automatic position locator is not universal note segmentation |
| Playlist Pattern CRUD | GUI verified, bounded | Automatic timeline/Track-label calibration and nonoverlapping actual move; inherited copy/trim/delete. Uniform visible tracks, bar1 origin,4/4 only |
| Automation creation | GUI verified, bounded | Sytrus Main-volume menu → Create automation clip; actual channel/points/clip parsed. Created at actual GUI range offset then GUI moved tozero |
| Automation curve | GUI verified, partial | Real initial-point drag/new-point creation. Reusable automation_move_value fitted saved non-flat points to observed purple curve and set start exactly.5. Flat/occluded/unknown-color/offscreen curves refuse; exact time-placement adapter not implemented |
| Automation arrangement | GUI verified, partial | Single-clip MOVE passed strict readback. Shared-source overlap refuses; trim/copy/delete and generic track management unimplemented |
| Preset discovery | Auxiliary verified | Actual924 Sytrus files indexed; actual Classic factory file exists |
| Preset loading | One stock GUI path verified | Sytrus presets→Plucked→Classic; visible name/description, native state and rendered audio changed. Opaque factory FST hash differs from saved state: no binary-equivalence claim |
| Plugin menus | Sytrus GUI profile verified | Native TSynthEditorForm850×450 and observed Main-tab color; preset and volume menus tested. Unknown profiles refuse |
| Plugin snapshot | Auxiliary verified |597 actual Sytrus values; page75 timeout→individual real replies. After curve edit only parameter0 changed .8→.5,596 unchanged; non-atomic snapshot |
| Channel identity | GUI recovery/auxiliary verified | Installed controller indices follow Channel Rack group. Automation filter exposed wrong target; actual UI All selection recovered. expected_channel checks name before/after reading. Tiny All-menu OCR failed and needed screenshot-relative click |
| Mixer | Inherited GUI volume verified | Lead fader readback retained; arbitrary routing/sends/FX insertion/removal unimplemented |
| Save/reopen/export | GUI verified | Actual dialogs, native equality and real WAV decode/PCM comparison. Tested export44.1k stereoFLOAT/Cut remainder; arbitrary formats unsupported |
| Third-party adapters | Not implemented | Plugin discovery is not actual Surge/TAL/Dexed GUI support |
| DPI/resolution | Not tested beyond baseline | Window movement/resize/scroll/zoom tested; other DPI/monitor resolutions unverified |
| Subjective hearing | Not performed | Real WAV exists; numerical checks do not constitute listening |

## Actual results and corrected failures

dev1 baseline810 notes; GUI additions F6 tick960 length48 velocity100 and C5 tick1536 length48 velocity100 yielded812 editable notes. Old notes retained.

A scrolled unsnapped draw actually landed at1535 instead of1536. Failed checkpoint retained; subpixel guard plus GUI Bar snap corrected native1536. Wrong caption drag opened a menu; screenshot exposed it and popup guard now refuses background input. Wheel/Shift1 no-ops are not zoom successes. Actual resize-stale token returned WINDOW_CHANGED; expired token OBSERVATION_EXPIRED; different intent with reused ID OPERATION_ID_CONFLICT. No input replayed. Musical canvas input retains full-pixel guard; navigation tolerates unrelated tooltip pixels but retains identity/geometry/modal guards.

Windows OCR is local, isolated stdin/base-Python worker with20s timeout and retained trace. Crops repeat only actual sparse label pixels, never synthesized labels; failed PowerShell probe did not bypass execution policy.

GUI curve: start.8→.403225809; new point32.209186554beats/.801075280, endpoint156.802082062/.8. This is not exact beat32. Reusable measured adapter then changed start to exactly.5. Notes/routes/clip layout unchanged; only target curve and expected Sytrus current master state changed.

First curve WAV and reopened WAV:75.3759863946s,3,324,081frames,44100stereoFLOAT,zero clipped samples, identical decoded PCM; SHA256774400c54c2af809896a6ef0e517488b3aecae95fc5487372edcbd59b9dedc79. Before/after:0–15s RMS.018863684→.016969495;30–75s PCM identical. Final measured-adapter artifacts/results are in the local delivery report.

Offline tests are not real FL evidence. Local evidence retains real MCP inputs/results, screenshots, failures and independent FLP/WAV checks. Public source excludes private logs/projects/audio/commercial presets.

Full P0/P1 remains incomplete: universal layouts/DPI, third-party presets/plugins, precise automation-time editing, automation CRUD and generic routing/FX are gaps. Publish only as a limited development candidate. Account/repository visibility is not integration write permission; actual remote commit/readback is required for a publication claim.

Final measured-adapter pair:75.3759863946s,peak−13.904624962dBFS,RMS−31.870081639dBFS,zero clipping;100ms-block quiet test below−70dBFS found longest.2s. Both WAVs SHA256bb9e089d59ed7531367e0b30b429b4ab56334e58a8b425e1af2b44eb6c3b785a, decoded PCM identical after actual GUI reopen. New environment installed from exact lock, pip check passed, and real stdio automatic Playlist calibration passed using that environment.

Publication recheck: authenticated Caelvoryn, target repository exists/public/empty, account reports admin/push but integration create_file returned403 Resource not accessible by integration. No upload or Release succeeded. Known dependency advisories remain separately documented in SECURITY_REVIEW.md.
