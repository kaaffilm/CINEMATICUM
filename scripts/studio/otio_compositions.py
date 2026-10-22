"""Bounded, media-safe OTIO composition interchange.

The public tree carries real tracks, nested trims, LinearTimeWarp and
SMPTE_Dissolve operators. No OTIO plugin, target URL or external process is
loaded while importing. Source-range duration is the output duration; a signed
LinearTimeWarp consumes abs(scalar) times that range, with a negative scalar
reversing the selected/conformed window. See OTIO_INTERCHANGE.md.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import math
import re
import uuid

if __package__:
    from . import interchange as io
    from .editorial import sequence_views, sequence_project, sequence_duration
    from .engine import track_state, _media_path
    from .timebase import project_rate, parse_rate
else:
    import interchange as io
    from editorial import sequence_views, sequence_project, sequence_duration
    from engine import track_state, _media_path
    from timebase import project_rate, parse_rate


def needs_export(project):
    if any(c.get('sequence_id') or c.get('speed', 1) != 1 or c.get('reverse') for c in project['clips']):
        return True
    for track in {c['track'] for c in project['clips']}:
        end = 0
        for clip in sorted((c for c in project['clips'] if c['track'] == track), key=lambda c:c['start']):
            if clip['start'] < end:
                return True
            end = clip['start'] + clip['duration']
    return bool(project.get('otio_dissolve'))


def needs_import(document):
    if io._metadata(document).get('composition_interchange') == 1:
        return True
    def visit(node, depth=0):
        if not isinstance(node, dict):
            return False
        schema = node.get('OTIO_SCHEMA')
        if schema == 'Transition.1' or schema == 'LinearTimeWarp.1':
            return True
        if schema in {'Track.1', 'Stack.1'} and (node.get('source_range') is not None or depth > 2 or schema == 'Stack.1' and depth > 1):
            return True
        return any(visit(child, depth+1) for child in node.get('children', []) if isinstance(node.get('children'), list)) or any(visit(effect, depth+1) for effect in node.get('effects', []) if isinstance(node.get('effects'), list))
    return visit(document.get('tracks'), 1)


def _effects(node, label, warnings):
    """Validate a single, explicit constant time warp; never guess time curves."""
    effects = node.get('effects', [])
    markers = node.get('markers', [])
    if (not isinstance(effects, list) or len(effects) > 256 or
            not isinstance(markers, list) or len(markers) > 4096 or
            not isinstance(node.get('enabled', True), bool)):
        raise ValueError(label + ' has invalid effects, markers or enabled state.')
    scalar = Fraction(1)
    found = False
    for effect in effects:
        if not isinstance(effect, dict) or not isinstance(effect.get('enabled', True), bool):
            raise ValueError('Invalid OTIO effect.')
        schema = effect.get('OTIO_SCHEMA')
        name = effect.get('effect_name')
        if schema == 'LinearTimeWarp.1':
            if found:
                raise ValueError('Multiple timewarp effects must be consolidated to one constant LinearTimeWarp.')
            found = True
            value = effect.get('time_scalar')
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not .25 <= abs(value) <= 4:
                raise ValueError('A constant timewarp scalar must be between 0.25 and 4 in magnitude; freeze frames and ramps are unsupported.')
            if effect.get('enabled', True):
                scalar = Fraction(str(value))
        elif schema in io._TIME_EFFECTS or name in {'LinearTimeWarp', 'FreezeFrame', 'TimeWarp'}:
            raise ValueError('Unsupported timewarp operator; only explicit constant LinearTimeWarp.1 is supported.')
        elif effect.get('enabled', True):
            warnings.append(label + ': effect ' + str(effect.get('name') or name or schema)[:160] + ' is not applied.')
    if markers:
        warnings.append(label + ': markers are not imported.')
    return scalar


def _effect(clip):
    value = clip.get('speed', 1) * (-1 if clip.get('reverse') else 1)
    return [] if value == 1 else [{'OTIO_SCHEMA':'LinearTimeWarp.1', 'name':'Constant source speed',
        'effect_name':'LinearTimeWarp', 'metadata':{}, 'enabled':True, 'time_scalar':value}]


def _lanes(clips):
    """Preserve the editor's list-order painter priority, not just start order."""
    lanes = []
    placed = []
    for clip in clips:
        overlaps = [(old, lane) for old, lane in placed if old['start'] < clip['start']+clip['duration'] and clip['start'] < old['start']+old['duration']]
        lowest = max([lane+1 for _, lane in overlaps] + [0])
        lane = lowest
        while lane < len(lanes) and any(old['start'] < clip['start']+clip['duration'] and clip['start'] < old['start']+old['duration'] for old in lanes[lane]):
            lane += 1
        if lane >= 16:
            raise ValueError('OTIO overlap exchange supports at most 16 ordered parallel lanes per source track. Split this composition into nested sequences.')
        while len(lanes) <= lane:
            lanes.append([])
        lanes[lane].append(clip)
        placed.append((clip,lane))
    return lanes or [[]]


