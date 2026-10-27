# Observe → act → verify → recover

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

