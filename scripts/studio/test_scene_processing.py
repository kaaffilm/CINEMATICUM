"""Pure graph semantics plus actual pinned-TLS/Cycles distributed acceptance.

These tests require an actual Blender, FFmpeg/ffprobe and OpenSSL on PATH.
Missing engines fail explicitly; no mocked renderers, transports or skip-based
acceptance is used. Rendered pictures are synthetic ENGINE TEST scenes.
"""
from concurrent.futures import ThreadPoolExecutor
import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile

from adapters import find_blender
from collaboration import CollaborationError, _certificate
from scene import default_scene, validate_scene, object_matrix_at
from scene_hierarchy import transform_point
from scene_modeling import primitive_cage
import scene_processing as graph
import scene_dispatch as dispatch


def fixture(width=64, height=48, animated=False):
    scene = default_scene(width, height)
    scene.update(frame_end=3, samples=4)
    scene["render"]["use_denoising"] = False
    scene["camera"].update(position=[0, -7, 2], target=[0, 0, 0], fov=40)
    scene["world"].update(color="#000000", strength=0.)
    scene["lights"] = []
    obj = {"id": "box", "name": "ENGINE TEST box", "type": "cube", "position": [0, 0, 0],
           "rotation": [0, 0, 0], "scale": [.5, .5, .5],
           "material": {"color": "#ff2020", "roughness": 1, "emission_color": "#ff2020", "emission_strength": 1}}
    if animated:
        obj["keyframes"] = [{"frame": frame, "position": [position, 0, 0], "rotation": [0, 0, 0], "scale": [.5, .5, .5]}
                            for frame, position in ((1, -1.), (3, 1.))]
    scene["objects"] = [obj]
    return graph.default_scene_graph(validate_scene(scene))


def add(document, operation, input_id=None, ident=None, **values):
    ident = ident or "n" + str(len(document["nodes"]))
    node = {"id": ident, "op": operation, **values}
    if input_id is not None: node["input"] = input_id
    elif operation not in {"source", "merge", "variant"}: node["input"] = document["output"]
    document["nodes"].append(node); document["output"] = ident
    return ident


def objects(evaluation):
    return {item["path"]: item for item in evaluation["locations"] if item["kind"] == "object"}


def read_frames(path, width=64, height=48):
    result = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-i", str(path),
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-threads", "1", "-"], capture_output=True, timeout=30, check=True)
    size = width * height * 3
    if len(result.stdout) % size: raise AssertionError("Actual decoded video has a partial frame.")
    return [result.stdout[index:index + size] for index in range(0, len(result.stdout), size)]


