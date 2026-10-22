# CINEMATICUM 0.11 frozen verification — passed run 02

**Result: exit 0; all 874 tests passed.** There were zero failures, errors,
skips, expected failures, or unexpected successes. Unittest execution took
807.404 seconds; the complete gate took 961.413 seconds. The parent collected
the original runner session 58519 with final exit 0.

## Exact source binding

- Commit: `530ba2400571a8b67efa2d9ab28997f65920c006`.
- Git tree: `4836005d8a9aed6790e596c23fa5e8b58d9d8ede`.
- Declared source: **330 files**, unchanged throughout the run.
- Runner inventory SHA256, identical before and after:
  `a4c94c9c4c0aafc2ab99cc74f35b7870daeae71ba353922bc75b413c01c68873`.
- Source-integrity manifest: 58,015 bytes; SHA256
  `141b53f435f68d325a73e2f0d930fc4acd7054b364b3336aada9f4439bd43d66`.
- Collection independently compared all 330 declared file blobs plus the
  manifest against this exact commit and the current worktree: **331/331
  matched**, without editing source or the index.

## Runtime evidence

The primary runtime was Python 3.12.14 with NumPy 2.3.5, OpenColorIO 2.6.0,
rawpy 0.27.1, OpenEXR 3.4.15, OpenTimelineIO 0.18.1, and
opencv-python-headless 4.11.0.86. The actual RAW fixture was present and
`allow_missing_raw` was false. Exact paths and RAW hashes are retained in the
adjacent JSON summary and original report.

All five managed runtime receipt/inventory identities matched before and after:

| Managed runtime | Inventory entries | Inventory SHA256 |
| --- | ---: | --- |
| optiland | 13460 | `d42c1fe559d287a646abdee491b31707d3a39c3e90b4dbdba26227db982fe821` |
| physical | 2561 | `e6cd9b75d102cbf9f0bff0b26f25746dc3b76054fc53a63dd7ef85ceb2e2e653` |
| learned | 16955 | `a2aa0c93a952a7b5863d774c4c3940910f18bce0d356ad43b18d600ab6330a6e` |
| reconstruction | 1967 | `07dc419caedff026f9aa09bc284158933a608f389d6629ee23e18c394cf07a88` |
| blender | 5652 | `0171b7e4db098bc851dcbe46a797f2dfd656607e6a92539cf72a254e591886fe` |

PBRT and Blender executable fingerprints are in the JSON summary. PBRT is an
optional binary identity, not a sixth managed before/after inventory.

## Preserved evidence

- Original report: 135,104 bytes; SHA256
  `d46c3a8de453269d18dcf0cb5981d2b3d83f3ceb5b4309fbf1ca5d5266a49d4c`.
- Original log: 288,584 bytes; SHA256
  `d8fbdd4a80e53021965c4afcfc659a504070ecf67bb1b7ebab716ff19f4d4efa`.
- Failed run 01 and both of its summaries remain unchanged.
- The original audio-clock/gap/preparation-cancellation test now passed inside
  this complete run. Its fixture alone gained `settings:{}` to satisfy the
  existing normalized-project invariant; its assertions were preserved.

This receipt covers the complete discoverable Python/Node/media suite. Native
executable and installed-application acceptance are collected separately by
the parent. No source, index, documentation, or runtime was modified during
this collection. Only these outside-source summaries were written, and the
owned read-only log-tail observer was stopped after completion.
