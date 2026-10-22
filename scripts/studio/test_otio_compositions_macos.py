#!/usr/bin/env python3
"""Real OTIO import/edit/export/archive acceptance, in <=18-second phases.

No Mac result is inferred from Chromium. Each phase owns and joins its server,
browser process group, and media jobs. Repeated attempts require a fresh fixture.
"""
from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import wave

from server import Handler, Server, Store
from test_editing_ui_macos import read_helper_result
from test_multicam_sync_macos import identity, safe_directory, write_json, read_json, source_inventory as sync_inventory

HERE=Path(__file__).resolve().parent
KIND='cinematicum-owned-otio-composition-v1'
PHASES=('prepare','author','render','archive')


def source_inventory():
    result=sync_inventory()
    for name in ('test_otio_compositions.py','test_otio_compositions_macos.py','test_otio_compositions_browser.cjs','macos/OtioCompositionsSmoke.js'):
        result[name]=identity(HERE/name)
    return dict(sorted(result.items()))


def foreground(argv,timeout):
    process=subprocess.Popen(list(map(str,argv)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    try:
        stdout,stderr=process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGTERM)
        try:stdout,stderr=process.communicate(timeout=.3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);stdout,stderr=process.communicate(timeout=.2)
        raise TimeoutError('The owned acceptance process exceeded its foreground deadline')
    return subprocess.CompletedProcess(argv,process.returncode,stdout,stderr)


def make_fixture(root):
    import numpy as np
    import opentimelineio as otio
    from interchange import _item,_range,_rt
    from timebase import parse_rate
    root=Path(root);root.mkdir();(root/'media').mkdir();(root/'truth').mkdir()
    n=np.arange(192000);sources={};rate=parse_rate(24)
    for name,channel,offset in (('red',0,1),('blue',2,997)):
        pcm=np.stack(((n*37+offset)%12001-6000,(n*59+offset*3)%10007-5003),axis=1).astype('<i2')
        sources[name]=pcm;(root/'truth'/f'{name}.s16le').write_bytes(pcm.tobytes())
        wav=root/'truth'/f'{name}.wav'
        with wave.open(str(wav),'wb') as handle:
            handle.setnchannels(2);handle.setsampwidth(2);handle.setframerate(48000);handle.writeframes(pcm.tobytes())
        pixels=np.zeros((96,48,64,3),dtype=np.uint8);pixels[:,:,:,channel]=180
        for bit in range(7):pixels[:,32:48,bit*8:(bit+1)*8,:]=np.where((np.arange(96)>>bit)&1,240,8)[:,None,None,None]
        command=[shutil.which('ffmpeg'),'-v','error','-nostdin','-y','-threads','1','-filter_complex_threads','1',
            '-f','rawvideo','-pixel_format','rgb24','-video_size','64x48','-framerate','24','-i','pipe:0','-i',str(wav),
            '-c:v','libx264','-preset','ultrafast','-crf','10','-pix_fmt','yuv420p','-threads','1','-c:a','pcm_s16le','-shortest',str(root/'media'/f'ENGINE_TEST_{name}.mov')]
        subprocess.run(command,input=pixels.tobytes(),check=True,capture_output=True,timeout=3)
    def clip(name,start,duration,reverse=False):
        ref={'OTIO_SCHEMA':'ExternalReference.1','name':'ENGINE TEST '+name,'metadata':{},'target_url':'ENGINE_TEST_'+name+'.mov',
            'available_range':_range(0,96,rate),'available_image_bounds':None}
        effects=[{'OTIO_SCHEMA':'LinearTimeWarp.1','name':'Reverse source window','effect_name':'LinearTimeWarp','metadata':{},'enabled':True,'time_scalar':-1}] if reverse else []
        return _item('Clip.2',name,source_range=_range(start,duration,rate),effects=effects,media_references={'DEFAULT_MEDIA':ref},active_media_reference_key='DEFAULT_MEDIA')
    transition={'OTIO_SCHEMA':'Transition.1','name':'ENGINE TEST linear dissolve','metadata':{},'transition_type':'SMPTE_Dissolve','in_offset':_rt(2,rate),'out_offset':_rt(2,rate)}
    children=[clip('red',8,12),transition,clip('blue',20,12),clip('red',32,8,True)]
    tracks=[_item('Track.1','ENGINE TEST '+kind,kind=kind,children=copy.deepcopy(children),source_range=_range(1,30,rate)) for kind in ('Video','Audio')]
    document={'OTIO_SCHEMA':'Timeline.1','name':'ENGINE TEST OTIO imported composition','metadata':{},'global_start_time':_rt(0,rate),
        'tracks':_item('Stack.1','Trimmed master',source_range=_range(1,28,rate),children=tracks)}
    official=otio.adapters.read_from_string(json.dumps(document),'otio_json')
    if official.duration().value!=28:raise ValueError('Upstream OTIO disagrees with fixture duration')
    raw=otio.adapters.write_to_string(official,'otio_json');(root/'ENGINE_TEST_timeline.otio').write_text(raw)
    weight=np.arange(8000)[:,None]/8000
    sound=np.concatenate((sources['red'][16000:36000],np.rint(sources['red'][36000:44000]*(1-weight)+sources['blue'][36000:44000]*weight).astype('<i2'),sources['blue'][44000:64000],sources['red'][64000:80000][::-1]))[4000:60000]
    (root/'truth/expected.s16le').write_bytes(sound.tobytes())
    return {'upstream_otio_version':otio.__version__,'frames':28,'sample_frames':56000,'source_counters':list(range(10,32))+list(range(39,33,-1)),
        'media':[{'name':name,'path':'media/ENGINE_TEST_'+name+'.mov','identity':identity(root/'media'/('ENGINE_TEST_'+name+'.mov'))} for name in ('red','blue')]}


def inspect_movie(movie,root):
    import numpy as np
    def decode(args):
        return subprocess.run([shutil.which('ffmpeg'),'-v','error','-nostdin','-threads','1','-filter_threads','1',*args],check=True,capture_output=True,timeout=3).stdout
    pixels=np.frombuffer(decode(['-i',str(movie),'-map','0:v:0','-pix_fmt','rgb24','-threads','1','-f','rawvideo','pipe:1']),np.uint8).reshape(-1,48,64,3)
    pcm=np.frombuffer(decode(['-i',str(movie),'-map','0:a:0','-f','s16le','pipe:1']),'<i2').reshape(-1,2)
    expected=np.fromfile(Path(root)/'truth/expected.s16le','<i2').reshape(-1,2)
    counters=sum(((pixels[:,40,bit*8+4,:].mean(axis=1)>120).astype(int)<<bit) for bit in range(7))
    target=np.array([180,0,0])[:,None]*(1-np.arange(4)/4)+np.array([0,0,180])[:,None]*(np.arange(4)/4)
    return {'frames':len(pixels),'sample_frames':len(pcm),'source_counters':counters.tolist(),
        'max_pcm_lsb_error':int(np.max(np.abs(pcm.astype(int)-expected.astype(int)))) if pcm.shape==expected.shape else None,
        'dissolve_rgb_max_error':float(np.max(np.abs(pixels[8:12,20,32,:].astype(float)-target.T))),
        'pure_picture_sources_correct':bool((pixels[:8,20,32,0]>165).all() and (pixels[12:22,20,32,2]>165).all() and (pixels[22:,20,32,0]>165).all())}


def run(binary,output,operation,fixture_workspace,expected_sources,*,transport='WKWebView'):
    began=time.monotonic();deadline=began+18;output=safe_directory(output,new=True)
    result={'kind':KIND,'operation':operation,'browser':transport,'passed':False,'checks':{},
        'native_certified':operation!='prepare' and transport=='WKWebView' and sys.platform=='darwin','fixture':'SYNTHETIC ENGINE TEST — NOT PRODUCTION CONTENT'}
    checks=result['checks'];root=fixture=store=server=thread=project=None
    def budget(maximum,reserve=0):
        remaining=deadline-time.monotonic()-reserve
        if remaining<=.1:raise TimeoutError('The OTIO phase exhausted its 18-second foreground budget')
        return min(maximum,remaining)
    try:
        if operation not in PHASES:raise ValueError('Unknown OTIO acceptance phase')
        before=source_inventory();result['source_before']=before
        if before!=expected_sources:raise ValueError('Runtime/web/acceptance source differs from the explicit frozen inventory')
        checks['exact_frozen_runtime_web_and_acceptance_source']=True
        if operation=='prepare':
            root=Path(fixture_workspace).absolute()
            if root.exists() or any(p.is_symlink() for p in (root,*root.parents)):raise ValueError('Prepare requires a new explicit fixture directory')
            root.parent.mkdir(parents=True,exist_ok=True)
            code="import json,sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom test_otio_compositions_macos import make_fixture\nprint(json.dumps(make_fixture(Path(sys.argv[2]))))\n"
            made=foreground([sys.executable,'-I','-B','-c',code,HERE,root],budget(8,3))
            if made.returncode:raise RuntimeError('Actual H.264/PCM and upstream OTIO preparation failed: '+made.stderr[-1600:])
            truth=json.loads(made.stdout);store=Store(root/'workspace')
            sentinel=store.new_project({'name':'ENGINE TEST OTIO sentinel','width':64,'height':48,'fps':24})
            project=store.new_project({'name':'ENGINE TEST OTIO initial cut','width':64,'height':48,'fps':24})
            for row in truth['media']:
                upload=root/('owned-upload-'+Path(row['path']).name);shutil.copyfile(root/row['path'],upload)
                asset=store.admit(project['id'],upload,Path(row['path']).name);row['asset_id']=asset['id']
            project=store.get(project['id']);project['clips']=[{'id':'original_cut','asset_id':truth['media'][0]['asset_id'],'track':0,'start':0,'in':0,'duration':8}]
            project=store.save(project['id'],project)
            fixture={'kind':KIND,'acceptance_id':uuid.uuid4().hex,'project_id':project['id'],'sentinel_id':sentinel['id'],
                'original_clip_id':'original_cut','truth':truth,'document':identity(root/'ENGINE_TEST_timeline.otio'),
                'truth_files':{p.name:identity(p) for p in (root/'truth').iterdir()}}
            write_json(root/'otio-fixture.json',fixture)
            checks['two_actual_h264_sources_and_lossless_stereo_pcm']=len(project['assets'])==2 and all(a['audio_sample_rate']==48000 and a['audio_channels']==2 for a in project['assets'])
            checks['actual_upstream_otio_18_fixture_duration']=truth['upstream_otio_version'] in ('0.18.0','0.18.1') and truth['frames']==28
            result['upstream_otio_version']=truth['upstream_otio_version']
        else:
            root=safe_directory(fixture_workspace);fixture=read_json(root/'otio-fixture.json')
            if fixture.get('kind')!=KIND or not re.fullmatch('[a-f0-9]{32}',fixture.get('acceptance_id','')):raise ValueError('Wrong explicitly prepared acceptance fixture')
            if (root/(operation+'-passed.json')).exists():raise ValueError('Preserve the completed phase; prepare a new fixture for repetition')
            prior_path=root/(PHASES[PHASES.index(operation)-1]+'-passed.json');prior=read_json(prior_path)
            if prior.get('passed') is not True or prior.get('acceptance_id')!=fixture['acceptance_id'] or prior.get('source_inventory')!=before:raise ValueError('The prior phase does not certify this fixture and source')
            persisted=root/'workspace/projects'/fixture['project_id']/'project.json'
            if identity(persisted)!=prior['saved_project_identity']:raise ValueError('Saved project changed after the preceding phase')
            if identity(root/'ENGINE_TEST_timeline.otio')!=fixture['document'] or any(identity(root/row['path'])!=row['identity'] for row in fixture['truth']['media']):raise ValueError('Original source fixture bytes changed')
            if {p.name:identity(p) for p in (root/'truth').iterdir()}!=fixture['truth_files']:raise ValueError('Independent PCM oracle changed')
            store=Store(root/'workspace');project=store.get(fixture['project_id']);initial=copy.deepcopy(project)
            with store.lock:jobs_before=set(store.jobs)
            script=output/'ENGINE_TEST_otio_compositions.js';script.write_text((HERE/'macos/OtioCompositionsSmoke.js').read_text().replace('/* ENGINE_TEST_CONFIG */ {}',json.dumps({**fixture,'operation':operation})))
            result['executed_javascript_identity']=identity(script);result['helper_identity']=identity(binary)
            downloads=output/'native_downloads';downloads.mkdir()
            class FixtureHandler(Handler):
                def dispatch_get(self):
                    if self.path=='/ENGINE_TEST_timeline.otio':return self.file(root/'ENGINE_TEST_timeline.otio')
                    return super().dispatch_get()
            server=Server(0,store);server.RequestHandlerClass=FixtureHandler
            thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.025},daemon=True);thread.start()
            origin='http://127.0.0.1:'+str(server.server_port);screenshot=output/'ENGINE_TEST_otio_compositions.png'
            maximum=budget(14,2.5)
            process=foreground([Path(binary).resolve(),'--url',origin+'/','--output',screenshot,'--script',script,'--download-dir',downloads,'--timeout',round(maximum,2)],budget(maximum+.2,2.1))
            ui=read_helper_result(process);result['ui']=ui;result['helper_exit_code']=process.returncode;write_json(output/'ENGINE_TEST_browser_result.json',ui)
            checks['actual_shipped_controls_succeeded']=ui.get('passed') is True and process.returncode==0
            checks['no_uncaught_browser_or_download_errors']=not ui.get('page_errors') and not ui.get('download_errors')
            if not checks['actual_shipped_controls_succeeded']:raise ValueError(ui.get('error') or 'Actual OTIO controls failed')
            expected={
                'author':['actual_public_file_relink_review_without_mutation','one_undo_redo_for_composition_import','save_switch_reopen_keeps_editable_dissolve_and_reverse','actual_otio_download_private_roundtrip_review'],
                'render':['reopened_real_nested_timeline','actual_processed_transition_frame','actual_prores_export_and_download'],
                'archive':['actual_archive_download_and_file_upload','new_restored_identity_preserves_original','restored_nested_picture_audio_render_and_download'],
            }[operation]
            checks.update({name:name in ui.get('steps',[]) for name in expected})
            project=store.get(fixture['project_id'])
            checks['saved_source_clips_replaced_once_with_trimmed_composition']=bool(project['sequence_duration']==28 and len(project['clips'])==1 and project['clips'][0]['duration']==28 and project['clips'][0].get('sequence_id'))
            checks['two_editable_dissolves_and_reverse_source_windows_preserved']=sum(bool(s.get('otio_dissolve')) for s in project['sequences'])==2 and sum(c.get('reverse',False) for s in project['sequences'] for c in s['clips'])==2
            checks['all_project_original_media_unchanged']=all(identity(store.project_dir(project['id'])/a['path'])==next(row['identity'] for row in fixture['truth']['media'] if row['asset_id']==a['id']) for a in project['assets']) and len(project['assets'])==2
            with store.lock:jobs=[copy.deepcopy(j) for key,j in store.jobs.items() if key not in jobs_before]
            actual_downloads=[]
            for row in ui.get('downloads',[]):
                path=Path(row.get('path','')).absolute();name=row.get('suggested_filename','')
                valid=path.name==name if transport=='Chromium' else bool(re.fullmatch(r'ENGINE_TEST_[A-Fa-f0-9-]{36}_'+re.escape(name),path.name))
                if path.parent!=downloads or not valid or row.get('state')!='completed':raise ValueError('An actual download escaped its owned destination')
                actual_downloads.append((path,row))
            if operation=='author':
                if len(actual_downloads)!=1 or actual_downloads[0][0].suffix!='.otio':raise ValueError('Exactly one real OTIO download is required')
                path,row=actual_downloads[0];original=store.project_dir(project['id'])/'exports'/row['suggested_filename']
                checks['actual_otio_download_matches_owned_export_bytes']=identity(path)==identity(original)
                document=read_json(path)
                checks['download_contains_exact_saved_authoring_and_bound_source_identity']=document['metadata']['cinematicum']['project']['clips']==project['clips'] and set(document['metadata']['cinematicum']['asset_sha256'].values())=={r['identity']['sha256'] for r in fixture['truth']['media']}
            else:
                renders=[j for j in jobs if j['kind']=='render']
                if len(renders)!=1 or renders[0]['state']!='completed' or renders[0]['result']['profile']!='prores':raise ValueError('Exactly one real completed ProRes job is required')
                movies=[(p,r) for p,r in actual_downloads if p.suffix=='.mov']
                if len(movies)!=1:raise ValueError('Exactly one actual movie download is required')
                movie,row=movies[0];job=renders[0]
                rendered=store.project_dir(job['project_id'])/'exports'/job['result']['filename']
                checks['actual_movie_download_matches_completed_job_bytes']=identity(movie)==identity(rendered) and identity(movie)['sha256']==job['result']['sha256']
                code="import json,sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom test_otio_compositions_macos import inspect_movie\nprint(json.dumps(inspect_movie(Path(sys.argv[2]),Path(sys.argv[3]))))\n"
                decoded=foreground([sys.executable,'-I','-B','-c',code,HERE,movie,root],budget(2.3,.5))
                if decoded.returncode:raise ValueError('Independent original PCM/frame decode failed: '+decoded.stderr[-1200:])
                measurement=json.loads(decoded.stdout);result['independent_movie']=measurement
                checks['every_decoded_source_frame_and_trim_reverse_boundary_correct']=measurement['frames']==28 and measurement['source_counters']==fixture['truth']['source_counters'] and measurement['pure_picture_sources_correct']
                checks['linear_dissolve_pixels_match_independent_original_sources']=measurement['dissolve_rgb_max_error']<=6
                checks['every_stereo_sample_preserves_trim_dissolve_and_reverse']=measurement['sample_frames']==56000 and measurement['max_pcm_lsb_error']<=1
                checks['render_and_archive_preserve_original_saved_edit']=project['clips']==initial['clips'] and project['sequences']==initial['sequences']
                if operation=='archive':
                    archives=[(p,r) for p,r in actual_downloads if p.suffix=='.zip']
                    if len(archives)!=1:raise ValueError('Exactly one actual project archive download is required')
                    restored=store.get(ui['metrics']['restored_project_id'])
                    checks['restored_new_identity_keeps_all_sequence_operators_and_media']=restored['id']!=project['id'] and restored['clips']==project['clips'] and restored['sequences']==project['sequences'] and all(identity(store.project_dir(restored['id'])/a['path'])==identity(store.project_dir(project['id'])/a['path']) for a in restored['assets'])
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
            checks['original_sources_and_independent_pcm_truth_unchanged']=identity(root/'ENGINE_TEST_timeline.otio')==fixture['document'] and all(identity(root/r['path'])==r['identity'] for r in fixture['truth']['media']) and {p.name:identity(p) for p in (root/'truth').iterdir()}==fixture['truth_files']
        result['source_after']=source_inventory();checks['source_unchanged_during_actual_phase']=result.get('source_before')==result['source_after']
    result['elapsed_seconds']=round(time.monotonic()-began,3);checks['phase_within_18_second_foreground_bound']=result['elapsed_seconds']<18
    result['passed']=bool(checks) and all(checks.values()) and 'error' not in result
    if not result['passed'] and 'error' not in result:result['error']='Failed checks: '+', '.join(k for k,v in checks.items() if not v)
    report=output/'ENGINE_TEST_otio_compositions_report.json';write_json(report,result)
    if result['passed']:write_json(root/(operation+'-passed.json'),{'passed':True,'acceptance_id':fixture['acceptance_id'],'operation':operation,'saved_project_identity':result['saved_project_identity'],'source_inventory':before,'report_identity':identity(report)})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--operation',choices=PHASES,required=True);parser.add_argument('--fixture-workspace',type=Path,required=True)
    parser.add_argument('--source-manifest',type=Path,required=True);args=parser.parse_args()
    if sys.platform!='darwin':
        print(json.dumps({'passed':False,'reason':'Actual macOS WKWebView required; browser results cannot certify native.'}));return 1
    result=run(args.binary,args.output,args.operation,args.fixture_workspace,read_json(args.source_manifest))
    print(json.dumps({'passed':result['passed'],'operation':args.operation,'checks':result['checks'],'elapsed_seconds':result['elapsed_seconds'],'error':result.get('error')}))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
