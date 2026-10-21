# CINEMATICUM Studio 0.9.1 verification

Candidate verification began on 21 October 2026. This record supersedes the
current-source claims in [verification 0.9](VERIFICATION_0_9.md); the earlier
515-test run remains evidence only for its original snapshot. CINEMATICUM is
still incomplete against the full requested systems and professional workflows.
The [capability ledger](capabilities.json) retains `parity_complete: false`.

## Source and release identity

Published commit `4530c54faf969b0a42f2eb7e73f67c295443d275` is the
base for the current candidate, continuing
`a6454d3514b3afa9ba29f594ab6bb3b79065d1a2` in isolated MIDIA-AI worktrees.
The owner's production checkout and its uncommitted changes are preserved.
Four native acceptance harness files now select their exact fixture project.
Subsequent canonical launch exposed bundle mutation by isolated Python workers;
five launch sites in four runtime modules now explicitly pass `-B`. The frozen
189-file inventory and 544-test run below include that production correction
and its actual subprocess regression. The current runtime therefore differs
from published `4530c54`; that commit's CI does not certify this follow-up.
This evidence freeze records no follow-up publication/CI result; subsequent
results belong to the exact published commit and
[PR #162 checks](https://github.com/kaaffilm/CINEMATICUM/pull/162/checks).
Canonical launch after replacement and final installed-source reconciliation
remain separate gates.

The deterministic [source manifest](source-integrity.json) covers the declared
tracked runtime, tests, native code, web assets, dependency locks, documentation
and CI workflow. [Its verifier](source_integrity.py) rejects changed, missing,
unexpected or untracked source in that scope. Generated media, temporary test
stores and acceptance evidence have separate identities to avoid circular
hashing. See [the integrity contract](SOURCE_INTEGRITY.md).

## Executed acceptance

| Gate | Result currently recorded | Actual scope |
| --- | --- | --- |
| Source PCM playback | Final-native-01 routing 11/11; overlap, nested and retimed scenarios 12/12 each, three repetitions per sequence scenario | Actual live captures, selected stream/channels, gain/pan, source-tempo retiming and restart; zero underruns and drift below 80 ms |
| High16 SDR output | Final-extended-01 21/21 in 2.153 seconds | Saved precision, transformed alpha, 16-bit paused frames, real export controls and 63,252-byte WKDownload. The earlier exact-fixture bootstrap failure remains retained |
| Planar tracking | After the worker correction, bundle-fixed-planar passed 10/10 in 10.282 seconds | Seven native stages, actual measurement, timing invalidation/undo, save/reopen and independent ProRes decoding; identical first/last pin centers |
| Normal Wan inference | Two real serial takes passed 14/14 media checks and both final native playbacks passed 14/14 | 480 × 272, 17 frames, 20 steps, CFG 6, seeds 42/43; all 17 timeline frames survive Add/Play/Save |
| Longer Wan case | Inference harness 11/11, independent media 14/14, native playback 14/14; generation 928.394 seconds | One actual 33-frame take at the same resolution/steps/fps/CFG; distinct nonblank pictures. Production quality and sustained operation remain unverified |
| Complete regression | **544 tests passed; zero failures, errors, skips or expected failures** | All 189 operative files unchanged. Actual pinned optional workers and genuine RAW ran. Report elapsed 169.194 seconds; wrapper elapsed 169.301 seconds. The 48 unchanged JavaScript files retain their syntax-check result |
| GitHub CI | Historical base `4530c54`: 23 successful workflow runs; Studio 543 tests and 209 manifest files | Historical published base only; this evidence freeze contains no follow-up CI result. Consult the exact subsequent commit and PR #162 checks |
| Native installation | Install-03 verifier observed PASSED in 16.515 seconds; all five gates and 189 operative hashes passed | 62 runtime files, 67 bundle files, 70-file prior archive and all 57 protected files preserved. Public record is an observation of returned fields; full raw receipt was not collected |
| Production ordinary quit | Quit-05 passed 21/21 independent and 10/10 native checks in 67.203 seconds | Actual Keep Working and Cancel Jobs and Quit choices with two real FFmpeg jobs; completed 48-frame master retained, second job cancelled, durable and ephemeral jobs settled. Isolated startup, not installed-app UI acceptance |
| Production chooser | Download-03 verified actual default-destination Save, hash, decode and alpha; aggregate failed because synthetic Escape did not cancel | Original failures are retained. Download-04's SDK Cancel helper is reviewed but **unexecuted**; production cancellation remains unaccepted |
| Canonical installed launch | Launch-01 found bundle mutation; corrected launch-02 started but its result was **not collected** | The first actual launch/engine/ordinary quit preserved all protected files, but added three bytecode files. The corrected app's whole-bundle immutability remains unaccepted |
| Final installed-source reconciliation | **Not executed** | Mac access changed: prior session denied cross-chat access, fresh session hit the 64-session limit. No new canonical or reconciliation pass is inferred |

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

The final-native-01 attempt failed before opening its intended fixture because
the harness relied on creation-time ordering. Its unaltered
[failed report](verification/0.9.1/final-native-01/high16/ENGINE_TEST_high16_native_report.json)
is retained. The harness now selects the exact project through native controls;
[final-extended-01](verification/0.9.1/final-extended-01/high16/ENGINE_TEST_high16_native_report.json)
passed 21/21 in 2.153 seconds. This changed fixture binding, not movie processing
or timeout limits. The raw-report SHA-256 is
`9a20eaaff4c41dfd15aa820d4a39cc6cf5d526087ca052913947037112c2afea`.
Its 63,252-byte master has SHA-256
`c864ecf9c5f9962a35a57827e40580f16ef21bf4ac4544cee5491b5282c518d2`.
The separate production chooser Save has since been verified; native cancellation remains unaccepted as detailed below.

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

The [final native rerun](verification/0.9.1/final-native-01/planar/result.json)
passed 10/10 in 7.342 seconds with seven control stages and no evidence errors.
Its actual ProRes movie retains the same size, hash and stable pin centroids
reported above. The final measurement-document SHA-256 is
`d82e16ee43fcb77acafe579d5ddf962cf011e9ba42a83534e15fb8c4a91f85b6`;
the final raw report SHA-256 is
`7a58f14f80987cfd8f6a3ed8dc4dd0323c19d4e63e980cc919670917e3154ed5`.

After adding explicit `-B` to the isolated worker launches, the
[bundle-fixed planar rerun](verification/0.9.1/bundle-fixed-planar/result.json)
passed 10/10 in 10.282 seconds, including all seven native stages and actual
OpenCV 4.11.0/NumPy 2.3.5 measurement. The 268,926-byte movie and both pin
centroids match the earlier output. Its report SHA-256 is
`00d5cd9eb9a8287fef76d0b91ad8844a05c80ab1286e97a40f3fcc0803f3e013`;
the measurement SHA-256 is
`48c773d26c4b3e1d7e91a7ff8571759aaa2beef3d2795ea031ca5f15f45537a5`.

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
JavaScript functions and the actual backend validator. After authority was
restored, both final native reruns passed 14/14 with all 17 timeline frames:
[take 1](verification/0.9.1/final-native-01/actual-take-1/ENGINE_TEST_actual_take_report.json)
in 2.236 seconds and
[take 2](verification/0.9.1/final-native-01/actual-take-2/ENGINE_TEST_actual_take_report.json)
in 2.149 seconds. Their raw-report SHA-256 values are
`aaa834bdd7c76e567ce8c1c4f8f62a86d2854f18198a8f8f754f1995721d0df6`
and `d64795e097b5b89aa9da7aae9744a29954c6be976f19da0af6e75fe5e7b20ed9`.
Original take media, provenance and job snapshots remain unchanged. This closes
the bounded normal 17-frame workflow; it does not erase the earlier 13/14 failure.

The 33-frame harness now selects its exact intended project through native UI
events and verifies the saved project/job identities. Actual longer job
`c3db07f8a6b549e8aed24a593035cb65` passed. The
[generation harness](verification/0.9.1/final-extended-01/generation33/report.json)
passed 11/11 in 928.394 seconds, its independent media verifier passed 14/14,
and [native playback](verification/0.9.1/final-extended-01/generation33-playback/ENGINE_TEST_actual_take_report.json)
passed 14/14 in 4.208 seconds. All 33 decoded frames were distinct and nonblank;
the exact sample timeline was 33/16 seconds and original media/provenance stayed
unchanged. Source SHA-256 is
`d04d5bad300a117b1519b1d7d2144741591589921275e326bddc15bba86f085e`.
The inference and playback report SHA-256 values are
`7df576feb8e7bedae8c45a42925bad64d34f77ede2d371456c1ddfb7ba6ea824`
and `bfcfbfe1849a522cf1ccaf91b5ed566b37968ac97a6bdfc96af538c66fc3c14e`.
The [extended batch](verification/0.9.1/final-extended-01/status.json) passed in
937.624 seconds: high16, generation33, generation33-playback and source-after
each exited 0. This is one longer bounded test, not a production-quality or
long-session certification.

The first normal attempt's earlier ordinary application termination remains
unexplained. The new quit path saves, checks active durable jobs and offers an
explicit choice before cancellation. Job admission and executor submission now
share one lock transaction; cancelled queued Futures settle their durable state
and release owned inputs. Deterministic concurrency tests cover both races.
The server records exit reason and affected job IDs without recording prompt
or media content. This improves prevention and diagnosis without claiming to
identify the initiator of the historical termination.

## Actual production quit acceptance

[Quit-05](verification/0.9.1/production-quit-05/production-quit-report.json)
passed **21/21 independent checks and 10/10 native checks in 67.203 seconds**.
The unchanged production ordinary-quit methods and actual AppKit alert buttons
ran against an isolated real server. **Keep Working** allowed the first actual
640 × 360, 48-frame, 12 fps FFV1 high16 render to complete. A second actual
render was then cancelled through **Cancel Jobs and Quit**. The dirty edit was
saved, both job snapshots retained their proper revisions, the second job
published no partial export, and the owned server exited normally.

The completed 9,281,929-byte master and its export manifest survived later
cancellation; independent decoding verified all 48 picture frames and audio.
Its SHA-256 is
`0bdcf44378a04acd0e00f035cd06b4d480c4ff77b85c4361235d36963898528d`.
The receipt reconciles durable render cancellation with separately settled
ephemeral frame-preview work. The report SHA-256 is
`a686c88ca02f35477223756652f3be71ab6af9a3a48d581efb21789d9a99dadf`.
This certifies the unchanged production methods and real alerts, not installed
bundle UI or an explanation of the historical generation termination.

Earlier reports remain unchanged: the first invocation refused an output path
inside source before native execution; quit-03's aggregate failed because the
fixture upload was moved during admission; quit-04 compared ephemeral preview
state with durable persistence. The corrected harness preserves the original
fixture and checks each job according to its actual lifecycle.

## Mac execution access interruptions

MIDIA-AI's catalogue 0.7.2-to-0.8.0 upgrade initially caused
`COMMANDER_AUTHORITY_EXPIRED_OR_CHANGED` before synchronization made changes.
A successor later acquired a reusable owner grant and successfully fetched
verified source, ran native gates and installed the app. That first interruption
was resolved without modifying governance settings or bypassing an access gate.

After install-03 passed, a connection-context change caused the prior session
to return `CROSS_CHAT_SESSION_ACCESS_DENIED`. Opening a proper fresh session for
this conversation returned `ACTIVE_SESSION_LIMIT` at 64 sessions. No fresh
session was created, no other session was closed and no alternate conversation
context was used. **Mac evidence collection and final reconciliation are now
blocked.** Canonical launch-02 had started, but its outcome is unobserved;
download-04 has not run. Earlier successful executions do not authorize a claim
that those remaining gates passed.

## Installation and canonical launch

[Install-02](verification/0.9.1/installation-02-summary.json) passed its before
snapshot, replacement and independent after-verification in 40.491 seconds.
Its privacy-minimized derived summary records 62 runtime files, 67 bundle files,
a preserved 59-file original app archive and all 56 then-protected workspace
files (2,858,327,609 bytes). Full raw filenames remain outside the public repo.
The original archive remains preserved. The independent helper's initial
2 GiB inventory bound refused before writes; its 4 GiB bound hashes all observed
bytes without exclusions.

The [first canonical launch](verification/0.9.1/installed-launch-01/installed-launch-report.json)
used the exact installed app through LaunchServices, observed its real bundled
server and default workspace, then performed ordinary native quit. All 56
protected files survived. The aggregate failed because the bundle grew from
67 to 70 files: isolated workers wrote cached bytecode for `imaging`,
`media_orientation` and `projective_warp`. Python `-I` ignored the inherited
bytecode environment flag. This was a real bundle-preservation defect.

The correction adds explicit `-B` to five subprocess launches in `imaging.py`,
`planar_tracking.py`, `lens_assets.py` and `roto_assets.py`. Native launcher and
processing behavior are unchanged. The
[worker-fix evidence](verification/0.9.1/worker-bytecode-fix/manifest.json)
retains the failing actual copied-runtime regression and the corrected **8/8**
focused run. The expanded test runs real imaging/planar/lens/roto subprocesses;
the full 544-test freeze and later native planar/quit runs include the fix.

[Install-03's observed output](verification/0.9.1/installation-03-observation.json)
then reported **PASSED in 16.515 seconds**: snapshot-before, actual replacement
and verify-after each exited 0; source, installed bytes, receipt/backup, projects
and original-checkout gates all passed. It checked all 189 frozen operative
files and installed the corrected 62-file runtime in a 67-file bundle. All 57
protected files, totalling 2,858,327,758 bytes, were preserved. The 70-file prior
bundle, including the observed caches, was archived separately from the original
59-file backup. This public record contains selected fields actually returned
by the verifier; **the full raw install-03 receipt was not collected** before
access changed.

The observation SHA-256 is
`de8ef8a29ccaf4126604ace9c9d05c7b16ca314dcf4deb119130fdca0510c9c0`.
The reported raw after-receipt SHA-256 is
`08a3d73a39706c46b9c63785f15403fd1abd9a8ea39cb2b11713c519cb10d852`;
the installed bundle inventory is
`577a3550a6136bfe130434bf760ff0f21f1e24864facd5c11c52a07028afb6a9`.
Canonical launch-02 was started with supervisor PID 8525, but its result is
**uncollected and not accepted**. Final published-source synchronization and
independent installed-source reconciliation have **not executed**.

The installer copies 40 runtime modules/locks and 22 web files, plus its own
generated `source-manifest.json`; repository `capabilities.json` and
`source-integrity.json` are not bundled. The four production worker corrections
required install-03. Remaining narrative/evidence edits do not themselves
replace the missing canonical-launch and final-reconciliation evidence.

## Native chooser: Save verified, cancellation still unaccepted

The unchanged production `StudioAppDelegate` was compiled with isolated startup;
this is not an installed-bundle UI claim. Original
[attempt 01](verification/0.9.1/production-native-01/production-download-report.json)
and [attempt 02](verification/0.9.1/production-native-02/production-download-report.json)
remain failed. Later inspection established that native Save had written each
exact job's master to its default Movies/job-UUID destination; the helper had
incorrectly expected a proxy-set destination. The
[recovery record](verification/0.9.1/owned-default-download-recovery.json)
binds only those two synthetic files to completed-job receipts and hashes before
relocation to evidence storage. No aggregate pass is inferred retrospectively.

[Attempt 03](verification/0.9.1/production-native-03/production-download-report.json)
verified actual native default-destination Save, the completed-job receipt,
all 63,252 downloaded bytes, FFV1 `gbrap16le`/PCM decoding, fractional alpha and
more than 256 colors. Master SHA-256 is
`33e350dc3493366a6e8a902f68324d2626201851aac75d4d47bf9123cac19d7c`.
Its aggregate remains failed: the helper's synthetic Escape interaction did not
cancel and the destination was recreated. The
[exact owned-file recovery](verification/0.9.1/production-native-03/owned-default-download-recovery.json)
preserves that failure without leaving the synthetic output in Movies.

Download-04 changes only the acceptance helper to use the explicit SDK Cancel
action. It has been reviewed and curated but is **unexecuted**. Production
NSSavePanel cancellation, arbitrary chooser navigation, renamed destinations and
replacement of existing files are not certified. The earlier automated 21/21
WKDownload gate and the verified Save are not substituted for those behaviors.

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

The [current complete local report](verification/0.9.1/bundle-fixed-full-actual-runtime-report.json)
records **544 tests passed with zero failures, errors, skips or expected
failures**. It used Python 3.12.14, NumPy 2.3.5, OpenColorIO 2.6.0,
rawpy 0.27.1, OpenEXR 3.4.15, OpenTimelineIO 0.18.1 and OpenCV 4.11.0.86.
The genuine Kodak DC50 fixture is 92,675 bytes with SHA-256
`37e290dbd0053f00e508d02a6b3a2a990432dad1eb74c40a52ca899f0f225ecc`.
The [frozen operative inventory](verification/0.9.1/bundle-fixed-frozen-operative-source.json)
and [post-run identity check](verification/0.9.1/bundle-fixed-frozen-operative-check.json)
confirm all 189 files remained unchanged. The report elapsed time is 169.194
seconds; the wrapper elapsed time is 169.301 seconds. Report SHA-256 is
`50f5531cbbd015abb7dc238c91e91ecc685d0cda48014deac31f70e416264541`;
inventory SHA-256 is
`30b514a409c8a0d86a047780b004942f6c65defbaf3ccb7e0da72f92085f7f3d`.
The worker correction changes Python files only; the 48 unchanged JavaScript
files retain the recorded successful syntax checks. Narrative documentation
and capability-status changes are outside this execution inventory and belong
in the separately regenerated source-integrity manifest.

The [543-test harness-corrected report](verification/0.9.1/final-full-actual-runtime-report.json)
(169.407-second test run, 169.519-second wrapper) and
[earlier 543-test report](verification/0.9.1/full-actual-runtime-report.json)
(169.490-second test run) remain historical receipts for their own snapshots.
They do not certify the later worker-launch correction.

On exact commit `4530c54faf969b0a42f2eb7e73f67c295443d275`, all 23 observed
GitHub workflow runs passed. The
[Studio CI job](https://github.com/kaaffilm/CINEMATICUM/actions/runs/39661961306/job/119437028259)
passed 543 tests in 172.641 seconds with zero skips and verified 209 manifest
files. This evidence freeze contains no CI result for the worker correction
and harness/documentation follow-up. Consult the exact published follow-up
commit and [PR #162 checks](https://github.com/kaaffilm/CINEMATICUM/pull/162/checks)
for subsequent results; success for the earlier head is not transferred to it.

The [native evidence summary](verification/0.9.1/native-evidence-summary.json)
retains current and historical results, original report locations and available
hashes. It is explicitly a normalized summary. Unaltered final-native-01 raw
reports are retained alongside it; that batch's original failed status remains
because high16 initially failed fixture bootstrap. Full captures, job snapshots,
model outputs and earlier rejected reports remain in preserved Mac worktrees.

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
purchase was performed. One 33-frame model take has bounded inference/playback
acceptance; broader longer-duration coverage, production quality and sustained
production-scale operation remain unverified.
