# CINEMATICUM Studio 0.12 verification

Recorded 22 October 2026. This isolated integration starts from the exact
0.11 core `530ba2400571a8b67efa2d9ab28997f65920c006`. It applies the reviewed
retime patch while preserving the later 0.11 still-photography runtimes and
the normalized `settings: {}` transport-test fixture. Source and runtime
identities distinguish each gate; previous release results do not certify this
candidate.

## Completed pre-integration acceptance

The original retime candidate's source manifest and receipts are retained under
`verification/0.12.0/isolated-retime-01/`. These results belong to that exact
isolated source, before the final 0.11 integration and 0.12 version changes.

| Gate | Actual result |
|---|---|
| New clock and actual-media tests | 19/19, zero failures/errors/skips, 16.195 s |
| Existing editing/live-PCM affected checks | 19/19, zero failures/errors/skips, 1.990 s |
| Existing constant-retime/reverse/nested/multicam/trim media checks | 10/10, zero failures/errors/skips, 18.317 s |
| Actual Chromium workflow | 58/58: prepare 0.760 s, author 2.291 s, playback 9.611 s, archive 5.437 s |

The numerical checks decode actual source and delivered media. Six measured
flow midpoints matched independently translated interior pixels exactly.
Fractional-rate split PCM was sample-for-sample identical to the unsplit output.
The browser captured 13 decoded pictures and 16,384 stereo sample frames. Both
downloaded ProRes movies had 15 pictures and 30,000 stereo sample frames, with
maximum analytic PCM error 0.5041 of a 16-bit LSB and maximum interior picture
MAE 3.0891. Archive restoration retained editable curves and original media.

All 121 operative browser/helper source identities remained unchanged. The
original failed source-PTS experiment is preserved separately; resetting PTS
after source-frame trimming fixed the observed picture duplication. Exact
rational source anchors also prevent a reopened split curve from changing a
half-frame nearest-picture decision.

## Integrated source freeze and current gates

Current integrated receipts belong under `verification/0.12.0/`. The declared
`source-integrity.json` covers tracked Studio source, documentation and the
Studio CI workflow, rejects untracked source in scope, and is checked before
and after the full runner. Reports retain their complete inventory and digest;
the result cannot be transferred to changed source or altered managed runtimes.

The full runner uses the existing hash-pinned Linux verification environment,
actual RAW fixture and isolated optical, physical-rendering, reconstruction,
learned and Cycles runtimes. It inventories the managed engines before and
after and fails skipped tests. The recurring CI workflow also runs the actual
retime prepare/author/playback/archive coordinator and shipped native script
through the accepted Chrome for Testing build. This is Chromium acceptance and
does not set `native_certified`.

The current frozen whole-build outcome is recorded in
`verification/0.12.0/whole-build-current-01/report.json`; targeted and browser
receipts remain separate. At source freeze, that full run is pending. Later
collection must retain the exact source identity and failures, if any, without
rewriting this record into an unsupported pass.

## Native and release acceptance still required

The actual WKWebView coordinator has separate **prepare**, **author**,
**playback** and **archive** phases. Each phase has an 18-second total foreground
budget and at most 14 seconds for its helper. It joins its owned server, helper
and jobs. Source drift, stale success markers and changed truth/media fail;
repetition requires a new whole fixture. The exact commands and dependencies
are in [RETIME.md](RETIME.md).

Native acceptance, exact-head CI, bundle replacement, installed source/runtime
reconciliation and canonical installed launch remain release-owner gates.
Existing projects and the previous application must remain preserved. No
current result certifies signed/notarized distribution, arbitrary-footage
optical-flow quality, sustained production performance or full professional
parity. [The unfinished-work register](UNFINISHED_0_12.md) retains those limits.
