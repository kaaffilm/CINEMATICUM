"""Project-owned authoring tools, immutable job outputs and their HTTP contracts.

Heavy scientific engines live in isolated workers. This module is standard
library only so opening an existing project never imports an optional engine.
Each registered tool still validates its own document and executes real work;
the registry only shares persistence, cancellation and artifact ownership.
"""
from __future__ import annotations

import copy
import importlib
from pathlib import Path
import re
import shutil
import stat
import tempfile


TOOLS = {
    "deep-compositing": {
        "module": "deep_compositing", "field": "deep_compositing",
        "validate": "validate_project_deep", "recipe": "validate_deep_recipe",
        "capabilities": "deep_capabilities", "run": "run_deep_compositing",
        "directory": "deep", "route": "deep-render", "admit": True,
        "label": "Deep composite", "preview": "preview.png",
    },
    "ray-optics": {
        "module": "ray_optics", "field": "ray_optics",
        "validate": "validate_optical_prescription", "recipe": "validate_ray_optics_recipe",
        "capabilities": "ray_optics_capabilities", "run": "run_ray_optics",
        "directory": "optics", "route": "ray-optics", "admit": False,
        "label": "Optical analysis", "preview": None,
    },
    "physical-rendering": {
        "module": "physical_rendering", "field": "physical_rendering",
        "validate": "validate_settings", "recipe": "validate_recipe",
        "capabilities": "capabilities", "run": "run",
        "directory": "physical", "route": "physical-rendering", "admit": True,
        "label": "Physical render", "preview": "preview.png",
        "receipt": "provenance.json", "recipe_project": True, "document_scene": True,
    },
    "scene-processing": {
        "module": "scene_processing", "field": "scene_processing",
        "validate": "validate_scene_graph", "recipe": "validate_scene_processing_recipe",
        "capabilities": "scene_processing_capabilities", "run": "run_scene_processing",
        "directory": "scene-processing", "route": "scene-processing", "admit": True,
        "label": "Scene graph render", "preview": "preview.mp4", "recipe_project": True,
    },
    "reconstruction": {
        "module": "reconstruction", "field": "reconstruction",
        "validate": "validate_settings", "recipe": "validate_recipe",
        "capabilities": "capabilities", "run": "run",
        "directory": "reconstruction", "route": "reconstruction", "admit": False,
        "label": "Photo reconstruction", "preview": "preview.png",
        "receipt": "provenance.json", "recipe_project": True,
    },
    "lens-calibration": {
        "module": "lens_calibration", "field": None,
        "recipe": "validate_recipe", "capabilities": "capabilities", "run": "run",
        "directory": "lens-calibration", "route": "lens-calibration", "admit": False,
        "label": "Measured lens calibration", "preview": "preview.png",
        "receipt": "provenance.json", "recipe_project": True,
    },
    "meshroom": {
        "module": "meshroom_reconstruction", "field": None,
        "recipe": "validate_recipe", "capabilities": "capabilities", "run": "run",
        "directory": "meshroom", "route": "meshroom", "admit": False,
        "label": "Meshroom dense reconstruction", "preview": None,
        "receipt": "provenance.json", "recipe_project": True,
    },
    "camera-control": {
        "module": "camera_ctrl", "field": None,
        "recipe": "validate_recipe", "capabilities": "capabilities", "run": "run",
        "directory": "camera-control", "route": "camera-control", "admit": False,
        "label": "CameraCtrl generation", "preview": "video.mp4",
        "receipt": "provenance.json", "recipe_project": True,
    },
    "diffusionlight": {
        "module": "diffusionlight", "field": None,
        "recipe": "validate_recipe", "capabilities": "capabilities", "run": "run",
        "directory": "diffusionlight", "route": "diffusionlight", "admit": False,
        "label": "DiffusionLight HDR", "preview": None,
        "receipt": "provenance.json", "recipe_project": True,
    },
    "learned-tracking": {
        "module": "learned_tracking", "field": None,
        "capabilities": "learned_capabilities", "directory": "learned",
        "label": "Learned masks and points", "preview": "preview.png",
    },
}
IDENTIFIER = re.compile(r"^[a-f0-9]{32}$")


