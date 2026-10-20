"""Own full-editor Linux GUI sessions without exposing a Docker or shell API.

The seven applications keep their native documents in a separate writable tree.
Studio's admitted media is a read-only bind mount.  Closing the Studio window
deliberately leaves these sessions alive: their in-memory documents may be dirty.
Only an explicit, confirmed stop may terminate an owned project session.
"""
from __future__ import annotations

from collections import deque
import csv
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
import uuid


EDITOR_NAMES = {
    "kdenlive": "Kdenlive",
    "shotcut": "Shotcut",
    "cinelerra": "Cinelerra-GG",
    "natron": "Natron",
    "friction": "Friction",
    "glaxnimate": "Glaxnimate",
    "blender": "Blender",
}
PROJECT_ID = re.compile(r"^[a-f0-9]{32}$")
HEX_DIGEST = re.compile(r"^[a-f0-9]{64}$")
RUNTIME_KIND = "full-editors-v1"
LABEL_PREFIX = "io.cinematicum."
CONTAINER_PORT = "14500/tcp"
MODE = "Linux x86-64 virtualized desktop; CPU/Mesa rendering"
DEFAULT_DOCKER = "/Applications/Docker.app/Contents/Resources/bin/docker"
CONTEXT = "desktop-linux"
BUILD_INPUTS = {"Dockerfile", ".dockerignore", "engines.json", "prepare.py", "install_bundles.py",
                "supervisor.py", "control.py", "cinematicum-open", "cinematicum-control", "xpra.sources"}


class NativeRuntimeError(RuntimeError):
    pass


def _private_directory(path):
    """Do not traverse symlink directories in application-owned runtime state."""
    path = Path(path)
    if path.is_symlink():
        raise NativeRuntimeError("Native editor state contains a symlink directory.")
    path.mkdir(mode=0o700, exist_ok=True)
    if not path.is_dir():
        raise NativeRuntimeError("Native editor state path is not a directory.")
    if path.stat().st_uid != os.getuid():
        raise NativeRuntimeError("Native editor state must be owned by this user.")
    path.chmod(0o700)
    return path


def _mount(source, target, readonly=False):
    # Docker --mount accepts CSV, not shell quoting. This also supports commas
    # in a workspace path without changing the meaning of mount options.
    output = io.StringIO()
    values = ["type=bind", "source=" + str(source), "target=" + target]
    if readonly:
        values.append("readonly")
    csv.writer(output, lineterminator="").writerow(values)
    return output.getvalue()


