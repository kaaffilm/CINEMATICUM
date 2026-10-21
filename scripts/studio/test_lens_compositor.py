"""Independent numerical and decoded-pixel proofs for calibrated lens nodes.

The inverse oracle uses a Newton Jacobian, not the production projected fixed
point iteration. Film pixels are synthetic test fixtures, never source footage.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zlib

from compositor import (LENS_MAP_NAMES, MAX_LENS_PIXELS, compile_graph, lens_domain,
                        lens_map_request, lens_nodes, lens_sample_point, validate_graph,
                        write_lens_maps)


BASE = {"direction": "undistort", "fx": 1.0, "fy": .8, "cx": .51, "cy": .47,
        "k1": .06, "k2": -.005, "k3": .0003, "p1": .003, "p2": -.002}
WIDTH, HEIGHT, FPS = 160, 90, 12


def graph_for(params=None):
    return {"version": 1, "nodes": [
        {"id": "source", "type": "source", "inputs": [], "params": {}},
        {"id": "lens", "type": "lens_distortion", "inputs": ["source"], "params": copy.deepcopy(params or BASE)}],
        "output": "lens"}


def oracle(params, x, y, width, height):
    """Brown forward evaluation or unconstrained Newton inverse, in pixels."""
    tx, ty = (x/width-params["cx"])/params["fx"], (y/height-params["cy"])/params["fy"]
    def evaluate(a, b):
        k1, k2, k3, p1, p2 = (params[k] for k in ("k1", "k2", "k3", "p1", "p2"))
        r = a*a+b*b; radial = 1+k1*r+k2*r*r+k3*r*r*r
        rx, ry = a*(2*k1+4*k2*r+6*k3*r*r), b*(2*k1+4*k2*r+6*k3*r*r)
        value = (a*radial+2*p1*a*b+p2*(3*a*a+b*b),
                 b*radial+p1*(a*a+3*b*b)+2*p2*a*b)
        jacobian = (radial+a*rx+2*p1*b+6*p2*a, a*ry+2*p1*a+2*p2*b,
                    b*rx+2*p1*a+2*p2*b, radial+b*ry+6*p1*b+2*p2*a)
        return value, jacobian
    if params["direction"] == "undistort":
        (a, b), _ = evaluate(tx, ty)
    else:
        a, b = tx, ty
        for _ in range(30):
            (px, py), (j00, j01, j10, j11) = evaluate(a, b)
            ex, ey = px-tx, py-ty
            if math.hypot(ex, ey) < 1e-13: break
            determinant = j00*j11-j01*j10
            a -= (j11*ex-j01*ey)/determinant
            b -= (-j10*ex+j00*ey)/determinant
        (px, py), _ = evaluate(a, b)
        if math.hypot(px-tx, py-ty) > 1e-11: raise AssertionError("Independent Newton oracle failed.")
    u, v = (a*params["fx"]+params["cx"])*width, (b*params["fy"]+params["cy"])*height
    if not (-1e-7 <= u <= width-1+1e-7 and -1e-7 <= v <= height-1+1e-7): return None
    return max(0, min(u, width-1)), max(0, min(v, height-1))


def png_samples(path):
    """Independent PNG/CRC reader for the worker's strict numeric map format."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset, packed, header, names = 8, b"", None, []
    while offset < len(data):
        size = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset+4:offset+8]; body = data[offset+8:offset+8+size]
        checksum = struct.unpack_from(">I", data, offset+8+size)[0]
        assert zlib.crc32(kind+body) & 0xffffffff == checksum
        names.append(kind)
        if kind == b"IHDR": header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT": packed += body
        elif kind != b"IEND": raise AssertionError("Unexpected map metadata chunk.")
        offset += size+12
    w, h, depth, color, compression, filtering, interlace = header
    assert depth == 16 and color in {0, 6} and (compression, filtering, interlace) == (0, 0, 0)
    assert names[0] == b"IHDR" and names[-1] == b"IEND" and offset == len(data)
    channels = 1 if color == 0 else 4; stride = w*channels*2+1
    raw = zlib.decompress(packed); assert len(raw) == h*stride
    result = []
    for y in range(h):
        assert raw[y*stride] == 0
        row = struct.unpack(">"+"H"*(w*channels), raw[y*stride+1:(y+1)*stride])
        result.append([row[x*channels:(x+1)*channels] for x in range(w)])
    return w, h, result


