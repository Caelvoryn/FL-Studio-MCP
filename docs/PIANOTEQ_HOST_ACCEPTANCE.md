# Pianoteq9 — FL-host acceptance, 2026-10-28

Later checkpoint: [direct-control foundation acceptance](FOUNDATION_ACCEPTANCE.md),164 tests.
The141-test registry/counts below describe this earlier Pianoteq checkpoint.

This supersedes the initial “host instance missing” status in the historical
[first candidate report](../PIANOTEQ_SUPPORT.md). Independent development branch
`codex/pianoteq-direct`, based on `92372d1`. No main merge or Release.

**The real FL-hosted parameter/preset/MIDI/save/reopen/WAV workflow passed in the
tested independent project. Exact PCM repeatability did not pass.** Preset and
file operations use explicit accessibility/keyboard fallbacks; parameter control
uses the existing host MIDI bridge. No screenshots or mouse operations occurred.

## Verified matrix

| Capability | Mechanism / actual result | Limit |
|---|---|---|
| Discover installed plugin | Actual FL plugin database: Modartt, VST3 x64 | Installation is not runtime compatibility |
| Initial instance creation | F8 picker, typed Pianoteq, Enter; host subsequently found channel1 | Keyboard GUI setup, **not** public host instantiation API |
| Loaded instance discovery | Real candidate stdio MCP → existing MIDI controller; Pianoteq9,4240 host slots | Current Channel Rack filter only; unused Sampler reports no plugin |
| Parameter discovery/read | Live host pages and single reads, actual names/display strings | Sparse/virtual wrapper slots; not4240 independent synth knobs |
| Batch parameter control | Actual changes0.50→0.53 Velocity Offset,0.50→0.46 Hammer Hardness,0.50→0.55 Sympathetic Resonance,0.54→0.35 Reverb Mix | Four separate real reads after writes; sequential/non-atomic |
| Current preset name | Hosted JUCE UIA Name property `Current preset: ...` | Accessibility fallback, requires visible matching plugin window |
| Preset selection | UIA InvokePattern / ExpandCollapsePattern by exact model/preset menu names; B Warm→B Bright and NY D Classical→B Warm verified through MCP | **Not** FL internal preset API or VST3 Program Change; model menu path known, separate internal model field not exposed |
| Host preset list | Host reports128 programs, generic `Program 0` | Does not establish a mapping to vendor's1883 standalone catalog entries; arbitrary program switching unverified |
| MIDI | Original12-note file imported by Piano Roll Ctrl+M and UIA native file dialog; native FLP confirms channel1, pitch/time/duration/velocity | Keyboard import fallback; no controller or Piano Roll script replacement |
| Save/reopen | Real stdio MCP no-image file tool, exclusive Save As / preservation / open fresh copy / resave | Native UIA dialogs and keyboard, **not** internal save/load API |
| Persistence | Four parameters read correctly after reopen; actual accessibility name remains Steinway B Warm (modified); actual resaved FLP retains12 notes, tempo, Playlist and identical plugin-state hashes | Does not claim arbitrary proprietary plugin-state parsing |
| WAV export | Real FL Ctrl+R, UIA filename entry and verified render-form Enter Start, then decode actual WAV | Existing render settings inherited, not configured; confirmed PCM16,44.1kHz,stereo |
| Audio checks | Six actual FL exports; each226800 frames /5.142857s, non-silent, finite, no sample clipping | No subjective listening, LUFS or true-peak claim |
| Repeated PCM | Same-session repeated export differs by max0.000518798828125; reopened export differs by max0.00042724609375 | **Not bit-identical**; same-session control also differs. Root cause not isolated (no assumption it is only dither or modeling randomness) |
| Other plugins | Generic discovery/page/batch tools available for loaded generators/FX | No new Serum/Nexus UIA profile or new compatibility claim |

Piano Roll import preserves notes, not file tempo: the test FL project remains140BPM.
The phrase ends at864ticks with PPQ96; FL exports3 bars /12beats. Do not describe these
WAVs as the earlier9.20s/90BPM standalone renders. All audio in this report is from FL.

## Failures retained and fixes

1. An overly strict foreground check expected the main HWND; FL editor panes can themselves
   be foreground windows. The new file adapter activates the main host, focuses the identified
   Playlist, then verifies foreground **process identity** before sending keys. The blocked
   attempt reported `FOCUS_LOST`, sent no keys, and did not save a phantom file. Retry succeeded.
