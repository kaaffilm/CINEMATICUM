#!/usr/bin/env python3
"""Native editorial controls and independently decoded short media outputs.

Each stage owns a fresh synthetic test workspace and completes within a bounded
native helper run. No user film or production project is read or modified.
"""
import argparse
import array
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from engine import probe_media,validate_project
from server import Store,Server

STAGES=('sequences','captions','audio','multicam')

def ffmpeg(args):
    return subprocess.run([shutil.which('ffmpeg'),'-v','error','-nostdin','-y','-threads','1','-filter_complex_threads','1']+args,
                          capture_output=True,check=True,timeout=4)

def run(binary,output,stage):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    result={'passed':False,'stage':stage,'fixture':'SYNTHETIC ENGINE TEST — NOT A FILM','checks':{}}
    start=time.monotonic();store=server=thread=None
    try:
        workspace=output/('ENGINE_TEST_editorial_'+stage+'_workspace')
        if workspace.exists():raise ValueError('Use a fresh output folder; this stage already owns its workspace.')
        store=Store(workspace);project=store.new_project({'name':'ENGINE TEST native editorial '+stage,'width':96,'height':64,'fps':24})
        assets=[]
        for name,color in (('red','red'),('blue','blue')):
            source=output/('ENGINE_TEST_'+stage+'_'+name+'.mov')
            ffmpeg(['-f','lavfi','-i',f'color=c={color}:s=96x64:r=24:d=1',
                    '-f','lavfi','-i','aevalsrc=0.1|0.2:s=48000:d=1',
                    '-f','lavfi','-i','aevalsrc=0.3|0.4:s=48000:d=1',
                    '-map','0:v','-map','1:a','-map','2:a','-c:v','libx264','-preset','ultrafast','-crf','0','-pix_fmt','yuv420p',
                    '-c:a','pcm_s16le','-threads','1',str(source)])
            assets.append(store.admit(project['id'],source,'ENGINE TEST '+name+'.mov',{'fixture':'ENGINE TEST'}))
        project=store.get(project['id'])
        if stage!='multicam':
            project['clips']=[{'id':'red_clip','asset_id':assets[0]['id'],'start':0,'in':0,'duration':8 if stage!='audio' else 16,'track':0}]
            if stage!='audio':project['clips'].append({'id':'blue_clip','asset_id':assets[1]['id'],'start':8,'in':0,'duration':8,'track':0})
        store.save(project['id'],project)
        script=output/('ENGINE_TEST_editorial_'+stage+'.js')
        script.write_text('const EDITORIAL_TEST='+json.dumps({'stage':stage})+';\n'+Path(__file__).with_name('macos').joinpath('EditorialSmoke.js').read_text())
        screenshot=output/('ENGINE_TEST_editorial_'+stage+'.png')
        server=Server(0,store);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True);thread.start()
        process=subprocess.run([str(Path(binary).resolve()),'--url','http://127.0.0.1:'+str(server.server_port),
                                '--output',str(screenshot),'--script',str(script),'--timeout','12'],capture_output=True,text=True,timeout=14)
        ui=None
        for line in reversed(process.stdout.splitlines()):
            try:
                value=json.loads(line)
                if isinstance(value,dict) and 'passed' in value:ui=value;break
            except ValueError:pass
        if ui is None:raise RuntimeError('Native helper returned no result: '+(process.stderr or process.stdout)[-1500:])
        result['ui']=ui;checks=result['checks'];checks['actual_native_controls']=process.returncode==0 and ui.get('passed') is True
        saved=validate_project(store.get(project['id']),store.project_dir(project['id']))
        checks['native_screenshot']=screenshot.is_file() and screenshot.stat().st_size>1000
        completed=[job for job in store.jobs.values() if job['project_id']==project['id'] and job['kind']=='render' and job['state']=='completed']
        checks['one_completed_movie']=len(completed)==1
        if stage=='sequences':checks['saved_live_sequence_dependency']=len(saved.get('sequences',[]))==1 and len(saved['clips'])==1 and saved['clips'][0].get('sequence_id')=='main'
        if stage=='captions':
            checks['saved_caption_and_raster']=len(saved.get('captions',[]))==1 and saved['captions'][0]['text']=='ENGINE TEST\nسلام' and len(saved['titles'])==1 and bool(saved['titles'][0].get('asset_id'))
            sidecars=list((store.project_dir(project['id'])/'exports').glob('*.srt'))
            checks['actual_caption_sidecar']=len(sidecars)==1 and '00:00:00,667' in sidecars[0].read_text() and 'سلام' in sidecars[0].read_text()
        if stage=='audio':checks['saved_source_mapping']=saved['clips'][0]['audio'].get('stream_index')==2 and saved['clips'][0]['audio'].get('channels')==[1,0]
        if stage=='multicam':checks['saved_exact_angle_cut']=len(saved.get('multicam_groups',[]))==1 and [(c['start'],c['duration']) for c in saved['clips']]==[(0,6),(6,18)] and saved['clips'][0]['asset_id']!=saved['clips'][1]['asset_id']
        if len(completed)==1:
            movie=store.project_dir(project['id'])/'exports'/completed[0]['result']['filename'];actual=probe_media(movie)
            frames=24 if stage=='multicam' else 16
            checks['exact_movie_frames']=actual['frames']==frames and actual['width']==96 and actual['height']==64
            raw=ffmpeg(['-i',str(movie),'-map','0:v:0','-pix_fmt','rgb24','-f','rawvideo','-threads','1','pipe:1']).stdout
            checks['decoded_frame_count']=len(raw)==frames*96*64*3
            if stage in ('sequences','multicam'):
                cut=8 if stage=='sequences' else 6;stride=96*64*3
                checks['independent_cut_picture_oracle']=all(raw[i*stride]>220 and raw[i*stride+2]<20 for i in range(cut)) and all(raw[i*stride+2]>220 and raw[i*stride]<20 for i in range(cut,frames))
            if stage=='audio':
                pcm=array.array('f',ffmpeg(['-i',str(movie),'-map','0:a:0','-ac','2','-ar','48000','-f','f32le','pipe:1']).stdout)
                left=sum(pcm[2000:20000:2])/9000;right=sum(pcm[2001:20001:2])/9000
                checks['actual_selected_audio_stream_and_swap']=abs(left-.4)<.002 and abs(right-.3)<.002
            checks['download_matches_actual_movie']=ui.get('metrics',{}).get('movie')==completed[0]['result']['url']+'?download=1'
            result['movie_sha256']=hashlib.sha256(movie.read_bytes()).hexdigest()
        result['passed']=all(checks.values())
        if not result['passed']:result['error']=ui.get('error') or 'Failed checks: '+','.join(k for k,v in checks.items() if not v)
    except Exception as error:result['error']=str(error)
    finally:
        if server:server.shutdown();server.server_close()
        if thread:thread.join(timeout=.3)
        if store:store.shutdown()
    result['elapsed_seconds']=round(time.monotonic()-start,3)
    (output/('ENGINE_TEST_editorial_'+stage+'_report.json')).write_text(json.dumps(result,indent=2))
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--binary',type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--stage',required=True,choices=STAGES);args=parser.parse_args()
    if sys.platform!='darwin':print(json.dumps({'status':'skipped','reason':'macOS WKWebView required'}));raise SystemExit(0)
    if not args.binary or not args.binary.is_file():parser.error('Supply the compiled macos/SmokeTest.swift helper with --binary.')
    result=run(args.binary,args.output,args.stage);print(json.dumps(result,sort_keys=True));raise SystemExit(0 if result['passed'] else 1)
