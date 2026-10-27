# Tested visual profiles

## Dev2 current adapters

Use `fl_ui_locate_piano` or omit `piano_grid` in `fl_ui_act` Piano actions to measure current native anchors, actual grid lines and Windows OCR labels. Three consistent time labels and recognized octave labels are required. Unknown views stop with diagnostics. Actual96DPI/1920×1080 only; movement, zoom, scrolling and maximize/restore were tested.

For Bar-onset draw, open `piano_snap_menu`, inspect actual popup, select Bar via exact visible text, reobserve the checked menu, then use `piano_snap_bar=true` with a recognized onset. This flag does not itself verify snap. Save and verify the actual tick. Without snap, subpixel targets refuse.

`fl_playlist_calibrate()` with no arguments measures ruler and Track labels. Explicit calibration below is retained compatibility, not a default to reuse blindly.

`sytrus_presets_menu` and `sytrus_master_menu` require actual native850×450 Sytrus profile; Main must be visibly selected for the latter. `text_click` uses exact OCR matches; `handle="active_popup"` targets exactly one observed popup containing the phrase. Ambiguous/missing text stops. Observed raw relative points remain a separately declared visual fallback.

`automation_move_value` with `automation_edit={"channel":8,"point_index":0,"value":0.5}` fits an existing non-flat light-purple curve from actual visible pixels and saved points. All points/lane must be visible; one source instance only. It sends a vertical drag, returns `verified=false`, and requires GUI save plus native point/other-state verification. Flat/unknown/occluded curves and exact point-time insertion are unsupported. Actual first point.403225809→.5 passed saved readback.

Generator parameter reads use current Channel Rack filter indices. Select All via actual UI; call `fl_plugin_state(track=0,slot=-1,complete=true,expected_channel="Classic")` with the actual target name.597 Sytrus values verified; single-read fallback handles missing page replies. Snapshot is not atomic. See [dev2 matrix](DEV2_ACCEPTANCE.md).

## Historical dev1 explicit calibration

Window-relative and screenshot-confirmed; not fixed desktop coordinates or universal DPI/theme profiles. Inspect fresh observation before use.

## Piano Roll

Observed 950×760 FL26.1.5 editor, 100% DPI. F7 opens; Shift+2 uses documented medium horizontal zoom. UIA exposes panes, not notes. Measured calibration:

```json
{"tick_zero_x":78,"tick_zero":0,"pixels_per_tick":0.5,"pitch_zero_y":449,"pitch_zero":72,"pixels_per_semitone":18,"grid_top":86,"grid_bottom":614,"grid_right":923}
```

`fl_ui_act` actions `piano_draw/move/resize/delete` accept `piano_grid`, `piano_note={tick,pitch,length_ticks}`, and move/resize `piano_target`. Draw accepts only tick/pitch: FL supplies current length/velocity. Read back then resize/adjust properties; do not assume defaults. Resize retains start/pitch; move retains length. Targets outside the calibrated grid refuse. Confirm current snap/tool/channel in the UI, then verify saved notes.

Velocity uses observed Note Properties knob and Accept, not UIA ValuePattern.

## Playlist

Explicit calibration after identifying bar1/track1: grid_left=272, first_track_top=83, pixels_per_bar=18.75, track_height=208, uniform tracks, 4/4. Native child windows anchor canvas; ruler/lane fingerprints guard zoom/scroll. Copy at tick15360 is adjacent to a 40-bar source, not overlapping.

## Plugin / Mixer / render

Channel Rack Smooth opens actual Sytrus. Master slider and Mixer Lead fader use screenshot-identified relative targets with read-only independent state. No arbitrary plugin adapter.

Render adapter recognizes 433×611 TWAVRenderForm, uses UIA filename/type and selects Cut remainder. Actual 44.1kHz stereo FLOAT is verified; generalized rate/depth selection is not accepted.

Official references: [Piano Roll](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/pianoroll.htm), [shortcuts](https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/basics_shortcuts.htm). Documentation guides exploration; only real tests establish support.
