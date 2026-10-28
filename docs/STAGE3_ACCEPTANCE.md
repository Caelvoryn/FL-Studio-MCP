# Stage3: full16-bar arrangement acceptance — BLOCKED

Historical locked-desktop result. Unlock continuation and actual partial acceptance are recorded
in [2026-10-29 acceptance](STAGE3_20261029_ACCEPTANCE.md); current limitations differ below.

Date2026-10-28, branch`codex/pianoteq-direct`, baseline`3f66f24`.

**No complete16-bar electronic composition was produced or accepted. No new stage3
FLP/WAV is delivered.** The first GUI-assisted Save As was blocked by the Windows lock
screen. New note/picker prototypes have not been exercised in real FL and are hidden
behind a separate experimental flag. Offline tests are not substituted for host acceptance.

## Review and current actual evidence

- Previous [Pianoteq host](PIANOTEQ_HOST_ACCEPTANCE.md) and [foundation](FOUNDATION_ACCEPTANCE.md)
  reports were reviewed. They explicitly leave full note CRUD, Playlist placement, instrument
  routing, FX insertion and automation incomplete. This stage did not skip those prerequisites.
- Actual stdio MCP still reads the real FL26.1.5.5618 session and Pianoteq9 parameter page.
  Current session is the **previous foundation test**:112BPM,2 channels,4 Patterns, stopped.
  It is not a new128BPM/16-bar project and is not presented as one.
- Foreground process metadata reports`lockapp.exe`. No screenshot/authentication-control
  inspection was used. The first two Save As attempts failed`FOCUS_LOST`; investigation
  identified the lock screen rather than treating it as a music/DAW bug.
- A new explicit lock guard was then tested through actual stdio MCP: Save As returns
  `DESKTOP_LOCKED` before GUI input. No musical shortcut, file save or project switch occurred.
  Focus-activation attempts preceded diagnosis; no automated unlocking or bypass was attempted.
- Normal Windows unlock is required for the accepted keyboard/UIA fallback operations.
  The user was asked to unlock, with no manual composition/plugin adjustment requested.

## Changes

1. `HostFiles.focus/_keys` check known Windows lock-screen foreground processes before
   activation/input. Process metadata uses limited-query handles, closes them, and never
   touches authentication fields. Unlocked behavior delegates to the previously accepted
   focus logic. An unrecognized desktop still relies on existing strict focus checks;
   absence of a known lock process is not proof that input is safe.
2. Experimental`fl_vst_keyboard_load` wraps native F8 picker keyboard navigation and verifies
   exactly one added channel and an actual host plugin name/parameter page. Unexpected topology
   or plugin identity fails. It does not claim a direct instantiation API or establish VST2/3
   variant from names. **This wrapped tool has no new real acceptance yet.**
3. Experimental`fl_score_replace_basic` takes structured basic notes and expected old notes,
   saves fresh native before/after checkpoints and uses FL's real Piano Roll MIDI importer.
   It can represent chords and full-list replacements for basic create/update/delete operations;
   empty desired lists clear without importing an empty MIDI file. It is a **keyboard/UIA
   fallback, not direct Score scripting**. Existing advanced note styles are refused. Expected
   notes, target/channel/Pattern/transport, other raw note records, plugin state hashes, Mixer,
   Playlist, automation and tempo are checked. A failed postcheck means possible partial live
   edits and requires inspection/recovery. **Actual FL roundtrip remains unverified.**
4. Those prototypes require both`FLSTUDIO_MCP_ENABLE_DIRECT_VST_WRITES=1` and
   `FLSTUDIO_MCP_ENABLE_EXPERIMENTAL_SCORE_IO=1` in an isolated candidate process.
   Default/direct/legacy registries remain48/54/93. Explicit experimental direct/legacy modes
   expose56/95. No default configuration was changed. Unaccepted prototypes are not silently
   advertised as supported tools in ordinary compatibility mode.

No new dependency, controller replacement, FLP musical-data rewriting, image recognition,
mouse simulation, external synthesis, or manual arrangement occurred.

## Requested end-to-end criteria

| Criterion | Stage3 result |
|---|---|
| Start from blank through MCP | Blocked before initial preservation Save As; blank template not opened |
|128BPM | Not set; prior112BPM project intentionally retained |
| Pianoteq original harmony/melody | Prior host control exists; new structured-note importer not host-accepted |
| Synth lead/layers, full drums, Bass | Not created |
| Multiple Pattern/Playlist arrangement | Pattern primitives were previously accepted; no verified no-image Playlist clip placement |
| Instrument Mixer assignments, EQ/compression/space | Incomplete bridge; prior unused-bus route switch does not satisfy this criterion |
| Dynamic automation | No accepted creation/editing path; static parameter edits do not count |
| Save/reopen new composition | Not performed |
| New full-song WAV / mix checks | Not performed; prior technical WAVs are not substituted |
| Musical/listening judgment | Not performed |

The missing Playlist/FX/automation routes remain blockers **even after unlock**. Unlock
alone does not turn the existing system into complete arrangement automation. No unsafe
memory integration/private-engine invocation is proposed to evade those limits.

## Tests and evidence

Offline regression covers validation, MIDI serialization/chords, non-basic property refusal,
invariant preservation, experimental registration and lock-screen no-input guards.
**187 offline tests passed**,0 failed/skipped,5 dependency deprecation warnings. This count
does not mean the new GUI prototypes or full-song workflow passed FL acceptance. Actual
MCP rejection and read-only host state are recorded separately in
[structured evidence](evidence/stage3_20261028.json). Raw local journals and the stopped
prerequisite test driver are retained in`stage3_local`. The driver stops on any failed
response and does not replay non-idempotent operations.

Resume order: normal unlock → blank-project/native picker acceptance → basic notes/chord
create/modify/delete/readback → repair and test Playlist/routing/FX/automation gaps → only
then create and judge the requested16-bar arrangement and its actual WAV.
