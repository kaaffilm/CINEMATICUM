"""Bounded editable speed ramps and actual source-media retiming.

The application keeps the recipe, original media and animation separate. The
optional pinned Tracking runtime renders temporary source-time derivatives for
the ordinary movie graph; no derivative becomes a replacement project source.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time

if __package__:
    from .timebase import project_rate
else:
    from timebase import project_rate

MAX_FRAMES = 240
MAX_KEYS = 32
MAX_EDGE = 1280
MAX_PIXELS = 1280 * 720
MAX_RAW_BYTES = 512 * 1024 ** 2
WORKER = Path(__file__).with_name('retime_worker.py')
_RUNTIME_CACHE = {}


def number(value, label, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high or integer and int(value) != value:
        raise ValueError(label + ' is outside the supported finite range.')
    return int(value) if integer else float(value)


def validate_recipe(value, duration):
    if not isinstance(value, dict) or set(value) != {'version','method','audio','offset','keys','source_origin'} or type(value['version']) is not int or value['version'] != 1:
        raise ValueError('A speed ramp needs an explicit version, method, audio mode, source origin, offset and keys.')
    if value['method'] not in ('nearest','optical_flow') or value['audio'] not in ('varispeed','pitch_preserve','mute'):
        raise ValueError('Choose nearest/optical-flow picture and varispeed, pitch-preserving or muted audio.')
    keys = value['keys']
    if not isinstance(keys, list) or not 2 <= len(keys) <= MAX_KEYS:
        raise ValueError('A speed ramp needs 2–32 ordered speed keys.')
    result=[];previous=-1
    for key in keys:
        if not isinstance(key, dict) or set(key) != {'frame','speed'}:
            raise ValueError('Each speed key contains only an output frame and source speed.')
        frame=number(key['frame'],'Speed-key frame',0,MAX_FRAMES,True)
        if frame <= previous:
            raise ValueError('Speed-key frames must be unique and increasing.')
        result.append({'frame':frame,'speed':number(key['speed'],'Source speed',.25,4)})
        previous=frame
    if result[0]['frame'] != 0 or result[-1]['frame'] < 1:
        raise ValueError('Speed keys must begin at zero and end at the curve duration.')
    offset=number(value['offset'],'Speed-ramp trim offset',0,result[-1]['frame']-1,True)
    if duration > MAX_FRAMES or offset+duration > result[-1]['frame']:
        raise ValueError('The edit must stay inside its 240-frame speed-curve domain. Edit the ramp to extend it.')
    origin=value['source_origin']
    if not isinstance(origin,dict) or set(origin)!={'numerator','denominator'} or not isinstance(origin['numerator'],str) or not isinstance(origin['denominator'],str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,255})',origin['numerator']) or not re.fullmatch(r'[1-9][0-9]{0,255}',origin['denominator']):
        raise ValueError('A speed-ramp source origin requires bounded nonnegative rational integer strings.')
    source=Fraction(int(origin['numerator']),int(origin['denominator']))
    if source>10_000_000:
        raise ValueError('The speed-ramp source origin exceeds the supported frame range.')
    return {'version':1,'method':value['method'],'audio':value['audio'],'offset':offset,'keys':result,
        'source_origin':{'numerator':str(source.numerator),'denominator':str(source.denominator)}}


def integral(recipe, frame):
    """Exact analytic integral of piecewise-linear speed in output-frame units."""
    t=Fraction(str(frame));keys=recipe['keys'];total=Fraction(0)
    if t < 0:
        return t*Fraction(str(keys[0]['speed']))
    for left,right in zip(keys,keys[1:]):
        width=right['frame']-left['frame'];span=min(t-left['frame'],Fraction(width))
        if span <= 0:
            break
        a,b=Fraction(str(left['speed'])),Fraction(str(right['speed']))
        total+=a*span+(b-a)*span*span/(2*width)
    if t > keys[-1]['frame']:
        total+=(t-keys[-1]['frame'])*Fraction(str(keys[-1]['speed']))
    return total


def source_delta(clip, local):
    recipe=clip.get('retime')
    if not recipe:
        return Fraction(str(local))*Fraction(str(clip.get('speed',1)))
    offset=recipe['offset']
    return integral(recipe,Fraction(offset)+Fraction(str(local)))-integral(recipe,offset)


def source_position(clip,local):
    recipe=clip.get('retime')
    if not recipe:
        return Fraction(str(clip['in']))+source_delta(clip,local)
    origin=recipe['source_origin']
    return Fraction(int(origin['numerator']),int(origin['denominator']))+integral(recipe,Fraction(recipe['offset'])+Fraction(str(local)))


def local_keys(clip):
    """The dialog's IEEE-754 local-key values, for lossless no-op detection.

    These values are only the editable representation. The original rational
    anchor, full curve and domain remain authoritative for unchanged keys.
    """
    recipe=clip['retime'];start=recipe['offset'];end=start+clip['duration'];keys=recipe['keys']
    def speed(frame):
        if frame<=0:return keys[0]['speed']
        for left,right in zip(keys,keys[1:]):
            if frame<=right['frame']:
                return left['speed']+(right['speed']-left['speed'])*(frame-left['frame'])/(right['frame']-left['frame'])
        return keys[-1]['speed']
    return [{'frame':0,'speed':speed(start)},*[{'frame':k['frame']-start,'speed':k['speed']} for k in keys if start<k['frame']<end],{'frame':clip['duration'],'speed':speed(end)}]


def validate_clip(project, clip, asset):
    if 'retime' not in clip:
        return
    recipe=validate_recipe(clip['retime'],clip['duration'])
    if project.get('settings',{}).get('image_precision','standard8') != 'standard8':
        raise ValueError('Speed ramps and optical flow currently require Standard 8-bit SDR processing.')
    if asset['kind'] not in ('video','audio') or clip.get('sequence_id') or clip['speed'] != 1 or clip['reverse']:
        raise ValueError('Apply a ramp to a forward original video/audio clip; remove constant retime/reverse or render nested sources first.')
    if clip.get('multicam') or any(clip.get(k) for k in ('tracking','planar_motion','learned_recipe','learned_bindings')):
        raise ValueError('Speed ramps cannot share a multicamera or measured-tracking source binding. Use a separate unbound source clip.')
    if any(node.get('tracking_source') for node in (clip.get('compositor') or {}).get('nodes',[])):
        raise ValueError('Remove source-bound tracked masks before adding a speed ramp.')
    if not re.fullmatch('[a-f0-9]{64}',str(asset.get('sha256',''))):
        raise ValueError('Import the original through Studio before retiming; a verified source identity is required.')
    if asset['kind']=='audio' and recipe['method']=='optical_flow':
        raise ValueError('Optical flow requires video picture media.')
    if asset['kind']=='video':
        if min(asset['width'],asset['height']) < 16 or max(asset['width'],asset['height']) > MAX_EDGE or asset['width']*asset['height'] > MAX_PIXELS:
            raise ValueError('This bounded retimer accepts original pictures from a 16-pixel minimum to a 1280-pixel edge and 921,600 pixels.')
        if str(asset.get('pixel_format','')).startswith(('yuva','gbrap','rgba','bgra','argb','abgr','ya')):
            raise ValueError('This optical-flow/ramp path requires opaque picture sources; alpha retiming is unsupported.')
        if asset.get('color_transfer') in ('smpte2084','arib-std-b67'):
            raise ValueError('Convert PQ/HLG footage through a supported color workflow before SDR retiming.')
    clip['retime']=recipe
    if abs(float(source_position(clip,0))-clip['in'])>1e-8:
        raise ValueError('The clip source in no longer matches its retained speed-curve origin. Edit the ramp rather than replacing its source clock.')
    end=source_position(clip,clip['duration'])
    if end > Fraction(str(asset['duration']))*project_rate(project).fraction+Fraction(1,1_000_000):
        raise ValueError('The integrated speed curve extends beyond the original media. Shorten the output or lower its speed keys.')
    if asset['kind']=='video':
        last=source_position(clip,clip['duration']-1)
        handle=math.floor(last+Fraction(1,2)) if recipe['method']=='nearest' else math.ceil(float(last)-1e-8)
        if handle >= math.ceil(asset['duration']*project_rate(project).fps-1e-6):
            raise ValueError('This ramp needs a real final source-picture handle. Shorten the output or lower its speed keys.')
    pixels=max(1,asset['width']*asset['height'])
    if (math.ceil(float(source_delta(clip,clip['duration'])))+3+clip['duration'])*pixels*3 > MAX_RAW_BYTES:
        raise ValueError('The retime source/output window exceeds the 512 MiB raw-picture bound. Use a shorter edit or smaller original.')


def validate_project_ramps(project):
    """Reject time-warping a live ramp a second time through an ancestor."""
    if __package__:
        from .editorial import sequence_views
    else:
        from editorial import sequence_views
    views=sequence_views(project)
    if sum(bool(c.get('retime')) for s in views.values() for c in s['clips']) > 16:
        raise ValueError('This bounded render supports at most 16 authored ramp clips per project.')
    memo={}
    def count(ident):
        if ident not in memo:
            memo[ident]=sum(1 if c.get('retime') else count(c['sequence_id']) if c.get('sequence_id') else 0 for c in views[ident]['clips'])
        return memo[ident]
    for sequence in views.values():
        ramp_ids={c['id'] for c in sequence['clips'] if c.get('retime')}
        if any(c.get('planar_motion',{}).get('source',{}).get('source',{}).get('clip_id') in ramp_ids for c in sequence['clips']):
            raise ValueError('Remove dependent measured corner pins before changing their background to a speed ramp.')
        if count(sequence['id']) > 16:
            raise ValueError('A rendered sequence may expand to at most 16 ramp instances.')
        for clip in sequence['clips']:
            if clip.get('sequence_id') and count(clip['sequence_id']) and (clip.get('speed',1)!=1 or clip.get('reverse')):
                raise ValueError('A sequence containing a speed ramp cannot be retimed/reversed again. Render that edit to a new original first.')


def apply_edit(project, values, *, remove=False):
    allowed={'clip_id'} if remove else {'clip_id','duration','method','audio','keys'}
    if set(values)!=allowed:
        raise ValueError('Speed-ramp controls require an explicit clip, duration, method, audio mode and keys.')
    clip=next((c for c in project['clips'] if c['id']==values['clip_id']),None)
    if clip is None:
        raise ValueError('Select an original timeline clip to edit its speed ramp.')
    if any(t.get('locked') and t['id']==clip['track'] for t in project['tracks']):
        raise ValueError('Unlock this track before changing its speed curve.')
    if remove:
        clip.pop('retime',None)
        # Removing returns to forward 1x at the current source in. Preserve the
        # selected source availability instead of inventing a frozen tail.
        asset=next(a for a in project['assets'] if a['id']==clip['asset_id'])
        clip['duration']=min(clip['duration'],max(1,math.floor(asset['duration']*project_rate(project).fps-clip['in']+1e-7)))
        return
    duration=number(values['duration'],'Ramp output duration',1,MAX_FRAMES,True)
    origin=source_position(clip,0)
    recipe=validate_recipe({'version':1,'method':values['method'],'audio':values['audio'],'offset':0,'keys':copy.deepcopy(values['keys']),
        'source_origin':{'numerator':str(origin.numerator),'denominator':str(origin.denominator)}},duration)
    if recipe['keys'][-1]['frame'] != duration:
        raise ValueError('The final authored speed key must equal the chosen output duration.')
    if clip.get('speed',1)!=1 or clip.get('reverse'):
        raise ValueError('Return this clip to forward 1x before applying a variable-speed curve.')
    if clip.get('retime') and duration==clip['duration'] and recipe['keys']==local_keys(clip):
        # Reopening a split interval must not round its speed keys, drop its
        # retained handles or change a nearest-frame tie on an unchanged Apply.
        kept=copy.deepcopy(clip['retime']);kept.update(method=recipe['method'],audio=recipe['audio']);recipe=kept
    clip['retime']=recipe;clip['duration']=duration


def _environment():
    env={k:v for k,v in os.environ.items() if not k.startswith(('PYTHON','OCIO'))}
    env.update(OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
    return env


def capabilities(python=None):
    if __package__:
        from .imaging import find_imaging_python
    else:
        from imaging import find_imaging_python
    reasons=[]
    candidates=[python or os.environ.get('CINEMATICUM_TRACKING_PYTHON'),str(Path.home()/'Library/Application Support/CINEMATICUM/Tracking/py313-v1/bin/python'),find_imaging_python()]
    for candidate in dict.fromkeys(filter(None,candidates)):
        path=Path(candidate).expanduser()
        if not path.is_absolute() or not path.is_file() or not os.access(path,os.X_OK):
            continue
        key=(str(path),path.stat().st_mtime_ns,WORKER.stat().st_mtime_ns)
        if key in _RUNTIME_CACHE:
            return copy.deepcopy(_RUNTIME_CACHE[key])
        try:
            process=subprocess.run([str(path),'-I','-B',str(WORKER),'--capabilities'],capture_output=True,text=True,env=_environment(),timeout=8)
            if process.returncode:
                raise ValueError(process.stderr[-1000:])
            value=json.loads(process.stdout)
            if value.get('available') is not True:
                raise ValueError('The actual dense-flow runtime probe did not pass.')
            result={**value,'python':str(path),'max_frames':MAX_FRAMES,'max_edge':MAX_EDGE,'max_pixels':MAX_PIXELS,'rendered_playback':True}
            _RUNTIME_CACHE.clear();_RUNTIME_CACHE[key]=result
            return copy.deepcopy(result)
        except (OSError,ValueError,subprocess.TimeoutExpired) as error:
            reasons.append(str(error))
    return {'available':False,'reason':'Install the pinned Tracking runtime for speed ramps and optical flow. '+(reasons[-1] if reasons else 'No isolated runtime was found.')}


def _cancel(event):
    if event is not None and event.is_set():
        if __package__:
            from .engine import RenderCancelled
        else:
            from engine import RenderCancelled
        raise RenderCancelled('Speed-ramp rendering cancelled; original media and completed exports are unchanged.')


def _run(command, root, label, event, deadline, output=None):
    errors=root/(label+'.stderr')
    with errors.open('wb') as log, (Path(output).open('wb') if output else open(os.devnull,'wb')) as sink:
        _cancel(event)
        process=subprocess.Popen(list(map(str,command)),stdin=subprocess.DEVNULL,stdout=sink,stderr=log,env=_environment(),start_new_session=True)
        try:
            while process.poll() is None:
                _cancel(event)
                if time.monotonic()>deadline or errors.stat().st_size>2*1024**2:
                    raise RuntimeError('The bounded retime exceeded its 120-second processing or diagnostic limit.')
                time.sleep(.02)
            if process.returncode:
                raise RuntimeError('Retime engine failed: '+errors.read_text(errors='replace')[-2500:])
        finally:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            if process.poll() is None:
                try:process.wait(timeout=.3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=.3)
        _cancel(event)


def _digest(path,event):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        before=os.fstat(stream.fileno())
        for data in iter(lambda:stream.read(1024*1024),b''):
            _cancel(event);value.update(data)
        after=os.fstat(stream.fileno())
        if any(getattr(before,k)!=getattr(after,k) for k in ('st_ino','st_size','st_mtime_ns','st_ctime_ns')):
            raise ValueError('The original changed during retime source verification.')
    return value.hexdigest()


def prepare(project, clip, asset, project_dir, directory, *, audio_origin=0, cancel_event=None):
    if __package__:
        from .engine import _media_path,_executable,probe_media
    else:
        from engine import _media_path,_executable,probe_media
    _cancel(cancel_event);runtime=capabilities()
    if not runtime['available']:
        raise ValueError(runtime['reason'])
    root=Path(directory);root.mkdir();source=_media_path(project_dir,asset['path'])
    if _digest(source,cancel_event)!=asset['sha256']:
        raise ValueError('The ramp original changed after admission. Reimport the intended media.')
    deadline=time.monotonic()+120;rate=project_rate(project);recipe=clip['retime']
    exact=[source_position(clip,f) for f in range(clip['duration'])]
    positions=[float(value) for value in exact];nearest=[math.floor(value+Fraction(1,2)) for value in exact]
    first=math.floor(min(exact));last=max(nearest) if recipe['method']=='nearest' else math.ceil(max(positions)-1e-8)
    width,height=(asset['width'],asset['height']) if asset['kind']=='video' else (16,16)
    ffmpeg=_executable('ffmpeg')
    common=[ffmpeg,'-v','error','-nostdin','-y','-threads','1','-filter_threads','1','-filter_complex_threads','1']
    if asset['kind']=='video':
        chain=f"setpts=PTS-STARTPTS,fps=fps={rate.ffmpeg}:round=near,trim=start_frame={first}:end_frame={last+1},setpts=PTS-STARTPTS,scale={width}:{height}:flags=lanczos,setsar=1,format=rgb24"
        _run(common+['-protocol_whitelist','file,pipe','-i',source,'-map',f"0:{asset['video_stream_index']}",'-an','-vf',chain,'-frames:v',str(last-first+1),'-pix_fmt','rgb24','-threads','1','-f','rawvideo','pipe:1'],root,'picture-decode',cancel_event,deadline,root/'source.rgb')
        if (root/'source.rgb').stat().st_size != (last-first+1)*width*height*3:
            raise ValueError('The requested original picture handles did not decode completely.')
    absolute=Fraction(str(audio_origin))+clip['start'];samples=rate.sample_span(absolute,clip['duration'])
    phase=Fraction(rate.samples_for_frames(absolute))-rate.seconds_for_frames(absolute)*48000
    # A canonical sample lattice for the complete retained curve makes the
    # spectral state identical on either side of a split, including fractional
    # sequence origins. Render its prefix and publish only this clip's interval.
    curve_sample=Fraction(recipe['offset'])*48000/rate.fraction+phase
    audio_grid_start=math.floor(curve_sample+Fraction(1,2))
    audio_grid_phase=curve_sample-audio_grid_start
    audio_first=audio_count=0
    if asset['has_audio'] and recipe['audio']!='mute':
        selected=clip['audio'].get('stream_index',asset['audio_stream_index']);stream=next(s for s in asset['audio_streams'] if s['index']==selected)
        if recipe['audio']=='pitch_preserve':
            # The 2048-sample analysis window needs real handles around every
            # mapped center. Prefix analysis starts at the same curve position
            # for whole, trimmed and split clips; missing media tails are zero.
            first_local=(audio_grid_phase-1024)*rate.fraction/48000
            last_local=(audio_grid_start+samples+1280+audio_grid_phase)*rate.fraction/48000
            low=source_position(clip,first_local-recipe['offset'])
            high=source_position(clip,last_local-recipe['offset'])
            padding=1026
        else:
            low=source_position(clip,phase*rate.fraction/48000)
            high=source_position(clip,(samples-1+phase)*rate.fraction/48000)
            padding=32
        audio_first=max(0,math.floor(float(rate.seconds_for_frames(low)*48000))-padding)
        audio_end=min(round(stream['duration']*48000),math.ceil(float(rate.seconds_for_frames(high)*48000))+padding+1)
        audio_end=max(audio_first,audio_end)
        audio_count=audio_end-audio_first
        channels=clip['audio'].get('channels');mapping=[f"pan=stereo|c0=c{channels[0]}|c1=c{channels[1]}"] if channels is not None else []
        chain=','.join(['asetpts=PTS-STARTPTS','aresample=48000',*mapping,'aformat=sample_fmts=fltp:channel_layouts=stereo',f'atrim=start_sample={audio_first}:end_sample={audio_end}','asetpts=PTS-STARTPTS'])
        _run(common+['-protocol_whitelist','file,pipe','-i',source,'-map',f'0:{selected}','-vn','-af',chain,'-ac','2','-ar','48000','-f','f32le','pipe:1'],root,'audio-decode',cancel_event,deadline,root/'source.f32')
        if (root/'source.f32').stat().st_size != audio_count*8:
            raise ValueError('The selected source audio handles did not decode completely.')
    request={'version':1,'width':width,'height':height,'video':asset['kind']=='video','source_first':first,'source_count':last-first+1,
        'positions':positions,'nearest_frames':nearest,'recipe':recipe,'source_origin':float(Fraction(int(recipe['source_origin']['numerator']),int(recipe['source_origin']['denominator']))),'duration':clip['duration'],'fps':rate.as_dict(),
        'samples':samples,'sample_phase':float(phase),'audio_first':audio_first,'audio_count':audio_count,
        'audio_grid_start':audio_grid_start,'audio_grid_phase':float(audio_grid_phase)}
    manifest=root/'request.json';manifest.write_text(json.dumps(request,allow_nan=False))
    _run([runtime['python'],'-I','-B',WORKER,'--request',manifest],root,'source-retime',cancel_event,deadline,root/'worker.json')
    result=json.loads((root/'worker.json').read_text())
    if (root/'retimed.rgb').stat().st_size!=clip['duration']*width*height*3 or (root/'retimed.f32').stat().st_size!=samples*8:
        raise ValueError('The retimer did not produce its exact picture/sample count.')
    output=root/'retimed.mkv'
    # No -shortest or video-frame mux limit: those can truncate the final PCM
    # packet. Both raw inputs already contain their exact bounded counts.
    _run(common+['-f','rawvideo','-pixel_format','rgb24','-video_size',f'{width}x{height}','-framerate',rate.ffmpeg,'-i',root/'retimed.rgb',
        '-f','f32le','-ar','48000','-ac','2','-i',root/'retimed.f32','-map','0:v:0','-map','1:a:0','-c:v','ffv1','-pix_fmt','gbrp','-c:a','pcm_f32le','-threads','1',output],root,'retime-mux',cancel_event,deadline)
    if _digest(source,cancel_event)!=asset['sha256']:
        raise ValueError('The original changed while the ramp was rendered.')
    rendered=probe_media(output)
    if rendered['width']!=width or rendered['height']!=height or rendered['codec']!='ffv1' or not rendered['has_audio']:
        raise ValueError('The retime intermediate failed its media-format check.')
    report={**result,'clip_id':clip['id'],'source_sha256':asset['sha256'],'source_path':asset['path'],
        'recipe':copy.deepcopy(recipe),'frame_rate':rate.as_dict(),'output_frames':clip['duration'],'output_samples':samples,
        'absolute_audio_origin':str(absolute),'source_frame_positions':positions,'nearest_source_frames':nearest,'selected_audio':copy.deepcopy(clip['audio']),
        'runtime_versions':runtime['versions'],'source_unchanged':True,'quality':'Bounded classical dense flow; review occlusions, cuts and fine texture.'}
    (root/'retime-report.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    return output,rendered,report
