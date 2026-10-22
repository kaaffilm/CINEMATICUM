# Segmentation, tracking and camera conditioning: source review

Reviewed 2026-10-21 through official repositories, source files and server documentation. The source objects below were read through the connected GitHub plugin. Their Git blob SHA identifies the inspected file content; it is **not** a repository commit SHA. The branch links are navigational and may move. No upstream model code, checkpoint or training data is bundled by this change.

| System | Inspected source | Git blob SHA |
| --- | --- | --- |
| SAM 2 | [`sam2/sam2_video_predictor.py`](https://github.com/facebookresearch/sam2/blob/main/sam2/sam2_video_predictor.py), initialization and prompt correction | `5a7e1a01c4d6e89db0453ce982ea8a31b16651c8` |
| TAPIR / TAPNext | [TAPNet README](https://github.com/google-deepmind/tapnet/blob/main/README.md), model families and coordinate conventions | `f11a85ae151e47ea146322e9f02850bd927364c2` |
| TAPNext | [`tapnet/tapnext/tapnext_torch.py`](https://github.com/google-deepmind/tapnet/blob/main/tapnet/tapnext/tapnext_torch.py), prediction heads and recurrent forward state | `d4543c00abaa8561bfd448cecaf58f702b7cf90c` |
| CameraCtrl | [`cameractrl/data/dataset.py`](https://github.com/hehao13/CameraCtrl/blob/main/cameractrl/data/dataset.py), camera records and ray conditioning | `e937426c54766d79b18a3260fc535bbf8bb1173e` |
| CameraCtrl | [`cameractrl/models/pose_adaptor.py`](https://github.com/hehao13/CameraCtrl/blob/main/cameractrl/models/pose_adaptor.py), pose feature injection | `e2ecf778ba1977babd8f88550307a8b5e2af90ba` |
| ComfyUI | [`server.py`](https://github.com/Comfy-Org/ComfyUI/blob/master/server.py), node/model discovery, prompt validation, history and scoped job cancellation | `29d0b19425806ce44f9a4ff0673005a1211a5449` |
| FFmpeg | [`libavfilter/vf_find_rect.c`](https://github.com/FFmpeg/FFmpeg/blob/master/libavfilter/vf_find_rect.c), template matching and missing-match output | `88dfecbe222859aaf65307a1be8b715723a3f3bf` |

## Different systems produce different kinds of evidence

| Operation | Inputs and outputs observed in the source | CINEMATICUM boundary |
| --- | --- | --- |
| SAM 2 video segmentation | Frames plus per-object positive/negative points, boxes or masks; object identities, cached memory and per-frame masks/logits | A geometric ellipse following a point does not identify an object or implement segmentation. SAM 2 inference and temporal mask clips remain missing. |
| TAPIR point tracking | A query point, video features, candidate matching and correlation refinement; point trajectories with separate visibility information | A point track can drive translation or a shape center. It does not supply a semantic mask, lens model or a solved camera. |
| TAPNext recurrent tracking | Video tokens and query tokens; point/visibility predictions plus a state containing step, queries and hidden caches | Streaming state, coordinate conversion and model identity must survive chunk boundaries. CINEMATICUM has no TAPNext inference worker in this release. |
| CameraCtrl generation | Intrinsics and world-to-camera poses become Plücker ray features, injected into a video diffusion model | Camera conditioning influences generated images. It is not camera recovery from observed footage. No CameraCtrl model execution or camera export is claimed. |
| ComfyUI execution | API graph, installed node definitions/model choices, prompt ID, execution history and actual output files | A configurable execution service can run a correctly provisioned workflow. Connectivity or a product label does not establish a working model. |
| CINEMATICUM point measurement | A selected patch in the conformed source frame; measured XY positions, confidence and explicit missing samples | The implemented tracker is FFmpeg template correlation. It is a bounded translation tracker, separately named and tested. |

### SAM 2: correction state is part of the editing model

`init_state` retains original video dimensions, frames, offload settings, object-ID mappings and per-object conditioning/non-conditioning outputs. `add_new_points_or_box` validates paired point/label input, handles box corners before points, converts coordinates using original width/height, and distinguishes initial prompts from corrections to already tracked frames. Prior mask logits can condition a correction. These details are visible in the inspected [predictor](https://github.com/facebookresearch/sam2/blob/main/sam2/sam2_video_predictor.py).

An implementation in CINEMATICUM would therefore need a versioned segmentation object with source hash, exact conformed frame mapping, model/config/checkpoint identity, object IDs, ordered edits and mask outputs. A UI click alone cannot be treated as a finished matte. Corrections must invalidate affected propagation/cache results. Existing ellipse/polygon nodes contain geometric coverage, not this prediction state. The [official repository](https://github.com/facebookresearch/sam2) supplies code, checkpoints and inference examples; this review did not run those models.

### TAPIR and TAPNext: coordinates and visibility must be explicit

The [TAPNet documentation](https://github.com/google-deepmind/tapnet/blob/main/README.md) distinguishes query `(t,y,x)` from output `(x,y)` and describes the point-tracking model families. The inspected TAPNext forward method tokenizes frames, combines image/query tokens and updates its recurrent cache and frame step. Its prediction heads return track coordinates, track logits and separate visibility logits; coordinates include a half-pixel offset. A generic adapter must specify batch/point/time axes, crop/resize mapping and pixel-center conventions rather than assuming all tensors are normalized XY.

CINEMATICUM now accepts an explicit point-track JSON format, but it does **not** accept arbitrary TAPIR/TAPNext tensors. A future model adapter must convert actual output and preserve visibility and model provenance. It must not fill occluded frames by pretending interpolation is a measurement. The current import validates source identity, contiguous sample times and bounded finite coordinates. It rejects a different source range, rate, speed, reverse state or clip identity.

### CameraCtrl: camera data is not a target/FOV animation preset

The inspected [dataset reader](https://github.com/hehao13/CameraCtrl/blob/main/cameractrl/data/dataset.py) extracts intrinsics and a 3×4 world-to-camera matrix, inverts that matrix, creates pixel-center rays, normalizes their directions, then forms moment/direction ray features. The [pose adapter](https://github.com/hehao13/CameraCtrl/blob/main/cameractrl/models/pose_adaptor.py) encodes these features and injects them into the diffusion network. The [official project](https://hehao13.github.io/projects-CameraCtrl/) describes the camera-controlled generation task.

CINEMATICUM's current authored camera has position, target and FOV in a Z-up scene. General camera data can additionally carry roll, an off-center principal point, distortion, distinct axis conventions and arbitrary scene scale. Those differences prevent a faithful universal CameraCtrl/COLMAP conversion from the current schema. CameraCtrl conditioning and COLMAP reconstruction must remain separate jobs, with explicit conversions and rendered geometric checks before either is marked available.

### ComfyUI: validate the installed graph and own the submitted job

The [official server routes](https://docs.comfy.org/development/comfyui-server/comms_routes) distinguish `/object_info`, `/prompt`, `/history/{prompt_id}`, `/view`, uploads and model discovery. The inspected current server source validates a prompt before queue admission and associates its ID with history. It also contains `/api/jobs/{job_id}/cancel`, which atomically acts only on the matching job. An older server may not expose that endpoint. A global `/interrupt` is not a safe substitute when another client can own the running job.

CINEMATICUM's existing local adapter imports API graphs, binds chosen prompt/negative/seed inputs, checks installed definitions and model choices, submits one graph, follows its own prompt ID, and only admits a downloaded, probed video. Preflight errors identify missing nodes/models; they are not replaced by fabricated takes. The current Mac check found no ComfyUI service listening on the configured loopback endpoint. Fixture protocol tests verify requests and output admission, but cannot establish real model execution. Paid provider integrations, SAM 2, TAPIR/TAPNext and CameraCtrl workers remain separate missing capabilities.

## Implemented measured-motion contract

The new `tracking.py` extracts a seed frame using the same trim, speed, reverse and exact rational project clock used by export. Analysis is bounded to 480 output frames and a 384-pixel maximum edge. It crops an explicitly selected grayscale patch and runs FFmpeg `find_rect`. The filter uses a normalized correlation score, including absolute correlation; confidence is not a calibrated probability of visibility. Low-contrast seeds and ambiguous initial matches are rejected. Every requested frame must produce an explicit record; missing detections remain invisible samples.

```json
{
  "version": 1,
  "kind": "point-track",
  "backend": "ffmpeg-template-correlation",
  "coordinates": "normalized-source-xy-top-left",
  "source": {
    "asset_id": "imported-asset-id",
    "sha256": "actual-media-sha256",
    "width": 1920,
    "height": 1080,
    "clip_id": "selected-clip-id",
    "in": 0,
    "duration": 48,
    "speed": 1,
    "reverse": false,
    "animation_offset": 0,
    "frame_rate": {"numerator": 24, "denominator": 1}
  },
  "reference_frame": 0,
  "samples": [
    {"frame": 0, "x": 0.5, "y": 0.5, "visible": true, "confidence": 1},
    {"frame": 1, "x": null, "y": null, "visible": false, "confidence": 0}
  ]
}
```

This example describes the schema; it is not a measured take. Actual exported receipts contain actual file identity and measured samples. Coordinates refer to the conformed source image before clip transforms and node processing; moving the clip on the timeline does not change them. Changing source timing does.

Stabilization computes the negative displacement relative to the chosen reference. Time-parametrized simplification limits interpolation error to half a source pixel at measured frames and rejects trajectories needing more than 128 keys. It refuses any missing point. The resulting independent `clip.tracking` channel adds transformed displacement without replacing authored position, scale, rotation, opacity or audio automation. Keys clamp outside the measured interval. Applying it is one undoable edit; removing it preserves manual motion.

Creating a tracked mask adds a new animated ellipse to the clip's compositor, with independent X/Y channels derived from the same measurements. It does not overwrite another mask's animation. This is rigid center following, not deforming object segmentation. Split/trim preserve the animation domain; changing speed rescales measured and compositor key times with the other clip animation channels. The native UI exposes the real seed image, measured path, gaps, range, radius and tolerance, plus import/export of track JSON. Each asynchronous measurement owns its cancellation and rejects stale UI completion.

## Acceptance and known limits

`test_tracking.py` uses actual translating textured frames, measures them, renders stabilization, then measures the resulting movie independently. It also checks missing visibility, source mismatch, malformed samples and cancellation. `test_server.py` exercises real seed/measurement HTTP jobs without saving the unsaved project. `test_tracking_ui_macos.py` operates actual WK controls and independently reads the saved motion/mask recipe after undo, retime and split. `test_timebase.py` includes negative animation-domain and later-reference render checks, so no implicit frame-zero anchor changes a measured trajectory.

This remains a translation tracker with a small analysis image. It lacks affine/projective estimation, planar tracking, optical flow, lens solving, rolling-shutter compensation, re-identification and calibrated occlusion handling. A texture can produce a high but wrong correlation; visual review is still required. Stabilization does not auto-crop exposed borders. None of these remaining gaps is represented as an available SAM/TAPIR/CameraCtrl feature.