def implementation(tool):
    if tool not in TOOLS:
        raise ValueError("Unknown authoring tool")
    spec = TOOLS[tool]
    name = ("." if __package__ else "") + spec["module"]
    return spec, importlib.import_module(name, __package__ or None)


def validate_authoring_documents(project, project_dir=None):
    """Normalize present documents without changing projects without a tool."""
    for key, spec in TOOLS.items():
        if spec["field"] and spec["field"] in project:
            _, module = implementation(key)
            value = project[spec["field"]]
            if value is None:
                project.pop(spec["field"])
            else:
                options = {"scene": project.get("settings", {}).get("scene")} if spec.get("document_scene") else {}
                project[spec["field"]] = getattr(module, spec["validate"])(value, **options)
                if key == "deep-compositing" and project_dir is not None:
                    for node in project[spec["field"]]["nodes"]:
                        if node["op"] == "source":
                            source = module._source(project_dir, node["source_id"], verify=False)
                            if node["part"] >= len(source["parts"]):
                                raise ValueError("The selected EXR source part does not exist")
    return project


def capabilities(tool):
    spec, module = implementation(tool)
    return getattr(module, spec["capabilities"])()


def apply_document(store, project_id, payload):
    """Validate/save an authored edit atomically before the UI changes history."""
    if (not isinstance(payload, dict) or not {"tool", "document", "project"} <= set(payload)
            or set(payload) - {"tool", "document", "project", "scene"}
            or not isinstance(payload["project"], dict) or payload["project"].get("id") != project_id):
        raise ValueError("An authoring edit requires its exact current project and document")
    tool = payload["tool"]
    if not isinstance(tool, str) or tool not in TOOLS or not TOOLS[tool]["field"]:
        raise ValueError("Unknown authoring tool")
    project = copy.deepcopy(payload["project"])
    if "scene" in payload:
        if tool not in {"physical-rendering", "scene-processing", "reconstruction"}:
            raise ValueError("This authoring tool does not import authored scenes")
        from scene import validate_scene
        scene = validate_scene(payload["scene"])
        if (scene["width"], scene["height"]) != (project.get("width"), project.get("height")):
            raise ValueError("The imported scene resolution differs from this project. Change the project resolution explicitly before applying the scene.")
        project.setdefault("settings", {})["scene"] = scene
    field = TOOLS[tool]["field"]
    if payload["document"] is None:
        project.pop(field, None)
    else:
        project[field] = copy.deepcopy(payload["document"])
    return store.save(project_id, project)


def _owned_artifact(project_dir, relative):
    """Reject symlink components as well as lexical path escapes."""
    root = Path(project_dir)
    relative = Path(relative)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("Invalid authoring artifact path")
    candidate = root
    for component in relative.parts:
        candidate = candidate / component
        if candidate.is_symlink():
            raise ValueError("Authoring artifacts must not contain symbolic links")
    if candidate.resolve().parent != (root.resolve() / relative.parent):
        raise ValueError("Authoring artifact is outside its project")
    if not stat.S_ISREG(candidate.stat().st_mode):
        raise ValueError("Authoring artifact must be a regular file")
    return candidate


def run_tool(store, project_id, tool, payload):
    """Submit one validated immutable recipe to the application's owned queue."""
    if not isinstance(payload, dict) or set(payload) != {"recipe"}:
        raise ValueError("Authoring requires one recipe")
    spec, module = implementation(tool)
    project = store.get(project_id)
    arguments = (copy.deepcopy(payload["recipe"]), project) if spec.get("recipe_project") else (copy.deepcopy(payload["recipe"]),)
    recipe = getattr(module, spec["recipe"])(*arguments)
    directory = store.project_dir(project_id)
    artifact_names = frozenset(module.ARTIFACT_NAMES)
    if not artifact_names or any(Path(name).name != name for name in artifact_names):
        raise RuntimeError("The authoring tool has an invalid artifact contract")

    def work(job_id, progress, event):
        output = directory / spec["directory"] / "outputs" / job_id
        result = getattr(module, spec["run"])(project, directory, recipe, output,
                                               progress=progress, cancel_event=event)
        return publish_result(store, project_id, tool, job_id, result, cancel_event=event)

    return store.submit(project_id, tool, work, {"project": project, "recipe": recipe})


