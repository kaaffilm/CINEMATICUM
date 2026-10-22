"""Real Lensfun-format import, independent ray math and decoded alpha pixels.

The compact XML is synthetic ENGINE TEST calibration data, not a claim to
have calibrated an actual physical lens. The oracle uses physical sensor
millimeters and a Newton inverse, independently of production image units
and bisection. Projection tests construct 3D rays independently.
"""
from __future__ import annotations

import copy
import hashlib
import http.client
import json
import math
from pathlib import Path
import shutil
import subprocess
import struct
import zlib
import sys
import tempfile
import threading
import unittest

from compositor import lens_map_request, lens_nodes, lens_sample_point, validate_graph, write_lens_maps
from lens_geometry import DEFAULTS, PROJECTIONS, parse_lensfun_xml, validate_profile
from test_lens_compositor import HEIGHT, WIDTH, fixture, graph_for, png_samples, render_pixels


XML = '''<!DOCTYPE lensdatabase SYSTEM "lensfun-database.dtd">
<lensdatabase version="2">
  <lens><maker>ENGINE TEST</maker><model>Measured radial fixture</model><mount>TEST</mount>
    <cropfactor>1.5</cropfactor><aspect-ratio>3:2</aspect-ratio><center x="0.01" y="-0.02"/>
    <calibration>
      <distortion model="poly3" focal="24" k1="-0.02"/>
      <distortion model="poly5" focal="35" k1="0.012" k2="-0.001"/>
      <distortion model="ptlens" focal="50" a="0.001" b="-0.006" c="0.002"/>
      <tca model="linear" focal="24" kr="1.001" kb="0.999"/>
      <vignetting model="pa" focal="24" aperture="4" distance="10" k1="-0.2"/>
    </calibration>
  </lens>
</lensdatabase>'''


def profile(model="ptlens", crop=1.5):
    item = next(row["profile"] for row in parse_lensfun_xml(XML)["calibrations"] if row["profile"]["distortion"] == model)
    item["image_crop"] = crop
    return item


def lensfun(model="ptlens", crop=1.5, direction="undistort"):
    return dict(DEFAULTS, model="lensfun", direction=direction, profile=profile(model, crop))


def fisheye(projection="equidistant", direction="undistort", **values):
    params=dict(DEFAULTS, model="fisheye", projection=projection, direction=direction, fx=.55, fy=.72, cx=.48, cy=.53)
    params.update(values)
    return params


def oracle(params, x, y, width=WIDTH, height=HEIGHT):
    """Independently evaluate calibration in sensor mm or a unit 3D ray."""
    if params["model"] == "lensfun":
        p = params["profile"]
        mm_per_pixel = math.sqrt(36**2 + 24**2) / p["image_crop"] / math.sqrt(width**2 + height**2)
        cx = (width - 1 + min(width - 1, height - 1) * p["center_x"]) / 2
        cy = (height - 1 + min(width - 1, height - 1) * p["center_y"]) / 2
        a, b = (x - cx) * mm_per_pixel, (y - cy) * mm_per_pixel
        radius = math.hypot(a, b)
        half_height = math.sqrt(36**2 + 24**2) / p["calibration_crop"] / math.sqrt(p["calibration_aspect"]**2 + 1) / 2
        c = p["coefficients"]
        if p["distortion"] == "poly3":
            powers = {2: c[0] / (1-c[0])**3 / half_height**2}
        elif p["distortion"] == "poly5":
            powers = {2: c[0] / half_height**2, 4: c[1] / half_height**4}
        else:
            d = 1 - sum(c)
            powers = {1: c[2] / d**2 / half_height, 2: c[1] / d**3 / half_height**2,
                      3: c[0] / d**4 / half_height**3}
        def evaluate(value):
            return (value + sum(k * value**(n + 1) for n, k in powers.items()),
                    1 + sum((n + 1) * k * value**n for n, k in powers.items()))
        if params["direction"] == "undistort": mapped = evaluate(radius)[0]
        else:
            mapped = radius
            for _ in range(20):
                value, derivative = evaluate(mapped)
                step = (value - radius) / derivative
                mapped -= step
                if abs(step) < 1e-13: break
            if abs(evaluate(mapped)[0] - radius) > 1e-10:
                raise AssertionError("Independent physical-millimeter Newton oracle did not converge")
        factor = mapped / radius if radius else 1
        u, v = cx + a * factor / mm_per_pixel, cy + b * factor / mm_per_pixel
    else:
        a = (x - params["cx"] * width) / (params["fx"] * width)
        b = (y - params["cy"] * height) / (params["fy"] * height)
        radius = math.hypot(a, b)
        if radius == 0: return x, y
        projection = params["projection"]
        if params["direction"] == "undistort":
            ray_length = math.sqrt(a*a + b*b + 1)
            cosine = 1 / ray_length
            # Build radius from the ray's direction, rather than the
            # production atan-based scalar or vector implementations.
            mapped = {"equidistant": lambda: math.acos(cosine),
                      "equisolid": lambda: math.sqrt(2 - 2*cosine),
                      "stereographic": lambda: 2 * math.sqrt((1-cosine)/(1+cosine)),
                      "orthographic": lambda: radius / ray_length}[projection]()
        else:
            if projection == "equidistant": cosine = math.cos(radius) if radius < math.pi/2 else -1
            elif projection == "equisolid": cosine = 1 - radius*radius/2
            elif projection == "stereographic": cosine = (4-radius*radius)/(4+radius*radius)
            else: cosine = math.sqrt(1-radius*radius) if radius < 1 else -1
            if cosine <= 0: return None
            mapped = math.sqrt(1-cosine*cosine) / cosine
        factor = mapped / radius
        u, v = params["cx"]*width + a*factor*params["fx"]*width, params["cy"]*height + b*factor*params["fy"]*height
    if not (-1e-7 <= u <= width-1+1e-7 and -1e-7 <= v <= height-1+1e-7): return None
    return max(0, min(u, width-1)), max(0, min(v, height-1))


