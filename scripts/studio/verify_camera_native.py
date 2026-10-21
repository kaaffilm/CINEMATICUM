"""Native camera import proof: real HTTP -> Blender render -> reopened .blend.

Run explicitly with --output pointing to a NEW directory on a machine with
Blender and FFmpeg. All inputs/output are marked ENGINE_TEST fixtures. This is
not evidence of a completed film, reconstruction, or image calibration solver.
"""

from __future__ import annotations

import argparse
import base64
import http.client
import json
from pathlib import Path
import subprocess
import threading

from adapters import find_blender
import scene
from server import Server, Store
from test_camera_io import colmap_payload, dot, fspy_bytes, fspy_state, matrix_vector, rodrigues, transpose


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", choices=("fspy_landscape", "fspy_portrait", "colmap_shifted_anisotropic"),
                        help="Run one fixture for gateways with a short command budget.")
    args = parser.parse_args()
    binary = find_blender()
    if not binary:
        raise RuntimeError("Native camera proof requires an installed Blender.")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    store = Store(output / "workspace")
    server = Server(0, store)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(method, path, body=None, token=True):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=30)
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Cinematicum-Token"] = store.token
        connection.request(method, path, json.dumps(body).encode() if body is not None else None, headers)
        response = connection.getresponse()
        status, result = response.status, json.loads(response.read())
        connection.close()
        return status, result

    cases, results = [], []
    for source_width, source_height in ((1200, 800), (800, 1200)):
        state = fspy_state(source_width, source_height)
        transform = state["cameraParameters"]["cameraTransform"]["rows"]
        local = [[.2, .3, -2], [-.6, .7, -4], [.7, -.3, -3]]
        points = [matrix_vector(transform[:3], p+[1]) for p in local]
        longest, focal = max(source_width, source_height), 1.7
        expected = [[(source_width/2+(focal*p[0]/-p[2]+.12)*longest/2)*.16,
                     (source_height/2-(focal*p[1]/-p[2]-.08)*longest/2)*.16] for p in local]
        cases.append({"name": "fspy_%s" % ("landscape" if source_width > source_height else "portrait"),
                      "width": int(source_width*.16), "height": int(source_height*.16),
                      "payload": {"format": "fspy", "name": "ENGINE_TEST_camera.fspy",
                                  "data_base64": base64.b64encode(fspy_bytes(state)).decode()},
                      "points": points, "expected": expected})
    rotation, local = rodrigues([1, 2, -1], .83), [[.3, .2, 2], [-.4, .8, 4], [.6, -.5, 3]]
    points = [matrix_vector(transpose(rotation), [p[i]-[1.1, -.4, 2.8][i] for i in range(3)]) for p in local]
    cases.append({"name": "colmap_shifted_anisotropic", "width": 192, "height": 128, "payload": colmap_payload(),
                  "points": points, "expected": [[(950*p[0]/p[2]+610)*.16, (850*p[1]/p[2]+390)*.16] for p in local]})
    if args.case:
        cases = [case for case in cases if case["name"] == args.case]
    try:
        for case in cases:
            status, project = request("POST", "/api/projects", {"name": "ENGINE_TEST_CAMERA_"+case["name"],
                                                               "width": case["width"], "height": case["height"], "fps": 24})
            if status != 201:
                raise AssertionError((status, project))
            route = "/api/projects/%s/scene/import-camera" % project["id"]
            denied, _ = request("POST", route, case["payload"], token=False)
            if denied != 403:
                raise AssertionError("Camera imports must require the application token.")
            status, imported = request("POST", route, case["payload"])
            if status != 200:
                raise AssertionError((status, imported))
            unchanged = store.get(project["id"])
            if unchanged != project:
                raise AssertionError("Reviewing an imported camera must not alter the persisted project.")
            spec = scene.default_scene(case["width"], case["height"])
            spec["camera"] = imported["cameras"][0]["camera"]
            spec["frame_end"], spec["samples"] = 1, 4
            spec["objects"] = [{"id": "test_cube", "name": "ENGINE_TEST reference geometry", "type": "cube",
                                "position": case["points"][0], "rotation": [20, 30, 15], "scale": [.12, .12, .12],
                                "material": {"color": "#d4a052", "roughness": .4, "metallic": .1}}]
            rendered = scene.render_scene(spec, output / case["name"], frame_start=1, frame_end=1)
            proof = output / (case["name"]+"_reopened_projection.json")
            script = output / (case["name"]+"_inspect.py")
            script.write_text("""import bpy,json,math
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
points=json.loads(%r)
expected=json.loads(%r)
scene=bpy.context.scene
scene.frame_set(1)
bpy.context.view_layer.update()
actual=[]
for point in points:
    p=world_to_camera_view(scene,scene.camera,Vector(point))
    actual.append([p.x*scene.render.resolution_x,(1-p.y)*scene.render.resolution_y])
error=max(abs(a-b) for point,reference in zip(actual,expected) for a,b in zip(point,reference))
if not math.isfinite(error) or error>.002:
    raise RuntimeError('Saved Blender camera lost source calibration: '+str(error))
result={'engine_test_fixture':True,'blender_version':bpy.app.version_string,'max_error_pixels':error,'actual':actual,'expected':expected,'camera':scene.camera.name,'resolution':[scene.render.resolution_x,scene.render.resolution_y],'pixel_aspect':[scene.render.pixel_aspect_x,scene.render.pixel_aspect_y]}
with open(%r,'w') as file:json.dump(result,file,indent=2,allow_nan=False)
""" % (json.dumps(case["points"]), json.dumps(case["expected"]), str(proof)), encoding="utf-8")
            log = output / (case["name"]+"_inspect.log")
            with log.open("wb") as stdout:
                subprocess.run([binary, "--background", "--disable-autoexec", rendered["scene_path"],
                                "--python-exit-code", "1", "--python", str(script)],
                               stdout=stdout, stderr=subprocess.STDOUT, timeout=120, check=True)
            checked = json.loads(proof.read_text())
            results.append({"case": case["name"], "http_status": status, "missing_token_status": denied,
                            "review_did_not_mutate_project": True, "source": imported["cameras"][0]["source"],
                            "camera": imported["cameras"][0]["camera"], "render": rendered, "reopened": checked})
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        store.shutdown()
    report = {"engine_test_fixture": True, "status": "passed", "cases": results,
              "scope": "Selected camera data imported through HTTP, real one-frame renders, and independent source reprojection in reopened Blender scenes."}
    path = output / "camera-native-proof.json"
    path.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "report": str(path), "cases": len(results)}))


if __name__ == "__main__":
    main()
