# Observe → act → verify → recover

Latest: [coordinate-free prerequisite workflow](STAGE3_20261029_ACCEPTANCE.md).
Use one basic-note instrument per Pattern, exact expected notes/parameters and fresh checkpoint
paths. Same-Pattern imported-note risks refuse before musical input. Native picker search uses
Unicode text to bypass IME, while shortcuts use virtual keys. No blind load retry on timeout;
read actual channels/slots first. Save/reopen waits for bridge readiness. Parameter persistence,
native state and PCM are separate checks; repeated PCM was not exact in the current probes.
Direct opt-in has57 tools, legacy96, unchanged default48. No default configuration is rewritten.

Historical correction: earlier absolute zero-pointer claims were too strong because pywinauto
Win32 `set_focus` can move the cursor. The current HostFiles layer uses native focus verification
and avoids that method. Three explicit picker diagnostic images were used on2026-10-29;
accepted new operations themselves do not capture images or use canvas coordinates.

Latest structured host workflow and actual foundation results: [FOUNDATION_ACCEPTANCE.md](FOUNDATION_ACCEPTANCE.md).
Saved Playlist data is never labeled live state; Pattern clone indices can shift.

For the opt-in `codex/pianoteq-direct` branch, use the [verified Pianoteq host workflow](PIANOTEQ_HOST_ACCEPTANCE.md):
direct structured host reads/writes first, named accessibility controls and keyboard/UIA file operations
only as explicit fallbacks. That tested workflow takes no screenshots and sends no mouse operations.

1. Inspect actual FL title/windows/modals. GUI Save As to a NEW test path establishes ownership and preserves current work.
2. `fl_ui_observe`: inspect image/UIA tree; identify actual editor, zoom, scroll, grid, tool and target. Tokens expire in 180 seconds. Images alone are not semantic recognition.
3. Prefer exact observed UIA selectors. Self-drawn targets use visually confirmed normalized window coordinates or explicit Piano Roll tick/pitch calibration. Never reuse old geometry blindly.
4. `fl_ui_act` with NEW alphanumeric operation ID. Ownership/process/title/geometry/pixel checks run before input, with occlusion checks. Explicitly observed FL-owned modals may be operated; blocked background panes may not.
5. `input_sent, verified=false` means input only. Inspect post-image; GUI Save As to another NEW FLP and independently verify intended note/clip delta. Read-only actual parameters verify plugin/Mixer edits.
6. After uncertain input, inspect journal/screenshots/checkpoints. Same ID/input returns the prior journal without sending again. Different input with same ID refuses. A crash leaving `input_pending` means uncertain, not success.
7. Known deletion can use verified Ctrl+Z. Otherwise GUI Open preserves the failed state first and reopens a verified checkpoint. No unknown error dialogs are dismissed automatically.
8. Playlist requires current calibration; pre/post FLPs verify musical state. Shared-instrument overlap refuses; source/end/target must be visible. Viewport changes require recalibration.
9. Export actual NEW WAV through GUI; decode/check duration, unexpected silence spans and clipping. Save/reopen/re-export and compare native state/PCM.
10. Present actual WAV for user listening. Translate timestamped feedback into note/rhythm/plugin/Mixer target; preserve prior version and repeat. Metrics do not establish subjective quality.

GUI primitive permits bounded FL shortcuts, not arbitrary typed commands. Recognized file dialogs use dedicated Save/Open/Render adapters. Complete automatic modal recovery is not claimed.
# Dev2 current workflow note

Current scope and actual acceptance: [DEV2_ACCEPTANCE.md](DEV2_ACCEPTANCE.md). Preserve an independent FLP first; observe current HWND/editor and popup state, measure grid automatically, perform one GUI input, reobserve, save a new checkpoint, read actual notes/curve/route/plugin state, then export actual WAV. GUI input receipts are not musical success. Stop on failed recognition. A popup, resize or changed pixels requires reobservation; do not replay uncertain non-idempotent inputs. Compare saved/reopened states and decoded PCM. Request user listening feedback separately. Historical workflows below may describe legacy/background tools; those are hidden by default and are not GUI acceptance.

