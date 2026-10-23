"""Independent real-PCM oracles for stereo buses, aux returns and loudness.

All source signals are synthetic ENGINE TEST media. Expected routing is a
literal delayed-sample equation; spectral and R128 checks measure decoded
audio, rather than comparing emitted filter strings to the implementation.
"""
from __future__ import annotations
import copy
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

import numpy as np
import audio_mixer as mixer

RATE=48000
FFMPEG=shutil.which('ffmpeg')


def graph(**changes):
    value={'version':1,'buses':[],'tracks':[],'master':{'gain':1,'loudness':{'enabled':False}}}
    value.update(changes);return value


class AudioMixerValidationTests(unittest.TestCase):
    def test_feedback_unknown_send_track_and_executable_values_are_rejected(self):
        cases=[graph(buses=[{'id':'a','output':'b'},{'id':'b','output':'a'}]),
            graph(buses=[{'id':'master'}]),graph(buses=[{'id':'a','inserts':[{'type':'shell','command':'touch /tmp/unowned'}]}]),
            graph(buses=[{'id':'a','inserts':[{'type':'highpass','frequency_hz':'100;anull'}]}]),
            graph(tracks=[{'track':-1,'sends':[{'bus':'absent','gain':1}]}]),
            graph(tracks=[{'track':-1},{'track':-1}]),graph(master={'gain':float('inf')}),
            graph(master={'loudness':{'enabled':True,'true_peak_dbfs':.1}})]
        for value in cases:
            with self.subTest(value=value),self.assertRaises(ValueError):mixer.validate_mixer(value,{-1})
        with self.assertRaises(ValueError):mixer.validate_mixer(graph(tracks=[{'track':-2}]),{-1})

    def test_document_edit_is_independent_and_does_not_create_optional_state(self):
        project={'clips':[{'track':-1}],'tracks':[],'assets':[]}
        unchanged=copy.deepcopy(project)
        self.assertEqual(mixer.validate_project_mixer(copy.deepcopy(project)),project)
        edited=mixer.apply_edit(project,{'mixer':graph(buses=[{'id':'return','inserts':[{'type':'delay','milliseconds':10}]}],tracks=[{'track':-1,'sends':[{'bus':'return','gain':.2}]}])})
        self.assertEqual(project,unchanged);self.assertIn('audio_mixer',edited)
        self.assertEqual(mixer.apply_edit(edited,{'mixer':None}),project)

    def test_repeated_filter_summary_cannot_erase_earlier_nonfinite_evidence(self):
        lines=[]
        for stage in ('input','normalized','final'):
            for key,value in [('Peak level dB',-20),('Number of NaNs',1 if stage=='normalized' else 0),('Number of Infs',0)]:
                lines.append(f'[astats@mix_{stage} @ 0xabc] {key}: {value}')
        lines.append('[astats@mix_normalized @ 0xdef] Number of NaNs: 0')
        with self.assertRaisesRegex(ValueError,'Repeated audio DSP evidence'):
            mixer.accept_normalization_audits(lines,{'mix'})


