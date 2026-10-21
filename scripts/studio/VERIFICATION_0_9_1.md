# CINEMATICUM Studio 0.9.1 verification

Candidate verification began on 21 October 2026. This record supersedes the
current-source claims in [verification 0.9](VERIFICATION_0_9.md); the earlier
515-test run remains evidence only for its original snapshot. CINEMATICUM is
still incomplete against the full requested systems and professional workflows.
The [capability ledger](capabilities.json) retains `parity_complete: false`.

## Source and release identity

The candidate continues commit `a6454d3514b3afa9ba29f594ab6bb3b79065d1a2`
on an isolated MIDIA-AI worktree. The owner's production checkout and its
uncommitted changes are preserved. Final frozen source, complete regression,
installed-bundle identity and PR publication receipts are recorded below only
after their corresponding gates complete.

The deterministic [source manifest](source-integrity.json) covers the declared
tracked runtime, tests, native code, web assets, dependency locks, documentation
and CI workflow. [Its verifier](source_integrity.py) rejects changed, missing,
unexpected or untracked source in that scope. Generated media, temporary test
stores and acceptance evidence have separate identities to avoid circular
hashing. See [the integrity contract](SOURCE_INTEGRITY.md).

## Executed acceptance

| Gate | Result currently recorded | Actual scope |
| --- | --- | --- |
| Source PCM playback | Native-03 routing 11/11; overlap, nested and retimed scenarios 12/12 each, three repetitions per sequence scenario | Live AudioWorklet captures, selected original stream/channels, gain/pan, source-tempo retiming, restart, independent FFmpeg PCM, zero underruns and drift below 80 ms |
| High16 SDR output | Native-03 21/21 | Actual export controls, saved precision, transformed alpha, 16-bit paused frames and a real WKDownload of a lossless FFV1 master |
| Planar tracking | Native-08 10/10 in 9.463 seconds | All seven native stages completed, 12/12 actual measurements, saved stabilization/pinning, timing invalidation/undo, reopen and independently decoded ProRes with identical first/last pin centers |
| Normal Wan inference | Two serial jobs and both 14/14 independent media verifications passed; native playback 13/14 and 14/14 | 480 × 272, 17 frames, 20 steps, CFG 6, seeds 42/43; both have 17 distinct nonblank decoded frames. Native playback exposed a final-frame insertion defect, corrected and locally tested; final native rerun is blocked by changed MIDIA-AI authorization |
| Complete regression | **543 tests passed in 169.490 seconds; zero failures, errors, skips or expected failures** | All 189 operative source/test files remained unchanged; actual isolated OpenCV, NumPy, OCIO, rawpy/LibRaw, OpenEXR and official OTIO executed. All 48 JavaScript files passed syntax checking |
| Native installation | Not executed; authorization blocked | Installer closure and rollback tests pass; MIDIA-AI's upgrade invalidated command authorization before the final correction could be synchronized or a replacement bundle installed |

Native UI and backend assertion counts are separate from discoverable Python
test counts. Tests with synthetic ENGINE TEST material establish those specified
operations; they do not establish a finished film or production-scale coverage.
Wan inference uses real weights and model output rather than a substitute clip.

## Corrected integration defects

### Live source audio

The [source scheduler](web/pcm-playback.js) now rebuffers at the last scheduled
sample after a late PCM range instead of scheduling expired samples while the
timeline continues. Native acceptance decodes the selected original stream,
channels and tempo independently, then compares actual live PCM. Overlapping
clips and expanded nested sequences retain separate voices on the shared clock.
Reverse audio still requires rendered playback. General buses, plugins,
surround layouts and production-scale audio remain absent.

The [lifecycle regression](test_media_lifecycle.py) loads the shipped scheduler
and executes 40 actual PCM voice creation/play/deletion cycles. It requires
scheduled nodes to stop/disconnect, timers and listeners to be removed, chunk
references to clear and immutable sample ranges to be reused. Existing video
decoder bounds and 40 video lifecycle cycles remain covered.

### High16 SDR and alpha