def publish_result(store, project_id, tool, output_id, result, cancel_event=None):
    """Expose only an immutable, independently verified published artifact set.

Worker return follows its atomic output commit. A late cancellation can defer
preview admission, but cannot relabel an already published result as cancelled.
The distributed dispatcher uses its stable batch identity across retries.
"""
    if not IDENTIFIER.fullmatch(output_id) or not isinstance(result, dict):
        raise RuntimeError("Authoring worker returned an invalid owned result")
    spec, module = implementation(tool)
    # Shutdown can begin after worker publication. Its owned project still
    # exists until this job finishes, even though new Store operations close.
    directory = store.root / "projects" / project_id
    urls = {}
    base = f"/api/projects/{project_id}/{spec['directory']}/outputs/{output_id}"
    for name in sorted(module.ARTIFACT_NAMES):
        relative = Path(spec["directory"]) / "outputs" / output_id / name
        if (directory / relative).exists():
            _owned_artifact(directory, relative)
            urls[name] = base + "/" + name
    receipt_name = spec.get("receipt", "receipt.json")
    if receipt_name not in urls:
        raise RuntimeError("Authoring worker did not publish its provenance receipt")
    from imaging import _hash_file, _read_json
    receipt_path = _owned_artifact(directory, Path(spec["directory"]) / "outputs" / output_id / receipt_name)
    receipt = _read_json(receipt_path, 8 * 1024 * 1024)
    entries = receipt.get("artifacts") if isinstance(receipt, dict) else None
    if isinstance(entries, dict):
        entries = [dict(value, filename=value.get("filename", key)) for key, value in entries.items() if isinstance(value, dict)]
    if not isinstance(entries, list) or not entries:
        raise ValueError("The published authoring result lacks its artifact inventory")
    expected = {}
    for entry in entries:
        if (not isinstance(entry, dict) or entry.get("filename") not in module.ARTIFACT_NAMES - {receipt_name}
                or entry["filename"] in expected):
            raise ValueError("The published authoring result has invalid or duplicate artifact identities")
        expected[entry["filename"]] = entry
    if set(urls) != set(expected) | {receipt_name}:
        raise ValueError("The published authoring files differ from the receipt inventory")
    for name, entry in expected.items():
        path = _owned_artifact(directory, Path(spec["directory"]) / "outputs" / output_id / name)
        if _hash_file(path, getattr(module, "MAX_ARTIFACT_BYTES", 1024 ** 3)) != (entry.get("sha256"), entry.get("size", entry.get("bytes"))):
            raise ValueError("The published authoring artifact differs from its recorded bytes")
    result.update(output_id=output_id, artifact_urls=urls, receipt_url=urls[receipt_name])
    if spec["preview"] and spec["preview"] in urls:
        result["display_url"] = urls[spec["preview"]]
    if "composite.exr" in urls:
        result["exr_url"] = urls["composite.exr"]
    if tool == "scene-processing":
        result["provenance"] = {"type": "cinematicum-scene-processing", "version": 1,
                                "output_id": output_id, "graph_sha256": receipt["graph_sha256"],
                                "receipt_sha256": _hash_file(receipt_path, 8 * 1024 * 1024)[0]}
    if spec["admit"] and spec["preview"] in urls:
        with store.lock:
            if store._closing or cancel_event is not None and cancel_event.is_set():
                result["preview_admission"] = "The published preview remains in Saved results; media admission was deferred during cancellation or shutdown."
                return result
            name = spec["preview"]
            source = _owned_artifact(directory, Path(spec["directory"]) / "outputs" / output_id / name)
            with tempfile.TemporaryDirectory(prefix="authoring-admit-", dir=str(directory)) as temp:
                selected = Path(temp) / name
                shutil.copyfile(source, selected)
                asset = store.admit(project_id, selected, spec["label"] + " " + output_id[:8] + Path(name).suffix,
                                    result.get("provenance"))
            result.update(asset=asset, url=f"/api/projects/{project_id}/media/{asset['id']}")
    return result