@unittest.skipUnless(FFMPEG,'Actual FFmpeg is required')
class AudioMixerPCMTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='cinematicum-audio-mixer-ENGINE-TEST-');self.root=Path(self.temp.name)

    def tearDown(self):self.temp.cleanup()

    def render(self,value,sources,*,name='mixed'):
        count=max(len(s) for s in sources)
        inputs=[];feeds=[]
        for index,source in enumerate(sources):
            path=self.root/f'{name}-{index}.f32';np.asarray(source,dtype='<f4').tofile(path)
            inputs.extend(['-f','f32le','-ar',str(RATE),'-ac','2','-i',str(path)])
            feeds.append((f'in{index}',-1-index))
        filters=[f'anullsrc=r=48000:cl=stereo,atrim=end_sample={count}[silence]']
        filters.extend(f'[{i}:a]aformat=sample_fmts=fltp:channel_layouts=stereo[in{i}]' for i in range(len(sources)))
        compiled,label,metadata=mixer.compile_graph(value,feeds,count)
        filters.extend(compiled);filters.append(f'[{label}]apad=whole_len={count},atrim=end_sample={count},asetpts=PTS-STARTPTS[out]')
        script=self.root/f'{name}-graph.txt';script.write_text(';\n'.join(filters))
        output=self.root/f'{name}.wav'
        audit=metadata['normalization_audit_required']
        process=subprocess.run([FFMPEG,'-v','info' if audit else 'error','-nostdin','-y','-filter_complex_threads','1',*inputs,
            '-filter_complex_script',str(script),'-map','[out]','-c:a','pcm_f32le',str(output)],capture_output=True,timeout=12)
        self.assertEqual(process.returncode,0,process.stderr.decode(errors='replace'))
        if audit:metadata['normalization_receipts']=mixer.accept_normalization_audits(process.stderr.decode(errors='replace'),{audit})
        raw=subprocess.run([FFMPEG,'-v','error','-nostdin','-i',str(output),'-map','0:a:0','-f','f32le','pipe:1'],capture_output=True,check=True,timeout=4).stdout
        actual=np.frombuffer(raw,dtype='<f4').reshape((-1,2))
        self.assertEqual(actual.shape,(count,2));self.assertTrue(np.isfinite(actual).all())
        return actual,output,metadata

    def test_buses_sends_return_gain_and_delay_follow_literal_sample_equation(self):
        rng=np.random.default_rng(14483);a=rng.uniform(-.025,.025,(RATE,2)).astype('<f4')
        b=np.zeros_like(a);b[2300]=[.07,-.03];b[17000]=[-.02,.04]
        value=graph(buses=[{'id':'dialogue','gain':.5},
            {'id':'return','gain':.25,'output':'dialogue','inserts':[{'type':'delay','milliseconds':10}]}],
            tracks=[{'track':-1,'output':'dialogue','sends':[{'bus':'return','gain':.4}]},
                {'track':-2,'output':'none','sends':[{'bus':'return','gain':.8}]}],master={'gain':.7})
        actual,_,report=self.render(value,[a,b])
        delayed_a=np.concatenate((np.zeros((480,2)),a[:-480]));delayed_b=np.concatenate((np.zeros((480,2)),b[:-480]))
        expected=.7*.5*(a+.25*(.4*delayed_a+.8*delayed_b))
        self.assertLess(float(np.max(np.abs(actual-expected))),8e-9)
        self.assertEqual(report['post_fader_send_count'],2)
        value['buses'][1]['mute']=True
        muted,_,_=self.render(value,[a,b],name='muted-return')
        self.assertLess(float(np.max(np.abs(muted-.35*a))),5e-9)

    def test_equal_and_opposite_stereo_channels_do_not_downmix_or_crossfeed(self):
        t=np.arange(RATE)/RATE;left=.1*np.sin(2*np.pi*619*t);a=np.stack((left,-left),axis=1).astype('<f4')
        actual,_,_=self.render(graph(buses=[{'id':'stem','gain':.75}],tracks=[{'track':-1,'output':'stem'}]),[a])
        self.assertLess(float(np.max(np.abs(actual[:,0]+actual[:,1]))),1e-9)
        self.assertLess(float(np.max(np.abs(actual-.75*a))),1e-8)
        self.assertGreater(float(np.sqrt(np.mean(actual[:,0]**2))),.04)

    def test_real_bus_filter_rejects_low_tone_without_losing_high_tone(self):
        t=np.arange(RATE*2)/RATE
        a=np.stack((.1*np.sin(2*np.pi*60*t),.1*np.sin(2*np.pi*3000*t)),axis=1).astype('<f4')
        actual,_,_=self.render(graph(buses=[{'id':'dialogue','inserts':[{'type':'highpass','frequency_hz':500}]}],tracks=[{'track':-1,'output':'dialogue'}]),[a])
        rms=np.sqrt(np.mean(actual[RATE:]**2,axis=0))
        self.assertLess(rms[0],.002);self.assertGreater(rms[1],.065)

    def test_real_stereo_linked_compressor_reduces_dynamic_level_ratio(self):
        t=np.arange(RATE*4)/RATE;level=np.where(t<2,.02,.6)
        a=np.stack((level*np.sin(2*np.pi*1000*t),.5*level*np.sin(2*np.pi*1000*t)),axis=1).astype('<f4')
        value=graph(buses=[{'id':'voice','inserts':[{'type':'compressor','threshold_db':-20,'ratio':6,'attack_ms':2,'release_ms':50}]}],tracks=[{'track':-1,'output':'voice'}])
        actual,_,_=self.render(value,[a]);quiet=np.sqrt(np.mean(actual[RATE:RATE*2,0]**2));loud=np.sqrt(np.mean(actual[RATE*3:,0]**2))
        self.assertGreater(quiet,.012);self.assertLess(loud/quiet,10)
        self.assertLess(float(np.max(np.abs(actual[:,1]-.5*actual[:,0]))),1e-7)

    def test_actual_r128_meter_and_normalized_export_match_independent_tone_reference(self):
        t=np.arange(RATE*4)/RATE;a=np.stack([.1*np.sin(2*np.pi*1000*t)]*2,axis=1).astype('<f4')
        _,original,_=self.render(graph(),[a],name='reference')
        measured=mixer.measure_media(original,FFMPEG,timeout=6)
        # Two in-phase 1 kHz stereo channels at peak .1 are -20 LUFS under
        # BS.1770 K weighting (within filter/coefficient rounding).
        self.assertAlmostEqual(measured['integrated_lufs'],-20,delta=.2)
        self.assertAlmostEqual(measured['true_peak_dbfs'],-20,delta=.15)
        self.assertFalse(measured['silent'])
        _,normalized,_=self.render(graph(master={'gain':1,'loudness':{'enabled':True,'integrated_lufs':-23,'true_peak_dbfs':-1,'range_lu':7}}),[a],name='normalized')
        accepted=mixer.measure_media(normalized,FFMPEG,timeout=6)
        self.assertAlmostEqual(accepted['integrated_lufs'],-23,delta=.3)
        self.assertLessEqual(accepted['true_peak_dbfs'],-.8)
        self.assertNotEqual(original.read_bytes(),normalized.read_bytes())

    def test_silence_meter_and_precancel_are_explicit(self):
        _,silent,_=self.render(graph(),[np.zeros((RATE,2),dtype='<f4')],name='silence')
        report=mixer.measure_media(silent,FFMPEG,timeout=4)
        self.assertTrue(report['silent']);self.assertIsNone(report['true_peak_dbfs'])
        self.assertIsNone(report['integrated_lufs']);self.assertTrue(report['decoded_output_finite'])
        normalized,_,metadata=self.render(graph(master={'loudness':{'enabled':True}}),[np.zeros((RATE,2),dtype='<f4')],name='normalized-silence')
        self.assertFalse(np.any(normalized));self.assertEqual(len(normalized),RATE)
        self.assertTrue(metadata['normalization_receipts'][0]['input_exact_silence'])
        self.assertTrue(metadata['normalization_receipts'][0]['target_unreachable'])
        event=threading.Event();event.set()
        with self.assertRaises(InterruptedError):mixer.measure_media(silent,FFMPEG,cancel_event=event,timeout=4)


if __name__=='__main__':unittest.main(verbosity=2)
