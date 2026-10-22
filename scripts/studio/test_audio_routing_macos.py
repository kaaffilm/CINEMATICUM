#!/usr/bin/env python3
"""Measure actual native WKWebView live PCM after the application's audio controls.

The source has two independent stereo tone streams; source stream 2 must reach
the application's output with its channels swapped (.4 at660Hz, .3 at440Hz).
No rendered export is substituted for the live audio observation.
"""
import argparse
import array
import copy
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


def run_sequence(binary, output, scenario, repetitions=3):
    """Observe the actual sum of owned live voices, including repeated starts.

    The disposable project is a fixture; playback, pause, restart and save use
    shipped controls. The observer connects only a silent measurement output
    and never supplies the application's sound or substitutes a movie render.
    """
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    result={'passed':False,'scenario':scenario,'repetitions':repetitions,
            'fixture':'SYNTHETIC ENGINE TEST — NOT A FILM','checks':{}}
    store=server=thread=None;started=time.monotonic()
    try:
        if scenario not in ('overlap','nested','retimed','reverse','reverse_retimed','nested_reverse') or not 2<=repetitions<=10:
            raise ValueError('Use overlap, nested or retimed and 2–10 repetitions.')
        workspace=output/'ENGINE_TEST_sequence_audio_workspace'
        if workspace.exists():raise ValueError('Use a fresh output folder for native audio acceptance.')
        source=output/'ENGINE_TEST_sequence_audio.mov'
        ffmpeg(['-f','lavfi','-i','color=c=blue:s=96x64:r=24:d=8',
                '-f','lavfi','-i','aevalsrc=0.1*sin(2*PI*220*t)|0.2*sin(2*PI*330*t):s=48000:d=8',
                '-f','lavfi','-i','aevalsrc=0.3*sin(2*PI*440*t)|0.4*sin(2*PI*660*t):s=48000:d=8',
                '-map','0:v','-map','1:a','-map','2:a','-c:v','libx264','-preset','ultrafast','-crf','0',
                '-pix_fmt','yuv420p','-c:a','pcm_s16le','-threads','1',str(source)])
        store=Store(workspace);project=store.new_project({'name':'ENGINE TEST '+scenario+' live audio','width':96,'height':64,'fps':24})
        asset=store.admit(project['id'],source,'ENGINE TEST sequence audio.mov',{'fixture':'ENGINE TEST'})
        source=store.asset(project['id'],asset['id'])[1]
        project=store.get(project['id']);first,second=asset['audio_streams'];speed=1.5 if scenario in ('retimed','reverse_retimed') else 1
        clip={'id':'primary','asset_id':asset['id'],'start':0,'in':12,'duration':96,'track':0,'speed':speed,
              'audio':{'stream_index':second['index'],'channels':[1,0]}}
        routes=[{'clip_id':'primary','stream_index':second['index'],'channels':[1,0],'playback_rate':speed,'scales':[1,1]}]
        project['clips']=[clip]
        if scenario=='overlap':
            clip['volume']=.5;routes[0]['scales']=[.5,.5]
            project['clips'].append({'id':'overlap','asset_id':asset['id'],'start':24,'in':12,'duration':72,'track':-1,
                                     'volume':.7,'audio':{'stream_index':first['index'],'channels':[0,1],'pan':-.2}})
            routes.append({'clip_id':'overlap','stream_index':first['index'],'channels':[0,1],'playback_rate':1,'scales':[.7,.56]})
        elif scenario in ('nested','nested_reverse'):
            # Parent and child gain/pan products must survive recursive audio
            # traversal, including a nonzero parent and source in point.
            clip.update(duration=144,volume=.9,audio={**clip['audio'],'pan':-.2})
            project.update(sequence_id='main',sequence_name='Main',tracks=[{'id':0,'gain':.75}],
                sequences=[{'id':'child','name':'ENGINE TEST child','clips':[clip],'titles':[],'captions':[],
                            'tracks':[{'id':0,'gain':.8}]}],
                clips=[{'id':'nested_parent','sequence_id':'child','start':0,'in':12,'duration':96,
                        'track':0,'volume':.8,'audio':{'pan':.25}}])
            routes[0]['scales']=[.75*.8*.8*.9*.75,.75*.8*.8*.9*.8]
        if scenario in ('reverse','reverse_retimed'):
            clip['reverse']=True
        elif scenario=='nested_reverse':
            project['clips'][0]['reverse']=True
        if 'reverse' in scenario: routes[0]['reverse']=True
        store.save(project['id'],project)
        authored=validate_project(store.get(project['id']),store.project_dir(project['id']))
        frequency_values=(220,330,440,660,990)
        oracle={'rms':[0,0],'amplitudes':{str(frequency):[0,0] for frequency in frequency_values}}
        raw_oracle=copy.deepcopy(oracle);decoded={};voice_oracles=[]
        for route in routes:
            mapping=route['channels'];filters=['asetpts=PTS-STARTPTS','aresample=48000',
                'pan=stereo|c0=c'+str(mapping[0])+'|c1=c'+str(mapping[1]),'aformat=sample_fmts=flt:channel_layouts=stereo']
            if route['playback_rate']!=1:filters.append('atempo='+str(route['playback_rate']))
            raw=ffmpeg(['-i',str(source),'-map','0:'+str(route['stream_index']),'-af',','.join(filters),
                        '-c:a','pcm_f32le','-f','f32le','pipe:1']).stdout
            decoded[route['clip_id']]=raw;values=array.array('f',raw)
            if sys.byteorder!='little':values.byteswap()
            channels=[values[48000+channel:113536+channel:2] for channel in (0,1)]
            observed={'rms':[math.sqrt(sum(value*value for value in channel)/len(channel)) for channel in channels],
                      'amplitudes':{str(frequency):[2*abs(sum(value*complex(math.cos(2*math.pi*frequency*i/48000),math.sin(2*math.pi*frequency*i/48000)) for i,value in enumerate(channel)))/len(channel) for channel in channels] for frequency in frequency_values}}
            voice_oracles.append({'clip_id':route['clip_id'],**observed})
            for channel,scale in enumerate(route['scales']):
                oracle['rms'][channel]+=(observed['rms'][channel]*scale)**2
                raw_oracle['rms'][channel]+=observed['rms'][channel]**2
                for frequency in frequency_values:
                    oracle['amplitudes'][str(frequency)][channel]+=observed['amplitudes'][str(frequency)][channel]*scale
                    raw_oracle['amplitudes'][str(frequency)][channel]+=observed['amplitudes'][str(frequency)][channel]
        for value in (oracle,raw_oracle):value['rms']=[math.sqrt(item) for item in value['rms']]
        result['independent_voice_oracles']=voice_oracles;result['independent_mix_oracle']=oracle
        test={'scenario':scenario,'repetitions':repetitions,'asset_id':asset['id'],'source_sha256':asset['sha256'],
              'routes':routes,'oracle':oracle,'raw_oracle':raw_oracle,'capture_frame':48}
        script=output/'ENGINE_TEST_sequence_audio.js';script.write_text('const AUDIO_ROUTING_TEST='+json.dumps(test)+';\n'+Path(__file__).with_name('macos').joinpath('AudioRoutingSmoke.js').read_text())
        screenshot=output/'ENGINE_TEST_sequence_audio.png';server=Server(0,store);server.RequestHandlerClass=AudioProbeHandler
        thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True);thread.start()
        timeout=12 if 'reverse' in scenario else 12+repetitions*8
        process=subprocess.run([str(Path(binary).resolve()),'--url','http://127.0.0.1:'+str(server.server_port),
                                '--output',str(screenshot),'--script',str(script),'--timeout',str(timeout)],
                               capture_output=True,text=True,timeout=timeout+3)
        ui=None
        for line in reversed(process.stdout.splitlines()):
            try:
                value=json.loads(line)
                if isinstance(value,dict) and 'passed' in value:ui=value;break
            except ValueError:pass
        if ui is None:raise RuntimeError('Native helper returned no report: '+(process.stderr or process.stdout)[-2000:])
        result['ui']=ui;checks=result['checks'];runs=ui.get('metrics',{}).get('runs',[])
        checks['actual_native_controls']=process.returncode==0 and ui.get('passed') is True
        checks['native_screenshot']=screenshot.is_file() and screenshot.stat().st_size>1000
        checks['all_repeated_runs_captured']=len(runs)==repetitions
        def matches(observed,expected):
            return observed.get('samples',0)>=32768 and all(abs(observed.get('rms',[0,0])[channel]-expected['rms'][channel])<.005 for channel in (0,1)) and all(abs(observed.get('amplitudes',{}).get(str(frequency),[0,0])[channel]-expected['amplitudes'][str(frequency)][channel])<.005 for frequency in frequency_values for channel in (0,1))
        checks['every_actual_live_mix_matches_independent_pcm']=bool(runs) and all(matches(run.get('pcm',{}),oracle) for run in runs)
        checks['every_actual_source_mix_matches_independent_pcm']=bool(runs) and all(matches(run.get('raw_pcm',{}),raw_oracle) for run in runs)
        voices=[voice for run in runs for voice in run.get('voices',[])]
        checks['all_voices_observed_each_run']=len(voices)==repetitions*len(routes)
        checks['reverse_voice_source_clock_decreases']=not ('reverse' in scenario) or (bool(voices) and all(voice.get('reverse') is True and voice.get('last_source_time',999)<voice.get('first_source_time',0)-.02 for voice in voices))
        checks['zero_native_underruns']=bool(voices) and all(voice.get('decoder',{}).get('underruns')==0 for voice in voices)
        checks['shared_clock_drift_below_80ms']=bool(voices) and all(voice.get('observations',0)>=3 and voice.get('clock_drift_seconds',999)<.08 for voice in voices)
        identities=[]
        for voice in (runs[0].get('voices',[]) if runs else []):
            receipt=voice.get('route',{}).get('manifest',{});url=receipt.get('url','');expected=decoded.get(voice['clip_id'])
            if not url.startswith('/api/projects/'+project['id']+'/audio-source/') or expected is None:identities.append(False);continue
            with urlopen('http://127.0.0.1:'+str(server.server_port)+url,timeout=3) as response:payload=response.read(8*1024*1024)
            raw=payload[58:];padding=raw[len(expected):]
            identities.append(receipt.get('source_sha256')==asset['sha256'] and receipt.get('sha256')==hashlib.sha256(payload).hexdigest()
                              and receipt.get('byte_size')==len(payload) and len(raw)==receipt.get('frames',0)*8
                              and raw[:len(expected)]==expected and padding==b'\0'*len(padding))
        checks['all_http_source_bytes_match_original_stream_tempo_and_mapping']=len(identities)==len(routes) and all(identities)
        saved=validate_project(store.get(project['id']),store.project_dir(project['id']))
        checks['saved_authored_structure_preserved']=all(saved.get(key)==authored.get(key) for key in ('clips','sequences','tracks'))
        checks['original_media_preserved']=hashlib.sha256(store.asset(project['id'],asset['id'])[1].read_bytes()).hexdigest()==asset['sha256']
        checks['no_render_substitution']=not any(job['kind']=='render' for job in store.jobs.values())
        result['passed']=all(checks.values())
        if not result['passed']:result['error']=ui.get('error') or 'Failed checks: '+','.join(key for key,value in checks.items() if not value)
    except Exception as error:result['error']=str(error)
    finally:
        if server:server.shutdown();server.server_close()
        if thread:thread.join(timeout=.3)
        if store:store.shutdown()
    result['elapsed_seconds']=round(time.monotonic()-started,3)
    (output/'ENGINE_TEST_sequence_audio_report.json').write_text(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--binary',type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--stream',choices=('first','second'),default='second');parser.add_argument('--codec',choices=('pcm_s16le','aac'),default='pcm_s16le');parser.add_argument('--container',choices=('mov','wav'),default='mov');parser.add_argument('--scenario',choices=('routing','overlap','nested','retimed','reverse','reverse_retimed','nested_reverse','all'),default='routing');parser.add_argument('--repetitions',type=int,default=3);args=parser.parse_args()
    if sys.platform!='darwin':print(json.dumps({'status':'skipped','reason':'macOS WKWebView required'}));raise SystemExit(0)
    if not args.binary or not args.binary.is_file():parser.error('Supply the compiled macos/SmokeTest.swift helper with --binary.')
    if args.scenario=='routing':result=run(args.binary,args.output,args.stream,args.codec,args.container)
    elif args.scenario=='all':
        reports=[run(args.binary,args.output/'routing',args.stream,args.codec,args.container)]
        reports.extend(run_sequence(args.binary,args.output/scenario,scenario,args.repetitions) for scenario in ('overlap','nested','retimed'))
        result={'passed':all(report['passed'] for report in reports),'reports':reports}
        (args.output/'ENGINE_TEST_audio_acceptance_report.json').write_text(json.dumps(result,indent=2))
    else:result=run_sequence(args.binary,args.output,args.scenario,args.repetitions)
    print(json.dumps(result,sort_keys=True));raise SystemExit(0 if result['passed'] else 1)
