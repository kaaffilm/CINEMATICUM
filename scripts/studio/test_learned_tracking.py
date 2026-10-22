"""Real checkpoint inference and editable source/timing binding acceptance.

The model gates require the explicitly installed optional runtime. With a
configured runtime, missing/tampered weights are failures, never substitutions
or silently skipped assertions. The fixture is geometric test data, not footage.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
import uuid

from engine import probe_media, render_project, validate_project
from learned_tracking import (ARTIFACT_NAMES, MAX_FRAMES, _digest, assert_learned_export_ready,
    find_learned_python, learned_capabilities, mask_application, point_application,
    run_learned_tracking, learned_frame, validate_learned_bindings, validate_recipe, validate_request,
    verify_learned_source_files)


def synthetic_motion(root, create=True):
    import numpy as np
    width, height, count = 256, 160, 10
    yy, xx = np.mgrid[:height, :width]
    background = np.stack([35 + (xx // 16) % 2 * 8, 47 + (yy // 16) % 2 * 8,
                           70 + (xx // 32 + yy // 32) % 2 * 9], axis=-1).astype(np.uint8)
    texture = np.random.default_rng(72351).integers(0, 256, (52, 52, 3), dtype=np.uint8)
    texture[:, :, 0] = 160 + texture[:, :, 0] // 3
    texture[:, :, 1] //= 3; texture[:, :, 2] //= 3
    frames, masks, centers = [], [], []
    for frame in range(count):
        center = (45 + frame * 14, 85)
        image = background.copy()
        mask = (xx - center[0]) ** 2 + (yy - center[1]) ** 2 <= 24 ** 2
        y0, x0 = center[1] - 26, center[0] - 26
        region = image[y0:y0+52, x0:x0+52]
        local = mask[y0:y0+52, x0:x0+52]
        region[local] = texture[local]
        occluder = (xx >= 89) & (xx <= 132) & (yy >= 42) & (yy <= 124)
        image[occluder] = [172, 185, 198]
        mask &= ~occluder
        frames.append(image); masks.append(mask); centers.append(center)
    source = Path(root) / "media" / "SYNTHETIC_LEARNED_OCCLUSION.mkv"
    source.parent.mkdir(parents=True, exist_ok=True)
    if create:
        if source.exists(): raise ValueError("An existing source fixture must remain immutable")
        subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{width}x{height}", "-r", "12", "-i", "pipe:0", "-an", "-c:v", "ffv1", "-level", "3",
            "-pix_fmt", "bgr0", "-threads", "1", str(source)], input=np.stack(frames).tobytes(), capture_output=True, check=True, timeout=20)
    else:
        decoded=subprocess.run([shutil.which("ffmpeg"),"-v","error","-i",str(source),"-threads","1","-pix_fmt","rgb24","-f","rawvideo","pipe:1"],
                               capture_output=True,check=True,timeout=20).stdout
        if decoded != np.stack(frames).tobytes(): raise ValueError("The retained source fixture changed its actual frames")
    asset = {"id": "original", "name": "Synthetic moving disk and foreground occluder", "path": str(source.relative_to(root)),
             "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), **probe_media(source)}
    project = {"version": 1, "id": "learned_test", "name": "Learned engine acceptance fixture", "fps": 12,
               "width": width, "height": height, "assets": [asset], "titles": [],
               "clips": [{"id": "picture", "asset_id": "original", "track": 0, "start": 0, "in": 0, "duration": count}],
               "settings": {"image_precision": "high16", "transparent_background": True}}
    return validate_project(project, root), np.stack(frames), np.stack(masks), centers


def sam_recipe():
    return {"version": 1, "backend": "sam2", "frame_start": 0, "frame_count": 10,
            "prompts": [{"frame": 0, "points": [{"x": 45/256, "y": 85/160, "label": 1}],
                         "box": [20/256, 60/160, 70/256, 110/160]}]}


def tap_recipe():
    return {"version": 1, "backend": "tapir", "frame_start": 0, "frame_count": 10,
            "points": [{"id": "disk_center", "frame": 0, "x": 45/256, "y": 85/160}]}


class LearnedRecipeTests(unittest.TestCase):
    def test_real_javascript_roundtrip_preserves_motion_binding_but_semantic_edits_stale(self):
        # A numeric transport regression, not a substitute inference fixture:
        # JavaScript serializes Python's exact0.0/1.0 JSON values as0/1. The
        # original source and every numerical trajectory value stay identical.
        from tracking import validate_motion
        asset = {"id": "original", "kind": "video", "sha256": "a" * 64,
                 "width": 100, "height": 100, "video_stream_index": 0}
        identity = {"asset_id": "original", "sha256": asset["sha256"], "width": 100, "height": 100,
                    "clip_id": "picture", "in": 0.0, "duration": 3, "speed": 1.0,
                    "reverse": False, "animation_offset": 0, "frame_rate": {"numerator": 12, "denominator": 1}}
        motion = {"version": 1, "mode": "stabilize",
                  "keys": [{"frame": index, "x": index * .25, "y": 0.0, "interpolation": "linear"} for index in range(3)],
                  "source": {"track_backend": "tapir-pytorch-panning", "reference_frame": 0,
                    "reference_point": [0.0, 1.0], "source": copy.deepcopy(identity), "max_simplification_error_pixels": .5,
                    "track_sha256": "b" * 64, "learned_result_sha256": "c" * 64,
                    "learned_corrections": [{"frame": 1, "x": 1.0, "y": 0.0}]}}
        binding = {"version": 1, "backend": "tapir", "source": identity,
                   "source_stream": {"kind": "video", "video_stream_index": 0, "width": 100, "height": 100, "rotation": 0, "exif_orientation": 1},
                   "recipe_sha256": "d" * 64, "result_sha256": "c" * 64, "checkpoint_sha256": "e" * 64,
                   "frame_start": 0, "frame_count": 3,
                   "target": {"kind": "tracking-motion", "motion_sha256": _digest(motion), "point_id": "center"}}
        clip = {"id": "picture", "asset_id": "original", "start": 0, "in": 0.0, "duration": 3,
                "speed": 1.0, "reverse": False, "animation_offset": 0,
                "tracking": motion, "learned_bindings": [binding]}
        project = {"fps": 12, "assets": [asset], "clips": [clip]}
        encoded = subprocess.run(["node", "-e", "let s='';process.stdin.on('data',v=>s+=v);process.stdin.on('end',()=>process.stdout.write(JSON.stringify(JSON.parse(s))));"],
                                 input=json.dumps(project), capture_output=True, text=True, check=True, timeout=5)
        transported = json.loads(encoded.stdout); target = transported["clips"][0]
        self.assertIsInstance(target["tracking"]["source"]["source"]["in"], int)
        self.assertIsInstance(motion["source"]["source"]["in"], float)
        self.assertEqual(project, transported, "The actual JSON transport must preserve all numerical values")
        target["tracking"] = validate_motion(target["tracking"], 0, 3)
        normalized = validate_learned_bindings(target["learned_bindings"], transported, target, transported["assets"])
        self.assertNotIn("invalidated", normalized[0], "An actual browser save must not stale the unchanged measured motion")
        # Before canonical motion hashing, correction metadata preserved the
        # user's integer literals while generated motion keys were floats.
        # That valid older shape must also survive the same real JS transport.
        integer_authored = copy.deepcopy(project)
        integer_clip = integer_authored["clips"][0]
        integer_clip["tracking"]["source"]["learned_corrections"] = [{"frame": 1, "x": 1, "y": 0}]
        integer_clip["learned_bindings"][0]["target"]["motion_sha256"] = _digest(integer_clip["tracking"])
        encoded_integer = subprocess.run(["node", "-e", "let s='';process.stdin.on('data',v=>s+=v);process.stdin.on('end',()=>process.stdout.write(JSON.stringify(JSON.parse(s))));"],
                                         input=json.dumps(integer_authored), capture_output=True, text=True, check=True, timeout=5)
        integer_transported = json.loads(encoded_integer.stdout); integer_target = integer_transported["clips"][0]
        integer_target["tracking"] = validate_motion(integer_target["tracking"], 0, 3)
        integer_normalized = validate_learned_bindings(integer_target["learned_bindings"], integer_transported,
                                                     integer_target, integer_transported["assets"])
        self.assertNotIn("invalidated", integer_normalized[0], "Integer-authored legacy corrections must survive browser transport")
        self.assertEqual(integer_normalized[0]["target"]["motion_sha256"], normalized[0]["target"]["motion_sha256"])
        target["learned_bindings"] = normalized
        for mutation in ("key", "correction", "reference", "metadata", "boolean", "timing", "container"):
            changed = copy.deepcopy(transported); edited = changed["clips"][0]
            if mutation == "key": edited["tracking"]["keys"][1]["x"] += .0000000000000001
            if mutation == "correction": edited["tracking"]["source"]["learned_corrections"][0]["x"] = .9
            if mutation == "reference": edited["tracking"]["source"]["reference_point"][0] = .1
            if mutation == "metadata": edited["tracking"]["source"]["source"]["in"] = 1
            if mutation == "boolean": edited["tracking"]["source"]["learned_corrections"][0]["y"] = False
            if mutation == "timing": edited["reverse"] = True
            if mutation == "container": edited["tracking"]["source"]["learned_corrections"] = None
            with self.subTest(mutation=mutation):
                stale = validate_learned_bindings(normalized, changed, edited, changed["assets"])
                self.assertIn("invalidated", stale[0], "Transport normalization must not hide any semantic edit")
                restored = validate_learned_bindings(stale, transported, target, transported["assets"])
                self.assertNotIn("invalidated", restored[0], "Undo must restore the exact measured binding")
        # A legacy numeric field must not make distinct large integer values
        # collide through a lossy compatibility conversion to IEEE754.
        large = copy.deepcopy(transported); large_clip = large["clips"][0]
        large_clip["tracking"]["source"]["reference_point"][0] = float(2 ** 53)
        legacy = copy.deepcopy(normalized)
        legacy[0]["target"]["motion_sha256"] = _digest(large_clip["tracking"])
        large_clip["tracking"]["source"]["reference_point"][0] = 2 ** 53 + 1
        self.assertIn("invalidated", validate_learned_bindings(legacy, large, large_clip, large["assets"])[0])

    def test_prompts_and_query_frames_are_strict_and_canonical(self):
        recipe = sam_recipe(); recipe["prompts"].append({"frame": 7, "points": [{"x": .9, "y": .9, "label": 0}]})
        before = copy.deepcopy(recipe)
        self.assertEqual(validate_recipe(recipe), recipe)
        self.assertEqual(recipe, before)
        for mutation in ("range", "backend", "label", "extra", "box", "duplicate", "nonfinite"):
            value = copy.deepcopy(recipe)
            if mutation == "range": value["frame_count"] = MAX_FRAMES + 1
            if mutation == "backend": value["backend"] = "template-correlation"
            if mutation == "label": value["prompts"][0]["points"][0]["label"] = True
            if mutation == "extra": value["command"] = "external execution"
            if mutation == "box": value["prompts"][0]["box"][2] = 0
            if mutation == "duplicate": value["prompts"].append(copy.deepcopy(value["prompts"][0]))
            if mutation == "nonfinite": value["prompts"][0]["points"][0]["x"] = float("nan")
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): validate_recipe(value)
        query = tap_recipe(); query["points"][0]["frame"] = 10
        with self.assertRaises(ValueError): validate_recipe(query)

    def test_missing_checkpoint_runtime_is_explicitly_unavailable(self):
        result = learned_capabilities("/does/not/exist/learned/python")
        self.assertFalse(result["available"])
        self.assertIn("Install", result["reason"])


@unittest.skipUnless(find_learned_python() and shutil.which("ffmpeg"), "The explicit optional learned CPU runtime and actual model checkpoints are required")
class ActualLearnedInferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retained = os.environ.get("CINEMATICUM_LEARNED_TEST_EVIDENCE")
        cls.temporary = None if retained else tempfile.TemporaryDirectory(prefix="cinematicum-actual-learned-")
        cls.root = Path(retained).absolute() if retained else Path(cls.temporary.name)
        if retained: cls.root.mkdir(parents=True, exist_ok=False)
        cls.project, cls.frames, cls.oracle_masks, cls.centers = synthetic_motion(cls.root)
        cls.runtime = learned_capabilities()
        if not cls.runtime["available"]:
            raise AssertionError("Configured learned runtime failed: " + cls.runtime.get("reason", "unknown error"))
        cls.results = {}
        for backend, recipe in (("tapir", tap_recipe()), ("sam2", sam_recipe())):
            cls.results[backend] = run_learned_tracking(cls.project, cls.root, "picture", recipe,
                cls.root / "learned" / "outputs" / uuid.uuid4().hex)
            output_id = cls.results[backend]["output_id"]
            if list((cls.root / "learned" / "outputs").glob(f".learned-work-{output_id}-*")):
                raise AssertionError("Successful learned inference retained its private working directory")
        if retained:
            (cls.root / "actual-responses.json").write_text(json.dumps(cls.results,indent=2)+"\n")

    @classmethod
    def tearDownClass(cls):
        if cls.temporary is not None: cls.temporary.cleanup()

    def test_actual_tapir_trajectory_occlusion_and_reidentification(self):
        import numpy as np
        result = self.results["tapir"]["measurement"]
        measured = result["measurement"]
        self.assertEqual(measured["checkpoint_sha256"], "628611c656b3bd65d4a70fbf5526b62afe82d1b085ce6044685287fb78509daa")
        samples = measured["tracks"][0]["track"]["samples"]
        self.assertEqual([sample["visible"] for sample in samples], [True]*4 + [False]*3 + [True]*3)
        errors = [np.linalg.norm(np.array([sample["x"]*256, sample["y"]*160])-center)
                  for sample, center in zip(samples, self.centers) if sample["visible"]]
        self.assertLess(max(errors), 2, "Real learned visible trajectories must follow independent geometric centers")
        self.assertTrue(all(samples[index]["confidence"] < .01 for index in (4,5,6)))
        with self.assertRaisesRegex(ValueError, "loses"):
            point_application(self.project, self.root, "picture", result, "disk_center")
        corrections = [{"frame": index, "x": self.centers[index][0]/256, "y": self.centers[index][1]/160} for index in (4,5,6)]
        plan = point_application(self.project, self.root, "picture", result, "disk_center", corrections)
        self.assertEqual(plan["tracking"]["source"]["learned_corrections"], corrections)
        applied = copy.deepcopy(self.project); clip = applied["clips"][0]
        clip["tracking"] = plan["tracking"]; clip["learned_bindings"] = [plan["binding"]]
        clip["learned_bindings"] = validate_learned_bindings(clip["learned_bindings"], applied, clip, applied["assets"])
        assert_learned_export_ready(applied)
        verify_learned_source_files(applied, self.root)
        output = self.root / "stabilized.mkv"
        render_project(applied, self.root, output, "master16")
        self.assertTrue(output.stat().st_size > 1000)

    def test_actual_sam_mask_pixels_and_foreground_cutout_export(self):
        import numpy as np
        response = self.results["sam2"]; result = response["measurement"]
        self.assertEqual(result["measurement"]["checkpoint_sha256"], "7402e0d864fa82708a20fbd15bc84245c2f26dff0eb43a4b5b93452deb34be69")
        raw = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-i", str(self.root / response["mask_path"]),
            "-threads", "1", "-pix_fmt", "rgba", "-f", "rawvideo", "pipe:1"],capture_output=True,check=True,timeout=20).stdout
        masks = np.frombuffer(raw,dtype=np.uint8).reshape(10,160,256,4)
        self.assertTrue(np.all(masks[:,:,:,:3] == 255))
        self.assertEqual(set(np.unique(masks[:,:,:,3]).tolist()), {0,255})
        ious = []
        for index, oracle in enumerate(self.oracle_masks):
            actual = masks[index,:,:,3] > 0
            ious.append(float((actual & oracle).sum() / (actual | oracle).sum()))
            self.assertEqual(int(actual.sum()), result["measurement"]["mask_frames"][index]["foreground_pixels"])
        self.assertGreater(min(ious), .90, "Actual SAM propagation must preserve the independently known occluded object")
        (self.root/"sam-mask-oracle.json").write_text(json.dumps({"source":"independent disk/occluder geometry","ious":ious},indent=2)+"\n")
        mask_source = self.root / response["mask_path"]
        admitted = self.root / "media" / "learned_mask.mkv"; shutil.copyfile(mask_source, admitted)
        asset = {"id":"actual_sam_mask","name":"Accepted actual SAM2 mask","path":str(admitted.relative_to(self.root)),
                 "sha256":hashlib.sha256(admitted.read_bytes()).hexdigest(),"provenance":response["provenance"],**probe_media(admitted)}
        project = copy.deepcopy(self.project); project["assets"].append(asset)
        plan = mask_application(project,self.root,"picture",result,asset)
        clip=project["clips"][0];clip["compositor"]=plan["compositor"];clip["learned_bindings"]=[plan["binding"]]
        clip["learned_bindings"]=validate_learned_bindings(clip["learned_bindings"],project,clip,project["assets"])
        assert_learned_export_ready(project);verify_learned_source_files(project,self.root)
        output=self.root/"foreground_cutout.mkv";render_project(project,self.root,output,"master16")
        raw=subprocess.run([shutil.which("ffmpeg"),"-v","error","-nostdin","-i",str(output),"-threads","1",
            "-pix_fmt","rgba64le","-f","rawvideo","pipe:1"],capture_output=True,check=True,timeout=20).stdout
        cutout=np.frombuffer(raw,dtype='<u2').reshape(10,160,256,4)
        self.assertTrue(np.array_equal(cutout[:,:,:,3],masks[:,:,:,3].astype(np.uint16)*257))
        foreground=masks[:,:,:,3]>0
        self.assertLessEqual(int(np.max(np.abs(cutout[:,:,:,:3][foreground].astype(int)-self.frames[foreground].astype(int)*257))),257)

    def test_actual_single_image_sam_and_explicit_still_hold(self):
        import numpy as np
        original=self.root/"media"/"SYNTHETIC_STILL.png"
        subprocess.run([shutil.which("ffmpeg"),"-v","error","-y","-f","rawvideo","-pix_fmt","rgb24","-s","256x160",
            "-i","pipe:0","-frames:v","1","-threads","1",str(original)],input=self.frames[0].tobytes(),capture_output=True,check=True,timeout=15)
        source={"id":"still","name":"Synthetic still object","path":str(original.relative_to(self.root)),
                "sha256":hashlib.sha256(original.read_bytes()).hexdigest(),**probe_media(original)}
        project=copy.deepcopy(self.project);project["assets"]=[source];project["clips"][0].update(asset_id="still",duration=6)
        project=validate_project(project,self.root)
        recipe=sam_recipe();recipe["frame_start"]=2;recipe["frame_count"]=1;recipe["prompts"][0]["frame"]=2
        seed=self.root/"analysis"/(uuid.uuid4().hex+".png")
        seeded=learned_frame(project,self.root,"picture",{"frame_start":2,"frame_count":1},seed)
        self.assertEqual(seeded["source_stream"]["kind"],"image")
        with self.assertRaisesRegex(ValueError,"real video"):
            validate_request(project,self.root,"picture",{**tap_recipe(),"frame_count":1})
        response=run_learned_tracking(project,self.root,"picture",recipe,self.root/"learned"/"outputs"/uuid.uuid4().hex)
        self.assertEqual(response["measurement"]["source_stream"]["kind"],"image")
        mask=self.root/response["mask_path"];admitted=self.root/"media"/"still_mask.mkv";shutil.copyfile(mask,admitted)
        asset={"id":"still_mask","name":"Actual still SAM2 alpha","path":str(admitted.relative_to(self.root)),
               "sha256":hashlib.sha256(admitted.read_bytes()).hexdigest(),"provenance":response["provenance"],**probe_media(admitted)}
        project["assets"].append(asset)
        plan=mask_application(project,self.root,"picture",response["measurement"],asset,hold_still=True)
        self.assertTrue(plan["binding"]["target"]["hold_still"])
        project["clips"][0].update(compositor=plan["compositor"],learned_bindings=[plan["binding"]])
        output=self.root/"still-held-cutout.mkv";render_project(project,self.root,output,"master16")
        raw=subprocess.run([shutil.which("ffmpeg"),"-v","error","-i",str(output),"-vf","alphaextract",
            "-threads","1","-pix_fmt","gray16le","-f","rawvideo","pipe:1"],capture_output=True,check=True,timeout=15).stdout
        alpha=np.frombuffer(raw,dtype='<u2').reshape(6,160,256)
        self.assertTrue(all(np.array_equal(frame,alpha[0]) for frame in alpha))
        actual=alpha[0]>0;oracle=self.oracle_masks[0]
        self.assertGreater(float((actual&oracle).sum()/(actual|oracle).sum()),.95)
        self.assertEqual(set(np.unique(alpha).tolist()),{0,65535})

    def test_actual_tapir_reverse_window_tracks_the_real_selected_frames(self):
        import numpy as np
        project=copy.deepcopy(self.project);project["clips"][0]["reverse"]=True
        recipe=tap_recipe();recipe.update(frame_start=1,frame_count=8)
        recipe["points"][0].update(frame=1,x=self.centers[8][0]/256)
        response=run_learned_tracking(project,self.root,"picture",recipe,self.root/"learned"/"outputs"/uuid.uuid4().hex)
        result=response["measurement"];self.assertTrue(result["source"]["reverse"])
        samples=result["measurement"]["tracks"][0]["track"]["samples"]
        self.assertEqual([sample["frame"] for sample in samples],list(range(1,9)))
        errors=[]
        for sample,center in zip(samples,self.centers[8:0:-1]):
            if sample["visible"]:errors.append(float(np.linalg.norm(np.array([sample["x"]*256,sample["y"]*160])-center)))
        self.assertGreaterEqual(len(errors),5)
        self.assertLess(max(errors),2)

    def test_timing_source_and_target_edits_invalidate_then_undo_restores(self):
        result=self.results["tapir"]["measurement"]
        plan=point_application(self.project,self.root,"picture",result,"disk_center",frame_start=0,frame_count=4)
        project=copy.deepcopy(self.project);clip=project["clips"][0];clip["tracking"]=plan["tracking"]
        original=copy.deepcopy(clip)
        for field,value in (("in",1),("speed",2),("reverse",True),("duration",9),("animation_offset",1)):
            changed=copy.deepcopy(project);target=changed["clips"][0];target[field]=value
            bindings=validate_learned_bindings([plan["binding"]],changed,target,changed["assets"])
            self.assertTrue(bindings[0].get("invalidated"),field)
            target["learned_bindings"]=bindings
            with self.assertRaisesRegex(ValueError,"stale"):assert_learned_export_ready(changed)
            restored=validate_learned_bindings(bindings,project,original,project["assets"])
            self.assertNotIn("invalidated",restored[0])
        moved=copy.deepcopy(project);moved["clips"][0]["start"]=12
        self.assertNotIn("invalidated",validate_learned_bindings([plan["binding"]],moved,moved["clips"][0],moved["assets"])[0])
        changed=copy.deepcopy(project);changed["clips"][0]["tracking"]["keys"][0]["x"]+=.1
        self.assertIn("invalidated",validate_learned_bindings([plan["binding"]],changed,changed["clips"][0],changed["assets"])[0])

    def test_owned_model_cancellation_does_not_publish_partial_artifacts(self):
        # Use a distinct project: another owned model job is allowed to have
        # its own active work directory while this job is cancelled.
        with tempfile.TemporaryDirectory(prefix="learned-cancel-",dir=self.root) as temporary:
            root=Path(temporary);project,*_=synthetic_motion(root)
            event=threading.Event(); output=root/"learned"/"outputs"/uuid.uuid4().hex
            stages=[]
            def progress(value):
                stages.append(value)
                if value>=.23:event.set()
            with self.assertRaisesRegex(RuntimeError,"cancelled"):
                run_learned_tracking(project,root,"picture",sam_recipe(),output,progress=progress,cancel_event=event)
            self.assertTrue(event.is_set());self.assertGreater(max(stages),.2)
            self.assertFalse(output.exists())
            self.assertFalse(list(output.parent.glob(f'.learned-work-{output.name}-*')))
            source=root/project["assets"][0]["path"]
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),project["assets"][0]["sha256"])

    def test_receipts_bind_actual_artifacts_and_explicit_model_identity(self):
        for response in self.results.values():
            receipt=json.loads((self.root/response["receipt_path"]).read_text())
            result=json.loads((self.root/response["result_path"]).read_text())
            self.assertEqual(receipt["result_sha256"],_digest(result))
            self.assertEqual(receipt["recipe_sha256"],_digest(result["recipe"]))
            output=(self.root/response["result_path"]).parent
            self.assertTrue({path.name for path in output.iterdir()}<=ARTIFACT_NAMES)
            for record in receipt["artifacts"]:
                data=(output/record["filename"]).read_bytes()
                self.assertEqual((hashlib.sha256(data).hexdigest(),len(data)),(record["sha256"],record["size"]))


if __name__=="__main__":unittest.main()
