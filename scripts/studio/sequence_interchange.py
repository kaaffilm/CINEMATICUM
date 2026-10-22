"""OTIO Stack/Track sequence exchange without loading external media URLs."""
from __future__ import annotations
import copy
from fractions import Fraction
import json
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


def has_nested(document):
    stack = document.get('tracks', {}) if isinstance(document, dict) else {}
    return any(isinstance(item, dict) and item.get('OTIO_SCHEMA') == 'Stack.1'
               for track in stack.get('children', []) if isinstance(track, dict)
               for item in track.get('children', []) if isinstance(track.get('children', []), list))


def export_nested(project, project_dir):
    p = io._validated_project(project, project_dir)
    rate = project_rate(p)
    views = sequence_views(p)
    assets = {a['id']: a for a in p['assets']}
    used = {reference['asset_id'] for reference in io._asset_reference_slots(p)}
    identities = {ident: io._sha256(_media_path(project_dir, assets[ident]['path'])) for ident in sorted(used)}
    warnings = ['Nested OTIO stacks carry sequence cuts and media references. Effects, captions, transforms and mixer gains remain CINEMATICUM metadata.']
    def has_sound(ident):
        return any(has_sound(c["sequence_id"]) if c.get("sequence_id") else assets[c["asset_id"]]["has_audio"] for c in views[ident]["clips"])
    def stack_for(ident, role=None):
        sequence = views[ident]
        sequence_view = sequence_project(p, sequence)
        tracks = []
        ids = sorted({c['track'] for c in sequence['clips']} | {t['id'] for t in sequence.get('tracks', [])}, key=lambda i:(i<0,i if i>=0 else -i))
        for track_id in ids:
            settings = next((t for t in sequence.get('tracks', []) if t['id'] == track_id), {})
            clips = [c for c in sequence['clips'] if c['track'] == track_id]
            roles = ['audio'] if track_id < 0 else ['video','audio']
            for channel in roles:
                if role is not None and channel != role:
                    continue
                selected = [c for c in clips if channel == 'video' or (has_sound(c['sequence_id']) if c.get('sequence_id') else assets[c['asset_id']]['has_audio'])]
                if not selected:
                    continue
                name = settings.get('name', ('A'+str(-track_id)) if track_id<0 else ('V'+str(track_id+1)))
                track = io._item('Track.1', name+(' source audio' if track_id>=0 and channel=='audio' else ''), kind='Video' if channel=='video' else 'Audio', children=[], enabled=track_state(sequence_view,track_id)[0])
                track['metadata'] = {'cinematicum':{'track_id':track_id,'sequence_id':ident,'role':'embedded_audio' if track_id>=0 and channel=='audio' else 'native'}}
                cursor = 0
                for clip in sorted(selected,key=lambda c:(c['start'],c['id'])):
                    if clip['start'] < cursor:
                        raise ValueError('OTIO cannot represent overlapping clips on one track; move them to separate tracks.')
                    if clip['speed'] != 1 or clip['reverse']:
                        raise ValueError('Nested OTIO cut exchange requires normal-speed forward clips.')
                    if clip['start'] > cursor:
                        track['children'].append(io._item('Gap.1', source_range=io._range(0,clip['start']-cursor,rate)))
                    if clip.get('sequence_id'):
                        item = stack_for(clip['sequence_id'],channel)
                        item['source_range'] = io._range(clip['in'],clip['duration'],rate)
                    else:
                        asset=assets[clip['asset_id']]
                        reference={'OTIO_SCHEMA':'ExternalReference.1','name':asset['name'],
                                   'metadata':{'cinematicum':{'sha256':identities[asset['id']],'asset_id':asset['id']}},
                                   'available_range':None if asset['kind']=='image' else io._range(0,asset['duration']*rate.fps,rate),
                                   'available_image_bounds':None,'target_url':asset['path']}
                        item=io._item('Clip.2',asset['name'],source_range=io._range(clip['in'],clip['duration'],rate),
                                      media_references={'DEFAULT_MEDIA':reference},active_media_reference_key='DEFAULT_MEDIA')
                    item['metadata']={'cinematicum':{'clip_id':clip['id'],'sequence_id':ident,
                                                    'role':'embedded_audio' if track_id>=0 and channel=='audio' else 'native'}}
                    track['children'].append(item);cursor=clip['start']+clip['duration']
                full_length=sequence_duration(sequence)
                if cursor<full_length:
                    track['children'].append(io._item('Gap.1',source_range=io._range(0,full_length-cursor,rate)))
                tracks.append(track)
        if not tracks and sequence_duration(sequence):
            tracks.append(io._item('Track.1','Sequence duration',kind='Audio' if role=='audio' else 'Video',children=[io._item('Gap.1',source_range=io._range(0,sequence_duration(sequence),rate))]))
        return io._item('Stack.1',sequence['name'],children=tracks)
    document={'OTIO_SCHEMA':'Timeline.1','name':p['name'],'metadata':{},'global_start_time':io._rt(0,rate),
              'tracks':stack_for(p.get('sequence_id','main'))}
    snapshot=copy.deepcopy(p);snapshot.pop('assets')
    document['metadata']={'cinematicum':{'version':1,'nested_sequences':1,'frame_rate':rate.as_dict(),
        'project':snapshot,'asset_sha256':identities,'public_sha256':io._public_digest(document)}}
    return {'document':io._json_copy(document),'warnings':warnings}


