"""Read a completed scene's .blend; do not render or save user preferences."""
import bpy
import json
from pathlib import Path
import sys

args = sys.argv[sys.argv.index("--") + 1:]
expected = json.loads(Path(args[0]).read_text())
scene = bpy.context.scene
recipe = json.loads(bpy.data.texts["CINEMATICUM Scene Recipe.json"].as_string())
receipt = json.loads(scene["cinematicum_render_device"])
checks = {
    "saved_cycles_gpu": scene.render.engine == "CYCLES" and scene.cycles.device == "GPU",
    "saved_receipt_matches_completed_render": receipt == expected["render_device"],
    "saved_recipe_matches_completed_snapshot": recipe == expected["scene"],
    "saved_metal_request": recipe["render"]["device"] == "METAL",
    "saved_samples_and_denoising": scene.cycles.samples == 4 and scene.cycles.use_denoising is False,
    "saved_resolution": (scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage) == (192, 128, 100),
    "saved_one_frame_at_16fps": scene.frame_start == scene.frame_end == 1 and scene.render.fps == 16 and scene.render.fps_base == 1,
}
objects = [obj for obj in scene.objects if obj.get("cinematicum_id") == "metal_acceptance"]
checks["saved_visible_authored_geometry"] = (len(objects) == 1 and objects[0].type == "MESH"
    and len(objects[0].data.vertices) == 8 and len(objects[0].data.polygons) == 6
    and not objects[0].hide_render and len(objects[0].data.materials) == 1)

# These are process preferences, not fields serialized in .blend. Report this
# fresh enumeration separately from the saved source and completed job receipt.
preferences = bpy.context.preferences.addons["cycles"].preferences
preferences.compute_device_type = "METAL"
preferences.get_devices()
for device in preferences.devices:
    device.use = device.type == "METAL"
devices = [{"id": str(d.id), "name": str(d.name), "type": str(d.type), "enabled": bool(d.use)}
           for d in preferences.devices]
metal_ids = {device["id"] for device in devices if device["enabled"] and device["type"] == "METAL"}
checks["fresh_metal_device_ids_match_render_receipt"] = bool(metal_ids) and {d["id"] for d in receipt["devices"]} <= metal_ids
checks["fresh_cpu_and_other_devices_disabled"] = all(not d["enabled"] for d in devices if d["type"] != "METAL")
report = {"passed": all(checks.values()), "checks": checks, "blender_version": bpy.app.version_string,
          "saved_cycles_device": scene.cycles.device, "saved_receipt": receipt,
          "fresh_verifier_device_enumeration": devices,
          "scope": "The completed job rendered the movie. This verifier reopens its saved source and enumerates hardware; it does not rerender or save preferences."}
Path(args[1]).write_text(json.dumps(report, indent=2) + "\n")
if not report["passed"]:
    raise RuntimeError("Saved Metal scene verification failed: " + ", ".join(k for k, v in checks.items() if not v))
