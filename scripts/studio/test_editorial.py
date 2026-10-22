"""Independent decoded acceptance for sequence, multicam and caption editing.

All source pictures/tones here are synthetic ENGINE TEST material.
"""
import array
import copy
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from editorial import (apply_action, export_captions, import_captions,
                       sequence_views, validate_sequence_graph)
from engine import probe_media, render_project, validate_project
from timebase import format_timecode, parse_rate, parse_timecode
from waveform import extract_waveform


class EditorialClockCaptionTests(unittest.TestCase):
    def test_drop_frame_boundaries_and_roundtrip(self):
        for rate, nominal, skipped in ((parse_rate(29.97), 30, 2), (parse_rate(59.94), 60, 4)):
            minute = nominal * 60
            self.assertEqual(format_timecode(minute, rate, drop_frame=True), f'00:01:00;{skipped:02}')
            ten = nominal * 600 - skipped * 9
            self.assertEqual(format_timecode(ten, rate, drop_frame=True), '00:10:00;00')
            hour = nominal * 3600 - skipped * 54
            self.assertEqual(format_timecode(hour, rate, drop_frame=True), '01:00:00;00')
            for frame in range(ten * 2):
                self.assertEqual(parse_timecode(format_timecode(frame, rate, drop_frame=True), rate), frame)
            for frame in range(skipped):
                with self.assertRaisesRegex(ValueError, 'omitted'):
                    parse_timecode(f'00:01:00;{frame:02}', rate)
        with self.assertRaises(ValueError):
            format_timecode(0, 23.976, drop_frame=True)
        self.assertEqual(parse_timecode('00:01:00:00', 29.97), 1800)

    def test_captions_unicode_crlf_absolute_rounding_and_vtt_roundtrip(self):
        rate = parse_rate(29.97)
        text = '\ufeff1\r\n00:00:00,000 --> 00:00:01,001\r\nسلام\r\nSecond line\r\n\r\n2\r\n00:00:01,001 --> 00:00:02,002\r\nNext'
        cues = import_captions(text, rate)
        self.assertEqual([(c['start'], c['duration']) for c in cues], [(0, 30), (30, 30)])
        self.assertEqual(cues[0]['text'], 'سلام\nSecond line')
        document = export_captions(cues, rate, 'vtt')
        replay = import_captions(document, rate, format='vtt')
        self.assertEqual([(c['start'], c['duration'], c['text']) for c in replay], [(c['start'], c['duration'], c['text']) for c in cues])
        for bad in ('1\n00:00:01,000 --> 00:00:00,500\nbad', 'WEBVTT\n\n00:00.000 --> 00:01.000 align:start\nx',
                    '1\n00:00:00,000 --> 00:00:01,000\n<b>styled</b>', 'garbage'):
            with self.assertRaises(ValueError):
                import_captions(bad, rate)

    def test_graph_rejects_dormant_cycle_duplicate_and_depth(self):
        p = {'sequence_id': 'main', 'sequence_name': 'Main', 'clips': [], 'sequences': [
            {'id': 'a', 'name': 'A', 'clips': [{'sequence_id': 'b'}]}, {'id': 'b', 'name': 'B', 'clips': [{'sequence_id': 'a'}]}]}
        with self.assertRaisesRegex(ValueError, 'itself'):
            validate_sequence_graph(p)
        p['sequences'] = [{'id': 'main', 'name': 'Duplicate'}]
        with self.assertRaisesRegex(ValueError, 'unique'):
            sequence_views(p)
        p['sequences'] = [{'id': str(i), 'name': str(i), 'clips': [{'sequence_id': str(i+1)}] if i < 9 else []} for i in range(10)]
        p['clips'] = [{'sequence_id': '0'}]
        with self.assertRaisesRegex(ValueError, 'eight'):
            validate_sequence_graph(p)
    def test_empty_and_title_only_nested_instances_consume_the_expansion_budget(self):
        p={'sequence_id':'main','sequence_name':'Main','clips':[{'sequence_id':'middle'} for _ in range(4)],
           'sequences':[{'id':'middle','name':'Middle','clips':[{'sequence_id':'leaf'} for _ in range(256)]},
                        {'id':'leaf','name':'Empty leaf','clips':[],'titles':[],'sequence_duration':24}]}
        with self.assertRaisesRegex(ValueError,'1,024 expanded'):validate_sequence_graph(p)
        p['clips']=[{'sequence_id':'middle'}]
        p['sequences'][0]['clips']=[{'sequence_id':'leaf'} for _ in range(50)]
        p['sequences'][1]['titles']=[{'id':'title'+str(i),'text':'Text','start':0,'duration':24} for i in range(20)]
        with self.assertRaisesRegex(ValueError,'1,024 expanded'):validate_sequence_graph(p)
        p['sequences'][0]['clips']=p['sequences'][0]['clips'][:4]
        self.assertEqual(len(validate_sequence_graph(p)),3)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class EditorialMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='cinematicum-editorial-ENGINE-TEST-')
        cls.root = Path(cls.temp.name)
        (cls.root/'media').mkdir()
        for name, color, frequency in (('red', 'red', 440), ('blue', 'blue', 880)):
            cls.ffmpeg(['-f','lavfi','-i',f'color=c={color}:s=96x64:r=24:d=2',
                        '-f','lavfi','-i',f'sine=f={frequency}:r=48000:d=2',
                        '-c:v','ffv1','-c:a','pcm_s16le','-shortest',str(cls.root/'media'/f'{name}.mkv')])
        cls.ffmpeg(['-f','rawvideo','-pixel_format','rgb24','-video_size','96x64','-framerate','24','-i','pipe:0',
                    '-c:v','ffv1','-pix_fmt','gbrp',str(cls.root/'media/counter.mkv')],
                   b''.join(bytes([20+i*8,10,5])*96*64 for i in range(24)))
        cls.ffmpeg(['-f','lavfi','-i','color=c=white:s=96x64:r=24:d=1',
                    '-f','lavfi','-i','aevalsrc=0.1|0.2:s=48000:d=1',
                    '-f','lavfi','-i','aevalsrc=0.3|0.4:s=48000:d=1',
                    '-map','0:v','-map','1:a','-map','2:a','-c:v','ffv1','-c:a','pcm_f32le',str(cls.root/'media/multi.mkv')])
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
    @staticmethod
    def ffmpeg(args, payload=None):
        return subprocess.run([shutil.which('ffmpeg'),'-v','error','-nostdin','-y','-threads','1','-filter_complex_threads','1']+args,
                              input=payload,capture_output=True,check=True,timeout=30)
    def project(self):
        return {'version':1,'id':'editorial_test','name':'ENGINE TEST','fps':24,'width':96,'height':64,
                'assets':[{'id':name,'path':f'media/{name}.mkv'} for name in ('red','blue','counter','multi')],
                'clips':[],'titles':[],'tracks':[]}
    def clip(self, asset, ident='clip', **kwargs):
        return {'id':ident,'asset_id':asset,'start':0,'in':0,'duration':24,'track':0,**kwargs}
    def render(self, p, name):
        path=self.root/(name+'.mov');render_project(p,self.root,path,'prores');return path
    def pictures(self,path):
        return self.ffmpeg(['-i',str(path),'-map','0:v:0','-pix_fmt','rgb24','-f','rawvideo','-threads','1','pipe:1']).stdout
    def pcm(self,path):
        return array.array('f',self.ffmpeg(['-i',str(path),'-map','0:a:0','-ac','2','-ar','48000','-f','f32le','pipe:1']).stdout)
    def test_nested_two_instances_preserve_exact_picture_and_sound(self):
        p=self.project();p['clips']=[self.clip('counter',duration=24)]
        baseline=self.pictures(self.render(p,'flat'))
        p.update(sequence_id='main',sequence_name='Main',sequences=[{'id':'source','name':'Source','clips':copy.deepcopy(p['clips']),'titles':[],'tracks':[]}])
        p['clips']=[{'id':'first','sequence_id':'source','start':0,'in':0,'duration':12,'track':0},
                    {'id':'second','sequence_id':'source','start':12,'in':12,'duration':12,'track':0}]
        self.assertEqual(self.pictures(self.render(p,'nested')),baseline)
        # Live edits to a retained child alter the parent without baking.
        p['sequences'][0]['clips'][0]['asset_id']='blue'
        pictures=self.pictures(self.render(p,'nested_changed'))
        self.assertGreater(pictures[2],200)
        self.assertLess(pictures[0],10)
        self.assertNotEqual(pictures,baseline)
    def test_nested_retime_reverse_uses_exact_sequence_clock(self):
        p=self.project();p['clips']=[self.clip('counter',duration=24)]
        raw=self.pictures(self.render(p,'sequence_clock_source'));stride=96*64*3
        source=[raw[i*stride:(i+1)*stride] for i in range(24)]
        for speed in (.25,.5,1,2,4):
            for reverse in (False,True):
                with self.subTest(speed=speed,reverse=reverse):
                    # Nearest project-frame sampling, with ties starting the next
                    # output interval. Derive this oracle from authored indices,
                    # independently of FFmpeg expressions/container timestamps.
                    indices=[min(23,math.ceil((i+.5)*speed)-1) for i in range(int(24/speed))]
                    if reverse:indices.reverse()
                    expected=b''.join(source[i] for i in indices)
                    p.update(sequence_id='main',sequence_name='Main',sequences=[{'id':'source','name':'Source',
                        'clips':[self.clip('counter',duration=24)],'titles':[],'tracks':[]}])
                    p['clips']=[{'id':'nested','sequence_id':'source','start':0,'in':0,'duration':int(24/speed),'track':0,'speed':speed,'reverse':reverse}]
                    self.assertEqual(self.pictures(self.render(p,f'nest_{speed}_{reverse}')),expected)

    def test_nested_transparency_group_opacity_gain_and_gap(self):
        p=self.project();p.update(sequence_id='main',sequence_name='Main')
        child={'id':'group','name':'Group','clips':[self.clip('red',start=6,duration=12)],'titles':[],
               'tracks':[{'id':0,'gain':.5}]}
        p['sequences']=[child]
        p['clips']=[self.clip('blue','under',duration=24,volume=0),
                    {'id':'over','sequence_id':'group','start':0,'in':0,'duration':18,'track':1,'opacity':.5,'volume':.5}]
        out=self.render(p,'group');raw=self.pictures(out);stride=96*64*3
        self.assertLess(raw[0],5);self.assertGreater(raw[2],240)
        inside=raw[8*stride:8*stride+3]
        self.assertTrue(115<=inside[0]<=140,inside)
        self.assertTrue(115<=inside[2]<=140,inside)
        pcm=self.pcm(out)
        self.assertEqual(len(pcm),96000)
        self.assertLess(max(abs(v) for v in pcm[:6*2000*2]),.0001)
        amplitude=max(abs(v) for v in pcm[8*2000*2:10*2000*2])
        self.assertAlmostEqual(amplitude, .125 / (2 ** .5) * .25, delta=.0002)
    def test_switch_duplicate_nest_and_inactive_source_validation(self):
        p=self.project();p['clips']=[self.clip('red')]
        new=apply_action(p,'sequence_create',{'name':'Assembly'},self.root)['project']
        self.assertEqual(new['clips'],[]);self.assertEqual(new['sequences'][0]['clips'][0]['asset_id'],'red')
        nested=apply_action(new,'sequence_nest',{'sequence_id':'main','start':0,'track':0},self.root)['project']
        self.assertEqual(nested['clips'][0]['sequence_id'],'main')
        with self.assertRaisesRegex(ValueError,'itself'):
            apply_action(nested,'sequence_nest',{'sequence_id':nested['sequence_id'],'start':0,'track':0},self.root)
        back=apply_action(nested,'sequence_switch',{'sequence_id':'main'},self.root)['project']
        self.assertEqual(back['clips'][0]['asset_id'],'red')
        broken=copy.deepcopy(back);broken['sequences'][0]['clips'][0]['sequence_id']='missing'
        with self.assertRaisesRegex(ValueError,'missing sequence'):
            validate_project(broken,self.root)
    def test_multicam_sync_and_frame_exact_cut(self):
        p=apply_action(self.project(),'multicam_create',{'angles':[{'asset_id':'red','in':4},{'asset_id':'blue','in':8}], 'name':'Two cameras'},self.root)['project']
        clip=p['clips'][0];group=p['multicam_groups'][0]
        p=apply_action(p,'multicam_cut',{'clip_id':clip['id'],'angle_id':group['angles'][1]['id'],'frame':6},self.root)['project']
        self.assertEqual([(c['asset_id'],c['start'],c['in'],c['duration']) for c in p['clips']],[('red',0,4,6),('blue',6,14,34)])
        raw=self.pictures(self.render(p,'multicam'));stride=96*64*3
        self.assertGreater(raw[5*stride],240);self.assertGreater(raw[6*stride+2],240)
        self.assertEqual(len(raw),40*stride)
    def test_audio_stream_channel_selection_changes_actual_pcm(self):
        p=self.project();p['clips']=[self.clip('multi',duration=12)]
        p=apply_action(p,'audio_map',{'clip_id':'clip','stream_index':2,'channels':[1,0]},self.root)['project']
        out=self.render(p,'mapped');pcm=self.pcm(out)
        left=sum(pcm[2000:20000:2])/9000;right=sum(pcm[2001:20001:2])/9000
        self.assertAlmostEqual(left,.4,places=3);self.assertAlmostEqual(right,.3,places=3)
        for values in ({'stream_index':9,'channels':[0,1]},{'stream_index':2,'channels':[2,0]}):
            with self.assertRaises(ValueError):
                apply_action(p,'audio_map',{'clip_id':'clip',**values},self.root)
    def test_waveform_selects_the_same_source_stream_channels_and_cache_identity(self):
        source=self.root/'media/multi.mkv';cache=self.root/'mapped_waveform_cache'
        first=extract_waveform(source,cache,bins=32)
        swapped=extract_waveform(source,cache,bins=32,stream_index=2,channels=[1,0])
        self.assertEqual((first['source_stream_index'],first['source_channels']),(1,None))
        self.assertEqual((swapped['source_stream_index'],swapped['source_channels']),(2,[1,0]))
        for measured,levels in ((first,(.1,.2)),(swapped,(.4,.3))):
            for channel,expected in zip(measured['peaks'],levels):
                for statistic in ('min','max','rms'):
                    for value in channel[statistic]:self.assertAlmostEqual(value,expected,places=6)
        cached=extract_waveform(source,cache,bins=32,stream_index=2,channels=[1,0])
        self.assertTrue(cached['cached']);self.assertEqual(cached['peaks'],swapped['peaks'])
        duplicate=extract_waveform(source,cache,bins=32,stream_index=2,channels=[1,1])
        self.assertFalse(duplicate['cached']);self.assertEqual(duplicate['peaks'][0],duplicate['peaks'][1])
        for values in ({'stream_index':0},{'stream_index':True},{'stream_index':99},
                       {'stream_index':2,'channels':[2,0]},{'channels':[0]}, {'channels':[True,1]}):
            with self.subTest(values=values),self.assertRaises(ValueError):extract_waveform(source,cache,**values)
    def test_multicam_angle_change_rebinds_source_specific_audio_mapping(self):
        p=apply_action(self.project(),'multicam_create',{'angles':[{'asset_id':'multi','in':0},{'asset_id':'red','in':0}]},self.root)['project']
        clip=p['clips'][0];group=p['multicam_groups'][0]
        p=apply_action(p,'audio_map',{'clip_id':clip['id'],'stream_index':2,'channels':[1,0]},self.root)['project']
        p=apply_action(p,'multicam_cut',{'clip_id':clip['id'],'angle_id':group['angles'][1]['id'],'frame':6},self.root)['project']
        self.assertEqual(p['clips'][0]['audio']['stream_index'],2)
        self.assertNotIn('stream_index',p['clips'][1]['audio']);self.assertNotIn('channels',p['clips'][1]['audio'])
        pcm=self.pcm(self.render(p,'multicam_mapped_audio'))
        self.assertAlmostEqual(sum(pcm[2000:10000:2])/4000,.4,places=3)
        # The chosen camera now contains a sine, not the previous camera's DC.
        self.assertLess(abs(sum(pcm[30000:50000:2])/10000),.002)
    def nested_project(self):
        p=self.project()
        p.update(sequence_id='main',sequence_name='Main',sequences=[
            {'id':'child','name':'Child','clips':[self.clip('red','red',duration=8),self.clip('blue','blue',start=8,duration=8)],'titles':[],'tracks':[]},
            {'id':'unused','name':'Unused','clips':[self.clip('counter','counter',duration=24)],'titles':[],'tracks':[],
             'captions':[{'id':'cue','start':0,'duration':12,'text':'Dormant caption'}]}])
        p['clips']=[{'id':'nested','sequence_id':'child','start':0,'in':2,'duration':12,'track':0}]
        return p

    def test_nested_otio_byte_identity_relink_and_private_timing_rejection(self):
        from interchange import export_otio,import_otio
        p=self.nested_project()
        document=export_otio(p,self.root)['document']
        self.assertEqual(document['tracks']['children'][0]['children'][0]['OTIO_SCHEMA'],'Stack.1')
        destination=self.project()
        for asset in destination['assets']:asset['id']='new_'+asset['id']
        replay=import_otio(document,destination,self.root)['project']
        self.assertEqual(replay['sequences'][1]['clips'][0]['asset_id'],'new_counter')
        self.assertEqual(replay['sequences'][1]['captions'][0]['text'],'Dormant caption')
        self.assertEqual(self.pictures(self.render(replay,'otio_nested')),self.pictures(self.render(p,'otio_original')))
        broken=copy.deepcopy(document);broken['metadata']['cinematicum']['project']['clips'][0]['in']=1
        with self.assertRaisesRegex(ValueError,'conflicts'):
            import_otio(broken,destination,self.root)
        broken=copy.deepcopy(document);broken['metadata']['cinematicum']['asset_sha256'].pop('counter')
        with self.assertRaisesRegex(ValueError,'identity'):
            import_otio(broken,destination,self.root)

    def test_public_nested_otio_import_preserves_picture_and_sound(self):
        from interchange import export_otio,import_otio
        p=self.nested_project();document=export_otio(p,self.root)['document']
        document['metadata']={}
        replay=import_otio(document,self.project(),self.root)['project']
        self.assertGreaterEqual(len(replay['sequences']),2)
        original=self.render(p,'public_original');rebuilt=self.render(replay,'public_replay')
        self.assertEqual(self.pictures(original),self.pictures(rebuilt))
        self.assertEqual(self.pcm(original),self.pcm(rebuilt))

    def test_nested_archive_and_recovery_retain_all_sequence_dependencies(self):
        from project_archive import export_archive,import_archive
        import recovery
        p=validate_project(self.nested_project(),self.root)
        p['revision']=1
        for asset in p['assets']:asset['sha256']=hashlib.sha256((self.root/asset['path']).read_bytes()).hexdigest()
        archive=self.root/'nested.cinematicum.zip'
        export_archive(p,self.root,archive)
        (self.root/'restored').mkdir(exist_ok=True)
        restored=import_archive(archive,self.root/'restored')
        output=self.root/'restored.mov'
        render_project(restored,self.root/'restored'/restored['id'],output,'prores')
        original=self.render(p,'archive_source')
        self.assertEqual(self.pictures(output),self.pictures(original))
        self.assertEqual(self.pcm(output),self.pcm(original))
        def atomic(path,value):Path(path).write_text(json.dumps(value))
        editor='a'*32
        recovery.put(self.root,editor,1,p,atomic)
        current=copy.deepcopy(p);current['revision']=2;current['sequences']=[];current['clips']=[]
        candidate,_=recovery.candidate(self.root,current,'draft',editor,1)
        self.assertEqual(candidate['sequences'],p['sequences'])
        self.assertEqual(candidate['revision'],2)
        validate_project(candidate,self.root)

    def test_caption_sidecar_preserves_project_and_optional_burn_in(self):
        p=self.project();original=copy.deepcopy(p)
        p=apply_action(p,'captions_import',{'text':'1\n00:00:00,000 --> 00:00:00,500\nCaption', 'burn_in':True},self.root)['project']
        self.assertEqual(original['titles'],[])
        self.assertEqual(p['titles'][0]['caption_id'],p['captions'][0]['id'])
        self.assertEqual(p['titles'][0]['duration'],12)
        export=apply_action(p,'captions_export',{'format':'srt'},self.root)
        self.assertIn('00:00:00,500',export['text'])
        p=apply_action(p,'captions_replace',{'captions':p['captions'],'burn_in':False},self.root)['project']
        self.assertEqual(p['titles'],[])
        self.assertEqual(len(p['captions']),1)
    def test_caption_style_and_plate_consistency_are_validated_before_save(self):
        p=apply_action(self.project(),'captions_import',{'text':'1\n00:00:00,000 --> 00:00:00,500\nCaption','burn_in':True},self.root)['project']
        for style in (None, [], {'size':0}, {'y':float('nan')}, {'color':'red'}, {'burn_in':'yes'}, {'unknown':1}):
            candidate=copy.deepcopy(p);candidate['caption_style']=style
            with self.subTest(style=style),self.assertRaises(ValueError):validate_project(candidate,self.root)
        for mutation in ('orphan','missing','duplicate','changed'):
            candidate=copy.deepcopy(p)
            if mutation=='orphan':candidate.pop('captions')
            elif mutation=='missing':candidate['titles']=[]
            elif mutation=='duplicate':candidate['titles'].append({**candidate['titles'][0],'id':'duplicate_plate'})
            else:candidate['titles'][0]['text']='Different'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):validate_project(candidate,self.root)


if __name__=='__main__':unittest.main()
