"""Independent rational FCPXML fixtures and actual source-frame/PCM oracles."""
import copy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave
import xml.etree.ElementTree as ET

import numpy as np

from engine import probe_media, render_project, validate_project
from editorial import sequence_views
from fcpxml import Document, export_fcpxml, import_fcpxml, inspect_fcpxml, time_value, time_string
from timebase import parse_rate

RATE = parse_rate({'numerator':30000,'denominator':1001})
WIDTH,HEIGHT,FRAMES = 48,32,96
ORIGIN,RED_ORIGIN,BLUE_ORIGIN,COMPOUND_ORIGIN = 108000,180000,240000,72000
MAPPING = {'red_source':'red','blue_source':'blue'}


def stamp(frame):
    value = Fraction(frame,1)/RATE.fraction
    return str(value.numerator)+(('/'+str(value.denominator)) if value.denominator != 1 else '')+'s'


def ffmpeg(arguments,data=None,timeout=40):
    executable = shutil.which('ffmpeg')
    if not executable:
        raise RuntimeError('Actual FFmpeg is required; FCPXML media acceptance cannot skip.')
    return subprocess.run([executable,'-v','error','-nostdin','-y','-filter_complex_threads','1','-threads','1']+arguments,
                          input=data,capture_output=True,check=True,timeout=timeout).stdout


def fixture_xml():
    """Hand-authored public document, never generated through the exporter."""
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.10"><resources>
  <format id="fmt" frameDuration="1001/30000s" width="48" height="32" fieldOrder="progressive" colorSpace="1-1-1 (Rec. 709)"/>
  <asset id="red_source" name="ENGINE TEST red" start="{stamp(RED_ORIGIN)}" duration="{stamp(FRAMES)}" hasVideo="1" hasAudio="1" format="fmt" videoSources="1" audioSources="1" audioChannels="2" audioRate="48000"><media-rep kind="original-media" src="file:///UNOPENED/ENGINE_TEST_red.mov"/></asset>
  <asset id="blue_source" name="ENGINE TEST blue" start="{stamp(BLUE_ORIGIN)}" duration="{stamp(FRAMES)}" hasVideo="1" hasAudio="1" format="fmt" videoSources="1" audioSources="1" audioChannels="2" audioRate="48000"><media-rep kind="original-media" src="https://example.invalid/NEVER_FETCH/ENGINE_TEST_blue.mov"/></asset>
  <media id="compound" name="ENGINE TEST compound"><sequence format="fmt" duration="{stamp(32)}" tcStart="{stamp(COMPOUND_ORIGIN)}" tcFormat="NDF" audioLayout="stereo" audioRate="48k"><spine>
    <asset-clip ref="red_source" name="compound picture" offset="{stamp(COMPOUND_ORIGIN)}" start="{stamp(RED_ORIGIN+32)}" duration="{stamp(32)}" srcEnable="video">
      <video lane="1" ref="blue_source" name="compound connected picture" offset="{stamp(RED_ORIGIN+42)}" start="{stamp(BLUE_ORIGIN+40)}" duration="{stamp(8)}"/>
      <audio lane="-1" ref="red_source" name="compound independent audio" offset="{stamp(RED_ORIGIN+32)}" start="{stamp(RED_ORIGIN+32)}" duration="{stamp(32)}"/>
    </asset-clip>
  </spine></sequence></media>
</resources><project name="ENGINE TEST rational FCPXML"><sequence format="fmt" duration="{stamp(40)}" tcStart="{stamp(ORIGIN)}" tcFormat="NDF" audioLayout="stereo" audioRate="48k"><spine>
  <asset-clip ref="red_source" name="primary picture" offset="{stamp(ORIGIN)}" start="{stamp(RED_ORIGIN+8)}" duration="{stamp(16)}" srcEnable="video">
    <video lane="1" ref="blue_source" name="connected picture" offset="{stamp(RED_ORIGIN+12)}" start="{stamp(BLUE_ORIGIN+20)}" duration="{stamp(6)}"/>
    <audio lane="-1" ref="red_source" name="independent source audio" offset="{stamp(RED_ORIGIN+8)}" start="{stamp(RED_ORIGIN+8)}" duration="{stamp(16)}"><adjust-volume amount="-6.020599913279624dB"/></audio>
  </asset-clip>
  <ref-clip ref="compound" name="trimmed real compound" offset="{stamp(ORIGIN+16)}" start="{stamp(COMPOUND_ORIGIN+4)}" duration="{stamp(16)}" srcEnable="all"><adjust-volume amount="-12.041199826559248dB"/></ref-clip>
  <asset-clip ref="red_source" name="constant forward retime" offset="{stamp(ORIGIN+32)}" start="{stamp(RED_ORIGIN+56)}" duration="{stamp(8)}" srcEnable="video">
    <conform-rate scaleEnabled="0" frameSampling="nearest-neighbor"/>
    <timeMap frameSampling="nearest-neighbor" preservesPitch="1"><timept time="{stamp(RED_ORIGIN+56)}" value="{stamp(RED_ORIGIN+56)}" interp="linear"/><timept time="{stamp(RED_ORIGIN+64)}" value="{stamp(RED_ORIGIN+72)}" interp="linear"/></timeMap>
  </asset-clip>
