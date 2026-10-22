# CINEMATICUM

## CINEMATICUM Studio — editable production workspace

The current **0.10 candidate** preserves the recovered scientific authoring,
learned tracking, reconstruction, scene-processing, collaboration and waveform
synchronization implementations. [Implemented scope](scripts/studio/FEATURES_0_10.md),
[verification](scripts/studio/VERIFICATION_0_10.md) and
[remaining work](scripts/studio/UNFINISHED_0_10.md) identify the actual bounds
and independent release gates. Earlier acceptance below belongs to its pinned
0.9.1 source; it does not certify this newer candidate.

Open the media editor with `make studio`. On macOS, `make studio-install-macos`
builds **CINEMATICUM Studio.app** using the installed Xcode tools. CINEMATICUM owns
the timeline, compositor, mixer, color controls and 3D authoring interface. They
share editable project data and undo history; FFmpeg, Blender and optional imaging
workers execute the processing.

The 0.9 source adds multiple editable sequences and live nested picture/sound,
manual synchronized multicamera cuts, SRT/WebVTT captions and burn-in, source
audio-stream/channel mapping, and 29.97/59.94 drop-frame display. Preview proxies
are verified against the original decoded frame clock; exact-original relinking
restores recorded media identity. Exports continue to use original media.

The compositor now has editable cubic Bézier roto with animated handles and
point feather, bounded SVG boundary exchange, and combined 1D-shaper/3D Cube
LUT processing. The 3D workspace adds object parenting with inherited animation,
editable UVs, actual Blender smart unwrap, island packing and eight live modifier
types. Cycles device selection validates the executing engine's actual devices.
A normal owned Metal scene job completed in 82.430497 seconds; independent
verification passed 18 checks on its actual pixels, retained scene and device
receipt. Other GPU backends have not been verified on hardware.

These additions retain exact rational timeline timing, retiming/reverse,
slip/slide/roll editing, measured source tracking, scopes, multi-source node
compositing, calibrated fSpy/COLMAP cameras, physical lens/material controls and
H.264/ProRes export. Authored Cycles scenes retain editable `.blend` files and
scene-linear float EXR sequences with optional render passes. The Develop
workspace performs real OCIO transforms, camera RAW still development and merges
pre-aligned brackets through an optional imaging runtime. Movie editing remains SDR;
RAW-movie and HDR finishing are not implemented.

Recovery checkpoints, saved-version history, portable project archive/restore
and production shot-plan binding/assembly remain part of the same app. Managed
ComfyUI installation, owned MPS startup and one real Wan 1.3B take are verified:
192 × 128, nine frames at 16 fps, four sampling steps, seed 42. Generation took
44.410 seconds. Independent media verification and native Add/Play/Save each
passed 14 checks, including all nine actual source pictures. This is a small
execution proof. Two later 480 × 272, 17-frame, 20-step Euler takes completed
and each passed 14 independent media checks. A preceding normal UniPC take was
nearly black and was rejected. An earlier native playback exposed a final-frame
insertion defect. After the nearest-frame correction, both final native
Add/Play/Save runs passed **14/14 checks** and preserved all 17 timeline frames.
The normal workflow is accepted within these settings. One real 33-frame take
also passed inference and native playback; its generation harness took 928.394
seconds. This is one bounded longer case. Production quality and sustained
operation remain unverified; the earlier ordinary termination's cause is unknown.

The 0.9.1 candidate replaces browser-decoded live sound with a source-sample
scheduler and adds measured affine/projective planar motion, stabilization,
image corner pinning, 16-bit UNORM SDR movie processing, and a lossless FFV1
RGB+alpha master. Native acceptance now covers source routing, overlapping
clips, live nested sequences and repeated retimed playback with zero underruns,
plus transformed 16-bit paused pictures and an actual native master download.
Current-source regression, remaining native gates and installation are recorded
separately in [Verification 0.9.1](scripts/studio/VERIFICATION_0_9_1.md).

