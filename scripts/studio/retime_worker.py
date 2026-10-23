#!/usr/bin/env python3
"""Pinned NumPy/OpenCV worker: dense-flow pictures and authored ramp PCM."""
from __future__ import annotations
import argparse
import importlib.metadata
import json
import math
from pathlib import Path


def runtime():
    import numpy as np
    import cv2
    versions={name:importlib.metadata.version(name) for name in ('numpy','opencv-python-headless')}
    if versions != {'numpy':'2.3.5','opencv-python-headless':'4.11.0.86'}:
        raise ValueError('Retiming requires pinned NumPy 2.3.5 and OpenCV headless 4.11.0.86.')
    cv2.setNumThreads(1)
    return np,cv2,versions


def flow(cv2,a,b):
    engine=cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    engine.setFinestScale(0)
    return engine.calc(a,b,None)


def capabilities():
    np,cv2,versions=runtime()
    rng=np.random.default_rng(199873);a=cv2.GaussianBlur(rng.integers(0,256,(96,128),dtype=np.uint8),(3,3),.7)
    b=cv2.warpAffine(a,np.float32([[1,0,4],[0,1,-2]]),(128,96))
    actual=flow(cv2,a,b)[16:-16,16:-16];error=float(np.median(np.linalg.norm(actual-np.float32([4,-2]),axis=2)))
    if error>.2:
        raise ValueError('Actual dense-flow displacement probe failed.')
    return {'available':True,'versions':versions,'method':'OpenCV DIS medium bidirectional dense optical flow',
        'operation_probe':{'median_displacement_error_pixels':error},'analysis_edge':640,
        'audio':'64-tap anti-aliased varispeed or stereo-linked 2048-sample phase-vocoder pitch preservation'}


def curve(np,recipe,t):
    """Vectorized analytic time integral and local derivative, no frame stepping."""
    x=np.asarray(t,dtype=np.float64);total=np.zeros_like(x);speed=np.full_like(x,recipe['keys'][-1]['speed'])
    keys=recipe['keys']
    for left,right in zip(keys,keys[1:]):
        width=right['frame']-left['frame'];u=np.clip(x-left['frame'],0,width);slope=(right['speed']-left['speed'])/width
        total+=left['speed']*u+.5*slope*u*u
        speed=np.where((x>=left['frame'])&(x<right['frame']),left['speed']+slope*(x-left['frame']),speed)
    total+=np.minimum(x,0)*keys[0]['speed']+np.maximum(x-keys[-1]['frame'],0)*keys[-1]['speed']
    speed=np.where(x<0,keys[0]['speed'],speed)
    return total,speed


