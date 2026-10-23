"""Typed stereo buses, post-fader aux returns and measured export loudness.

The graph consumes already timed, faded, panned and track-scaled clip audio.
It never changes source selection or its sample lattice. Inserts are named
FFmpeg DSP operators; this module does not host arbitrary external plugins.
"""
from __future__ import annotations

import copy
import math
from pathlib import Path
import re
import subprocess
import tempfile
import time


MAX_BUSES=8
MAX_SENDS=4
MAX_INSERTS=4
_ID=re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,47}')
REQUIRED_FILTERS=('amix','asplit','anull','anullsink','anullsrc','volume','adelay','aeval',
    'highpass','lowpass','acompressor','loudnorm','ebur128','aresample','astats')


def _object(value,keys,label):
    if not isinstance(value,dict) or set(value)-set(keys):
        raise ValueError(label+' contains unsupported fields.')
    return value


def _number(value,label,low,high,integer=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high or integer and int(value)!=value:
        raise ValueError(label+' is outside its finite supported range.')
    return int(value) if integer else float(value)


def _flag(value,label):
    if not isinstance(value,bool):raise ValueError(label+' must be true or false.')
    return value


def _insert(value):
    if not isinstance(value,dict):raise ValueError('A bus insert must be an object.')
    kind=value.get('type')
    if kind in ('highpass','lowpass'):
        _object(value,('type','frequency_hz'),'Bus filter')
        return {'type':kind,'frequency_hz':_number(value.get('frequency_hz',120 if kind=='highpass' else 12000),'Filter frequency',20,20000)}
    if kind=='delay':
        _object(value,('type','milliseconds'),'Delay return')
        return {'type':'delay','milliseconds':_number(value.get('milliseconds',120),'Delay time',0,2000)}
    if kind=='compressor':
        _object(value,('type','threshold_db','ratio','attack_ms','release_ms','makeup_db'),'Bus compressor')
        return {'type':'compressor',**{key:_number(value.get(key,default),'Compressor '+key,low,high)
            for key,default,low,high in (('threshold_db',-18,-60,0),('ratio',4,1,20),
                ('attack_ms',10,.01,2000),('release_ms',150,.01,9000),('makeup_db',0,0,24))}}
    raise ValueError('Choose a highpass, lowpass, delay or stereo-linked compressor insert.')


def validate_mixer(value,track_ids=None):
    _object(value,('version','buses','tracks','master'),'Audio mixer')
    if type(value.get('version')) is not int or value['version']!=1:
        raise ValueError('Audio mixer version must be 1.')
    buses=value.get('buses',[])
    if not isinstance(buses,list) or len(buses)>MAX_BUSES:
        raise ValueError('A sequence supports at most eight audio buses/returns.')
    result=[];seen=set()
    for bus in buses:
        _object(bus,('id','name','output','gain','mute','inserts'),'Audio bus')
        ident=bus.get('id')
        if not isinstance(ident,str) or not _ID.fullmatch(ident) or ident in ('master','none') or ident in seen:
            raise ValueError('Audio bus identifiers must be unique bounded names; master/none are reserved.')
        seen.add(ident);name=bus.get('name',ident)
        if not isinstance(name,str) or not name.strip() or len(name)>80 or any(ord(c)<32 for c in name):
            raise ValueError('Audio bus names require 1–80 printable characters.')
        inserts=bus.get('inserts',[])
        if not isinstance(inserts,list) or len(inserts)>MAX_INSERTS:
            raise ValueError('An audio bus supports at most four named inserts.')
        result.append({'id':ident,'name':name.strip(),'output':bus.get('output','master'),
            'gain':_number(bus.get('gain',1),'Audio bus gain',0,4),
            'mute':_flag(bus.get('mute',False),'Audio bus mute'),'inserts':[_insert(v) for v in inserts]})
    by_id={bus['id']:bus for bus in result}
    for bus in result:
        if not isinstance(bus['output'],str) or bus['output'] not in seen|{'master'}:
            raise ValueError('A bus output must reference an existing bus or master.')
    def visit(ident,path):
        if ident=='master':return
        if ident in path:raise ValueError('Audio bus outputs cannot create feedback cycles.')
        visit(by_id[ident]['output'],path+(ident,))
    for ident in seen:visit(ident,())
    routes=value.get('tracks',[])
    if not isinstance(routes,list) or len(routes)>32:
        raise ValueError('The audio mixer supports at most 32 explicit track routes.')
    normalized=[];routed=set()
    for route in routes:
        _object(route,('track','output','sends'),'Track audio route')
        track=_number(route.get('track'),'Routed track',-16,15,True)
        if track in routed or track_ids is not None and track not in track_ids:
            raise ValueError('Track routes must be unique and reference an existing timeline track.')
        routed.add(track);output=route.get('output','master')
        if not isinstance(output,str) or output not in seen|{'master','none'}:
            raise ValueError('Track output must be master, an existing bus, or send-only.')
        sends=route.get('sends',[])
        if not isinstance(sends,list) or len(sends)>MAX_SENDS:
            raise ValueError('A track supports at most four post-fader sends.')
        targets=set();accepted=[]
        for send in sends:
            _object(send,('bus','gain'),'Post-fader send')
            target=send.get('bus')
            if not isinstance(target,str) or target not in seen or target in targets:
                raise ValueError('Send targets must be distinct existing buses.')
            targets.add(target);accepted.append({'bus':target,'gain':_number(send.get('gain',0),'Send gain',0,4)})
        normalized.append({'track':track,'output':output,'sends':accepted})
    master=_object(value.get('master',{}),('gain','loudness'),'Audio master')
    loudness=_object(master.get('loudness',{}),('enabled','integrated_lufs','true_peak_dbfs','range_lu'),'Master loudness')
    master={'gain':_number(master.get('gain',1),'Master gain',0,4),'loudness':{
        'enabled':_flag(loudness.get('enabled',False),'Master normalization'),
        'integrated_lufs':_number(loudness.get('integrated_lufs',-23),'Integrated loudness target',-36,-9),
        'true_peak_dbfs':_number(loudness.get('true_peak_dbfs',-1),'True-peak ceiling',-9,-.3),
        'range_lu':_number(loudness.get('range_lu',7),'Loudness range target',1,20)}}
    return {'version':1,'buses':result,'tracks':sorted(normalized,key=lambda r:r['track']),'master':master}


def validate_project_mixer(project):
    if 'audio_mixer' in project:
        tracks={track['id'] for track in project.get('tracks',[])}|{clip.get('track',0) for clip in project.get('clips',[])}
        project['audio_mixer']=validate_mixer(project['audio_mixer'],tracks)
    return project


def configured_mixers(project):
    """Reachable per-sequence mixer recipes; inactive libraries stay separate."""
    library={sequence['id']:sequence for sequence in project.get('sequences',[])}
    result={};seen=set()
    def visit(sequence,ident):
        if ident in seen:return
        seen.add(ident)
        if 'audio_mixer' in sequence:result[ident]=copy.deepcopy(sequence['audio_mixer'])
        for clip in sequence.get('clips',[]):
            child=clip.get('sequence_id')
            if child in library:visit(library[child],child)
    visit(project,project.get('sequence_id','main'))
    return result


def apply_edit(project,values):
    _object(values,('mixer',),'Audio mixer edit')
    if set(values)!={'mixer'}:raise ValueError('Audio mixer edit requires an explicit mixer or null.')
    result=copy.deepcopy(project)
    if values['mixer'] is None:result.pop('audio_mixer',None)
    else:result['audio_mixer']=copy.deepcopy(values['mixer'])
    return validate_project_mixer(result)


def _decimal(value):return format(float(value),'.12g')


def _stats(name):
    return 'astats@'+name+'=metadata=0:reset=0:measure_overall=Peak_level+Number_of_NaNs+Number_of_Infs:measure_perchannel=none'


def _read_stats(lines):
    records={}
    if isinstance(lines,str):lines=lines.splitlines()
    pattern=re.compile(r'^\[astats@([A-Za-z0-9_]+)\s+@\s+[^]]+\]\s+(Peak level dB|Number of NaNs|Number of Infs):\s*([-+A-Za-z0-9.]+)\s*$')
    for line in lines:
        match=pattern.match(line.strip())
        if match:
            record=records.setdefault(match.group(1),{})
            if match.group(2) in record:
                raise ValueError('Repeated audio DSP evidence cannot replace an earlier finite-sample result.')
            record[match.group(2)]=float(match.group(3))
    return records


def _finite_stats(record,label):
    if record is None or set(record)!={'Peak level dB','Number of NaNs','Number of Infs'}:
        raise ValueError('The actual audio DSP omitted its '+label+' finite-sample evidence.')
    nan,inf=record['Number of NaNs'],record['Number of Infs']
    if not math.isfinite(nan) or not math.isfinite(inf) or nan<0 or inf<0:
        raise ValueError('Invalid nonfinite-sample counters in '+label+'.')
    return nan,inf


def accept_normalization_audits(lines,expected):
    """Admit silence protection only with complete actual input/output evidence.

    The renderer calls this before publishing an export. Non-silent programs
    containing any normalizer NaN, or any Inf anywhere, fail atomically even if
    the final guard would otherwise have hidden the corrupted values.
    """
    records=_read_stats(lines);receipts=[]
    for prefix in sorted(set(expected)):
        stages={name:records.get(prefix+'_'+name) for name in ('input','normalized','final')}
        input_nan,input_inf=_finite_stats(stages['input'],prefix+' input')
        normal_nan,normal_inf=_finite_stats(stages['normalized'],prefix+' normalized output')
        final_nan,final_inf=_finite_stats(stages['final'],prefix+' final output')
        peak=stages['input']['Peak level dB']
        if input_nan or input_inf or math.isnan(peak) or peak==math.inf:
            raise ValueError('Master normalization input contains nonfinite audio samples.')
        silent=peak==-math.inf
        if normal_inf or final_nan or final_inf or normal_nan and not silent:
            raise ValueError('Master normalization produced nonfinite audio in a non-silent program or invalid final output.')
        normal_peak=stages['normalized']['Peak level dB']
        if normal_peak==math.inf or not normal_nan and math.isnan(normal_peak):
            raise ValueError('Normalizer peak evidence is inconsistent with its finite-sample counters.')
        final_peak=stages['final']['Peak level dB']
        if math.isnan(final_peak) or final_peak==math.inf or silent and final_peak!=-math.inf:
            raise ValueError('Normalized output did not retain finite audio or exact source silence.')
        receipts.append({'instance':prefix,'input_finite':True,'input_exact_silence':silent,
            'normalizer_nan_counter':normal_nan,'final_finite':True,
            'silence_nan_protection_admitted':bool(normal_nan and silent),
            'target_unreachable':silent})
    return receipts


def _insert_filter(value):
    kind=value['type']
    if kind in ('highpass','lowpass'):return kind+'=f='+_decimal(value['frequency_hz'])+':poles=2'
    if kind=='delay':
        # Suffix S makes both stereo delays exact 48 kHz sample counts.
        samples=round(value['milliseconds']*48)
        return f'adelay={samples}S:all=1'
    return ('acompressor=threshold='+_decimal(10**(value['threshold_db']/20))+':ratio='+_decimal(value['ratio'])+
        ':attack='+_decimal(value['attack_ms'])+':release='+_decimal(value['release_ms'])+
        ':makeup='+_decimal(10**(value['makeup_db']/20))+':link=maximum:detection=rms')


def compile_graph(value,audio_inputs,samples,*,silence='silence',prefix='mix'):
    """Return real FFmpeg filters and one pre-limiter master output label.

    audio_inputs contains (unbracketed label, track) pairs after existing clip
    and track controls. The caller retains its existing master limiter and
    exact final sample trim. Nested calls qualify these local labels normally.
    """
    mixer=validate_mixer(value)
    if type(samples) is not int or not 1<=samples<=48000*6*60*60 or not re.fullmatch('[A-Za-z][A-Za-z0-9_]*',prefix):
        raise ValueError('Audio mixer graph needs a bounded sample count and safe prefix.')
    filters=[];incoming={bus['id']:[] for bus in mixer['buses']};incoming['master']=[silence]
    routes={route['track']:route for route in mixer['tracks']};groups={};counter=0
    for label,track in audio_inputs:
        if not isinstance(label,str) or not re.fullmatch('[A-Za-z0-9_:]+',label):raise ValueError('Unsafe audio input label.')
        groups.setdefault(track,[]).append(label)
    def mix(labels,label):
        if not labels:filters.append(f'anullsrc=r=48000:cl=stereo,atrim=end_sample={samples}[{label}]')
        elif len(labels)==1:filters.append(f'[{labels[0]}]anull[{label}]')
        else:filters.append(''.join('['+v+']' for v in labels)+f'amix=inputs={len(labels)}:duration=longest:normalize=0[{label}]')
    def route(label,edges):
        nonlocal counter
        if not edges:filters.append(f'[{label}]anullsink');return
        branches=[label]
        if len(edges)>1:
            branches=[f'{prefix}_split_{counter}_{i}' for i in range(len(edges))];counter+=1
            filters.append(f'[{label}]asplit={len(edges)}'+''.join('['+v+']' for v in branches))
        for branch,(target,gain) in zip(branches,edges):
            out=f'{prefix}_edge_{counter}';counter+=1
            filters.append(f'[{branch}]volume={_decimal(gain)}[{out}]');incoming[target].append(out)
    for ordinal,(track,labels) in enumerate(sorted(groups.items())):
        stem=f'{prefix}_track_{ordinal}';mix(labels,stem)
        setting=routes.get(track,{'output':'master','sends':[]})
        edges=[] if setting['output']=='none' else [(setting['output'],1)]
        edges.extend((send['bus'],send['gain']) for send in setting['sends'])
        route(stem,edges)
    pending={bus['id']:bus for bus in mixer['buses']}
    bus_ordinal={bus['id']:i for i,bus in enumerate(mixer['buses'])}
    while pending:
        ready=[bus for bus in pending.values() if not any(other['output']==bus['id'] for other in pending.values())]
        if not ready:raise ValueError('Audio routing cycle escaped validation.')
        for bus in ready:
            source=f'{prefix}_busin_{bus_ordinal[bus["id"]]}';output=f'{prefix}_busout_{bus_ordinal[bus["id"]]}'
            mix(incoming[bus['id']],source)
            chain=[_insert_filter(insert) for insert in bus['inserts']]
            chain.append('volume='+_decimal(0 if bus['mute'] else bus['gain']))
            filters.append(f'[{source}]'+','.join(chain)+f'[{output}]')
            route(output,[(bus['output'],1)]);del pending[bus['id']]
    mix(incoming['master'],prefix+'_master')
    chain=['volume='+_decimal(mixer['master']['gain'])];target=mixer['master']['loudness']
    if target['enabled']:
        chain.append(_stats(prefix+'_input'))
        chain.append('loudnorm=I='+_decimal(target['integrated_lufs'])+':TP='+_decimal(target['true_peak_dbfs'])+
            ':LRA='+_decimal(target['range_lu'])+':linear=false:dual_mono=false')
        chain.append(_stats(prefix+'_normalized'))
        # Actual loudnorm builds can return NaN for a completely silent input.
        # Keep that case exactly silent; do not add dither/noise that would be
        # boosted toward the requested loudness. Finite audio passes unchanged.
        chain.append("aeval=exprs='if(isnan(val(0)),0,val(0))|if(isnan(val(1)),0,val(1))':channel_layout=stereo")
        chain.append(_stats(prefix+'_final'))
    chain.append('aresample=48000')
    filters.append(f'[{prefix}_master]'+','.join(chain)+f'[{prefix}_out]')
    return filters,prefix+'_out',{'version':1,'bus_count':len(mixer['buses']),
        'post_fader_send_count':sum(len(r['sends']) for r in mixer['tracks']),
        'sample_rate':48000,'channels':2,'master_loudness':copy.deepcopy(target),
        'normalization_audit_required':prefix if target['enabled'] else None,
        'tail_policy':'Effects remain inside the sequence out point; extend the sequence to retain longer returns.'}


def measure_media(path,ffmpeg,*,cancel_event=None,timeout=120):
    """Decode an actual export through FFmpeg's EBU R128/true-peak scanner."""
    source=Path(path)
    if source.is_symlink() or not source.is_file():raise ValueError('Loudness metering requires a regular exported media file.')
    before=source.stat();command=[str(ffmpeg),'-hide_banner','-nostdin','-v','info','-threads','1',
        '-protocol_whitelist','file,pipe','-i',str(source),'-map','0:a:0','-vn',
        '-af','ebur128=peak=true:framelog=verbose,'+_stats('cinematicum_export'),'-f','null','-']
    process=None;began=time.monotonic()
    try:
        if cancel_event is not None and cancel_event.is_set():raise InterruptedError('Audio loudness measurement cancelled.')
        with tempfile.TemporaryFile() as errors:
            process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=errors)
            while process.poll() is None:
                if cancel_event is not None and cancel_event.is_set():raise InterruptedError('Audio loudness measurement cancelled.')
                if time.monotonic()-began>timeout:raise TimeoutError('Audio loudness measurement exceeded its bounded deadline.')
                if errors.tell()>4*1024*1024:raise RuntimeError('Audio loudness diagnostic output exceeded its bound.')
                time.sleep(.02)
            errors.seek(0);log=errors.read(4*1024*1024).decode('utf-8',errors='replace')
            if process.returncode:raise RuntimeError('Actual export loudness scan failed: '+log[-1800:])
        if cancel_event is not None and cancel_event.is_set():raise InterruptedError('Audio loudness measurement cancelled.')
        after=source.stat()
        if any(getattr(before,key)!=getattr(after,key) for key in ('st_ino','st_size','st_mtime_ns','st_ctime_ns')):
            raise ValueError('Export changed during actual loudness measurement.')
        final_stats=_read_stats(log).get('cinematicum_export')
        nans,infs=_finite_stats(final_stats,'decoded final export')
        if nans or infs or math.isnan(final_stats['Peak level dB']) or final_stats['Peak level dB']==math.inf:
            raise ValueError('The actual decoded export contains nonfinite audio samples.')
        summary=log.rsplit('Summary:',1)[-1]
        def metric(pattern,label):
            match=re.search(pattern,summary)
            if not match:raise ValueError('The actual loudness scan omitted '+label+'.')
            value=float(match.group(1))
            if math.isfinite(value):return value
            if value==-math.inf and label=='true peak':return None
            raise ValueError('The actual export has invalid nonfinite '+label+'.')
        integrated=metric(r'Integrated loudness:\s*I:\s*([-+0-9.inf]+)\s+LUFS','integrated loudness')
        loudness_range=metric(r'Loudness range:\s*LRA:\s*([-+0-9.inf]+)\s+LU','loudness range')
        peak=metric(r'True peak:\s*Peak:\s*([-+0-9.inf]+)\s+dBFS','true peak')
        return {'algorithm':'FFmpeg EBU R128 gated integrated loudness and oversampled true peak',
            'integrated_lufs':integrated if peak is not None else None,'loudness_range_lu':loudness_range,'true_peak_dbfs':peak,
            'silent':peak is None,'decoded_output_finite':True,'measured_export_bytes':after.st_size,
            'elapsed_seconds':round(time.monotonic()-began,3)}
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=.5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=.5)
