"""Shipped nested playback sampling compared with decoded export frames.

Every source and output here is a synthetic ENGINE TEST, never film footage.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from engine import render_project


@unittest.skipUnless(all(shutil.which(tool) for tool in ('node','ffmpeg','ffprobe')), 'Node and FFmpeg required')
class SequencePlaybackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='cinematicum-PLAYBACK-ENGINE-TEST-')
        cls.root=Path(cls.temp.name);(cls.root/'media').mkdir()
        raw=b''.join(bytes((12+i*4,16,8))*32*32 for i in range(48))
        cls.ffmpeg(['-f','rawvideo','-pixel_format','rgb24','-video_size','32x32','-framerate','24','-i','pipe:0',
                    '-c:v','ffv1','-pix_fmt','gbrp',str(cls.root/'media/counter.mkv')],raw)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    @staticmethod
    def ffmpeg(args,payload=None):
        return subprocess.run([shutil.which('ffmpeg'),'-v','error','-nostdin','-y','-threads','1','-filter_complex_threads','1']+args,
                              input=payload,capture_output=True,check=True,timeout=30).stdout
    def picture(self,project,name):
        movie=self.root/(name+'.mov');render_project(project,self.root,movie,'prores')
        raw=self.ffmpeg(['-i',str(movie),'-map','0:v:0','-pix_fmt','rgb24','-threads','1','-f','rawvideo','pipe:1'])
        stride=32*32*3
        return [raw[i:i+stride] for i in range(0,len(raw),stride)]
    def project(self,rate):
        return {'version':1,'id':'playback_test','name':'ENGINE TEST playback','width':32,'height':32,
                'frame_rate':rate,'fps':rate['numerator']/rate['denominator'],
                'assets':[{'id':'counter','path':'media/counter.mkv'}],
                'clips':[{'id':'counter','asset_id':'counter','start':0,'in':0,'duration':48,'track':0}],
                'titles':[],'tracks':[]}
    def sample(self,project,clips,length):
        script="""
