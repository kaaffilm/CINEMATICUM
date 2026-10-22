#!/usr/bin/env python3
"""Owned actual-browser Lensfun/fisheye workflow plus independent saved pixels.

Requires an explicitly provisioned browser/Playwright and the pinned upstream
Lensfun file. It does not download software, mutate user projects or certify
WKWebView/native installation. The image fixture is SYNTHETIC ENGINE TEST.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit

from engine import probe_media
from frame_preview import preview_identity
from lens_geometry import parse_lensfun_xml
import server as server_module
from server import Server, Store
from test_lens_compositor import WIDTH, HEIGHT, FPS, fixture, render_delivery_control
from test_lens_geometry import oracle

HERE=Path(__file__).resolve().parent
PROFILE_SHA='f7693b6779edd8ed10d7dc23113669255bfa4987cea7db0e843f7f5f2bbbe615'
PROFILE_ID='ea257b1f0767fc45329a2d98'
FRAMES=8


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value): Path(path).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def run(browser,profile_file,evidence):
    evidence.mkdir(parents=True,exist_ok=False)
    result={'schema':'cinematicum-lens-models-browser-acceptance-v1','native_certified':False,'passed':False,'checks':{}}
    checks=result['checks'];started=time.monotonic();server=store=thread=None
    original=server_module.render_frame;requests={}
    def observe(project,directory,frame,output,*args,**kwargs):
        requests[Path(output).stem]={'project':copy.deepcopy(project),'frame':frame,'identity':preview_identity(project,frame)}
        return original(project,directory,frame,output,*args,**kwargs)
    def decode(path):
        return subprocess.run([shutil.which('ffmpeg'),'-v','error','-nostdin','-threads','1','-i',str(path),'-map','0:v:0','-an','-threads','1','-pix_fmt','rgb24','-f','rawvideo','pipe:1'],capture_output=True,check=True,timeout=4).stdout
    try:
        if digest(profile_file)!=PROFILE_SHA:raise ValueError('Pass the exact recorded Lensfun XML bytes; no substitute profile is accepted.')
        result['profile_sha256']=PROFILE_SHA;result['browser_sha256']=digest(browser)
        with tempfile.TemporaryDirectory(prefix='cinematicum-lens-models-ENGINE-TEST-') as temp:
            scratch=Path(temp);store=Store(scratch/'workspace');server_module.render_frame=observe
            project=store.new_project({'name':'ENGINE TEST — Lensfun and fisheye','width':WIDTH,'height':HEIGHT,'fps':FPS})
            source=scratch/'ENGINE_TEST_alpha_ramps.mkv'
            pixels=b''.join(bytes(fixture(frame,x,y)) for frame in range(FRAMES) for y in range(HEIGHT) for x in range(WIDTH))
            subprocess.run([shutil.which('ffmpeg'),'-v','error','-nostdin','-y','-threads','1','-f','rawvideo','-pixel_format','rgba','-video_size',f'{WIDTH}x{HEIGHT}','-framerate',str(FPS),'-i','pipe:0','-an','-c:v','ffv1','-pix_fmt','bgra','-threads','1',str(source)],input=pixels,capture_output=True,check=True,timeout=4)
            source_sha=digest(source);asset=store.admit(project['id'],source,source.name)
            server=Server(0,store);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.025},daemon=True);thread.start()
            config={'url':f'http://127.0.0.1:{server.server_port}/','asset_id':asset['id'],'browser':str(browser),'profile_file':str(profile_file),'profile_sha256':PROFILE_SHA,'profile_id':PROFILE_ID,'report':str(evidence/'ui-report.json'),'screenshot':str(evidence/'ENGINE_TEST_lens_controls.png')}
            write(scratch/'config.json',config)
            process=subprocess.run(['node',str(HERE/'test_lens_models_browser.cjs'),str(scratch/'config.json')],capture_output=True,text=True,timeout=30)
            (evidence/'driver.stdout').write_text(process.stdout);(evidence/'driver.stderr').write_text(process.stderr)
            ui=json.loads((evidence/'ui-report.json').read_text());result['ui']=ui
            checks['actual_shipped_browser_controls']=process.returncode==0 and ui.get('passed') is True
            saved=store.get(project['id']);directory=store.project_dir(project['id']);write(evidence/'ENGINE_TEST_saved_project.json',saved)
            expected=next(row['profile'] for row in parse_lensfun_xml(profile_file.read_text())['calibrations'] if row['id']==PROFILE_ID)
            clips=saved.get('clips',[]);nodes=clips[0].get('compositor',{}).get('nodes',[]) if len(clips)==1 else []
            node=next((n for n in nodes if n['id']==ui.get('lens_id')),{});params=node.get('params',{})
            checks['exact_upstream_calibration_saved']=params.get('profile')==expected and params.get('model')=='lensfun'
            checks['one_owned_source_and_clip']=len(saved['assets'])==len(clips)==1 and not saved.get('titles')
            checks['original_source_bytes_unchanged']=digest(directory/asset['path'])==source_sha==asset['sha256']
            with store.lock:jobs=copy.deepcopy([j for j in store.jobs.values() if j.get('project_id')==project['id']])
            frame_pixels={}
            for name,row in ui.get('frames',{}).items():
                image=directory/'previews'/Path(urlsplit(row['url']).path).name
                request=requests.get(image.stem,{})
                frame_node=next((n for n in request.get('project',{}).get('clips',[{}])[0].get('compositor',{}).get('nodes',[]) if n['id']==ui.get('lens_id')),{});p=frame_node.get('params',{})
                wanted=params if name in {'lensfun','reopened'} else {'model':'fisheye','projection':name,'fx':.55,'fy':.72,'direction':'undistort'}
                checks[name+'_exact_snapshot']=request.get('identity')==image.stem and request.get('frame')==0 and all(p.get(k)==v for k,v in wanted.items())
                matching=[j for j in jobs if j['kind']=='frame-preview' and j['state']=='completed' and j.get('result',{}).get('url')==row['url']]
                checks[name+'_actual_receipt']=bool(matching) and digest(image)==matching[-1]['result'].get('sha256')
                decoded=decode(image);frame_pixels[name]=decoded;errors=[]
                for y in range(3,HEIGHT,7):
                    for x in range(3,WIDTH,9):
                        point=oracle(p,x,y);expected_rgb=[0.,0.,0.]
                        if point:
                            u,v=point;xx,yy=math.floor(u),math.floor(v);dx,dy=u-xx,v-yy
                            for a,b,w in ((xx,yy,(1-dx)*(1-dy)),(min(xx+1,WIDTH-1),yy,dx*(1-dy)),(xx,min(yy+1,HEIGHT-1),(1-dx)*dy),(min(xx+1,WIDTH-1),min(yy+1,HEIGHT-1),dx*dy)):
                                rgba=fixture(0,a,b)
                                for c in range(3):expected_rgb[c]+=w*rgba[c]*rgba[3]/255
                        offset=3*(y*WIDTH+x);errors.extend(abs(a-b) for a,b in zip(decoded[offset:offset+3],expected_rgb))
                result.setdefault('picture_errors',{})[name]={'mean':sum(errors)/len(errors),'max':max(errors)}
                checks[name+'_independent_ray_and_alpha_pixels']=len(decoded)==WIDTH*HEIGHT*3 and sum(errors)/len(errors)<3 and max(errors)<8
                shutil.copy2(image,evidence/('ENGINE_TEST_'+name+'.png'))
            if {'lensfun','reopened'} <= ui.get('frames',{}).keys():
                snapshots=[]
                for name in ('lensfun','reopened'):
                    snapshot=copy.deepcopy(requests[Path(urlsplit(ui['frames'][name]['url']).path).stem]['project'])
                    for key in ('revision','updated_at'):snapshot.pop(key,None)
                    snapshots.append(snapshot)
                checks['reopen_preserves_full_project_except_save_metadata']=snapshots[0]==snapshots[1]
                checks['reopen_preserves_every_decoded_pixel']=frame_pixels['lensfun']==frame_pixels['reopened']
            rendered=[j for j in jobs if j['kind']=='render' and j['state']=='completed'];checks['one_complete_movie_export']=len(rendered)==1
            if rendered:
                receipt=rendered[0]['result'];movie=directory/'exports'/receipt['filename'];decoded=decode(movie);metadata=probe_media(movie);result['media']=metadata
                checks['movie_receipt_and_every_frame']=digest(movie)==receipt['sha256'] and metadata['frames']==FRAMES and len(decoded)==FRAMES*WIDTH*HEIGHT*3
                checks['browser_plays_same_export']=ui.get('playback',{}).get('url')==receipt['url'] and ui['playback']['time']>.06
                control=scratch/'codec-control';control.mkdir();lossless,encoded,_=render_delivery_control(saved,directory,control)
                checks['paused_picture_equals_lossless_movie']=frame_pixels.get('lensfun')==lossless[:WIDTH*HEIGHT*3]
                checks['whole_movie_equals_separate_codec_control']=decoded==encoded
                shutil.copy2(movie,evidence/'ENGINE_TEST_lensfun_movie.mp4')
            result['jobs']=[{'kind':j['kind'],'state':j['state']} for j in jobs]
            write(evidence/'ENGINE_TEST_frame_requests.json',requests)
            checks['browser_binary_unchanged']=result['browser_sha256']==digest(browser)
    except Exception as error:
        result['error']=str(error)
        if isinstance(error,subprocess.CalledProcessError):result['process_error']=(error.stderr or b'').decode(errors='replace')[-1600:]
    finally:
        if server:server.shutdown();server.server_close()
        if thread:thread.join(timeout=1)
        if store:store.shutdown()
        server_module.render_frame=original
    result['elapsed_seconds']=round(time.monotonic()-started,3);result['passed']=bool(checks) and all(checks.values()) and 'error' not in result
    write(evidence/'browser-report.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--browser',type=Path,required=True);parser.add_argument('--profile',type=Path,required=True);parser.add_argument('--evidence',type=Path,required=True);args=parser.parse_args()
    result=run(args.browser.resolve(),args.profile.resolve(),args.evidence.resolve());print(json.dumps(result));raise SystemExit(0 if result['passed'] else 1)
