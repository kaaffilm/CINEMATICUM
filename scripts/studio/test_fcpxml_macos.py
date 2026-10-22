#!/usr/bin/env python3
"""Owned FCPXML prepare/import/render acceptance in <=18-second phases.

The XML and source-picture/PCM oracle come from the hand-authored focused
fixture, never from the exporter. Native decoding requires the existing
WKWebView helper; the explicit Chromium adapter reports that exclusion.
"""
from __future__ import annotations

import argparse
import base64
import copy
from fractions import Fraction
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET

import server as server_module
from server import Server, Store
from frame_preview import preview_identity
from test_editing_ui_macos import read_helper_result
from test_multicam_sync_macos import identity, safe_directory, write_json, read_json, source_inventory as common_inventory
from test_otio_compositions_macos import foreground

HERE=Path(__file__).resolve().parent
KIND='cinematicum-owned-fcpxml-native-v1'
PHASES=('prepare','author','render')


def source_inventory():
    result=common_inventory()
    for name in ('fcpxml.py','test_fcpxml.py','test_fcpxml_macos.py','test_fcpxml_native_browser.cjs',
                 'test_otio_compositions_macos.py','test_retime_browser.cjs','macos/FcpxmlSmoke.js'):
        result[name]=identity(HERE/name)
    return dict(sorted(result.items()))


def make_fixture(root):
    """Generate actual original media and independently retained truth files."""
    from test_fcpxml import create_fixture,fixture_xml,fixture_expectations,RATE,WIDTH,HEIGHT,MAPPING,stamp,ORIGIN,COMPOUND_ORIGIN
    root=Path(root);root.mkdir();(root/'truth').mkdir()
    base=create_fixture(root/'source-fixture')
    xml=fixture_xml();(root/'truth/ENGINE_TEST_timeline.fcpxml').write_text(xml,encoding='utf-8')
    frames,channels,pcm=fixture_expectations()
    (root/'truth/expected.s16le').write_bytes(pcm.tobytes())
    source=ET.fromstring(xml);resources={node.get('id'):node for node in source.findall('resources/asset')}
    map_node=source.find('.//project/sequence/spine/asset-clip/timeMap')
    if map_node is None:raise ValueError('The independent fixture must include a forward time map')
    def exact(value):
        if not value.endswith('s'):raise ValueError('Fixture time must be exact seconds')
        return Fraction(value[:-1])
    points=list(map_node);speed=float((exact(points[-1].get('value'))-exact(points[0].get('value')))/(exact(points[-1].get('time'))-exact(points[0].get('time'))))
    preview=6;pixel=[0,0,0];pixel[int(channels[preview])]=80+int(frames[preview])
    expected={'frames':len(frames),'sample_frames':len(pcm),'source_counters':frames.tolist(),'source_channels':channels.tolist(),
              'width':WIDTH,'height':HEIGHT,'frame_rate':RATE.as_dict(),'top_level_clips':5,'forward_speed':speed,
              'preview_frame':preview,'preview_x':20,'preview_y':8,'preview_rgb':pixel,'preview_tolerance':4,
              'sequence_origin':stamp(ORIGIN),'compound_origin':stamp(COMPOUND_ORIGIN)}
    write_json(root/'truth/expected.json',expected)
    media=[]
    for reference,ident in MAPPING.items():
        asset=next(asset for asset in base['assets'] if asset['id']==ident)
        path=Path('source-fixture')/asset['path']
        media.append({'reference_id':reference,'reference_label':resources[reference].get('name'),'path':path.as_posix(),
                      'identity':identity(root/path),'fixture_asset_id':ident})
    return {'expected':expected,'media':media,'imported_name':source.find('project').get('name')}