Native quit now asks before cancelling active media jobs. Actual production
alert acceptance passed **21/21 independent and 10/10 native checks**: one real
48-frame high16 master completed after Keep Working, and a second render was
cancelled without damaging the first export. The installer archives the prior
bundle and records every copied runtime file's SHA-256 identity. The original
production checkout remains preserved.

Canonical launch exposed isolated workers creating bytecode inside the app.
Five launches in four modules now explicitly suppress it with `-B`; the frozen
corrected source passed **544 tests with zero failures, errors or skips** and
all 189 operative files stayed unchanged. The 48 unchanged JavaScript files
retain their successful syntax checks. The corrected runtime is published at
`81827cf92d159b9619d51000da61ea3c8a6b6ce7`; all 23 exact-head workflows passed. Later documentation-commit CI remains
separate from this frozen result and live
[PR #162 checks](https://github.com/kaaffilm/CINEMATICUM/pull/162/checks).

Install-03 passed in 16.515 seconds, and its full private receipt has now been
collected and hash-verified. The corrected 62-file runtime, 67-file bundle,
70-file prior archive and all 57 protected workspace files were verified.
Canonical launch-02 passed **16/16**, preserving the entire bundle through real
launch/engine/ordinary quit. Final reconciliation passed **9/9** against the
published `81827cf` runtime. Production chooser acceptance passed **22/22**
through actual Save and the public NSSavePanel Cancel action, with exact media
bytes and no cancelled destination or partial download. This does not certify
physical Cancel-button/Escape input, arbitrary chooser navigation or replacement
of existing files. Current-session access is restored; earlier failed attempts
remain retained. Full system parity and signed distribution remain unfinished. This Studio work
does not establish current THE LAST RENDER film completion or issuance; retained
historical compiler/replay records keep their separate scope.

Start with [the Studio guide](scripts/studio/README.md),
[the source comparison and capability audit](scripts/studio/CAPABILITY_AUDIT.md),
[the current verification record](scripts/studio/VERIFICATION_0_9_1.md), and
[the current unfinished-work register](scripts/studio/UNFINISHED_0_9.md). These
records separate source implementation, executed acceptance and deployment.
Run `make studio-doctor` to inspect installed engines or `make studio-test` for
application/media tests. Film footage must be imported or actually generated;
missing media are never replaced with a procedural film. Studio exports do not change
Case 001's issuance status or repository authority.

Full professional feature parity with all referenced applications and commercial
AI-provider integrations is not implemented. The audit and machine-readable
ledger record the remaining work rather than treating an installed engine or a
visible control as proof of the full feature set.

## Historical production and replay CLI

The sections below retain the **THE LAST RENDER** compiler/replay history and
its v1.0–v1.7 package boundaries. That version line is separate from Studio 0.9.
In particular, the old `cinematicum studio` command and its no-network,
no-external-media/no-selection boundary describe that historical replay
surface. Studio 0.9 imports and selects media, renders authored scenes, and
optionally downloads and runs a managed generation engine. Those historical
restrictions do not describe Studio's current authoring workflow, and neither
version line changes the repository's issuance authority.

Strict realistic production stack for **THE LAST RENDER**.

This repository does not accept toy procedural media as a final film.

## Real final-picture input

Place realistic MP4 shots here:

```text
source/films/THE_LAST_RENDER/shots/
````

Each file must match:

```text
production/THE_LAST_RENDER/shots/shotlist.json
```

## Commands

```bash
make check
make source-qc
make render
make open
```

## External video backend

```bash
VIDEO_GEN_COMMAND='your_real_video_backend_command' make render
```

The backend receives:

```text
SHOT_ID
PROMPT_FILE
OUT_MP4
DURATION
WIDTH
HEIGHT
FPS
```

and must write a real MP4 to `OUT_MP4`.

No procedural fallback. No fake media. No proof-only issuance.

<!-- CINEMATICUM_PRODUCT_BOUNDARY_V1_START -->
## CINEMATICUM v1.0 Product Boundary

This historical v1.0 boundary records the local compiler/replay product surface.

```bash
node bin/cinematicum.cjs verify
node bin/cinematicum.cjs proof
node bin/cinematicum.cjs artifact
node bin/cinematicum.cjs studio
node bin/cinematicum.cjs export
```

Boundary:

- no external API
- no external media
- no network runtime dependency
- no manual media selection
- no candidate selection
- no truth claim
- no admissibility claim
- no external reality claim

The product boundary proves command availability, local studio surface, release-bundle export, director-engine linkage, compiler-generated film linkage, and issued GODCUT artifact integrity.
<!-- CINEMATICUM_PRODUCT_BOUNDARY_V1_END -->

<!-- CINEMATICUM_INSTALLABLE_PRODUCT_BOUNDARY_V11_START -->
## CINEMATICUM v1.1 Installable Product Boundary

This historical v1.1 boundary records the installable compiler/replay package;
it is separate from the native Studio application described above.

The package must prove, from a clean temporary install, that these commands work without cloning the working tree manually:

```bash
cinematicum proof
cinematicum artifact
cinematicum studio
cinematicum verify
cinematicum export
```

The installable boundary preserves:

- no external API
- no external media
- no network runtime dependency
- no manual media selection
- no candidate selection
- no truth claim
- no admissibility claim
- no external reality claim

The release package is a product transport. It does not convert the film into truth, admissibility, or external reality.
<!-- CINEMATICUM_INSTALLABLE_PRODUCT_BOUNDARY_V11_END -->

<!-- CINEMATICUM_OUTSIDER_REPRODUCIBLE_RELEASE_V12_START -->

## CINEMATICUM v1.2 — Outsider Reproducible Release Boundary

CINEMATICUM v1.2 seals the public release surface.

The v1.2 boundary proves that an outsider can verify the issued GODCUT film artifact from a deterministic release bundle without trusting the author's working tree.

Verified boundary:

- deterministic release bundle
- deterministic outsider replay manifest
- release asset hash ledger
- replay from extracted bundle
- single JSON command surface
- gitless runtime verification
- no external API
- no external media
- no network runtime dependency
- no manual media selection
- no candidate selection
- truth/admissibility/external reality not claimed

Canonical issued artifact:

```text
CASES/CASE_001_THE_LAST_RENDER/FILM/CASE_001_THE_LAST_RENDER_GODCUT_0001.mp4
sha256: f23d3da43ed0dfc0a4f97b7c6ad722107cc2531ac584780424ace2c45ff5a192
```

Verification:

```bash
node scripts/verify-outsider-reproducible-release.mjs
```

<!-- CINEMATICUM_OUTSIDER_REPRODUCIBLE_RELEASE_V12_END -->

<!-- CINEMATICUM_PUBLIC_RELEASE_CONSUMPTION_V130_START -->

## CINEMATICUM v1.3 — Public Release Consumption Receipt

CINEMATICUM v1.3 adds a public release consumption receipt.

The verifier starts from the public GitHub release assets for `v1.2.0-outsider-reproducible-release`, downloads the release bundle and reproducibility ledgers, verifies their SHA-256 values, extracts the outsider bundle into a temporary clean directory, runs the bundled CLI commands, verifies the film artifact hash, and emits:

```text
CONSUMPTION/CASE_001_PUBLIC_RELEASE_CONSUMPTION_RECEIPT.json
```

This proves public release asset consumption and extracted outsider replay.

It does not prove truth, admissibility, or external reality.

<!-- CINEMATICUM_PUBLIC_RELEASE_CONSUMPTION_V130_END -->

<!-- CINEMATICUM_PUBLIC_RELEASE_LINEAGE_V140_START -->

## CINEMATICUM v1.4 — Public Release Lineage Ledger

CINEMATICUM v1.4 adds a public release lineage ledger.

The verifier checks the public release chain from v0.9 through v1.3, verifies each GitHub release exists, verifies releases are not drafts or prereleases, checks ordered Git ancestry between release tags, binds the public release consumption receipt into the lineage, and emits:

```text
RELEASES/CINEMATICUM_PUBLIC_RELEASE_LINEAGE_LEDGER.json
```

This proves a machine-readable public release chain.

It does not prove truth, admissibility, or external reality.

<!-- CINEMATICUM_PUBLIC_RELEASE_LINEAGE_V140_END -->

<!-- CINEMATICUM_EXTERNAL_AUDITOR_PACK_V150_START -->

## CINEMATICUM v1.5 — External Auditor Pack

CINEMATICUM v1.5 adds a minimal external auditor pack:

```text
AUDIT/CINEMATICUM_EXTERNAL_AUDITOR_PACK.json
```

The pack is public-pointer-only. It does not embed the source tree or film media. It names the public release URLs, expected asset hashes, expected replay commands, expected JSON object types, expected artifact hash, and the runtime boundary after public asset acquisition.

It proves that an external auditor has a machine-readable audit contract.

It does not prove truth, admissibility, or external reality.

<!-- CINEMATICUM_EXTERNAL_AUDITOR_PACK_V150_END -->


## CINEMATICUM v1.6 — External Auditor Pack Public Consumption Receipt

CINEMATICUM v1.6 adds a public consumption receipt for the external auditor pack itself.

This boundary verifies that a clean consumer can acquire the v1.5 public auditor pack release assets, validate the auditor pack and standard, use the pack as the machine-readable replay map, acquire the public assets named by the pack, verify their SHA-256 values, extract the outsider reproducible bundle, run the expected replay commands, and confirm the GODCUT artifact hash.

It does not embed the source tree.
It does not embed film media in the auditor pack.
It does not require a local repository for the auditor after public asset acquisition.
It does not claim truth, admissibility, or external reality.

## CINEMATICUM v1.7 — Standalone Public Auditor Runner

CINEMATICUM v1.7 adds a standalone public auditor runner.

The runner is designed to be executed outside the source repository. It consumes the public v1.5.1 auditor pack release, verifies the public auditor pack canonical hash, verifies the public assets named by the pack, extracts the outsider reproducible release bundle, runs the bundled CINEMATICUM CLI commands, verifies the expected JSON object types, and checks the issued film artifact hash.

It does not require private source, a local repository, embedded source tree, or film media embedded in the auditor pack. Network is required only to acquire public release assets. After acquisition, replay runs from the extracted public bundle.

It does not claim truth, admissibility, or external reality.

```bash
node AUDIT/CINEMATICUM_PUBLIC_AUDITOR_RUNNER.mjs
node scripts/verify-public-auditor-runner.mjs
````


<!-- CINEMATICUM_RECIPROCAL_PRODUCTION_AUTHORITY_ACK_V1_START -->

## Cross-repository authority acknowledgement

This production/replay repository acknowledges CINEMATICUM/CINEMATICUM at accepted merge 517fd51f43ae8a17db219da352f5b83998d45fbd as the canonical CINEMATICUM issuance jurisdiction.

This repository remains the canonical pinned production/replay artifact track for its own production artifacts, replay artifacts, and public release replay evidence.

It does not hold truth authority, admissibility authority, or admissible-motion-picture issuance authority.

The acknowledged Case 001 issuance status is CASE_OPEN_NOT_ISSUED.

The production GODCUT remains pinned at:

CASES/CASE_001_THE_LAST_RENDER/FILM/CASE_001_THE_LAST_RENDER_GODCUT_0001.mp4
SHA-256: f23d3da43ed0dfc0a4f97b7c6ad722107cc2531ac584780424ace2c45ff5a192

Production artifact existence, artifact issuance, or successful replay does not imply admissibility or admissible-motion-picture issuance.

This acknowledgement does not delete, archive, rewrite, or source-merge either repository.

This acknowledgement becomes effective only if this change is independently approved and merged to production main.

On that accepted merge, the two-repository role split becomes reciprocally bound, full cross-repository canonicality becomes resolved, and Kaaffilm adapter implementation becomes eligible without source merge.

Machine-readable acknowledgement:

AUTHORITY/CINEMATICUM_PRODUCTION_REPOSITORY_AUTHORITY_ACKNOWLEDGEMENT.json

Verification command:

node scripts/verify-production-repository-authority-acknowledgement.mjs

<!-- CINEMATICUM_RECIPROCAL_PRODUCTION_AUTHORITY_ACK_V1_END -->

