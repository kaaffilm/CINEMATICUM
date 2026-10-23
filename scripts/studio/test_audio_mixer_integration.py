"""Actual engine and float-audio path acceptance for authored mixer graphs."""
from __future__ import annotations
import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from engine import probe_media,render_project,validate_project
from audio_mixer import validate_mixer

RATE=48000
FFMPEG=shutil.which('ffmpeg')


def mixer(gain=1):return {'version':1,'buses':[],'tracks':[],'master':{'gain':gain}}


@unittest.skipUnless(FFMPEG and shutil.which('ffprobe'),'Actual FFmpeg and ffprobe are required')
class AudioMixerEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='cinematicum-mix-integrated-ENGINE-TEST-');self.root=Path(self.temp.name);(self.root/'media').mkdir()
        t=np.arange(RATE*4)/RATE
        self.a=np.stack((.08*np.sin(2*np.pi*193*t),.06*np.sin(2*np.pi*317*t)),axis=1).astype('<f4')
        self.b=np.zeros_like(self.a);self.b[1000:1010]=[.1,-.07];self.b[33000:33010]=[-.05,.02]
        self.assets=[]
        for name,data in (('a',self.a),('b',self.b)):
            raw=self.root/(name+'.f32');data.tofile(raw);path=self.root/'media'/('ENGINE_TEST_'+name+'.wav')
            self.ff(['-f','f32le','-ar',RATE,'-ac',2,'-i',raw,'-c:a','pcm_f32le',path])
            self.assets.append({**probe_media(path),'id':name,'name':path.name,'path':'media/'+path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})

    def tearDown(self):self.temp.cleanup()

    @staticmethod
    def ff(arguments):return subprocess.run([FFMPEG,'-v','error','-nostdin','-y','-threads','1','-filter_threads','1',*map(str,arguments)],capture_output=True,check=True,timeout=10).stdout

    def pcm(self,path):return np.frombuffer(self.ff(['-i',path,'-map','0:a:0','-f','f32le','pipe:1']),dtype='<f4').reshape((-1,2))

    def project(self):return {'version':1,'id':'mix-engine','name':'ENGINE TEST buses','width':16,'height':16,'fps':24,'assets':copy.deepcopy(self.assets),'clips':[],'titles':[],'tracks':[],'settings':{}}

    def routed(self):
        p=self.project();p['sequence_duration']=60
        p['clips']=[{'id':'a','asset_id':'a','track':-1,'start':3,'in':2,'duration':48,'volume':.5,'audio':{'pan':.25}},
            {'id':'b','asset_id':'b','track':-2,'start':0,'in':0,'duration':48,'volume':.25}]
        p['tracks']=[{'id':-1,'gain':.4},{'id':-2,'gain':.5}]
        p['audio_mixer']={'version':1,'buses':[{'id':'stem','gain':.6},{'id':'return','gain':.5,'output':'stem','inserts':[{'type':'delay','milliseconds':10}]}],
            'tracks':[{'track':-1,'output':'stem','sends':[{'bus':'return','gain':.3}]},{'track':-2,'output':'none','sends':[{'bus':'return','gain':.8}]}],
            'master':{'gain':.7}}
        return validate_project(p,self.root)

    def expected(self):
        a=np.zeros((120000,2));a[6000:102000]=self.a[4000:100000]*[.15,.2]
        b=np.zeros_like(a);b[:96000]=self.b[:96000]*.125
        delayed_a=np.concatenate((np.zeros((480,2)),a[:-480]));delayed_b=np.concatenate((np.zeros((480,2)),b[:-480]))
        return .7*.6*(a+.5*(.3*delayed_a+.8*delayed_b))

    def test_actual_prores_pcm_applies_existing_controls_once_then_bus_graph(self):
        p=self.routed();before=copy.deepcopy(p);out=self.root/'ENGINE_TEST_mix.mov'
        report=render_project(p,self.root,out,'prores');actual=self.pcm(out)
        self.assertEqual(actual.shape,(120000,2));self.assertLess(float(np.max(np.abs(actual-self.expected()))),2/32768)
        self.assertEqual(p,before);self.assertEqual(report['audio_mixer'],p['audio_mixer'])
        self.assertEqual(report['audio_meter']['measured_export_sha256'],hashlib.sha256(out.read_bytes()).hexdigest())
        self.assertFalse(report['audio_meter']['silent'])
        self.assertTrue(all(hashlib.sha256((self.root/a['path']).read_bytes()).hexdigest()==a['sha256'] for a in p['assets']))

    def test_float_audio_path_preserves_original_track_routing_after_picture_flattening(self):
        from float_movie import _audio
        p=self.routed();scratch=self.root/'float-audio';scratch.mkdir()
        output,metadata=_audio(p,self.root,scratch,None);actual=self.pcm(output)
        self.assertEqual(metadata['samples'],120000)
        self.assertLess(float(np.max(np.abs(actual-self.expected()))),2e-8)

    def test_normalized_engine_export_has_measured_target_loudness(self):
        p=self.project();p['clips']=[{'id':'tone','asset_id':'a','track':-1,'duration':96}]
        p['audio_mixer']=mixer();p['audio_mixer']['master']['loudness']={'enabled':True,'integrated_lufs':-23,'true_peak_dbfs':-1,'range_lu':7}
        out=self.root/'ENGINE_TEST_normalized.mov';report=render_project(p,self.root,out,'prores')
        self.assertAlmostEqual(report['audio_meter']['integrated_lufs'],-23,delta=.4)
        self.assertLessEqual(report['audio_meter']['true_peak_dbfs'],-.8)
        self.assertEqual(len(self.pcm(out)),192000)
        self.assertTrue(report['audio_meter']['decoded_output_finite'])
        self.assertFalse(report['audio_normalization'][0]['input_exact_silence'])

    def test_normalized_exact_silence_is_finite_and_target_is_explicitly_unreachable(self):
        p=self.project();p['sequence_duration']=24
        p['audio_mixer']=mixer();p['audio_mixer']['master']['loudness']={'enabled':True}
        out=self.root/'ENGINE_TEST_normalized_silence.mov';report=render_project(p,self.root,out,'prores')
        actual=self.pcm(out)
        self.assertEqual(actual.shape,(RATE,2));self.assertTrue(np.isfinite(actual).all());self.assertFalse(np.any(actual))
        self.assertTrue(report['audio_meter']['silent']);self.assertTrue(report['audio_meter']['decoded_output_finite'])
        self.assertTrue(report['audio_normalization'][0]['input_exact_silence'])
        self.assertTrue(report['audio_normalization'][0]['target_unreachable'])
        from float_movie import _audio
        scratch=self.root/'float-silent';scratch.mkdir();output,_=_audio(validate_project(p,self.root),self.root,scratch,None)
        self.assertFalse(np.any(self.pcm(output)))
        self.assertTrue(json.loads((scratch/'audio-normalization-audit.json').read_text())[0]['target_unreachable'])

    def test_real_non_silent_nan_is_refused_before_atomic_publication(self):
        import audio_mixer
        p=self.project();p['clips']=[{'id':'tone','asset_id':'a','track':-1,'duration':96}]
        p['audio_mixer']=mixer();p['audio_mixer']['master']['loudness']={'enabled':True}
        original_compile=audio_mixer.compile_graph;injected=[];bad_value='0/0'
        def corrupt(*args,**kwargs):
            filters,label,metadata=original_compile(*args,**kwargs)
            prefix=metadata['normalization_audit_required']
            if prefix:
                target=',astats@'+prefix+'_normalized='
                replacement=",aeval=exprs='if(eq(n,4096),"+bad_value+",val(0))|val(1)':channel_layout=stereo"+target
                filters=[line.replace(target,replacement) for line in filters];injected.append(prefix)
            return filters,label,metadata
        out=self.root/'ENGINE_TEST_keep_completed.mov';sentinel=b'ENGINE TEST existing accepted export';out.write_bytes(sentinel)
        for bad_value in ('0/0','1/0'):
            with self.subTest(actual_expression=bad_value),patch('audio_mixer.compile_graph',side_effect=corrupt):
                with self.assertRaisesRegex(ValueError,'nonfinite audio'):
                    render_project(p,self.root,out,'prores')
            self.assertEqual(out.read_bytes(),sentinel)
        self.assertEqual(injected,['mix','mix'])
        self.assertFalse(any('.partial' in f.name for f in self.root.iterdir()))

    def test_repeated_child_normalizers_have_independent_evidence_and_parent_meter(self):
        p=self.project();p.update(sequence_id='main',sequence_name='Main',
            clips=[{'id':'first','sequence_id':'child','track':-1,'start':0,'duration':24},
                {'id':'second','sequence_id':'child','track':-2,'start':24,'duration':24}],
            sequences=[{'id':'child','name':'Child','clips':[{'id':'source','asset_id':'a','track':-1,'duration':24}],
                'titles':[],'tracks':[],'audio_mixer':mixer()}])
        p['sequences'][0]['audio_mixer']['master']['loudness']={'enabled':True}
        out=self.root/'ENGINE_TEST_child_loudness.mov';report=render_project(p,self.root,out,'prores')
        self.assertEqual(len(report['audio_normalization']),2)
        self.assertEqual(len({item['instance'] for item in report['audio_normalization']}),2)
        self.assertIsNone(report['audio_mixer']);self.assertIn('child',report['audio_mixers'])
        self.assertTrue(report['audio_meter']['decoded_output_finite'])

    def test_unity_routing_preserves_fractional_frame_sample_grid_exactly(self):
        p=self.project();p.pop('fps');p['frame_rate']={'numerator':30000,'denominator':1001};p['sequence_duration']=40
        p['clips']=[{'id':'fractional','asset_id':'a','track':-1,'start':5,'in':1.5,'duration':30,'volume':.5,'audio':{'pan':.3}}]
        p['tracks']=[{'id':-1,'gain':.7}]
        direct=self.root/'ENGINE_TEST_direct_fractional.mov';render_project(p,self.root,direct,'prores')
        p['audio_mixer']=mixer();routed=self.root/'ENGINE_TEST_bus_fractional.mov';render_project(p,self.root,routed,'prores')
        before,after=self.pcm(direct),self.pcm(routed)
        self.assertEqual(len(after),64064);self.assertTrue(np.array_equal(before,after))

    def test_child_mix_is_applied_once_and_parent_mix_never_inherits_into_child(self):
        p=self.project();p.update(sequence_id='main',sequence_name='Main',audio_mixer=mixer(.4),
            clips=[{'id':'nest','sequence_id':'child','track':-2,'start':0,'in':0,'duration':24}],
            sequences=[{'id':'child','name':'Child','clips':[{'id':'source','asset_id':'a','track':-1,'start':0,'in':0,'duration':24}],'titles':[],'tracks':[]}])
        for child_gain in (None,.5):
            value=copy.deepcopy(p)
            if child_gain is not None:value['sequences'][0]['audio_mixer']=mixer(child_gain)
            out=self.root/('ENGINE_TEST_nested_'+str(child_gain)+'.mov');render_project(value,self.root,out,'prores')
            actual=self.pcm(out);expected=self.a[:48000]*(.4 if child_gain is None else .2)
            self.assertEqual(len(actual),48000);self.assertLess(float(np.max(np.abs(actual-expected))),2/32768)

    def test_sequence_switch_and_saved_json_preserve_each_independent_mix(self):
        from editorial import apply_action
        p=self.routed();first=copy.deepcopy(p['audio_mixer'])
        created=apply_action(p,'sequence_create',{'name':'Second mix'},self.root)['project']
        self.assertNotIn('audio_mixer',created)
        second=apply_action(created,'audio_mixer_apply',{'mixer':mixer(.3)},self.root)['project']
        restored=apply_action(second,'sequence_switch',{'sequence_id':'main'},self.root)['project']
        self.assertEqual(restored['audio_mixer'],first)
        saved=self.root/'ENGINE_TEST_project.json';saved.write_text(json.dumps(restored))
        reopened=validate_project(json.loads(saved.read_text()),self.root)
        self.assertEqual(reopened['audio_mixer'],first)
        self.assertEqual(reopened['sequences'][0]['audio_mixer'],validate_mixer(mixer(.3)))


if __name__=='__main__':unittest.main(verbosity=2)
