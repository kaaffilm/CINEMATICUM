#!/usr/bin/env python3
"""Actual Lensfun/fisheye controls, persisted fixture and <=18-second phases.

Only actual WKWebView on macOS can certify native acceptance. The exact XML is
admitted through a test-created File and the shipped onchange; physical open/
save panels are outside scope. No user project or shared runtime is changed.
"""
from __future__ import annotations
import argparse
import base64
import copy
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid

from engine import probe_media
from frame_preview import preview_identity
from lens_geometry import parse_lensfun_xml
import server as server_module
from server import Server,Store
from test_editing_ui_macos import read_helper_result
from test_lens_compositor import WIDTH,HEIGHT,FPS,fixture as source_pixel
from test_lens_geometry import oracle
from test_multicam_sync_macos import identity,safe_directory,write_json,read_json,source_inventory as runtime_inventory
from test_otio_compositions_macos import foreground

HERE=Path(__file__).resolve().parent
KIND='cinematicum-owned-lens-models-v1'
PHASES=('prepare','author','render')
PROFILE_SHA='f7693b6779edd8ed10d7dc23113669255bfa4987cea7db0e843f7f5f2bbbe615'
PROFILE_ID='ea257b1f0767fc45329a2d98'
FRAMES=8


def source_inventory():
    value=runtime_inventory()
    for name in ('test_lens_models_macos.py','macos/LensModelsSmoke.js','test_lens_models_native_browser.cjs',
                 'test_lens_compositor.py','test_lens_geometry.py','test_otio_compositions_macos.py','test_retime_browser.cjs'):
        value[name]=identity(HERE/name)
    return dict(sorted(value.items()))


def decode(path,*,pixel_format='rgb24',timeout=3):
    return subprocess.run([shutil.which('ffmpeg'),'-v','error','-nostdin','-threads','1','-i',str(path),
        '-map','0:v:0','-an','-threads','1','-pix_fmt',pixel_format,'-f','rawvideo','pipe:1'],
        capture_output=True,check=True,timeout=timeout).stdout


def expected_picture(params,frame,pixels):
    """Sample the independently generated source using physical-mm/ray math."""
    errors=[]
    for y in range(3,HEIGHT,7):
        for x in range(3,WIDTH,9):
            point=oracle(params,x,y);expected=[0.,0.,0.]
            if point:
                u,v=point;xx,yy=math.floor(u),math.floor(v);dx,dy=u-xx,v-yy
                for a,b,w in ((xx,yy,(1-dx)*(1-dy)),(min(xx+1,WIDTH-1),yy,dx*(1-dy)),(xx,min(yy+1,HEIGHT-1),(1-dx)*dy),(min(xx+1,WIDTH-1),min(yy+1,HEIGHT-1),dx*dy)):
                    rgba=source_pixel(frame,a,b)
                    for c in range(3):expected[c]+=w*rgba[c]*rgba[3]/255
            offset=3*(y*WIDTH+x);errors.extend(abs(a-b) for a,b in zip(pixels[offset:offset+3],expected))
    return {'mean_rgb_error':sum(errors)/len(errors),'max_rgb_error':max(errors),'sampled_components':len(errors)}


def codec_control(project,directory,scratch,profile,budget):
    """Separate lossless picture identity from the actual delivery encoder."""
    import engine
    from timebase import project_rate
    project=engine.validate_project(project,directory);rate=project_rate(project)
    inputs,graph,frames=engine._graph(project,directory,scratch)
    picture=graph+';[aout]anullsink;[vout]format=rgb24[lossless]'
    common=[shutil.which('ffmpeg'),'-v','error','-nostdin','-y','-threads','1']
    pixels=subprocess.run(common+['-filter_complex_threads','1']+inputs+['-filter_complex',picture,'-map','[lossless]','-an','-threads','1','-pix_fmt','rgb24','-f','rawvideo','pipe:1'],capture_output=True,check=True,timeout=budget(3)).stdout
    if len(pixels)!=frames*WIDTH*HEIGHT*3:raise ValueError('Lossless control frame count is wrong')
    movie=scratch/('ENGINE_TEST_codec_control.mov' if profile=='prores' else 'ENGINE_TEST_codec_control.mp4')
    encoder=['-c:v','prores_ks','-profile:v','3','-pix_fmt','yuv422p10le'] if profile=='prores' else ['-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p']
    subprocess.run(common+['-f','rawvideo','-pixel_format','rgb24','-video_size',f'{WIDTH}x{HEIGHT}','-framerate',rate.ffmpeg,'-i','pipe:0',
        '-vf','scale=out_color_matrix=bt709:out_range=tv','-r',rate.ffmpeg,'-t',rate.seconds_decimal(frames),'-an','-threads','2']+encoder+
        ['-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-movie_timescale','48000','-movflags','+faststart',str(movie)],
        input=pixels,capture_output=True,check=True,timeout=budget(3))
    return pixels,decode(movie,timeout=budget(3)),movie


