"""Protocol and process-boundary tests; fixture bytes are never production media."""

import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock
import urllib.parse

import adapters


class _ComfyHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_payload(self, payload, code=200, headers=None):
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json" if not isinstance(payload, bytes) else "video/mp4")
        self.send_header("Content-Length", str(len(data)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.server.calls.append(("GET", self.path))
        route = urllib.parse.urlsplit(self.path).path
        if route == "/system_stats":
            self.send_payload({"system": {"python_version": "test"}, "devices": []})
        elif route == "/history/prompt-test":
            self.send_payload(self.server.history)
        elif route == "/view":
            if self.server.download_redirect:
                self.send_payload(b"", 302, {"Location": "/forbidden"})
            else:
                self.send_payload(self.server.video, self.server.download_status)
        else:
            self.send_payload({"error": "not found"}, 404)

    def do_POST(self):
        self.server.calls.append(("POST", self.path))
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.submissions.append(json.loads(body))
        if self.path == "/prompt":
            self.send_payload(self.server.accepted, self.server.submit_status)
        else:
            self.send_payload({"error": "unexpected mutation"}, 500)


class ComfyAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _ComfyHandler)
        self.server.calls = []
        self.server.submissions = []
        self.server.accepted = {"prompt_id": "prompt-test", "node_errors": {}}
        self.server.submit_status = 200
        self.server.video = b"TEST-ONLY-PROTOCOL-FIXTURE-NOT-VALID-MEDIA"
        self.server.download_status = 200
        self.server.download_redirect = False
        self.server.history = {"prompt-test": {
            "status": {"completed": True, "status_str": "success", "messages": []},
            "outputs": {"9": {"gifs": [{"filename": "clip.mp4", "type": "output", "subfolder": "shots"}]}},
        }}
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:%d" % self.server.server_port
        self.workflow = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "film: CINEMATICUM_POSITIVE_PROMPT"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "keep this negative text"}},
            "3": {"class_type": "KSampler", "inputs": {"seed": "CINEMATICUM_SEED", "positive": ["1", 0], "negative": ["2", 0]}},
        }

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
        self.temp.cleanup()

    def generate(self, **kwargs):
        return adapters.generate_comfyui(self.url, self.workflow, "actual prompt", "requested negative", 123,
                                        self.temp.name, **kwargs)

    def test_readiness_is_read_only(self):
        self.assertTrue(adapters.check_comfyui(self.url)["available"])
        self.assertEqual(self.server.submissions, [])

    def test_marker_binding_preserves_unmarked_text_and_source_workflow(self):
        original = copy.deepcopy(self.workflow)
        result = self.generate()
        submitted = self.server.submissions[0]["prompt"]
        self.assertEqual(submitted["1"]["inputs"]["text"], "film: actual prompt")
        self.assertEqual(submitted["2"]["inputs"]["text"], "keep this negative text")
        self.assertEqual(submitted["3"]["inputs"]["seed"], 123)
        self.assertEqual(submitted["3"]["inputs"]["negative"], ["2", 0])
        self.assertEqual(self.workflow, original)
        self.assertEqual(Path(result["path"]).read_bytes(), self.server.video)
        self.assertEqual(result["provenance"]["prompt_id"], "prompt-test")
        self.assertTrue(result["provenance"]["seed_bound"])

    def test_markers_in_inserted_prompt_are_not_recursively_replaced(self):
        self.workflow["2"]["inputs"]["text"] = adapters.NEGATIVE_MARKER
        result = adapters.generate_comfyui(self.url, self.workflow, "literal " + adapters.NEGATIVE_MARKER,
                                          "bad lighting", 1, self.temp.name)
        submitted = self.server.submissions[0]["prompt"]
        self.assertEqual(submitted["1"]["inputs"]["text"], "film: literal CINEMATICUM_NEGATIVE_PROMPT")
        self.assertEqual(submitted["2"]["inputs"]["text"], "bad lighting")
        self.assertTrue(Path(result["path"]).exists())

    def test_seed_is_optional_workflow_binding_and_truthful_in_provenance(self):
        self.workflow["3"]["inputs"]["seed"] = 77
        result = self.generate()
        self.assertEqual(self.server.submissions[0]["prompt"]["3"]["inputs"]["seed"], 77)
        self.assertFalse(result["provenance"]["seed_bound"])

    def test_missing_positive_marker_refuses_before_submission(self):
        self.workflow["1"]["inputs"]["text"] = "unchanged text"
        with self.assertRaisesRegex(adapters.AdapterError, "CINEMATICUM_POSITIVE_PROMPT"):
            self.generate()
        self.assertEqual(self.server.calls, [])

    def test_ui_graph_and_invalid_nodes_refused(self):
        for graph in ({"nodes": []}, {"1": {"class_type": "", "inputs": {}}}, {"1": {"class_type": "Save", "inputs": []}}):
            with self.assertRaises(adapters.AdapterError):
                adapters.validate_workflow(graph)

    def test_validation_error_is_not_retried(self):
        self.server.submit_status = 400
        self.server.accepted = {"error": {"message": "model not installed"}}
        with self.assertRaisesRegex(adapters.AdapterError, "not retried"):
            self.generate()
        self.assertEqual(len(self.server.submissions), 1)

    def test_failed_execution_retains_prompt_id_and_does_not_download(self):
        self.server.history["prompt-test"]["status"] = {
            "completed": False, "status_str": "error",
            "messages": [["execution_error", {"exception_message": "model missing"}]],
        }
        with self.assertRaisesRegex(adapters.AdapterError, "model missing") as raised:
            self.generate()
        self.assertEqual(raised.exception.prompt_id, "prompt-test")
        self.assertFalse(any(path.startswith("/view") for _, path in self.server.calls))

    def test_image_only_workflow_fails_explicitly(self):
        self.server.history["prompt-test"]["outputs"] = {"9": {"images": [{"filename": "still.png"}]}}
        with self.assertRaisesRegex(adapters.AdapterError, "Image-only"):
            self.generate()
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_missing_video_download_does_not_publish_a_partial_file(self):
        self.server.download_status = 404
        with self.assertRaises(adapters.AdapterError):
            self.generate()
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_cancel_after_submission_never_interrupts_shared_server(self):
        self.server.history = {}
        event = threading.Event()

        def on_progress(value):
            if value >= 0.1:
                event.set()

        with self.assertRaises(adapters.AdapterCancelled) as raised:
            self.generate(progress=on_progress, cancel_event=event)
        self.assertEqual(raised.exception.prompt_id, "prompt-test")
        self.assertEqual([path for method, path in self.server.calls if method == "POST"], ["/prompt"])

    def test_download_redirect_is_not_followed(self):
        self.server.download_redirect = True
        with self.assertRaisesRegex(adapters.AdapterError, "redirect"):
            self.generate()
        self.assertFalse(any(path == "/forbidden" for _, path in self.server.calls))
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_output_traversal_refused(self):
        self.server.history["prompt-test"]["outputs"]["9"]["gifs"][0]["subfolder"] = "../private"
        with self.assertRaisesRegex(adapters.AdapterError, "unsafe"):
            self.generate()
        self.assertFalse(any(path.startswith("/view") for _, path in self.server.calls))

    def test_download_limit_prevents_publishing(self):
        with mock.patch.object(adapters, "MAX_DOWNLOAD_BYTES", 5):
            with self.assertRaisesRegex(adapters.AdapterError, "download limit"):
                self.generate()
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_timeout_is_bounded_and_not_resubmitted(self):
        self.server.history = {}
        with mock.patch.object(adapters, "_COMFY_TIMEOUT", 0.02), mock.patch.object(adapters, "_POLL_INTERVAL", 0.005):
            with self.assertRaisesRegex(adapters.AdapterError, "Timed out") as raised:
                self.generate()
        self.assertEqual(raised.exception.prompt_id, "prompt-test")
        self.assertEqual(len(self.server.submissions), 1)