[Numeric acceptance](test_high_precision.py) checks 1,024 distinct source
values, identity preservation, fractional alpha, independent source-over,
hidden-RGB invariance, geometric transforms and paused-frame/movie agreement.
The native three-frame fixture is 64 × 32 at 12 fps; the actual downloaded master
contains FFV1 `gbrap16le` and 48 kHz stereo PCM. Native-03 downloaded 63,252 bytes
with SHA-256 `0635c6f95ee4051e30c839e58eb2d64b2cecb83a9a8c9eeb177ed2c5d9cf7ef4`.

This pipeline uses clamped unsigned 16-bit SDR values. Lanczos overshoot can
clip alpha and premultiplied channels independently; the tested constant-color
edge deviation is bounded to 280/65,535 and the separate FFmpeg fractional-alpha
scaling check uses a 64-code tolerance. These are explicit numerical limits,
not evidence of an 8-bit intermediate. Whole-timeline scene-linear float,
ACES/OCIO, HDR mastering and calibrated output monitoring remain missing.
The automated native download exercises WKDownload's actual byte transfer;
it does not certify interaction with the production NSSavePanel chooser.

### Planar state and rendering

The real OpenCV LK/RANSAC worker measures affine/projective motion. Saved
measurements are bound to source hashes and clip timing. Incompatible changes
mark derived motion stale while preserving clips, imported media, authored keys
and measurements. Pure timeline translation remaps a dependent pin; undo restores
the relationship. Export rejects stale motion. Pins account for an already
stabilized background, independent of clip-array ordering.

Native execution exposed and corrected a WebKit dialog serialization issue and
the Edit-mode viewer's missing planar/high16 processed-frame trigger. The
acceptance fixture also now selects its exact project instead of relying on
creation-time sorting. The renderer remains bounded to 240 measured frames,
640-pixel analysis edge and a 2,073,600-pixel warp canvas; broader tracking,
occlusion recovery and lens/rolling-shutter estimation remain separate work.

Native-08 completed in 9.463 seconds after the inference jobs had finished.
Its 268,926-byte ProRes movie has SHA-256
`1c5bd058c3ca54a033ce1afd6f38aa26086b85c3b0ce9215d6dbf84467beb84c`.
The measured image pin's decoded centroid is `(80.5, 64.0)` in both captured
frames. The worker measurement document has SHA-256
`9f06e8171f55641f40b6ce4a6e31e52f8c6ea6237eb712fbad1573695db40165`.
Native-07's 12-second export wait expired during simultaneous Wan inference;
that failed attempt remains recorded. The current harness retains its unique
workspace, job state, source measurements and diagnostics even on failure.
The passing serialized run does not establish concurrent production throughput.

### Managed inference and ordinary quit

The pinned managed ComfyUI runtime uses the core Wan 1.3B graph and verified
model bytes. An initial normal UniPC run completed but produced nearly black
frames and failed independent acceptance. The normal workflow now selects the
core Euler sampler. Both subsequent serial normal takes completed and contain
distinct nonblank pictures. Visible output, provenance, timing and native
playback are independent gates; a completed job status alone is insufficient.

The two normal takes completed through native controls in 1,094.710 seconds
overall. Their media SHA-256 values are
`57fcc0bf999b53ce0661e467f94688875969ae9d16e60ff7d27e547657242e51`
and `05a8f65656cc522cb3a637628d2022252216872eb1bcf8025d5905349b562613`.
The first file's MP4 edit lasts 1,062 ticks on a 1,000 Hz movie clock, while all
17 media samples retain 1,024 ticks each on a 16,384 Hz clock. Its displayed
1.062012-second duration therefore reflects edit quantization; the sample
timeline is exactly 17/16 seconds. The updated independent verifier reads
`mvhd`, `mdhd`, `elst` and `stts`, verifies every packet and decoded timestamp,
and reconciles the probe duration against those actual integer clocks.
Real-encode regressions reject truncated samples, missing frames, invalid edit
offsets and edits longer or shorter than the measured clock's floor/ceiling.
The original failed report and original generated bytes remain unchanged.

