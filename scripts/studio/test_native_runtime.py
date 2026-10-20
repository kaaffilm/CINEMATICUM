"""Ownership, mount isolation, authentication, and unsaved-document lifecycle.

Docker operations are modeled at the process boundary so these tests can prove
that rejected input never reaches a mutating Docker command. Actual packaged
editors and the Xpra/audio path require the separate native runtime smoke test.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from native_runtime import NativeRuntime, NativeRuntimeError, LABEL_PREFIX, RUNTIME_KIND, EDITOR_NAMES, _mount


PID = "a" * 32
CONTAINER_ID = "c" * 64
IMAGE_ID = "sha256:" + "d" * 64


class DockerBoundary:
    def __init__(self):
        self.manager = None
        self.container = None
        self.calls = []
        self.image_present = True
        self.image_foreign = False
        self.daemon = True
        self.endpoint = "unix:///Users/test/.docker/run/docker.sock"
        self.exec_response = {"ok": True, "editor": "kdenlive", "pid": 123}
        self.desktop_response = {"ok": True, "ready": True, "complete_set": True, "editors": [
            {"id": key, "version": "fixture", "running": True, "window_ready": True,
             "windows": [{"id": "0x123", "pid": 123, "title": "Editing window"}]}
            for key in EDITOR_NAMES]}

    def result(self, value="", code=0):
        return subprocess.CompletedProcess([], code, json.dumps(value) if not isinstance(value, str) else value,
                                           "No such container or image" if code else "")

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        assert argv[1:3] == ["--context", "desktop-linux"]
        args = argv[3:]
        if args[:2] == ["context", "inspect"]:
            return self.result([{"Endpoints": {"docker": {"Host": self.endpoint}}}])
        if args[0] == "info":
            if not self.daemon:
                return subprocess.CompletedProcess(argv, 1, "", "Cannot connect to the Docker daemon")
            return self.result({"OSType": "linux", "Architecture": "aarch64"})
        if args[:2] == ["image", "inspect"]:
            if not self.image_present:
                return self.result(code=1)
            m = self.manager
            return self.result([{"Id": IMAGE_ID, "Config": {"Labels": {
                LABEL_PREFIX + "runtime": "foreign" if self.image_foreign else RUNTIME_KIND,
                LABEL_PREFIX + "source": m._source_fingerprint(),
                LABEL_PREFIX + "uid": str(m.uid), LABEL_PREFIX + "gid": str(m.gid),
            }}}])
        if args[:2] == ["container", "inspect"]:
            return self.result([self.container]) if self.container else self.result(code=1)
        if args[:2] == ["container", "ls"]:
            return self.result(PID if self.container else "")
        if args[:2] == ["container", "run"]:
            self.container = self.make_container(args)
            return self.result(CONTAINER_ID)
        if args[:2] == ["container", "start"]:
            self.container["State"] = {"Running": True, "Status": "running"}
            return self.result(CONTAINER_ID)
        if args[:2] == ["container", "stop"]:
            self.container["State"] = {"Running": False, "Status": "exited"}
            return self.result(CONTAINER_ID)
        if args[:2] == ["container", "exec"]:
            if args[3:] == ["/usr/local/bin/cinematicum-control", "status"]:
                return self.result(self.desktop_response)
            return self.result(self.exec_response)
        raise AssertionError("Unexpected Docker command: " + repr(args))

    def make_container(self, args):
        labels = {}
        mounts = []
        for i, arg in enumerate(args):
            if arg == "--label":
                key, value = args[i + 1].split("=", 1)
                labels[key] = value
            elif arg == "--mount":
                fields = next(csv.reader(io.StringIO(args[i + 1])))
                values = dict(field.split("=", 1) for field in fields if "=" in field)
                mounts.append({"Type": values["type"], "Source": values["source"],
                               "Destination": values["target"], "RW": "readonly" not in fields})
        return {
            "Id": CONTAINER_ID,
            "Image": IMAGE_ID,
            "Config": {"Labels": labels, "User": str(self.manager.uid) + ":" + str(self.manager.gid)},
            "HostConfig": {"Privileged": False, "ReadonlyRootfs": "--read-only" in args,
                           "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges:true"],
                           "PortBindings": {"14500/tcp": [{"HostIp": "127.0.0.1", "HostPort": ""}]}},
            "NetworkSettings": {"Ports": {"14500/tcp": [{"HostIp": "127.0.0.1", "HostPort": "56234"}]}},
            "Mounts": mounts,
            "State": {"Running": True, "Status": "running"},
        }

    def mutations(self):
        return [argv[3:] for argv, _ in self.calls if argv[3:5] in
                (["container", "run"], ["container", "start"], ["container", "stop"], ["container", "exec"])]


class NativeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cinematicum-native-manager-")
        self.root = Path(self.temp.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        (self.runtime / "Dockerfile").write_text("FROM ubuntu:24.04\n")
        (self.runtime / "prepare.py").write_text("# acquisition test fixture\n")
        (self.runtime / "engines.json").write_text("{}\n")
        self.workspace = self.root / "workspace"
        self.project = self.workspace / "projects" / PID
        (self.project / "media").mkdir(parents=True)
        (self.project / "project.json").write_text('{"immutable": true}')
        self.fake = DockerBoundary()
        self.manager = NativeRuntime(self.workspace, docker_path="/fixture/docker", runtime_dir=self.runtime, runner=self.fake)
        self.fake.manager = self.manager
        self.ready = patch.object(self.manager, "_wait_ready", side_effect=lambda project_id, **kwargs: self.manager._session_status(project_id, self.manager._inspect(project_id)))
        self.ready.start()

    def tearDown(self):
        self.ready.stop()
        self.temp.cleanup()

    def start(self):
        return self.manager.start(self.project, PID)

    def test_real_start_contract_mounts_only_native_documents_and_readonly_admitted_media(self):
        result = self.start()
        mounts = {x["Destination"]: x for x in self.fake.container["Mounts"]}
        self.assertEqual({"/projects/" + PID, "/media", "/home/cinematicum", "/run/cinematicum/password"}, set(mounts))
        self.assertFalse(mounts["/media"]["RW"])
        self.assertFalse(mounts["/run/cinematicum/password"]["RW"])
        self.assertTrue(mounts["/projects/" + PID]["RW"])
        self.assertEqual(str(self.project / "media"), mounts["/media"]["Source"])
        self.assertEqual(str(self.workspace / "nativeprojects" / PID), mounts["/projects/" + PID]["Source"])
        self.assertTrue(result["running"])
        self.assertNotIn("password", result)
        run = next(x for x in self.fake.mutations() if x[1] == "run")
        self.assertEqual(IMAGE_ID, run[-1])
        self.assertIn("127.0.0.1::14500/tcp", run)
        self.assertNotIn("--privileged", run)
        self.assertNotIn("/var/run/docker.sock", " ".join(run))

    def test_unknown_editor_and_command_never_reach_docker_exec(self):
        for editor in ("sh", "kdenlive; rm", "../blender", None):
            with self.assertRaises((ValueError, TypeError)):
                self.manager.open_editor(editor, PID, self.project)
        for action in ("shell", "save;exit", "quit", None):
            with self.assertRaises((ValueError, TypeError)):
                self.manager.command(PID, action)
        self.assertEqual([], self.fake.mutations())

    def test_path_and_project_id_injection_do_not_create_containers(self):
        for project_id in ("../secrets", "a" * 31, "A" * 32, "/tmp/x", PID + "\n"):
            with self.assertRaises((ValueError, NativeRuntimeError)):
                self.manager.start(self.project, project_id)
        with self.assertRaises(NativeRuntimeError):
            self.manager.start(self.root, PID)
        self.assertEqual([], self.fake.mutations())

    def test_foreign_named_container_is_never_adopted_or_stopped(self):
        self.start()
        self.fake.container["Config"]["Labels"][LABEL_PREFIX + "workspace"] = "someone-else"
        before = len(self.fake.mutations())
        for action in (lambda: self.manager.start(self.project, PID),
                       lambda: self.manager.stop(PID, confirmed=True),
                       lambda: self.manager.access(PID),
                       lambda: self.manager.command(PID, "save")):
            with self.assertRaisesRegex(NativeRuntimeError, "not owned"):
                action()
        self.assertEqual(before, len(self.fake.mutations()))

    def test_readwrite_media_and_extra_host_mount_are_rejected_before_control(self):
        self.start()
        original = copy.deepcopy(self.fake.container)
        self.fake.container["Mounts"][1]["RW"] = True
        before = len(self.fake.mutations())
        with self.assertRaisesRegex(NativeRuntimeError, "mounts"):
            self.manager.command(PID, "save")
        self.fake.container = copy.deepcopy(original)
        self.fake.container["Mounts"].append({"Type": "bind", "Source": "/var/run/docker.sock", "Destination": "/socket", "RW": True})
        with self.assertRaisesRegex(NativeRuntimeError, "mounts"):
            self.manager.stop(PID, confirmed=True)
        self.assertEqual(before, len(self.fake.mutations()))

    def test_public_network_bind_or_unexpected_port_is_rejected(self):
        self.start()
        original = copy.deepcopy(self.fake.container)
        self.fake.container["HostConfig"]["PortBindings"]["14500/tcp"][0]["HostIp"] = "0.0.0.0"
        with self.assertRaisesRegex(NativeRuntimeError, "loopback"):
            self.manager.access(PID)
        self.fake.container = copy.deepcopy(original)
        self.fake.container["HostConfig"]["PortBindings"]["5900/tcp"] = [{"HostIp": "127.0.0.1", "HostPort": "5900"}]
        with self.assertRaisesRegex(NativeRuntimeError, "unexpected network"):
            self.manager.access(PID)
        self.fake.container = copy.deepcopy(original)
        self.fake.container["NetworkSettings"]["Ports"]["14500/tcp"][0]["HostIp"] = "::"
        with self.assertRaisesRegex(NativeRuntimeError, "loopback"):
            self.manager.access(PID)

    def test_privilege_or_root_user_drift_blocks_access_and_stop(self):
        self.start()
        original = copy.deepcopy(self.fake.container)
        for change in (lambda x: x["HostConfig"].update(Privileged=True),
                       lambda x: x["HostConfig"].update(ReadonlyRootfs=False),
                       lambda x: x["Config"].update(User="0:0")):
            self.fake.container = copy.deepcopy(original)
            change(self.fake.container)
            with self.assertRaises(NativeRuntimeError):
                self.manager.stop(PID, confirmed=True)

    def test_authentication_is_private_stable_and_excluded_from_status_and_launch_results(self):
        started = self.start()
        first = self.manager.access(PID)
        password_path = self.manager._project_paths(PID)["password"]
        self.assertEqual(0o600, password_path.stat().st_mode & 0o777)
        self.assertGreaterEqual(len(first["password"]), 40)
        opened = self.manager.open_editor("kdenlive", PID, self.project)
        status = self.manager.status(PID)
        second = self.manager.access(PID)
        self.assertEqual(first["password"], second["password"])
        self.assertNotIn(first["password"], json.dumps([started, opened, status]))
        self.assertNotIn(first["password"], json.dumps([argv for argv, _ in self.fake.calls]))
        self.assertEqual("http://127.0.0.1:56234/", second["url"])

    def test_world_readable_or_hardlinked_authentication_is_rejected(self):
        self.start()
        path = self.manager._project_paths(PID)["password"]
        path.chmod(0o644)
        with self.assertRaisesRegex(NativeRuntimeError, "0600"):
            self.manager.access(PID)
        path.chmod(0o600)
        os.link(path, path.with_name("copy"))
        with self.assertRaisesRegex(NativeRuntimeError, "0600"):
            self.manager.access(PID)

    def test_open_waits_for_an_actual_owned_editor_window_after_process_acknowledgement(self):
        pending = copy.deepcopy(self.fake.desktop_response)
        ready = copy.deepcopy(pending)
        pending["editors"][0].update(window_ready=False, windows=[])
        self.fake.exec_response = {"ok": True, "running": True, "window_ready": False}
        with patch.object(self.manager, "_desktop_status", side_effect=[pending, ready]) as check, patch("native_runtime.time.sleep"):
            result = self.manager.open_editor("kdenlive", PID, self.project)
        self.assertEqual(2, check.call_count)
        self.assertEqual({"id": "kdenlive", "running": True, "window_ready": True,
                          "window_count": 1, "version": "fixture"}, result["launch"])
        self.assertNotIn("windows", result["launch"])

    def test_editor_process_failure_is_not_reported_as_a_ready_workspace(self):
        self.fake.desktop_response["editors"][0].update(running=False, window_ready=False, windows=[])
        with self.assertRaisesRegex(NativeRuntimeError, "stopped before"):
            self.manager.open_editor("kdenlive", PID, self.project)
        self.assertTrue(self.fake.container["State"]["Running"])
        self.assertFalse(any(call[1] == "stop" for call in self.fake.mutations()))

    def test_cancelling_window_readiness_preserves_owned_session_and_unsaved_work(self):
        self.start()
        event = threading.Event()
        event.set()
        with self.assertRaisesRegex(NativeRuntimeError, "unsaved documents"):
            self.manager._wait_editor(PID, "kdenlive", cancel_event=event)
        self.assertTrue(self.fake.container["State"]["Running"])
        self.assertFalse(any(call[1] == "stop" for call in self.fake.mutations()))

    def test_symlink_media_or_native_project_is_rejected(self):
        media = self.project / "media"
        media.rmdir()
        media.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(NativeRuntimeError, "symlink"):
            self.start()
        media.unlink()
        media.mkdir()
        (self.workspace / "nativeprojects" / PID).symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(NativeRuntimeError, "symlink"):
            self.start()
        self.assertEqual([], self.fake.mutations())

    def test_symlink_authentication_is_rejected_without_reading_target(self):
        path = self.manager._project_paths(PID)["password"]
        outside = self.root / "unrelated.txt"
        outside.write_text("x" * 48)
        outside.chmod(0o600)
        path.symlink_to(outside)
        with self.assertRaisesRegex(NativeRuntimeError, "symlink"):
            self.start()
        self.assertEqual("x" * 48, outside.read_text())
        self.assertEqual([], self.fake.mutations())

    def test_closing_host_preserves_running_editor_and_unsaved_state(self):
        self.start()
        before = len(self.fake.calls)
        result = self.manager.shutdown()
        self.assertTrue(result["native_sessions_preserved"])
        self.assertTrue(self.fake.container["State"]["Running"])
        self.assertEqual(before, len(self.fake.calls))

    def test_reopening_host_reuses_owned_container_and_secret(self):
        self.start()
        original = self.manager.access(PID)["password"]
        reopened = NativeRuntime(self.workspace, docker_path="/fixture/docker", runtime_dir=self.runtime, runner=self.fake)
        self.fake.manager = reopened
        with patch.object(reopened, "_wait_ready", side_effect=lambda key, **kwargs: reopened._session_status(key, reopened._inspect(key))):
            reopened.start(self.project, PID)
        self.assertEqual(original, reopened.access(PID)["password"])
        self.assertEqual(1, sum(x[1] == "run" for x in self.fake.mutations()))

    def test_stop_requires_explicit_boolean_confirmation_and_uses_verified_id(self):
        self.start()
        for confirmed in (False, None, 1, "yes"):
            with self.assertRaisesRegex(NativeRuntimeError, "unsaved"):
                self.manager.stop(PID, confirmed=confirmed)
        result = self.manager.stop(PID, confirmed=True)
        self.assertFalse(result["running"])
        stops = [x for x in self.fake.mutations() if x[1] == "stop"]
        self.assertEqual([["container", "stop", "--time", "30", CONTAINER_ID]], stops)
        self.start()
        starts = [x for x in self.fake.mutations() if x[1] == "start"]
        self.assertEqual([["container", "start", CONTAINER_ID]], starts)

    def test_shortcuts_are_allowlisted_arguments_not_shell_commands(self):
        self.start()
        result = self.manager.command(PID, "undo")
        self.assertTrue(result["sent"])
        call = self.fake.mutations()[-1]
        self.assertEqual(["container", "exec", CONTAINER_ID, "/usr/local/bin/cinematicum-control", "key", "undo"], call)
        self.assertFalse(any(kwargs.get("shell") for _, kwargs in self.fake.calls))

    def test_missing_daemon_does_not_report_installed_or_start_docker(self):
        self.fake.daemon = False
        result = self.manager.status()
        self.assertFalse(result["available"])
        self.assertFalse(result["installed"])
        self.assertIn("Cannot connect", result["errors"][0])
        self.assertEqual([], self.fake.mutations())

    def test_remote_docker_context_is_rejected_before_any_mutation(self):
        self.fake.endpoint = "tcp://remote.example:2375"
        with self.assertRaisesRegex(NativeRuntimeError, "remote Docker"):
            self.start()
        self.assertEqual([], self.fake.mutations())

    def test_unverified_image_is_not_overwritten_or_used(self):
        self.fake.image_foreign = True
        with self.assertRaisesRegex(NativeRuntimeError, "unverified image"):
            self.manager.provision()
        self.assertEqual([], self.fake.mutations())

    def test_docker_helper_path_is_added_without_rewriting_configuration(self):
        with patch.dict(os.environ, {"PATH": "/usr/bin:/bin", "DOCKER_HOST": "tcp://evil:2375", "DOCKER_CONTEXT": "remote"}):
            self.manager.status(PID)
        env = self.fake.calls[0][1]["env"]
        self.assertEqual("/usr/bin:/bin:/fixture", env["PATH"])
        self.assertNotIn("DOCKER_HOST", env)
        self.assertNotIn("DOCKER_CONTEXT", env)

    def test_mount_csv_preserves_commas_without_option_injection(self):
        value = _mount(Path("/Users/editor/film,readonly=false"), "/media", True)
        fields = next(csv.reader(io.StringIO(value)))
        self.assertEqual(["type=bind", "source=/Users/editor/film,readonly=false", "target=/media", "readonly"], fields)

    def test_build_cache_symlink_is_not_followed(self):
        self.fake.image_present = False
        source = self.runtime / "nested"
        source.mkdir()
        (source / "file.txt").write_text("BUILD DEFINITION")
        build = self.manager.state_dir / "build" / self.manager._source_fingerprint()
        build.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        (build / "nested").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(NativeRuntimeError, "symlink"):
            self.manager.provision()
        self.assertFalse((outside / "file.txt").exists())

    def test_verified_package_cache_survives_runtime_code_changes_and_rejects_tampering(self):
        self.fake.image_present = False
        destinations = []
        created = []

        def acquisition(argv, **kwargs):
            if argv[0] == "/fixture/docker":
                self.fake.image_present = True
                return
            package_dir = Path(argv[argv.index("--output") + 1])
            destinations.append(package_dir)
            manifest = package_dir / "engines.lock.json"
            if manifest.exists():
                return
            entries = []
            for editor in EDITOR_NAMES:
                raw = ("VERIFIED ENGINE FIXTURE " + editor).encode()
                archive = package_dir / (editor + ".archive")
                archive.write_bytes(raw)
                created.append(archive)
                entries.append({"id": editor, "archive": archive.name, "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)})
            manifest.write_text(json.dumps({"schema": 1, "platform": "linux/amd64", "engines": entries}))

        with patch.object(self.manager, "_long_command", side_effect=acquisition):
            first = self.manager.provision()
            (self.runtime / "Dockerfile").write_text("FROM ubuntu:24.04\n# runtime fix\n")
            self.fake.image_present = False
            second = self.manager.provision()
            self.assertNotEqual(first["image"], second["image"])
            self.assertEqual(1, len(set(destinations)))
            self.assertEqual(7, len(created))
            data = created[0].read_bytes()
            created[0].write_bytes(b"X" + data[1:])
            self.fake.image_present = False
            with self.assertRaisesRegex(NativeRuntimeError, "SHA-256"):
                self.manager.provision()

    def test_documentation_edits_do_not_invalidate_runtime_build_identity(self):
        previous = self.manager._source_fingerprint()
        (self.runtime / "README.md").write_text("Documentation only")
        self.assertEqual(previous, self.manager._source_fingerprint())
        (self.runtime / "Dockerfile").write_text("FROM ubuntu:24.04\n# changed runtime\n")
        self.assertNotEqual(previous, self.manager._source_fingerprint())

    def test_installation_cancellation_terminates_only_owned_cli_group(self):
        event = threading.Event()
        timer = threading.Timer(.25, event.set)
        started = time.monotonic()
        timer.start()
        try:
            with self.assertRaisesRegex(NativeRuntimeError, "cancelled"):
                self.manager._long_command([sys.executable, "-c", "import time; print('fixture', flush=True); time.sleep(30)"], cancel_event=event, timeout=10)
        finally:
            timer.cancel()
        self.assertLess(time.monotonic() - started, 3)


if __name__ == "__main__":
    unittest.main()