def inspect_movie(path,root):
    import numpy as np
    from test_fcpxml import decode_movie,picture_counters
    pictures,pcm=decode_movie(path);root=Path(root);truth=read_json(root/'truth/expected.json')
    expected=np.fromfile(root/'truth/expected.s16le',dtype='<i2').reshape(-1,2)
    frames=np.asarray(truth['source_counters']);channels=np.asarray(truth['source_channels'])
    colors=np.zeros((len(frames),3),dtype=float);colors[np.arange(len(frames)),channels]=80+frames
    return {'frames':len(pictures),'sample_frames':len(pcm),'source_counters':picture_counters(pictures).tolist(),
            'source_channels':pictures[:,8,20,:].argmax(axis=1).tolist(),
            'source_color_max_error':float(np.max(np.abs(pictures[:,8,20,:].astype(float)-colors))) if len(pictures)==len(frames) else None,
            'max_pcm_lsb_error':int(np.max(np.abs(pcm.astype(np.int32)-expected.astype(np.int32)))) if pcm.shape==expected.shape else None,
            'every_pcm_sample_identical':bool(np.array_equal(pcm,expected))}


def check_edit(project,fixture):
    """Compare persisted native authoring with the independent XML contract."""
    from editorial import sequence_views
    expected=fixture['expected'];media={row['fixture_asset_id']:row['asset_id'] for row in fixture['media']}
    clips=project['clips'];picture=[clip for clip in clips if clip['track']>=0]
    first=next((clip for clip in picture if clip.get('asset_id')==media['red'] and clip['start']==0),{})
    overlay=next((clip for clip in picture if clip.get('asset_id')==media['blue'] and clip['start']==4),{})
    sound=next((clip for clip in clips if clip['track']<0),{})
    nested=next((clip for clip in picture if clip.get('sequence_id')),{});child=sequence_views(project).get(nested.get('sequence_id'),{})
    forward=next((clip for clip in picture if clip['start']==32),{})
    child_picture=next((clip for clip in child.get('clips',[]) if clip.get('asset_id')==media['red'] and clip['track']>=0),{})
    child_overlay=next((clip for clip in child.get('clips',[]) if clip.get('asset_id')==media['blue']),{})
    child_sound=next((clip for clip in child.get('clips',[]) if clip['track']<0),{})
    origins=project.get('settings',{}).get('fcpxml',{}).get('sequence_origins',{})
    prior=next((sequence for sequence in project.get('sequences',[]) if any(clip.get('id')==fixture['original_clip_id'] for clip in sequence.get('clips',[]))),{})
    return {
        'exact_rational_clock_canvas_and_extent':project.get('frame_rate')==expected['frame_rate'] and (project['width'],project['height'],project['sequence_duration'])==(expected['width'],expected['height'],expected['frames']),
        'five_public_items_remain_editable':len(clips)==5,
        'primary_source_origin_and_trim':(first.get('in'),first.get('duration'),first.get('volume'))==(8,16,0),
        'connected_picture_source_and_parent_clock':(overlay.get('in'),overlay.get('duration'),overlay.get('volume'))==(20,6,0) and overlay.get('track',-1)>first.get('track',100),
        'independent_audio_source_trim_and_gain':(sound.get('asset_id'),sound.get('start'),sound.get('in'),sound.get('duration'),sound.get('volume'))==(media['red'],0,8,16,.5),
        'real_compound_reference_and_trim':(nested.get('start'),nested.get('in'),nested.get('duration'),nested.get('volume'),child.get('sequence_duration'))==(16,4,16,.25,32),
        'compound_contains_three_editable_items':len(child.get('clips',[]))==3,
        'compound_primary_source_origin':(child_picture.get('start'),child_picture.get('in'),child_picture.get('duration'),child_picture.get('volume'))==(0,32,32,0),
        'compound_connected_parent_clock':(child_overlay.get('start'),child_overlay.get('in'),child_overlay.get('duration'),child_overlay.get('volume'))==(10,40,8,0),
        'compound_independent_audio':(child_sound.get('start'),child_sound.get('in'),child_sound.get('duration'),child_sound.get('volume'))==(0,32,32,1),
        'forward_time_map_source_window':(forward.get('in'),forward.get('duration'),forward.get('speed'),forward.get('reverse'),forward.get('volume'))==(56,8,expected['forward_speed'],False,0),
        'nonzero_sequence_and_compound_origins_preserved':origins.get(project.get('sequence_id'),{}).get('tcStart')==expected['sequence_origin'] and origins.get(nested.get('sequence_id'),{}).get('tcStart')==expected['compound_origin'],
        'original_sequence_preserved_in_library':prior.get('clips')==fixture['original_clips'],
        'document_provenance_matches_actual_input':all(clip.get('fcpxml',{}).get('document_sha256')==fixture['document']['sha256'] for clip in clips+child.get('clips',[])),
    }


