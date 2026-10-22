"""Actual OTIO 0.18 operators, decoded pictures and source-PCM acceptance.

Fixtures are synthetic ENGINE TEST material; no production project is opened.
"""
import array
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave

import numpy as np

from editorial import apply_action, sequence_views
from engine import render_project, validate_project
from interchange import export_otio, import_otio, _item, _range, _rt
from timebase import parse_rate

try:
    import opentimelineio as otio
except ImportError:
    otio = None


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Actual FFmpeg required')
class OtioCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='cinematicum-OTIO-composition-ENGINE-TEST-')
        cls.root=Path(cls.temp.name);(cls.root/'media').mkdir()
        cls.original_pcm={}
        frames=96;count=frames*2000
        n=np.arange(count)
        for ident,channel in (('red',0),('blue',2)):
            pixels=np.zeros((frames,32,48,3),dtype=np.uint8)
            pixels[:,:,:,channel]=np.arange(frames,dtype=np.uint8)[:,None,None]+100
            # Seven wide binary bars survive the normal delivery encoder.
            # Decode their source-frame number independently of engine timing.
            for bit in range(7):
                pixels[:,24:32,bit*6:(bit+1)*6,:]=np.where((np.arange(frames)>>bit)&1,240,8)[:,None,None,None]
            pcm=np.stack((((n*37+(1 if ident=='red' else 997))%12001)-6000,
                          ((n*59+(777 if ident=='red' else 13))%10007)-5003),axis=1).astype('<i2')
            cls.original_pcm[ident]=pcm
            wav=cls.root/f'{ident}.wav'
            with wave.open(str(wav),'wb') as output:
                output.setnchannels(2);output.setsampwidth(2);output.setframerate(48000);output.writeframes(pcm.tobytes())
            cls.ffmpeg(['-f','rawvideo','-pixel_format','rgb24','-video_size','48x32','-framerate','24','-i','pipe:0',
                '-i',str(wav),'-c:v','ffv1','-pix_fmt','gbrp','-c:a','pcm_s16le','-shortest',str(cls.root/'media'/f'{ident}.mkv')],pixels.tobytes())
        # Source alpha is essential: ordinary source-over opacity is *not* a
        # dissolve. The independent pixel oracle below tests the distinction.
        for ident,rgba in (('red_alpha',(240,0,0,128)),('blue_alpha',(0,0,200,64))):
            cls.ffmpeg(['-f','rawvideo','-pixel_format','rgba','-video_size','48x32','-i','pipe:0','-frames:v','1','-threads','1',
                str(cls.root/'media'/f'{ident}.png')],bytes(rgba)*48*32)
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
    @staticmethod
    def ffmpeg(args,data=None):
        return subprocess.run([shutil.which('ffmpeg'),'-v','error','-nostdin','-y','-filter_complex_threads','1','-threads','1']+args,
            input=data,capture_output=True,check=True,timeout=30).stdout
    def project(self):
        return validate_project({'version':1,'id':'composition_test','name':'ENGINE TEST OTIO composition','fps':24,
            'width':48,'height':32,'assets':[{'id':name,'path':f'media/{name}.'+('png' if 'alpha' in name else 'mkv')}
                for name in ('red','blue','red_alpha','blue_alpha')],'clips':[],'titles':[],'tracks':[],'settings':{}},self.root)
    @staticmethod
    def strip(value):
        if isinstance(value,dict):return {key:{} if key=='metadata' else OtioCompositionTests.strip(item) for key,item in value.items()}
        if isinstance(value,list):return [OtioCompositionTests.strip(item) for item in value]
        return value
    def mapping(self):
        return {asset['path']:asset['id'] for asset in self.project()['assets']}
    def clip(self,ident,start=8,duration=12,speed=1,kind='Video'):
        rate=parse_rate(24);suffix='png' if 'alpha' in ident else 'mkv'
        reference={'OTIO_SCHEMA':'ExternalReference.1','name':ident,'target_url':f'media/{ident}.{suffix}',
            'metadata':{},'available_range':None if suffix=='png' else _range(0,96,rate),'available_image_bounds':None}
        effects=[] if speed==1 else [{'OTIO_SCHEMA':'LinearTimeWarp.1','name':'Test constant retime','effect_name':'LinearTimeWarp','metadata':{},'enabled':True,'time_scalar':speed}]
        return _item('Clip.2',ident,source_range=_range(start,duration,rate),media_references={'DEFAULT_MEDIA':reference},active_media_reference_key='DEFAULT_MEDIA',effects=effects)
    def document(self,children,kind='Video',**kwargs):
        rate=parse_rate(24)
        return {'OTIO_SCHEMA':'Timeline.1','name':'ENGINE TEST public OTIO','metadata':{},'global_start_time':_rt(0,rate),
            'tracks':_item('Stack.1','Tracks',children=[_item('Track.1',kind,children=children,kind=kind)],**kwargs)}
    def transition(self,inside=2,outside=3):
        rate=parse_rate(24)
        return {'OTIO_SCHEMA':'Transition.1','name':'ENGINE TEST dissolve','metadata':{},'transition_type':'SMPTE_Dissolve',
            'in_offset':_rt(inside,rate),'out_offset':_rt(outside,rate)}
    def import_public(self,document):
        return import_otio(document,self.project(),self.root,self.mapping())['project']
    def render(self,project,name,high=False):
        p=copy.deepcopy(project)
        if high:p.setdefault('settings',{}).update(image_precision='high16',transparent_background=True)
        path=self.root/(name+('.mkv' if high else '.mov'))
        render_project(p,self.root,path,'master16' if high else 'prores')
        pictures=np.frombuffer(self.ffmpeg(['-i',str(path),'-map','0:v:0','-pix_fmt','rgba','-threads','1','-f','rawvideo','pipe:1']),dtype=np.uint8).reshape(-1,32,48,4)
        pcm=np.frombuffer(self.ffmpeg(['-i',str(path),'-map','0:a:0','-f','s16le','pipe:1']),dtype='<i2').reshape(-1,2)
        return pictures,pcm
    @staticmethod
    def counters(pictures):
        return sum(((pictures[:,28,bit*6+3,:3].mean(axis=1)>120).astype(int)<<bit) for bit in range(7))
    @unittest.skipUnless(otio,'Actual upstream OpenTimelineIO runtime required')
    def test_signed_timewarp_official_output_duration_and_private_serializer_roundtrip(self):
        for speed in (.25,.5,2,4,-.5,-1,-2):
            with self.subTest(speed=speed):
                p=self.project();p['clips']=[{'id':'retime','asset_id':'red','track':0,'start':3,'in':12.5,'duration':12,
                    'speed':abs(speed),'reverse':speed<0}];p=validate_project(p,self.root)
                exported=export_otio(p,self.root)['document']
                official=otio.adapters.read_from_string(json.dumps(exported),'otio_json')
                self.assertEqual(official.duration().value,15)
                public_clip=next(c for c in official.tracks[0] if isinstance(c,otio.schema.Clip))
                self.assertEqual(public_clip.duration().value,12)
                self.assertEqual(public_clip.effects[0].time_scalar,speed)
                serialized=otio.adapters.write_to_string(official,'otio_json')
                self.assertEqual(import_otio(serialized,p,self.root)['project'],p)
                public=self.import_public(self.strip(json.loads(serialized)))
                self.assertEqual([(c['in'],c['duration'],c['speed'],c['reverse']) for c in public['clips']],[(12.5,12,abs(speed),speed<0)]*2)
                a=self.render(p,'retime_original_'+str(speed));b=self.render(public,'retime_public_'+str(speed))
                np.testing.assert_array_equal(a[0],b[0]);np.testing.assert_array_equal(a[1],b[1])
    def test_reverse_picture_order_and_every_source_pcm_sample_are_independent(self):
        document=self.document([self.clip('red',8,12,-1)])
        audio=copy.deepcopy(document['tracks']['children'][0]);audio['kind']='Audio';document['tracks']['children'].append(audio)
        actual=self.import_public(document);pictures,pcm=self.render(actual,'independent_reverse')
        # Frame counter is in every red pixel, independent of importer/renderer.
        np.testing.assert_array_equal(self.counters(pictures),np.arange(19,7,-1))
        np.testing.assert_array_equal(pcm,self.original_pcm['red'][8*2000:20*2000][::-1])
    @unittest.skipUnless(otio,'Actual upstream OpenTimelineIO runtime required')
    def test_same_track_overlaps_preserve_original_painter_order_and_additive_pcm(self):
        p=self.project();p['clips']=[
            {'id':'first_in_painter_order','asset_id':'red','track':0,'start':8,'in':0,'duration':16},
            {'id':'second_in_painter_order','asset_id':'blue','track':0,'start':0,'in':0,'duration':16},
            {'id':'third','asset_id':'red','track':0,'start':6,'in':30,'duration':6}]
        p=validate_project(p,self.root);document=export_otio(p,self.root)['document']
        official=otio.adapters.read_from_string(json.dumps(document),'otio_json')
        self.assertEqual(official.duration().value,24)
        self.assertIsInstance(official.tracks[0][0],otio.schema.Stack)
        self.assertEqual(len(official.tracks[0][0]),3)
        rebuilt=self.import_public(self.strip(document));a=self.render(p,'overlap_original');b=self.render(rebuilt,'overlap_imported')
        np.testing.assert_array_equal(a[0],b[0]);np.testing.assert_array_equal(a[1],b[1])
        self.assertGreater(int(b[0][7,16,24,0]),int(b[0][7,16,24,2]))
        self.assertGreater(int(b[0][13,16,24,2]),int(b[0][13,16,24,0]))
    @unittest.skipUnless(otio,'Actual upstream OpenTimelineIO runtime required')
    def test_dissolve_handles_match_upstream_expansion_and_all_rendered_samples(self):
        document=self.document([self.clip('red',8,12),self.transition(),self.clip('blue',20,12)])
        audio=copy.deepcopy(document['tracks']['children'][0]);audio['kind']='Audio';document['tracks']['children'].append(audio)
        official=otio.adapters.read_from_string(json.dumps(document),'otio_json')
        expanded=otio.algorithms.track_with_expanded_transitions(official.tracks[0])
        self.assertEqual(official.duration().value,24)
        before,transition,after=expanded[1]
        self.assertEqual((before.source_range.start_time.value,after.source_range.start_time.value,transition.duration().value),(18,18,5))
        p=self.import_public(document);pictures,pcm=self.render(p,'dissolve',high=True)
        self.assertEqual(len(pictures),24);self.assertEqual(len(pcm),48000)
        for local in range(5):
            expected=np.array([(118+local)*(1-local/5),0,(118+local)*(local/5)])
            np.testing.assert_allclose(pictures[10+local,16,24,:3],expected,atol=2)
        expected=np.concatenate((self.original_pcm['red'][8*2000:18*2000],
            np.rint(self.original_pcm['red'][18*2000:23*2000]*(1-np.arange(10000)[:,None]/10000)+
                    self.original_pcm['blue'][18*2000:23*2000]*(np.arange(10000)[:,None]/10000)).astype('<i2'),
            self.original_pcm['blue'][23*2000:32*2000]))
        np.testing.assert_allclose(pcm,expected,atol=1)
        again=export_otio(p,self.root)['document']
        official_again=otio.adapters.read_from_string(json.dumps(again),'otio_json')
        self.assertTrue(any(isinstance(item,otio.schema.Transition) for track in official_again.tracks for item in track.find_children(otio.schema.Transition)))
        replay=self.import_public(self.strip(again));b=self.render(replay,'dissolve_again',high=True)
        np.testing.assert_array_equal(pictures,b[0]);np.testing.assert_array_equal(pcm,b[1])
    def test_alpha_dissolve_is_premultiplied_linear_mixing_in_high16_master(self):
        document=self.document([self.clip('red_alpha',0,6),self.transition(2,2),self.clip('blue_alpha',0,6)])
        p=self.import_public(document);pictures,_=self.render(p,'alpha_dissolve',high=True)
        self.assertEqual(len(pictures),12)
        for local in range(4):
            w=local/4;alpha=(1-w)*128+w*64
            expected=[240*(1-w)*128/alpha,0,200*w*64/alpha,alpha]
            np.testing.assert_allclose(pictures[4+local,16,24],expected,atol=1.1)
    def test_ntsc_nested_dissolve_uses_absolute_sample_grid_without_tail_padding(self):
        # At 30000/1001 the transition occupies absolute frames 4..8:
        # 6407 samples, rather than the 6406 samples of a local-zero span.
        # Source phase and fade position are independently computed below.
        document=self.document([self.clip('red',10,6),self.transition(2,2),self.clip('blue',30,8)],kind='Audio')
        def ntsc(value):
            if isinstance(value,dict):
                if value.get('OTIO_SCHEMA')=='RationalTime.1':value['rate']=30000/1001
                for item in value.values():ntsc(item)
            elif isinstance(value,list):
                for item in value:ntsc(item)
        ntsc(document)
        p=import_otio(document,self.project(),self.root,self.mapping())['project']
        self.assertEqual(p['frame_rate'],{'numerator':30000,'denominator':1001})
        _,pcm=self.render(p,'ntsc_absolute_sample_grid')
        weights=np.arange(6407)[:,None]/6406.4
        expected=np.concatenate((self.original_pcm['red'][16016:22422],
            np.rint(self.original_pcm['red'][22422:28829]*(1-weights)+self.original_pcm['blue'][44844:51251]*weights).astype('<i2'),
            self.original_pcm['blue'][51251:60860]))
        self.assertEqual(len(pcm),22422)
        np.testing.assert_allclose(pcm,expected,atol=1)
    def test_trimmed_tracks_root_stack_and_negative_padding_keep_exact_source_clock(self):
        rate=parse_rate(24)
        track=_item('Track.1','Trimmed audio',kind='Audio',children=[self.clip('red',10,24)],source_range=_range(4,16,rate))
        video=_item('Track.1','Trimmed video',kind='Video',children=[self.clip('red',10,24)],source_range=_range(4,16,rate))
        document=self.document([]);document['tracks']['children']=[video,track];document['tracks']['source_range']=_range(3,8,rate)
        p=self.import_public(document);pictures,pcm=self.render(p,'trimmed')
        np.testing.assert_array_equal(self.counters(pictures),np.arange(17,25))
        np.testing.assert_array_equal(pcm,self.original_pcm['red'][17*2000:25*2000])
        document['tracks']['source_range']=_range(-2,20,rate)
        padded=self.import_public(document);images,sound=self.render(padded,'padded')
        self.assertEqual(len(images),20);self.assertEqual(len(sound),40000)
        self.assertLessEqual(int(images[:2,:,:,:3].max()),1);self.assertLessEqual(int(images[18:,:,:,:3].max()),1)
        self.assertFalse(sound[:4000].any());self.assertFalse(sound[36000:].any())
        np.testing.assert_array_equal(sound[4000:36000],self.original_pcm['red'][14*2000:30*2000])
    def test_nested_track_inside_stack_inside_track_preserves_trim_retime_reverse(self):
        rate=parse_rate(24);document=self.document([])
        inner=_item('Track.1','Inner',kind='Video',children=[self.clip('red',8,24)])
        inner['source_range']=_range(2,16,rate)
        inner['effects']=[{'OTIO_SCHEMA':'LinearTimeWarp.1','time_scalar':-.5,'effect_name':'LinearTimeWarp','metadata':{},'name':'Reverse half speed'}]
        stack=_item('Stack.1','Nested',children=[inner],source_range=_range(2,10,rate))
        document['tracks']['children'][0]['children']=[_item('Gap.1',source_range=_range(0,3,rate)),stack]
        p=self.import_public(document);a=self.render(p,'nested_track')
        exported=export_otio(p,self.root)['document'];replay=self.import_public(self.strip(exported));b=self.render(replay,'nested_track_replay')
        self.assertEqual(len(a[0]),13);np.testing.assert_array_equal(a[0],b[0]);np.testing.assert_array_equal(a[1],b[1])
        self.assertGreater(int(a[0][3,16,24,0]),int(a[0][-1,16,24,0]))
    def test_missing_handles_unsupported_operators_invalid_offsets_and_stale_private_data_refuse(self):
        base=self.document([self.clip('red',8,12),self.transition(),self.clip('blue',20,12)])
        variants=[]
        bad=copy.deepcopy(base);bad['tracks']['children'][0]['children'][1]['transition_type']='Wipe';variants.append(bad)
        bad=copy.deepcopy(base);bad['tracks']['children'][0]['children'][2]['source_range']['start_time']['value']=0;variants.append(bad)
        bad=copy.deepcopy(base);bad['tracks']['children'][0]['children'][1]['in_offset']['value']=13;variants.append(bad)
        bad=copy.deepcopy(base);bad['tracks']['children'][0]['children'].insert(1,copy.deepcopy(self.transition()));variants.append(bad)
        bad=copy.deepcopy(base);bad['tracks']['children'][0]['children'][0]['effects']=[{'OTIO_SCHEMA':'FreezeFrame.1','time_scalar':0}];variants.append(bad)
        bad=copy.deepcopy(base);bad['tracks']['children'][0]['children'][0]['effects']=[{'OTIO_SCHEMA':'LinearTimeWarp.1','time_scalar':0}];variants.append(bad)
        bad=copy.deepcopy(base);bad['tracks']['children'][0]['children'][0]['effects']=[{'OTIO_SCHEMA':'TimeEffect.1','effect_name':'VariableSpeed'}];variants.append(bad)
        for index,bad in enumerate(variants):
            with self.subTest(index=index),self.assertRaises(ValueError):self.import_public(bad)
        p=self.import_public(base);exported=export_otio(p,self.root)['document']
        exported['metadata']['cinematicum']['project']['clips'][0]['in']+=1
        with self.assertRaisesRegex(ValueError,'conflicts'):import_otio(exported,p,self.root)
    def test_dissolve_sequence_switch_duplicate_save_schema_and_mutation_fence(self):
        p=self.import_public(self.document([self.clip('red',8,12),self.transition(),self.clip('blue',20,12)]))
        dissolve=next(s for s in p['sequences'] if s.get('otio_dissolve'))
        active=apply_action(p,'sequence_switch',{'sequence_id':dissolve['id']},self.root)['project']
        self.assertEqual(active['otio_dissolve'],dissolve['otio_dissolve'])
        replay=apply_action(active,'sequence_switch',{'sequence_id':p['sequence_id']},self.root)['project']
        self.assertNotIn('otio_dissolve',replay)
        self.assertEqual(validate_project(json.loads(json.dumps(replay)),self.root),replay)
        bad=copy.deepcopy(p);next(s for s in bad['sequences'] if s.get('otio_dissolve'))['clips'][1]['start']=1
        with self.assertRaisesRegex(ValueError,'dissolve|Dissolve'):validate_project(bad,self.root)
