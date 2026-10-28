# Stage3 continuation: coordinate-free prerequisites — partial acceptance

Date:2026-10-29. Branch:`codex/pianoteq-direct`, baseline:`4d1d267`.
Runtime: real FL Studio26.1.5.5618, Python3.12, FastMCP2.14.7, existing protocol2
`probe-v16` MIDI controller. Candidate launched as isolated stdio MCP; installed/default
MCP configuration and controller were not replaced. All music mutations below passed through
the candidate MCP. Engineering window/IME diagnostics are distinguished from music actions.

**The requested original16-bar complete electronic arrangement is NOT accepted.**
Actual technical FLPs and6 WAVs exist, but they do not contain the requested full song,
drum/bass arrangement, Playlist or automation. No external synthesis substitutes for FL.

## Verified capability matrix

| Capability | Actual input and execution | Independent result | Status/limit |
|---|---|---|---|
| Blank project/BPM | Factory Empty copied/opened;128BPM through existing host bridge | Native FLP and live BPM128 | Verified; default Sampler remains |
| Pianoteq loading | Native F8 picker/keyboard | Actual hosted Pianoteq9, parameter page; named UIA preset Steinway B Bright | Verified fallback; no direct instantiation API |
| Basic notes |12 original piano chord notes; modify/delete/add→14; clear→0; restore→14 | New before/after native FLPs verify pitch/tick/duration/velocity and other state | Verified basic import, not full Score API |
| Multi-instrument | New Synth Probe Pattern;4 Sylenth1 notes | Other Pattern's14 piano raw records unchanged | Verified separate Patterns; same-Pattern limit below |
| Sylenth1 loading | Native F8, Unicode search Sylenth1, Down/Enter once | Exactly one new channel, host plugin Sylenth1, named parameters | Verified fallback, not Serum/Nexus compatibility |
| Sylenth1 parameters | AmpEnv A Attack .015→.025; Release .07→.12 | Separate host reads after writes and after FLP reopen | Verified direct host control; preset identity unknown |
| Channel assignment | Select exact channel, Channel Rack Ctrl+L once | Piano→Mixer1, Sylenth1→Mixer2, persisted | Verified keyboard fallback; cannot request arbitrary destination |
| FX insertion | Selected Mixer2 caption Sylenth1; F8 Unicode search | Existing slots preserved; exact EQ2/Compressor/Reeverb2 slots0/1/2; no added channels | Verified fallback on selected track; arbitrary track selection unsupported |
| FX parameter | EQ2 band1 level .5→.45 | Host readback after write and reopen | Verified direct parameter, not completed mix design |
| Native persistence | Save35→open copy36→save38 | Exact Pattern data, plugin/Mixer hashes, Playlist and automation unchanged | Verified for technical probe |
| WAV | Native Ctrl+R dialog/Start;6 actual WAVs | Decode every sample; duration, silence, finite values, no sample clipping | Verified actual sound; settings inherited |
| PCM consistency | Compare3 pre/post-reopen WAV pairs | All numeric_difference, not exact_pcm | Bit-exact repeat criterion NOT passed |
| Playlist | Live bridge has no clip CRUD; saved FLP is readable | No new clips in this workflow | Incomplete; old calibrated GUI editor retained separately |
| Automation | Existing state readable from saved FLP | No new curve in this workflow | Incomplete; old GUI acceptance is not direct API acceptance |
| Listening | No user listening of these probes | No subjective evidence | Not performed |

VST host count4240 is not4240 useful named controls; it includes host/wrapper namespace.
Only observed named pages and specific tested parameters are established. Names alone do not
establish VST2/VST3 variant. Sytrus was also observed with597 parameters, but the earlier delayed
picker attempts were not counted as reliable Sytrus load acceptance.

## Defects found and repaired

1. **IME search interference.** A diagnostic screenshot showed physical English keys producing
   Chinese composition instead of Sylenth1. Unicode VK_PACKET text yielded the exact search;
   actual MCP Sylenth1 and3 FX loads then passed. Shortcuts still use virtual keys. No input
   language, default configuration or plugin binary was modified.
2. **Late loads.** Fruity Wrapper is an observed pending name, not success. Read timeouts during
   initialization retry reads only. Every mutating load is sent once. Wrong identity/topology
   stops and keeps evidence; after timeout inspect channels/slots before another load.
3. **Focus.** Do not tap Alt when the picker is already active. Native AttachThreadInput/SetFocus
   plus GetGUIThreadInfo verify editor focus. Avoid pywinauto Win32 set_focus, which internally
   moves the pointer. Earlier absolute zero-pointer claims are corrected here; old musical
   results are not invalidated, but that historical implementation did not prove no movement.
