"""CINEMATICUM sequence, caption and multicamera document operations.

All actions return independent candidates. The caller applies the candidate once
through the editor's undo history; no operation saves files or executes code.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import math
import hashlib
import re
import uuid

if __package__:
    from .timebase import project_rate, format_timecode, parse_timecode
    from .multicam import set_audio_lock, monitor_plan, group_for, verify_sources
else:
    from timebase import project_rate, format_timecode, parse_timecode
    from multicam import set_audio_lock, monitor_plan, group_for, verify_sources

SEQUENCE_FIELDS = ('clips', 'titles', 'tracks', 'captions', 'caption_style', 'sequence_duration', 'otio_dissolve')
MAX_SEQUENCES = 64
MAX_DEPTH = 8
MAX_EXPANDED_CLIPS = 1024
MAX_CAPTIONS = 4096
_ID = re.compile(r'^[A-Za-z0-9_-]{1,128}$')
_TIME = re.compile(r'^(?:(\d{1,3}):)?([0-5]\d):([0-5]\d)[,.](\d{3})$')


def _id(value, label):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(label + ' must be a valid identifier.')
    return value


def _integer(value, label, low=0, high=10_000_000):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or int(value) != value or not low <= value <= high:
        raise ValueError(label + ' must be an integer in the supported range.')
    return int(value)


def _name(value, fallback='Sequence'):
    if not isinstance(value, str) or not value.strip() or len(value) > 200 or '\x00' in value:
        raise ValueError('A name must contain 1–200 characters.')
    return value.strip()


def sequence_duration(sequence):
    ends = [_integer(sequence.get('sequence_duration', 0), 'Sequence out frame')]
    for field in ('clips', 'titles', 'captions'):
        items = sequence.get(field, [])
        if not isinstance(items, list):
            raise ValueError('Sequence ' + field + ' must be a list.')
        for item in items:
            if not isinstance(item, dict):
                raise ValueError('Sequence items must be objects.')
            ends.append(_integer(item.get('start', 0), 'Item start') + _integer(item.get('duration', 0), 'Item duration'))
    return max(ends)


def snapshot_sequence(project):
    value = {'id': project.get('sequence_id', 'main'), 'name': project.get('sequence_name', 'Main sequence')}
    for field in SEQUENCE_FIELDS:
        if field == 'otio_dissolve' and field not in project:
            continue
        value[field] = copy.deepcopy(project.get(field, 0 if field == 'sequence_duration' else {} if field == 'caption_style' else []))
    return value


def sequence_views(project):
    """The active edit is authoritative; stored entries contain inactive edits."""
    if not isinstance(project, dict):
        raise ValueError('Project must be an object.')
    current = snapshot_sequence(project)
    _id(current['id'], 'Active sequence id')
    _name(current['name'])
    stored = project.get('sequences', [])
    if not isinstance(stored, list) or len(stored) >= MAX_SEQUENCES:
        raise ValueError('A project supports at most 64 sequences.')
    result = {current['id']: current}
    for item in stored:
        if not isinstance(item, dict) or set(item) - ({'id', 'name'} | set(SEQUENCE_FIELDS)):
            raise ValueError('A stored sequence contains unsupported fields.')
        ident = _id(item.get('id'), 'Sequence id')
        _name(item.get('name'))
        if ident in result:
            raise ValueError('Sequence identifiers must be unique; the active edit is not duplicated in its library.')
        result[ident] = copy.deepcopy(item)
    total = 0
    for value in result.values():
        for field in ('clips', 'titles', 'tracks', 'captions'):
            if not isinstance(value.get(field, []), list):
                raise ValueError('Sequence ' + field + ' must be a list.')
        total += len(value.get('clips', []))
    if total > 4096:
        raise ValueError('The sequence library exceeds 4,096 authored clips.')
    return result


def validate_sequence_graph(project):
    views = sequence_views(project)
    def visit(ident, path):
        if ident in path:
            raise ValueError('A sequence cannot contain itself, directly or through another sequence.')
        if len(path) >= MAX_DEPTH:
            raise ValueError('Sequence nesting exceeds eight levels.')
        # Count each instance, including empty/title-only sequences. Counting
        # just media leaves lets an empty shared child expand exponentially.
        # Text plates are real render inputs too, so they consume this budget.
        count = 1 + len(views[ident].get('titles', []))
        if count > MAX_EXPANDED_CLIPS:
            raise ValueError('A rendered sequence exceeds 1,024 expanded clips, text plates or sequence layers.')
        for clip in views[ident].get('clips', []):
            if not isinstance(clip, dict):
                raise ValueError('Invalid sequence clip.')
            child = clip.get('sequence_id')
            if child is not None:
                _id(child, 'Nested sequence id')
                if clip.get('asset_id') is not None:
                    raise ValueError('A nested clip cannot also reference a media asset.')
                if child not in views:
                    raise ValueError('A nested clip refers to a missing sequence.')
                count += visit(child, path + (ident,))
            else:
                count += 1
            if count > MAX_EXPANDED_CLIPS:
                raise ValueError('A rendered sequence exceeds 1,024 expanded clips, text plates or sequence layers.')
        return count
    for ident in views:
        visit(ident, ())
    return views


def sequence_project(project, sequence):
    value = copy.deepcopy(project)
    value.pop('sequences', None)
    value['sequence_id'] = sequence['id']
    value['sequence_name'] = sequence['name']
    for field in SEQUENCE_FIELDS:
        if field == 'otio_dissolve' and field not in sequence:
            value.pop(field, None)
            continue
        value[field] = copy.deepcopy(sequence.get(field, 0 if field == 'sequence_duration' else {} if field == 'caption_style' else []))
    return value


def sequence_asset(project, ident, views=None):
    views = views or sequence_views(project)
    if ident not in views:
        raise ValueError('Unknown nested sequence.')
    sequence = views[ident]
    rate = project_rate(project)
    frames = sequence_duration(sequence)
    return {'id': ident, 'name': sequence['name'], 'kind': 'sequence', 'path': '_sequence_.mkv',
            'width': project['width'], 'height': project['height'], 'duration': float(rate.seconds_for_frames(frames)),
            'frames': frames, 'has_audio': True, 'audio_channels': 2, 'audio_sample_rate': 48000,
            'audio_stream_index': 'aout', 'video_stream_index': 'vout', 'audio_duration': float(rate.seconds_for_frames(frames))}


def validate_dissolve(project):
    """A converted OTIO dissolve is an explicit two-operand composition.

    Sources remain editable in their own sequences. Its operator cannot silently
    turn into a different mix after an accidental move, crop, mute or third layer.
    """
    if 'otio_dissolve' not in project:
        return
    value = project['otio_dissolve']
    if not isinstance(value, dict) or set(value) != {'version', 'in_offset', 'out_offset'} or value['version'] != 1:
        raise ValueError('Invalid OTIO dissolve composition.')
    inside = _integer(value['in_offset'], 'Dissolve in offset')
    outside = _integer(value['out_offset'], 'Dissolve out offset')
    duration = inside + outside
    if not duration or sequence_duration(project) != duration or len(project['clips']) != 2 or project['titles'] or project.get('captions'):
        raise ValueError('An OTIO dissolve needs exactly two operands and its original duration.')
    for index, clip in enumerate(project['clips']):
        expected = {'track': index, 'start': 0, 'in': 0, 'duration': duration, 'speed': 1, 'reverse': False,
                    'opacity': 1, 'x': 0, 'y': 0, 'scale': 1, 'rotation': 0, 'volume': 1}
        if not clip.get('sequence_id') or any(clip.get(key) != item for key, item in expected.items()):
            raise ValueError('Dissolve operands must be full-duration nested sequences. Edit their source sequences instead.')
        if clip['keyframes'] or any(clip.get(key) for key in ('tracking', 'planar_motion', 'compositor', 'color_pipeline')) or any(clip['effects'].values()) or clip['grade'] != {'exposure': 0, 'contrast': 1, 'saturation': 1, 'temperature': 0}:
            raise ValueError('Apply effects inside a dissolve source sequence, before the linear mix.')
        audio = clip['audio']
        if any(audio.get(key, 0) != item for key, item in {'fade_in': duration if index else 0,
                'fade_out': 0 if index else duration, 'fade_duration': duration, 'fade_offset': 0, 'pan': 0}.items()) or audio.get('channels') is not None or audio.get('stream_index') is not None:
            raise ValueError('Dissolve audio uses complementary linear fades; edit routing inside the source sequence.')
    if any(t['id'] not in (0, 1) or t['mute'] or t['solo'] or t['gain'] != 1 for t in project['tracks']):
        raise ValueError('Dissolve operator tracks cannot change the prescribed two-source mix.')


def validate_captions(captions, rate, maximum):
    if not isinstance(captions, list) or len(captions) > MAX_CAPTIONS:
        raise ValueError('Captions must contain at most 4,096 cues.')
    result, seen = [], set()
    for cue in captions:
        if not isinstance(cue, dict):
            raise ValueError('Invalid caption cue.')
        item = copy.deepcopy(cue)
        ident = _id(item.get('id'), 'Caption id')
        if ident in seen:
            raise ValueError('Caption identifiers must be unique.')
        seen.add(ident)
        item['start'] = _integer(item.get('start'), 'Caption start', 0, maximum)
        item['duration'] = _integer(item.get('duration'), 'Caption duration', 1, maximum)
        if item['start'] + item['duration'] > maximum:
            raise ValueError('Caption exceeds the timeline range.')
        text = item.get('text')
        if not isinstance(text, str) or not text.strip() or len(text) > 4000 or any(ord(ch) < 32 and ch not in '\n\t' for ch in text):
            raise ValueError('Caption text must contain 1–4,000 printable characters.')
        item['text'] = text.replace('\r\n', '\n').replace('\r', '\n')
        result.append(item)
    return sorted(result, key=lambda item: (item['start'], item['id']))


def _milliseconds(value):
    match = _TIME.fullmatch(value.strip())
    if not match:
        raise ValueError('Caption timestamp must be HH:MM:SS,mmm or MM:SS.mmm.')
    hours, minutes, seconds, ms = match.groups()
    return ((int(hours or 0) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(ms)


def import_captions(text, rate, *, format=None):
    if not isinstance(text, str) or len(text.encode('utf-8')) > 2 * 1024 * 1024:
        raise ValueError('Caption files must contain at most 2 MiB of UTF-8 text.')
    text = text.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
    vtt = text.startswith('WEBVTT')
    if format not in (None, 'srt', 'vtt') or (format == 'vtt' and not vtt):
        raise ValueError('Select a valid SRT or WEBVTT caption file.')
    blocks = re.split(r'\n[ \t]*\n', text.strip())
    cues = []
    for block in blocks:
        lines = block.split('\n')
        if vtt and (lines[0].startswith('WEBVTT') or lines[0].startswith('NOTE')):
            continue
        if lines[0] in ('STYLE', 'REGION'):
            raise ValueError('VTT styles and regions are not silently discarded; import plain text cues.')
        index = next((i for i, line in enumerate(lines[:2]) if '-->' in line), None)
        if index is None:
            raise ValueError('A caption block has no timestamp range.')
        times = lines[index].split('-->')
        if len(times) != 2:
            raise ValueError('Invalid caption timestamp range.')
        right = times[1].strip().split()
        if len(right) != 1:
            raise ValueError('VTT positioning/settings are unsupported; import plain text cues.')
        start_ms, end_ms = _milliseconds(times[0]), _milliseconds(right[0])
        if end_ms <= start_ms:
            raise ValueError('A caption must end after it starts.')
        # Round each absolute endpoint once; adjacent cues retain their boundary.
        start = rate.frames_for_seconds(Fraction(start_ms, 1000))
        end = rate.frames_for_seconds(Fraction(end_ms, 1000))
        if end <= start:
            raise ValueError('A caption is shorter than one project frame after conform.')
        content = '\n'.join(lines[index + 1:])
        if re.search(r'<[^>]*>', content):
            raise ValueError('Styled/timed caption markup needs explicit conversion; plain text is supported.')
        cues.append({'id': uuid.uuid4().hex, 'start': start, 'duration': end - start, 'text': content})
    if not cues:
        raise ValueError('The caption file contains no cues.')
    return validate_captions(cues, rate, rate.max_timeline_frames(6 * 60 * 60))


def export_captions(captions, rate, format='srt'):
    if format not in ('srt', 'vtt'):
        raise ValueError('Caption format must be srt or vtt.')
    cues = validate_captions(captions, rate, rate.max_timeline_frames(6 * 60 * 60))
    def timestamp(frame):
        ms = round(rate.seconds_for_frames(frame) * 1000)
        hours, ms = divmod(ms, 3_600_000)
        minutes, ms = divmod(ms, 60_000)
        seconds, ms = divmod(ms, 1000)
        return f'{hours:02}:{minutes:02}:{seconds:02}{"," if format == "srt" else "."}{ms:03}'
    blocks = []
    for index, cue in enumerate(cues):
        blocks.append(f'{index+1}\n{timestamp(cue["start"])} --> {timestamp(cue["start"] + cue["duration"])}\n{cue["text"]}')
    return ('WEBVTT\n\n' if format == 'vtt' else '') + '\n\n'.join(blocks) + '\n'


def _locked(project):
    if any(track.get('locked') for track in project.get('tracks', [])):
        raise ValueError('Unlock the affected timeline tracks before changing its structure.')


def _locked_multicam(project, group_id):
    for sequence in [project, *project.get('sequences', [])]:
        tracks = {track['id'] for track in sequence.get('tracks', []) if track.get('locked')}
        if any(clip.get('multicam', {}).get('group_id') == group_id and clip['track'] in tracks for clip in sequence.get('clips', [])):
            raise ValueError('Unlock every affected camera track before changing this group\'s shared sound.')


def _switch(project, ident):
    views = sequence_views(project)
    if ident not in views:
        raise ValueError('Unknown sequence.')
    active = views.pop(ident)
    for field in SEQUENCE_FIELDS:
        if field == 'otio_dissolve' and field not in active:
            project.pop(field, None)
            continue
        project[field] = copy.deepcopy(active.get(field, 0 if field == 'sequence_duration' else {} if field == 'caption_style' else []))
    project['sequence_id'], project['sequence_name'] = ident, active['name']
    project['sequences'] = list(views.values())


def _caption_titles(project, burn_in):
    if not isinstance(burn_in, bool):
        raise ValueError('Caption burn-in must be true or false.')
    ordinary = [t for t in project.get('titles', []) if not t.get('caption_id')]
    if burn_in and len(ordinary) + len(project.get('captions', [])) > 128:
        raise ValueError('This render supports 128 text plates. Export the full caption sidecar or shorten the burn-in range.')
    project['titles'] = ordinary
    if burn_in:
        style = project.get('caption_style', {})
        for cue in project.get('captions', []):
            project['titles'].append({'id': 'caption_' + hashlib.sha256(cue['id'].encode()).hexdigest()[:32], 'caption_id': cue['id'],
                'start': cue['start'], 'duration': cue['duration'], 'text': cue['text'],
                'x': 0, 'y': style.get('y', .38), 'size': style.get('size', max(12, round(project['height'] * .045))),
                'color': style.get('color', '#ffffff'), 'fade': 0})
    project.setdefault('caption_style', {})['burn_in'] = bool(burn_in)


def apply_action(project, action, values, project_dir):
    """Validate and return an unsaved candidate or a caption download document."""
    if __package__:
        from .engine import validate_project
    else:
        from engine import validate_project
    if not isinstance(values, dict):
        raise ValueError('Editorial action values must be an object.')
    p = validate_project(project, project_dir)
    rate = project_rate(p)
    views = sequence_views(p)
    p.setdefault('sequence_id', 'main')
    p.setdefault('sequence_name', 'Main sequence')
    p.setdefault('sequences', [])
    if action == 'sequence_create':
        if len(views) >= MAX_SEQUENCES:
            raise ValueError('The project already contains 64 sequences.')
        ident = uuid.uuid4().hex
        p['sequences'].append({'id': ident, 'name': _name(values.get('name', 'New sequence')), 'clips': [], 'titles': [], 'tracks': [], 'captions': []})
        _switch(p, ident)
    elif action == 'sequence_duplicate':
        if len(views) >= MAX_SEQUENCES:
            raise ValueError('The project already contains 64 sequences.')
        ident = uuid.uuid4().hex
        item = snapshot_sequence(p)
        item.update(id=ident, name=_name(values.get('name', p['sequence_name'] + ' copy')))
        p['sequences'].append(item)
        _switch(p, ident)
    elif action == 'sequence_switch':
        _switch(p, _id(values.get('sequence_id'), 'Sequence id'))
    elif action == 'sequence_rename':
        p['sequence_name'] = _name(values.get('name'))
    elif action == 'sequence_delete':
        ident = _id(values.get('sequence_id'), 'Sequence id')
        if ident == p['sequence_id']:
            raise ValueError('Switch to another sequence before deleting the active one.')
        if ident not in views:
            raise ValueError('Unknown sequence.')
        if any(c.get('sequence_id') == ident for s in views.values() for c in s.get('clips', [])):
            raise ValueError('A referenced sequence cannot be deleted. Remove its nested clips first.')
        p['sequences'] = [s for s in p['sequences'] if s['id'] != ident]
    elif action == 'sequence_nest':
        _locked(p)
        ident = _id(values.get('sequence_id'), 'Sequence id')
        if ident not in views:
            raise ValueError('Unknown sequence.')
        length = sequence_duration(views[ident])
        if not length:
            raise ValueError('An empty sequence cannot be nested.')
        p['clips'].append({'id': uuid.uuid4().hex, 'sequence_id': ident, 'track': _integer(values.get('track', 0), 'Track', -16, 15),
                           'start': _integer(values.get('start', sequence_duration(p)), 'Start'), 'in': 0, 'duration': length})
    elif action in ('captions_import', 'captions_replace'):
        _locked(p)
        cues = import_captions(values.get('text'), rate, format=values.get('format')) if action == 'captions_import' else validate_captions(values.get('captions'), rate, rate.max_timeline_frames(21600))
        p['captions'] = cues
        if 'style' in values:
            style = values['style']
            if not isinstance(style, dict) or set(style) - {'size', 'color', 'y', 'burn_in'}:
                raise ValueError('Invalid caption style.')
            p['caption_style'] = copy.deepcopy(style)
        _caption_titles(p, values.get('burn_in', p.get('caption_style', {}).get('burn_in', False)))
    elif action == 'captions_export':
        kind = values.get('format', 'srt')
        return {'text': export_captions(p.get('captions', []), rate, kind), 'format': kind,
                'filename': 'CINEMATICUM-captions.' + kind}
    elif action == 'timecode':
        mode = values.get('mode')
        if mode not in ('ndf', 'df'):
            raise ValueError('Timecode display must be ndf or df.')
        format_timecode(0, rate, drop_frame=mode == 'df')
        p.setdefault('settings', {})['timecode_mode'] = mode
    elif action == 'multicam_create':
        _locked(p)
        angles = values.get('angles')
        if not isinstance(angles, list) or not 2 <= len(angles) <= 16:
            raise ValueError('Select 2–16 camera angles.')
        assets = {a['id']: a for a in p['assets']}
        sources, ids = [], set()
        for angle in angles:
            if not isinstance(angle, dict):
                raise ValueError('Invalid camera angle.')
            a = assets.get(angle.get('asset_id'))
            if not a or a['kind'] != 'video' or a['id'] in ids:
                raise ValueError('Camera angles must be distinct imported videos.')
            offset = _integer(angle.get('in', 0), 'Synchronized source frame')
            remaining = math.floor(a['duration'] * rate.fps + 1e-7) - offset
            if remaining < 1:
                raise ValueError('An angle has no frames after its synchronization point.')
            sources.append({'id': uuid.uuid4().hex, 'asset_id': a['id'], 'in': offset, 'available': remaining})
            ids.add(a['id'])
        duration = min(item['available'] for item in sources)
        start = _integer(values.get('start', sequence_duration(p)), 'Multicam start')
        group = {'id': uuid.uuid4().hex, 'name': _name(values.get('name', 'Multicam')), 'angles': sources}
        groups = p.setdefault('multicam_groups', [])
        if len(groups) >= 64:
            raise ValueError('A project supports at most 64 multicamera groups.')
        groups.append(group)
        first = sources[0]
        p['clips'].append({'id': uuid.uuid4().hex, 'asset_id': first['asset_id'], 'track': _integer(values.get('track', 0), 'Track', 0, 15),
            'start': start, 'duration': duration, 'in': first['in'], 'multicam': {'group_id': group['id'], 'angle_id': first['id']}})
    elif action in ('multicam_audio_lock', 'multicam_monitor'):
        clip = next((c for c in p['clips'] if c['id'] == values.get('clip_id')), None)
        if not clip:
            raise ValueError('Select a multicamera clip.')
        if action == 'multicam_monitor':
            if set(values) - {'clip_id', 'frame'}:
                raise ValueError('The monitor accepts one clip and playhead frame.')
            group, _ = group_for(p, clip)
            if group:
                verify_sources(p, project_dir, group)
            return {'monitor': monitor_plan(p, clip, values.get('frame')), 'action': action}
        group, _ = group_for(p, clip)
        if group:
            _locked_multicam(p, group['id'])
        set_audio_lock(p, clip, values)
    elif action == 'multicam_cut':
        _locked(p)
        clip = next((c for c in p['clips'] if c['id'] == values.get('clip_id')), None)
        if not clip or not isinstance(clip.get('multicam'), dict):
            raise ValueError('Select a multicamera clip.')
        if clip['speed'] != 1 or clip['reverse'] or clip.get('tracking') or clip.get('compositor'):
            raise ValueError('Switch angles before retiming, tracking or compositing the multicamera clip.')
        group = next((g for g in p.get('multicam_groups', []) if g['id'] == clip['multicam']['group_id']), None)
        if not group:
            raise ValueError('Multicamera source group is missing.')
        old = next((a for a in group['angles'] if a['id'] == clip['multicam']['angle_id']), None)
        new = next((a for a in group['angles'] if a['id'] == values.get('angle_id')), None)
        if not old or not new:
            raise ValueError('Select an angle from this multicamera group.')
        frame = _integer(values.get('frame'), 'Cut frame', clip['start'], clip['start'] + clip['duration'] - 1)
        local = frame - clip['start']
        right = copy.deepcopy(clip)
        right.update(id=uuid.uuid4().hex if local else clip['id'], asset_id=new['asset_id'], start=frame,
                     duration=clip['duration'] - local, **{'in': clip['in'] + local + new['in'] - old['in']})
        right['animation_offset'] += local
        right['audio']['fade_offset'] += local
        if old['asset_id'] != new['asset_id']:
            # Stream IDs and source-channel roles belong to a camera file.
            # An angle change follows that camera's default audio, while keeping
            # authored timeline gain, balance and fade envelopes intact.
            right['audio'].pop('stream_index', None)
            right['audio'].pop('channels', None)
        right['multicam']['angle_id'] = new['id']
        if local:
            clip['duration'] = local
            p['clips'].append(right)
        else:
            p['clips'][p['clips'].index(clip)] = right
    elif action == 'audio_map':
        clip = next((c for c in p['clips'] if c['id'] == values.get('clip_id')), None)
        if not clip:
            raise ValueError('Select a clip to map its source audio.')
        if any(t.get('locked') and t['id'] == clip['track'] for t in p.get('tracks', [])):
            raise ValueError('Unlock the selected track before editing source audio.')
        group, _ = group_for(p, clip)
        if group and group.get('audio_lock'):
            _locked_multicam(p, group['id'])
            locked_angle = next(a for a in group['angles'] if a['id'] == group['audio_lock']['angle_id'])
            locked_asset = next(a for a in p['assets'] if a['id'] == locked_angle['asset_id'])
            set_audio_lock(p, clip, {'clip_id': clip['id'], 'angle_id': group['audio_lock']['angle_id'],
                                   'stream_index': values.get('stream_index') if values.get('stream_index') is not None else locked_asset['audio_stream_index'],
                                   'channels': values.get('channels')})
            return {'project': validate_project(p, project_dir), 'action': action, 'sequence': p.get('sequence_id', 'main')}
        audio = clip.setdefault('audio', {})
        if values.get('stream_index') is None:
            audio.pop('stream_index', None)
        else:
            audio['stream_index'] = values['stream_index']
        if values.get('channels') is None:
            audio.pop('channels', None)
        else:
            audio['channels'] = values['channels']
    else:
        raise ValueError('Unknown editorial action.')
    p = validate_project(p, project_dir)
    return {'project': p, 'action': action, 'sequence': p.get('sequence_id', 'main')}
