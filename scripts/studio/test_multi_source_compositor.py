"""Real decoded-media acceptance for independently timed compositor sources.

All generated pictures are synthetic engine fixtures, not film footage. The
pixel oracle is independent of the graph compiler and tests moving images,
selected-range endpoints, empty gaps, split windows and paused/export parity.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from compositor import (MAX_ANIMATION_FRAME, compile_graph, media_frame_at,
                        media_sources, validate_graph, validate_media_sources)


WIDTH, HEIGHT, FPS, FRAMES = 160, 90, 12, 24


def node(ident, kind, inputs=(), **params):
    return {"id": ident, "type": kind, "inputs": list(inputs), "params": params}


def recipe(*, outside="transparent", offset=6, source_in=4, duration=8, external_only=False):
    nodes = [node("source", "source"),
             node("plate", "media_source", asset_id="blue", source_in=source_in,
                  duration=duration, offset=offset, outside=outside)]
    if external_only:
        return {"version": 1, "nodes": nodes, "output": "plate"}
    nodes += [node("matte", "mask", ["plate"], shape="rectangle", x=.75, y=.5,
                   width=.5, height=1, feather=0),
              node("merge", "merge", ["source", "matte"], opacity=1)]
    return {"version": 1, "nodes": nodes, "output": "merge"}


def fixture_pixel(kind, frame, x, y):
    """Known source pixels authored without FFmpeg filter expressions."""
    if kind == "red":
        return (240, 35, 5, 255) if 8 + 3 * frame <= x < 26 + 3 * frame and 20 <= y < 42 else (40, 12, 6, 255)
    return (4, 70, 240, 255) if 110 <= x < 136 and 5 + 2 * frame <= y < 21 + 2 * frame else (6, 12, 70, 255)


def make_fixture(path, kind, *, fps=FPS, frames=FRAMES, width=WIDTH, height=HEIGHT):
    pixels = b"".join(bytes(fixture_pixel(kind, frame, x, y))
                       for frame in range(frames) for y in range(height) for x in range(width))
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-threads", "1",
                    "-f", "rawvideo", "-pixel_format", "rgba", "-video_size", f"{width}x{height}",
                    "-framerate", str(fps), "-i", "pipe:0", "-an", "-c:v", "ffv1", "-pix_fmt", "bgra",
                    "-threads", "1", str(path)], input=pixels, check=True, capture_output=True, timeout=15)


def decode(path, *, rgba=True):
    result = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-threads", "1",
                             "-i", str(path), "-map", "0:v:0", "-an", "-threads", "1",
                             "-pix_fmt", "rgba" if rgba else "rgb24", "-f", "rawvideo", "pipe:1"],
                            check=True, capture_output=True, timeout=20)
    return result.stdout


class MultiSourceValidationTests(unittest.TestCase):
    def test_v1_is_preserved_and_media_nodes_are_detached(self):
        raw = recipe()
        clean = validate_graph(raw)
        self.assertEqual(clean["version"], 1)
        clean["nodes"][1]["params"]["source_in"] = 9
        self.assertEqual(raw["nodes"][1]["params"]["source_in"], 4)
        self.assertEqual([n["id"] for n in media_sources(raw)], ["plate"])
        sources = media_sources(raw)
        sources[0]["params"]["asset_id"] = "mutated"
        self.assertEqual(raw["nodes"][1]["params"]["asset_id"], "blue")

    def test_source_schema_rejects_unsafe_or_ambiguous_timing(self):
        invalid = [{"asset_id": "../blue.mp4"}, {"asset_id": "a];movie=file"},
                   {"source_in": True}, {"source_in": -.1}, {"source_in": 1.5},
                   {"duration": 0}, {"duration": float("nan")}, {"duration": 2.5},
                   {"offset": float("inf")}, {"offset": .5}, {"outside": "loop"},
                   {"outside": []}, {"path": "/tmp/blue.mp4"}, {"command": "run"},
                   {"source_in": MAX_ANIMATION_FRAME - 1}, {"offset": MAX_ANIMATION_FRAME}]
        for change in invalid:
            raw = recipe(); raw["nodes"][1]["params"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_graph(raw)
        raw = recipe(); raw["nodes"][1]["animation"] = {"offset": [{"frame": 0, "value": 1}]}
        with self.assertRaisesRegex(ValueError, "animation channel"):
            validate_graph(raw)

    def test_unused_sources_still_require_valid_project_assets(self):
        raw = recipe(); raw["output"] = "source"
        self.assertEqual(media_sources(raw), [])
        self.assertEqual(len(media_sources(raw, active_only=False)), 1)
        for assets in ({}, {"blue": {"kind": "audio"}}, {"blue": {"kind": "scene"}},
                       {"blue": {"kind": "video", "duration": .5}},
                       {"blue": {"kind": "image", "path": "media/linear.EXR"}},
                       {"blue": {"kind": "image", "codec": "exr"}},
                       {"blue": {"kind": "video", "duration": 2, "color_transfer": "smpte2084"}}):
            with self.subTest(assets=assets), self.assertRaises(ValueError):
                validate_media_sources(raw, assets, FPS)
        self.assertEqual(len(validate_media_sources(raw, {"blue": {"kind": "video", "duration": 2}}, FPS)), 1)

    def test_image_ranges_start_at_zero_and_hold_for_selected_duration(self):
        raw = recipe(source_in=0, duration=100)
        validate_media_sources(raw, {"blue": {"kind": "image", "duration": 0}}, FPS)
        raw["nodes"][1]["params"]["source_in"] = 1
        with self.assertRaisesRegex(ValueError, "no source in"):
            validate_media_sources(raw, {"blue": {"kind": "image", "duration": 0}}, FPS)

    def test_media_limit_cycle_and_disconnected_cycle_are_enforced(self):
        raw = recipe()
        for i in range(8):
            item = copy.deepcopy(raw["nodes"][1]); item["id"] = "extra" + str(i); raw["nodes"].append(item)
        with self.assertRaisesRegex(ValueError, "at most 8"):
            validate_graph(raw)
        raw = recipe(); raw["nodes"] += [node("loop", "grade", ["loop"])]
        with self.assertRaisesRegex(ValueError, "cycle"):
            validate_graph(raw)

    def test_compile_labels_are_owned_distinct_and_exactly_reachable(self):
        raw = recipe()
        for labels in (None, {}, {"plate": "0:v"}, {"plate": "x];movie=a"},
                       {"plate": "input"}, {"plate": "testn1"}, {"plate": "plateInput", "unused": "other"}):
            with self.subTest(labels=labels), self.assertRaises(ValueError):
                compile_graph(raw, "input", "test", frame_count=24, external_labels=labels)
        with self.assertRaises(ValueError):
            compile_graph(raw, "input", "test", external_labels={"plate": "plateInput"})
        raw["output"] = "source"
        clauses, output = compile_graph(raw, "input", "test")
        self.assertEqual((clauses, output), ([], "input"))

    @unittest.skipUnless(shutil.which("node"), "Node required to evaluate shipped JavaScript")
    def test_actual_js_and_python_sampling_agree_with_explicit_frame_oracle(self):
        transparent, held = recipe(), recipe(outside="hold")
        expected_transparent = [None] * 6 + list(range(4, 12)) + [None] * 10
        expected_hold = [4] * 6 + list(range(4, 12)) + [11] * 10
        payload = {"source": str(Path(__file__).parent / "web" / "compositor-ui.js"),
                   "graphs": [transparent, held]}
        script = """