class BlenderAdapterTests(unittest.TestCase):
    def test_pre_cancel_does_not_launch_blender(self):
        event = threading.Event()
        event.set()
        with mock.patch.object(adapters.subprocess, "Popen") as spawn:
            with self.assertRaises(adapters.AdapterCancelled):
                adapters.render_blender("missing.blend", ".", 1, 2, cancel_event=event)
        spawn.assert_not_called()

    def test_script_order_frame_range_and_atomic_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            scene = Path(directory) / "scene.blend"
            scene.write_bytes(b"TEST-ONLY-SCENE-FIXTURE")
            output = Path(directory) / "output"
            calls = []

            def run(argv, log_path, event, timeout, on_tick=lambda: None):
                calls.append(argv)
                if "--python" in argv:
                    self.assertLess(argv.index("--disable-autoexec"), argv.index(str(scene.resolve())))
                    self.assertLess(argv.index(str(scene.resolve())), argv.index("--python"))
                    script = Path(argv[argv.index("--python") + 1])
                    content = script.read_text()
                    compile(content, str(script), "exec")
                    self.assertIn("scene.frame_start = 2", content)
                    self.assertIn("scene.frame_end = 3", content)
                    self.assertIn("scene.render.fps = 24", content)
                    # Execute the generated safeguards against both Blender API
                    # generations, shared groups and a cyclic group reference.
                    # None of these protocol fixtures are production media.
                    class NodeTree:
                        def __init__(self, nodes):
                            self.nodes = nodes

                        def as_pointer(self):
                            return id(self)

                    legacy_output = SimpleNamespace(bl_idname="CompositorNodeOutputFile", mute=False,
                        base_path="/outside/job", file_slots=[SimpleNamespace(path="../../escape")],
                        layer_slots=[SimpleNamespace(name="../layer")])
                    modern_output = SimpleNamespace(bl_idname="CompositorNodeOutputFile", mute=False,
                        directory="/outside/job", file_name="../../escape",
                        file_output_items=[SimpleNamespace(name="../../item")])
                    composite = SimpleNamespace(bl_idname="CompositorNodeComposite", mute=False)
                    nested = NodeTree([modern_output])
                    main_tree = NodeTree([legacy_output, composite,
                        SimpleNamespace(bl_idname="CompositorNodeGroup", node_tree=nested)])
                    nested.nodes.append(SimpleNamespace(bl_idname="CompositorNodeGroup", node_tree=main_tree))
                    other_output = SimpleNamespace(bl_idname="CompositorNodeOutputFile", mute=False,
                        base_path="/other/scene", file_slots=[])
                    other_tree = NodeTree([other_output])
                    render = SimpleNamespace(image_settings=SimpleNamespace())
                    active_scene = SimpleNamespace(node_tree=main_tree, render=render)
                    render_call = mock.Mock()
                    fake_bpy = SimpleNamespace(context=SimpleNamespace(scene=active_scene),
                        data=SimpleNamespace(scenes=[active_scene,
                            SimpleNamespace(compositing_node_group=other_tree)], node_groups=[nested, main_tree]),
                        ops=SimpleNamespace(render=SimpleNamespace(render=render_call)))
                    with mock.patch.dict(sys.modules, {"bpy": fake_bpy}):
                        exec(compile(content, str(script), "exec"), {})
                    safe_directory = script.parent / "disabled-compositor-outputs"
                    for node in (legacy_output, modern_output, other_output):
                        self.assertTrue(node.mute)
                        self.assertEqual(getattr(node, "base_path", getattr(node, "directory", None)), str(safe_directory))
                    self.assertEqual(legacy_output.file_slots[0].path, "slot_0000")
                    self.assertEqual(legacy_output.layer_slots[0].name, "slot_0000")
                    self.assertEqual(modern_output.file_output_items[0].name, "slot_0000")
                    self.assertRegex(modern_output.file_name, r"^disabled_output_\d{4}$")
                    self.assertFalse(composite.mute)
                    render_call.assert_called_once_with(animation=True)
                    for frame in (2, 3):
                        (script.parent / "frames" / ("frame_%06d.png" % frame)).write_bytes(b"TEST-ONLY-FRAME")
                else:
                    self.assertEqual(argv[argv.index("-start_number") + 1], "2")
                    self.assertEqual(argv[argv.index("-frames:v") + 1], "2")
                    Path(argv[-1]).write_bytes(b"TEST-ONLY-ENCODED-PROTOCOL-FIXTURE")

            with mock.patch.object(adapters, "find_blender", return_value="/test/blender"), \
                    mock.patch.object(adapters.shutil, "which", return_value="/test/ffmpeg"), \
                    mock.patch.object(adapters, "_run_owned", side_effect=run):
                result = adapters.render_blender(scene, output, 2, 3)
            self.assertEqual(len(calls), 2)
            self.assertEqual(len(list(output.iterdir())), 1)
            self.assertTrue(Path(result["path"]).is_file())
            self.assertFalse(result["provenance"]["autoexec_enabled"])
            self.assertTrue(result["provenance"]["frame_end_inclusive"])

    def test_cancel_terminates_only_the_process_started_here(self):
        event = threading.Event()
        launched = []
        real_popen = subprocess.Popen

        def capture(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            launched.append(process)
            event.set()
            return process

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(adapters.subprocess, "Popen", side_effect=capture):
            with self.assertRaises(adapters.AdapterCancelled):
                adapters._run_owned([sys.executable, "-c", "import time; time.sleep(20)"],
                                    Path(directory) / "owned.log", event, 30)
        self.assertEqual(len(launched), 1)
        self.assertIsNotNone(launched[0].poll())


if __name__ == "__main__":
    unittest.main()
