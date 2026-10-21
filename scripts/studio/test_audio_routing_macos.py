#!/usr/bin/env python3
"""Measure actual native WKWebView live PCM after the application's audio controls.

The source has two independent stereo tone streams; source stream 2 must reach
the application's output with its channels swapped (.4 at660Hz, .3 at440Hz).
No rendered export is substituted for the live audio observation.
"""
import argparse
import array
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from urllib.request import urlopen

from engine import probe_media,validate_project
from server import Store,Server,Handler


class AudioProbeHandler(Handler):
    def dispatch_get(self):
        if self.path=='/ENGINE_TEST_audio_probe_worklet.js':
            return self.file(Path(__file__).with_name('macos')/'AudioProbeWorklet.js')
        return super().dispatch_get()


def ffmpeg(args):
    return subprocess.run([shutil.which('ffmpeg'),'-v','error','-nostdin','-y','-threads','1','-filter_complex_threads','1']+args,
                          capture_output=True,check=True,timeout=5)


def run(binary,output,stream_choice='second',audio_codec='pcm_s16le',container='mov'):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    result={'passed':False,'stream_choice':stream_choice,'source_codec':audio_codec,'source_container':container,'fixture':'SYNTHETIC ENGINE TEST — NOT A FILM','checks':{}}
    started=time.monotonic();store=server=thread=None
    try:
        workspace=output/'ENGINE_TEST_audio_routing_workspace'
        if workspace.exists():raise ValueError('Use a fresh output folder; this harness already owns its workspace.')
        source=output/('ENGINE_TEST_audio_source.'+container)
        if container=='wav':
            ffmpeg(['-f','lavfi','-i','aevalsrc=0.3*sin(2*PI*440*t)|0.4*sin(2*PI*660*t):s=48000:d=4','-c:a','pcm_s16le',str(source)])
        else:ffmpeg(['-f','lavfi','-i','color=c=blue:s=96x64:r=24:d=4',
                '-f','lavfi','-i','aevalsrc=0.1*sin(2*PI*220*t)|0.2*sin(2*PI*330*t):s=48000:d=4',
                '-f','lavfi','-i','aevalsrc=0.3*sin(2*PI*440*t)|0.4*sin(2*PI*660*t):s=48000:d=4',
                '-map','0:v','-map','1:a','-map','2:a','-c:v','libx264','-preset','ultrafast','-crf','0','-pix_fmt','yuv420p',
                '-c:a',audio_codec]+(['-b:a','192k'] if audio_codec=='aac' else [])+['-threads','1',str(source)])
        inspected=probe_media(source);streams=inspected['audio_streams'];result['source_streams']=streams
        if container=='mov' and (len(streams)!=2 or any(not stream.get('container_id') for stream in streams)):raise ValueError('Native fixture lacks distinct container audio-track IDs.')
        selected=streams[0 if container=='wav' or stream_choice=='first' else 1]
        pcm=array.array('f',ffmpeg(['-i',str(source),'-map','0:'+str(selected['index']),'-ac','2','-f','f32le','pipe:1']).stdout)
        if sys.byteorder!='little':pcm.byteswap()
        channels=[pcm[4097:20481:2],pcm[4096:20480:2]]
        oracle={'rms':[math.sqrt(sum(value*value for value in channel)/len(channel)) for channel in channels],
                'amplitudes':{str(frequency):[2*abs(sum(value*complex(math.cos(2*math.pi*frequency*i/48000),math.sin(2*math.pi*frequency*i/48000)) for i,value in enumerate(channel)))/len(channel) for channel in channels] for frequency in (220,330,440,660)}}
        result['independent_source_pcm_oracle']=oracle
        store=Store(workspace);project=store.new_project({'name':'ENGINE TEST live source audio','width':96,'height':64,'fps':24})
        asset=store.admit(project['id'],source,'ENGINE TEST audio source.'+container,{'fixture':'ENGINE TEST'})
        project=store.get(project['id']);project['clips']=[{'id':'source_clip','asset_id':asset['id'],'start':0,'in':0,'duration':96,'track':-1 if container=='wav' else 0}];store.save(project['id'],project)
        test={'asset_id':asset['id'],'source_sha256':asset['sha256'],'stream_index':selected['index'],
              'frequencies':[330,220] if container=='mov' and stream_choice=='first' else [660,440],
              'oracle':oracle,
              'binding':'decoded-source-pcm'}
        script=output/'ENGINE_TEST_audio_routing.js';script.write_text('const AUDIO_ROUTING_TEST='+json.dumps(test)+';\n'+Path(__file__).with_name('macos').joinpath('AudioRoutingSmoke.js').read_text())
        screenshot=output/'ENGINE_TEST_audio_routing.png';server=Server(0,store);server.RequestHandlerClass=AudioProbeHandler
        thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True);thread.start()
        process=subprocess.run([str(Path(binary).resolve()),'--url','http://127.0.0.1:'+str(server.server_port),
                                '--output',str(screenshot),'--script',str(script),'--timeout','12'],capture_output=True,text=True,timeout=14)
        ui=None
        for line in reversed(process.stdout.splitlines()):
            try:
                value=json.loads(line)
                if isinstance(value,dict) and 'passed' in value:ui=value;break
            except ValueError:pass
        if ui is None:raise RuntimeError('Native helper returned no report: '+(process.stderr or process.stdout)[-2000:])
        result['ui']=ui;checks=result['checks'];checks['actual_native_controls']=process.returncode==0 and ui.get('passed') is True
        checks['native_screenshot']=screenshot.is_file() and screenshot.stat().st_size>1000
        saved=validate_project(store.get(project['id']),store.project_dir(project['id']))
        checks['saved_source_mapping']=saved['clips'][0]['audio'].get('stream_index')==selected['index'] and saved['clips'][0]['audio'].get('channels')==[1,0]
        checks['saved_live_gain_pan']=saved['clips'][0].get('volume')==.5 and saved['clips'][0]['audio'].get('pan')==.25
        measured=ui.get('metrics',{}).get('pcm',{})
        checks['live_pcm_matches_independent_decoded_source']=measured.get('samples',0)>=8192 and all(abs(measured.get('rms',[0,0])[channel]-oracle['rms'][channel])<.005 for channel in (0,1)) and all(abs(measured.get('amplitudes',{}).get(str(frequency),[0,0])[channel]-oracle['amplitudes'][str(frequency)][channel])<.005 for frequency in (220,330,440,660) for channel in (0,1))
        mixed=ui.get('metrics',{}).get('gain_pan',{}).get('pcm',{});scales=(.375,.5)
        checks['live_gain_pan_matches_decoded_source']=mixed.get('samples',0)>=8192 and all(abs(mixed.get('rms',[0,0])[channel]-oracle['rms'][channel]*scales[channel])<.005 for channel in (0,1)) and all(abs(mixed.get('amplitudes',{}).get(str(frequency),[0,0])[channel]-oracle['amplitudes'][str(frequency)][channel]*scales[channel])<.005 for frequency in (220,330,440,660) for channel in (0,1))
        metrics=ui.get('metrics',{});receipt=metrics.get('route',{}).get('manifest',{})
        checks['http_pcm_provenance']=False;checks['decoded_pcm_is_exact_source_pair']=False
        if receipt.get('url','').startswith('/api/projects/'+project['id']+'/audio-source/'):
            with urlopen('http://127.0.0.1:'+str(server.server_port)+receipt['url'],timeout=2) as response:
                decoded_bytes=response.read(4*1024*1024)
            decoded_file=output/'ENGINE_TEST_verified_http_source.wav';decoded_file.write_bytes(decoded_bytes)
            original_path=store.asset(project['id'],asset['id'])[1]
            source_hash=hashlib.sha256(original_path.read_bytes()).hexdigest()
            checks['http_pcm_provenance']=(receipt.get('source_sha256')==source_hash==asset['sha256']
                and receipt.get('sha256')==hashlib.sha256(decoded_bytes).hexdigest()
                and receipt.get('byte_size')==len(decoded_bytes)
                and receipt.get('channels')==[1,0] and receipt.get('stream_index')==selected['index']
                and metrics.get('source_url')==receipt['url']
                and metrics.get('current_src')=='http://127.0.0.1:'+str(server.server_port)+receipt['url'])
            decoded_pcm=array.array('f',ffmpeg(['-i',str(decoded_file),'-map','0:a:0','-f','f32le','pipe:1']).stdout)
            if sys.byteorder!='little':decoded_pcm.byteswap()
            expected=array.array('f')
            for i in range(0,len(pcm),2):expected.extend((pcm[i+1],pcm[i]))
            error=max((abs(a-b) for a,b in zip(decoded_pcm,expected)),default=1)
            padding=max((abs(value) for value in decoded_pcm[len(expected):]),default=0)
            result['http_source_pcm_comparison']={'original_samples':len(expected),'decoded_samples':len(decoded_pcm),'max_absolute_error':error,'padding_peak':padding}
            checks['decoded_pcm_is_exact_source_pair']=(len(decoded_pcm)>=len(expected) and len(decoded_pcm)==receipt.get('frames',0)*2 and error<1e-7 and padding==0)
        checks['gain_pan_uses_same_source_recipe']=bool(receipt) and metrics.get('gain_pan',{}).get('route',{}).get('cache_key')==receipt.get('cache_key')
        checks['owned_source_audio_job']=any(job['kind']=='audio-source' for job in store.jobs.values())
        checks['no_export_substitution']=not any(job['kind']=='render' for job in store.jobs.values())
        result['passed']=all(checks.values())
        if not result['passed']:result['error']=ui.get('error') or 'Failed checks: '+','.join(key for key,value in checks.items() if not value)
    except Exception as error:result['error']=str(error)
    finally:
        if server:server.shutdown();server.server_close()
        if thread:thread.join(timeout=.3)
        if store:store.shutdown()
    result['elapsed_seconds']=round(time.monotonic()-started,3)
    (output/'ENGINE_TEST_audio_routing_report.json').write_text(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--binary',type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--stream',choices=('first','second'),default='second');parser.add_argument('--codec',choices=('pcm_s16le','aac'),default='pcm_s16le');parser.add_argument('--container',choices=('mov','wav'),default='mov');args=parser.parse_args()
    if sys.platform!='darwin':print(json.dumps({'status':'skipped','reason':'macOS WKWebView required'}));raise SystemExit(0)
    if not args.binary or not args.binary.is_file():parser.error('Supply the compiled macos/SmokeTest.swift helper with --binary.')
    result=run(args.binary,args.output,args.stream,args.codec,args.container);print(json.dumps(result,sort_keys=True));raise SystemExit(0 if result['passed'] else 1)
