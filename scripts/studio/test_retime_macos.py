#!/usr/bin/env python3
"""Owned real-media speed-ramp acceptance, in independent <=18 s phases.

The identical ordinary-control script runs in WKWebView or explicit Chromium.
Only an actual macOS WKWebView invocation may report native certification.
"""
from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid

from server import Handler, Server, Store
from test_editing_ui_macos import read_helper_result
from test_multicam_sync_macos import identity, safe_directory, write_json, read_json, source_inventory as runtime_inventory
from test_otio_compositions_macos import foreground

HERE=Path(__file__).resolve().parent
KIND='cinematicum-owned-speed-ramp-v1'
PHASES=('prepare','author','playback','archive')


def source_inventory():
    result=runtime_inventory()
    for name in ('test_retime.py','test_retime_macos.py','test_retime_browser.cjs','macos/RetimeSmoke.js','test_otio_compositions_macos.py'):
        result[name]=identity(HERE/name)
    return dict(sorted(result.items()))


def source_signal(np, positions):
    """Independent continuous source PCM used before and after the nonlinear clock."""
    t=np.asarray(positions,dtype=np.float64)/48000
    return np.stack((.14*np.sin(2*np.pi*191*t),.14*np.sin(2*np.pi*307*t)+.025*np.sin(2*np.pi*73*t)),axis=-1)


def true_picture(np,texture,position):
    x=16+2*position;left=int(np.floor(x));fraction=x-left
    return np.rint(texture[16:80,left:left+96]*(1-fraction)+texture[16:80,left+1:left+97]*fraction).astype(np.uint8)


def make_fixture(root):
    import numpy as np
    from retime import capabilities
    runtime=capabilities()
    if not runtime.get('available'):raise ValueError(runtime.get('reason'))
    root=Path(root);root.mkdir();(root/'media').mkdir();(root/'truth').mkdir()
    rng=np.random.default_rng(652697)
    # Constant chroma keeps the native H.264 4:2:0 fixture's compression error
    # separate from the geometric interpolation being measured.
    gray=rng.integers(30,226,(112,192)).astype(np.float64)
    texture=np.stack((gray,gray+7,gray-9),axis=-1)
    texture=sum(np.roll(texture,(dy,dx),(0,1))*weight for dy,dx,weight in ((0,0,4),(1,0,2),(-1,0,2),(0,1,2),(0,-1,2),(1,1,1),(1,-1,1),(-1,1,1),(-1,-1,1)))/16
    np.save(root/'truth/texture.npy',texture,allow_pickle=False)
    pictures=np.stack([true_picture(np,texture,n) for n in range(24)])
    source=source_signal(np,np.arange(48000)).astype('<f4');(root/'truth/selected.f32').write_bytes(source.tobytes())
    other=np.stack((.09*np.sin(2*np.pi*659*np.arange(48000)/48000),.08*np.sin(2*np.pi*877*np.arange(48000)/48000)),axis=1).astype('<f4')
    (root/'truth/other.f32').write_bytes(other.tobytes())
    movie=root/'media/ENGINE_TEST_ramp_original.mov'
    command=[shutil.which('ffmpeg'),'-v','error','-nostdin','-y','-threads','1','-filter_threads','1',
        '-f','rawvideo','-pixel_format','rgb24','-video_size','96x64','-framerate','24','-i','pipe:0',
        '-f','f32le','-ar','48000','-ac','2','-i',str(root/'truth/other.f32'),
        '-f','f32le','-ar','48000','-ac','2','-i',str(root/'truth/selected.f32'),
        '-map','0:v','-map','1:a','-map','2:a','-c:v','libx264','-preset','ultrafast','-crf','8','-pix_fmt','yuv420p','-threads','1','-c:a','pcm_f32le',str(movie)]
    subprocess.run(command,input=pictures.tobytes(),capture_output=True,check=True,timeout=3)
    positions=4+.5*np.arange(12)+np.arange(12,dtype=float)**2/24
    expected=np.concatenate((np.zeros((3,64,96,3),np.uint8),np.stack([true_picture(np,texture,n) for n in positions])))
    (root/'truth/expected.rgb').write_bytes(expected.tobytes())
    # A literal quadratic, independent of the application's integral/worker.
    local=np.arange(24000,dtype=float)*24/48000
    pcm=source_signal(np,(4+.5*local+local*local/24)*48000/24)[:,::-1]*np.array([.45,.6])
    pcm=np.concatenate((np.zeros((6000,2)),pcm));np.save(root/'truth/expected-pcm.npy',pcm,allow_pickle=False)
    return {'frames':15,'ramp_frames':12,'sample_frames':30000,'source_positions':positions.tolist(),
        'probe_absolute_frame':9,'probe_pixel':expected[9,32,48].tolist(),'source_identity':identity(movie),
        'runtime':runtime,'selected_stream_index':2,'channels':[1,0],'gain':.6,'pan':.25}


