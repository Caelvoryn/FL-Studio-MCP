# Pianoteq Direct-Control candidate — 2026-10-28

**Experimental, partial support. FL-hosted Pianoteq acceptance is NOT complete.**
Independent branch: `codex/pianoteq-direct`, based on `39288e8`.
No default MCP configuration, installed controller, plugin binary, or formal FLP was changed.
No screenshots, image recognition, mouse simulation, memory modification or injection were used.

## Implementation

`tools/vst.py` adds reusable FL-host operations using the existing MIDI/SysEx bridge:

| Tool | Behavior |
|---|---|
| `fl_vst_find_generators` | Bounded live generator discovery, including renamed channels; current Channel Rack filter only, maximum32 per request |
| `fl_vst_parameter_page` | Bounded sparse parameter page with exact channel/plugin name checks before/after |
| `fl_vst_preset_info` | Raw existing host preset information; internal preset identity remains unknown |
| `fl_vst_batch_parameters` | Preflight maximum32 edits, stale-value guard, independent read after every write, partial/uncertain results on failure |

Writes require candidate-process environment `FLSTUDIO_MCP_ENABLE_DIRECT_VST_WRITES=1`.
This does not enable other legacy background writers. Default47 tools, direct-mode48,
legacy compatibility87. Existing installed/default server is untouched.
Each edit requires `param`, exact full `name`, `expected_value`, `value`, `tolerance`.
Use an independently observed host parameter index; no guessed semantic mappings.
The controller rounds values to four decimals, so tolerance must be explicitly .0001.. .01.
Transport must be stopped. A batch is sequential and non-atomic. Failed writes are not
automatically replayed or rolled back onto a possibly changed target. MCP mutations use
the existing transaction lock and durable request journal. The deadline is checked
between calls; an in-flight call also depends on the bridge transport timeout.

Generator indices respect the current Channel Rack filter, not guaranteed global indices.
Name guards cannot distinguish identical duplicate instances or guarantee that a user
has not switched to another project with identical names. Use one responding FL instance,
a stable independently saved test project, and do not concurrently edit it during a batch.
Complete plugin-state capture, plugin instantiation, arbitrary preset selection and FLP
save/reopen are not implemented by these four tools.

`pianoteq.py` provides a separate, explicitly named `PianoteqStandalone` adapter for the
official loopback JSON-RPC server. It checks vendor/type, lists actual presets and
parameters, selects exact name/bank, verifies actual preset/model, and edits parameters
by stable vendor ID with stale/readback checks. It is **not registered as an FL MCP tool**,
does not control a hosted VST instance, and never infers FL indices from RPC indices.
Use only with an explicitly started isolated standalone process, not the user's existing
session. It does not launch processes, modify preferences, activate software or delete presets.

## Actual results

Windows / FL26.1.5.5618; installed Pianoteq9.1.2/20260210, Modartt VST3 x64.

| Capability | Actual status and evidence |
|---|---|
| Installation / FL plugin database discovery | Verified binary and actual `.nfo` registration, vendor Modartt,64bit,VST3 |
| New candidate → real stdio MCP → current FL | Verified; scanned14 generator targets; no Pianoteq instance in current filter |
| Generic host parameter read | Verified using actual FL Keys channel8: total15, first page7 real values/display strings |
| Wrong target guard | Verified actual FL Keys refused when expected plugin was Pianoteq9 (`TARGET_CHANGED`) |
| Pianoteq loaded in independent FL project | **Not verified**; currently open project remained formal Skyline; no plugin-loading command in installed bridge |
| Pianoteq host parameter discovery/write | **Pending a loaded test instance**; not inferred from independent standalone success |
| Official standalone catalog | Verified1,883 presets,213 parameters; Steinway B entries reported available (`license_status=ok`) |
| Same-model preset switch | Verified in isolated standalone: Steinway B Warm → Steinway B Bright, exact name/bank/instrument readback |
| Different-model switch | Verified in isolated standalone: NY Steinway D Classical, exact name/model readback |
| Standalone parameter edits | Velocity Offset .53, Hammer Hardness .46, Sympathetic Resonance .55, Reverb Mix .35 independently read back |
| FL preset/model name read | **Unknown**. Existing controller's `getName(...,flag,0)` reads index0, not necessarily CURRENT preset |
| VST3 Program Change | **Not verified**. Not interchangeable with Pianoteq internal browser or arbitrary parameters |
| Saved/reopened Pianoteq FLP persistence | **Not verified**; no Pianoteq test FLP was created or claimed |
| Actual standalone WAV | Verified two9.200907s,44.1kHz stereo24bit renders of same original MIDI; non-silent, no sample clipping, PCM differs |
| Actual FL-hosted Pianoteq WAV | **Not verified** |
| Subjective listening | **Not performed**; numeric/audio-file checks are not listening |

