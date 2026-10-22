"""Measured ENGINE TEST pitch, stereo and retained-curve sample invariants.

Numerical tests use independently synthesized tones, not the retimer's source
clock as an audio oracle. The media test also decodes the real FFV1/PCM
intermediate through FFmpeg and verifies selected source-stream routing.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import numpy as np

import retime
import retime_worker


RATE=48_000


def recipe(duration=48,speed0=.5,speed1=1.5,origin=12):
    return {'version':1,'method':'nearest','audio':'pitch_preserve','offset':0,
        'source_origin':{'numerator':str(origin),'denominator':'1'},
        'keys':[{'frame':0,'speed':speed0},{'frame':duration,'speed':speed1}]}


def request(curve,duration,*,fps=Fraction(24),start=0,origin=Fraction(0),audio_first=0,audio_count=RATE*10):
    # Exact absolute boundary subtraction, independently of timebase helpers.
    absolute=Fraction(origin)+start
    first=round(absolute*RATE/fps);last=round((absolute+duration)*RATE/fps)
    phase=Fraction(first)-absolute*RATE/fps
    q=Fraction(curve['offset'])*RATE/fps+phase
    grid=math.floor(q+Fraction(1,2))
    return {'samples':last-first,'recipe':copy.deepcopy(curve),
        'fps':{'numerator':fps.numerator,'denominator':fps.denominator},
        'sample_phase':float(phase),'source_origin':float(Fraction(curve['source_origin']['numerator'])/int(curve['source_origin']['denominator'])),
        'audio_first':audio_first,'audio_count':audio_count,
        'audio_grid_start':grid,'audio_grid_phase':float(q-grid)}


def peak(signal):
    signal=np.asarray(signal,dtype=np.float64)
    spectrum=np.abs(np.fft.rfft(signal*np.hanning(len(signal)),n=262144))
    index=int(np.argmax(spectrum))
    return index*RATE/262144


class PitchRetimeNumericalTests(unittest.TestCase):
    def render(self,source,value):
        with tempfile.TemporaryDirectory(prefix='cinematicum-pitch-ENGINE-TEST-') as name:
            root=Path(name)
            np.asarray(source,dtype='<f4').tofile(root/'source.f32')
            value={**value,'audio_count':len(source)}
            report=retime_worker.audio(np,value,root)
            actual=np.fromfile(root/'retimed.f32',dtype='<f4').reshape((-1,2))
        self.assertTrue(np.isfinite(actual).all())
        self.assertEqual(actual.shape,(value['samples'],2))
        return actual,report

    @staticmethod
    def source(shared=False):
        n=np.arange(RATE*10,dtype=np.float64)
        left=.2*np.sin(2*np.pi*440*n/RATE+.2)
        right=.13*(np.cos(2*np.pi*440*n/RATE+.2) if shared else np.sin(2*np.pi*880*n/RATE-.4))
        return np.stack((left,right),axis=1).astype('<f4')

    def test_constant_speed_extremes_and_variable_ramp_preserve_measured_pitch(self):
        source=self.source()
        for a,b in ((.25,.25),(4,4),(.5,1.5),(4,.25)):
            with self.subTest(start_speed=a,end_speed=b):
                curve=recipe(speed0=a,speed1=b)
                actual,report=self.render(source,request(curve,48))
                self.assertEqual(len(actual),96_000)
                self.assertTrue(report['pitch_preserved'])
                self.assertEqual(report['mode'],'pitch_preserve')
                for begin in (8000,40000,72000):
                    sample=actual[begin:begin+12000]
                    self.assertLess(abs(peak(sample[:,0])-440),1)
                    self.assertLess(abs(peak(sample[:,1])-880),1)
                    self.assertGreater(float(np.sqrt(np.mean(sample[:,0]**2))),.08)
                    # The independently routed right tone must not appear in
                    # the left channel merely because stereo phases are linked.
                    n=np.arange(len(sample));leak=abs(np.sum(sample[:,0]*np.exp(-2j*np.pi*880*n/RATE)))*2/len(sample)
                    self.assertLess(leak,.005)

    def test_stereo_relative_phase_and_level_remain_linked(self):
        actual,_=self.render(self.source(shared=True),request(recipe(),48))
        sample=actual[12000:84000].astype(np.float64)
        n=np.arange(len(sample));oscillator=np.exp(-2j*np.pi*440*n/RATE)
        phasors=np.sum(sample*np.hanning(len(sample))[:,None]*oscillator[:,None],axis=0)
        difference=np.angle(phasors[1]/phasors[0])
        self.assertLess(abs(difference-np.pi/2),.015)
        self.assertLess(abs(abs(phasors[1]/phasors[0])-.65),.01)

    def test_unity_speed_retains_original_stereo_waveform(self):
        rng=np.random.default_rng(5638)
        source=rng.uniform(-.15,.15,(RATE*10,2)).astype('<f4')
        actual,_=self.render(source,request(recipe(speed0=1,speed1=1),48))
        self.assertLess(float(np.max(np.abs(actual-source[24000:120000]))),1e-7)

    def test_amplitude_event_follows_independently_inverted_variable_clock(self):
        time=np.arange(RATE*10,dtype=np.float64)/RATE
        envelope=.025+.175*np.exp(-.5*((time-2)/.025)**2)
        source=np.stack((envelope*np.sin(2*np.pi*440*time),
            envelope*np.sin(2*np.pi*880*time)),axis=1).astype('<f4')
        actual,_=self.render(source,request(recipe(),48))
        # Original event at 2s, source origin .5s. Inside this ramp the
        # independent source clock is .5+.5t+.25t², so t=sqrt(7)-1.
        energy=np.convolve(actual[:,0].astype(np.float64)**2,np.ones(1024)/1024,mode='same')
        measured=int(np.argmax(energy))/RATE
        self.assertLess(abs(measured-(math.sqrt(7)-1)),.055,
            'The peak must follow the variable source clock, within one finite analysis window')

    def test_fractional_origin_split_and_trim_reproduce_identical_samples(self):
        source=self.source();fps=Fraction(30000,1001);origin=Fraction(5,2)
        curve=recipe();whole,_=self.render(source,request(curve,48,fps=fps,start=7,origin=origin))
        left,_=self.render(source,request(curve,17,fps=fps,start=7,origin=origin))
        right_curve=copy.deepcopy(curve);right_curve['offset']=17
        right,_=self.render(source,request(right_curve,31,fps=fps,start=24,origin=origin))
        self.assertEqual(len(whole),len(left)+len(right))
        self.assertTrue(np.array_equal(np.concatenate((left,right)),whole),
            'A split must retain prefix phase state and the same global sample lattice')
        # Decode a different source subwindow; no memmap-relative position or
        # source-origin rebase may change the retained-curve result.
        sub=request(right_curve,31,fps=fps,start=24,origin=origin,audio_first=6000)
        changed,_=self.render(source[6000:],sub)
        self.assertTrue(np.array_equal(changed,right))

    def test_explicit_mode_validation_and_silent_sources(self):
        curve=recipe()
        self.assertEqual(retime.validate_recipe(curve,48)['audio'],'pitch_preserve')
        bad=copy.deepcopy(curve);bad['audio']='preserve_pitch'
        with self.assertRaises(ValueError):retime.validate_recipe(bad,48)
        actual,report=self.render(np.zeros((RATE,2),dtype='<f4'),request(curve,48))
        self.assertFalse(np.any(actual));self.assertTrue(report['pitch_preserved'])


class PitchRetimeMediaTests(unittest.TestCase):
    def test_actual_selected_pcm_stream_mux_and_fractional_split(self):
        from engine import probe_media
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            raise unittest.SkipTest('Actual FFmpeg and ffprobe are required')
        runtime=retime.capabilities()
        if not runtime.get('available'):
            raise unittest.SkipTest(runtime.get('reason','Pinned Tracking runtime unavailable'))
        with tempfile.TemporaryDirectory(prefix='cinematicum-pitch-media-ENGINE-TEST-') as name:
            root=Path(name);(root/'media').mkdir()
            source=PitchRetimeNumericalTests.source()
            other=np.stack((np.zeros(len(source)),.1*np.sin(2*np.pi*173*np.arange(len(source))/RATE)),axis=1).astype('<f4')
            source.tofile(root/'selected.f32');other.tofile(root/'other.f32')
            def ffmpeg(args):
                return subprocess.run([shutil.which('ffmpeg'),'-v','error','-nostdin','-y','-threads','1',*map(str,args)],capture_output=True,check=True,timeout=30).stdout
            movie=root/'media/ENGINE_TEST_selected.mkv'
            ffmpeg(['-f','f32le','-ar',RATE,'-ac',2,'-i',root/'other.f32',
                '-f','f32le','-ar',RATE,'-ac',2,'-i',root/'selected.f32',
                '-map','0:a','-map','1:a','-c:a','pcm_f32le',movie])
            asset={**probe_media(movie),'id':'sound','name':movie.name,'path':'media/'+movie.name,'sha256':hashlib.sha256(movie.read_bytes()).hexdigest()}
            rate=Fraction(30000,1001);origin=Fraction(5,2);curve=recipe()
            clip={'id':'pitch','asset_id':'sound','start':7,'in':12,'duration':48,'speed':1,'reverse':False,
                'audio':{'stream_index':1,'channels':[1,0]},'retime':curve}
            project={'frame_rate':{'numerator':rate.numerator,'denominator':rate.denominator}}
            observations=[]
            def render(value,label):
                output,media,report=retime.prepare(project,value,asset,root,root/label,audio_origin=origin)
                pcm=np.frombuffer(ffmpeg(['-i',output,'-map','0:a:0','-f','f32le','pipe:1']),dtype='<f4').reshape((-1,2))
                self.assertEqual(report['output_samples'],len(pcm));self.assertTrue(report['audio']['pitch_preserved'])
                self.assertEqual(report['selected_audio'],{'stream_index':1,'channels':[1,0]})
                self.assertEqual(media['codec'],'ffv1');self.assertEqual(report['source_sha256'],asset['sha256'])
                observations.append({'name':label,'sample_frames':len(pcm),'report':report})
                return pcm
            whole=render(clip,'whole');left=copy.deepcopy(clip);left['duration']=17
            right=copy.deepcopy(clip);right.update(start=24,duration=31);right['retime']['offset']=17
            right['in']=float(retime.source_position(right,0))
            self.assertTrue(np.array_equal(np.concatenate((render(left,'left'),render(right,'right'))),whole))
            self.assertLess(abs(peak(whole[12000:24000,0])-880),1)
            self.assertLess(abs(peak(whole[12000:24000,1])-440),1)
            self.assertEqual(hashlib.sha256(movie.read_bytes()).hexdigest(),asset['sha256'])
            evidence=os.environ.get('CINEMATICUM_PITCH_RETIME_TEST_REPORT')
            if evidence:
                Path(evidence).write_text(json.dumps({'kind':'pitch-retime-actual-media-ENGINE-TEST','observations':observations,
                    'selected_left_peak_hz':peak(whole[12000:24000,0]),'selected_right_peak_hz':peak(whole[12000:24000,1]),
                    'split_pcm_identical':True,'source_unchanged':True},sort_keys=True,indent=2)+'\n')


if __name__=='__main__':
    unittest.main(verbosity=2)
