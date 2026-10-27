# 1.2 UI-first architecture

Codex → stdio MCP → cooperating OS mutation lock/request log → observed Windows UI → real FL Studio.

- `ui_first.py`: actual Win32 identity/screenshots/UIA; expiring observations; exact selectors; calibrated Piano Roll targets; relative input; occlusion; durable single-use intent journal. No FLP setter, MIDI writer or bridge write.
- `desktop.py`: actual GUI save/open/render and bounded Playlist. Native inspector is read-only. Playlist native postconditions verify musical state beyond mouse receipts.
- `native.py`: read-only observed FL26.1.5 fields/hashes. Musical state is compared strictly; only timestamps and opaque regenerated clip identities are excluded.
- Existing bridge: read-only independent live state for this workflow. Legacy music writers retained but hidden by default; explicit compatibility opt-in remains labeled background operation.
- `workflow.py`: backups, persistent request log, OS byte lock, decoded audio and PCM comparison. Crash releases OS lock but does not validate uncertain input.

Private observations/logs/projects/audio/backups stay outside public source. Entry point does not modify installed MCP configuration. GUI observation/input need interactive desktop; Playlist transport and plugin/Mixer readback use existing bridge. Lock cannot prevent human edits or unrelated legacy servers. No universal UI understanding, subjective hearing or complete third-party plugin support is claimed.
# Dev2 delta

`vision.py` and isolated `ocr_worker.py` add native UI anchors, image-grid measurement and local Windows OCR. `ui_first.py` retains one-use intent journals, geometry/process/title/pixel/hit-test guards, then maps measured musical targets to real mouse input. Both drag endpoints are checked. `automation_move_value` fits saved control-point values against observed curve pixels; no FLP write occurs. Plugin complete snapshots use bounded paginated readback with actual single-parameter fallback and optional pre/post channel-name guard. See current [matrix](DEV2_ACCEPTANCE.md); historical architecture below is retained.