def run(binary,output,operation,fixture_workspace,expected_sources,*,profile_file=None,delivery='prores',transport='WKWebView'):
    began=time.monotonic();deadline=began+18;output=safe_directory(output,new=True)
    result={'kind':KIND,'operation':operation,'browser':transport,'passed':False,'checks':{},
            'native_certified':operation!='prepare' and transport=='WKWebView' and sys.platform=='darwin',
            'scope':'Actual shipped lens controls and file onchange; no physical open/save panel or installed-launcher claim. ProRes playback is an explicit test-owned native video decoder probe of the real downloaded export.',
            'fixture':'SYNTHETIC ENGINE TEST — NOT PRODUCTION FOOTAGE'}
    checks=result['checks'];store=server=thread=root=fixture=project=None;requests={};prior_requests={};old_render=server_module.render_frame
    def budget(maximum,reserve=0):
        remaining=deadline-time.monotonic()-reserve
        if remaining<=.1:raise TimeoutError('The lens phase exhausted its18-second foreground budget')
        return min(maximum,remaining)
    def observe(project,directory,frame,output_path,*args,**kwargs):
        requests[Path(output_path).stem]={'project':copy.deepcopy(project),'frame':frame,'identity':preview_identity(project,frame)}
        return old_render(project,directory,frame,output_path,*args,**kwargs)
    try:
        if operation not in PHASES or delivery not in {'h264','prores'}:raise ValueError('Unsupported lens phase or delivery')
        before=source_inventory();result['source_before']=before
        if before!=expected_sources:raise ValueError('Runtime/web/acceptance source differs from the exact frozen inventory')
        checks['exact_frozen_runtime_web_acceptance_source']=True;result['helper_identity']=identity(binary)
        if operation=='prepare':
            if profile_file is None or identity(profile_file)['sha256']!=PROFILE_SHA:raise ValueError('Prepare requires the exact pinned Olympus XML bytes')
            catalog=parse_lensfun_xml(Path(profile_file).read_bytes().decode('utf-8'))
            expected=next(row['profile'] for row in catalog['calibrations'] if row['id']==PROFILE_ID)
            root=Path(fixture_workspace).absolute()
            if root.exists() or any(p.is_symlink() for p in (root,*root.parents)):raise ValueError('Prepare requires a new explicit fixture directory')
            root.mkdir(parents=True);(root/'media').mkdir();(root/'truth').mkdir()
            shutil.copyfile(profile_file,root/'truth/lensfun.xml')
            raw=b''.join(bytes(source_pixel(frame,x,y)) for frame in range(FRAMES) for y in range(HEIGHT) for x in range(WIDTH));(root/'truth/source.rgba').write_bytes(raw)
            original=root/'media/ENGINE_TEST_lens_alpha_ramps.mkv'
            subprocess.run([shutil.which('ffmpeg'),'-v','error','-nostdin','-y','-threads','1','-f','rawvideo','-pixel_format','rgba','-video_size',f'{WIDTH}x{HEIGHT}',
                '-framerate',str(FPS),'-i','pipe:0','-an','-c:v','ffv1','-pix_fmt','bgra','-threads','1',str(original)],input=raw,capture_output=True,check=True,timeout=budget(4,3))
            checks['lossless_fixture_matches_independent_source_samples']=decode(original,pixel_format='rgba',timeout=budget(3,2))==raw
            store=Store(root/'workspace');sentinel=store.new_project({'name':'ENGINE TEST lens sentinel','width':WIDTH,'height':HEIGHT,'fps':FPS})
            project=store.new_project({'name':'ENGINE TEST native Lensfun and fisheye','width':WIDTH,'height':HEIGHT,'fps':FPS})
            upload=root/'owned-upload.mkv';shutil.copyfile(original,upload);asset=store.admit(project['id'],upload,original.name);project=store.get(project['id'])
            fixture={'kind':KIND,'acceptance_id':uuid.uuid4().hex,'project_id':project['id'],'project_name':project['name'],'sentinel_id':sentinel['id'],'sentinel_name':sentinel['name'],
                'asset_id':asset['id'],'source_identity':identity(original),'truth':{p.name:identity(p) for p in (root/'truth').iterdir()},
                'sentinel_identity':identity(store.project_dir(sentinel['id'])/'project.json'),'profile_id':PROFILE_ID,'expected_profile':expected,'calibration_count':len(catalog['calibrations']),
                'helper_identity':result['helper_identity'],'delivery':delivery}
            write_json(root/'lens-fixture.json',fixture)
            checks['exact_upstream_profile_bytes_and106_samples']=fixture['truth']['lensfun.xml']['sha256']==PROFILE_SHA and len(catalog['calibrations'])==106
            checks['one_real_source_and_no_preauthored_graph']=len(project['assets'])==1 and not project['clips']
        else:
            root=safe_directory(fixture_workspace);fixture=read_json(root/'lens-fixture.json')
            if fixture.get('kind')!=KIND or not re.fullmatch('[a-f0-9]{32}',fixture.get('acceptance_id','')):raise ValueError('Wrong explicitly prepared lens fixture')
            if any(not re.fullmatch('[a-f0-9]{32}',fixture.get(k,'')) for k in ('project_id','sentinel_id','asset_id')):raise ValueError('Invalid fixture-owned identifiers')
            if fixture.get('delivery')!=delivery or fixture.get('helper_identity')!=result['helper_identity']:raise ValueError('Delivery or native helper changed after preparation')
            if (root/(operation+'-passed.json')).exists():raise ValueError('Preserve completed phases; use a new fixture for repetition')
            prior_path=root/(PHASES[PHASES.index(operation)-1]+'-passed.json');prior=read_json(prior_path)
            if prior.get('passed') is not True or prior.get('acceptance_id')!=fixture['acceptance_id'] or prior.get('source_inventory')!=before:raise ValueError('Prior phase does not certify this exact source/fixture')
            if prior.get('verified_frames_identity'):
                verified=root/'verified-frame-requests.json'
                if identity(verified)!=prior['verified_frames_identity']:raise ValueError('Previously verified frame snapshots changed')
                prior_requests=read_json(verified)
            if identity(root/'workspace/projects'/fixture['project_id']/'project.json')!=prior.get('saved_project_identity'):raise ValueError('Saved project changed after the previous phase')
            if identity(root/'media/ENGINE_TEST_lens_alpha_ramps.mkv')!=fixture['source_identity'] or {p.name:identity(p) for p in (root/'truth').iterdir()}!=fixture['truth']:raise ValueError('Original fixture media or truth changed')
            for path in (root/'workspace/jobs').glob('*.json'):
                job=read_json(path)
                if job.get('project_id') not in {fixture['project_id'],fixture['sentinel_id']} or job.get('state') not in {'completed','failed','cancelled'}:raise ValueError('Fixture contains unexpected or pending durable work')
            store=Store(root/'workspace');project=store.get(fixture['project_id']);initial=copy.deepcopy(project)
            with store.lock:jobs_before=set(store.jobs)
            cfg={**fixture,'operation':operation}
            if operation=='author':cfg['profile_base64']=base64.b64encode((root/'truth/lensfun.xml').read_bytes()).decode('ascii')
            else:
                lens_nodes=[n for c in project['clips'] for n in c.get('compositor',{}).get('nodes',[]) if n['type']=='lens_distortion']
                if len(lens_nodes)!=1:raise ValueError('Saved authoring did not retain exactly one measured lens')
                cfg['lens_id']=lens_nodes[0]['id']
            script=output/'ENGINE_TEST_lens_models.js';script.write_text((HERE/'macos/LensModelsSmoke.js').read_text().replace('/* ENGINE_TEST_CONFIG */ {}',json.dumps(cfg)),encoding='utf-8')
            result['executed_javascript_identity']=identity(script);downloads=output/'native_downloads';downloads.mkdir()
            server_module.render_frame=observe;server=Server(0,store);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.025},daemon=True);thread.start()
            screenshot=output/'ENGINE_TEST_lens_models.png';maximum=budget(14,2.8)
            process=foreground([Path(binary).resolve(),'--url','http://127.0.0.1:'+str(server.server_port)+'/','--output',screenshot,'--script',script,'--download-dir',downloads,'--timeout',round(maximum,2)],budget(maximum+.2,2.4))
            ui=read_helper_result(process);result['ui']=ui;result['helper_exit_code']=process.returncode;write_json(output/'ENGINE_TEST_browser_result.json',ui)
            checks['actual_shipped_controls_succeeded']=ui.get('passed') is True and process.returncode==0
            checks['no_browser_or_download_errors']=not ui.get('page_errors') and not ui.get('download_errors')
            if not checks['actual_shipped_controls_succeeded']:raise ValueError(ui.get('error') or 'Native lens controls failed')
            checks['all_declared_ui_checks_passed']=bool(ui.get('checks')) and all(ui['checks'].values())
            project=store.get(fixture['project_id']);clips=project.get('clips',[])
            nodes=clips[0].get('compositor',{}).get('nodes',[]) if len(clips)==1 else []
            node=next((n for n in nodes if n['id']==ui.get('metrics',{}).get('lens_id')),{});params=node.get('params',{})
            checks['exact_upstream_profile_saved']=params.get('model')=='lensfun' and params.get('profile')==fixture['expected_profile']
            checks['one_owned_source_clip_and_connected_lens']=len(project['assets'])==len(clips)==1 and len(nodes)==2 and clips[0]['compositor']['output']==node.get('id')
            with store.lock:jobs=[copy.deepcopy(j) for key,j in store.jobs.items() if key not in jobs_before]
            pictures={};snapshot_projects={}
            for name,row in ui.get('frames',{}).items():
                match=re.fullmatch('/api/projects/'+fixture['project_id']+'/previews/([a-f0-9]{64})\\.png',row.get('url',''))
                if not match:raise ValueError('Unexpected paused-frame receipt URL')
                key=match.group(1);path=store.project_dir(project['id'])/'previews'/(key+'.png');request=requests.get(key,prior_requests.get(key,{}))
                candidate=next((n for c in request.get('project',{}).get('clips',[]) for n in c.get('compositor',{}).get('nodes',[]) if n['id']==node.get('id')),{}).get('params',{})
                wanted=params if name in {'lensfun','reopened'} else {'model':'fisheye','projection':name,'fx':.55,'fy':.72,'direction':'undistort'}
                checks[name+'_actual_render_snapshot']=request.get('identity')==key and request.get('frame')==0 and preview_identity(request.get('project'),0)==key and all(candidate.get(k)==v for k,v in wanted.items())
                matched=[j for j in jobs if j['kind']=='frame-preview' and j['state']=='completed' and j.get('result',{}).get('url')==row['url']]
                checks[name+'_receipt_hash']=bool(matched) and identity(path)['sha256']==matched[-1]['result'].get('sha256')
                checks[name+'_verified_live_or_cached_snapshot']=key in requests or bool(key in prior_requests and matched and matched[-1]['result'].get('cached') is True)
                pixels=decode(path,timeout=budget(2.5,.8));pictures[name]=pixels;measurement=expected_picture(candidate,0,pixels)
                result.setdefault('independent_paused_pixels',{})[name]=measurement
                checks[name+'_independent_ray_and_alpha_pixels']=len(pixels)==WIDTH*HEIGHT*3 and measurement['mean_rgb_error']<3 and measurement['max_rgb_error']<8
                shutil.copyfile(path,output/('ENGINE_TEST_'+name+'.png'));snapshot_projects[name]=copy.deepcopy(request['project'])
            checks['required_actual_frames_observed']=set(pictures)==({'equidistant','equisolid','stereographic','orthographic','lensfun','reopened'} if operation=='author' else {'lensfun'})
            if operation=='author':
                for value in snapshot_projects.values():
                    for name in ('revision','updated_at'):value.pop(name,None)
                checks['save_reopen_preserves_full_project_except_metadata']=snapshot_projects['lensfun']==snapshot_projects['reopened']
                checks['save_reopen_preserves_every_pixel']=pictures['lensfun']==pictures['reopened']
                checks['no_unrequested_movie_download']=len(ui.get('downloads',[]))==0
            else:
                rendered=[j for j in jobs if j['kind']=='render' and j['state']=='completed' and j.get('result',{}).get('profile')==delivery]
                if len(rendered)!=1 or len(ui.get('downloads',[]))!=1:raise ValueError('Exactly one completed export and one actual download are required')
                row=ui['downloads'][0];target=Path(row.get('path','')).absolute();name=row.get('suggested_filename','')
                valid=target.name==name if transport=='Chromium' else bool(re.fullmatch(r'ENGINE_TEST_[A-Fa-f0-9-]{36}_'+re.escape(name),target.name))
                if not name or Path(name).name!=name or target.parent!=downloads or not valid or row.get('state')!='completed':raise ValueError('Actual download escaped its owned evidence directory')
                receipt=rendered[0]['result'];movie=store.project_dir(project['id'])/'exports'/receipt['filename'];actual=decode(target,timeout=budget(2.5,1));metadata=probe_media(target);result['media']=metadata
                checks['actual_download_matches_export_bytes']=identity(target)==identity(movie) and identity(movie)['sha256']==receipt['sha256']
                checks['every_exported_frame_decodes']=metadata['frames']==FRAMES and len(actual)==FRAMES*WIDTH*HEIGHT*3
                playback=ui.get('metrics',{}).get('playback',{});checks['native_decoder_plays_exact_export']=playback.get('url')==receipt['url'] and playback.get('time',0)>.06
                control=output/'codec-control';control.mkdir();lossless,encoded,_=codec_control(project,store.project_dir(project['id']),control,delivery,budget)
                checks['paused_frame_equals_lossless_movie']=pictures['lensfun']==lossless[:WIDTH*HEIGHT*3]
                checks['every_movie_frame_matches_separate_codec_control']=actual==encoded
                checks['render_preserves_original_editable_graph']=project['clips']==initial['clips'] and project['assets']==initial['assets']
            checks['actual_native_screenshot']=screenshot.is_file() and screenshot.stat().st_size>1000
        if fixture and store and project:
            checks['sentinel_project_unchanged']=identity(store.project_dir(fixture['sentinel_id'])/'project.json')==fixture['sentinel_identity']
            checks['original_owned_source_bytes_unchanged']=len(project['assets'])==1 and identity(store.project_dir(project['id'])/project['assets'][0]['path'])==fixture['source_identity']
            checks['native_helper_binary_unchanged']=identity(binary)==result['helper_identity']
    except Exception as error:
        result['error']=str(error)
        if isinstance(error,subprocess.CalledProcessError):result['process_error']=(error.stderr or b'').decode(errors='replace')[-1600:]
    finally:
        if server:server.shutdown();server.server_close()
        if thread:thread.join(timeout=.3)
        if store:
            store.shutdown()
            with store.lock:owned_jobs=copy.deepcopy(list(store.jobs.values()))
            checks['all_owned_jobs_terminal']=all(j['state'] not in {'queued','running'} for j in owned_jobs);write_json(output/'ENGINE_TEST_owned_jobs.json',owned_jobs)
        server_module.render_frame=old_render
        if requests:write_json(output/'ENGINE_TEST_frame_requests.json',requests)
        if prior_requests:write_json(output/'ENGINE_TEST_verified_prior_frames.json',prior_requests)
        if root and fixture and project:
            persisted=root/'workspace/projects'/fixture['project_id']/'project.json';result['saved_project_identity']=identity(persisted)
            (output/'ENGINE_TEST_saved_project.json').write_bytes(persisted.read_bytes())
        result['elapsed_seconds']=round(time.monotonic()-began,3);checks['foreground_phase_within18_seconds']=result['elapsed_seconds']<=18
        checks['runtime_web_acceptance_source_unchanged']=source_inventory()==result.get('source_before')
        result['artifacts']={p.relative_to(output).as_posix():identity(p) for p in sorted(output.rglob('*')) if p.is_file()}
        result['passed']=not result.get('error') and bool(checks) and all(checks.values())
        report=output/'ENGINE_TEST_lens_models_report.json';write_json(report,result)
        if result['passed'] and fixture:
            verified_frames={**prior_requests,**requests}
            if verified_frames:write_json(root/'verified-frame-requests.json',verified_frames)
            write_json(root/(operation+'-passed.json'),{'passed':True,'acceptance_id':fixture['acceptance_id'],'operation':operation,
                'saved_project_identity':result['saved_project_identity'],'source_inventory':before,'helper_identity':result['helper_identity'],'report_identity':identity(report),
                'verified_frames_identity':identity(root/'verified-frame-requests.json') if verified_frames else None})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--binary',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--operation',required=True,choices=PHASES);parser.add_argument('--fixture-workspace',required=True,type=Path);parser.add_argument('--expected-sources',required=True,type=Path)
    parser.add_argument('--profile',type=Path);parser.add_argument('--delivery',choices=('prores','h264'),default='prores');args=parser.parse_args()
    result=run(args.binary,args.output,args.operation,args.fixture_workspace,read_json(args.expected_sources),profile_file=args.profile,delivery=args.delivery)
    print(json.dumps({'passed':result['passed'],'operation':args.operation,'checks':len(result['checks']),'elapsed_seconds':result['elapsed_seconds'],'error':result.get('error'),'native_certified':result['native_certified']}));return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