const fs=require('fs'),vm=require('vm'),input=JSON.parse(fs.readFileSync(0,'utf8')),sandbox={window:{}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(input.module,'utf8'),sandbox);
const sample=sandbox.window.CinematicumSequencePlayback.sampleSequenceFrame;
process.stdout.write(JSON.stringify(input.clips.map(clip=>Array.from({length:clip.duration},(_,i)=>sample(clip,clip.start+i,input.project,input.length)))));
"""
        result=subprocess.run([shutil.which('node'),'-e',script],input=json.dumps({'module':str(Path(__file__).parent/'web/sequence-playback.js'),
            'project':project,'clips':clips,'length':length}),capture_output=True,text=True,timeout=10,check=True)
        return json.loads(result.stdout)
    def test_integer_fractional_fast_slow_reverse_samples_match_decoded_engine(self):
        for rate in ({'numerator':24,'denominator':1},{'numerator':30000,'denominator':1001}):
            baseline=self.project(rate)
            # The source is normalized onto this sequence clock before nesting.
            source=self.picture(baseline,'source_'+str(rate['numerator']))
            variants=[{'in':start,'speed':speed,'reverse':reverse,'duration':8}
                      for start in (0,.25,.49999,.5,.50001,1.25,3.75,11.1)
                      for speed in (.25,.5,.75,1,1.25,1.7,2,4) for reverse in (False,True)]
            for batch_start in range(0,len(variants),16):
                variants_batch=variants[batch_start:batch_start+16];project=copy.deepcopy(baseline)
                project.update(sequence_id='main',sequence_name='Main',sequences=[{'id':'child','name':'Child','clips':baseline['clips'],'titles':[],'tracks':[]}])
                project['clips']=[{'id':'nested'+str(i),'sequence_id':'child','start':i*8,'track':0,**clip} for i,clip in enumerate(variants_batch)]
                samples=self.sample(project,project['clips'],len(source))
                actual=self.picture(project,'retime_'+str(rate['numerator'])+'_'+str(batch_start))
                self.assertEqual(len(actual),len(variants_batch)*8)
                for index,(clip,indices) in enumerate(zip(project['clips'],samples)):
                    with self.subTest(rate=rate,clip=clip):
                        self.assertEqual([hashlib.sha256(frame).hexdigest() for frame in actual[index*8:(index+1)*8]],
                                         [hashlib.sha256(source[i]).hexdigest() for i in indices],
                            'Interactive sequence samples differ from independently decoded export pictures: '+str(indices))
    def test_picture_clock_and_continuous_audio_cross_different_child_cuts(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),root=JSON.parse(fs.readFileSync(0,'utf8')).root;
const text=[],draws=[],created=new Map(),context=()=>({setTransform(){},clearRect(){},save(){},restore(){},translate(){},rotate(){},drawImage(...args){draws.push(args);},fillText(value){text.push(value);}});
const sandbox={window:{},document:{createElement(){return {width:0,height:0,getContext:context};}}};vm.createContext(sandbox);
for(const name of ['editing.js','sequence-playback.js'])vm.runInContext(fs.readFileSync(root+'/'+name,'utf8'),sandbox);
const p={width:96,height:64,fps:24,frame_rate:{numerator:24,denominator:1},sequence_id:'main',tracks:[{id:0,gain:.4}],titles:[],
 assets:[{id:'a',kind:'video',width:96,height:64,has_audio:true,audio_channels:2},{id:'b',kind:'video',width:96,height:64,has_audio:true,audio_channels:2}],
 clips:[{id:'nest',sequence_id:'child',start:0,in:.5,duration:4,speed:2,track:0,volume:.5,audio:{pan:.2}}],
 sequences:[{id:'child',name:'Child',tracks:[{id:0,gain:.5}],clips:[
  {id:'left',asset_id:'a',start:0,in:2,duration:3,speed:1,track:0,volume:.3,audio:{pan:-.3,fade_in:4,fade_duration:8}},
  {id:'right',asset_id:'b',start:3,in:7,duration:9,speed:1.5,track:0,volume:1}],
  titles:[{text:'Previous',start:2,duration:1},{text:'Current',start:3,duration:1}]}]};
const mediaFor=(clip,asset)=>{const media={kind:asset.kind,el:{duration:10,currentTime:0,readyState:4,paused:true,play(){this.paused=false;return Promise.resolve();},pause(){this.paused=true;}}};created.set(clip.id,{media,asset});return media;};
const ensureAudio=media=>{for(const key of ['gain','left','right','stereo'])media[key]={gain:{value:1}};};
const activeIds=new Set();sandbox.window.CinematicumSequencePlayback.draw({project:p,frame:1,context:context(),width:96,height:64,mediaFor,ensureAudio,playing:false,activeIds,revision:9});
assert.deepStrictEqual([...created.keys()].sort(),['nest/left/sound','nest/right']);
const picture=created.get('nest/right'),sound=created.get('nest/left/sound');
assert.strictEqual(picture.asset.kind,'video');assert.strictEqual(picture.media.el.currentTime,7/24);assert.strictEqual(picture.media.el.muted,true);
assert.strictEqual(sound.asset.kind,'audio');assert.strictEqual(sound.media.el.currentTime,4.5/24);assert.strictEqual(sound.media.el.muted,false);
assert(Math.abs(sound.media.gain.gain.value-.5*.4*.3*.5*(2.5/4))<1e-12,'Group gain/fade must use the continuous audio clock');
assert.strictEqual(sound.media.left.gain.value,.8);assert.strictEqual(sound.media.right.gain.value,.7);
assert.strictEqual(picture.media.el.playbackRate,3);assert.strictEqual(sound.media.el.playbackRate,2);
assert.deepStrictEqual(text,['Current'],'Titles must use the sampled integer picture clock');
assert.deepStrictEqual([...activeIds].sort(),['nest/left/sound','nest/right']);
"""
        result=subprocess.run([shutil.which('node'),'-e',script],input=json.dumps({'root':str(Path(__file__).parent/'web')}),
                              capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_top_level_video_keeps_original_audio_separate_from_proxy_picture(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),root=JSON.parse(fs.readFileSync(0,'utf8')).root;
const created=new Map(),routed=[],context={save(){},restore(){},translate(){},rotate(){},drawImage(){}};
const sandbox={window:{}};vm.createContext(sandbox);for(const name of ['editing.js','sequence-playback.js'])vm.runInContext(fs.readFileSync(root+'/'+name,'utf8'),sandbox);
const asset={id:'original',kind:'video',width:96,height:64,has_audio:true,audio_channels:6,audio_stream_index:1,audio_streams:[{index:1,channels:6,container_id:'0x2'}]};
const clip={id:'top',asset_id:'original',start:0,in:.5,duration:8,speed:1.5,track:0,volume:.7,audio:{stream_index:1,channels:[5,2],pan:.25}};
const project={width:96,height:64,fps:24,assets:[asset],clips:[clip],titles:[],tracks:[{id:0,gain:.5}]};
const mediaFor=(item,source)=>{const media={kind:source.kind,url:source.kind==='video'?'/proxy/original':'/media/original',el:{duration:10,currentTime:0,readyState:4,paused:true,play(){this.paused=false;return Promise.resolve();},pause(){this.paused=true;}}};created.set(item.id,{media,clip:item,asset:source});return media;};
const ensureAudio=(media,item,source)=>{routed.push({media,clip:item,asset:source});for(const key of ['gain','left','right'])media[key]={gain:{value:1}};return {ready:true};};
const activeIds=new Set();sandbox.window.CinematicumSequencePlayback.draw({project,frame:3,context,width:96,height:64,mediaFor,ensureAudio,playing:true,activeIds,revision:2});
assert.deepStrictEqual([...created.keys()],['top','top/sound']);assert.deepStrictEqual([...activeIds],['top','top/sound']);
const picture=created.get('top'),sound=created.get('top/sound');
assert.strictEqual(picture.media.url,'/proxy/original');assert.strictEqual(picture.media.el.muted,true);assert.strictEqual(picture.media.el.volume,0);
assert.strictEqual(sound.media.url,'/media/original');assert.strictEqual(sound.media.el.muted,false);assert.strictEqual(sound.media.el.volume,1);
assert.strictEqual(sound.asset.audio_streams,asset.audio_streams);assert.strictEqual(sound.clip.audio.channels,clip.audio.channels);
assert.strictEqual(routed.length,1);assert.strictEqual(routed[0].media,sound.media);
assert.strictEqual(sound.media.el.currentTime,5/24);assert.strictEqual(sound.media.el.playbackRate,1.5);
assert(Math.abs(sound.media.gain.gain.value-.35)<1e-12);assert.strictEqual(sound.media.left.gain.value,.75);assert.strictEqual(sound.media.right.gain.value,1);
"""
        result=subprocess.run([shutil.which('node'),'-e',script],input=json.dumps({'root':str(Path(__file__).parent/'web')}),
                              capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