4. **Piano Roll targeting.** Close a stale roll through standard WM_CLOSE, select exact Rack
   channel and open F7. Actual separate-Pattern test verifies the target and all other records.
5. **Importer side effect.** In failed20b, all14 other piano notes retained their musical values
   but byte19 changed128→0. Strict raw-record postcheck failed, correctly. No success was faked
   or comparison relaxed. Failed state saved23; source20a reopened into22. A new preflight
   rejects import when another channel in the current Pattern has this imported-note marker.
   Real negative test33 returned IMPORT_NORMALIZES_OTHER_NOTES before musical input; MIDI08
   and after-FLP34 were not created. Save35 confirmed all notes unchanged. Separate Patterns
   passed the original exact-record contract. Arbitrary advanced-note editing remains refused.
6. **Reopen readiness.** Project title/enabled state can precede bridge/plugin readiness. Native
   reopen now waits for a real protocol ping before returning; subsequent host readbacks pass.

No unsafe injection, process-memory writes, musical FLP rewriting, controller replacement or
formal project edits.3 explicit FL-only picker screenshots assisted development; accepted new
music operations did not use image recognition, coordinates, mouse clicks or drags.

## Actual files and evidence

Local project directory: `D:\音乐\fl工程\MCP自动编曲前置验收\20261029_stage3`.
Final technical project: `38_Final_Resaved.flp` (14 Pianoteq notes Pattern1;4 Sylenth1 notes
Pattern2; no Playlist). Source/checkpoints and failed attempts retained, never overwritten.

Audio directory: `D:\音乐\fl完整歌曲\MCP自动编曲前置验收\20261029_stage3`:

- `基础音符技术测试\完整音频`:2 actual piano WAVs,9.375011s each; first peak−9.83dBFS.
- `独立Pattern技术测试\完整音频`:4 actual Sylenth WAVs,3.75s each; first dry peak−6.34dBFS,
  first FX peak−4.68dBFS. All6 nonempty, finite,0 sample clips. No true-peak/LUFS or subjective
  mix-quality claim. PCM variation cause is not established; do not assume random phase explains it.

Private real stdio request/response logs, diagnostics, scripts, JUnit and audio comparisons:
`upgrade_20261026/stage3_20261029_local`. Each receipt records tool inputs, output and time;
candidate mutation journal adds request IDs. Public [evidence JSON](evidence/stage3_20261029.json)
contains artifact hashes and actual structured results with abstract workstation roots. Audio,
commercial plugin content, images and full private journals are not published in source.

Formal Skyline and installed controller hashes match their prior references. Old accepted FLPs,
original MCP_Apply piano script and default MCP configuration were not written.

## Regression and reproducibility

194 offline tests passed,5 dependency warnings,14.66s. Offline doubles verify guards, never
substitute for the real cases above. Default/direct/legacy tool registries48/57/96. Accepted
bounded fallback tools are now under the existing direct-write opt-in; the prior experimental
score flag is no longer required. Do not enable legacy writers for actual acceptance.

Run in an isolated candidate process with `FLSTUDIO_MCP_ENABLE_DIRECT_VST_WRITES=1`, its own
state directory and verified existing MIDI endpoints. On this machine the actual RX/RX route
worked; names are workstation-specific and must be verified. No default config change is needed.

Reproduce: preserve session→open independent Empty copy→set/read BPM→load/read generator→new
Pattern per basic-note instrument→import/read new native checkpoints→assign/read Mixer→load
FX only with exact selected-track caption→write/read parameters→save/open copy/read→render
actual WAV→decode/compare→user listens separately. No blind retry of non-idempotent requests.

Remaining full-song blockers: coordinate-free Playlist placement/arrangement, direct automation
creation, additional verified drum/bass resource loading and rendered full-song structure/mix
acceptance. The preserved UI-first implementation is an explicit last-resort alternative,
not silently invoked or described as direct control. No main merge or Release in this phase.

References checked: Image-Line [shortcuts](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/basics_shortcuts.htm),
[browser/picker](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/browser.htm),
[Piano Roll import](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/pianoroll_menu.htm),
[separate Piano Roll scripting context](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/pianoroll_scripting_api.htm).
PyFLP's original [note layout](https://github.com/demberto/PyFLP/blob/master/pyflp/pattern.py)
documents the imported MIDI-channel marker; no GPL source was copied or dependency added.