class NativeRuntime:
    def __init__(self, workspace, *, docker_path=None, runtime_dir=None, runner=None):
        self.workspace = Path(workspace).expanduser().resolve()
        if not self.workspace.is_dir():
            raise NativeRuntimeError("The Studio workspace must exist first.")
        self.runtime_dir = Path(runtime_dir or Path(__file__).parent / "full_runtime").resolve()
        self.docker = str(docker_path or DEFAULT_DOCKER)
        if not os.path.isabs(self.docker):
            raise NativeRuntimeError("Docker executable must have an absolute path.")
        self.runner = runner or subprocess.run
        self.owner = hashlib.sha256(str(self.workspace).encode("utf-8")).hexdigest()[:24]
        self.uid = os.getuid() if os.getuid() != 0 else 1000
        self.gid = os.getgid() if os.getuid() != 0 else 1000
        self.state_dir = _private_directory(self.workspace / ".native-runtime")
        self.native_dir = _private_directory(self.workspace / "nativeprojects")
        for child in ("auth", "settings", "build", "packages"):
            _private_directory(self.state_dir / child)
        self._lock = threading.RLock()

    def _env(self):
        env = dict(os.environ)
        # --context selects the one local Docker Desktop daemon. Explicitly
        # avoid inherited remote overrides and keep its credential helper on PATH.
        for name in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
            env.pop(name, None)
        bindir = str(Path(self.docker).parent)
        parts = env.get("PATH", "/usr/bin:/bin").split(os.pathsep)
        if bindir not in parts:
            parts.append(bindir)
        env["PATH"] = os.pathsep.join(parts)
        return env

    def _argv(self, args):
        return [self.docker, "--context", CONTEXT] + list(args)

    def _run(self, args, timeout=20, check=True):
        try:
            result = self.runner(self._argv(args), capture_output=True, text=True,
                                 timeout=timeout, env=self._env(), stdin=subprocess.DEVNULL)
        except FileNotFoundError:
            raise NativeRuntimeError("Docker Desktop is not installed at its expected application path.") from None
        except subprocess.TimeoutExpired:
            raise NativeRuntimeError("Docker Desktop did not respond in time.") from None
        except OSError as exc:
            raise NativeRuntimeError("Could not run Docker Desktop: " + str(exc)) from None
        if check and result.returncode:
            detail = (result.stderr or result.stdout or "Command failed").strip()[-1800:]
            raise NativeRuntimeError("Native editor runtime: " + detail)
        return result

    def _json(self, args, *, missing=False):
        result = self._run(args, check=False)
        if result.returncode:
            error = (result.stderr or result.stdout or "").lower()
            if missing and ("no such" in error or "not found" in error):
                return None
            raise NativeRuntimeError("Native editor runtime: " + (result.stderr or result.stdout or "Docker command failed").strip()[-1800:])
        try:
            return json.loads(result.stdout)
        except (TypeError, ValueError):
            raise NativeRuntimeError("Docker returned an invalid runtime description.") from None

    def _require_docker(self):
        contexts = self._json(["context", "inspect", CONTEXT])
        try:
            endpoint = contexts[0]["Endpoints"]["docker"]["Host"]
        except (IndexError, KeyError, TypeError):
            raise NativeRuntimeError("Docker Desktop's local context is unavailable.") from None
        if not isinstance(endpoint, str) or not endpoint.startswith("unix:///"):
            raise NativeRuntimeError("The desktop-linux context must use a local Unix socket; remote Docker hosts are not accepted.")
        info = self._json(["info", "--format", "{{json .}}"])
        if not isinstance(info, dict) or info.get("OSType") != "linux":
            raise NativeRuntimeError("Docker Desktop must be running its Linux engine.")
        return info

    def _source_fingerprint(self):
        """Hash build definitions and the locked download manifest, not caches."""
        if not (self.runtime_dir / "Dockerfile").is_file():
            raise NativeRuntimeError("The full-editor runtime build files are missing.")
        digest = hashlib.sha256()
        count = 0
        for path in sorted(self.runtime_dir.rglob("*")):
            relative = path.relative_to(self.runtime_dir)
            if any(part in {"__pycache__", ".git"} for part in relative.parts):
                continue
            if path.is_symlink():
                raise NativeRuntimeError("The runtime source contains a symlink.")
            if not path.is_file() or path.suffix == ".pyc":
                continue
            # Bundled packages are independently SHA-256 checked by prepare.py
            # and the image build. Their content hashes live in the lock file.
            if str(relative) not in BUILD_INPUTS:
                continue
            if path.stat().st_size > 2 * 1024 * 1024:
                raise NativeRuntimeError("Unexpected oversized runtime build definition.")
            digest.update(str(relative).encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
            count += 1
        if count < 2:
            raise NativeRuntimeError("The full-editor runtime source is incomplete.")
        digest.update((str(self.uid) + ":" + str(self.gid)).encode("ascii"))
        return digest.hexdigest()

    def _image_name(self):
        return "cinematicum-native-editors:" + self._source_fingerprint()[:20]

    def _image(self):
        data = self._json(["image", "inspect", self._image_name()], missing=True)
        if data is None:
            return None
        try:
            image = data[0]
            labels = image["Config"]["Labels"] or {}
            good = (labels.get(LABEL_PREFIX + "runtime") == RUNTIME_KIND and
                    labels.get(LABEL_PREFIX + "source") == self._source_fingerprint() and
                    labels.get(LABEL_PREFIX + "uid") == str(self.uid) and
                    labels.get(LABEL_PREFIX + "gid") == str(self.gid))
        except (KeyError, TypeError, IndexError):
            good = False
        if not good:
            raise NativeRuntimeError("The runtime image name belongs to an unverified image; it was not adopted or overwritten.")
        return image

    @staticmethod
    def _project_id(value):
        if not isinstance(value, str) or not PROJECT_ID.fullmatch(value):
            raise ValueError("Invalid project ID")
        return value

    def _project_paths(self, project_id, project_dir=None, create=False):
        project_id = self._project_id(project_id)
        projects = self.workspace / "projects"
        expected = projects / project_id
        if project_dir is not None and Path(os.path.abspath(str(project_dir))) != expected:
            raise NativeRuntimeError("Native editors can only mount the selected Studio project.")
        paths = {
            "project": expected,
            "media": expected / "media",
            "native": self.native_dir / project_id,
            "home": self.state_dir / "settings" / project_id,
            "password": self.state_dir / "auth" / (project_id + ".password"),
        }
        for path in (projects, expected, paths["media"], self.native_dir,
                     paths["native"], self.state_dir, self.state_dir / "settings",
                     paths["home"], self.state_dir / "auth", paths["password"]):
            if path.is_symlink():
                raise NativeRuntimeError("A native editor mount or state path is a symlink.")
        if create:
            if not expected.is_dir() or not paths["media"].is_dir():
                raise NativeRuntimeError("The selected Studio project or its media folder is missing.")
            _private_directory(paths["native"])
            _private_directory(paths["native"] / "exports")
            _private_directory(paths["home"])
        return paths

    def _password(self, project_id, create=False):
        path = self._project_paths(project_id)["password"]
        if create:
            try:
                fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, "w", encoding="ascii") as stream:
                    stream.write(secrets.token_urlsafe(36))
                    stream.flush()
                    os.fsync(stream.fileno())
        try:
            fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except OSError:
            raise NativeRuntimeError("The native editor authentication file is missing or unsafe.") from None
        with os.fdopen(fd, "r", encoding="ascii") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                    stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid()):
                raise NativeRuntimeError("The native editor authentication file must be owned by this user with mode 0600.")
            password = stream.read(129).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{40,100}", password):
            raise NativeRuntimeError("The native editor authentication file is invalid.")
        return password

    def _container_name(self, project_id):
        return "cinematicum-" + self.owner[:12] + "-" + self._project_id(project_id)

    def _inspect(self, project_id):
        data = self._json(["container", "inspect", self._container_name(project_id)], missing=True)
        if data is None:
            return None
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise NativeRuntimeError("Docker returned an invalid container description.")
        self._validate_container(project_id, data[0])
        return data[0]

    def _validate_container(self, project_id, data):
        paths = self._project_paths(project_id)
        labels = (data.get("Config") or {}).get("Labels") or {}
        config = data.get("Config") or {}
        host = data.get("HostConfig") or {}
        required = {
            "runtime": RUNTIME_KIND, "workspace": self.owner, "project": project_id,
            "uid": str(self.uid), "gid": str(self.gid),
        }
        if any(labels.get(LABEL_PREFIX + key) != value for key, value in required.items()):
            raise NativeRuntimeError("The named container is not owned by this CINEMATICUM workspace; it was not changed.")
        if (not HEX_DIGEST.fullmatch(str(labels.get(LABEL_PREFIX + "source", ""))) or
                not HEX_DIGEST.fullmatch(str(data.get("Id", ""))) or
                config.get("User") != str(self.uid) + ":" + str(self.gid)):
            raise NativeRuntimeError("The owned runtime has an invalid identity or user configuration.")
        expected_mounts = {
            "/projects/" + project_id: (paths["native"], True),
            "/media": (paths["media"], False),
            "/home/cinematicum": (paths["home"], True),
            "/run/cinematicum/password": (paths["password"], False),
        }
        actual = {}
        for mount in data.get("Mounts", []):
            if mount.get("Type") == "tmpfs" and mount.get("Destination") == "/tmp":
                continue
            destination = mount.get("Destination")
            if destination in actual or mount.get("Type") != "bind":
                raise NativeRuntimeError("The runtime has an unexpected mount.")
            actual[destination] = (Path(str(mount.get("Source", ""))), mount.get("RW"))
        if actual != expected_mounts:
            raise NativeRuntimeError("The runtime's project, media, settings, or authentication mounts do not match this project.")
        if (host.get("Privileged") or not host.get("ReadonlyRootfs") or
                "ALL" not in [str(v).upper() for v in host.get("CapDrop", [])] or
                not any(str(v).startswith("no-new-privileges") for v in host.get("SecurityOpt", []))):
            raise NativeRuntimeError("The runtime does not have the expected restricted container configuration.")
        bindings = (host.get("PortBindings") or {}).get(CONTAINER_PORT) or []
        if len(bindings) != 1 or bindings[0].get("HostIp") != "127.0.0.1":
            raise NativeRuntimeError("Native editor networking must be bound exclusively to loopback.")
        if set(host.get("PortBindings") or {}) != {CONTAINER_PORT}:
            raise NativeRuntimeError("The runtime exposes unexpected network ports.")

    @staticmethod
    def _port(data):
        ports = ((data.get("NetworkSettings") or {}).get("Ports") or {}).get(CONTAINER_PORT) or []
        if len(ports) != 1 or ports[0].get("HostIp") != "127.0.0.1":
            raise NativeRuntimeError("The native editor display has no private loopback port.")
        try:
            port = int(ports[0]["HostPort"])
        except (ValueError, TypeError, KeyError):
            raise NativeRuntimeError("The native editor display returned an invalid port.") from None
        if not 1 <= port <= 65535:
            raise NativeRuntimeError("The native editor display returned an invalid port.")
        return port

    def _session_status(self, project_id, data):
        state = data.get("State") or {}
        running = state.get("Running") is True
        result = {"project_id": project_id, "container_id": data["Id"][:12],
                  "running": running, "state": state.get("Status", "unknown"),
                  "mode": MODE, "native_project_directory": str(self.native_dir / project_id),
                  "unsaved_work_preserved_on_host_quit": True}
        if running:
            result["port"] = self._port(data)
        return result

    def _desktop_status(self, data):
        response = self._run(["container", "exec", data["Id"], "/usr/local/bin/cinematicum-control", "status"], timeout=12)
        try:
            result = json.loads(response.stdout)
        except (TypeError, ValueError):
            raise NativeRuntimeError("The native desktop returned an invalid readiness report.") from None
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise NativeRuntimeError("The native desktop could not report its readiness.")
        return result

    def status(self, project_id=None):
        result = {"available": False, "installed": False, "image_ready": False, "state": "unavailable",
                  "mode": MODE, "editors": [{"id": key, "name": name} for key, name in EDITOR_NAMES.items()],
                  "sessions": [], "errors": []}
        try:
            self._require_docker()
            result["available"] = True
            result["image_ready"] = self._image() is not None
            result["installed"] = result["image_ready"]
            result["state"] = "ready" if result["image_ready"] else "not_installed"
            if project_id is not None:
                identifiers = [self._project_id(project_id)]
            else:
                listing = self._run(["container", "ls", "--all", "--filter", "label=" + LABEL_PREFIX + "runtime=" + RUNTIME_KIND,
                                     "--filter", "label=" + LABEL_PREFIX + "workspace=" + self.owner,
                                     "--format", '{{.Label "' + LABEL_PREFIX + 'project"}}'])
                identifiers = sorted(set(listing.stdout.splitlines()))[:64]
            for identifier in identifiers:
                if not PROJECT_ID.fullmatch(identifier):
                    result["errors"].append("An owned runtime has an invalid project label and was ignored.")
                    continue
                try:
                    data = self._inspect(identifier)
                    if data is not None:
                        session = self._session_status(identifier, data)
                        result["sessions"].append(session)
                        if session["running"]:
                            desktop = self._desktop_status(data)
                            session["desktop_ready"] = desktop.get("ready") is True
                            session["complete_editor_set"] = desktop.get("complete_set") is True
                            session["editors"] = desktop.get("editors", [])
                except NativeRuntimeError as exc:
                    result["errors"].append(str(exc))
        except (NativeRuntimeError, ValueError, OSError) as exc:
            result["errors"].append(str(exc))
        result["error"] = " ".join(result["errors"])[:1200] or None
        return result

    def _stage_bundles(self, package_dir, destination):
        """Reuse verified package bytes across build-definition changes."""
        _private_directory(destination)
        manifest = package_dir / "engines.lock.json"
        if manifest.is_symlink() or not manifest.is_file():
            raise NativeRuntimeError("The verified editor package lock is missing or unsafe.")
        raw = manifest.read_bytes()
        try:
            lock = json.loads(raw)
            entries = lock["engines"]
        except (KeyError, TypeError, ValueError):
            raise NativeRuntimeError("The editor package lock is invalid.") from None
        if not isinstance(entries, list) or {x.get("id") for x in entries if isinstance(x, dict)} != set(EDITOR_NAMES) or len(entries) != 7:
            raise NativeRuntimeError("The editor package lock must contain all seven applications exactly once.")
        for item in entries:
            name, expected = item.get("archive"), item.get("sha256")
            if (not isinstance(name, str) or Path(name).name != name or not name or
                    not HEX_DIGEST.fullmatch(str(expected))):
                raise NativeRuntimeError("The editor package lock contains an unsafe archive identity.")
            source = package_dir / name
            if source.is_symlink() or not source.is_file() or source.stat().st_size != item.get("size"):
                raise NativeRuntimeError("A cached editor archive is missing, unsafe, or changed.")
            digest = hashlib.sha256()
            with source.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != expected:
                raise NativeRuntimeError("A cached editor archive failed its locked SHA-256 check.")
            target = destination / name
            if target.is_symlink():
                raise NativeRuntimeError("The editor build package path is a symlink.")
            temporary = destination / (".package-" + uuid.uuid4().hex)
            try:
                try:
                    os.link(source, temporary)
                except OSError:
                    shutil.copy2(source, temporary)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        lock_target = destination / "engines.lock.json"
        if lock_target.is_symlink():
            raise NativeRuntimeError("The editor build lock is a symlink.")
        temporary = destination / (".lock-" + uuid.uuid4().hex)
        try:
            temporary.write_bytes(raw)
            os.replace(temporary, lock_target)
        finally:
            temporary.unlink(missing_ok=True)

    def _long_command(self, argv, *, progress=None, cancel_event=None, timeout=3600):
        """Bound build output; cancellation signals only this owned CLI group."""
        tail = deque(maxlen=100)
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, env=self._env(), start_new_session=True)
        def consume():
            for line in iter(process.stdout.readline, b""):
                tail.append(line.decode("utf-8", errors="replace")[-1200:].rstrip())
        reader = threading.Thread(target=consume, daemon=True)
        reader.start()
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if (cancel_event is not None and cancel_event.is_set()) or time.monotonic() > deadline:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        process.wait(timeout=5)
                    raise NativeRuntimeError("Native editor installation cancelled." if cancel_event is not None and cancel_event.is_set() else "Native editor installation timed out.")
                time.sleep(0.15)
            reader.join(timeout=2)
            if process.returncode:
                raise NativeRuntimeError("Native editor installation failed:\n" + "\n".join(tail)[-6000:])
        finally:
            if process.stdout:
                process.stdout.close()

    def provision(self, progress=None, cancel_event=None):
        """Build verified complete application packages; caller runs this as a job."""
        with self._lock:
            self._require_docker()
            if self._image() is not None:
                return {"image_ready": True, "image": self._image_name(), "mode": MODE}
            if cancel_event is not None and cancel_event.is_set():
                raise NativeRuntimeError("Native editor installation cancelled.")
            if progress:
                progress(0.02)
            fingerprint = self._source_fingerprint()
            build = self.state_dir / "build" / fingerprint
            if build.is_symlink():
                raise NativeRuntimeError("Native editor build directory is a symlink.")
            build.mkdir(mode=0o700, exist_ok=True)
            for source in sorted(self.runtime_dir.rglob("*")):
                relative = source.relative_to(self.runtime_dir)
                if any(part in {"__pycache__", ".git", "bundles"} for part in relative.parts) or source.suffix == ".pyc":
                    continue
                if source.is_symlink():
                    raise NativeRuntimeError("The runtime build source contains a symlink.")
                destination = build / relative
                for candidate in (destination,) + tuple(destination.parents):
                    if candidate == build.parent:
                        break
                    if candidate.is_symlink():
                        raise NativeRuntimeError("The native editor build cache contains a symlink.")
                if source.is_dir():
                    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    if not destination.exists() or source.stat().st_size != destination.stat().st_size or source.name == "engines.lock.json" or "bundles" not in relative.parts:
                        shutil.copy2(source, destination)
            prepare = build / "prepare.py"
            if not prepare.is_file():
                raise NativeRuntimeError("The package acquisition and verification script is missing.")
            catalog = build / "engines.json"
            if catalog.is_symlink() or not catalog.is_file():
                raise NativeRuntimeError("The editor acquisition catalog is missing.")
            package_dir = _private_directory(self.state_dir / "packages" / hashlib.sha256(catalog.read_bytes()).hexdigest())
            # A prepared installer may already contain verified archives. Seed
            # once; later Dockerfile changes reuse this package cache unchanged.
            bundled = self.runtime_dir / "bundles"
            if not (package_dir / "engines.lock.json").exists() and (bundled / "engines.lock.json").is_file():
                self._stage_bundles(bundled, package_dir)
            self._long_command([sys.executable, str(prepare), "--output", str(package_dir), "--max-seconds", "3400"], cancel_event=cancel_event)
            self._long_command([sys.executable, str(prepare), "--output", str(package_dir), "--verify"], cancel_event=cancel_event)
            self._stage_bundles(package_dir, _private_directory(build / "bundles"))
            if self._source_fingerprint() != fingerprint:
                raise NativeRuntimeError("The runtime build definitions changed during installation. Retry with the current application.")
            if progress:
                progress(0.35)
            args = ["build", "--platform", "linux/amd64", "--progress", "plain",
                    "--build-arg", "APP_UID=" + str(self.uid), "--build-arg", "APP_GID=" + str(self.gid),
                    "--tag", "cinematicum-native-editors:" + fingerprint[:20]]
            for key, value in {"runtime": RUNTIME_KIND, "source": fingerprint, "uid": str(self.uid), "gid": str(self.gid)}.items():
                args.extend(["--label", LABEL_PREFIX + key + "=" + value])
            args.append(str(build))
            self._long_command(self._argv(args), cancel_event=cancel_event)
            if self._image() is None:
                raise NativeRuntimeError("Docker finished without the verified editor image.")
            if progress:
                progress(0.98)
            return {"image_ready": True, "image": self._image_name(), "mode": MODE}

    @staticmethod
    def _check_cancel(cancel_event):
        if cancel_event is not None and cancel_event.is_set():
            raise NativeRuntimeError("Opening native editors was cancelled. The owned session was preserved, including any unsaved documents.")

    def _wait_ready(self, project_id, timeout=90, cancel_event=None):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._check_cancel(cancel_event)
            data = self._inspect(project_id)
            if data is None or (data.get("State") or {}).get("Running") is not True:
                raise NativeRuntimeError("The native editor desktop stopped before it became ready. Its project files were preserved.")
            port = self._port(data)
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            try:
                connection.request("GET", "/")
                response = connection.getresponse()
                if response.status in (200, 301, 302, 401, 403):
                    desktop = self._desktop_status(data)
                    editors = desktop.get("editors", [])
                    if desktop.get("complete_set") is not True or not isinstance(editors, list) or {
                            item.get("id") for item in editors if isinstance(item, dict)} != set(EDITOR_NAMES):
                        raise NativeRuntimeError("The runtime does not contain the complete seven-editor set.")
                    if desktop.get("ready") is True:
                        result = self._session_status(project_id, data)
                        result.update(desktop_ready=True, complete_editor_set=True, editors=editors)
                        return result
            except (OSError, http.client.HTTPException):
                pass
            finally:
                connection.close()
            time.sleep(.25)
        raise NativeRuntimeError("The native editor desktop has not become ready. The owned container was left intact for diagnosis.")

    def start(self, project_dir, project_id, *, cancel_event=None):
        with self._lock:
            self._check_cancel(cancel_event)
            self._require_docker()
            paths = self._project_paths(project_id, project_dir, create=True)
            data = self._inspect(project_id)
            if data is not None:
                self._password(project_id)  # Never rotate a running session's key.
                if (data.get("State") or {}).get("Running") is not True:
                    self._run(["container", "start", data["Id"]], timeout=40)
                return self._wait_ready(project_id, cancel_event=cancel_event)
            image = self._image()
            if image is None:
                raise NativeRuntimeError("Install the full-editor runtime before opening a native workspace.")
            self._password(project_id, create=True)
            args = ["container", "run", "--detach", "--init", "--platform", "linux/amd64",
                    "--name", self._container_name(project_id), "--user", str(self.uid) + ":" + str(self.gid),
                    "--restart", "no", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                    "--pids-limit", "2048", "--shm-size", "1g", "--tmpfs", "/tmp:rw,nosuid,nodev,size=2g",
                    "--publish", "127.0.0.1::14500/tcp", "--env", "LIBGL_ALWAYS_SOFTWARE=1",
                    "--env", "HOME=/home/cinematicum"]
            for key, value in {"runtime": RUNTIME_KIND, "workspace": self.owner, "project": project_id,
                               "source": self._source_fingerprint(), "uid": str(self.uid), "gid": str(self.gid)}.items():
                args.extend(["--label", LABEL_PREFIX + key + "=" + value])
            for key, destination, readonly in (("native", "/projects/" + project_id, False), ("media", "/media", True),
                                               ("home", "/home/cinematicum", False), ("password", "/run/cinematicum/password", True)):
                args.extend(["--mount", _mount(paths[key], destination, readonly)])
            # The immutable ID just inspected closes the tag-replacement race.
            args.append(image["Id"])
            self._run(args, timeout=60)
            return self._wait_ready(project_id, cancel_event=cancel_event)

    def _wait_editor(self, project_id, editor_id, *, timeout=120, cancel_event=None):
        """An acknowledged process is not an editable workspace until it owns a window."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._check_cancel(cancel_event)
            data = self._inspect(project_id)
            if data is None or (data.get("State") or {}).get("Running") is not True:
                raise NativeRuntimeError("The native editor desktop stopped while opening " + EDITOR_NAMES[editor_id] + ". Project files were preserved.")
            desktop = self._desktop_status(data)
            editors = desktop.get("editors")
            editor = next((entry for entry in editors if isinstance(entry, dict) and entry.get("id") == editor_id), None) if isinstance(editors, list) else None
            if editor is None:
                raise NativeRuntimeError("The native desktop did not report the requested editor.")
            if editor.get("running") is not True:
                raise NativeRuntimeError(EDITOR_NAMES[editor_id] + " stopped before its editing window became ready. The owned session and project files were preserved.")
            windows = editor.get("windows")
            if editor.get("window_ready") is True and isinstance(windows, list) and windows:
                return {"id": editor_id, "running": True, "window_ready": True,
                        "window_count": len(windows), "version": str(editor.get("version", ""))[:100]}
            time.sleep(.25)
        raise NativeRuntimeError(EDITOR_NAMES[editor_id] + " has not opened an editing window yet. The owned session was left running for recovery.")

    def open_editor(self, editor_id, project_id, project_dir, *, cancel_event=None):
        if editor_id not in EDITOR_NAMES:
            raise ValueError("Unknown native editor")
        with self._lock:
            result = self.start(project_dir, project_id, cancel_event=cancel_event)
            self._check_cancel(cancel_event)
            data = self._inspect(project_id)
            reply = self._run(["container", "exec", data["Id"], "/usr/local/bin/cinematicum-open", editor_id, project_id], timeout=45)
            try:
                details = json.loads(reply.stdout)
            except (ValueError, TypeError):
                raise NativeRuntimeError("The editor did not return a valid launch acknowledgement.") from None
            if not isinstance(details, dict) or details.get("error") or details.get("ok") is False:
                reason = details.get("error", "invalid response") if isinstance(details, dict) else "invalid response"
                raise NativeRuntimeError("The native editor could not be opened: " + str(reason)[:600])
            result["editor"] = editor_id
            result["editor_name"] = EDITOR_NAMES[editor_id]
            result["launch"] = self._wait_editor(project_id, editor_id, cancel_event=cancel_event)
            return result

    def access(self, project_id):
        """Sensitive result: only expose through an authenticated access endpoint.

        Never persist this payload in jobs, bootstrap responses, or logs. The
        caller proxies this loopback endpoint and keeps the password in memory.
        """
        with self._lock:
            self._require_docker()
            data = self._inspect(project_id)
            if data is None or (data.get("State") or {}).get("Running") is not True:
                raise NativeRuntimeError("The native workspace is not running.")
            port = self._port(data)
            return {"project_id": project_id, "port": port, "url": "http://127.0.0.1:" + str(port) + "/",
                    "username": "cinematicum", "password": self._password(project_id)}

    def command(self, project_id, action):
        """Forward only established edit shortcuts to the focused native editor."""
        if action not in {"save", "undo", "redo"}:
            raise ValueError("Unknown native editor command")
        with self._lock:
            self._require_docker()
            data = self._inspect(project_id)
            if data is None or (data.get("State") or {}).get("Running") is not True:
                raise NativeRuntimeError("The native workspace is not running.")
            result = self._run(["container", "exec", data["Id"], "/usr/local/bin/cinematicum-control", "key", action])
            try:
                reply = json.loads(result.stdout)
            except (TypeError, ValueError):
                raise NativeRuntimeError("The native editor did not acknowledge the command.") from None
            if not isinstance(reply, dict) or reply.get("error") or reply.get("ok") is False:
                raise NativeRuntimeError("The native editor could not apply the command.")
            return {"project_id": project_id, "action": action, "sent": True}

    def stop(self, project_id, *, confirmed=False):
        if confirmed is not True:
            raise NativeRuntimeError("Stopping native editors can discard unsaved documents. Save them and explicitly confirm stopping this project.")
        with self._lock:
            self._require_docker()
            data = self._inspect(project_id)
            if data is None:
                return {"project_id": self._project_id(project_id), "state": "absent", "running": False}
            if (data.get("State") or {}).get("Running") is True:
                self._run(["container", "stop", "--time", "30", data["Id"]], timeout=45)
            stopped = self._inspect(project_id)
            if stopped is None:
                return {"project_id": project_id, "state": "absent", "running": False}
            return self._session_status(project_id, stopped)

    def shutdown(self):
        # Closing Studio is not evidence that every native application saved its
        # document. Keep sessions and buffers alive, reconnect on the next open.
        return {"native_sessions_preserved": True}
