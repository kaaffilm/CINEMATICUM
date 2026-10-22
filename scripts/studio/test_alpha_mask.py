"""Independent decoded alpha-mask arithmetic, including real 16-bit codes."""
from __future__ import annotations

import array
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from compositor import compile_graph, high16_source_conversion, validate_graph
from engine import probe_media, render_project
from test_high_precision import decode_rgba16, write_fixture


def mask_graph(invert=False):
    return {"version": 1, "nodes": [
        {"id": "source", "type": "source", "inputs": [], "params": {}},
        {"id": "matte", "type": "media_source", "inputs": [],
         "params": {"asset_id": "matte", "source_in": 0, "duration": 3, "offset": 0, "outside": "transparent"}},
        {"id": "cutout", "type": "alpha_mask", "inputs": ["source", "matte"], "params": {"invert": invert}},
    ], "output": "cutout"}


class AlphaMaskValidationTests(unittest.TestCase):
    def test_second_alpha_is_a_real_cycle_checked_image_edge(self):
        graph = mask_graph()
        normalized = validate_graph(graph)
        self.assertEqual(normalized["nodes"][-1]["inputs"], ["source", "matte"])
        for change in ("cycle", "missing", "boolean"):
            bad = copy.deepcopy(graph)
            if change == "cycle": bad["nodes"][-1]["inputs"][1] = "cutout"
            if change == "missing": bad["nodes"][-1]["inputs"].pop()
            if change == "boolean": bad["nodes"][-1]["params"]["invert"] = 1
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_graph(bad)

    @unittest.skipUnless(shutil.which("node"), "Node is required to validate the shipped graph editor")
    def test_shipped_editor_accepts_and_can_invert_the_same_two_input_node(self):
        program = """const fs=require('fs'),vm=require('vm'),data=JSON.parse(fs.readFileSync(0,'utf8')),s={window:{}};
vm.createContext(s);vm.runInContext(fs.readFileSync(data.path,'utf8'),s);const api=s.window.CinematicumCompositor;
if(api.validate(data.graph))throw Error('Valid alpha mask rejected');
if(api.nodeTypes.alpha_mask.inputs.join(',')!=='Image,Mask alpha')throw Error('Missing editable image/alpha edges');
data.graph.nodes[2].params.invert=true;if(api.validate(data.graph))throw Error('Boolean inversion rejected');
data.graph.nodes[2].params.invert=1;if(!api.validate(data.graph))throw Error('Numeric inversion accepted');"""
        subprocess.run([shutil.which("node"), "-e", program], input=json.dumps({
            "path": str(Path(__file__).parent / "web/compositor-ui.js"), "graph": mask_graph()}),
            text=True, capture_output=True, check=True, timeout=10)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class AlphaMaskPixelsTests(unittest.TestCase):
    def test_opaque_source_conversion_has_exact_coverage_and_does_not_flatten_real_alpha(self):
        width, height = 16, 16
        rgba = bytes(channel for index in range(width*height)
                     for channel in (37, 149, 211, (0, 17, 128, 255)[index%4]))
        command = [shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-f", "rawvideo",
                   "-pix_fmt", "rgba", "-s", f"{width}x{height}", "-i", "pipe:0",
                   "-frames:v", "1", "-threads", "1"]
        for source_format in ("bgr0", "rgb24", "yuv420p"):
            filters = ["format="+source_format] + high16_source_conversion(source_format) + ["alphaextract"]
            raw = subprocess.run(command + ["-vf", ",".join(filters), "-pix_fmt", "gray16le", "-f", "rawvideo", "pipe:1"],
                                 input=rgba, capture_output=True, check=True, timeout=10).stdout
            values = array.array("H", raw)
            if sys.byteorder != "little": values.byteswap()
            self.assertEqual(set(values), {65535}, source_format)
        for source_format in ("rgba", "bgra", "gbrap16le", "yuva444p16le", "ya8", "pal8", None):
            self.assertEqual(high16_source_conversion(source_format), ["format=gbrap16le"])
        # Preserve all alpha supplied by a genuine high-depth source, including
        # one-code coverage; the opaque correction must never run on this path.
        values = array.array("H", [v for i in range(width*height) for v in (7133, 61234, 29917, (0,1,32749,65535)[i%4])])
        if sys.byteorder != "little": values.byteswap()
        raw = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba64le",
            "-s", f"{width}x{height}", "-i", "pipe:0", "-vf", ",".join(high16_source_conversion("rgba64le")),
            "-frames:v", "1", "-threads", "1", "-pix_fmt", "rgba64le", "-f", "rawvideo", "pipe:1"],
            input=values.tobytes(), capture_output=True, check=True, timeout=10).stdout
        self.assertEqual(raw, values.tobytes())

    def test_full_high16_movie_preserves_rgb_and_multiplies_independent_fractional_alphas(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-alpha-mask-") as temporary:
            root = Path(temporary)
            width, height = 64, 32
            colors = [(1001+i%1024*33, 60123-i%1024*17, 9733+i%1024*19,
                       (0, 1, 7133, 32749, 60013, 65535)[i%6]) for i in range(width*height)]
            masks = [(27183, 14321, 37977, (0, 65535, 19991, 48013, 1001)[i%5]) for i in range(width*height)]
            assets=[]
            for name, pixels in (("source", colors), ("matte", masks)):
                path=write_fixture(root/"media"/(name+".mkv"),pixels,width=width,height=height)
                self.assertEqual(decode_rgba16(path)[:width*height],pixels)
                assets.append({"id":name,"name":name,"path":"media/"+name+".mkv",**probe_media(path)})
            project={"version":1,"id":"alpha_mask_test","name":"Synthetic alpha arithmetic",
                     "fps":12,"width":width,"height":height,"assets":assets,"titles":[],
                     "settings":{"image_precision":"high16","transparent_background":True},
                     "clips":[{"id":"picture","asset_id":"source","start":0,"in":0,"duration":3,"track":0}]}
            for invert in (False,True):
                project["clips"][0]["compositor"]=mask_graph(invert)
                output=root/("inverted.mkv" if invert else "cutout.mkv")
                render_project(project,root,output,"master16")
                actual=decode_rgba16(output)
                self.assertEqual(len(actual),width*height*3)
                expected=[(*c[:3],round(c[3]*(65535-m[3] if invert else m[3])/65535)) for c,m in zip(colors,masks)]
                self.assertLessEqual(max(abs(a[3]-e[3]) for a,e in zip(actual,expected*3)),1)
                # The full timeline associates/unassociates at its fit and
                # compositing stages. At alpha=1 a half-code rounding of an
                # associated channel represents 32767 straight codes. Bound
                # error in physical associated coverage instead of incorrectly
                # expecting transparent straight RGB to survive UNORM math.
                # The direct kernel test below separately requires exact RGB.
                associated_error=max(abs(a[c]*a[3]-e[c]*e[3])/65535
                                     for a,e in zip(actual,expected*3) for c in range(3))
                self.assertLessEqual(associated_error,3)
                surviving={a[0] for a in actual[:width*height] if a[3]}
                self.assertGreater(len(surviving),256,"An eight-bit bottleneck destroyed high16 source colors")

    def test_high16_node_keeps_straight_rgb_exact_and_uses_full_depth_alpha(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-alpha16-node-") as temporary:
            root=Path(temporary);width,height=64,32
            colors=[(1001+i%1024*33,60123-i%1024*17,9733+i%1024*19,
                     (0,1,7133,32749,60013,65535)[i%6]) for i in range(width*height)]
            masks=[(27183,14321,37977,(0,65535,19991,48013,1001)[i%5]) for i in range(width*height)]
            for name,pixels in (("source",colors),("matte",masks)):
                write_fixture(root/(name+".mkv"),pixels,width=width,height=height,frames=1)
            for invert in (False,True):
                graph=mask_graph(invert);graph["nodes"][1]["params"]["duration"]=1
                filters,label=compile_graph(graph,"picture","alpha",precision="high16",frame_count=1,external_labels={"matte":"maskinput"})
                chain=";".join(["[0:v]format=gbrap16le[picture]","[1:v]format=gbrap16le[maskinput]"]+filters)
                raw=subprocess.run([shutil.which("ffmpeg"),"-v","error","-nostdin","-filter_complex_threads","1",
                    "-i",str(root/"source.mkv"),"-i",str(root/"matte.mkv"),"-filter_complex",chain,
                    "-map",f"[{label}]","-frames:v","1","-threads","1","-pix_fmt","rgba64le","-f","rawvideo","pipe:1"],
                    capture_output=True,check=True,timeout=20).stdout
                values=array.array("H",raw)
                if sys.byteorder!="little":values.byteswap()
                actual=list(zip(*(iter(values),)*4))
                expected=[(*c[:3],round(c[3]*(65535-m[3] if invert else m[3])/65535)) for c,m in zip(colors,masks)]
                self.assertEqual(actual,expected)

    def test_standard8_graph_uses_mask_alpha_not_rgb_and_rounds_only_once(self):
        with tempfile.TemporaryDirectory(prefix="cinematicum-alpha8-") as temporary:
            root=Path(temporary); width,height=16,16
            colors=[(37,149,211,(0,17,73,128,191,255)[i%6]) for i in range(width*height)]
            matte=[(255-i%256,i%256,11,(0,3,67,129,213,255)[i%6]) for i in range(width*height)]
            for name,pixels in (("source",colors),("matte",matte)):
                (root/(name+".rgba")).write_bytes(bytes(channel for p in pixels for channel in p))
            for invert in (False,True):
                graph=mask_graph(invert);graph["nodes"][1]["params"]["duration"]=1
                filters,label=compile_graph(graph,"picture","alpha",frame_count=1,external_labels={"matte":"maskinput"})
                chain=";".join(["[0:v]format=rgba[picture]","[1:v]format=rgba[maskinput]"]+filters)
                command=[shutil.which("ffmpeg"),"-v","error","-nostdin","-filter_complex_threads","1"]
                for name in ("source","matte"):
                    command += ["-f","rawvideo","-pix_fmt","rgba","-s",f"{width}x{height}","-r","12","-i",str(root/(name+".rgba"))]
                command += ["-filter_complex",chain,"-map",f"[{label}]","-frames:v","1","-threads","1","-pix_fmt","rgba","-f","rawvideo","pipe:1"]
                result=subprocess.run(command,capture_output=True,check=True,timeout=20).stdout
                actual=list(zip(*(iter(result),)*4))
                expected=[(*c[:3],round(c[3]*(255-m[3] if invert else m[3])/255)) for c,m in zip(colors,matte)]
                self.assertEqual(actual,expected)


if __name__=="__main__":unittest.main()