def fixture(frame, x, y):
    """Smooth color ramps plus hard moving alpha boundaries and hidden red."""
    if x < 32+frame and y < 32:
        return (255, 0, 0, 0)
    return ((3*x+2*y+frame*11) % 256, (x+5*y+frame*7) % 256,
            (7*x+y+frame*3) % 256, 55+((x//10+y//10+frame) % 5)*50)


def expected_pixel(params, frame, x, y, pixel=fixture):
    point = oracle(params, x, y, WIDTH, HEIGHT)
    if point is None: return (0, 0, 0, 0)
    u, v = point; x0, y0 = math.floor(u), math.floor(v)
    dx, dy = u-x0, v-y0
    values = [0., 0., 0., 0.]
    for xx, yy, weight in ((x0,y0,(1-dx)*(1-dy)), (min(x0+1,WIDTH-1),y0,dx*(1-dy)),
                            (x0,min(y0+1,HEIGHT-1),(1-dx)*dy), (min(x0+1,WIDTH-1),min(y0+1,HEIGHT-1),dx*dy)):
        rgba = pixel(frame, xx, yy)
        for c in range(3): values[c] += weight*rgba[c]*rgba[3]/255
        values[3] += weight*rgba[3]
    return tuple(values)


def render_pixels(graph, directory, *, first=0, frames=4, pixel=fixture, backend="python"):
    ffmpeg = shutil.which("ffmpeg")
    command = [ffmpeg, "-v", "error", "-nostdin", "-y", "-filter_complex_threads", "1",
               "-threads", "1", "-f", "rawvideo", "-pixel_format", "rgba", "-video_size", f"{WIDTH}x{HEIGHT}",
               "-framerate", str(FPS), "-i", "pipe:0"]
    filters, labels, input_index = ["[0:v]format=rgba[src]"], {}, 1
    for lens in lens_nodes(graph):
        path = directory / lens["id"]; path.mkdir()
        write_lens_maps(lens_map_request(lens["params"], WIDTH, HEIGHT), path, backend=backend)
        labels[lens["id"]] = {}
        for name in LENS_MAP_NAMES:
            label = f"map{input_index}"
            labels[lens["id"]][name] = label
            command += ["-threads", "1", "-framerate", str(FPS), "-i", str(path/(name+".png"))]
            filters.append(f"[{input_index}:v]loop=loop={frames-1}:size=1:start=0,settb=expr=1/{FPS},setpts=N[{label}]")
            input_index += 1
    clauses, output = compile_graph(graph, "src", "render", fps=FPS, frame_offset=first,
                                    frame_count=frames, animation_duration=24, lens_labels=labels)
    filters += clauses
    raw = b"".join(bytes(pixel(frame, x, y)) for frame in range(first, first+frames)
                   for y in range(HEIGHT) for x in range(WIDTH))
    result = subprocess.run(command+["-filter_complex", ";".join(filters), "-map", f"[{output}]", "-an",
                                     "-frames:v", str(frames), "-threads", "1", "-pix_fmt", "rgba", "-f", "rawvideo", "pipe:1"],
                            input=raw, check=True, capture_output=True, timeout=20)
    assert len(result.stdout) == frames*WIDTH*HEIGHT*4
    return result.stdout


def render_delivery_control(project, directory, scratch, *, timeout=lambda maximum: maximum):
    """Separate lossless picture identity from the temporal H.264 codec.

    The complete sequence is essential: encoding a repeated still changes the
    encoder's motion decisions and is not a control for a moving movie. This
    reference first materializes the RGB timeline without video compression,
    then feeds that independent raw stream into the actual delivery settings.
    It never substitutes for the independent Newton/alpha pixel oracle.
    """
    import engine
    from timebase import project_rate
    project = engine.validate_project(project, directory)
    rate = project_rate(project)
    ffmpeg = engine._executable("ffmpeg")
    inputs, graph, frames = engine._graph(project, directory, scratch)
    picture = graph + ";[aout]anullsink;[vout]format=rgb24[lossless]"
    common = [ffmpeg, "-v", "error", "-nostdin", "-y", "-threads", "1"]
    lossless = subprocess.run(common + ["-filter_complex_threads", "1"] + inputs + [
        "-filter_complex", picture, "-map", "[lossless]", "-an", "-threads", "1",
        "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"],
        capture_output=True, check=True, timeout=timeout(4)).stdout
    if len(lossless) != frames * project["width"] * project["height"] * 3:
        raise AssertionError("Lossless delivery control has an incorrect frame count.")
    movie = Path(scratch) / "ENGINE_TEST_rgb_sequence_codec_control.mp4"
    subprocess.run(common + [
        "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{project['width']}x{project['height']}",
        "-framerate", rate.ffmpeg, "-i", "pipe:0", "-vf", "scale=out_color_matrix=bt709:out_range=tv",
        "-r", rate.ffmpeg, "-t", rate.seconds_decimal(frames), "-an", "-threads", "2",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-movie_timescale", "48000", "-movflags", "+faststart", str(movie)],
        input=lossless, capture_output=True, check=True, timeout=timeout(3))
    decoded = subprocess.run(common + ["-i", str(movie), "-map", "0:v:0", "-an", "-threads", "1",
                                      "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"],
                             capture_output=True, check=True, timeout=timeout(3)).stdout
    if len(decoded) != len(lossless):
        raise AssertionError("H.264 delivery control has an incorrect frame count.")
    return lossless, decoded, movie


class LensValidationTests(unittest.TestCase):
    def test_static_bounded_schema_and_independent_certificate(self):
        graph = graph_for(); clean = validate_graph(graph, WIDTH, HEIGHT)
        self.assertEqual(clean["nodes"][1]["params"], BASE)
        self.assertEqual(len(lens_nodes(graph)), 1)
        invalid = [{"direction":"fisheye"}, {"direction":[]}, {"fx":0}, {"fy":True},
                   {"cx":float("nan")}, {"k1":float("inf")}, {"p1":.201},
                   {"k1":1,"fx":.1,"fy":.1}, {"profile":"/tmp/lens.xml"}, {"expression":"1+X"}]
        for change in invalid:
            value = graph_for(); value["nodes"][1]["params"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError): validate_graph(value)
        graph["nodes"][1]["animation"] = {"k1":[{"frame":0,"value":.1}]}
        with self.assertRaisesRegex(ValueError,"animation"): validate_graph(graph)

    def test_identity_unused_and_resolution_bounds(self):
        identity = dict(BASE, k1=0,k2=0,k3=0,p1=0,p2=0)
        graph = graph_for(identity)
        validate_graph(graph,3840,2160)
        self.assertEqual(lens_nodes(graph),[])
        clauses,_=compile_graph(graph,"src","test")
        self.assertFalse(any("remap" in line for line in clauses))
        graph = graph_for(); graph["output"]="source"
        validate_graph(graph,3840,2160)
        self.assertEqual(lens_nodes(graph),[])
        self.assertEqual(len(lens_nodes(graph,active_only=False)),1)
        graph["output"]="lens"
        with self.assertRaisesRegex(ValueError,"2,073,600"): validate_graph(graph,3840,2160)
        validate_graph(graph,1920,1080)
        self.assertEqual(MAX_LENS_PIXELS,1920*1080)

    def test_exact_map_label_set_and_alias_rejection(self):
        graph=graph_for();labels={"lens":{name:"map"+name for name in LENS_MAP_NAMES}}
        compile_graph(graph,"src","test",frame_count=4,lens_labels=labels)
        invalid=[None,{}, {"unknown":labels["lens"]}, {"lens":{**labels["lens"],"path":"/tmp"}},
                 {"lens":{**labels["lens"],"x0":"src"}}, {"lens":{**labels["lens"],"x0":"mapx1"}},
                 {"lens":{**labels["lens"],"x0":"a];movie=file"}}, {"lens":{**labels["lens"],"x0":"testn0"}}]
        for value in invalid:
            with self.subTest(labels=value),self.assertRaises(ValueError):
                compile_graph(graph,"src","test",frame_count=4,lens_labels=value)
        with self.assertRaises(ValueError): compile_graph(graph,"src","test",lens_labels=labels)

    def test_full_canvas_inverse_matches_separate_newton_solver(self):
        calibrations=[BASE,dict(BASE,k1=-.12,k2=.015,k3=-.001,p1=-.004,p2=.006),
                      dict(BASE,fx=.8,fy=1.2,cx=.23,cy=.61,k1=.025,k2=.005,p1=.004,p2=-.005)]
        tested=0
        for calibration in calibrations:
            for direction in ("undistort","distort"):
                params=dict(calibration,direction=direction)
                self.assertLessEqual(lens_domain(params)["q"],.45)
                for y in range(0,HEIGHT,7):
                    for x in range(0,WIDTH,9):
                        expected=oracle(params,x,y,WIDTH,HEIGHT)
                        actual=lens_sample_point(params,x,y,WIDTH,HEIGHT)
                        self.assertEqual(actual is None,expected is None,(params,x,y))
                        if expected is not None:
                            self.assertLess(math.hypot(actual[0]-expected[0],actual[1]-expected[1]),1e-7)
                        tested+=1
        self.assertGreater(tested,1200)

    @unittest.skipUnless(shutil.which("node"),"Node required to execute the shipped graph validator")
    def test_shipped_javascript_rejects_unsupported_calibrations_and_matches_bound(self):
        values=[graph_for(),graph_for(dict(BASE,direction="distort")),graph_for(dict(BASE,k1=1,fx=.1)),
                graph_for(dict(BASE,p1=.3)),graph_for(dict(BASE,direction="fisheye"))]
        keyed=graph_for();keyed["nodes"][1]["animation"]={"k1":[{"frame":0,"value":.1}]};values.append(keyed)
        script="""const fs=require('fs'),vm=require('vm');const context={window:{}};vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);const api=context.window.CinematicumCompositor;
const graphs=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(graphs.map(g=>({error:api.validate(g),bound:api.lensBound(g.nodes[1].params),channels:api.animationFields('lens_distortion')}))));"""
        result=subprocess.run([shutil.which("node"),"-e",script,str(Path(__file__).with_name("web")/"compositor-ui.js")],
                              input=json.dumps(values),capture_output=True,text=True,check=True,timeout=10)
        rows=json.loads(result.stdout)
        self.assertEqual([bool(row["error"]) for row in rows],[False,False,True,True,True,True])
        self.assertTrue(all(row["channels"]==[] for row in rows))
        self.assertAlmostEqual(rows[0]["bound"],lens_domain(BASE)["q"],places=14)


class LensMapWorkerTests(unittest.TestCase):
    def test_numeric_maps_receipts_and_subpixel_accuracy(self):
        for direction in ("undistort","distort"):
            with self.subTest(direction=direction), tempfile.TemporaryDirectory() as temporary:
                params=dict(BASE,direction=direction);root=Path(temporary)
                request=lens_map_request(params,61,35)
                result=write_lens_maps(request,root,backend="python")
                self.assertEqual(set(result),{"version","width","height","backend","request_sha256","maps"})
                self.assertEqual(result["backend"],"python")
                self.assertEqual(result["request_sha256"],hashlib.sha256(json.dumps(request,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest())
                self.assertEqual(set(p.name for p in root.iterdir()),{name+".png" for name in LENS_MAP_NAMES})
                maps={}
                for name in LENS_MAP_NAMES:
                    path=root/(name+".png");meta=result["maps"][name]
                    self.assertEqual(meta["sha256"],hashlib.sha256(path.read_bytes()).hexdigest())
                    self.assertEqual(meta["bytes"],path.stat().st_size)
                    w,h,maps[name]=png_samples(path);self.assertEqual((w,h),(61,35))
                    self.assertEqual(meta["channels"],4 if name in {"wx","wy"} else 1)
                for y in range(35):
                    for x in range(61):
                        expected=oracle(params,x,y,61,35)
                        if expected is None:
                            self.assertEqual([maps[name][y][x][0] for name in LENS_MAP_NAMES[:4]],[65535]*4)
                        else:
                            for name in ("wx","wy"): self.assertEqual(maps[name][y][x][:3],(65535,65535,65535))
                            actual=(maps["x0"][y][x][0]+maps["wx"][y][x][3]/65535,
                                    maps["y0"][y][x][0]+maps["wy"][y][x][3]/65535)
                            self.assertLessEqual(abs(actual[0]-expected[0]),.5001/65535)
                            self.assertLessEqual(abs(actual[1]-expected[1]),.5001/65535)

    @unittest.skipUnless(importlib.util.find_spec("numpy"),"Optional isolated NumPy runtime is absent")
    def test_numpy_accelerator_matches_standard_library_maps(self):
        for direction in ("undistort","distort"):
            with self.subTest(direction=direction),tempfile.TemporaryDirectory() as temporary:
                request=lens_map_request(dict(BASE,direction=direction),97,55);root=Path(temporary)
                for backend in ("python","numpy"):
                    path=root/backend;path.mkdir();write_lens_maps(request,path,backend=backend)
                for name in LENS_MAP_NAMES:
                    left=png_samples(root/"python"/(name+".png"))[2];right=png_samples(root/"numpy"/(name+".png"))[2]
                    self.assertEqual(left,right,(direction,name))

    def test_data_only_requests_and_exclusive_output_directory(self):
        request=lens_map_request(BASE,8,6)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            bad=[{**request,"path":"/tmp/input"},{**request,"version":True},{**request,"width":float("nan")},
                 {**request,"width":8193},{**request,"height":0},{**request,"width":1920,"height":1081},
                 {**request,"params":{**BASE,"file":"profile.xml"}}]
            for value in bad:
                with self.subTest(value=value),self.assertRaises(ValueError):write_lens_maps(value,root)
                self.assertEqual(list(root.iterdir()),[])
            (root/"x0.png").write_bytes(b"preserve")
            with self.assertRaisesRegex(ValueError,"empty"):write_lens_maps(request,root)
            self.assertEqual((root/"x0.png").read_bytes(),b"preserve")
            link=root/"linked";target=root/"target";target.mkdir();link.symlink_to(target,target_is_directory=True)
            with self.assertRaises(ValueError):write_lens_maps(request,link)
            self.assertEqual(list(target.iterdir()),[])

    def test_isolated_worker_runs_without_third_party_modules_and_bounds_json(self):
        worker=Path(__file__).with_name("compositor.py")
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            result=subprocess.run([sys.executable,"-I","-S",str(worker),"--lens-maps",str(root)],
                                  input=json.dumps(lens_map_request(BASE,16,10)),capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)["backend"],"python")
        invalid=[b'{"version":1,"version":1,"width":8,"height":6,"params":{}}',b" "*16385,
                 b'{"version":1,"width":8,"height":6,"params":{"fx":NaN}}']
        for raw in invalid:
            with tempfile.TemporaryDirectory() as temporary:
                result=subprocess.run([sys.executable,"-I",str(worker),"--lens-maps",temporary],
                                      input=raw,capture_output=True,timeout=10)
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(list(Path(temporary).iterdir()),[])


@unittest.skipUnless(shutil.which("ffmpeg"),"FFmpeg required for actual rendered pixels")
class LensRenderedPixelTests(unittest.TestCase):
    def test_both_directions_match_independent_premultiplied_bilinear_pixels(self):
        for direction in ("undistort","distort"):
            with self.subTest(direction=direction),tempfile.TemporaryDirectory() as temporary:
                params=dict(BASE,direction=direction)
                pixels=render_pixels(graph_for(params),Path(temporary),frames=3)
                maximum=0.;transparent=0; fractional=0
                for frame in range(3):
                    for y in range(0,HEIGHT,3):
                        for x in range(0,WIDTH,3):
                            position=((frame*HEIGHT+y)*WIDTH+x)*4
                            rgba=pixels[position:position+4]
                            expected=expected_pixel(params,frame,x,y)
                            actual=[rgba[c]*rgba[3]/255 for c in range(3)]+[rgba[3]]
                            maximum=max(maximum,max(abs(a-b) for a,b in zip(actual,expected)))
                            if expected[3]==0:
                                self.assertEqual(tuple(rgba),(0,0,0,0));transparent+=1
                            elif abs(expected[3]-round(expected[3]))>.1:fractional+=1
                self.assertLess(maximum,2.2)
                self.assertGreater(transparent,30)
                self.assertGreater(fractional,30)

    def test_transparent_hidden_red_does_not_bleed_into_green_edges(self):
        def edge(frame,x,y):return (0,200,0,220) if x>=45+frame and y>=20 else (255,0,0,0)
        with tempfile.TemporaryDirectory() as temporary:
            pixels=render_pixels(graph_for(),Path(temporary),pixel=edge,frames=2)
            partial=0
            for i in range(0,len(pixels),4):
                r,g,b,a=pixels[i:i+4]
                if 3<a<217:
                    self.assertEqual(r,0);self.assertEqual(b,0);self.assertLessEqual(abs(g-200),2);partial+=1
            self.assertGreater(partial,30)

    def test_lens_identity_is_exact_and_trim_preserves_upstream_animation(self):
        identity=graph_for(dict(BASE,k1=0,k2=0,k3=0,p1=0,p2=0))
        with tempfile.TemporaryDirectory() as temporary:
            pixels=render_pixels(identity,Path(temporary),frames=2)
            expected=b"".join(bytes(fixture(f,x,y)) for f in range(2) for y in range(HEIGHT) for x in range(WIDTH))
            self.assertEqual(pixels,expected)
        graph=graph_for();graph["nodes"][1]["inputs"]=["mask"]
        graph["nodes"].append({"id":"mask","type":"mask","inputs":["source"],
            "params":{"shape":"rectangle","width":.6,"height":.7,"x":.3},
            "animation":{"x":[{"frame":0,"value":.3},{"frame":7,"value":.7}]}})
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/"full").mkdir();(root/"trim").mkdir()
            full=render_pixels(graph,root/"full",frames=8)
            trimmed=render_pixels(graph,root/"trim",first=3,frames=4)
            self.assertEqual(trimmed,full[3*WIDTH*HEIGHT*4:7*WIDTH*HEIGHT*4])

    def test_actual_engine_lens_media_split_map_dedup_and_paused_export_match(self):
        import engine
        from frame_preview import render_frame
        from test_multi_source_compositor import make_fixture,recipe,decode
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/"media").mkdir();assets=[]
            for kind in ("red","blue"):
                path=root/"media"/(kind+".mkv");make_fixture(path,kind)
                assets.append({"id":kind,"name":kind,"path":str(path.relative_to(root)),**engine.probe_media(path)})
            graph=recipe();graph["nodes"].append({"id":"lens","type":"lens_distortion","inputs":[graph["output"]],"params":dict(BASE,direction="distort")});graph["output"]="lens"
            project={"version":1,"id":"lens_engine_test","name":"ENGINE TEST lens pipeline","width":WIDTH,"height":HEIGHT,"fps":FPS,
                     "assets":assets,"clips":[{"id":"original","asset_id":"red","track":0,"start":0,"in":0,"duration":24,"compositor":graph}],"titles":[]}
            before=root/"before.png";render_frame(project,root,12,before)
            normalized=engine.validate_project(project,root);original=normalized["clips"][0]
            left=copy.deepcopy(original);left["duration"]=8
            right=copy.deepcopy(original);right.update(id="right",start=11,duration=13,animation_offset=11,**{"in":11})
            project["clips"]=[left,right]
            after=root/"after.png";render_frame(project,root,12,after)
            self.assertEqual(decode(before),decode(after))
            movie=root/"export.mp4"
            with mock.patch.object(engine,"prepare_lens_maps",wraps=engine.prepare_lens_maps) as prepare:
                report=engine.render_project(project,root,movie,"h264")
                self.assertEqual(prepare.call_count,1,"One calibration should prepare maps once across both windows.")
            self.assertEqual(report["frames"],24)
            pixels=decode(movie,rgba=False);frame_size=WIDTH*HEIGHT*3
            self.assertEqual(len(pixels),24*frame_size)
            for frame in (8,9,10):self.assertLessEqual(max(pixels[frame*frame_size:(frame+1)*frame_size]),3)
            paused=decode(after,rgba=False);export=pixels[12*frame_size:13*frame_size]
            self.assertLess(sum(abs(a-b) for a,b in zip(paused,export))/frame_size,4)
            # A red source and a temporally selected blue source both survive
            # their external inputs plus the twelve per-window map inputs.
            at=3*(50*WIDTH+130);self.assertGreater(paused[at+2],50)
            at=3*(50*WIDTH+40);self.assertGreater(paused[at],30)

    def test_high_frequency_alpha_movie_matches_complete_sequence_codec_control(self):
        import engine
        from frame_preview import render_frame
        from test_multi_source_compositor import decode
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/"media").mkdir();(root/"control").mkdir()
            source=root/"media"/"alpha.mkv";frames=12
            pixels=b"".join(bytes(fixture(frame,x,y)) for frame in range(frames)
                            for y in range(HEIGHT) for x in range(WIDTH))
            subprocess.run([shutil.which("ffmpeg"),"-v","error","-nostdin","-y","-threads","1",
                            "-f","rawvideo","-pixel_format","rgba","-video_size",f"{WIDTH}x{HEIGHT}",
                            "-framerate",str(FPS),"-i","pipe:0","-an","-c:v","ffv1","-pix_fmt","bgra",
                            "-threads","1",str(source)],input=pixels,check=True,capture_output=True,timeout=5)
            fy=.5/math.tan(math.radians(48)/2)
            params=dict(BASE,fx=fy*HEIGHT/WIDTH*1.12,fy=fy,cx=.54,cy=.475,direction="distort")
            asset={"id":"source","name":"alpha","path":"media/alpha.mkv",**engine.probe_media(source)}
            project={"version":1,"id":"lens_codec_test","name":"ENGINE TEST moving alpha codec",
                     "width":WIDTH,"height":HEIGHT,"fps":FPS,"assets":[asset],"titles":[],
                     "clips":[{"id":"clip","asset_id":"source","track":0,"start":0,"in":0,
                               "duration":frames,"compositor":graph_for(params)}]}
            paused=root/"frame6.png";movie=root/"movie.mp4"
            render_frame(project,root,6,paused);engine.render_project(project,root,movie,"h264")
            lossless,control,_=render_delivery_control(project,root,root/"control")
            decoded=decode(movie,rgba=False);size=WIDTH*HEIGHT*3
            self.assertEqual(decode(paused,rgba=False),lossless[6*size:7*size])
            self.assertEqual(decoded,control,"Decoded delivery must match the separate complete-RGB-sequence encoder.")
            # This control preserves the strict pixel assertion even where
            # chroma subsampling and temporal coding exceed a flat RGB budget.
            self.assertNotEqual(decoded[6*size:7*size],lossless[6*size:7*size])
            self.assertNotEqual(decoded[5*size:6*size],control[6*size:7*size])


if __name__=="__main__":unittest.main()