class LensImportAndSchemaTests(unittest.TestCase):
    def test_actual_xml_exact_samples_hash_and_explicit_scope(self):
        value = parse_lensfun_xml(XML)
        self.assertEqual(len(value["calibrations"]), 3)
        self.assertEqual([r["profile"]["focal_mm"] for r in value["calibrations"]], [24,35,50])
        self.assertEqual(value["source_sha256"], hashlib.sha256(XML.encode()).hexdigest())
        self.assertEqual(len({r["id"] for r in value["calibrations"]}), 3)
        self.assertTrue(any("TCA" in text and "vignetting" in text for text in value["warnings"]))
        self.assertTrue(any("interpolation" in text for text in value["warnings"]))
        for row in value["calibrations"]:
            self.assertEqual(validate_profile(row["profile"]), row["profile"])

    def test_version_one_calibration_attributes_and_portrait_aspect(self):
        value = XML.replace('version="2"','version="1"').replace('<calibration>','<calibration cropfactor="2" aspect-ratio="4:3">')
        rows = parse_lensfun_xml(value)["calibrations"]
        self.assertTrue(all(r["profile"]["calibration_crop"] == 2 and r["profile"]["calibration_aspect"] == 4/3 for r in rows))
        p=lensfun(crop=2)
        for x,y in ((0,0),(44,79),(80,120),(89,159)):
            actual=lens_sample_point(p,x,y,90,160);expected=oracle(p,x,y,90,160)
            self.assertEqual(actual is None,expected is None)
            if actual:self.assertLess(math.dist(actual,expected),1e-8)

    def test_no_external_xml_entities_paths_or_unsupported_model_coercion(self):
        for text in (XML.replace('lensfun-database.dtd','file:///etc/passwd'),
                     '<!DOCTYPE lensdatabase [<!ENTITY x "test">]><lensdatabase version="2"/>',
                     XML.replace('<maker>ENGINE TEST</maker>','<maker>'+('x'*161)+'</maker>'),
                     XML.replace('<aspect-ratio>3:2</aspect-ratio>','<aspect-ratio>3:0</aspect-ratio>'),
                     XML.replace('model="poly3"','model="acm"').replace('model="poly5"','model="acm"').replace('model="ptlens"','model="acm"')):
            with self.subTest(text=text[:80]),self.assertRaises(ValueError):parse_lensfun_xml(text)
        for change in ({"profile":"/tmp/lens.xml"},{"model":["lensfun"]},{"fx":2},{"k1":.01},
                       {"profile":dict(profile(),distortion=["ptlens"])},
                       {"profile":dict(profile(),image_crop=.5)},
                       {"profile":dict(profile(),coefficients=[.99,.99,.99])}):
            p=lensfun();p.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):validate_graph(graph_for(p),WIDTH,HEIGHT)
        for change in ({"projection":["equidistant"]},{"projection":"unknown"},{"profile":profile()},{"k2":.1}):
            p=fisheye();p.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):validate_graph(graph_for(p),WIDTH,HEIGHT)

    def test_brown_schema_identity_and_new_model_resolution_guards(self):
        self.assertEqual(validate_graph(graph_for(DEFAULTS))["nodes"][1]["params"],DEFAULTS)
        self.assertEqual(lens_nodes(graph_for(DEFAULTS)),[])
        self.assertEqual(len(lens_nodes(graph_for(fisheye()))),1)
        for p in (lensfun(),fisheye()):
            with self.assertRaisesRegex(ValueError,'2,073,600'):validate_graph(graph_for(p),3840,2160)
        p=lensfun();p['profile']['coefficients']=[0.,0.,0.]
        self.assertEqual(lens_nodes(graph_for(p)),[])
        validate_graph(graph_for(p),3840,2160)

    @unittest.skipUnless(shutil.which('node'),'Node is required for shipped validator execution')
    def test_shipped_javascript_and_backend_validation_agree(self):
        values=[graph_for(lensfun(model,crop)) for model in ('poly3','poly5','ptlens') for crop in (1.5,2)]
        values += [graph_for(fisheye(model,direction)) for model in PROJECTIONS for direction in ('undistort','distort')]
        for p in (dict(profile(),distortion=['ptlens']),dict(profile(),image_crop=.5),dict(profile(),source_sha256='bad'),dict(profile(),version=True)):
            values.append(graph_for(dict(lensfun(),profile=p)))
        values.append(graph_for(dict(fisheye(),projection=['equidistant'])))
        values.append(graph_for(dict(DEFAULTS,model=None)))
        script="const fs=require('fs'),vm=require('vm'),context={window:{}};vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);process.stdout.write(JSON.stringify(JSON.parse(fs.readFileSync(0,'utf8')).map(g=>context.window.CinematicumCompositor.validate(g))));"
        result=subprocess.run(['node','-e',script,str(Path(__file__).with_name('web')/'compositor-ui.js')],input=json.dumps(values),capture_output=True,text=True,check=True,timeout=5)
        rows=json.loads(result.stdout)
        self.assertEqual([bool(error) for error in rows],[False]*14+[True]*6)
        for graph,error in zip(values,rows):
            try:validate_graph(graph,WIDTH,HEIGHT);accepted=True
            except ValueError:accepted=False
            self.assertEqual(accepted,not error)