const fs=require('fs'),vm=require('vm'),p=JSON.parse(fs.readFileSync(0,'utf8')),s={window:{}};
vm.createContext(s);vm.runInContext(fs.readFileSync(p.source,'utf8'),s);
const api=s.window.CinematicumCompositor;
for(const graph of p.graphs)if(api.validate(graph))throw Error(api.validate(graph));
const bad=JSON.parse(JSON.stringify(p.graphs[0]));bad.nodes[1].params.path='/tmp/film';
if(!api.validate(bad))throw Error('Arbitrary path accepted');
process.stdout.write(JSON.stringify(p.graphs.map(g=>Array.from({length:24},(_,f)=>api.mediaFrameAt(g.nodes[1],f)))));
"""
        actual = json.loads(subprocess.run([shutil.which("node"), "-e", script], input=json.dumps(payload),
                                         text=True, capture_output=True, check=True, timeout=10).stdout)
        self.assertEqual(actual, [expected_transparent, expected_hold])
        for graph, expected in zip((transparent, held), (expected_transparent, expected_hold)):
            self.assertEqual([media_frame_at(graph["nodes"][1], frame) for frame in range(24)], expected)


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required for real media acceptance")
class MultiSourceDecodedMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="cinematicum-multiple-ENGINE-TEST-")
        cls.root = Path(cls.temporary.name)
        for kind in ("red", "blue"):
            make_fixture(cls.root / ("ENGINE_TEST_" + kind + ".mkv"), kind)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def render_compiled(self, raw, *, offset=0, count=FRAMES, primary_in=0, rate=FPS):
        requests = media_sources(raw)
        labels = {item["id"]: "external" + str(i) for i, item in enumerate(requests)}
        clauses = [f"[0:v]fps={rate},trim=start_frame={primary_in}:end_frame={primary_in+count},setpts=PTS-STARTPTS,setsar=1,format=rgba[primary]"]
        inputs = ["-threads", "1", "-i", str(self.root / "ENGINE_TEST_red.mkv")]
        for index, request in enumerate(requests):
            inputs += ["-threads", "1", "-i", str(self.root / "ENGINE_TEST_blue.mkv")]
            clauses.append(f"[{index+1}:v]setpts=PTS-STARTPTS,fps={rate},setsar=1,format=rgba[{labels[request['id']]}]")
        filters, output = compile_graph(raw, "primary", "test", fps=float(rate) if isinstance(rate, int) else 24000/1001,
                                        frame_offset=offset, frame_count=count, animation_start=-24,
                                        animation_duration=48, external_labels=labels)
        clauses += filters
        result = subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-filter_complex_threads", "1",
                                 *inputs, "-filter_complex", ";".join(clauses), "-map", "["+output+"]", "-an",
                                 "-threads", "1", "-pix_fmt", "rgba", "-fps_mode", "passthrough", "-f", "rawvideo", "pipe:1"],
                                check=True, capture_output=True, timeout=20)
        frame_bytes = WIDTH * HEIGHT * 4
        self.assertEqual(len(result.stdout), frame_bytes * count, "A source range or EOF changed the exact output frame count")
        return [result.stdout[at:at+frame_bytes] for at in range(0, len(result.stdout), frame_bytes)]

    def assert_pixel(self, picture, x, y, expected):
        at = 4 * (y * WIDTH + x)
        actual = tuple(picture[at:at+4])
        self.assertLessEqual(max(abs(a-b) for a,b in zip(actual, expected)), 2, (x,y,actual,expected))

    def test_two_independently_moving_movies_merge_with_exact_transparent_gaps(self):
        pictures = self.render_compiled(recipe())
        source_indices = [None] * 6 + list(range(4, 12)) + [None] * 10
        for frame, (picture, sample) in enumerate(zip(pictures, source_indices)):
            for x,y in ((24, 25), (48, 25), (73, 25), (113, 17), (125, 31), (140, 55)):
                expected = fixture_pixel("blue", sample, x, y) if x >= 80 and sample is not None else fixture_pixel("red", frame, x, y)
                self.assert_pixel(picture, x, y, expected)
        self.assertNotEqual(pictures[6], pictures[10])

    def test_hold_uses_selected_endpoints_and_does_not_repeat_entire_asset(self):
        pictures = self.render_compiled(recipe(outside="hold"))
        for frame, sample in ((0,4),(5,4),(6,4),(9,7),(13,11),(14,11),(23,11)):
            for x,y in ((113,17),(125,31),(140,55)):
                self.assert_pixel(pictures[frame], x,y,fixture_pixel("blue",sample,x,y))

    def test_external_only_output_consumes_main_input_and_preserves_zero_alpha(self):
        pictures = self.render_compiled(recipe(external_only=True))
        for frame in (0,5,14,23):
            self.assertEqual(set(pictures[frame][3::4]), {0})
        for frame in (6,10,13):
            self.assert_pixel(pictures[frame],113,17,fixture_pixel("blue",frame-2,113,17))

    def test_negative_offset_and_negative_animation_window(self):
        raw = recipe(offset=-3, source_in=2, duration=8)
        pictures = self.render_compiled(raw)
        for frame,sample in enumerate([5,6,7,8,9]+[None]*19):
            self.assert_pixel(pictures[frame],113,17,fixture_pixel("red",frame,113,17) if sample is None else fixture_pixel("blue",sample,113,17))
        negative = self.render_compiled(raw,offset=-5,count=8)
        for frame,sample in enumerate([None,None,2,3,4,5,6,7]):
            self.assert_pixel(negative[frame],113,17,fixture_pixel("red",frame,113,17) if sample is None else fixture_pixel("blue",sample,113,17))

    def test_trim_split_windows_are_pixel_identical_with_animated_merge(self):
        raw=recipe(outside="hold")
        raw["nodes"][-1]["animation"]={"opacity":[{"frame":0,"value":.2,"interpolation":"ease_in_out"},{"frame":20,"value":.9}]}
        original=self.render_compiled(raw)
        left=self.render_compiled(raw,count=10)
        right=self.render_compiled(raw,offset=10,count=14,primary_in=10)
        trimmed=self.render_compiled(raw,offset=13,count=7,primary_in=13)
        self.assertEqual(left+right,original)
        self.assertEqual(trimmed,original[13:20])

    def test_fully_before_or_after_range_emits_all_frames_for_both_policies(self):
        for outside in ("transparent","hold"):
            for offset in (-20,40):
                raw=recipe(outside=outside,offset=offset,external_only=True)
                pictures=self.render_compiled(raw)
                if outside=="transparent":
                    self.assertTrue(all(set(p[3::4])=={0} for p in pictures))
                else:
                    self.assertTrue(all(p==pictures[0] for p in pictures))

    def test_same_asset_can_feed_distinct_independently_timed_nodes(self):
        raw=recipe(external_only=True)
        duplicate=copy.deepcopy(raw["nodes"][1]);duplicate["id"]="second";duplicate["params"].update(source_in=0,offset=0,duration=24)
        raw["nodes"] += [duplicate,node("merge","merge",["plate","second"],opacity=.5)]
        raw["output"]="merge"
        pictures=self.render_compiled(raw)
        self.assertNotEqual(pictures[0],pictures[10])
        self.assertEqual(set(pictures[0][3::4]),{128})
        self.assertEqual(set(pictures[10][3::4]),{255})

    def test_ntsc_conformed_sources_keep_integer_range_endpoints(self):
        raw=recipe(offset=5,source_in=1,duration=11,external_only=True)
        pictures=self.render_compiled(raw,rate="24000/1001")
        for frame,picture in enumerate(pictures):
            self.assertEqual(set(picture[3::4]),{255} if 5<=frame<16 else {0})


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required for engine acceptance")
class MultiSourceEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from engine import probe_media
        cls.temporary=tempfile.TemporaryDirectory(prefix="cinematicum-multisource-pipeline-TEST-")
        cls.root=Path(cls.temporary.name);(cls.root/"media").mkdir()
        cls.assets=[]
        for kind in ("red","blue"):
            path=cls.root/"media"/("ENGINE_TEST_"+kind+".mkv")
            make_fixture(path,kind)
            cls.assets.append({"id":kind,"path":str(path.relative_to(cls.root)),"name":"ENGINE TEST "+kind,**probe_media(path)})

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def project(self,raw=None):
        return {"version":1,"id":"multi_source_test","name":"ENGINE TEST independently moving sources",
                "width":WIDTH,"height":HEIGHT,"fps":FPS,"assets":copy.deepcopy(self.assets),
                "clips":[{"id":"base_clip","asset_id":"red","track":0,"start":0,"in":0,"duration":FRAMES,
                          "compositor":raw or recipe()}],"titles":[]}

    def test_actual_engine_export_paused_frame_and_trimmed_split_are_consistent(self):
        from engine import render_project,validate_project
        from frame_preview import render_frame
        project=self.project()
        before=self.root/"ENGINE_TEST_before.png"
        render_frame(project,self.root,12,before)
        normalized=validate_project(project,self.root)
        original=normalized["clips"][0]
        left=copy.deepcopy(original);left["duration"]=8
        right=copy.deepcopy(original);right.update(id="right_clip",start=11,duration=13,**{"in":11,"animation_offset":11})
        project["clips"]=[left,right]
        after=self.root/"ENGINE_TEST_after.png"
        render_frame(project,self.root,12,after)
        self.assertEqual(decode(before),decode(after))
        movie=self.root/"ENGINE_TEST_export.mp4"
        report=render_project(project,self.root,movie,"h264")
        self.assertEqual(report["frames"],FRAMES)
        pixels=decode(movie,rgba=False);size=WIDTH*HEIGHT*3
        self.assertEqual(len(pixels),FRAMES*size)
        for frame in (8,9,10):
            self.assertLessEqual(max(pixels[frame*size:(frame+1)*size]),3)
        paused=decode(after,rgba=False);actual=pixels[12*size:13*size]
        self.assertLess(sum(abs(a-b) for a,b in zip(paused,actual))/size,4)
        for frame,x,y in ((6,113,17),(12,125,31),(14,125,31),(23,73,25)):
            sample=frame-2 if 6<=frame<14 else None
            expected=fixture_pixel("blue",sample,x,y)[:3] if x>=80 and sample is not None else fixture_pixel("red",frame,x,y)[:3]
            at=frame*size+3*(y*WIDTH+x)
            self.assertLessEqual(max(abs(a-b) for a,b in zip(pixels[at:at+3],expected)),10)

    def test_unused_invalid_asset_references_fail_project_validation(self):
        from engine import validate_project
        raw=recipe();raw["output"]="source";raw["nodes"][1]["params"]["asset_id"]="missing"
        with self.assertRaisesRegex(ValueError,"missing project media"):
            validate_project(self.project(raw),self.root)

    def test_additional_inputs_do_not_shift_later_timeline_clip_index(self):
        from engine import render_project
        project=self.project(recipe(external_only=True,outside="hold"))
        project["clips"].append({"id":"second_clip","asset_id":"red","track":0,"start":FRAMES,"in":0,"duration":FRAMES})
        movie=self.root/"ENGINE_TEST_two_clips.mp4"
        report=render_project(project,self.root,movie,"h264")
        self.assertEqual(report["frames"],48)
        pixels=decode(movie,rgba=False);size=WIDTH*HEIGHT*3
        self.assertEqual(len(pixels),48*size)
        for frame in (24,28,40,47):
            x,y=48,25;at=frame*size+3*(y*WIDTH+x)
            expected=fixture_pixel("red",frame-24,x,y)[:3]
            self.assertLessEqual(max(abs(a-b) for a,b in zip(pixels[at:at+3],expected)),10)

    def test_external_movie_audio_is_not_mixed_and_later_clip_audio_uses_its_own_input(self):
        from engine import probe_media,render_project
        project=self.project(recipe(external_only=True,outside="hold"))
        for asset,frequency in zip(project["assets"],(440,880)):
            source=self.root/asset["path"];target=source.with_name(source.stem+"_audio.mkv")
            subprocess.run([shutil.which("ffmpeg"),"-v","error","-nostdin","-y","-threads","1","-i",str(source),
                            "-f","lavfi","-i",f"sine=frequency={frequency}:sample_rate=48000:duration=2",
                            "-c:v","copy","-c:a","pcm_s16le","-shortest",str(target)],
                           check=True,capture_output=True,timeout=10)
            asset.update(path=str(target.relative_to(self.root)),**probe_media(target))
        project["clips"].append({"id":"second_clip","asset_id":"blue","track":0,"start":24,"in":0,"duration":24})
        movie=self.root/"ENGINE_TEST_audio_indices.mp4";render_project(project,self.root,movie,"h264")
        result=subprocess.run([shutil.which("ffmpeg"),"-v","error","-nostdin","-i",str(movie),"-map","0:a:0","-vn",
                               "-ac","1","-ar","48000","-f","f32le","pipe:1"],check=True,capture_output=True,timeout=10)
        samples=struct.unpack("<"+"f"*(len(result.stdout)//4),result.stdout)
        def power(start,frequency):
            window=samples[int(start*48000):int((start+.5)*48000):8]
            real=sum(value*math.cos(2*math.pi*frequency*i/6000) for i,value in enumerate(window))
            imaginary=sum(value*math.sin(2*math.pi*frequency*i/6000) for i,value in enumerate(window))
            return real*real+imaginary*imaginary
        self.assertGreater(power(.25,440),100*power(.25,880))
        self.assertGreater(power(2.25,880),100*power(2.25,440))

    def test_raster_title_after_external_inputs_uses_its_own_picture(self):
        from engine import probe_media,render_project
        project=self.project()
        raster=self.root/"media"/"ENGINE_TEST_title.png"
        subprocess.run([shutil.which("ffmpeg"),"-v","error","-nostdin","-y","-f","lavfi","-i",
                        f"color=green:size={WIDTH}x{HEIGHT}:rate=12","-frames:v","1","-threads","1",str(raster)],
                       check=True,capture_output=True,timeout=10)
        project["assets"].append({"id":"raster_title","path":str(raster.relative_to(self.root)),"name":"ENGINE TEST title",**probe_media(raster)})
        project["titles"]=[{"id":"title","text":"ENGINE TEST","asset_id":"raster_title","start":15,"duration":3}]
        movie=self.root/"ENGINE_TEST_raster_indices.mp4";report=render_project(project,self.root,movie,"h264")
        self.assertEqual(report["frames"],24)
        pixels=decode(movie,rgba=False);size=WIDTH*HEIGHT*3
        for frame in (15,16,17):
            at=frame*size+3*(45*WIDTH+80);r,g,b=pixels[at:at+3]
            self.assertLess(r,5);self.assertGreater(g,120);self.assertLess(b,5)
        at=18*size+3*(45*WIDTH+80)
        self.assertLess(pixels[at+1],30)


if __name__ == "__main__":
    unittest.main()