def inspect_movie(movie,root):
    import numpy as np
    def decode(args):
        return subprocess.run([shutil.which('ffmpeg'),'-v','error','-nostdin','-threads','1','-filter_threads','1',*args],capture_output=True,check=True,timeout=3).stdout
    pixels=np.frombuffer(decode(['-i',str(movie),'-map','0:v:0','-pix_fmt','rgb24','-threads','1','-f','rawvideo','pipe:1']),np.uint8).reshape(-1,64,96,3)
    pcm=np.frombuffer(decode(['-i',str(movie),'-map','0:a:0','-f','s16le','pipe:1']),'<i2').reshape(-1,2)
    expected=np.fromfile(Path(root)/'truth/expected.rgb',np.uint8).reshape(-1,64,96,3)
    truth=np.load(Path(root)/'truth/expected-pcm.npy',allow_pickle=False)
    return {'frames':len(pixels),'sample_frames':len(pcm),'black_lead_max':int(np.max(pixels[:3])),
        'per_frame_interior_mae':np.mean(np.abs(pixels.astype(float)-expected.astype(float))[:,16:-16,16:-16],axis=(1,2,3)).tolist() if pixels.shape==expected.shape else None,
        'max_pcm_lsb_error':float(np.max(np.abs(pcm.astype(float)-truth*32768))) if pcm.shape==truth.shape else None,
        'silent_lead_exact':bool(np.all(pcm[:6000]==0))}


