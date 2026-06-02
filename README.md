# CINEMATICUM

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

CINEMATICUM is now operable as a local product surface.

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

CINEMATICUM now has an installable package boundary.

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

