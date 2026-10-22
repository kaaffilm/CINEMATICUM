"""Studio ownership for explicitly paired scene workers and durable batches.

Private credentials, listener configuration and dispatch databases remain in
the workspace service directory. Only graph data and verified render artifacts
enter a project. Constructing this manager never listens or contacts a peer.
"""
from __future__ import annotations

import copy
from pathlib import Path
import re
import threading
from urllib.parse import urlsplit

from collaboration_store import _directory, _read, _write
from scene_dispatch import (Dispatcher, DispatchError, RenderClient, RenderWorker,
                            start_render_worker)
from scene_processing import (_identifier, compile_scene_graph, validate_context,
                              validate_scene_graph)

_ID = re.compile(r"[a-f0-9]{32}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")


def _payload(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or not set(required) <= set(value):
        raise ValueError("The scene-worker request contains missing or unsupported properties.")
    return value


def _id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("An exact owned scene batch identity is required.")
    return value


class SceneDispatchStore:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.root = _directory(store.root / "scene-services")
        self.bindings = _directory(self.root / "bindings")
        self.workers = _directory(self.root / "workers")
        self.records = _directory(self.root / "batches")
        self.services = {}

    def _binding_path(self, name):
        return self.bindings / (_identifier(name, "Worker name") + ".json")

    def _binding(self, name):
        value = _read(self._binding_path(name))
        if (not isinstance(value, dict) or value.get("version") != 1 or value.get("name") != name
                or type(value.get("local")) is not bool):
            raise ValueError("The saved worker binding is inconsistent.")
        client = RenderClient(value.get("connection"))
        client._headers()
        _id(client.binding.get("client_id"))
        if value["local"]:
            config = value.get("listener")
            _payload(config, {"host", "port", "advertise_host", "slots"}, {"host", "port", "slots"})
            if type(config["port"]) is not int or config["port"] != client.port:
                raise ValueError("The saved listener differs from its paired worker endpoint.")
        return value

    def inventory(self):
        with self.lock:
            self.store._require_open()
            rows = []
            paths = sorted(self.bindings.glob("*.json"))
            if len(paths) > 8:
                raise ValueError("The workspace exceeds its eight-worker pairing limit.")
            for path in paths:
                record = self._binding(path.stem)
                binding = record["connection"]
                rows.append({"name": path.stem, "local": record["local"],
                             "running": path.stem in self.services if record["local"] else None,
                             "endpoint": binding["url"], "worker_id": binding["session_id"],
                             "client_id": binding["client_id"],
                             "certificate_sha256": binding["certificate_sha256"]})
            return {"version": 1, "workers": rows,
                    "startup": "Listeners and remote connections start only after an explicit request."}

    def _new_name(self, name):
        path = self._binding_path(name)
        if path.exists() or path.is_symlink():
            raise ValueError("That worker name is already paired. Its identity was preserved.")
        if len(list(self.bindings.glob("*.json"))) >= 8:
            raise ValueError("A workspace supports at most eight paired workers.")
        return path

    def start(self, payload):
        _payload(payload, {"name", "host", "port", "advertise_host", "slots"}, {"name"})
        name = _identifier(payload["name"], "Worker name")
        with self.lock:
            self.store._require_open()
            existing = self._binding(name) if self._binding_path(name).exists() else None
            if existing:
                if not existing["local"]:
                    raise ValueError("This name belongs to a paired remote worker.")
                config = existing["listener"]
                if any(key != "name" and value != config.get(key) for key, value in payload.items()):
                    raise ValueError("Resume this worker using its saved listener identity and port.")
            else:
                self._new_name(name)
                config = {"host": payload.get("host", "127.0.0.1"), "port": payload.get("port", 0),
                          "advertise_host": payload.get("advertise_host"), "slots": payload.get("slots", 1)}
            if name in self.services:
                return self.inventory()
            worker = RenderWorker(self.workers / name, slots=config["slots"])
            service = None
            try:
                if existing and worker.worker_id != existing["connection"]["session_id"]:
                    raise ValueError("The local worker database no longer matches its saved pairing.")
                service = start_render_worker(worker, host=config["host"], port=config["port"],
                                              advertise_host=config.get("advertise_host"))
                if existing:
                    connection = existing["connection"]
                    if (service.url != connection["url"]
                            or service.certificate_sha256 != connection["certificate_sha256"]):
                        raise ValueError("The resumed worker TLS identity differs from its saved pairing.")
                else:
                    connection = worker.pair_owner("Studio owner")
                    config["port"] = urlsplit(service.url).port
                    _write(self._binding_path(name), {"version": 1, "name": name, "local": True,
                                                     "connection": connection, "listener": config})
                self.services[name] = (worker, service)
                return self.inventory()
            except BaseException:
                if service is not None:
                    service.close()
                worker.close()
                raise

    def pair(self, payload):
        _payload(payload, {"name", "invitation", "participant_name"}, {"name", "invitation", "participant_name"})
        name = _identifier(payload["name"], "Worker name")
        with self.lock:
            self.store._require_open()
            path = self._new_name(name)
            connection = RenderClient.join(payload["invitation"], payload["participant_name"])
            RenderClient(connection)._headers()
            _write(path, {"version": 1, "name": name, "local": False, "connection": connection})
            return self.inventory()

    def invite(self, payload):
        _payload(payload, {"name", "expires_seconds"}, {"name"})
        with self.lock:
            self.store._require_open()
            connection = self._binding(payload["name"])["connection"]
            return RenderClient(connection).invite(payload.get("expires_seconds", 600))

    def revoke(self, payload):
        _payload(payload, {"name", "client_id"}, {"name", "client_id"})
        with self.lock:
            self.store._require_open()
            connection = self._binding(payload["name"])["connection"]
            return RenderClient(connection).revoke(_id(payload["client_id"]))

    def stop(self, payload):
        _payload(payload, {"name"}, {"name"})
        with self.lock:
            self.store._require_open()
            record = self._binding(payload["name"])
            if not record["local"]:
                raise ValueError("Only a local owned worker can be stopped by this Studio instance.")
            pair = self.services.pop(payload["name"], None)
            if pair:
                worker, service = pair
                service.close()
                worker.close()
            return self.inventory()

    def _dispatcher(self, names):
        if (not isinstance(names, list) or not 1 <= len(names) <= 8
                or any(not isinstance(name, str) for name in names) or len(set(names)) != len(names)):
            raise ValueError("Select one to eight distinct paired worker names.")
        return Dispatcher(self.root / "dispatcher", {name: self._binding(name)["connection"] for name in names})

    def _record(self, project_id, batch_id):
        self.store.project_dir(project_id)
        record = _read(self.records / (_id(batch_id) + ".json"))
        if (not isinstance(record, dict) or record.get("version") != 1 or record.get("project_id") != project_id
                or record.get("batch_id") != batch_id or not isinstance(record.get("request_sha256"), str)
                or not _SHA.fullmatch(record["request_sha256"])):
            raise FileNotFoundError("This scene batch does not belong to the selected project.")
        if record.get("job_id") is not None:
            _id(record["job_id"])
        return record

    def _recover_job(self, record):
        """Recover admission after a crash between the job and mapping writes."""
        if record.get("job_id"):
            job = self.store.jobs.get(record["job_id"])
            if job is None or job.get("project_id") != record["project_id"] or job.get("kind") != "scene-dispatch":
                raise ValueError("The scene batch's saved Studio job identity is inconsistent.")
            return copy.deepcopy(job)
        matches = []
        for job in self.store.jobs.values():
            if job.get("project_id") != record["project_id"] or job.get("kind") != "scene-dispatch":
                continue
            path = self.store.root / "jobs" / (job["id"] + ".snapshot")
            if path.exists():
                identity = _read(path).get("scene_dispatch", {})
                if identity == {"batch_id": record["batch_id"], "request_sha256": record["request_sha256"]}:
                    matches.append(job)
        if matches:
            job = max(matches, key=lambda row: row["created_at"])
            record["job_id"] = job["id"]
            _write(self.records / (record["batch_id"] + ".json"), record)
            return copy.deepcopy(job)
        return None

    @staticmethod
    def _public(batch, record, job=None):
        result = copy.deepcopy(batch)
        result.pop("output", None)
        result.update(project_id=record["project_id"], output_id=record["batch_id"],
                      job_id=job["id"] if job else record.get("job_id"))
        return result

    def status(self, project_id, batch_id=None):
        with self.lock:
            self.store.project_dir(project_id)
            if batch_id is None:
                paths = sorted(self.records.glob("*.json"))
                if len(paths) > 4096:
                    raise ValueError("The scene batch history exceeds its inspection bound.")
                rows = []
                for path in paths:
                    if _read(path).get("project_id") == project_id:
                        rows.append(self.status(project_id, path.stem))
                return {"batches": sorted(rows, key=lambda row: row["created"], reverse=True)}
            record = self._record(project_id, batch_id)
            dispatcher = self._dispatcher(record["workers"])
            batch = dispatcher.status(batch_id)
            if batch["request_sha256"] != record["request_sha256"]:
                raise ValueError("The private dispatch database no longer matches its project ownership record.")
            return self._public(batch, record, self._recover_job(record))

    def submit(self, project_id, payload):
        _payload(payload, {"graph", "contexts", "frames", "workers", "operation_id"},
                 {"graph", "contexts", "frames", "workers", "operation_id"})
        operation = payload["operation_id"]
        if not isinstance(operation, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", operation):
            raise ValueError("An explicit idempotent scene-dispatch operation identity is required.")
        graph = validate_scene_graph(payload["graph"])
        with self.lock:
            project = self.store.get(project_id)
            contexts, frames = payload["contexts"], payload["frames"]
            if (not isinstance(contexts, list) or not 1 <= len(contexts) <= 16
                    or not isinstance(frames, list) or not 1 <= len(frames) * len(contexts) <= 64):
                raise ValueError("Choose one to sixteen context variations and one to sixty-four total frame tasks.")
            for context in contexts:
                if not isinstance(context, dict) or "frame" in context:
                    raise ValueError("Context variations are objects; choose batch frames separately.")
                for frame in frames:
                    normalized = validate_context({**context, "frame": frame}, graph["context"])
                    scene = compile_scene_graph(graph, {key: value for key, value in normalized.items() if key != "time"})["scene"]
                    if (scene["width"], scene["height"]) != (project["width"], project["height"]):
                        raise ValueError("Distributed scene resolution differs from the current project.")
            dispatcher = self._dispatcher(payload["workers"])
            # The Dispatcher validates and compiles every variation before it
            # creates a durable batch; no remote work has started at this point.
            batch = dispatcher.submit(graph, contexts=payload["contexts"], frames=payload["frames"],
                                      operation_id=project_id + "_" + operation)
            path = self.records / (batch["id"] + ".json")
            if path.exists() or path.is_symlink():
                record = self._record(project_id, batch["id"])
                if record["request_sha256"] != batch["request_sha256"]:
                    raise ValueError("The scene batch ownership identity changed.")
                job = self._recover_job(record)
                if job:
                    return {"batch": self._public(batch, record, job), "job": job}
            else:
                record = {"version": 1, "project_id": project_id, "batch_id": batch["id"],
                          "request_sha256": batch["request_sha256"], "workers": sorted(payload["workers"]), "job_id": None}
                _write(path, record)
            return self._queue(record, dispatcher)

    def _queue(self, record, dispatcher):
        project_id, batch_id = record["project_id"], record["batch_id"]
        directory = self.store.project_dir(project_id)

        def work(job_id, progress, event):
            output = directory / "scene-processing" / "outputs" / batch_id
            result = dispatcher.run(batch_id, output, progress=progress, cancel_event=event)
            from studio_tools import publish_result
            return publish_result(self.store, project_id, "scene-processing", batch_id, result, cancel_event=event)

        snapshot = {"scene_dispatch": {"batch_id": batch_id, "request_sha256": record["request_sha256"]}}
        job = self.store.submit(project_id, "scene-dispatch", work, snapshot)
        record["job_id"] = job["id"]
        _write(self.records / (batch_id + ".json"), record)
        return {"batch": self._public(dispatcher.status(batch_id), record, job), "job": job}

    def control(self, project_id, batch_id, operation, payload):
        _payload(payload, set())
        if operation not in {"cancel", "retry", "resume"}:
            raise ValueError("Choose cancel, retry or resume for an owned scene batch.")
        with self.lock:
            record = self._record(project_id, batch_id)
            dispatcher = self._dispatcher(record["workers"])
            batch = dispatcher.status(batch_id)
            if batch["request_sha256"] != record["request_sha256"]:
                raise ValueError("The scene batch ownership identity changed.")
            job = self._recover_job(record)
            if operation == "cancel":
                if job and job["state"] in {"queued", "running"}:
                    job = self.store.cancel(job["id"])
                batch = dispatcher.cancel(batch_id)
                if not job or job["state"] not in {"queued", "running"}:
                    event = threading.Event()
                    event.set()
                    try:
                        output = self.store.project_dir(project_id) / "scene-processing" / "outputs" / batch_id
                        dispatcher.run(batch_id, output, cancel_event=event)
                    except DispatchError as error:
                        if error.code != "cancelled":
                            raise
                    batch = dispatcher.status(batch_id)
                return {"batch": self._public(batch, record, job), "job": job}
            if job and job["state"] in {"queued", "running"}:
                return {"batch": self._public(batch, record, job), "job": job}
            if operation == "retry":
                dispatcher.retry(batch_id)
            elif batch["status"] in {"failed", "cancelled", "interrupted"}:
                raise DispatchError("Use Retry for a settled failed, interrupted or cancelled batch.", status=409)
            if batch["status"] == "completed" and job and job["state"] == "completed":
                return {"batch": self._public(batch, record, job), "job": job}
            return self._queue(record, dispatcher)

    def close(self):
        with self.lock:
            for worker, service in self.services.values():
                service.close()
                worker.close()
            self.services.clear()