def artifact(store, project_id, directory_name, job_id, filename):
    matches = [(tool, spec) for tool, spec in TOOLS.items() if spec["directory"] == directory_name]
    if not matches or not IDENTIFIER.fullmatch(job_id):
        raise ValueError("Invalid authoring artifact")
    tool, spec = matches[0]
    _, module = implementation(tool)
    if filename not in module.ARTIFACT_NAMES:
        raise ValueError("Invalid authoring artifact")
    directory = store.project_dir(project_id)
    relative = Path(directory_name) / "outputs" / job_id
    receipt_name = spec.get("receipt", "receipt.json")
    # A portable project keeps its immutable outputs but deliberately does not
    # import another machine's job database. Authority is this project's
    # atomically published, hash-verified artifact set, not a transient job row.
    from imaging import _hash_file, _read_json
    receipt_path = _owned_artifact(directory, relative / receipt_name)
    receipt = _read_json(receipt_path, 8 * 1024 * 1024)
    records = receipt.get("artifacts") if isinstance(receipt, dict) else None
    if isinstance(records, dict):
        records = [dict(value, filename=value.get("filename", key))
                   for key, value in records.items() if isinstance(value, dict)]
    if not isinstance(records, list) or not records:
        raise ValueError("Authoring output has no artifact identities")
    identities = {}
    for record in records:
        if (not isinstance(record, dict) or record.get("filename") not in module.ARTIFACT_NAMES
                or record["filename"] == receipt_name or record["filename"] in identities):
            raise ValueError("Authoring output has an invalid artifact inventory")
        identities[record["filename"]] = record
    if filename == receipt_name:
        return receipt_path
    if filename not in identities:
        raise FileNotFoundError("This authoring output does not contain the selected artifact")
    path = _owned_artifact(directory, relative / filename)
    expected = identities[filename]
    if _hash_file(path, getattr(module, "MAX_ARTIFACT_BYTES", 1024 ** 3)) != (expected.get("sha256"), expected.get("size", expected.get("bytes"))):
        raise ValueError("The authoring artifact no longer matches its published identity")
    return path


def import_deep(store, project_id, incoming, name):
    from deep_compositing import import_deep_source
    with store.lock:
        store._require_open()
        return import_deep_source(store.project_dir(project_id), incoming, name)


def list_results(store, project_id, limit=30):
    """List immutable outputs across reopening and portable project restoration."""
    from imaging import _read_json
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Result history limit must be between 1 and 100")
    directory = store.project_dir(project_id)
    records = []
    for tool, spec in TOOLS.items():
        root = directory / spec["directory"] / "outputs"
        if not root.exists():
            continue
        if (directory / spec["directory"]).is_symlink() or root.is_symlink() or not root.is_dir():
            raise ValueError("The authoring result directory is not owned by this project")
        _, module = implementation(tool)
        count = 0
        for output in root.iterdir():
            count += 1
            if count > 4096:
                raise ValueError("The authoring output directory exceeds its history inspection limit")
            if not IDENTIFIER.fullmatch(output.name):
                continue
            receipt_name = spec.get("receipt", "receipt.json")
            receipt_path = _owned_artifact(directory, Path(spec["directory"]) / "outputs" / output.name / receipt_name)
            receipt = _read_json(receipt_path, 8 * 1024 * 1024)
            entries = receipt.get("artifacts") if isinstance(receipt, dict) else None
            if isinstance(entries, dict):
                entries = [dict(value, filename=value.get("filename", key))
                           for key, value in entries.items() if isinstance(value, dict)]
            if not isinstance(entries, list) or not entries:
                raise ValueError("A saved authoring result has no artifact inventory")
            names = [entry.get("filename") for entry in entries if isinstance(entry, dict)]
            if len(names) != len(entries) or len(set(names)) != len(names) or not set(names) <= module.ARTIFACT_NAMES - {receipt_name}:
                raise ValueError("A saved authoring result has an invalid artifact inventory")
            base = f"/api/projects/{project_id}/{spec['directory']}/outputs/{output.name}/"
            records.append({"tool": tool, "label": spec["label"], "output_id": output.name,
                            "modified_at": receipt_path.stat().st_mtime,
                            "artifact_urls": {name: base + name for name in sorted(names + [receipt_name])}})
    return sorted(records, key=lambda row: (row["modified_at"], row["output_id"]), reverse=True)[:limit]