class LensGeometryTests(unittest.TestCase):
    def test_all_fisheye_models_and_lensfun_models_match_independent_ray_oracle(self):
        tested=0
        values=[lensfun(model,crop,direction) for model in ('poly3','poly5','ptlens') for crop in (1.5,2) for direction in ('undistort','distort')]
        values += [fisheye(model,direction) for model in PROJECTIONS for direction in ('undistort','distort')]
        for p in values:
            validate_graph(graph_for(p),WIDTH,HEIGHT)
            for y in range(0,HEIGHT,7):
                for x in range(0,WIDTH,9):
                    actual=lens_sample_point(p,x,y,WIDTH,HEIGHT);expected=oracle(p,x,y)
                    self.assertEqual(actual is None,expected is None,(p,x,y))
                    if actual:self.assertLess(math.dist(actual,expected),1e-7,(p,x,y,actual,expected))
                    tested+=1
        self.assertGreater(tested,4500)

    def test_exact_optical_centers_and_behind_plane_coverage(self):
        for model in PROJECTIONS:
            p=fisheye(model);p.update(cx=.5,cy=.5)
            self.assertEqual(lens_sample_point(p,80,45,WIDTH,HEIGHT),(80.,45.))
            p.update(direction='distort',fx=.1,fy=.1)
            self.assertIsNone(lens_sample_point(p,0,0,WIDTH,HEIGHT))

    def test_scalar_and_numpy_numeric_maps_agree_with_quantization(self):
        import numpy as np
        values=[lensfun(model,direction=direction) for model in ('poly3','poly5','ptlens') for direction in ('undistort','distort')]
        values += [fisheye(model,direction) for model in PROJECTIONS for direction in ('undistort','distort')]
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for i,p in enumerate(values):
                one=root/str(i)/'scalar';two=root/str(i)/'vector';one.mkdir(parents=True);two.mkdir()
                request=lens_map_request(p,36,24)
                write_lens_maps(request,one,backend='python');write_lens_maps(request,two,backend='numpy')
                for name in ('x0','x1','y0','y1','wx','wy'):
                    _,_,left=png_samples(one/(name+'.png'));_,_,right=png_samples(two/(name+'.png'))
                    delta=np.max(np.abs(np.asarray(left,dtype=np.int32)-np.asarray(right,dtype=np.int32)))
                    self.assertLessEqual(delta,1 if name in {'wx','wy'} else 0,(i,name))

    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg is required to decode actual movie pixels')
    def test_decoded_movie_alpha_and_picture_match_independent_oracle(self):
        values=[lensfun(model) for model in ('poly3','poly5','ptlens')]
        values += [fisheye(model) for model in PROJECTIONS]
        values += [lensfun('ptlens',direction='distort'),fisheye('equisolid','distort')]
        comparisons=0
        with tempfile.TemporaryDirectory() as temp:
            for i,p in enumerate(values):
                directory=Path(temp)/str(i);directory.mkdir()
                pixels=render_pixels(graph_for(p),directory,frames=1,backend='numpy')
                for y in range(2,HEIGHT-2,7):
                    for x in range(2,WIDTH-2,9):
                        point=oracle(p,x,y)
                        expected=[0.,0.,0.,0.]
                        if point:
                            u,v=point;xx,yy=math.floor(u),math.floor(v);dx,dy=u-xx,v-yy
                            for a,b,weight in ((xx,yy,(1-dx)*(1-dy)),(min(xx+1,WIDTH-1),yy,dx*(1-dy)),(xx,min(yy+1,HEIGHT-1),(1-dx)*dy),(min(xx+1,WIDTH-1),min(yy+1,HEIGHT-1),dx*dy)):
                                rgba=fixture(0,a,b)
                                for c in range(3):expected[c]+=weight*rgba[c]*rgba[3]/255
                                expected[3]+=weight*rgba[3]
                        actual=pixels[(y*WIDTH+x)*4:(y*WIDTH+x)*4+4]
                        self.assertLessEqual(abs(actual[3]-expected[3]),3,(p,x,y,actual,expected))
                        for c in range(3):
                            # Renderer returns straight RGBA; compare the
                            # physically meaningful premultiplied result.
                            self.assertLessEqual(abs(actual[c]*actual[3]/255-expected[c]),4,(p,x,y,actual,expected))
                        comparisons+=1
        self.assertGreater(comparisons,1900)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg is required for actual UNORM16 movie pixels')
    def test_high16_new_models_preserve_numeric_precision_alpha_and_paused_movie_parity(self):
        from engine import probe_media,render_project
        from frame_preview import render_frame
        from test_high_precision import write_fixture,decode_rgba16
        width,height=64,32;maximum=65535
        pixels=[]
        for y in range(height):
            for x in range(width):
                i=y*width+x
                pixels.append((65535,0,65535,0) if x<16 and y<8 else
                              (4096+32*(i%1024),12288+16*(i%1024),49152-24*(i%1024),5000+(i%7)*8000))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=write_fixture(root/'media'/'ENGINE_TEST_high16_lens.mkv',pixels,width=width,height=height,frames=1)
            source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
            asset={'id':'source','name':'ENGINE TEST 16-bit lens samples','path':str(source.relative_to(root)),**probe_media(source)}
            for number,p in enumerate((lensfun(),fisheye('equisolid'),lensfun(direction='distort'),fisheye('equisolid','distort'))):
                project={'version':1,'id':'lens_high16_test','name':'ENGINE TEST lens high16','fps':12,'width':width,'height':height,'assets':[asset],
                         'clips':[{'id':'picture','asset_id':'source','track':0,'start':0,'in':0,'duration':1,'compositor':graph_for(p)}],
                         'titles':[],'settings':{'image_precision':'high16','transparent_background':True}}
                movie=root/f'exports/ENGINE_TEST_lens_{number}.mkv';receipt=render_project(project,root,movie,'master16')
                actual=decode_rgba16(movie)
                self.assertEqual(receipt['processing_bits'],16);self.assertEqual(receipt['pixel_format'],'gbrap16le')
                self.assertEqual(len(actual),width*height)
                self.assertGreater(len({rgba[0] for rgba in actual if rgba[3]>0}),512)
                png=root/f'ENGINE_TEST_lens_{number}.png';preview=render_frame(project,root,0,png)
                self.assertEqual(preview['processing_bits'],16);self.assertEqual(decode_rgba16(png),actual)
                for y in range(height):
                    for x in range(width):
                        point=oracle(p,x,y,width,height);expected=[0.,0.,0.,0.]
                        if point:
                            u,v=point;xx,yy=math.floor(u),math.floor(v);dx,dy=u-xx,v-yy
                            for a,b,w in ((xx,yy,(1-dx)*(1-dy)),(min(xx+1,width-1),yy,dx*(1-dy)),(xx,min(yy+1,height-1),(1-dx)*dy),(min(xx+1,width-1),min(yy+1,height-1),dx*dy)):
                                rgba=pixels[b*width+a]
                                for c in range(3):expected[c]+=w*rgba[c]*rgba[3]/maximum
                                expected[3]+=w*rgba[3]
                        rgba=actual[y*width+x]
                        self.assertLessEqual(abs(rgba[3]-expected[3]),5,(number,x,y,'alpha',rgba,expected))
                        for c in range(3):self.assertLessEqual(abs(rgba[c]*rgba[3]/maximum-expected[c]),5,(number,x,y,c,rgba,expected))
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),source_hash)