2. A JUCE submenu opened incorrectly while FL was inactive. `GUI_TIMEOUT` / `ACCESSIBILITY_LAYOUT`
   stopped the operation; the preset remained unchanged. The identified menu was dismissed
   with Escape, current preset re-read, and the adapter corrected to activate/verify FL first
   and expand named intermediate menus with ExpandCollapsePattern. The corrected real MCP
   attempt selected Steinway B Warm from NY Steinway D Classical and verified its actual name.
   Failure responses now retain the accessible menu item names and prohibit blind replay.
3. Parameter display strings can lag an immediate normalized read. The saved/reopened live
   reads resolve Velocity Offset to`+0.06`, Hammer Hardness`-0.08`, resonance`1.25`, reverb`-15.0dB`.
   Immediate stale display text was retained in evidence; no preset success was inferred from it.
4. Audio comparison found real PCM differences. Repeated same-session exports also differ.
   No test threshold was relaxed and no output bytes were rewritten to fabricate equality.

## Reusable candidate tools

The original four generic VST tools remain. Two explicit opt-in fallbacks were added:

- `fl_host_project_file(action, destination, expected_title, ...)`: `save_as`, `reopen_copy`,
  `export_wav`. Fresh paths required; reopen preserves current session before switching.
  Export/reopen require the saved session owned by this adapter. Verify live parameters
  separately after reopen. Render settings are inherited and actual output is reported.
- `fl_vst_accessible_preset(action, track, expected_plugin, expected_channel, expected_title, ...)`:
  `read` or `select`; selection requires exact current preset and exact menu path. Only the
  observed Pianoteq9 accessibility profile is enabled. Unknown/ambiguous controls stop safely.

No new dependency, installed controller, default MCP config or stable source was replaced.
For an isolated candidate server, set `FLSTUDIO_MCP_ENABLE_DIRECT_VST_WRITES=1` and launch
`scripts/run_server.py` with the correct existing MIDI ports. This exposes50 tools; default
remains47, legacy compatibility89. It does not expose unrelated legacy writers.

Example after opening a fresh copy of the tested Warm template with the file tool:

```json
{
  "action": "select",
  "track": 1,
  "expected_plugin": "Pianoteq 9",
  "expected_channel": "Pianoteq 9",
  "expected_title": "Your_Test_Copy.flp - FL Studio 2026",
  "expected_current": "Steinway B Warm",
  "menu_path": ["Grand Steinway B", "Steinway B Bright"]
}
```

Use with `fl_vst_accessible_preset`. Read current state first; do not reuse a title/index
blindly. Selecting presets resets/reconfigures plugin state, so reobserve host parameters
before constructing a subsequent batch. Do not infer host indices from standalone IDs.

## Template / reproducibility

Local editable outputs are under the designated `Pianoteq MCP验收/20261028_host_direct` project
directory. `07_Steinway_B_Bright.flp` and `11_Warm_Reopened_Resaved.flp` are real FL-saved templates
with the12 editable test notes and actual hosted Pianoteq state. Future runs can use
`reopen_copy` on either, preserving the current session and never changing the template itself.
This is the verified alternative to unsupported direct VST instantiation.

Raw input/output/request journals, failure logs, JUnit and full local paths are retained in
`pianoteq_direct_local/host_round2`. The actual driver`finish_acceptance.py` checks every MCP
response before continuing. Public [structured evidence](evidence/pianoteq_host_20261028.json)
contains real responses, audio metrics and artifact hashes without distributing proprietary
plugin/preset binaries, FLPs or audio. **141 regression tests passed**,0 failed/skipped,
5 dependency deprecation warnings. Real GUI/host checks are separate from those offline tests.

Protected formal Skyline file SHA256 remained unchanged, as did the installed controller
(`d4ce0b0c383002b943e0884a4fb149686962ae41f2f7157d9102d6ae6dc246dc`). The independent FL project
is left open. No original preset was modified or deleted; the user's standalone Pianoteq
process was not used as a substitute for these FL-host checks.

Official references:

- [FL MIDI API and plugin parameter/preset interfaces](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm)
- [FL wrapper and preset controls](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/plugins/wrapper.htm)
- [Piano Roll MIDI import](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/pianoroll_menu.htm)
- [Steinberg VST3 program lists](https://steinbergmedia.github.io/vst3_dev_portal/pages/Technical%2BDocumentation/Presets%2BProgram%2BLists/Index.html)