def export_compositions(project, project_dir):
    p = io._validated_project(project, project_dir)
    rate = project_rate(p)
    views = sequence_views(p)
    assets = {a['id']:a for a in p['assets']}
    used = {reference['asset_id'] for reference in io._asset_reference_slots(p)}
    identities = {ident:io._sha256(_media_path(project_dir,assets[ident]['path'])) for ident in sorted(used)}
    warnings = [
        'OTIO exchanges cuts, gaps, nested trims, constant retime/reverse, ordered overlap lanes and linear SMPTE dissolves. Media is not embedded.',
        'Transforms, grades, non-transition effects, titles and mixer automation remain private CINEMATICUM metadata; other editors receive the unprocessed cuts with public timing operators.',
        'LinearTimeWarp uses output duration and the lower bound of the consumed source window. Negative speed reverses the conformed window; check the receiving editor\'s time-effect convention.',
    ]
    if any(c.get('color_pipeline',{}).get('lut') for s in views.values() for c in s.get('clips',[]) if isinstance(c.get('color_pipeline'),dict)):
        warnings.append('LUT tables are project-owned files and are not embedded in OTIO. Import the same LUTs before restoring private authoring data.')
    def has_sound(clip):
        if max([clip.get('volume',1)]+[k.get('volume',0) for k in clip.get('keyframes',[])]) <= 0:
            return False
        if clip.get('sequence_id'):
            return any(has_sound(c) for c in views[clip['sequence_id']]['clips'])
        return assets[clip['asset_id']]['has_audio']
    def item_for(clip, kind, sequence_id, role):
        if clip.get('sequence_id'):
            item = stack_for(clip['sequence_id'], kind)
            item['source_range'] = io._range(clip['in'],clip['duration'],rate)
            item['effects'] = _effect(clip)
        else:
            asset = assets[clip['asset_id']]
            reference = {'OTIO_SCHEMA':'ExternalReference.1','name':asset['name'],
                'metadata':{'cinematicum':{'sha256':identities[asset['id']],'asset_id':asset['id']}},
                'available_range':None if asset['kind']=='image' else io._range(0,asset['duration']*rate.fps,rate),
                'available_image_bounds':None,'target_url':asset['path']}
            item = io._item('Clip.2',asset['name'],source_range=io._range(clip['in'],clip['duration'],rate),
                media_references={'DEFAULT_MEDIA':reference},active_media_reference_key='DEFAULT_MEDIA',effects=_effect(clip))
        item['metadata'] = {'cinematicum':{'clip_id':clip['id'],'sequence_id':sequence_id,'role':role}}
        return item
    def stack_for(ident, kind=None):
        sequence = views[ident]
        length = sequence_duration(sequence)
        if sequence.get('otio_dissolve'):
            settings=sequence['otio_dissolve'];inside=settings['in_offset'];outside=settings['out_offset']
            tracks=[]
            for channel in ([kind] if kind else ['Video','Audio']):
                before,after=sequence['clips']
                if channel=='Audio' and not (has_sound(before) or has_sound(after)):
                    continue
                # The two operands contain the whole transition interval.
                # Public nominal cuts expose handles on either side of the
                # transition cut; the operator itself adds no duration.
                pre=item_for(before,channel,ident,'native');post=item_for(after,channel,ident,'native')
                pre['source_range']=io._range(0,inside,rate)
                post['source_range']=io._range(inside,outside,rate)
                transition={'OTIO_SCHEMA':'Transition.1','name':'Linear dissolve','metadata':{},
                    'transition_type':'SMPTE_Dissolve','in_offset':io._rt(inside,rate),'out_offset':io._rt(outside,rate)}
                tracks.append(io._item('Track.1','Dissolve '+channel,kind=channel,children=[pre,transition,post]))
            return io._item('Stack.1',sequence['name'],children=tracks)
        view=sequence_project(p,sequence);tracks=[]
        ids=sorted({c['track'] for c in sequence['clips']}|{t['id'] for t in sequence.get('tracks',[])},key=lambda n:(n<0,n if n>=0 else -n))
        for track_id in ids:
            settings=next((t for t in sequence.get('tracks',[]) if t['id']==track_id),{})
            name=settings.get('name',('A'+str(-track_id)) if track_id<0 else 'V'+str(track_id+1))
            channels=['Audio'] if track_id<0 else ['Video','Audio']
            for channel in channels:
                if kind and channel!=kind:
                    continue
                selected=[c for c in sequence['clips'] if c['track']==track_id and (channel=='Video' or has_sound(c))]
                if channel=='Audio' and track_id>=0 and not selected:
                    continue
                role='embedded_audio' if track_id>=0 and channel=='Audio' else 'native'
                label=name+(' source audio' if role=='embedded_audio' else '')
                lanes=[];partition=_lanes(selected)
                for ordinal,clips in enumerate(partition):
                    cursor=0;children=[]
                    for clip in sorted(clips,key=lambda c:c['start']):
                        if clip['start']>cursor:
                            children.append(io._item('Gap.1',source_range=io._range(0,clip['start']-cursor,rate)))
                        children.append(item_for(clip,channel,ident,role));cursor=clip['start']+clip['duration']
                    if cursor<length:
                        children.append(io._item('Gap.1',source_range=io._range(0,length-cursor,rate)))
                    lane=io._item('Track.1',label+(f' overlap lane {ordinal+1}' if len(partition)>1 else ''),kind=channel,children=children)
                    lanes.append(lane)
                if len(lanes)==1:
                    track=lanes[0]
                else:
                    track=io._item('Track.1',label,kind=channel,children=[io._item('Stack.1',label+' overlap composition',children=lanes)])
                track['enabled']=track_state(view,track_id)[0]
                track['metadata']={'cinematicum':{'track_id':track_id,'sequence_id':ident,'role':role}}
                tracks.append(track)
        if not tracks and length:
            tracks=[io._item('Track.1','Sequence duration',kind=kind or 'Video',children=[io._item('Gap.1',source_range=io._range(0,length,rate))])]
        return io._item('Stack.1',sequence['name'],children=tracks)
    document={'OTIO_SCHEMA':'Timeline.1','name':p['name'],'metadata':{},'global_start_time':io._rt(0,rate),
        'tracks':stack_for(p.get('sequence_id','main'))}
    snapshot=copy.deepcopy(p);snapshot.pop('assets')
    document['metadata']={'cinematicum':{'version':1,'composition_interchange':1,'frame_rate':rate.as_dict(),
        'project':snapshot,'asset_sha256':identities,'public_sha256':io._public_digest(document)}}
    return {'document':io._json_copy(document),'warnings':warnings}