</spine></sequence></project></fcpxml>'''


def source_pcm(ident):
    count = RATE.samples_for_frames(FRAMES)
    n = np.arange(count,dtype=np.int64)
    return (np.stack((((n*37+(1 if ident=='red' else 997))%3001)-1500,
                     ((n*59+(777 if ident=='red' else 13))%2503)-1251),axis=1)*4).astype('<i2')


def create_fixture(directory):
    directory = Path(directory);(directory/'media').mkdir(parents=True,exist_ok=True)
    assets = []
    for ident,channel in (('red',0),('blue',2)):
        pixels = np.zeros((FRAMES,HEIGHT,WIDTH,3),dtype=np.uint8)
        pixels[:,:,:,channel] = np.arange(FRAMES,dtype=np.uint8)[:,None,None]+80
        for bit in range(7):
            pixels[:,24:32,bit*6:(bit+1)*6,:] = np.where((np.arange(FRAMES)>>bit)&1,240,8)[:,None,None,None]
        wav = directory/(ident+'.wav')
        with wave.open(str(wav),'wb') as output:
            output.setnchannels(2);output.setsampwidth(2);output.setframerate(48000);output.writeframes(source_pcm(ident).tobytes())
        destination = directory/'media'/(ident+'.mov')
        ffmpeg(['-f','rawvideo','-pixel_format','rgb24','-video_size',f'{WIDTH}x{HEIGHT}','-framerate',RATE.ffmpeg,'-i','pipe:0',
                '-i',str(wav),'-c:v','qtrle','-pix_fmt','rgb24','-c:a','pcm_s16le','-shortest',str(destination)],pixels.tobytes())
        assets.append({'id':ident,'path':'media/'+destination.name,'name':'ENGINE TEST '+ident,'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),**probe_media(destination)})
    project = {'version':1,'id':'fcpxml_test','name':'ENGINE TEST FCPXML source','width':WIDTH,'height':HEIGHT,
               'fps':RATE.fps,'frame_rate':RATE.as_dict(),'assets':assets,'clips':[],'titles':[],'tracks':[],'settings':{}}
    return validate_project(project,directory)


def decode_movie(path):
    pictures = np.frombuffer(ffmpeg(['-i',str(path),'-map','0:v:0','-pix_fmt','rgb24','-threads','1','-f','rawvideo','pipe:1']),dtype=np.uint8).reshape(-1,HEIGHT,WIDTH,3)
    pcm = np.frombuffer(ffmpeg(['-i',str(path),'-map','0:a:0','-f','s16le','pipe:1']),dtype='<i2').reshape(-1,2)
    return pictures,pcm


def picture_counters(pictures):
    return sum(((pictures[:,28,bit*6+3,:3].mean(axis=1)>120).astype(int)<<bit) for bit in range(7))


def fixture_expectations():
    # Independently enumerate source frame numbers and source channel identities.
    frames = np.concatenate((np.arange(8,24),np.arange(36,52),np.arange(56,72,2)))
    channels = np.zeros(40,dtype=int)
    frames[4:10] = np.arange(20,26);channels[4:10] = 2
    frames[22:30] = np.arange(40,48);channels[22:30] = 2
    pcm = np.zeros((RATE.samples_for_frames(40),2),dtype='<i2')
    source = source_pcm('red')
    first = RATE.sample_span(0,16)
    pcm[:first] = source[RATE.samples_for_frames(8):RATE.samples_for_frames(8)+first]//2
    begin,end = RATE.samples_for_frames(16),RATE.samples_for_frames(32)
    pcm[begin:end] = source[RATE.samples_for_frames(36):RATE.samples_for_frames(36)+end-begin]//4
    return frames,channels,pcm


class FCPXMLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='cinematicum-FCPXML-ENGINE-TEST-')
        cls.root = Path(cls.temp.name)
        cls.base = create_fixture(cls.root)
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
    def imported(self,document=None):
        return import_fcpxml(document or fixture_xml(),self.base,self.root,MAPPING)['project']
    def test_exact_time_wire_and_no_rounding(self):
        self.assertEqual(time_value('1001/30000s'),Fraction(1001,30000))
        self.assertEqual(time_string(time_value('2002/60000s')),'1001/30000s')
        for bad in ('0.5s','NaNs','1/0s','1/4294967296s','9223372036854775808s','1s trailing'):
            with self.subTest(bad=bad),self.assertRaises(ValueError):time_value(bad)
        with self.assertRaisesRegex(ValueError,'whole project frames'):
            self.imported(fixture_xml().replace('duration="'+stamp(16)+'"','duration="1s"',1))
    def test_inspection_is_opaque_and_explicit_relink_required(self):
        result = inspect_fcpxml(fixture_xml())
        self.assertEqual({r['target'] for r in result['references']},set(MAPPING))
        self.assertTrue(any('magnetic' in message for message in result['warnings']))
        with self.assertRaisesRegex(ValueError,'relink'):
            import_fcpxml(fixture_xml(),self.base,self.root)
        with self.assertRaisesRegex(ValueError,'media mapping'):
            import_fcpxml(fixture_xml(),self.base,self.root,{'red_source':'../outside'})
    def test_independent_import_timing_compound_and_source_identity(self):
        original = copy.deepcopy(self.base)
        p = self.imported();self.assertEqual(self.base,original)
        self.assertEqual(p['frame_rate'],{'numerator':30000,'denominator':1001})
        self.assertEqual(p['sequence_duration'],40)
        self.assertEqual(len(p['clips']),5)
        primary = next(c for c in p['clips'] if c.get('asset_id')=='red' and c['track']>=0 and c['start']==0)
        self.assertEqual((primary['in'],primary['duration'],primary['volume']),(8,16,0))
        nested = next(c for c in p['clips'] if c.get('sequence_id'))
        self.assertEqual((nested['start'],nested['in'],nested['duration']),(16,4,16))
        child = sequence_views(p)[nested['sequence_id']]
        self.assertEqual(len(child['clips']),3)
        self.assertEqual(next(c for c in child['clips'] if c.get('asset_id')=='blue')['start'],10)
        self.assertEqual(p['settings']['fcpxml']['sequence_origins'][p['sequence_id']]['tcStart'],stamp(ORIGIN))
        self.assertEqual(primary['fcpxml']['source_sha256'],hashlib.sha256((self.root/'media/red.mov').read_bytes()).hexdigest())
        self.assertEqual(len(p['sequences']),2) # prior empty active sequence + actual compound
    def test_actual_ntsc_frames_nested_trim_forward_map_and_every_pcm_sample(self):
        p = self.imported();out = self.root/'independent.mov'
        render_project(p,self.root,out,'prores')
        pictures,pcm = decode_movie(out);frames,channels,expected_pcm = fixture_expectations()
        np.testing.assert_array_equal(picture_counters(pictures),frames)
        np.testing.assert_array_equal(pictures[:,8,20,:].argmax(axis=1),channels)
        np.testing.assert_array_equal(pcm,expected_pcm)
    def test_public_roundtrip_exact_media_and_real_nested_structure(self):
        p = self.imported();result=export_fcpxml(p,self.root)
        root = ET.fromstring(result['document'])
        self.assertEqual(len(root.findall('resources/media')),1)
        self.assertTrue(root.findall('.//ref-clip'))
        q = import_fcpxml(result['document'],self.base,self.root)['project']
        self.assertEqual(q['frame_rate'],p['frame_rate'])
        self.assertEqual(q['sequence_duration'],40)
        a,b = self.root/'roundtrip_a.mov',self.root/'roundtrip_b.mov'
        render_project(p,self.root,a,'prores');render_project(q,self.root,b,'prores')
        aa,bb=decode_movie(a),decode_movie(b)
        np.testing.assert_array_equal(aa[0],bb[0]);np.testing.assert_array_equal(aa[1],bb[1])
    def test_xml_entities_external_dtd_processing_and_path_traversal_rejected(self):
        cases = [fixture_xml().replace('<!DOCTYPE fcpxml>','<!DOCTYPE fcpxml SYSTEM "https://example.invalid/DTD">'),
                 fixture_xml().replace('<!DOCTYPE fcpxml>','<!DOCTYPE fcpxml [<!ENTITY leak SYSTEM "file:///etc/passwd">]>'),
                 fixture_xml().replace('<resources>','<?evil x?><resources>'),
                 fixture_xml().replace('https://example.invalid/NEVER_FETCH/','file:///safe/%2e%2e/')]
        for doc in cases:
            with self.subTest(document=doc[:80]),self.assertRaises(ValueError):inspect_fcpxml(doc)
    def test_unsupported_negative_smooth_sampling_mismatch_and_effects_rejected(self):
        cases = [fixture_xml().replace('value="'+stamp(RED_ORIGIN+72)+'"','value="'+stamp(RED_ORIGIN+40)+'"'),
                 fixture_xml().replace('interp="linear"','interp="smooth2"'),
                 fixture_xml().replace('<conform-rate scaleEnabled="0" frameSampling="nearest-neighbor"/>','<conform-rate scaleEnabled="0" frameSampling="floor"/>'),
                 fixture_xml().replace('<adjust-volume amount="-6.020599913279624dB"/>','<adjust-volume amount="-6.020599913279624dB"><param name="x" value="1"/></adjust-volume>'),
                 fixture_xml().replace('</spine></sequence></project>','<transition duration="'+stamp(1)+'"/></spine></sequence></project>')]
        for doc in cases:
            with self.subTest(document=doc[-200:]),self.assertRaises(ValueError):self.imported(doc)
    def test_export_rejects_untranslated_live_edits(self):
        for change in ({'reverse':True},{'grade':{'exposure':1}},{'audio':{'pan':.5}},{'keyframes':[{'frame':0,'scale':1.2}]}):
            p=self.imported();p['clips'][0].update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):export_fcpxml(p,self.root)
    def test_original_sequences_and_unsaved_project_are_preserved(self):
        base=copy.deepcopy(self.base)
        base['clips']=[{'id':'prior','asset_id':'red','track':0,'start':0,'duration':4,'in':2}]
        before=validate_project(base,self.root)
        imported=import_fcpxml(fixture_xml(),before,self.root,MAPPING)['project']
        prior=next(s for s in imported['sequences'] if s['id']=='main')
        self.assertEqual(prior['clips'],before['clips'])
        self.assertEqual(before,validate_project(base,self.root))

    def test_actual_reordered_h264_frames_use_decoded_presentation_clock(self):
        target=self.root/'media/red_bframes.mov'
        ffmpeg(['-i',str(self.root/'media/red.mov'),'-c:v','libx264','-preset','medium','-crf','10','-bf','3','-g','48',
                '-pix_fmt','yuv420p','-video_track_timescale','30000','-c:a','copy',str(target)])
        facts=json.loads(subprocess.run([shutil.which('ffprobe'),'-v','error','-select_streams','v:0','-show_entries','frame=pict_type,pts,best_effort_timestamp','-of','json',str(target)],capture_output=True,check=True,timeout=10).stdout)
        self.assertTrue(any(frame['pict_type']=='B' for frame in facts['frames']))
        base=copy.deepcopy(self.base);base['assets'][0]={'id':'red','path':'media/red_bframes.mov'}
        imported=import_fcpxml(fixture_xml(),base,self.root,MAPPING)['project']
        out=self.root/'reordered.mov';render_project(imported,self.root,out,'prores')
        pictures,pcm=decode_movie(out);frames,channels,expected=fixture_expectations()
        np.testing.assert_array_equal(picture_counters(pictures),frames)
        np.testing.assert_array_equal(pictures[:,8,20,:].argmax(axis=1),channels)
        np.testing.assert_array_equal(pcm,expected)
    def test_actual_quantized_source_clock_is_refused_for_double_speed(self):
        target=self.root/'media/red_quantized.mkv'
        ffmpeg(['-i',str(self.root/'media/red.mov'),'-c:v','ffv1','-pix_fmt','gbrp','-c:a','copy',str(target)])
        base=copy.deepcopy(self.base);base['assets'][0]={'id':'red','path':'media/red_quantized.mkv'}
        with self.assertRaisesRegex(ValueError,'source clock is not proven exact'):
            import_fcpxml(fixture_xml(),base,self.root,MAPPING)
    def test_floor_repeat_grids_have_independent_exact_frame_and_pcm_oracles(self):
        for speed,repetitions in ((Fraction(1,2),2),(Fraction(1,4),4)):
            with self.subTest(speed=speed):
                root=ET.fromstring(fixture_xml());last=root.find('project/sequence/spine')[-1]
                last.find('conform-rate').set('frameSampling','floor')
                mapping=last.find('timeMap');mapping.set('frameSampling','floor')
                mapping[-1].set('value',stamp(RED_ORIGIN+56+8*speed))
                imported=self.imported(ET.tostring(root,encoding='unicode'))
                out=self.root/('repeat_'+str(repetitions)+'.mov');render_project(imported,self.root,out,'prores')
                pictures,pcm=decode_movie(out);frames,channels,expected=fixture_expectations()
                frames[-8:]=np.repeat(np.arange(56,56+8//repetitions),repetitions)
                np.testing.assert_array_equal(picture_counters(pictures),frames)
                np.testing.assert_array_equal(pcm,expected)
                exported=export_fcpxml(imported,self.root)['document']
                self.assertIn('frameSampling="floor"',exported)
                restored=import_fcpxml(exported,self.base,self.root)['project']
                self.assertEqual(next(c for c in restored['clips'] if c['start']==32)['speed'],float(speed))
    def test_partial_repeat_tail_and_unproven_positive_maps_are_refused(self):
        for speed,duration in ((Fraction(1,4),10),(Fraction(3,5),10),(Fraction(3),8),(Fraction(4),8)):
            with self.subTest(speed=speed,duration=duration):
                root=ET.fromstring(fixture_xml());sequence=root.find('project/sequence');sequence.set('duration',stamp(32+duration))
                last=sequence.find('spine')[-1];last.set('duration',stamp(duration))
                sampling='floor' if speed<1 else 'nearest-neighbor'
                last.find('conform-rate').set('frameSampling',sampling)
                mapping=last.find('timeMap');mapping.set('frameSampling',sampling)
                mapping[-1].set('time',stamp(RED_ORIGIN+56+duration));mapping[-1].set('value',stamp(RED_ORIGIN+56+duration*speed))
                with self.assertRaises(ValueError):self.imported(ET.tostring(root,encoding='unicode'))
    def test_static_apple_position_scale_opacity_and_level_are_public(self):
        root=ET.fromstring(fixture_xml());sequence=root.find('project/sequence');sequence.set('duration',stamp(4))
        spine=sequence.find('spine');spine.clear()
        clip=ET.SubElement(spine,'asset-clip',ref='red_source',offset=stamp(ORIGIN),start=stamp(RED_ORIGIN+8),duration=stamp(4),srcEnable='all')
        ET.SubElement(clip,'adjust-transform',position='25 -25',scale='0.5 0.5',rotation='0',anchor='0 0')
        ET.SubElement(clip,'adjust-blend',amount='0.5',mode='normal')
        ET.SubElement(clip,'adjust-volume',amount='-6.020599913279624dB')
        p=import_fcpxml(ET.tostring(root,encoding='unicode'),self.base,self.root,{'red_source':'red'})['project']
        c=p['clips'][0];self.assertEqual((c['x'],c['y'],c['scale'],c['opacity'],c['volume']),(1/6,.25,.5,.5,.5))
        out=self.root/'transform.mov';render_project(p,self.root,out,'prores');pictures,pcm=decode_movie(out)
        self.assertLessEqual(abs(int(pictures[0,20,24,0])-44),4)
        self.assertLessEqual(int(pictures[:,4,4,:].max()),3)
        self.assertLessEqual(int(pictures[:,15,24,:].max()),3)
        expected=source_pcm('red')[RATE.samples_for_frames(8):RATE.samples_for_frames(8)+RATE.samples_for_frames(4)]//2
        np.testing.assert_array_equal(pcm,expected)
        wire=export_fcpxml(p,self.root)['document'];self.assertIn('adjust-transform',wire);self.assertIn('adjust-volume',wire)
        q=import_fcpxml(wire,self.base,self.root)['project']
        out2=self.root/'transform_roundtrip.mov';render_project(q,self.root,out2,'prores');other=decode_movie(out2)
        np.testing.assert_array_equal(pictures,other[0]);np.testing.assert_array_equal(pcm,other[1])
    def test_apple_positive_rotation_is_counterclockwise_in_actual_pixels(self):
        pixels=np.zeros((HEIGHT,WIDTH,3),dtype=np.uint8)
        pixels[:16,:24]=[240,0,0];pixels[:16,24:]=[0,240,0];pixels[16:,:24]=[0,0,240];pixels[16:,24:]=[240,240,240]
        path=self.root/'media/quadrants.png';ffmpeg(['-f','rawvideo','-pixel_format','rgb24','-video_size','48x32','-i','pipe:0','-frames:v','1','-threads','1',str(path)],pixels.tobytes())
        base=copy.deepcopy(self.base);base['assets'][0]={'id':'red','path':'media/quadrants.png'}
        root=ET.fromstring(fixture_xml());root.find("resources/asset[@id='red_source']").set('hasAudio','0')
        sequence=root.find('project/sequence');sequence.set('duration',stamp(4));spine=sequence.find('spine');spine.clear()
        clip=ET.SubElement(spine,'asset-clip',ref='red_source',offset=stamp(ORIGIN),start=stamp(RED_ORIGIN),duration=stamp(4),srcEnable='video')
        ET.SubElement(clip,'adjust-transform',rotation='90')
        p=import_fcpxml(ET.tostring(root,encoding='unicode'),base,self.root,{'red_source':'red'})['project']
        self.assertEqual(p['clips'][0]['rotation'],-90)
        out=self.root/'rotation.mov';render_project(p,self.root,out,'prores');pictures,_=decode_movie(out)
        for y,x,expected in ((11,19,(0,240,0)),(11,29,(240,240,240)),(21,19,(240,0,0)),(21,29,(0,0,240))):
            np.testing.assert_allclose(pictures[0,y,x],expected,atol=8,rtol=0)
    def test_notes_unknown_attributes_bounds_and_compound_cycles_are_rejected(self):
        cases=[fixture_xml().replace('<spine>','<spine mystery="1">',1),
               fixture_xml().replace('<spine>','<note><filter-video ref="effect"/></note><spine>',1),
               fixture_xml().replace('name="compound picture"','name="compound picture" bad="1"'),
               fixture_xml().replace('<spine>','<spine><ref-clip ref="compound" duration="'+stamp(1)+'"/>',1),
               '<fcpxml version="1.10">'+'<x>'*41+'</x>'*41+'</fcpxml>']
        for doc in cases:
            with self.subTest(document=doc[:100]),self.assertRaises(ValueError):self.imported(doc)
    def test_exported_hash_autolink_refuses_ambiguous_identical_assets(self):
        wire=export_fcpxml(self.imported(),self.root)['document'];base=copy.deepcopy(self.base)
        base['assets'].append({'id':'duplicate','path':'media/red.mov'})
        with self.assertRaisesRegex(ValueError,'unique imported match'):
            import_fcpxml(wire,base,self.root)

    def test_repeated_import_preserves_prior_sequence_timecode_provenance(self):
        first=self.imported()
        prior_origins=copy.deepcopy(first['settings']['fcpxml']['sequence_origins'])
        second=import_fcpxml(fixture_xml(),first,self.root,MAPPING)['project']
        self.assertEqual(len(second['sequences']),4)
        for ident,origin in prior_origins.items():
            self.assertEqual(second['settings']['fcpxml']['sequence_origins'][ident],origin)
            self.assertEqual(sequence_views(second)[ident],sequence_views(first)[ident])

    def test_real_archive_relocation_preserves_source_clocks_nested_edits_and_media(self):
        from project_archive import export_archive,import_archive
        p=self.imported();before=copy.deepcopy(p)
        archive=self.root/'fcpxml.cinematicum.zip';report=export_archive(p,self.root,archive)
        projects=self.root/'restored';projects.mkdir()
        restored=import_archive(archive,projects)
        fresh=projects/restored['id']
        self.assertEqual(restored['clips'],p['clips']);self.assertEqual(restored['sequences'],p['sequences'])
        self.assertEqual(restored['settings']['fcpxml'],p['settings']['fcpxml']);self.assertEqual(p,before)
        self.assertEqual({f['path'] for f in report['manifest']['files'] if f['path'].startswith('media/')},{'media/red.mov','media/blue.mov'})
        out=self.root/'archive_restored.mov';render_project(restored,fresh,out,'prores')
        pictures,pcm=decode_movie(out);frames,channels,expected=fixture_expectations()
        np.testing.assert_array_equal(picture_counters(pictures),frames);np.testing.assert_array_equal(pcm,expected)
        wire=export_fcpxml(restored,fresh)['document']
        self.assertEqual(ET.fromstring(wire).find('project/sequence').get('tcStart'),stamp(ORIGIN))

if __name__ == '__main__':
    unittest.main()
