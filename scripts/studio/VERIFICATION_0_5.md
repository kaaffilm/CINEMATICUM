# CINEMATICUM Studio 0.5.0 — executed verification

Recorded on 2026-10-21. The native macOS application was built, installed and opened successfully. This report describes the operations actually exercised; it does not certify parity with the applications in the [capability audit](CAPABILITY_AUDIT.md).

## Source identity

- Final runtime source: [`41e61617e21488d0e8e816cb5b50a6531e81b34d`](https://github.com/kaaffilm/CINEMATICUM/commit/41e61617e21488d0e8e816cb5b50a6531e81b34d).
- Initial upgrade checkpoint: [`6ddea02922f26f2870b8d9e2a23e772a826fa11c`](https://github.com/kaaffilm/CINEMATICUM/commit/6ddea02922f26f2870b8d9e2a23e772a826fa11c).
- `source-integrity.json` SHA-256: `3127b9b7512e64da38c86b9c2b4ad9a79bf9d77443801528d5b1f62823c138ab`.
- The transfer verified all 64 files listed in that manifest and the manifest itself. All 22 installed runtime files were then independently compared against their tested source bytes.
- This verification report is recorded after execution and is outside the source checkpoint's manifest.

## Automated media and API verification

The final [Studio media verification workflow](https://github.com/kaaffilm/CINEMATICUM/actions/runs/39524675276) completed successfully on the final runtime commit. Its real-media/API job ran **177 tests in 73.292 seconds**, with `OK`; JavaScript syntax checks also passed. The workflow installed the official OpenTimelineIO 0.18.1 reader/writer as an independent test dependency. Studio itself has no pip or npm runtime dependency.

Before the final mesh correction, the local full suite passed all 176 then-existing tests in 72.649 seconds. The added mesh transport regression and all 15 spatial-import tests passed after that correction. Final source also passed Python 3.9 syntax checks for 37 Python files and Node syntax checks for 13 web/native test scripts.

The timing regression compares every decoded output frame for 48 combinations of project clock, timestamp precision, speed and direction, each split at three positions. Audio checks inspect decoded PCM and absolute sample boundaries. These tests use explicitly identified synthetic fixtures; they are not a claim about the quality of a finished film.

## Actual native Mac acceptance

These runs launched the real WKWebView helper against the shipped interface and a disposable project server. The scripts operated visible controls, then Python independently inspected saved data or decoded actual output. They did not substitute a model of the interface for the running editor.

| Workflow | Executed evidence | Result |
| --- | --- | --- |
| Point tracking | Selected a feature in a decoded frame; measured 12 frames; applied additive stabilization and a connected animated mask; undo/redo, retime, split and save | 7 checks passed; 1.330 s |
| Compositor animation | Authored independent grade, mask and polygon keys; exercised easing and point gestures; split/trimmed; compared exact paused PNGs; exported and played 24 movie frames | 29 checks passed; 4.718 s |
| OBJ/MTL import | Rejected invalid topology without a history checkpoint; imported two actual mesh parts through the file input; checked shaded WebGL pixels, undo/redo, material edits, animation and saved geometry | 12 checks passed; 0.721 s |
| OTIO interchange | Exported an unsaved grade; read the actual attachment; reviewed roundtrip data; rejected duplicate JSON members; explicitly relinked media; applied and undid/redid external cuts | 19 checks passed; 1.015 s |
| Existing edit/export workflow | Fractional in-point, reverse/retime, track controls, eased transforms, curve/polygon gestures, decoded waveform, three scopes, save, H.264 export and native playback | 30 checks passed; 2.772 s |
| Existing 3D authoring workflow | Direct gizmos, camera/light/object animation, material edits, actual WebGL pixels, real Blender render, retained scene, completed-media history preservation and timeline admission | 30 checks passed; 3.739 s |
| Imported mesh render and scene replay | Rendered three actual frames at 24000/1001; reopened the retained `.blend`; inspected vertices, triangles, corner UVs, normals, materials, hashes, animation and saved clock | 14 checks passed |

All **seven workflows and 141 explicit checks** passed. Timings concern tiny acceptance fixtures, not production throughput or realtime performance. The tracked source and rendered test clips were never inserted into the user's production projects.

The tracking, interchange, existing editing and primitive-scene runs used the initial upgrade checkpoint. The final correction only changed mesh zero canonicalization and the compositor test's intake-file check; the affected mesh import, compositor acceptance and saved-mesh Blender replay were executed after that correction. Final CI exercised the complete final source.

## Defects found and corrected during acceptance

1. Fractional splits selected different pictures because retimed timestamps were truncated on an unrelated microsecond timebase. The conform clock now aligns to project frames and rounds explicitly; decoded split regressions pass.
2. Extending a clip left newly visible frames outside the animation domain. The domain now expands without changing existing keys, curves or independent fade endpoints.
3. Late tracking polling/cancellation callbacks could affect a reopened dialog. Per-session ownership checks now prevent those continuations from changing the new session.
4. Imported private OTIO metadata could contain invalid scene settings. Export input, import destination and returned candidates now use the same explicit settings/scene validation.
5. A mesh normal containing negative zero changed representation through JavaScript JSON serialization and failed its unchanged-geometry digest. Numeric zero is now canonicalized before hashing; a real Python/Node roundtrip regression passes, and changed coordinates still fail integrity validation.
6. The compositor acceptance harness tried to hash the staging source after intake had moved it into the project. It now verifies the admitted asset ID, path, inventory hash and actual owned media bytes. All visual and export assertions remain intact.

## Installed application

The ARM64 native build completed without compiler warnings. Bundle version is **0.5.0**, build **5**. The previous application bundle was retained as a backup.

After launch, the actual native application's child service reported `CINEMATICUM/0.5.0 Python/3.14.3`; FFmpeg, Blender and point tracking were available. Both existing projects remained present. All four pre-existing project/inventory JSON files were byte-identical before installation and after launch. No authority records, production shots or issuance objects were edited.

The configured ComfyUI endpoint refused the connection. Accordingly, no successful neural-generation, SAM 2, TAPIR, TAPNext or CameraCtrl inference is claimed. The tested per-job cancellation protocol is not evidence of model execution. Commercial model providers remain unconnected.

## Scope that remains incomplete

The installed build implements the bounded editing, compositor, tracking, geometry and interchange operations above. It does not implement the complete feature sets of the compared products. ACES/HDR/RAW, general multi-source and deep compositing, full vector/Bezier authoring, advanced topology/rigging/simulation, SfM/MVS reconstruction, neural segmentation/tracking/camera conditioning, advanced audio routing and professional-scale caching/conform remain engineering work. The [capability ledger](capabilities.json) and [source comparison](CAPABILITY_AUDIT.md) explicitly retain those gaps.
