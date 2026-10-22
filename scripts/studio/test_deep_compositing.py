"""Actual deep EXR roundtrips, independent radiance checks and owned-job gates.

The runtime cases use CINEMATICUM_IMAGING_PYTHON and never download or install
anything. They write real OpenEXR fixtures with the public library API and
read exported sample arrays independently of the coordinator's JSON receipt.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

import deep_compositing as deep


def recipe(source="a" * 64):
    return {"version": 1, "nodes": [{"id": "source", "op": "source", "source_id": source}],
            "outputs": ["source"], "preview": {"auxiliary": "front"}}


PREAMBLE = '''
import sys, json, pathlib, math, struct
import numpy as np
import OpenEXR as exr
sys.path.insert(0, sys.argv[1])
import deep_compositing_worker as w
root = pathlib.Path(sys.argv[2])
def fixture(name, pixels, types=None, view=None, origin=(0,0), extra=None):
    types = types or {}
    names = list(pixels[0])
    channels = {}
    for channel in names:
        array = np.empty((1, len(pixels)), dtype=object)
        for x, values in enumerate(pixels):
            array[0,x] = np.asarray(values[channel], dtype=types.get(channel, 'float32'))
        channels[channel] = array
    lower = np.array(origin, dtype=np.int32)
    upper = lower + np.array([len(pixels)-1, 0], dtype=np.int32)
    header = {'type': exr.deepscanline, 'compression': exr.ZIPS_COMPRESSION,
              'dataWindow': (lower, upper), 'displayWindow': (lower, upper),
              'name': name, 'pixelAspectRatio': 1.0}
    if view is not None: header['view'] = view
    if extra: header.update(extra)
    path = root / (name + '.exr')
    exr.File(header, channels).write(str(path))
    return path
def rgba(z, a, r, g=None, b=None, back=None, **extra):
    result = {'Z': z, 'A': a, 'R': r, 'G': g if g is not None else [0.]*len(z),
              'B': b if b is not None else [0.]*len(z)}
    if back is not None: result['ZBack'] = back
    result.update(extra)
    return result
def image(name, pixel, **kwargs):
    return w.read_exr(fixture(name, [pixel], **kwargs))[0]
'''


class DeepGraphValidationTests(unittest.TestCase):
    def test_graph_normalization_is_pure_and_optional_project_field_is_explicit(self):
        original = recipe()
        before = copy.deepcopy(original)
        result = deep.validate_deep_recipe(original)
        self.assertEqual(original, before)
        self.assertEqual(result["nodes"][0]["part"], 0)
        self.assertEqual(result["preview"]["transfer"], "linear_to_srgb")
        self.assertIsNone(deep.validate_project_deep(None))
        self.assertEqual(deep.validate_project_deep(original), result)

    def test_cycles_missing_references_and_unreachable_work_are_rejected(self):
        valid = recipe()
        bad = [
            {**valid, "nodes": [{"id": "loop", "op": "flatten", "input": "loop"}], "outputs": ["loop"]},
            {**valid, "outputs": ["missing"]},
            {**valid, "nodes": valid["nodes"] + [{"id": "unused", "op": "flatten", "input": "source"}]},
            {**valid, "nodes": valid["nodes"] * 2},
            {**valid, "outputs": [["source"]]},
            {**valid, "nodes": [{"id": "one", "op": "flatten", "input": "two"}, {"id": "two", "op": "flatten", "input": "one"}], "outputs": ["one"]},
        ]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                deep.validate_deep_recipe(value)

    def test_paths_scripts_unknown_keys_and_nonfinite_controls_are_rejected(self):
        valid = recipe()
        for alteration in ({"version": True}, {"script": "x"}, {"preview": {"exposure": float("nan")}},
                           {"preview": {"output": True}}, {"preview": {"channels": ["R"]}},
                           {"preview": {"transfer": "arbitrary"}}, {"preview": {"alpha": "bad\nname"}}):
            with self.subTest(alteration=alteration), self.assertRaises(ValueError):
                deep.validate_deep_recipe({**valid, **alteration})
        for node in ({"id": "source", "op": "source", "source_id": "../../media/file"},
                     {"id": "source", "op": "source", "source_id": "a" * 64, "path": "/tmp/x"},
                     {"id": "source", "op": "python", "expression": "1"}):
            with self.subTest(node=node), self.assertRaises(ValueError):
                deep.validate_deep_recipe({**valid, "nodes": [node]})

    def test_channel_schema_prevents_ambiguous_renames_and_uint_loss(self):
        for changes in ({"rename": {"R": "x", "G": "x"}}, {"remove": ["R", "R"]},
                        {"remove": ["R"], "rename": {"R": "x"}}, {"scale": {"R": {"expression": "x"}}},
                        {"create": {"object.id": {"type": "uint", "value": 2**32}}},
                        {"create": {"object.id": {"type": "uint", "value": .5}}}):
            graph = recipe()
            graph["nodes"].append({"id": "edit", "op": "channels", "input": "source", **changes})
            graph["outputs"] = ["edit"]
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                deep.validate_deep_recipe(graph)

    def test_optional_runtime_unavailable_is_honest_and_coordinator_imports_no_optional_packages(self):
        self.assertFalse(deep.deep_capabilities("/not/installed/python")["available"])
        code = "import sys;sys.path.insert(0,sys.argv[1]);import deep_compositing;assert not {'numpy','OpenEXR'} & set(sys.modules)"
        result = subprocess.run([sys_executable(), "-I", "-B", "-c", code, str(Path(__file__).parent)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


def sys_executable():
    import sys
    return sys.executable


class DeepEXRRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.python = deep.find_imaging_python()
        if not cls.python:
            raise unittest.SkipTest("The optional isolated imaging runtime is not installed")
        available = deep.deep_capabilities(cls.python)
        if not available["available"]:
            raise unittest.SkipTest(available.get("reason", "Deep EXR runtime is unavailable"))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cinematicum-deep-TEST-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def code(self, value, timeout=35):
        result = subprocess.run([self.python, "-I", "-B", "-c", PREAMBLE + "\n" + value,
                                 str(Path(__file__).parent), str(self.root)], capture_output=True, text=True, timeout=timeout)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def admit_fixture(self, name="source"):
        self.code(f"fixture({name!r}, [rgba([1.,3.],[.5,1.],[.25,0.],b=[0.,1.], **{{'object.id':[4294967295,17]}})], types={{'object.id':'uint32'}})")
        return deep.import_deep_source(self.root, self.root / f"{name}.exr", f"{name}.exr", self.python)

    def test_actual_multipart_roundtrip_preserves_deep_values_types_views_windows_and_metadata(self):
        self.code('''
left = image('left', rgba([3.,1.],[.25,.5],[.1,.4], back=[4.,1.], **{'object.id':[4294967295,16777217], 'motion.X':[-12.,7.]}),
             types={'R':'float16','object.id':'uint32'}, view='left', origin=(-17,30), extra={'shotLabel':'synthetic-test'})
right = image('right', rgba([2.],[.75],[.6], back=[2.], **{'object.id':[123456789], 'motion.X':[.125]}),
              types={'R':'float16','object.id':'uint32'}, view='right', origin=(-17,30), extra={'shotLabel':'synthetic-test'})
w.write_exr(root/'multi.exr', [left,right])
with exr.File(str(root/'multi.exr'), separate_channels=True) as actual:
    assert len(actual.parts)==2
    for p, original, view in zip(actual.parts, [left,right], ['left','right']):
        assert p.header['type']==exr.deepscanline and p.header['view']==view
        assert p.header['shotLabel']=='synthetic-test'
        np.testing.assert_array_equal(p.header['dataWindow'][0], [-17,30])
        assert set(p.channels)==set(original.channels)
        for name in p.channels:
            np.testing.assert_array_equal(p.channels[name].pixels[0,0], original.channels[name][0,0])
            assert p.channels[name].pixels[0,0].dtype == original.channels[name][0,0].dtype
decoded=w.read_exr(root/'multi.exr')
assert [p.header['view'] for p in decoded]==['left','right']
''')

    def test_unsorted_point_occlusion_and_merge_retain_real_individual_samples(self):
        self.code('''
a=image('a',rgba([5.,1.],[1.,1.],[0.,1.],b=[1.,0.]))
b=image('b',rgba([3.],[.5],[0.],g=[.5]))
merged=w.merge(a,b)
np.testing.assert_array_equal(merged.channels['Z'][0,0],[1,3,5])
assert len(merged.channels['A'][0,0])==3
flat=w.flatten(merged,'error')
np.testing.assert_allclose([flat.channels[c][0,0] for c in 'RGBA'],[1,0,0,1],atol=1e-7)
w.write_exr(root/'merged.exr',[merged])
with exr.File(str(root/'merged.exr'),separate_channels=True) as f:
    assert f.parts[0].header['type']==exr.deepscanline
    assert len(f.channels()['Z'].pixels[0,0])==3
''')

    def test_overlapping_volumes_match_independent_fine_step_radiative_integral(self):
        self.code('''
# Two differently colored homogeneous media overlap only over [2,4].
sa,sb=.4,.7
aa,ab=1-math.exp(-3*sa),1-math.exp(-3*sb)
a=image('a',rgba([1.],[aa],[aa],back=[4.]))
b=image('b',rgba([2.],[ab],[0.],b=[ab],back=[5.]))
result=w.over(a,b,'error')
np.testing.assert_allclose(result.channels['Z'][0,0],[1,2,4])
np.testing.assert_allclose(result.channels['ZBack'][0,0],[2,4,5])
actual=w.flatten(result,'error')
# Midpoint integration in 200k equal depth slices, independent of split/merge code.
z=np.linspace(1,5,200000,endpoint=False)+.00001
da=np.where(z<4,sa,0.); db=np.where(z>=2,sb,0.); dz=.00002
optical=(np.cumsum(da+db)-.5*(da+db))*dz
expected=[np.sum(np.exp(-optical)*da)*dz, 0., np.sum(np.exp(-optical)*db)*dz, 1-math.exp(-3*(sa+sb))]
np.testing.assert_allclose([actual.channels[c][0,0] for c in 'RGBA'],expected,rtol=3e-7,atol=1e-7)
# Input order cannot alter physical RGBA, although an explicit aux tie may differ.
reverse=w.flatten(w.over(b,a,'error'),'error')
for c in 'RGBA': np.testing.assert_allclose(actual.channels[c],reverse.channels[c],atol=1e-7)
''')

    def test_point_inside_volume_splits_depth_and_obeys_front_transmittance(self):
        self.code('''
a=image('a',rgba([1.],[.75],[.75],back=[3.]))
b=image('b',rgba([2.],[1.],[0.],b=[1.],back=[2.]))
result=w.over(a,b,'error')
np.testing.assert_array_equal(result.channels['Z'][0,0],[1,2,2])
np.testing.assert_array_equal(result.channels['ZBack'][0,0],[2,2,3])
flat=w.flatten(result,'error')
np.testing.assert_allclose([flat.channels[c][0,0] for c in 'RGBA'],[.5,0,.5,1],atol=1e-7)
''')

    def test_equal_depth_points_are_symmetric_and_zero_alpha_emission_survives(self):
        self.code('''
a=image('a',rgba([2.],[.5],[.5]))
b=image('b',rgba([2.],[.5],[0.],b=[.5]))
flat=w.flatten(w.over(a,b,'error'),'error')
np.testing.assert_allclose([flat.channels[c][0,0] for c in 'RGBA'],[.375,0,.375,.75],atol=1e-7)
emission=image('light',rgba([1.],[0.],[2.],back=[3.]))
mask=image('cut',rgba([2.],[1.],[0.],back=[2.]))
out=w.holdout(emission,mask,'error')
np.testing.assert_allclose(out.channels['R'][0,0],[1.],atol=1e-7)
np.testing.assert_allclose(out.channels['A'][0,0],[0.],atol=1e-7)
opaque1=image('opaque1',rgba([1.],[1.],[1.]))
opaque2=image('opaque2',rgba([1.],[1.],[0.],b=[1.]))
f=w.flatten(w.over(opaque1,opaque2,'error'),'error')
np.testing.assert_allclose([f.channels[c][0,0] for c in 'RGBA'],[.5,0,.5,1],atol=1e-7)
''')

    def test_layered_and_color_specific_alpha_use_their_actual_associations(self):
        self.code('''
p=rgba([1.,2.],[.1,.2],[.4,.6], **{'AR':[.5,.75], 'layer.A':[.25,.5], 'layer.R':[.2,.4], 'layer.inner.G':[.1,.3]})
a=image('layers',p)
flat=w.flatten(a,'error')
assert abs(float(flat.channels['R'][0,0])-(.4+.5*.6))<1e-7
assert abs(float(flat.channels['layer.R'][0,0])-(.2+.75*.4))<1e-7
assert abs(float(flat.channels['layer.inner.G'][0,0])-(.1+.75*.3))<1e-7
assert abs(float(flat.channels['A'][0,0])-.28)<1e-7
assert abs(float(flat.channels['AR'][0,0])-.875)<1e-7
''')

    def test_opaque_holdout_clips_crossing_volume_and_rejects_fractional_matte(self):
        self.code('''
a=image('subject',rgba([1.,5.],[.75,1.],[.75,0.],b=[0.,1.],back=[3.,5.]))
mask=image('matte',{'Z':[2.],'A':[1.]})
result=w.holdout(a,mask,'error')
np.testing.assert_array_equal(result.channels['Z'][0,0],[1.])
np.testing.assert_array_equal(result.channels['ZBack'][0,0],[2.])
np.testing.assert_allclose(result.channels['A'][0,0],[.5],atol=1e-7)
np.testing.assert_allclose(result.channels['R'][0,0],[.5],atol=1e-7)
fraction=image('fraction',{'Z':[2.],'A':[.5]})
try: w.holdout(a,fraction,'front')
except ValueError as e: assert 'fractional' in str(e)
else: raise AssertionError('fractional holdout falsely accepted')
''')

    def test_fully_occluded_empty_deep_output_is_still_real_typed_deep_exr(self):
        self.code('''
a=image('subject',rgba([2.],[1.],[1.], **{'object.id':[4294967295]}),types={'object.id':'uint32'})
mask=image('matte',{'Z':[1.],'A':[1.]})
result=w.holdout(a,mask,'error')
w.write_exr(root/'empty.exr',[result])
decoded=w.read_exr(root/'empty.exr')[0]
assert decoded.deep and decoded.types['object.id']=='uint'
for name in decoded.channels: assert len(decoded.channels[name][0,0])==0
np.testing.assert_array_equal(w.flatten(decoded,'error').channels['A'],[[0.]])
''')

    def test_auxiliary_overlap_requires_explicit_policy_and_uint_is_never_rounded(self):
        self.code('''
a=image('a',rgba([1.],[.5],[.5],back=[3.], **{'object.id':[4294967295], 'motion.X':[-4.]}),types={'object.id':'uint32'})
b=image('b',rgba([2.],[.5],[0.],b=[.5],back=[4.], **{'object.id':[16777217], 'motion.X':[8.]}),types={'object.id':'uint32'})
try: w.over(a,b,'error')
except ValueError as e: assert 'auxiliary' in str(e)
else: raise AssertionError('ambiguous auxiliary mixture accepted')
merged=w.merge(a,b)
np.testing.assert_array_equal(merged.channels['object.id'][0,0],[4294967295,16777217])
result=w.over(a,b,'front')
np.testing.assert_array_equal(result.channels['object.id'][0,0],[4294967295,4294967295,16777217])
flat=w.flatten(result,'front')
assert flat.channels['object.id'][0,0]==4294967295
''')

    def test_deep_over_promotes_mixed_half_float_auxiliary_without_losing_front_values(self):
        self.code('''
value=np.float32(0.123456791)
a=image('half_back',rgba([2.],[.5],[.25], **{'velocity.x':[0.], 'object.id':[4294967295]}),types={'velocity.x':'float16','object.id':'uint32'})
b=image('float_front',rgba([1.],[.5],[.125], **{'velocity.x':[value], 'object.id':[16777217]}),types={'velocity.x':'float32','object.id':'uint32'})
for index,(first,second) in enumerate(((a,b),(b,a))):
    combined=w.over(first,second,'front')
    assert combined.types['velocity.x']=='float'
    assert combined.channels['velocity.x'][0,0][0]==value
    w.write_exr(root/('promoted'+str(index)+'.exr'),[combined])
    decoded=w.read_exr(root/('promoted'+str(index)+'.exr'))[0]
    assert decoded.types['velocity.x']=='float'
    assert decoded.channels['velocity.x'][0,0][0]==value
    np.testing.assert_array_equal(decoded.channels['object.id'][0,0],[16777217,4294967295])
    assert w.flatten(decoded,'front').channels['velocity.x'][0,0]==value
bad=image('mixed_uint',rgba([1.],[.5],[.125], **{'velocity.x':[1], 'object.id':[16777217]}),types={'velocity.x':'uint32','object.id':'uint32'})
try: w.over(a,bad,'front')
except ValueError as error: assert 'UINT' in str(error)
else: raise AssertionError('mixed UINT auxiliary silently converted')
''')

    def test_channel_edit_preserves_arbitrary_types_and_checks_uint_range(self):
        self.code('''
import deep_compositing as d
a=image('a',rgba([1.],[.5],[.25], **{'object.id':[4294967295], 'velocity.x':[-3.]}),types={'R':'float16','object.id':'uint32'})
node={'id':'edit','op':'channels','input':'source','rename':{'velocity.x':'motion.X'},'remove':['G'],
      'scale':{'R':{'multiply':2},'motion.X':{'multiply':-1,'add':1}},
      'create':{'G':{'type':'half','value':.125},'matte.id':{'type':'uint','value':16777217}}}
graph={'version':1,'nodes':[{'id':'source','op':'source','source_id':'a'*64},node],'outputs':['edit']}
normalized=d.validate_deep_recipe(graph)['nodes'][1]
out=w.channel_ops(a,normalized)
assert out.channels['R'][0,0].dtype==np.float16
assert out.channels['R'][0,0][0]==.5 and out.channels['motion.X'][0,0][0]==4
assert out.channels['matte.id'][0,0][0]==16777217 and 'velocity.x' not in out.channels
normalized['scale']={'object.id':{'multiply':1,'add':1}}
try: w.channel_ops(a,normalized)
except ValueError as e: assert 'UINT' in str(e)
else: raise AssertionError('UINT overflow accepted')
''')

    def test_binary_mismatched_views_windows_or_channels_are_not_silently_coerced(self):
        self.code('''
a=image('a',rgba([1.],[.5],[.5]),view='left')
others=[image('right',rgba([1.],[.5],[.5]),view='right'),
        image('window',rgba([1.],[.5],[.5]),view='left',origin=(1,0)),
        image('channels',rgba([1.],[.5],[.5],extra=[2.]),view='left')]
for b in others:
    try: w.over(a,b,'front')
    except ValueError: pass
    else: raise AssertionError('incompatible binary input silently changed')
''')

    def test_legacy_singlepart_multiview_is_normalized_without_channel_loss(self):
        self.code('''
channels={n: np.array([[v]],dtype=np.float32) for n,v in {'R':.2,'G':0.,'B':0.,'A':.5,
 'right.R':0.,'right.G':.3,'right.B':0.,'right.A':.75,'layer.left.R':.1,'layer.left.A':.25,
 'unassigned.data':4.}.items()}
exr.File({'multiView':['left','right'],'type':exr.scanlineimage,'compression':exr.ZIP_COMPRESSION},channels).write(str(root/'stereo.exr'))
parts=w.read_exr(root/'stereo.exr')
assert [p.header.get('view') for p in parts]==['left','right',None]
assert 'layer.R' in parts[0].channels and 'unassigned.data' in parts[2].channels
w.write_exr(root/'normalized.exr',parts)
with exr.File(str(root/'normalized.exr'),separate_channels=True) as f:
    assert len(f.parts)==3 and all('multiView' not in p.header for p in f.parts)
    assert f.parts[1].channels['G'].pixels[0,0]==np.float32(.3)
''')

    def test_flat_arbitrary_channels_and_flat_over_export_remain_flat(self):
        self.code('''
for name,r,a,ident in [('a',.25,.5,4294967295),('b',.5,1.,16777217)]:
    channels={c:np.array([[v]],np.float32) for c,v in {'R':r,'G':0.,'B':0.,'A':a,'motion.X':-3.}.items()}
    channels['object.id']=np.array([[ident]],np.uint32)
    exr.File({'type':exr.scanlineimage},channels).write(str(root/(name+'.exr')))
a,b=[w.read_exr(root/(n+'.exr'))[0] for n in ['a','b']]
out=w.over(a,b,'front')
assert not out.deep and out.channels['object.id'][0,0]==4294967295
assert out.channels['R'][0,0]==.5 and out.channels['A'][0,0]==1.
w.write_exr(root/'out.exr',[out])
with exr.File(str(root/'out.exr'),separate_channels=True) as f:
    assert f.parts[0].header['type']==exr.scanlineimage
    assert f.channels()['object.id'].pixels.dtype==np.uint32
''')

    def test_preflight_rejects_deep_allocation_bomb_before_library_pixel_decode(self):
        self.code('''
path=fixture('small',[rgba([1.],[.5],[.5])])
data=bytearray(path.read_bytes())
# Locate the known final chunk via its offset table, then forge only its
# declared unpacked sample size. No giant allocation or giant fixture needed.
import io
stream=io.BytesIO(data);stream.seek(8)
while True:
    name=w._cstring(stream)
    if not name:break
    w._cstring(stream); n=struct.unpack('<I',stream.read(4))[0];stream.seek(n,1)
offset=struct.unpack('<Q',stream.read(8))[0]
struct.pack_into('<Q',data,offset+4+16,2**40)
(root/'bomb.exr').write_bytes(data)
original=exr.File
def forbidden(*args,**kwargs):raise AssertionError('pixel decoder called before bounding deep chunk size')
exr.File=forbidden
try:
    try:w.read_exr(root/'bomb.exr')
    except ValueError as e:assert 'bound' in str(e) or 'inconsistent' in str(e)
    else:raise AssertionError('allocation bomb accepted')
finally:exr.File=original
''')

    def test_real_source_admission_freezes_hash_and_rejects_tamper_or_symlink(self):
        source = self.admit_fixture()
        self.assertEqual(source["sha256"], hashlib.sha256((self.root / source["path"]).read_bytes()).hexdigest())
        self.assertEqual(source["parts"][0]["total_samples"], 2)
        self.assertEqual(deep.list_deep_sources(self.root)[0]["id"], source["id"])
        link = self.root / "linked.exr"
        link.symlink_to(self.root / "source.exr")
        with self.assertRaises(ValueError):
            deep.import_deep_source(self.root, link, "linked.exr", self.python)
        (self.root / source["path"]).write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            deep.run_deep_compositing({}, self.root, recipe(source["id"]), self.root / "deep/outputs/tamper", python=self.python)

    def test_end_to_end_worker_writes_real_deep_and_flat_parts_and_bound_receipt(self):
        source = self.admit_fixture()
        graph = recipe(source["id"])
        graph["nodes"].append({"id": "flat", "op": "flatten", "input": "source", "auxiliary": "front"})
        graph["outputs"] = ["source", "flat"]
        events = []
        result = deep.run_deep_compositing({}, self.root, graph, self.root / "deep/outputs/real", progress=events.append, python=self.python)
        self.assertEqual(set(Path(result["path"]).parent.iterdir()), {self.root / "deep/outputs/real" / name for name in deep.ARTIFACT_NAMES})
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["recipe"], deep.validate_deep_recipe(graph))
        self.assertEqual([p["deep"] for p in receipt["output"]["parts"]], [True, False])
        self.assertEqual(result["provenance"]["display_encoding"], "sRGB")
        self.assertEqual(events[-1], 1)
        for kind, item in result["artifacts"].items():
            self.assertEqual(hashlib.sha256((Path(result["path"]).parent / item["filename"]).read_bytes()).hexdigest(), item["sha256"])
        self.code('''
with exr.File(str(root/'deep/outputs/real/composite.exr'),separate_channels=True) as f:
    assert len(f.parts)==2
    assert f.parts[0].header['type']==exr.deepscanline and len(f.parts[0].channels['Z'].pixels[0,0])==2
    assert f.parts[0].channels['object.id'].pixels[0,0][0]==4294967295
    assert f.parts[1].header['type']==exr.scanlineimage
    assert f.parts[1].channels['object.id'].pixels[0,0]==4294967295
    np.testing.assert_allclose(f.parts[1].channels['R'].pixels,[[.25]],atol=1e-7)
''')

    def test_rgb_preview_projects_only_selected_channels_without_reducing_exported_ids(self):
        source = self.admit_fixture()
        graph = recipe(source["id"])
        graph["preview"]["auxiliary"] = "error"
        result = deep.run_deep_compositing({}, self.root, graph, self.root / "deep/outputs/preview-projection", python=self.python)
        self.assertEqual(result["receipt"]["preview"]["source_channels"], ["R", "G", "B"])
        self.code('''
with exr.File(str(root/'deep/outputs/preview-projection/composite.exr'),separate_channels=True) as f:
    assert f.parts[0].header['type']==exr.deepscanline
    np.testing.assert_array_equal(f.channels()['object.id'].pixels[0,0],[4294967295,17])
''')

    def test_cancelled_owned_worker_publishes_nothing_and_preserves_source(self):
        source = self.admit_fixture()
        event = threading.Event()
        real_popen = subprocess.Popen
        children = []
        def launch(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            children.append(child)
            event.set()  # Cancel the actual spawned process, not a fake job.
            return child
        with patch.object(deep.subprocess, "Popen", side_effect=launch), self.assertRaisesRegex(RuntimeError, "cancelled"):
            deep.run_deep_compositing({}, self.root, recipe(source["id"]), self.root / "deep/outputs/cancelled",
                                      cancel_event=event, python=self.python)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        self.assertFalse((self.root / "deep/outputs/cancelled").exists())
        self.assertEqual(list((self.root / "deep/outputs").iterdir()), [])
        self.assertEqual(hashlib.sha256((self.root / source["path"]).read_bytes()).hexdigest(), source["sha256"])

    def test_output_identity_cannot_overwrite_an_existing_job_or_escape_project(self):
        source = self.admit_fixture()
        target = self.root / "deep/outputs/existing"
        target.mkdir(parents=True)
        (target / "owned").write_bytes(b"preserve")
        for output in (target, self.root / "outside", self.root.parent / "outside-deep"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                deep.run_deep_compositing({}, self.root, recipe(source["id"]), output, python=self.python)
        self.assertEqual((target / "owned").read_bytes(), b"preserve")


if __name__ == "__main__":
    unittest.main()
