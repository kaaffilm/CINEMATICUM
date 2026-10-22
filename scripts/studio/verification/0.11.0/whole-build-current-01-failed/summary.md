# CINEMATICUM 0.11 frozen verification — failed run 01

**Result: exit 1; 874 tests ran, 873 passed, one failed.** There were no errors,
skips, expected failures, or unexpected successes. Unittest execution took
772.515 seconds; the complete gate took 919.042 seconds.

The only failure was
`test_audio_routing.AudioRoutingTests.test_shipped_transport_uses_audio_clock_gaps_and_cancels_pending_preparation`.
The extracted JavaScript VM fixture supplies `state.project` with only `id` and
`fps`. The new Float32 branch in `play()` reads `project.settings.image_precision`
and therefore raises `TypeError` before the existing audio assertions execute.

## Diagnosis and smallest fix

This is a stale VM fixture. In the shipped application, `normalizeProject()`
initializes `p.settings ??= {}`. Project adoption, save results, recovery, and
authoring/candidate application normalize their incoming projects. Undo
restores snapshots of normalized state. The isolated fixture bypasses that
invariant.

Add `settings:{}` to the existing fixture. Keep every existing source-clock,
silent-gap, delayed-master, preparation-cancellation, and audio-failure
assertion. No production-code change is required by this failure. Regenerate
the manifest and complete the full gate against the corrected freeze.

## Preserved identities

- Frozen source: **330 files**, unchanged before/after; inventory SHA256
  `89c85eb6a56d4ffbbde7eaabdb48a1906e14e2e0e00f5793657a800496304ef9`.
- Parent-reported staged tree: `7379e62171a5f70e0bceba53918fdf5baae19217`.
- All five managed runtime identities remained unchanged: Optiland, physical
  rendering, learned tracking, reconstruction, and Blender. Exact receipt and
  inventory hashes are in the adjacent JSON summary and original report.
- Original report: 135,226 bytes; SHA256
  `fe3123609f213384860b6afa803e9a91d1282d098cb676cc3a6a31f7d3fa5d47`.
- Original log: 289,895 bytes; SHA256
  `d2c5ff88733b801f8abb6b064fca2141829d859b2d73216231668fd81fd9c5a9`.

The primary runtime was Python 3.12.14 with NumPy 2.3.5, OpenColorIO 2.6.0,
rawpy 0.27.1, OpenEXR 3.4.15, OpenTimelineIO 0.18.1, and OpenCV 4.11.0.86.
The actual RAW fixture was present and no missing-RAW exception was enabled.

This collection changed no frozen source, index, documentation, or runtime.
The original log and report are retained; only this outside-source summary was
written. The observer's read-only log-tail process was stopped after completion.