def _semantic_digest(document):
    """Compare public timing/structure after content-addressed media relocation."""
    value=copy.deepcopy(document)
    def walk(node):
        if isinstance(node,dict):
            node.pop('name',None)
            if node.get('OTIO_SCHEMA')=='ExternalReference.1':
                meta=io._metadata(node)
                digest=meta.get('sha256')
                if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest):
                    raise ValueError('A preserved nested reference lacks media identity.')
                node['target_url']='sha256:'+digest
            for key,item in list(node.items()):
                if key!='metadata':walk(item)
        elif isinstance(node,list):
            for item in node:walk(item)
    walk(value)
    return io._public_digest(value)


def import_nested(document, project, project_dir, asset_map=None):
    doc=io._json_copy(document);io._object(doc,{'Timeline.1'},'top-level OTIO object')
    base=io._validated_project(project,project_dir)
    assets={a['id']:a for a in base['assets']}
    mapping={} if asset_map is None else asset_map
    if not isinstance(mapping,dict) or len(mapping)>512 or any(not isinstance(k,str) or len(k)>4096 or not isinstance(v,str) or v not in assets for k,v in mapping.items()):
        raise ValueError('OTIO mappings must reference already-imported assets.')
    own=io._metadata(doc)
    if own and own.get('version')!=1:
        raise ValueError('Unsupported CINEMATICUM OTIO metadata version.')
    rate=parse_rate(own['frame_rate']) if own.get('frame_rate') else parse_rate(doc['global_start_time']['rate']) if doc.get('global_start_time') else project_rate(base)
    warnings=[];hashes={};resolved={}
    def asset_for(reference,strict=False):
        io._object(reference,{'ExternalReference.1'},'media reference')
        target=reference.get('target_url');meta=io._metadata(reference);digest=meta.get('sha256')
        if not isinstance(target,str) or not target or len(target)>4096 or '\x00' in target:
            raise ValueError('An OTIO external reference needs a bounded target URL.')
        if digest is not None and (not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest)):
            raise ValueError('Invalid media content hash.')
        key=(target,digest,meta.get('asset_id'))
        if key in resolved:return resolved[key]
        chosen=mapping.get(target) or (mapping.get('sha256:'+digest) if digest else None)
        if chosen is None and digest:
            preferred=meta.get('asset_id');order=([preferred] if preferred in assets else [])+[ident for ident in assets if ident!=preferred]
            for ident in order:
                hashes.setdefault(ident,io._sha256(_media_path(project_dir,assets[ident]['path'])))
                if hashes[ident]==digest:chosen=ident;break
        if chosen is None:
            raise ValueError('Unresolved OTIO media: '+target[:160]+'. Import and map the source first.')
        if digest:
            hashes.setdefault(chosen,io._sha256(_media_path(project_dir,assets[chosen]['path'])))
            if hashes[chosen]!=digest:
                if strict:raise ValueError('Private authoring restoration requires byte-identical media.')
                warnings.append('Explicit relink selected different content for '+target[:160]+'.')
        resolved[key]=chosen;return chosen
    stored=[];event_count=0
    def parse_stack(stack,depth=0):
        nonlocal event_count
        if depth>=8 or len(stored)>=63:raise ValueError('OTIO sequence nesting exceeds supported bounds.')
        io._object(stack,{'Stack.1'},'nested stack');io._noneditorial(stack,'Sequence',warnings)
        if not stack.get('enabled',True):raise ValueError('Disabled nested sequences require explicit conversion.')
        tracks=stack.get('children')
        if not isinstance(tracks,list) or len(tracks)>32:raise ValueError('A nested sequence supports at most 32 tracks.')
        sequence={'id':uuid.uuid4().hex,'name':str(stack.get('name') or 'Imported sequence')[:200],'clips':[],'titles':[],'tracks':[],'captions':[]}
        video=audio=0;sequence_end=0
        for track in tracks:
            io._object(track,{'Track.1'},'sequence track');io._noneditorial(track,'Track',warnings)
            if track.get('source_range') is not None:raise ValueError('Trimmed OTIO tracks require explicit conversion to a trimmed nested stack.')
            kind=track.get('kind')
            if kind not in ('Video','Audio'):raise ValueError('OTIO tracks must be Video or Audio.')
            if kind=='Video':track_id=video;video+=1
            else:audio+=1;track_id=-audio
            if video>16 or audio>16:raise ValueError('A sequence supports 16 picture and 16 sound tracks.')
            sequence['tracks'].append({'id':track_id,'name':str(track.get('name') or 'Track')[:100],
                'mute':not track.get('enabled',True),'solo':False,'locked':False,'gain':1})
            children=track.get('children')
            if not isinstance(children,list) or len(children)>512:raise ValueError('Invalid or excessive OTIO track items.')
            cursor=0
            for item in children:
                event_count+=1
                if event_count>4096:raise ValueError('OTIO contains more than 4,096 events.')
                io._object(item,{'Clip.1','Clip.2','Stack.1','Gap.1'},'sequence item')
                io._noneditorial(item,'Item',warnings)
                if not item.get('enabled',True):raise ValueError('Disabled clips require explicit conversion.')
                child=None
                if item['OTIO_SCHEMA']=='Stack.1':
                    child=parse_stack(item,depth+1)
                    if item.get('source_range') is None:source_in,duration_value=Fraction(0),Fraction(sequence_duration(child))
                    else:source_in,duration_value=io._time_range(item['source_range'],rate,'Nested range')
                else:source_in,duration_value=io._time_range(item.get('source_range'),rate,'Item source range')
                duration=io._integer_frame(duration_value,'Item duration')
                if duration<1 or cursor+duration>rate.max_timeline_frames(21600):raise ValueError('Invalid nested clip/gap duration.')
                if item['OTIO_SCHEMA']=='Gap.1':cursor+=duration;continue
                clip={'id':uuid.uuid4().hex,'track':track_id,'start':cursor,'duration':duration,'in':float(source_in),'volume':0 if kind=='Video' else 1}
                if child:
                    if source_in<0 or source_in+duration>sequence_duration(child):raise ValueError('A nested range exceeds its sequence.')
                    stored.append(child);clip['sequence_id']=child['id'];clip['volume']=1
                else:
                    if item['OTIO_SCHEMA']=='Clip.1':reference=item.get('media_reference')
                    else:
                        references=item.get('media_references');active=item.get('active_media_reference_key')
                        if not isinstance(references,dict) or not isinstance(active,str) or active not in references:raise ValueError('Missing active media reference.')
                        reference=references[active]
                    clip['asset_id']=asset_for(reference)
                    if reference.get('available_range') is not None:
                        begin,available=io._time_range(reference['available_range'],rate,'Available range')
                        if available<0 or source_in<begin or source_in+duration_value>begin+available+Fraction(1,2):raise ValueError('Clip exceeds available source range.')
                        clip['in']=float(source_in-begin)
                    if clip['in']<0:raise ValueError('Negative source in is unsupported.')
                sequence['clips'].append(clip);cursor+=duration
            sequence_end=max(sequence_end,cursor)
        sequence['sequence_duration']=sequence_end
        return sequence
    stack=io._object(doc.get('tracks'),{'Stack.1'},'timeline stack')
    if stack.get('source_range') is not None:raise ValueError('Trimmed top-level stacks need explicit sequence conversion.')
    public=parse_stack(stack)
    if own and own.get('nested_sequences')==1 and own.get('public_sha256')==io._public_digest(doc):
        snapshot=own.get('project')
        if not isinstance(snapshot,dict):raise ValueError('Missing CINEMATICUM sequence snapshot.')
        candidate=copy.deepcopy(snapshot);candidate['id']=base['id'];candidate['assets']=copy.deepcopy(base['assets'])
        identities=io._asset_identities(own.get('asset_sha256'));references=list(io._asset_reference_slots(candidate))
        remap={}
        for reference in references:
            source=reference.get('asset_id')
            if source not in identities:raise ValueError('A private sequence dependency lacks a content identity.')
            if source not in remap:
                remap[source]=asset_for({'OTIO_SCHEMA':'ExternalReference.1','target_url':'sha256:'+identities[source],
                    'metadata':{'cinematicum':{'asset_id':source,'sha256':identities[source]}}},strict=True)
            reference['asset_id']=remap[source]
        candidate['frame_rate'],candidate['fps']=rate.as_dict(),rate.fps
        candidate=io._validated_project(candidate,project_dir)
        regenerated=export_nested(candidate,project_dir)['document']
        if _semantic_digest(regenerated)!=_semantic_digest(doc):
            raise ValueError('Private sequence timing or media conflicts with the public OTIO structure.')
        warnings.append('Nested CINEMATICUM sequences and authoring data restored against byte-identical local media.')
    else:
        previous=sequence_views(base)
        if project_rate(base)!=rate and any(sequence_duration(s)>0 for s in previous.values()):
            raise ValueError('Existing sequences use a different clock. Import this nested timeline into a new project.')
        if len(stored)+len(previous)>=64:
            raise ValueError('Imported and retained sequences exceed the 64-sequence bound.')
        candidate=copy.deepcopy(base)
        candidate.update(name=str(doc.get('name') or 'Imported OTIO')[:200],frame_rate=rate.as_dict(),fps=rate.fps,
                         sequence_id=public['id'],sequence_name=public['name'],sequences=stored+list(previous.values()),
                         clips=public['clips'],titles=[],tracks=public['tracks'],captions=[],sequence_duration=public['sequence_duration'])
        candidate.pop('caption_style',None)
        if rate.fraction not in (Fraction(30000,1001),Fraction(60000,1001)):
            candidate.setdefault('settings',{}).pop('timecode_mode',None)
        warnings.append('Public nested stacks imported as editable sequences. Unsupported private effects are not applied.')
        candidate=io._validated_project(candidate,project_dir)
    return {'project':candidate,'warnings':list(dict.fromkeys(warnings))}