Warm peak .28676486, RMS .03153178; Bright peak .27200699, RMS .03444518.
These exports used Pianoteq's official CLI, not FL Studio's export engine.
Initial CLI attempt with `--no-audio-prefs` failed (exit1, no WAV); removing that
inapplicable export option succeeded. Both failure and retry logs were retained locally.

## Why preset systems must remain separate

FL's public MIDI API exposes normalized parameters and host preset navigation/metadata,
not the full VST3 component/controller interfaces. Existing `plugin_preset` uses flags3/6
with preset index0; returned names cannot establish the selected internal piano preset.
The official FL API documents omission of paramIndex / `GPN_GetCurrentPreset` for CURRENT
preset reads. The installed controller was preserved; no untested replacement was installed.

VST3 program lists use `IUnitInfo` and a program-selection parameter flagged
`kIsProgramChange`. That does not mean every preset in a vendor's own browser is exported
as a host program. Current bridge responses do not expose those VST3 flags/interfaces.
Do not send guessed Program Change messages or treat ordinary parameter changes as
model switches.

The official standalone JSON-RPC API can select real presets and read their model names.
No evidence currently establishes a corresponding server attached to FL's VST3 instance.
Reliable alternatives to investigate are vendor-exported `.vstpreset` files recalled by
the actual FL wrapper, or explicitly configured MIDI preset mappings with real name/state
readback. Neither is claimed as integrated here. No dangerous injection is proposed.

Primary sources:

- [FL MIDI API](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm)
- [Steinberg preset/program-list specification](https://steinbergmedia.github.io/vst3_dev_portal/pages/Technical%2BDocumentation/Presets%2BProgram%2BLists/Index.html)
- Installed Pianoteq `--help` and its9.1.2 local `/jsonrpc` API reference (saved with local evidence)
- [Modartt administrator's server/reference instructions](https://forum.modartt.com/viewtopic.php?id=9043)

## Tests / next acceptance gate

122 offline regression/contract tests passed, including28 new tests. These are not real
plugin compatibility claims. The two inherited legacy-mode tests were made explicit
about requiring legacy mode; the exact registry expectation changed83→87 to account for
the four new tools. Separate tests require exact47/48/87 registries and verify that direct
opt-in does not expose unrelated legacy writers. No existing behavior checks were removed.
Five dependency deprecation warnings remain; no new dependency was introduced or upgraded.

Run from candidate root in a compatible existing environment:

```powershell
$env:PYTHONPATH=(Resolve-Path src).Path
python -m pytest tests -q
```

For an isolated candidate MCP process only (do not edit default configuration):

```powershell
$env:FLSTUDIO_MCP_TRANSPORT='direct'
$env:FLSTUDIO_MCP_PORT_TO_FL='FLStudioMCP RX'
$env:FLSTUDIO_MCP_PORT_FROM_FL='FLStudioMCP RX'
$env:FLSTUDIO_MCP_ENABLE_DIRECT_VST_WRITES='1'
python scripts/run_server.py
```

The RX/RX route is the observed local return path, not a universal installation default.
Do not run a competing MIDI client while testing it.

Next gate: obtain a safely saved independent FLP containing Pianoteq. Discover the real
instance/host parameters; read actual preset metadata without assuming it equals the
standalone catalog. Batch-edit only observed accessible parameters. Save AS a new FLP,
reopen and compare the same parameter values; import/play the original MIDI and export
through FL. Only then can hosted Pianoteq/persistence/audio acceptance be marked passed.
At present “change the FL piano to another internal Pianoteq preset” is not yet automated.
