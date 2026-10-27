# 1.2 UI-first test results — 2026-10-27

- Independent new Python 3.12 environment installed from pinned requirements, editable candidate installed with --no-deps, pip check clean.
- Full offline regression: **73 passed**, five dependency deprecation warnings. Legacy writer compatibility enabled only for inherited tests; default policy has its own explicit test.
- Default UI-first guard tests: **13 passed**, two dependency deprecation warnings. These 13 are included in the 73, not additional independent coverage.
- Actual GUI acceptance uses real stdio MCP subprocesses and a running FL26.1.5. Unit fakes are not presented as FL evidence.
- Piano Roll draw/move/resize/delete/velocity/undo and calibrated three-note chord verified in actual UI-saved FLPs.
- Actual Sytrus master .8→.75 and Mixer Lead .65→.6361 by GUI, verified using separate read-only live state.
- Actual calibrated non-overlap Playlist move/copy/delete/trim, strict native postconditions and GUI checkpoint restoration.
- Actual overlap rejection, stale image rejection, operation-ID conflict and journal replay tests. Failed attempts retained, not counted as successful inputs.
- GUI save/reopen/re-render: strict native equality and decoded PCM exact, 3,324,081 frames at 44.1kHz stereo FLOAT, 75.375986 seconds. No subjective listening claim.
- Original configuration/controller/Piano Roll script/two accepted projects hash-checked unchanged. Prior dev2 source is retained.

See UI12_ACCEPTANCE.md for detailed scope and actual defects discovered. New GUI draw controls position/pitch; duration/dynamics inherit FL and require readback. Arbitrary GUI format selection, third-party adapters, routing/effect insertion and automation/audio-clip editing remain unaccepted.
# Dev2 current evidence

See [dev2 actual GUI acceptance and limitations](DEV2_ACCEPTANCE.md). Final full regression in a freshly installed environment:94 passed,5 dependency deprecation warnings. F821 static check and pip dependency check passed. Local actual-artifact audit:43/44 checks passed; the full Codex config hash differs from the earlier baseline only in node_repl.env; FL MCP sections/controller/accepted projects and all81 dev1 source files are retained. The hash discrepancy is preserved, not marked successful. Dependency vulnerability audit did not pass; see SECURITY_REVIEW.md. Offline doubles never replace FL execution. Other results above belong to earlier stages.