class _Importer:
    def __init__(self,document,base,project_dir,mapping,rate):
        self.document,self.base,self.root,self.mapping,self.rate=document,base,project_dir,mapping,rate
        self.assets={a['id']:a for a in base['assets']}
        self.hashes={};self.resolved={};self.stored=[];self.events=0;self.warnings=[]
        self.maximum=rate.max_timeline_frames(21600)
    def asset_for(self,reference,strict=False):
        io._object(reference,{'ExternalReference.1'},'media reference')
        target=reference.get('target_url');meta=io._metadata(reference);digest=meta.get('sha256');source=meta.get('asset_id')
        if not isinstance(target,str) or not target or len(target)>4096 or '\x00' in target:
            raise ValueError('An OTIO external reference needs a bounded target URL.')
        if digest is not None and (not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest)):
            raise ValueError('Invalid media content hash.')
        if source is not None and not isinstance(source,str):
            raise ValueError('Invalid source asset identity.')
        key=(target,digest,source)
        chosen=self.resolved.get(key)
        if chosen is None:
            chosen=self.mapping.get(target) or (self.mapping.get('sha256:'+digest) if digest else None)
        if chosen is None and digest:
            order=([source] if source in self.assets else [])+[ident for ident in self.assets if ident!=source]
            for ident in order:
                if ident not in self.hashes:
                    self.hashes[ident]=io._sha256(_media_path(self.root,self.assets[ident]['path']))
                if self.hashes[ident]==digest:
                    chosen=ident;break
        if chosen is None:
            raise ValueError('Unresolved OTIO media: '+target[:160]+'. Import and map the source first.')
        if digest:
            if chosen not in self.hashes:
                self.hashes[chosen]=io._sha256(_media_path(self.root,self.assets[chosen]['path']))
            if self.hashes[chosen]!=digest:
                if strict:
                    raise ValueError('Private authoring restoration requires byte-identical media.')
                self.warnings.append('Explicit relink selected different content for '+target[:160]+'.')
        self.resolved[key]=chosen
        return chosen
    def sequence(self,name,clips=None,tracks=None,duration=0,**extra):
        return {'id':uuid.uuid4().hex,'name':str(name or 'Imported sequence')[:200],
            'clips':clips or [],'tracks':tracks or [],'titles':[],'captions':[],'sequence_duration':duration,**extra}
    def keep(self,sequence):
        if len(self.stored)>=62:
            raise ValueError('OTIO composition conversion exceeds the 64-sequence project bound.')
        self.stored.append(sequence)
        return sequence['id']
    def duration(self,value,label,zero=False):
        frames=io._integer_frame(value,label)
        if not (0 if zero else 1)<=frames<=self.maximum:
            raise ValueError(label+' is outside the six-hour timeline bound.')
        return frames
    def item(self,node,kind,depth):
        self.events+=1
        if self.events>4096 or depth>=32:
            raise ValueError('OTIO exceeds 4,096 events or 32 input composition levels.')
        schema=io._object(node,{'Clip.1','Clip.2','Stack.1','Track.1','Gap.1'},'sequence item')['OTIO_SCHEMA']
        scalar=_effects(node,'Item',self.warnings)
        if schema in {'Stack.1','Track.1'}:
            child=self.composition(node,kind,depth+1)
            source,duration=(Fraction(0),Fraction(sequence_duration(child))) if node.get('source_range') is None else io._time_range(node['source_range'],self.rate,'Composition source range')
            ident = self.identity_sequence(child)
            descriptor={'sequence_id':ident or self.keep(child),'available':Fraction(sequence_duration(child))}
        elif schema=='Gap.1':
            source,duration=io._time_range(node.get('source_range'),self.rate,'Gap range')
            descriptor={'gap':True};scalar=Fraction(1)
        else:
            if schema=='Clip.1':
                reference=node.get('media_reference')
            else:
                references=node.get('media_references');active=node.get('active_media_reference_key')
                if not isinstance(references,dict) or not isinstance(active,str) or active not in references:
                    raise ValueError('Missing active media reference.')
                reference=references[active]
            asset_id=self.asset_for(reference);asset=self.assets[asset_id]
            available_start=Fraction(0);available=Fraction(str(asset['duration']))*self.rate.fraction if asset['kind']!='image' else None
            if reference.get('available_range') is not None:
                available_start,declared=io._time_range(reference['available_range'],self.rate,'Available range')
                if declared<0:
                    raise ValueError('Available media range has negative duration.')
                available=declared if available is None else min(available,declared)
            if node.get('source_range') is None:
                if reference.get('available_range') is None:
                    raise ValueError('An OTIO clip needs a source_range or an explicit available_range.')
                source,duration=available_start,declared
            else:
                source,duration=io._time_range(node['source_range'],self.rate,'Clip source range')
            source-=available_start
            descriptor={'asset_id':asset_id,'available':available}
            if kind=='Audio' and not asset['has_audio']:
                raise ValueError('An imported Audio-track clip must have source audio.')
            if kind=='Video' and asset['kind']=='audio':
                raise ValueError('An imported Video-track clip must have picture media.')
        duration=self.duration(duration,'Item duration',zero=True)
        descriptor.update(source=source,duration=duration,scalar=scalar,kind=kind,name=node.get('name','Item'))
        if not node.get('enabled',True):
            descriptor={'gap':True,**{key:descriptor[key] for key in ('source','duration','scalar','kind','name')}}
        if 'asset_id' in descriptor:
            self.bounds(descriptor,source,duration)
        return descriptor
    def bounds(self,descriptor,source,duration):
        if descriptor.get('gap'):
            return
        consumed=Fraction(duration)*abs(descriptor['scalar'])
        if 'asset_id' in descriptor:
            asset=self.assets[descriptor['asset_id']]
            if asset['kind']=='image':
                if source:
                    raise ValueError('Still images have no source in point.')
                return
            if source<0 or source+consumed>descriptor['available']+Fraction(1,2):
                raise ValueError('Clip or transition handles exceed available source media; missing handles are not synthesized.')
    def segment(self,descriptor,local,length,start,track):
        if length<=0 or descriptor.get('gap'):
            return None
        scalar=descriptor['scalar'];speed=abs(scalar)
        source=descriptor['source']+(descriptor['duration']-local-length if scalar<0 else local)*speed
        if 'asset_id' in descriptor and self.assets[descriptor['asset_id']]['kind']=='image':
            source=Fraction(0)
        self.bounds(descriptor,source,length)
        clip={'id':uuid.uuid4().hex,'track':track,'start':start,'in':float(source),'duration':length,
            'speed':float(speed),'reverse':scalar<0,'volume':0 if descriptor['kind']=='Video' and 'asset_id' in descriptor else 1}
        if 'sequence_id' in descriptor:
            available=descriptor['available']
            if source<0 or source+length*speed>available:
                # A composition trim may expose leading/trailing transparency.
                # Preserve the edit window rather than clamp and shift media.
                low=max(Fraction(0),source);high=min(available,source+length*speed)
                child=self.sequence('Composition trim and padding',duration=length)
                if high>low:
                    visible=self.duration((high-low)/speed,'Padded composition visible duration')
                    lead=(source+length*speed-high if scalar<0 else low-source)/speed
                    placed=self.duration(lead,'Padded composition leading duration',zero=True)
                    child['clips']=[{**clip,'sequence_id':descriptor['sequence_id'],'start':placed,'in':float(low),'duration':visible}]
                clip.update(sequence_id=self.keep(child),start=start,**{'in':0,'speed':1,'reverse':False})
            else:
                clip['sequence_id']=descriptor['sequence_id']
        else:
            clip['asset_id']=descriptor['asset_id']
        return clip
    def operand(self,descriptor,local,length):
        clip=self.segment(descriptor,local,length,0,0 if descriptor['kind']=='Video' else -1)
        child=self.sequence(descriptor['name']+' transition source',clips=[clip] if clip else [],duration=length)
        return self.identity_sequence(child) or self.keep(child)
    def identity_sequence(self,sequence):
        """Drop identity wrappers, not retimes or trims with a sampling clock.

        OTIO carries a Track inside every Stack. Reimporting a public dissolve
        must not add two native sequence levels on each interchange cycle.
        """
        if sequence.get('otio_dissolve') or sequence.get('titles') or sequence.get('captions') or len(sequence['clips'])!=1:
            return None
        if any(t.get('mute') or t.get('solo') or t.get('gain',1)!=1 for t in sequence.get('tracks',[])):
            return None
        clip=sequence['clips'][0]
        if not clip.get('sequence_id') or any(clip.get(k,v)!=v for k,v in {'start':0,'in':0,'speed':1,'reverse':False,'volume':1}.items()) or clip['duration']!=sequence_duration(sequence):
            return None
        child=next(s for s in self.stored if s['id']==clip['sequence_id'])
        return child['id'] if sequence_duration(child)==clip['duration'] else None
    def dissolve(self,before,after,inside,outside,kind):
        length=inside+outside
        left=self.operand(before,before['duration']-inside,length)
        right=self.operand(after,-inside,length)
        # Both operands are full-canvas nested pictures. Their PCM envelopes
        # use the existing sample-grid fade implementation, exactly once.
        clips=[]
        for index,ident in enumerate((left,right)):
            clips.append({'id':uuid.uuid4().hex,'sequence_id':ident,'track':index,'start':0,'in':0,'duration':length,
                'audio':{'fade_in':length if index else 0,'fade_out':0 if index else length,'fade_duration':length}})
        sequence=self.sequence('Linear dissolve',clips=clips,duration=length,
            otio_dissolve={'version':1,'in_offset':inside,'out_offset':outside})
        return {'id':uuid.uuid4().hex,'sequence_id':self.keep(sequence),'track':0 if kind=='Video' else -1,
            'start':0,'in':0,'duration':length}
    def track(self,node,kind,depth):
        children=node.get('children')
        if not isinstance(children,list) or len(children)>512:
            raise ValueError('Invalid or excessive OTIO track items.')
        descriptors=[];transitions={}
        for child in children:
            if isinstance(child,dict) and child.get('OTIO_SCHEMA')=='Transition.1':
                self.events+=1
                if not descriptors or len(descriptors) in transitions:
                    raise ValueError('Transitions need adjacent items and cannot be adjacent to each other.')
                if child.get('transition_type')!='SMPTE_Dissolve':
                    raise ValueError('Unsupported transition type; only linear SMPTE_Dissolve is supported.')
                if not isinstance(child.get('enabled',True),bool):
                    raise ValueError('Invalid transition enabled state.')
                inside=self.duration(io._time_frames(child.get('in_offset'),self.rate,'Transition in offset'),'Transition in offset',zero=True)
                outside=self.duration(io._time_frames(child.get('out_offset'),self.rate,'Transition out offset'),'Transition out offset',zero=True)
                if inside+outside<1:
                    raise ValueError('A dissolve needs at least one transition frame.')
                transitions[len(descriptors)]=(inside,outside) if child.get('enabled',True) else (0,0)
            else:
                descriptors.append(self.item(child,kind,depth))
        if len(descriptors) in transitions:
            raise ValueError('A transition needs an item on both sides; use an explicit zero-duration Gap for an end fade.')
        for position,(inside,outside) in transitions.items():
            before,after=descriptors[position-1],descriptors[position]
            if inside>before['duration'] or outside>after['duration']:
                raise ValueError('Transition offsets extend beyond the adjacent item durations.')
        clips=[];cursor=0
        for index,descriptor in enumerate(descriptors):
            head=transitions.get(index,(0,0))[1];tail=transitions.get(index+1,(0,0))[0]
            if head+tail>descriptor['duration']:
                raise ValueError('Transitions overlap within an adjacent item.')
            start=cursor+head;length=descriptor['duration']-head-tail
            clip=self.segment(descriptor,head,length,start,0 if kind=='Video' else -1)
            if clip:
                clips.append(clip)
            cursor+=descriptor['duration']
            if index+1 in transitions:
                inside,outside=transitions[index+1]
                if inside+outside:
                    clip=self.dissolve(descriptor,descriptors[index+1],inside,outside,kind)
                    clip['start']=cursor-inside;clips.append(clip)
        self.duration(cursor,'Track duration',zero=True)
        return self.sequence(node.get('name','Track'),clips=clips,duration=cursor,
            tracks=[{'id':0 if kind=='Video' else -1,'name':str(node.get('name') or 'Track')[:100],
                'mute':not node.get('enabled',True),'solo':False,'locked':False,'gain':1}])
    def composition(self,node,kind=None,depth=0):
        if depth>=32:
            raise ValueError('OTIO input composition nesting exceeds 32 levels.')
        schema=io._object(node,{'Stack.1','Track.1'},'composition')['OTIO_SCHEMA']
        _effects(node,'Composition',self.warnings)
        if schema=='Track.1':
            declared=node.get('kind')
            if declared not in {'Video','Audio'}:
                raise ValueError('OTIO tracks must be Video or Audio.')
            return self.track(node,kind or declared,depth)
        children=node.get('children')
        if not isinstance(children,list) or len(children)>48:
            raise ValueError('An OTIO stack supports at most 48 input tracks.')
        result=self.sequence(node.get('name','Sequence'));video=audio=0
        for child in children:
            if not isinstance(child,dict):
                raise ValueError('Invalid stack child.')
            channel=child.get('kind',kind or 'Video')
            if channel not in {'Video','Audio'}:
                raise ValueError('OTIO tracks must be Video or Audio.')
            if kind and channel!=kind:
                continue
            track_id=video if channel=='Video' else -(audio+1)
            video+=channel=='Video';audio+=channel=='Audio'
            if video>16 or audio>16:
                raise ValueError('A sequence supports 16 picture and 16 sound tracks.')
            settings={'id':track_id,'name':str(child.get('name') or channel+' track')[:100],
                'mute':not child.get('enabled',True) or not node.get('enabled',True),'solo':False,'locked':False,'gain':1}
            result['tracks'].append(settings)
            if child.get('OTIO_SCHEMA')=='Track.1' and child.get('source_range') is None and _effects(child,'Track',self.warnings)==1:
                sequence=self.track(child,channel,depth+1)
                result['clips'].extend({**clip,'track':track_id} for clip in sequence['clips'])
                result['sequence_duration']=max(result['sequence_duration'],sequence['sequence_duration'])
            else:
                descriptor=self.item(child,channel,depth+1)
                clip=self.segment(descriptor,0,descriptor['duration'],0,track_id)
                if clip:
                    result['clips'].append(clip)
                result['sequence_duration']=max(result['sequence_duration'],descriptor['duration'])
        return result