class LensProjectWorkflowTests(unittest.TestCase):
    def test_guarded_http_import_does_not_mutate_project_and_profile_saves_reopens(self):
        from server import Server,Store
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp)/'workspace');server=None;thread=None
            try:
                project=store.new_project({'name':'ENGINE TEST Lensfun import','width':WIDTH,'height':HEIGHT,'fps':12})
                server=Server(0,store);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.025},daemon=True);thread.start()
                path=store.project_dir(project['id'])/'project.json';before=path.read_bytes()
                connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                route='/api/projects/'+project['id']+'/lensfun-import';body=json.dumps({'text':XML})
                headers={'Content-Type':'application/json','X-Cinematicum-Token':store.token}
                connection.request('POST',route,body,headers);response=connection.getresponse();data=json.loads(response.read());self.assertEqual(response.status,200)
                self.assertEqual(path.read_bytes(),before)
                self.assertEqual(data['calibrations'][2]['profile'],profile())
                connection.request('POST',route,body,{'Content-Type':'application/json'});response=connection.getresponse();response.read();self.assertEqual(response.status,403)
                connection.close()
                # Graphs remain normal project data. Real media admission
                # provides a renderable source rather than a dangling asset.
                source=Path(temp)/'ENGINE_TEST_source.png'
                def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
                raw=(b'\0'+b'\x55\x66\x77'*WIDTH)*HEIGHT
                source.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',WIDTH,HEIGHT,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))
                asset=store.admit(project['id'],source,source.name)
                current=store.get(project['id']);current['clips']=[{'id':'lens_clip','asset_id':asset['id'],'start':0,'in':0,'duration':4,'track':0,'compositor':graph_for(lensfun())}]
                saved=store.save(project['id'],current)
                self.assertEqual(saved['clips'][0]['compositor']['nodes'][1]['params']['profile'],profile())
                self.assertEqual(store.get(project['id'])['clips'],saved['clips'])
            finally:
                if server:server.shutdown();server.server_close()
                if thread:thread.join(timeout=1)
                store.shutdown()
            reopened=Store(Path(temp)/'workspace')
            try:self.assertEqual(reopened.get(project['id'])['clips'][0]['compositor']['nodes'][1]['params']['profile'],profile())
            finally:reopened.shutdown()


if __name__ == '__main__':unittest.main()