def red_center(frame, width=64):
    indices = [index for index in range(len(frame) // 3)
               if frame[index * 3] > 90 and frame[index * 3] > 2 * frame[index * 3 + 1] and frame[index * 3] > 2 * frame[index * 3 + 2]]
    if not indices: raise AssertionError("Real Cycles output contains no expected red geometry.")
    return sum(index % width for index in indices) / len(indices)


class SceneGraphSemanticsTests(unittest.TestCase):
    def test_sources_have_absolute_paths_sets_and_queryable_children(self):
        source = fixture()
        evaluated = graph.evaluate_scene_graph(source)
        self.assertEqual(["/world/objects/box"], evaluated["sets"]["__objects"])
        query = graph.query_scene(evaluated, "/world", "__objects | __cameras")
        self.assertEqual(["/world/camera", "/world/objects"], query["children"])
        self.assertEqual(["/world/camera", "/world/objects/box"], query["matches"])
        self.assertEqual(["/world"], graph.query_scene(evaluated)["children"])
        self.assertEqual(source, json.loads(json.dumps(source)))

    def test_contexts_are_typed_with_derived_time_and_no_undeclared_variables(self):
        source = fixture()
        source["context"].update(shot={"type": "string", "default": "A"}, count={"type": "int", "default": 2, "min": 1, "max": 4},
                                 enabled={"type": "bool", "default": True}, offset={"type": "vector3", "default": [0, 0, 0]})
        ctx = graph.evaluate_scene_graph(source, {"frame": 12, "fps": 24, "count": 3})["context"]
        self.assertEqual(.5, ctx["time"]); self.assertIs(type(ctx["count"]), int)
        for bad in ({"time": 1}, {"unknown": 3}, {"count": 2.5}, {"count": True}, {"enabled": 1}, {"offset": [1, 2]}, {"fps": 0}):
            with self.subTest(bad=bad), self.assertRaises(ValueError): graph.evaluate_scene_graph(source, bad)

    def test_context_nodes_change_only_their_upstream_branch_and_input_is_immutable(self):
        source = fixture(animated=True)
        left = add(source, "context", "source", ident="early", values={"frame": 1})
        left = add(source, "group", left, ident="left", prefix="/left")
        right = add(source, "context", "source", ident="late", values={"frame": 3})
        right = add(source, "group", right, ident="right", prefix="/right")
        add(source, "merge", ident="merge", inputs=[left, right])
        before = copy.deepcopy(source)
        evaluated = graph.evaluate_scene_graph(source, {"frame": 2})
        positions = {path: item["world_transform"][12] for path, item in objects(evaluated).items()}
        self.assertEqual({"/left/world/objects/box": -1., "/right/world/objects/box": 1.}, positions)
        self.assertEqual(2, evaluated["context"]["frame"])
        self.assertEqual(before, source)
        evaluated["locations"][0]["attributes"]["touched"] = True
        self.assertNotIn("touched", graph.evaluate_scene_graph(source)["locations"][0]["attributes"])

    def test_time_warp_samples_actual_eased_animation_and_subframes(self):
        source = fixture(animated=True)
        source["assets"][0]["scene"]["objects"][0]["keyframes"][0]["interpolation"] = "ease_in"
        add(source, "time_warp", scale=2, offset=-1)
        result = graph.compile_scene_graph(source, {"frame": 1.5})
        self.assertAlmostEqual(-.5, result["scene"]["objects"][0]["position"][0])
        self.assertEqual(1.5, result["evaluation"]["context"]["frame"])
        upstream = next(x for x in result["evaluation"]["trace"] if x["op"] == "source")
        self.assertEqual(2., upstream["context"]["frame"])

    def test_set_algebra_filters_paths_and_preserves_named_membership_through_groups(self):
        source = fixture()
        add(source, "set", name="hero", filter={"paths": ["/world/objects/*"]})
        add(source, "set", name="all_visible", filter={"sets": "__objects | __cameras"})
        add(source, "group", prefix="/shot")
        result = graph.evaluate_scene_graph(source)
        self.assertEqual(["/shot/world/objects/box"], result["sets"]["hero"])
        self.assertEqual({"/shot/world/camera"}, graph.set_expression("(all_visible - hero) & __cameras", result["sets"]))
        self.assertEqual({"/shot/world/objects/box"}, graph.set_expression("hero | __lights & __objects", result["sets"]))
        with self.assertRaisesRegex(ValueError, "Unknown scene set"): graph.set_expression("missing", result["sets"])

    def test_recursive_patterns_and_descendants_are_explicit(self):
        source = fixture()
        add(source, "set", name="deep", filter={"paths": ["/world/**/box"]})
        add(source, "set", name="one_level", filter={"paths": ["/world/*"]})
        add(source, "set", name="subtree", filter={"paths": ["/world/objects"], "descendants": True})
        result = graph.evaluate_scene_graph(source)
        self.assertEqual(["/world/objects/box"], result["sets"]["deep"])
        self.assertNotIn("/world/objects/box", result["sets"]["one_level"])
        self.assertEqual(["/world/objects", "/world/objects/box"], result["sets"]["subtree"])

    def test_real_affine_shear_is_baked_without_loss_of_world_geometry(self):
        source = fixture()
        source["assets"][0]["scene"]["objects"][0]["rotation"] = [0, 0, 35]
        add(source, "transform", filter={"paths": ["/world/objects"]}, transform={"scale": [2, 1, 1]})
        compiled = graph.compile_scene_graph(source)
        self.assertEqual(1, len(compiled["baked_transforms"]))
        actual = compiled["scene"]["objects"][0]
        self.assertEqual("mesh", actual["type"])
        matrix = objects(compiled["evaluation"])["/world/objects/box"]["world_transform"]
        points, _ = primitive_cage("cube")
        for expected, found in zip((transform_point(matrix, point) for point in points), actual["mesh"]["vertices"]):
            for a, b in zip(expected, found): self.assertAlmostEqual(a, b, places=10)

    def test_original_parented_object_world_matrices_are_preserved(self):
        source = fixture()
        scene = source["assets"][0]["scene"]
        child = copy.deepcopy(scene["objects"][0]); child.update(id="child", parent_id="box", position=[1, .5, 0], rotation=[0, 0, 45])
        scene["objects"][0]["scale"] = [2, 1, 1]; scene["objects"].append(child)
        scene = validate_scene(scene); source["assets"][0]["scene"] = scene
        result = graph.evaluate_scene_graph(source)
        matrix = objects(result)["/world/objects/box/child"]["world_transform"]
        for a, b in zip(matrix, object_matrix_at(scene, "child", 1)): self.assertAlmostEqual(a, b)

    def test_camera_uniform_group_transform_retains_aim_and_roll(self):
        source = fixture()
        source["assets"][0]["scene"]["camera"]["roll"] = 25
        add(source, "group", prefix="/assembly", transform={"position": [1, 2, 3], "rotation": [15, 25, 35], "scale": [2, 2, 2]})
        compiled = graph.compile_scene_graph(source)
        camera = next(x for x in compiled["evaluation"]["locations"] if x["kind"] == "camera")
        for key in ("position", "target"):
            expected = transform_point(camera["world_transform"], camera["camera"][key])
            for a, b in zip(expected, compiled["scene"]["camera"][key]): self.assertAlmostEqual(a, b)
        source["nodes"][-1]["transform"]["scale"] = [2, 1, 1]
        with self.assertRaisesRegex(ValueError, "uniform-scale"): graph.compile_scene_graph(source)

    def test_attribute_inheritance_and_prune_remove_render_geometry_and_sets(self):
        source = fixture()
        add(source, "set", name="hero", filter={"sets": "__objects"})
        hidden = add(source, "attributes", filter={"paths": ["/world/objects"]}, values={"visibility": False, "asset_role": "hero"})
        compiled = graph.compile_scene_graph(source)
        self.assertEqual([], compiled["scene"]["objects"])
        self.assertEqual("hero", objects(compiled["evaluation"])["/world/objects/box"]["inherited_attributes"]["asset_role"])
        add(source, "prune", input_id=hidden, filter={"paths": ["/world/objects"]})
        evaluated = graph.evaluate_scene_graph(source)
        self.assertEqual([], evaluated["sets"]["hero"])
        self.assertFalse(objects(evaluated))

    def test_variants_are_named_deterministic_and_independent_of_input_order(self):
        source = fixture()
        source["context"]["seed"] = {"type": "int", "default": 4}
        red = add(source, "material", "source", ident="red", filter={"sets": "__objects"}, values={"color": "#ff0000"})
        blue = add(source, "material", "source", ident="blue", filter={"sets": "__objects"}, values={"color": "#0000ff"})
        add(source, "variant", ident="variant", mode="hash", seed={"context": "seed"}, key="/asset", choices=[{"name": "red", "input": red}, {"name": "blue", "input": blue}])
        def choose(seed): return graph.compile_scene_graph(source, {"seed": seed})["scene"]["objects"][0]["material"]["color"]
        with ThreadPoolExecutor(max_workers=8) as pool: first = list(pool.map(choose, range(32)))
        self.assertEqual({"#ff0000", "#0000ff"}, set(first))
        source["nodes"][-1]["choices"].reverse()
        with ThreadPoolExecutor(max_workers=8) as pool: second = list(pool.map(choose, range(32)))
        self.assertEqual(first, second)
        source["nodes"][-1] = {"id": "variant", "op": "variant", "mode": "select", "selector": "blue", "choices": source["nodes"][-1]["choices"]}
        self.assertEqual("#0000ff", choose(999))

    def test_context_expressions_are_data_only_and_reject_undefined_math(self):
        source = fixture()
        source["context"]["offset"] = {"type": "float", "default": 2}
        add(source, "transform", filter={"sets": "__objects"}, transform={"position": [{"op": "multiply", "args": [{"context": "offset"}, 3]}, 0, 0]})
        self.assertEqual(3., graph.compile_scene_graph(source)["scene"]["objects"][0]["position"][0])  # .5 local object scale
        source["nodes"][-1]["transform"]["position"][0] = {"op": "divide", "args": [1, 0]}
        with self.assertRaisesRegex(ValueError, "division by zero"): graph.compile_scene_graph(source)
        for value in ({"python": "os.system('echo unsafe')"}, {"context": "undeclared"}, {"op": "exec", "args": ["x"]}):
            source["nodes"][-1]["transform"]["position"][0] = value
            with self.subTest(value=value), self.assertRaises(ValueError): graph.validate_scene_graph(source)

    def test_numeric_context_equality_does_not_confuse_integers_floats_or_booleans(self):
        source = fixture(); source["context"]["count"] = {"type": "int", "default": 1}
        add(source, "material", filter={"sets": "__objects"}, values={"color": {"op": "if", "args": [
            {"op": "equal", "args": [{"context": "count"}, 1]}, "#00ff00", "#ff0000"]}})
        self.assertEqual("#00ff00", graph.compile_scene_graph(source)["scene"]["objects"][0]["material"]["color"])
        self.assertEqual("#ff0000", graph.compile_scene_graph(source, {"count": 2})["scene"]["objects"][0]["material"]["color"])
        source["nodes"][-1]["values"]["color"]["args"][0]["args"] = [True, 1]
        self.assertEqual("#ff0000", graph.compile_scene_graph(source)["scene"]["objects"][0]["material"]["color"])

    def test_cycles_dangling_nodes_and_colliding_scene_paths_fail_explicitly(self):
        source = fixture()
        add(source, "context", input_id="missing", values={"frame": 1})
        with self.assertRaisesRegex(ValueError, "missing node"): graph.validate_scene_graph(source)
        source["nodes"][-1]["input"] = source["nodes"][-1]["id"]
        with self.assertRaisesRegex(ValueError, "cycle"): graph.validate_scene_graph(source)
        source = fixture(); other = add(source, "source", asset="main", root="/world"); add(source, "merge", inputs=["source", other])
        with self.assertRaisesRegex(ValueError, "paths collide"): graph.evaluate_scene_graph(source)

    def test_depth_bounds_cannot_be_bypassed_by_topological_node_order(self):
        source = fixture()
        for index in range(32): add(source, "context", values={"frame": 1})
        for order in (source["nodes"], list(reversed(source["nodes"]))):
            source["nodes"] = order
            with self.assertRaisesRegex(ValueError, "32 upstream"): graph.validate_scene_graph(source)

    def test_strict_paths_types_filters_and_materials_reject_unsupported_inputs(self):
        for path in ("relative", "/a/../b", "/a//b", "/a/", "/a\\b", "/$HOME", "/a/**x"):
            with self.subTest(path=path), self.assertRaises(ValueError): graph.validate_path(path, pattern=True)
        source = fixture()
        for node in ({"id": "bad", "op": []}, {"id": "bad", "op": "source", "asset": []},
                     {"id": "bad", "op": "merge", "inputs": [[], []]}, {"id": "bad", "op": "source", "asset": "main", "filename": "/tmp/file"}):
            with self.subTest(node=node), self.assertRaises(ValueError): graph.validate_scene_graph({**source, "nodes": [*source["nodes"], node]})
        add(source, "material", filter={"sets": "__objects"}, values={"roughness": 2})
        with self.assertRaises(ValueError): graph.compile_scene_graph(source)
        for expression in ("hero |", "(hero", "hero;system", "__import__('os')"):
            with self.subTest(expression=expression), self.assertRaises(ValueError): graph.set_expression(expression, {"hero": []})

    def test_graph_hash_and_canonical_roundtrip_do_not_depend_on_global_state(self):
        source = fixture(animated=True); normalized = graph.validate_scene_graph(source)
        first = graph.compile_scene_graph(normalized, {"frame": 2})
        again = graph.compile_scene_graph(json.loads(graph.canonical_bytes(normalized)), {"frame": 2})
        self.assertEqual(first, again)
        code = "import sys,json;sys.path.insert(0,sys.argv[1]);import scene_processing as s;print(s.compile_scene_graph(json.load(sys.stdin),{'frame':2})['scene_sha256'])"
        process = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(Path(__file__).parent)], input=graph.canonical_bytes(normalized), capture_output=True, check=True, timeout=15)
        self.assertEqual(first["scene_sha256"], process.stdout.decode().strip())


class ActualSceneDispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not find_blender() or not shutil.which("ffmpeg") or not shutil.which("ffprobe") or not shutil.which("openssl"):
            raise RuntimeError("Actual scene-processing acceptance requires Blender, FFmpeg, ffprobe and OpenSSL; skipping is not acceptance.")
        version = subprocess.run([str(find_blender()), "--version"], capture_output=True, text=True, check=True, timeout=20)
        if not version.stdout.startswith("Blender "): raise RuntimeError("The configured Blender executable is not an actual upstream renderer.")
        cls.seed = tempfile.TemporaryDirectory(prefix="scene-TLS-certificates-")
        for index in range(2):
            worker = dispatch.RenderWorker(Path(cls.seed.name) / str(index)); _certificate(worker); worker.close()

    @classmethod
    def tearDownClass(cls): cls.seed.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cinematicum-SCENE-ENGINE-TEST-")
        self.root = Path(self.temporary.name).resolve(); self.services = []; self.workers = []
        self.bindings = {}

    def tearDown(self):
        for service in self.services:
            if service is not None: service.close()
        for worker in self.workers:
            if worker is not None: worker.close()
        self.temporary.cleanup()

    def worker(self, name="first", index=0, slots=1):
        worker = dispatch.RenderWorker(self.root / name, slots=slots)
        for filename in ("key.pem", "certificate.pem"):
            shutil.copyfile(Path(self.seed.name) / str(index) / "tls" / filename, worker.tls / filename)
        service = dispatch.start_render_worker(worker)
        binding = worker.pair_owner("ENGINE TEST owner")
        self.workers.append(worker); self.services.append(service); self.bindings[name] = binding
        return worker, service, dispatch.RenderClient(binding)

    def settle(self, client, job, timeout=35):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            report = client.job(job["id"])
            if report["status"] in dispatch.TERMINAL: return report
            time.sleep(.04)
        self.fail("Actual worker did not settle: " + json.dumps(client.job(job["id"])))

    def wait_engine(self, worker_root, job_id, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for path in (Path(worker_root) / "jobs" / job_id).rglob("*.log"):
                if path.is_file():
                    text = path.read_text(errors="replace")
                    if "Blender " in text and ("Fra:" in text or "Rendering" in text): return
            time.sleep(.02)
        self.fail("A real Blender render did not start before the acceptance deadline.")

    def heavy(self):
        source = fixture(1024, 768)
        source["assets"][0]["scene"]["samples"] = 256
        return source

    def test_local_graph_render_has_real_nonblank_pixels_blend_and_byte_receipts(self):
        source = fixture(animated=True)
        result = graph.run_scene_processing({"width": 64, "height": 48}, self.root,
            {"operation": "render", "graph": source, "context": {"frame": 1}}, self.root / "local")
        frames = read_frames(result["path"])
        self.assertEqual(1, len(frames)); self.assertLess(red_center(frames[0]), 30)
        self.assertEqual("Cycles CPU", result["receipt"]["renderer"]["renderer"])
        self.assertEqual(b"BLENDER", (self.root / "local/authored.blend").read_bytes()[:7])
        for item in result["receipt"]["artifacts"]:
            path = self.root / "local" / item["filename"]
            self.assertEqual(item["sha256"], graph._hash_file(path)); self.assertEqual(item["size"], path.stat().st_size)
        with self.assertRaises(ValueError): graph.run_scene_processing({"width": 64, "height": 48}, self.root, {"operation": "render", "graph": source}, self.root / "local")

    def test_authenticated_worker_executes_actual_scene_and_downloads_integrity_bound_media(self):
        worker, _, client = self.worker()
        request = dispatch.render_request(graph.compile_scene_graph(fixture(animated=True), {"frame": 3}))
        job = self.settle(client, client.submit_job(request, "real_render"))
        self.assertEqual("completed", job["status"], job.get("error"))
        self.assertEqual(request["scene_sha256"], job["result"]["receipt"]["scene_sha256"])
        self.assertTrue(job["result"]["receipt"]["engine_version"].startswith("Blender "))
        for record in job["result"]["artifacts"]:
            client.download_artifact(job["id"], record, self.root / "download" / record["filename"])
        self.assertGreater(red_center(read_frames(self.root / "download/preview.mp4")[0]), 34)
        self.assertEqual(job["result"]["receipt"], json.loads((self.root / "download/receipt.json").read_text()))
        self.assertNotIn("token", graph.canonical_bytes(job).decode())

    def test_two_actual_workers_render_concurrently_and_assemble_exact_ordered_frames(self):
        self.worker("first", 0); self.worker("second", 1)
        owner = dispatch.Dispatcher(self.root / "dispatch", self.bindings)
        batch = owner.submit(fixture(animated=True), frames=[1, 3], operation_id="two_workers")
        result = owner.run(batch["id"], self.root / "published")
        self.assertEqual(2, result["receipt"]["worker_count"])
        frames = read_frames(result["path"])
        self.assertEqual(2, len(frames)); self.assertLess(red_center(frames[0]), red_center(frames[1]) - 8)
        status = owner.status(batch["id"])
        executions = [item["report"]["result"]["receipt"]["execution"] for item in status["tasks"]]
        self.assertLess(max(item["started"] for item in executions), min(item["finished"] for item in executions), "Actual Cycles task intervals on this same host did not overlap.")
        with zipfile.ZipFile(self.root / "published/tasks.zip") as archive:
            for index, task in enumerate(status["tasks"]):
                for record in task["report"]["result"]["artifacts"]:
                    data = archive.read("task-%04d/" % index + record["filename"])
                    self.assertEqual(record["sha256"], hashlib.sha256(data).hexdigest())
                    self.assertEqual(record["size"], len(data))
        for binding in self.bindings.values():
            self.assertNotIn(binding["token"].encode(), (self.root / "published/dispatch.json").read_bytes())

    def test_submission_retry_is_idempotent_under_real_concurrent_clients(self):
        worker, _, client = self.worker(slots=1)
        request = dispatch.render_request(graph.compile_scene_graph(fixture()))
        with ThreadPoolExecutor(max_workers=6) as pool:
            jobs = list(pool.map(lambda _: dispatch.RenderClient(client.binding).submit_job(request, "same_operation"), range(6)))
        self.assertEqual(1, len({j["id"] for j in jobs}))
        completed = self.settle(client, jobs[0]); self.assertEqual("completed", completed["status"], completed.get("error"))
        self.assertEqual(1, completed["attempt"])
        with worker._db() as db: self.assertEqual(1, db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])
        other = dispatch.render_request(graph.compile_scene_graph(fixture(animated=True), {"frame": 3}))
        with self.assertRaisesRegex(CollaborationError, "already used"): client.submit_job(other, "same_operation")
        self.assertEqual(completed["id"], client.operation("same_operation")["id"])
        self.assertIsNone(client.operation("never_submitted"))

    def test_tls_pairing_is_one_use_pinned_authenticated_and_job_scoped(self):
        _, _, alice = self.worker()
        invitation = alice.invite()
        bob = dispatch.RenderClient(dispatch.RenderClient.join(invitation, "ENGINE TEST peer"))
        with self.assertRaises(CollaborationError): dispatch.RenderClient.join(invitation, "Reused")
        job = alice.submit_job(dispatch.render_request(graph.compile_scene_graph(fixture())), "owned")
        with self.assertRaises(CollaborationError): bob.job(job["id"])
        with self.assertRaises(CollaborationError): bob.cancel_job(job["id"])
        forged = {**alice.binding, "token": "a" * 40}
        with self.assertRaises(CollaborationError): dispatch.RenderClient(forged).job(job["id"])
        with self.assertRaises(CollaborationError): dispatch.RenderClient({**alice.binding, "certificate_sha256": "0" * 64})
        alice.revoke(bob.binding["client_id"])
        with self.assertRaises(CollaborationError): bob.operation("not_submitted")
        self.assertEqual("completed", self.settle(alice, job)["status"])

    def test_queued_and_running_cancellation_settle_real_engine_without_public_artifacts(self):
        worker, _, client = self.worker()
        running = client.submit_job(dispatch.render_request(graph.compile_scene_graph(self.heavy())), "running")
        self.wait_engine(worker.root, running["id"])
        queued = client.submit_job(dispatch.render_request(graph.compile_scene_graph(fixture())), "queued")
        self.assertEqual("cancelled", client.cancel_job(queued["id"])["status"])
        self.assertEqual("cancelled", self.settle(client, client.cancel_job(running["id"]))["status"])
        result = client.job(running["id"])
        self.assertIsNone(result["result"])
        with self.assertRaises(CollaborationError): client.download_artifact(running["id"], {"filename": "preview.mp4", "sha256": "0" * 64, "size": 1}, self.root / "forbidden.mp4")
        self.assertFalse((self.root / "forbidden.mp4").exists())
        self.assertEqual(0, client.job(queued["id"])["attempt"])

    def test_worker_restart_retains_identity_completed_bytes_and_explicit_retry(self):
        worker, service, client = self.worker()
        job = client.submit_job(dispatch.render_request(graph.compile_scene_graph(self.heavy())), "interrupted")
        self.wait_engine(worker.root, job["id"])
        port = service.server.server_port; service.close(); self.services[0] = None
        worker.close(); self.workers[0] = None
        resumed = dispatch.RenderWorker(worker.root)
        new_service = dispatch.start_render_worker(resumed, port=port)
        self.workers.append(resumed); self.services.append(new_service)
        retained = client.job(job["id"])
        self.assertEqual("interrupted", retained["status"])
        self.assertEqual(job["id"], client.retry_job(job["id"])["id"])
        completed = self.settle(client, job, timeout=60)
        self.assertEqual("completed", completed["status"], completed.get("error")); self.assertEqual(2, completed["attempt"])
        preview = next(x for x in completed["result"]["artifacts"] if x["filename"] == "preview.mp4")
        client.download_artifact(job["id"], preview, self.root / "after_restart.mp4")
        self.assertEqual(1, len(read_frames(self.root / "after_restart.mp4", 1024, 768)))

    def test_coordinator_crash_gap_recovers_remote_operation_without_duplicate_render(self):
        worker, _, client = self.worker()
        owner = dispatch.Dispatcher(self.root / "dispatch", self.bindings)
        source = fixture(animated=True); batch = owner.submit(source, frames=[3], operation_id="lost_reply")
        request = dispatch.render_request(graph.compile_scene_graph(source, {"frame": 3}))
        accepted = self.settle(client, client.submit_job(request, batch["id"] + "_0"))
        # Real worker committed; a crashed coordinator has not recorded its ID.
        self.assertIsNone(owner.status(batch["id"])["tasks"][0]["remote_id"])
        reopened = dispatch.Dispatcher(self.root / "dispatch", self.bindings)
        result = reopened.run(batch["id"], self.root / "recovered")
        self.assertEqual(accepted["id"], reopened.status(batch["id"])["tasks"][0]["remote_id"])
        with worker._db() as db: self.assertEqual(1, db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])
        self.assertEqual(1, len(read_frames(result["path"])))
        self.assertEqual(result, reopened.run(batch["id"], self.root / "recovered"))

    def test_cancel_recovers_lost_submission_reply_without_creating_new_tasks(self):
        worker, _, client = self.worker()
        owner = dispatch.Dispatcher(self.root / "dispatch", self.bindings)
        source = self.heavy(); batch = owner.submit(source, frames=[1, 2], operation_id="lost_cancel")
        job = client.submit_job(dispatch.render_request(graph.compile_scene_graph(source, {"frame": 1})), batch["id"] + "_0")
        self.wait_engine(worker.root, job["id"])
        owner.cancel(batch["id"])
        with self.assertRaisesRegex(CollaborationError, "cancelled"):
            owner.run(batch["id"], self.root / "cancelled-output")
        self.assertEqual("cancelled", owner.status(batch["id"])["status"])
        self.assertEqual("cancelled", client.job(job["id"])["status"])
        with worker._db() as db: self.assertEqual(1, db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])
        self.assertFalse((self.root / "cancelled-output").exists())

    def test_parent_process_death_cancels_owned_child_and_recovers_durable_job(self):
        script = self.root / "host.py"
        script.write_text("import sys,json,time\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nimport scene_dispatch as d\nw=d.RenderWorker(sys.argv[2]);s=d.start_render_worker(w);print(json.dumps(w.pair_owner()),flush=True)\nsys.stdin.buffer.read(1)\ns.close();w.close()\n")
        directory = self.root / "crashed-worker"
        process = subprocess.Popen([sys.executable, "-I", "-B", str(script), str(Path(__file__).parent), str(directory)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            binding = json.loads(process.stdout.readline()); client = dispatch.RenderClient(binding)
            job = client.submit_job(dispatch.render_request(graph.compile_scene_graph(self.heavy())), "host_crash")
            self.wait_engine(directory, job["id"])
            process.kill(); process.wait(timeout=10)  # current owned Popen only
            lease = directory / "jobs" / job["id"] / "render.lock"
            deadline = time.monotonic() + 15; settled = False
            while time.monotonic() < deadline:
                fd = os.open(lease, os.O_RDWR)
                try:
                    try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); settled = True
                    except BlockingIOError: pass
                finally: os.close(fd)
                if settled: break
                time.sleep(.05)
            self.assertTrue(settled, "Real render child did not release its job lease after supervisor EOF.")
            worker = dispatch.RenderWorker(directory)
            port = dispatch.urlsplit(binding["url"]).port
            service = dispatch.start_render_worker(worker, port=port)
            self.workers.append(worker); self.services.append(service)
            self.assertEqual("interrupted", client.job(job["id"])["status"])
            self.assertIsNone(client.job(job["id"])["result"])
        finally:
            if process.poll() is None: process.terminate(); process.wait(timeout=15)
            for stream in (process.stdin, process.stdout, process.stderr): stream.close()

    def test_corrupt_worker_and_published_artifacts_fail_without_overwriting(self):
        worker, _, client = self.worker()
        job = self.settle(client, client.submit_job(dispatch.render_request(graph.compile_scene_graph(fixture())), "tamper"))
        self.assertEqual("completed", job["status"], job.get("error"))
        path = worker.jobs_dir / job["id"] / "attempt-0001/render/published/preview.mp4"
        original = path.read_bytes(); path.write_bytes(original + b"changed")
        record = next(x for x in job["result"]["artifacts"] if x["filename"] == "preview.mp4")
        with self.assertRaises(CollaborationError): client.download_artifact(job["id"], record, self.root / "corrupt.mp4")
        self.assertFalse((self.root / "corrupt.mp4").exists()); path.write_bytes(original)
        owner = dispatch.Dispatcher(self.root / "dispatch", self.bindings); batch = owner.submit(fixture(), frames=[1], operation_id="publication")
        owner.run(batch["id"], self.root / "published")
        target = self.root / "published/preview.mp4"; target.write_bytes(b"owner edit retained")
        with self.assertRaises(CollaborationError): owner.run(batch["id"], self.root / "published")
        self.assertEqual(b"owner edit retained", target.read_bytes())

    def test_requests_cannot_name_commands_paths_or_claim_other_payload_hashes(self):
        _, _, client = self.worker()
        request = dispatch.render_request(graph.compile_scene_graph(fixture()))
        for replacement in ({"operation": "exec", "command": "echo bad"}, {"filename": "/tmp/external"},
                            {"scene_sha256": "0" * 64}, {"context_sha256": "0" * 64}):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError): client.submit_job({**request, **replacement}, "invalid")
        with self.assertRaises(ValueError): dispatch.RenderWorker(self.root / "first")
        outside = self.root / "outside"; outside.mkdir(); symlink = self.root / "link"; symlink.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError): dispatch.RenderWorker(symlink)

    def test_batch_identity_drift_and_context_bounds_fail_before_remote_mutation(self):
        worker, _, _ = self.worker()
        owner = dispatch.Dispatcher(self.root / "dispatch", self.bindings)
        source = fixture(); batch = owner.submit(source, frames=[1], operation_id="identity")
        with self.assertRaises(CollaborationError): owner.submit(source, frames=[2], operation_id="identity")
        for contexts, frames in (([{}], [1, 1]), ([{"frame": 2}], [1]), ([{}] * 16, list(range(5))), ([{"unknown": 1}], [1])):
            with self.subTest(contexts=contexts, frames=frames), self.assertRaises(ValueError): owner.submit(source, contexts, frames, operation_id="invalid")
        changed = copy.deepcopy(self.bindings); changed["first"]["client_id"] = "0" * 32
        reopened = dispatch.Dispatcher(self.root / "dispatch", changed)
        with self.assertRaisesRegex(CollaborationError, "identity changed"): reopened.run(batch["id"], self.root / "unpublished")
        with worker._db() as db: self.assertEqual(0, db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])


if __name__ == "__main__": unittest.main(verbosity=2)