def import_compositions(document,project,project_dir,asset_map=None):
    doc=io._json_copy(document);io._object(doc,{'Timeline.1'},'top-level OTIO object')
    base=io._validated_project(project,project_dir)
    assets={a['id']:a for a in base['assets']}
    mapping={} if asset_map is None else asset_map
    if not isinstance(mapping,dict) or len(mapping)>512 or any(not isinstance(k,str) or len(k)>4096 or '\x00' in k or not isinstance(v,str) or v not in assets for k,v in mapping.items()):
        raise ValueError('OTIO mappings must reference already-imported assets.')
    own=io._metadata(doc)
    if own and own.get('version')!=1:
        raise ValueError('Unsupported CINEMATICUM OTIO metadata version.')
    rate=parse_rate(own['frame_rate']) if own.get('frame_rate') else parse_rate(doc['global_start_time']['rate']) if doc.get('global_start_time') else project_rate(base)
    parser=_Importer(doc,base,project_dir,mapping,rate)
    stack=io._object(doc.get('tracks'),{'Stack.1'},'timeline stack')
    public=parser.composition(stack)
    scalar=_effects(stack,'Timeline stack',parser.warnings)
    if stack.get('source_range') is not None or scalar!=1:
        source,length=(Fraction(0),Fraction(sequence_duration(public))) if stack.get('source_range') is None else io._time_range(stack['source_range'],rate,'Timeline stack source range')
        length=parser.duration(length,'Timeline duration',zero=True)
        descriptor={'sequence_id':parser.keep(public),'source':source,'duration':length,'scalar':scalar,
            'kind':'Video','available':Fraction(sequence_duration(public)),'name':'Timeline composition'}
        clip=parser.segment(descriptor,0,length,0,0)
        public=parser.sequence(stack.get('name','Trimmed timeline'),clips=[clip] if clip else [],duration=length)
    if own and own.get('public_sha256')==io._public_digest(doc):
        snapshot=own.get('project')
        if not isinstance(snapshot,dict):
            raise ValueError('Missing CINEMATICUM composition snapshot.')
        candidate=copy.deepcopy(snapshot);candidate['id']=base['id'];candidate['assets']=copy.deepcopy(base['assets'])
        identities=io._asset_identities(own.get('asset_sha256'));remap={}
        for reference in io._asset_reference_slots(candidate):
            source=reference.get('asset_id')
            if source not in identities:
                raise ValueError('A private sequence dependency lacks a content identity.')
            if source not in remap:
                remap[source]=parser.asset_for({'OTIO_SCHEMA':'ExternalReference.1','target_url':'sha256:'+identities[source],
                    'metadata':{'cinematicum':{'asset_id':source,'sha256':identities[source]}}},strict=True)
            reference['asset_id']=remap[source]
        candidate['frame_rate'],candidate['fps']=rate.as_dict(),rate.fps
        candidate=io._validated_project(candidate,project_dir)
        if __package__:
            from .sequence_interchange import _semantic_digest,export_nested
        else:
            from sequence_interchange import _semantic_digest,export_nested
        regenerated=(export_compositions if own.get('composition_interchange')==1 else export_nested)(candidate,project_dir)['document']
        if _semantic_digest(regenerated)!=_semantic_digest(doc):
            raise ValueError('Private sequence timing or media conflicts with the public OTIO structure.')
        parser.warnings.append('CINEMATICUM authoring metadata restored against byte-identical local media. No project has been saved.')
    else:
        previous=sequence_views(base)
        if project_rate(base)!=rate and any(sequence_duration(s)>0 for s in previous.values()):
            raise ValueError('Existing sequences use a different clock. Import this composition into a new project.')
        if len(parser.stored)+len(previous)>=64:
            raise ValueError('Imported and retained sequences exceed the 64-sequence project bound.')
        candidate=copy.deepcopy(base)
        candidate.update(name=str(doc.get('name') or 'Imported OTIO')[:200],frame_rate=rate.as_dict(),fps=rate.fps,
            sequence_id=public['id'],sequence_name=public['name'],sequences=parser.stored+list(previous.values()),
            clips=public['clips'],titles=[],tracks=public['tracks'],captions=[],sequence_duration=public['sequence_duration'])
        candidate.pop('otio_dissolve',None)
        candidate.pop('caption_style',None)
        if rate.fraction not in (Fraction(30000,1001),Fraction(60000,1001)):
            candidate.setdefault('settings',{}).pop('timecode_mode',None)
        parser.warnings.append('Public OTIO composition imported as editable sequences with exact output-frame timing. Video tracks are picture-only; explicit Audio tracks supply sound. No project has been saved.')
        if own:
            parser.warnings.append('The public OTIO edit changed; stale CINEMATICUM authoring metadata was not applied.')
        candidate=io._validated_project(candidate,project_dir)
    if doc.get('global_start_time') is not None:
        start=io._time_frames(doc['global_start_time'],rate,'Global start time')
        if start:
            candidate.setdefault('settings',{})['otio_global_start_time']=copy.deepcopy(doc['global_start_time'])
            parser.warnings.append('The OTIO global start time is retained as metadata; the editable timeline starts at frame zero.')
    return {'project':candidate,'warnings':list(dict.fromkeys(parser.warnings))}