Native playback then revealed a separate application defect: rounding source
duration down admitted only 16 timeline frames for that 17-frame take. The
default clip and inspector/trim/slip limits now use nearest project-frame
quantization, matching the backend's existing half-frame contract. Eighteen
focused timing/editing/trim tests pass using real probed media, the shipped
JavaScript functions and the actual backend validator. The first take's
native rerun has not executed. The explicit 33-frame acceptance harness is
prepared but has not run; no longer-take pass is claimed.

The first normal attempt's earlier ordinary application termination remains
unexplained. The new quit path saves, checks active durable jobs and offers an
explicit choice before cancellation. Job admission and executor submission now
share one lock transaction; cancelled queued Futures settle their durable state
and release owned inputs. Deterministic concurrency tests cover both races.
The server records exit reason and affected job IDs without recording prompt
or media content. This improves prevention and diagnosis without claiming to
identify the initiator of the historical termination.

## Mac execution authorization interruption

During completion work, MIDIA-AI upgraded from catalogue 0.7.2 to 0.8.0.
The next source synchronization returned
`COMMANDER_AUTHORITY_EXPIRED_OR_CHANGED` before making changes. The documented
session-successor operation preserved the predecessor worktree and created a
current-runtime context, but that context reports no reusable execution grant.
No grant or governance setting was modified to work around the rejection.

Consequently, the final source synchronization, affected native reruns,
33-frame inference and replacement installation remain unexecuted. The prior
native successes remain valid at their recorded source scopes; the final
Mac steps require renewed owner authorization. The local full regression,
integrity manifest and GitHub draft update proceed independently.

## Reproducible regression contract

`run_verification.py` requires an isolated virtual environment, pinned package
versions, actual worker interpreters and real FFmpeg/Node. The Linux CI lock
includes SHA-256 wheel identities for its supported Python versions. CI fetches
the genuine Kodak DC50 camera fixture from a pinned rawpy source commit and
checks its SHA-256 before running the full suite. A missing optional dependency
or skipped test fails the strict release run.

The native macOS CLI harnesses and actual Blender/GPU execution are separate
acceptance gates. Linux unit/media success does not imply native UI, Apple
Metal, model inference, signed distribution or calibrated monitoring.

The [complete local report](verification/0.9.1/full-actual-runtime-report.json)
records Python 3.12.14 and NumPy 2.3.5, OpenColorIO 2.6.0, rawpy 0.27.1,
OpenEXR 3.4.15, OpenTimelineIO 0.18.1 and OpenCV 4.11.0.86. The genuine
Kodak DC50 fixture is 92,675 bytes with SHA-256
`37e290dbd0053f00e508d02a6b3a2a990432dad1eb74c40a52ca899f0f225ecc`.
The [frozen operative inventory](verification/0.9.1/frozen-operative-source.json)
and [post-run identity check](verification/0.9.1/frozen-operative-check.json)
bind that execution to the unchanged code and tests. Narrative documentation
and capability-status updates are outside this execution inventory, but are
included in the final source-integrity manifest. The report SHA-256 is
`d436f9f736d0c4ba5d41bf5762de9e9039efccd99afc18e5577b2311eee821a8`.

The [native evidence summary](verification/0.9.1/native-evidence-summary.json)
retains observed gate results, original report locations and available hashes.
It is explicitly a normalized summary; the full native captures, job snapshots,
model outputs and rejected reports remain in the preserved Mac worktree.

## Remaining scope

All 11 major absent systems remain recorded in [the unfinished-work register](UNFINISHED_0_9.md):
deep/multiview/arbitrary-channel composition, AliceVision reconstruction,
SAM 2, TAPIR/TAPNext, CameraCtrl, authenticated named commercial AI services,
ray-optics lens design, Mitsuba/pbrt transport, general scene processing,
DiffusionLight and concurrent collaboration. The partial professional systems
in that register also remain incomplete.

The Mac has Apple M3, 16 GiB memory and macOS 26.5.2 build 25F84. A signing
identity inspection found an Apple Development identity and no Developer ID
Application identity. This candidate is not a notarized distribution. Its
native launcher still depends on external Python/FFmpeg/Blender and separately
managed optional runtimes. No authenticated commercial-provider generation or
purchase was performed. Longer model takes, production quality and sustained
production-scale operation remain unverified.