def pitch_audio(np,request,source,output):
    """Stereo-linked phase vocoder at analytically mapped source centers.

    Synthesis uses a fixed curve-wide sample lattice and retains prefix phase
    state after a trim/split. Only one overlap window is held in memory. This
    bounded classical method can smear transients; it does not claim neural
    restoration, formant control or production acceptance for arbitrary sound.
    """
    size,hop=2048,256
    window=np.hanning(size);omega=2*np.pi*np.arange(size//2+1)/size
    offsets=np.arange(size,dtype=np.float64)-size//2
    accumulated=np.zeros((size,2),dtype=np.float64);weight=np.zeros(size)
    previous=phase=previous_center=None
    first=request['audio_grid_start'];last=first+request['samples']
    fps=request['fps']['numerator']/request['fps']['denominator']
    lattice=request['audio_grid_phase']
    for cursor in range(-size,last,hop):
        center=cursor+size//2
        mapped,_=curve(np,request['recipe'],(center+lattice)*fps/48000)
        source_center=(request['source_origin']+float(mapped))*48000/fps
        locations=source_center+offsets
        absolute_lower=np.floor(locations).astype(np.int64);amount=locations-absolute_lower
        lower=absolute_lower-request['audio_first']
        # Zero padding is restricted to genuinely unavailable original handles.
        a=source[np.clip(lower,0,len(source)-1)].astype(np.float64)*((lower>=0)&(lower<len(source)))[:,None]
        upper=lower+1
        b=source[np.clip(upper,0,len(source)-1)].astype(np.float64)*((upper>=0)&(upper<len(source)))[:,None]
        frame=a*(1-amount[:,None])+b*amount[:,None]
        spectrum=np.fft.rfft(frame*window[:,None],axis=0)
        angle=np.angle(spectrum);magnitude=np.abs(spectrum)
        if previous is None:
            phase=angle.copy()
        else:
            advance=source_center-previous_center
            if not advance>0:
                raise ValueError('Pitch-preserving ramp requires increasing source time.')
            residual=angle-previous-omega[:,None]*advance
            residual-=2*np.pi*np.floor(residual/(2*np.pi)+.5)
            phase+=omega[:,None]*hop+residual*(hop/advance)
            # Use one shared phase increment per bin; retain the original
            # interchannel phase instead of independently drifting stereo.
            reference=np.argmax(magnitude,axis=1)
            bins=np.arange(len(reference))
            phase=phase[bins,reference,None]+angle-angle[bins,reference,None]
        previous=angle;previous_center=source_center
        synthesized=np.fft.irfft(magnitude*np.exp(1j*phase),n=size,axis=0)*window[:,None]
        accumulated+=synthesized;weight+=window*window
        begin=max(cursor,first);end=min(cursor+hop,last)
        if end>begin:
            indexes=slice(begin-cursor,end-cursor)
            output[begin-first:end-first]=accumulated[indexes]/np.maximum(weight[indexes,None],1e-12)
        accumulated[:-hop]=accumulated[hop:];accumulated[-hop:]=0
        weight[:-hop]=weight[hop:];weight[-hop:]=0
    output.flush()
    return {'mode':'pitch_preserve','sample_frames':request['samples'],'pitch_preserved':True,
        'algorithm':'stereo-linked phase vocoder','window_samples':size,'hop_samples':hop,
        'source_clock':'analytic piecewise-linear speed integral; curve-wide synthesis lattice',
        'quality':'Finite-window processing can smear transients; review rendered speech and music.'}


def audio(np,request,root):
    count=request['samples'];recipe=request['recipe'];fps=request['fps']['numerator']/request['fps']['denominator']
    output=np.memmap(root/'retimed.f32',dtype='<f4',mode='w+',shape=(count,2))
    if request['audio_count']==0 or recipe['audio']=='mute':
        output[:]=0;output.flush();return {'mode':recipe['audio'],'sample_frames':count,'pitch_preserved':False,'filter_taps':64}
    source=np.memmap(root/'source.f32',dtype='<f4',mode='r',shape=(request['audio_count'],2))
    if recipe['audio']=='pitch_preserve':
        return pitch_audio(np,request,source,output)
    tap=np.arange(-31,33,dtype=np.int64)
    for start in range(0,count,4096):
        indexes=np.arange(start,min(count,start+4096),dtype=np.float64)
        local=(indexes+request['sample_phase'])*fps/48000
        mapped,speed=curve(np,recipe,recipe['offset']+local)
        positions=(request['source_origin']+mapped)*48000/fps-request['audio_first']
        base=np.floor(positions).astype(np.int64);where=base[:,None]+tap
        distance=where-positions[:,None];z=distance/32
        window=np.where(np.abs(z)<1,.42+.5*np.cos(np.pi*z)+.08*np.cos(2*np.pi*z),0)
        cutoff=.95/np.maximum(1,np.abs(speed))
        weights=cutoff[:,None]*np.sinc(cutoff[:,None]*distance)*window
        weights/=weights.sum(axis=1)[:,None]
        valid=(where>=0)&(where<len(source))
        values=source[np.clip(where,0,len(source)-1)].astype(np.float64)*valid[:,:,None]
        # Silence authored holds rather than emitting a frozen sample as DC.
        # An isolated zero derivative at a turn is part of a continuous source
        # waveform; muting that one sample would introduce an audible impulse.
        holding=np.zeros(len(indexes),dtype=bool)
        for first,last in request.get('audio_hold_spans',[]):
            holding|=(indexes>=first)&(indexes<last)
        output[start:start+len(indexes)]=np.sum(values*weights[:,:,None],axis=1)*(~holding)[:,None]
    output.flush()
    return {'mode':'varispeed','sample_frames':count,'pitch_preserved':False,'filter_taps':64,'antialias':'Blackman-windowed sinc; adaptive cutoff 0.95/max(1,abs(speed))','zero_speed_audio':'authored holds are silent; isolated turns preserve waveform continuity'}


def picture(np,cv2,request,root):
    w,h=request['width'],request['height'];n=request['duration']
    metrics={'method':request['recipe']['method'],'interpolated_frames':0,'flow_pairs':0,'cut_fallback_frames':0,'low_confidence_fraction':[],'analysis_edge':640}
    if not request['video']:
        (root/'retimed.rgb').write_bytes(bytes(w*h*3*n));return metrics
    source=np.memmap(root/'source.rgb',dtype='uint8',mode='r',shape=(request['source_count'],h,w,3))
    grid_y,grid_x=np.mgrid[0:h,0:w].astype(np.float32);cache={}
    def remap(image,x,y):
        return cv2.remap(image,x,y,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
    def pair(index):
        if index in cache:return cache[index]
        a,b=np.asarray(source[index]),np.asarray(source[index+1]);ratio=min(1,640/max(w,h));aw=max(16,round(w*ratio));ah=max(16,round(h*ratio))
        ag=cv2.cvtColor(cv2.resize(a,(aw,ah)),cv2.COLOR_RGB2GRAY);bg=cv2.cvtColor(cv2.resize(b,(aw,ah)),cv2.COLOR_RGB2GRAY)
        forward=flow(cv2,ag,bg);backward=flow(cv2,bg,ag)
        if (aw,ah)!=(w,h):
            forward=cv2.resize(forward,(w,h));backward=cv2.resize(backward,(w,h));forward*=np.float32([w/aw,h/ah]);backward*=np.float32([w/aw,h/ah])
        next_x,next_y=grid_x+forward[:,:,0],grid_y+forward[:,:,1]
        prev_x,prev_y=grid_x+backward[:,:,0],grid_y+backward[:,:,1]
        error_a=np.linalg.norm(forward+remap(backward,next_x,next_y),axis=2);error_b=np.linalg.norm(backward+remap(forward,prev_x,prev_y),axis=2)
        residual=np.mean(np.abs(a.astype(np.float32)-remap(b,next_x,next_y).astype(np.float32)),axis=2)
        cut=bool(np.mean(residual)>45 and np.mean(residual>35)>.7)
        good_a=(error_a<1.5+.05*np.linalg.norm(forward,axis=2)).astype(np.float32)
        good_b=(error_b<1.5+.05*np.linalg.norm(backward,axis=2)).astype(np.float32)
        cache.clear();cache[index]=(a,b,forward,backward,good_a,good_b,cut);metrics['flow_pairs']+=1
        return cache[index]
    with (root/'retimed.rgb').open('wb') as output:
        for frame,absolute in enumerate(request['positions']):
            position=absolute-request['source_first'];index=math.floor(position);amount=position-index
            if request['recipe']['method']=='nearest' or amount<1e-8:
                chosen=request['nearest_frames'][frame]-request['source_first']
                if not 0<=chosen<len(source):raise ValueError('The exact nearest source frame is outside its decoded window.')
                output.write(source[chosen].tobytes());continue
            if index+1>=len(source):raise ValueError('Optical-flow interpolation is missing its real next source frame.')
            a,b,forward,backward,good_a,good_b,cut=pair(index)
            if cut:
                output.write(source[request['nearest_frames'][frame]-request['source_first']].tobytes());metrics['cut_fallback_frames']+=1;continue
            ax,ay=grid_x.copy(),grid_y.copy();bx,by=grid_x.copy(),grid_y.copy()
            for _ in range(4):
                af=remap(forward,ax,ay);bf=remap(backward,bx,by)
                ax,ay=grid_x-amount*af[:,:,0],grid_y-amount*af[:,:,1]
                bx,by=grid_x-(1-amount)*bf[:,:,0],grid_y-(1-amount)*bf[:,:,1]
            wa=(1-amount)*remap(good_a,ax,ay)*((ax>=0)&(ax<=w-1)&(ay>=0)&(ay<=h-1))
            wb=amount*remap(good_b,bx,by)*((bx>=0)&(bx<=w-1)&(by>=0)&(by<=h-1))
            total=wa+wb;usable=total>1e-6
            mixed=(remap(a,ax,ay).astype(np.float32)*wa[:,:,None]+remap(b,bx,by).astype(np.float32)*wb[:,:,None])/np.maximum(total[:,:,None],1e-6)
            mixed=np.where(usable[:,:,None],mixed,source[request['nearest_frames'][frame]-request['source_first']])
            output.write(np.clip(np.rint(mixed),0,255).astype(np.uint8).tobytes())
            metrics['interpolated_frames']+=1;metrics['low_confidence_fraction'].append(float(np.mean(~usable)))
    return metrics


def execute(path):
    np,cv2,versions=runtime();root=path.parent
    if path.stat().st_size>65536:raise ValueError('Retime worker request exceeds its bound.')
    request=json.loads(path.read_text())
    if not 1<=request['duration']<=240 or not 16<=request['width']<=1280 or not 16<=request['height']<=1280 or request['width']*request['height']>1280*720:
        raise ValueError('Retime worker picture bounds are invalid.')
    if len(request['positions'])!=request['duration'] or len(request['nearest_frames'])!=request['duration'] or not 1<=request['samples']<=48_000*240:
        raise ValueError('Retime worker clock bounds are invalid.')
    if request['recipe']['audio']=='pitch_preserve':
        first=request.get('audio_grid_start');phase=request.get('audio_grid_phase')
        if type(first) is not int or not 0<=first<=48_000*240 or first+request['samples']>48_000*240+1 or isinstance(phase,bool) or not isinstance(phase,(int,float)) or not math.isfinite(phase) or not -.5<=phase<.5:
            raise ValueError('Pitch-preserving synthesis lattice exceeds the retained curve bounds.')
    spans=request.get('audio_hold_spans',[]);previous=-1
    if not isinstance(spans,list) or len(spans)>34:
        raise ValueError('Authored audio holds exceed their explicit span bound.')
    for span in spans:
        if not isinstance(span,list) or len(span)!=2 or any(type(x) is not int for x in span) or not 0<=span[0]<span[1]<=request['samples'] or span[0]<previous:
            raise ValueError('Authored audio holds require ordered half-open PCM index spans.')
        previous=span[1]
    if request['video'] and (root/'source.rgb').stat().st_size!=request['source_count']*request['width']*request['height']*3:
        raise ValueError('The exact raw source picture inventory does not match.')
    if request['audio_count'] and (root/'source.f32').stat().st_size!=request['audio_count']*8:
        raise ValueError('The exact selected stereo source PCM inventory does not match.')
    pictures=picture(np,cv2,request,root);sound=audio(np,request,root)
    return {'version':1,'picture':pictures,'audio':sound,'versions':versions,'runtime_operations_executed':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True);group.add_argument('--capabilities',action='store_true');group.add_argument('--request',type=Path)
    options=parser.parse_args();print(json.dumps(capabilities() if options.capabilities else execute(options.request),allow_nan=False))