def run(binary,output,operation,fixture_workspace,expected_sources,*,transport='WKWebView'):
    began=time.monotonic();deadline=began+18;output=safe_directory(output,new=True)
    result={'kind':KIND,'operation':operation,'browser':transport,'passed':False,'checks':{},
            'native_certified':operation!='prepare' and transport=='WKWebView' and sys.platform=='darwin',
            'scope':'Actual shipped FCPXML file/relink/review/apply/undo/save/reopen/export controls and exact owned downloads. No physical chooser, installed launcher or external Final Cut Pro renderer claim. Native ProRes decoding uses a separately labeled test video element.',
            'fixture':'SYNTHETIC ENGINE TEST — NOT PRODUCTION CONTENT'}
    checks=result['checks'];root=fixture=store=server=thread=project=None;requests={};old_render=server_module.render_frame
    def budget(maximum,reserve=0):
        remaining=deadline-time.monotonic()-reserve
        if remaining<=.1:raise TimeoutError('The FCPXML phase exhausted its18-second foreground budget')
        return min(maximum,remaining)
    def observe(snapshot,directory,frame,output_path,*args,**kwargs):
        requests[Path(output_path).stem]={'project':copy.deepcopy(snapshot),'frame':frame,'identity':preview_identity(snapshot,frame)}
        return old_render(snapshot,directory,frame,output_path,*args,**kwargs)
    try:
        if operation not in PHASES:raise ValueError('Unsupported FCPXML phase')
        before=source_inventory();result['source_before']=before;result['helper_identity']=identity(binary)
        if before!=expected_sources:raise ValueError('Runtime/web/acceptance source differs from the exact frozen inventory')
        checks['exact_frozen_runtime_web_acceptance_source']=True
        if operation=='prepare':
            root=Path(fixture_workspace).absolute()
            if root.exists() or any(path.is_symlink() for path in (root,*root.parents)):raise ValueError('Prepare requires a new explicit fixture directory')
            root.parent.mkdir(parents=True,exist_ok=True)
            code="import json,sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom test_fcpxml_macos import make_fixture\nprint(json.dumps(make_fixture(Path(sys.argv[2]))))\n"
            made=foreground([sys.executable,'-I','-B','-c',code,HERE,root],budget(8,3))
            if made.returncode:raise RuntimeError('Actual independent FCPXML fixture preparation failed: '+made.stderr[-1600:])
            truth=json.loads(made.stdout);store=Store(root/'workspace');properties={'width':truth['expected']['width'],'height':truth['expected']['height'],'frame_rate':truth['expected']['frame_rate']}
            sentinel=store.new_project({**properties,'name':'ENGINE TEST FCPXML sentinel'})
            project=store.new_project({**properties,'name':'ENGINE TEST FCPXML initial cut'})
            for row in truth['media']:
                upload=root/('owned-upload-'+Path(row['path']).name);shutil.copyfile(root/row['path'],upload)
                asset=store.admit(project['id'],upload,'ENGINE TEST '+row['fixture_asset_id']+Path(row['path']).suffix);row['asset_id']=asset['id']
            project=store.get(project['id']);project['clips']=[{'id':'original_cut','asset_id':truth['media'][0]['asset_id'],'track':0,'start':0,'in':0,'duration':8}];project=store.save(project['id'],project)
            fixture={'kind':KIND,'acceptance_id':uuid.uuid4().hex,'project_id':project['id'],'initial_name':project['name'],
                     'sentinel_id':sentinel['id'],'sentinel_name':sentinel['name'],'sentinel_identity':identity(store.project_dir(sentinel['id'])/'project.json'),
                     'original_clip_id':'original_cut','original_clips':copy.deepcopy(project['clips']),'helper_identity':result['helper_identity'],
                     'document':identity(root/'truth/ENGINE_TEST_timeline.fcpxml'),'truth_files':{path.name:identity(path) for path in (root/'truth').iterdir()},**truth}
            write_json(root/'fcpxml-fixture.json',fixture)
            shutil.copyfile(root/'truth/ENGINE_TEST_timeline.fcpxml',output/'ENGINE_TEST_input.fcpxml')
            checks['retained_input_xml_matches_exact_fixture_bytes']=identity(output/'ENGINE_TEST_input.fcpxml')==fixture['document']
            checks['two_actual_lossless_picture_and_stereo_pcm_sources']=len(project['assets'])==2 and all(asset['audio_channels']==2 and asset['audio_sample_rate']==48000 and asset['fps']=='30000/1001' for asset in project['assets'])
            checks['hand_authored_public_xml_and_independent_40_frame_pcm_truth']=fixture['expected']['frames']==40 and fixture['expected']['sample_frames']==64064 and fixture['document']['size']>1000
            checks['existing_cut_has_no_preauthored_import']=len(project['clips'])==1 and project['clips'][0]['id']=='original_cut' and not project.get('sequences')
        else:
            root=safe_directory(fixture_workspace);fixture=read_json(root/'fcpxml-fixture.json')
            if fixture.get('kind')!=KIND or any(not re.fullmatch('[a-f0-9]{32}',fixture.get(key,'')) for key in ('acceptance_id','project_id','sentinel_id')):raise ValueError('Wrong explicitly prepared FCPXML fixture')
            if fixture.get('helper_identity')!=result['helper_identity']:raise ValueError('Native helper changed after preparation')
            if (root/(operation+'-passed.json')).exists():raise ValueError('Preserve completed phases; prepare a new fixture for repetition')
            prior=read_json(root/(PHASES[PHASES.index(operation)-1]+'-passed.json'))
            if prior.get('passed') is not True or prior.get('acceptance_id')!=fixture['acceptance_id'] or prior.get('source_inventory')!=before:raise ValueError('Prior phase does not certify this exact fixture and source')
            if identity(root/'workspace/projects'/fixture['project_id']/'project.json')!=prior.get('saved_project_identity'):raise ValueError('Saved project changed after the prior phase')
            if {path.name:identity(path) for path in (root/'truth').iterdir()}!=fixture['truth_files']:raise ValueError('Independent XML/picture/PCM oracle changed')
            if any(identity(root/row['path'])!=row['identity'] for row in fixture['media']):raise ValueError('Original source fixture bytes changed')
            for path in (root/'workspace/jobs').glob('*.json'):
                job=read_json(path)
                if job.get('project_id') not in {fixture['project_id'],fixture['sentinel_id']} or job.get('state') not in {'completed','failed','cancelled'}:raise ValueError('Unexpected or pending fixture work')
            store=Store(root/'workspace');project=store.get(fixture['project_id']);initial=copy.deepcopy(project)
            with store.lock:jobs_before=set(store.jobs)
            cfg={**fixture,'operation':operation,'native_playback_required':transport=='WKWebView'}
            if operation=='author':cfg['document_base64']=base64.b64encode((root/'truth/ENGINE_TEST_timeline.fcpxml').read_bytes()).decode('ascii')
            script=output/'ENGINE_TEST_fcpxml.js';script.write_text((HERE/'macos/FcpxmlSmoke.js').read_text().replace('/* ENGINE_TEST_CONFIG */ {}',json.dumps(cfg)),encoding='utf-8')
            result['executed_javascript_identity']=identity(script);downloads=output/'native_downloads';downloads.mkdir()
            server_module.render_frame=observe;server=Server(0,store);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.025},daemon=True);thread.start()
            screenshot=output/'ENGINE_TEST_fcpxml.png';maximum=budget(14,2.8)
            process=foreground([Path(binary).resolve(),'--url','http://127.0.0.1:'+str(server.server_port)+'/','--output',screenshot,'--script',script,'--download-dir',downloads,'--timeout',round(maximum,2)],budget(maximum+.2,2.4))
            ui=read_helper_result(process);result['ui']=ui;result['helper_exit_code']=process.returncode;write_json(output/'ENGINE_TEST_browser_result.json',ui)
            checks['actual_shipped_controls_succeeded']=ui.get('passed') is True and process.returncode==0
            checks['no_browser_or_download_errors']=not ui.get('page_errors') and not ui.get('download_errors')
            if not checks['actual_shipped_controls_succeeded']:raise ValueError(ui.get('error') or 'Actual FCPXML controls failed')
            checks['all_declared_ui_checks_passed']=bool(ui.get('checks')) and all(ui['checks'].values())
            project=store.get(fixture['project_id']);checks.update(check_edit(project,fixture))
            with store.lock:jobs=[copy.deepcopy(job) for key,job in store.jobs.items() if key not in jobs_before]
            actual_downloads=[]
            for row in ui.get('downloads',[]):
                target=Path(row.get('path','')).absolute();name=row.get('suggested_filename','')
                valid=target.name==name if transport=='Chromium' else bool(re.fullmatch(r'ENGINE_TEST_[A-Fa-f0-9-]{36}_'+re.escape(name),target.name))
                if not name or Path(name).name!=name or target.parent!=downloads or not valid or row.get('state')!='completed':raise ValueError('Actual download escaped its owned evidence directory')
                actual_downloads.append((target,row))
            if len(actual_downloads)!=1:raise ValueError('Exactly one completed actual download is required per UI phase')
            target,row=actual_downloads[0]
            if operation=='author':
                if target.suffix!='.fcpxml':raise ValueError('The actual interchange download is not FCPXML')
                exported=store.project_dir(project['id'])/'exports'/row['suggested_filename']
                checks['actual_xml_download_matches_owned_export_bytes']=identity(target)==identity(exported)
                shutil.copyfile(target,output/'ENGINE_TEST_exported.fcpxml')
                checks['retained_export_xml_matches_actual_download_bytes']=identity(output/'ENGINE_TEST_exported.fcpxml')==identity(target)
                xml=ET.fromstring(target.read_bytes());asset_hashes=[node.get('value') for node in xml.findall('resources/asset/metadata/md') if node.get('key')=='com.cinematicum.media.sha256']
                checks['public_xml_contains_bound_original_content_hashes']=set(asset_hashes)=={media['identity']['sha256'] for media in fixture['media']}
                checks['public_xml_retains_actual_compound_and_time_map']=len(xml.findall('resources/media/sequence'))==1 and bool(xml.findall('.//ref-clip')) and bool(xml.findall('.//timeMap'))
                checks['no_unrequested_movie_render']=not any(job['kind']=='render' for job in jobs)
            else:
                renders=[job for job in jobs if job['kind']=='render' and job['state']=='completed' and job.get('result',{}).get('profile')=='prores']
                if len(renders)!=1 or target.suffix!='.mov':raise ValueError('Exactly one completed ProRes job and actual movie download are required')
                receipt=renders[0]['result'];movie=store.project_dir(project['id'])/'exports'/receipt['filename']
                checks['actual_movie_download_matches_export_receipt']=identity(target)==identity(movie) and identity(movie)['sha256']==receipt['sha256']
                code="import json,sys\nfrom pathlib import Path\nsys.path.insert(0,sys.argv[1])\nfrom test_fcpxml_macos import inspect_movie\nprint(json.dumps(inspect_movie(Path(sys.argv[2]),Path(sys.argv[3]))))\n"
                decoded=foreground([sys.executable,'-I','-B','-c',code,HERE,target,root],budget(2.5,.7))
                if decoded.returncode:raise ValueError('Independent source-picture/PCM decode failed: '+decoded.stderr[-1400:])
                measurement=json.loads(decoded.stdout);result['independent_movie']=measurement;truth=fixture['expected']
                checks['every_source_frame_and_retime_boundary_matches_independent_xml_truth']=measurement['frames']==truth['frames'] and measurement['source_counters']==truth['source_counters']
                checks['every_overlap_and_compound_picture_source_correct']=measurement['source_channels']==truth['source_channels'] and measurement['source_color_max_error']<=5
                checks['every_stereo_sample_matches_independent_original_pcm_windows']=measurement['sample_frames']==truth['sample_frames'] and measurement['every_pcm_sample_identical'] and measurement['max_pcm_lsb_error']==0
                frame=ui.get('frames',{}).get('imported',{});match=re.fullmatch('/api/projects/'+fixture['project_id']+'/previews/([a-f0-9]{64})\\.png',frame.get('url',''))
                if not match:raise ValueError('Exact paused frame has no owned receipt URL')
                key=match.group(1);request=requests.get(key,{});picture=store.project_dir(project['id'])/'previews'/(key+'.png')
                checks['paused_frame_snapshot_has_exact_requested_graph']=request.get('frame')==truth['preview_frame'] and request.get('identity')==key and preview_identity(request.get('project'),truth['preview_frame'])==key
                completed=[job for job in jobs if job['kind']=='frame-preview' and job['state']=='completed' and job.get('result',{}).get('url')==frame['url']]
                checks['paused_frame_bytes_match_completed_job']=bool(completed) and completed[-1]['result'].get('sha256')==identity(picture)['sha256']
                shutil.copyfile(picture,output/'ENGINE_TEST_imported_frame.png')
                if transport=='WKWebView':
                    playback=ui.get('metrics',{}).get('playback',{});checks['native_prores_decoder_advances_exact_export']=playback.get('url')==receipt['url'] and playback.get('time',0)>.06
                else:result['native_prores_playback_exclusion']='Chromium portability run; actual WKWebView ProRes decode remains a separate required native gate.'
                before_edit=copy.deepcopy(initial);after_edit=copy.deepcopy(project)
                result['export_saved_metadata']={key:{'before':before_edit.pop(key,None),'after':after_edit.pop(key,None)} for key in ('revision','updated_at')}
                checks['movie_export_preserves_complete_saved_edit']=before_edit==after_edit
                checks['movie_export_performs_one_normal_save_revision']=project['revision']==initial['revision']+1
            checks['actual_browser_snapshot']=screenshot.is_file() and screenshot.stat().st_size>1000
        if fixture and store and project:
            checks['sentinel_project_unchanged']=identity(store.project_dir(fixture['sentinel_id'])/'project.json')==fixture['sentinel_identity']
            checks['all_original_owned_source_bytes_unchanged']=len(project['assets'])==2 and all(identity(store.project_dir(project['id'])/asset['path'])==next(row['identity'] for row in fixture['media'] if row['asset_id']==asset['id']) for asset in project['assets'])
            checks['native_helper_binary_unchanged']=identity(binary)==result['helper_identity']
    except Exception as error:
        result['error']=str(error)
        if isinstance(error,subprocess.CalledProcessError):result['process_error']=(error.stderr or b'').decode(errors='replace')[-1600:]
    finally:
        if server:server.shutdown();server.server_close()
        if thread:thread.join(timeout=.3)
        if store:
            store.shutdown()
            with store.lock:jobs=copy.deepcopy(list(store.jobs.values()))
            checks['all_owned_jobs_terminal']=all(job['state'] not in {'queued','running'} for job in jobs);write_json(output/'ENGINE_TEST_owned_jobs.json',jobs)
        server_module.render_frame=old_render
        if requests:write_json(output/'ENGINE_TEST_frame_requests.json',requests)
        if root and fixture and project:
            persisted=root/'workspace/projects'/fixture['project_id']/'project.json';result['saved_project_identity']=identity(persisted);(output/'ENGINE_TEST_saved_project.json').write_bytes(persisted.read_bytes())
        result['elapsed_seconds']=round(time.monotonic()-began,3);checks['foreground_phase_within18_seconds']=result['elapsed_seconds']<=18
        checks['runtime_web_acceptance_source_unchanged']=source_inventory()==result.get('source_before')
        result['artifacts']={path.relative_to(output).as_posix():identity(path) for path in sorted(output.rglob('*')) if path.is_file()}
        result['passed']=not result.get('error') and bool(checks) and all(checks.values())
        report=output/'ENGINE_TEST_fcpxml_report.json';write_json(report,result)
        if result['passed'] and fixture:
            write_json(root/(operation+'-passed.json'),{'passed':True,'acceptance_id':fixture['acceptance_id'],'operation':operation,
                       'saved_project_identity':result['saved_project_identity'],'source_inventory':before,'helper_identity':result['helper_identity'],'report_identity':identity(report)})
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--binary',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--operation',required=True,choices=PHASES);parser.add_argument('--fixture-workspace',required=True,type=Path);parser.add_argument('--expected-sources',required=True,type=Path);args=parser.parse_args()
    result=run(args.binary,args.output,args.operation,args.fixture_workspace,read_json(args.expected_sources))
    print(json.dumps({'passed':result['passed'],'operation':args.operation,'checks':len(result['checks']),'elapsed_seconds':result['elapsed_seconds'],'error':result.get('error'),'native_certified':result['native_certified']}));return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