def run(binary,output,operation,fixture_workspace,expected_sources,*,transport='WKWebView'):
    began=time.monotonic();deadline=began+18;output=safe_directory(output,new=True)
    result={'kind':KIND,'operation':operation,'browser':transport,'passed':False,'checks':{},
        'native_certified':operation!='prepare' and transport=='WKWebView' and sys.platform=='darwin',
        'fixture':'SYNTHETIC ENGINE TEST — NOT PRODUCTION CONTENT'}
    checks=result['checks'];root=fixture=store=server=thread=project=None
    def budget(maximum,reserve=0):
        remaining=deadline-time.monotonic()-reserve
        if remaining<=.1:raise TimeoutError('The ramp phase exhausted its 18-second foreground budget')
        return min(maximum,remaining)
    try:
        if operation not in PHASES:raise ValueError('Unknown speed-ramp acceptance phase')
        before=source_inventory();result['source_before']=before
        if before!=expected_sources:raise ValueError('Runtime/web/acceptance source differs from the exact frozen inventory')
        checks['exact_frozen_runtime_web_and_acceptance_source']=True
        if operation=='prepare':
            root=Path(fixture_workspace).absolute()
            if root.exists() or any(p.is_symlink() for p in (root,*root.parents)):raise ValueError('Prepare requires a new explicit fixture directory')
            root.parent.mkdir(parents=True,exist_ok=True)
            code="import json,sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom test_retime_macos import make_fixture\nprint(json.dumps(make_fixture(Path(sys.argv[2]))))\n"
            made=foreground([sys.executable,'-I','-B','-c',code,HERE,root],budget(8,3))
            if made.returncode:raise RuntimeError('Actual H.264/PCM and pinned dense-flow preparation failed: '+made.stderr[-1800:])
            truth=json.loads(made.stdout);store=Store(root/'workspace')
            sentinel=store.new_project({'name':'ENGINE TEST ramp sentinel','width':96,'height':64,'fps':24})
            project=store.new_project({'name':'ENGINE TEST source-time ramp','width':96,'height':64,'fps':24})
            upload=root/'owned-upload.mov';shutil.copyfile(root/'media/ENGINE_TEST_ramp_original.mov',upload)
            asset=store.admit(project['id'],upload,'ENGINE_TEST_ramp_original.mov')
            project=store.get(project['id']);project['clips']=[{'id':'ramp_source','asset_id':asset['id'],'track':0,'start':3,'in':4,'duration':12,
                'volume':.6,'audio':{'stream_index':2,'channels':[1,0],'pan':.25}}]
            project=store.save(project['id'],project)
            fixture={'kind':KIND,'acceptance_id':uuid.uuid4().hex,'project_id':project['id'],'sentinel_id':sentinel['id'],
                'clip_id':'ramp_source','asset_id':asset['id'],'truth':truth,'truth_files':{p.name:identity(p) for p in (root/'truth').iterdir()}}
            write_json(root/'retime-fixture.json',fixture)
            checks['actual_pinned_dense_flow_operation_probe']=truth['runtime']['available'] and truth['runtime']['operation_probe']['median_displacement_error_pixels']<.2
            checks['real_h264_picture_and_two_distinct_stereo_pcm_streams']=len(project['assets'])==1 and len(asset['audio_streams'])==2 and all(s['codec']=='pcm_f32le' for s in asset['audio_streams'])
        else:
            root=safe_directory(fixture_workspace);fixture=read_json(root/'retime-fixture.json')
            if fixture.get('kind')!=KIND or not re.fullmatch('[a-f0-9]{32}',fixture.get('acceptance_id','')):raise ValueError('Wrong explicitly prepared acceptance fixture')
            if (root/(operation+'-passed.json')).exists():raise ValueError('Preserve completed phases; prepare a new fixture for repetition')
            prior=read_json(root/(PHASES[PHASES.index(operation)-1]+'-passed.json'))
            if prior.get('passed') is not True or prior.get('acceptance_id')!=fixture['acceptance_id'] or prior.get('source_inventory')!=before:raise ValueError('The prior phase does not certify this fixture and source')
            persisted=root/'workspace/projects'/fixture['project_id']/'project.json'
            if identity(persisted)!=prior['saved_project_identity']:raise ValueError('Saved project changed after the preceding phase')
            if identity(root/'media/ENGINE_TEST_ramp_original.mov')!=fixture['truth']['source_identity']:raise ValueError('Original fixture bytes changed')
            if {p.name:identity(p) for p in (root/'truth').iterdir()}!=fixture['truth_files']:raise ValueError('Independent original-pixel/sample oracle changed')
            store=Store(root/'workspace');project=store.get(fixture['project_id']);initial=copy.deepcopy(project)
            with store.lock:jobs_before=set(store.jobs)
            script=output/'ENGINE_TEST_retime.js';script.write_text((HERE/'macos/RetimeSmoke.js').read_text().replace('/* ENGINE_TEST_CONFIG */ {}',json.dumps({**fixture,'operation':operation})))
            result['executed_javascript_identity']=identity(script);result['helper_identity']=identity(binary)
            downloads=output/'native_downloads';downloads.mkdir()
            server=Server(0,store);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.025},daemon=True);thread.start()
            origin='http://127.0.0.1:'+str(server.server_port);screenshot=output/'ENGINE_TEST_retime.png'
            maximum=budget(14,2.5)
            process=foreground([Path(binary).resolve(),'--url',origin+'/','--output',screenshot,'--script',script,'--download-dir',downloads,'--timeout',round(maximum,2)],budget(maximum+.2,2.1))
            ui=read_helper_result(process);result['ui']=ui;result['helper_exit_code']=process.returncode;write_json(output/'ENGINE_TEST_browser_result.json',ui)
            checks['actual_shipped_controls_succeeded']=ui.get('passed') is True and process.returncode==0
            checks['no_uncaught_browser_or_download_errors']=not ui.get('page_errors') and not ui.get('download_errors')
            if not checks['actual_shipped_controls_succeeded']:raise ValueError(ui.get('error') or 'Actual speed-ramp controls failed')
            expected={'author':['real_speed_key_controls','one_undo_redo_applies_recipe','split_and_tail_trim_preserve_source_curve','save_switch_reopen_keeps_recipe_routing_and_gain'],
                'playback':['actual_interpolated_paused_picture','play_uses_actual_rendered_preview','rendered_picture_clock_and_nonzero_stereo_audio','actual_prores_export_and_download'],
                'archive':['actual_archive_download_and_file_upload','restored_new_identity_keeps_editable_ramps','restored_picture_audio_render_and_download']}[operation]
            checks.update({name:name in ui.get('steps',[]) for name in expected})
            project=store.get(fixture['project_id'])
            ordered=sorted(project['clips'],key=lambda c:c['start'])
            checks['two_saved_curve_windows_preserve_exact_split']=len(ordered)==2 and [c['duration'] for c in ordered]==[4,8] and [c['retime']['offset'] for c in ordered]==[0,4] and abs(ordered[1]['in']-(4+2+16/24))<1e-12
            checks['original_stream_channel_gain_and_pan_preserved']=all(c['audio']['stream_index']==2 and c['audio']['channels']==[1,0] and c['audio']['pan']==.25 and c['volume']==.6 for c in ordered)
            checks['all_original_source_media_unchanged']=len(project['assets'])==1 and identity(store.project_dir(project['id'])/project['assets'][0]['path'])==fixture['truth']['source_identity']
            with store.lock:jobs=[copy.deepcopy(j) for key,j in store.jobs.items() if key not in jobs_before]
            actual_downloads=[]
            for row in ui.get('downloads',[]):
                path=Path(row.get('path','')).absolute();name=row.get('suggested_filename','')
                valid=path.name==name if transport=='Chromium' else bool(re.fullmatch(r'ENGINE_TEST_[A-Fa-f0-9-]{36}_'+re.escape(name),path.name))
                if path.parent!=downloads or not valid or row.get('state')!='completed':raise ValueError('An actual download escaped its owned destination')
                actual_downloads.append((path,row))
            if operation!='author':
                renders=[j for j in jobs if j['kind']=='render' and j.get('result',{}).get('profile')=='prores']
                if len(renders)!=1 or renders[0]['state']!='completed':raise ValueError('Exactly one actual completed ProRes job is required')
                movies=[(p,r) for p,r in actual_downloads if p.suffix=='.mov']
                if len(movies)!=1:raise ValueError('Exactly one actual movie download is required')
                movie,row=movies[0];job=renders[0];rendered=store.project_dir(job['project_id'])/'exports'/job['result']['filename']
                checks['actual_download_matches_completed_render_bytes']=identity(movie)==identity(rendered) and identity(movie)['sha256']==job['result']['sha256']
                reports=job['result'].get('retime_reports',[]);result['retime_reports']=reports
                checks['real_flow_and_varispeed_engines_executed']=len(reports)==2 and all(r['runtime_operations_executed'] and r['picture']['flow_pairs']>0 and r['audio']['filter_taps']==64 and r['source_unchanged'] for r in reports)
                code="import json,sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom test_retime_macos import inspect_movie\nprint(json.dumps(inspect_movie(Path(sys.argv[2]),Path(sys.argv[3]))))\n"
                decoded=foreground([sys.executable,'-I','-B','-c',code,HERE,movie,root],budget(2.5,.45))
                if decoded.returncode:raise ValueError('Independent original-pixel/sample decode failed: '+decoded.stderr[-1200:])
                measure=json.loads(decoded.stdout);result['independent_movie']=measure
                checks['every_ramped_picture_matches_independent_translated_texture']=measure['frames']==15 and measure['black_lead_max']<=2 and measure['per_frame_interior_mae'] is not None and max(measure['per_frame_interior_mae'])<8
                checks['every_stereo_sample_matches_literal_quadratic_clock_and_routing']=measure['sample_frames']==30000 and measure['silent_lead_exact'] and measure['max_pcm_lsb_error'] is not None and measure['max_pcm_lsb_error']<=3
                checks['render_keeps_original_saved_authoring']=project['clips']==initial['clips'] and project['assets']==initial['assets']
                if operation=='archive':
                    archives=[p for p,r in actual_downloads if p.suffix=='.zip']
                    if len(archives)!=1:raise ValueError('Exactly one actual project archive download is required')
                    restored=store.get(ui['metrics']['restored_project_id'])
                    checks['archive_new_identity_preserves_curve_and_source_bytes']=restored['id']!=project['id'] and restored['clips']==project['clips'] and all(identity(store.project_dir(restored['id'])/a['path'])==identity(store.project_dir(project['id'])/a['path']) for a in restored['assets'])
            checks['actual_browser_snapshot']=screenshot.is_file() and screenshot.stat().st_size>1000
    except Exception as error:
        result['error']=str(error)
    finally:
        if server:server.shutdown();server.server_close()
        if thread:thread.join(timeout=.3)
        if store:
            store.shutdown()
            with store.lock:jobs=copy.deepcopy(list(store.jobs.values()))
            checks['all_owned_jobs_terminal']=all(j['state'] not in ('queued','running') for j in jobs)
            write_json(output/'ENGINE_TEST_owned_jobs.json',jobs)
        if root and fixture and project:
            persisted=root/'workspace/projects'/fixture['project_id']/'project.json';result['saved_project_identity']=identity(persisted)
            (output/'ENGINE_TEST_saved_project.json').write_bytes(persisted.read_bytes())
        result['elapsed_seconds']=round(time.monotonic()-began,3)
        checks['foreground_phase_within_18_seconds']=result['elapsed_seconds']<=18
        checks['runtime_web_and_acceptance_source_unchanged']=source_inventory()==result.get('source_before')
        result['passed']=not result.get('error') and bool(checks) and all(checks.values())
        report=output/'ENGINE_TEST_retime_report.json';write_json(report,result)
        if result['passed'] and fixture:
            write_json(root/(operation+'-passed.json'),{'passed':True,'acceptance_id':fixture['acceptance_id'],'operation':operation,'saved_project_identity':result['saved_project_identity'],'source_inventory':before,'report_identity':identity(report)})
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--binary',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--operation',required=True,choices=PHASES);parser.add_argument('--fixture-workspace',required=True,type=Path);parser.add_argument('--expected-sources',required=True,type=Path)
    args=parser.parse_args();result=run(args.binary,args.output,args.operation,args.fixture_workspace,read_json(args.expected_sources))
    print(json.dumps({'passed':result['passed'],'operation':args.operation,'checks':len(result['checks']),'elapsed_seconds':result['elapsed_seconds'],'error':result.get('error'),'native_certified':result['native_certified']}))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
