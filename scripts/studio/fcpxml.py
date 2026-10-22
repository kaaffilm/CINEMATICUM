"""Bounded Final Cut Pro XML 1.9/1.10 timeline interchange.

Only public, explicitly represented edits are exchanged. XML media URLs are
labels to relink against already-owned media; this module never opens them.
Apple's FCPXML 1.10 DTD, timing attributes, timeMap, story-elements and
adjust-transform references define the wire format. See FCPXML_INTERCHANGE.md.
"""
from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
import json
import math
import re
import subprocess
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import quote, unquote, urlsplit

if __package__:
    from . import interchange as io
    from .editorial import sequence_views, sequence_duration
    from .engine import _media_path, _executable
    from .timebase import parse_rate, project_rate
else:
    import interchange as io
    from editorial import sequence_views, sequence_duration
    from engine import _media_path, _executable
    from timebase import parse_rate, project_rate

MAX_BYTES = 8 * 1024 * 1024
MAX_ELEMENTS = 30000
MAX_DEPTH = 40
MAX_EVENTS = 4096
SHA_KEY = 'com.cinematicum.media.sha256'
_ID = re.compile(r'[A-Za-z_][A-Za-z0-9_.-]{0,127}\Z')
_TIME = re.compile(r'([+-]?\d{1,19})(?:/(\d{1,10}))?s\Z')
_STORY = {'asset-clip', 'video', 'audio', 'ref-clip', 'clip', 'gap', 'spine'}
_TIMING = {'conform-rate', 'timeMap'}
_ADJUST = {'adjust-conform', 'adjust-transform', 'adjust-blend', 'adjust-volume'}
_DESCRIPTIVE = {'note', 'metadata'}
_BASE_ATTRS = {'name', 'lane', 'offset', 'start', 'duration', 'enabled'}
_ZERO_GRADE = {'exposure': 0, 'contrast': 1, 'saturation': 1, 'temperature': 0}


def _fail(message):
    raise ValueError('FCPXML: ' + message)


def _text(value, label, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        _fail(label + ' must be bounded, printable text.')
    return value


def _id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        _fail('resource identifiers must be bounded XML IDs.')
    return value


def time_value(value, label='time'):
    """The Apple wire clock is signed int64 / unsigned int32 seconds."""
    match = _TIME.fullmatch(value) if isinstance(value, str) else None
    if not match:
        _fail(label + ' must use exact rational seconds, for example 1001/30000s.')
    numerator, denominator = int(match[1]), int(match[2] or 1)
    if not -(2**63) <= numerator < 2**63 or not 1 <= denominator < 2**32:
        _fail(label + ' exceeds the FCPXML rational clock bounds.')
    return Fraction(numerator, denominator)


def time_string(value):
    value = Fraction(value)
    result = str(value.numerator) + (('/' + str(value.denominator)) if value.denominator != 1 else '') + 's'
    time_value(result, 'exported time')
    return result


def _number(value, label, low, high):
    try:
        if isinstance(value, bool) or not isinstance(value, (str, int, float)) or len(str(value)) > 80:
            raise ValueError()
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        _fail(label + ' must be numeric.')
    if not math.isfinite(result) or not low <= result <= high:
        _fail(label + ' is outside the supported bounds.')
    return result


def _integer(value, label, low, high):
    if not isinstance(value, str) or not re.fullmatch(r'[+-]?\d{1,12}', value):
        _fail(label + ' must be an integer.')
    number = int(value)
    if not low <= number <= high:
        _fail(label + ' is outside the supported bounds.')
    return number


def _pair(value, label, low, high):
    if not isinstance(value, str) or len(value.split()) != 2:
        _fail(label + ' requires two numeric values.')
    return tuple(_number(v, label, low, high) for v in value.split())


def _bool(value, label):
    if value not in {'0', '1'}:
        _fail(label + ' must be 0 or 1.')
    return value == '1'


def _native_number(value, label):
    """Never round an accepted rational clock into a different native value."""
    value = Fraction(value)
    result = float(value)
    if not math.isfinite(result) or Fraction(str(result)) != value:
        _fail(label + ' cannot be represented exactly by the native source clock. Use an exact decimal source frame/speed.')
    return int(value) if value.denominator == 1 else result


def _frames(value, rate, label, zero=False):
    frames = Fraction(value) * rate.fraction
    if frames.denominator != 1 or not (0 if zero else 1) <= frames <= rate.max_timeline_frames(21600):
        _fail(label + ' must fall on whole project frames inside the six-hour timeline.')
    return int(frames)


def _check(node, attrs=(), children=(), multiple=()):
    if set(node.attrib) - set(attrs):
        _fail('<' + node.tag + '> has unsupported attribute(s): ' + ', '.join(sorted(set(node.attrib) - set(attrs))))
    counts = {}
    for child in node:
        if child.tag not in children:
            _fail('<' + node.tag + '> contains unsupported <' + child.tag + '>; render or convert that edit explicitly before interchange.')
        if child.tag == 'note' and (child.attrib or len(child)):
            _fail('notes must contain plain text only.')
        if child.tail and child.tail.strip():
            _fail('unexpected text between XML elements.')
        counts[child.tag] = counts.get(child.tag, 0) + 1
        if counts[child.tag] > 1 and child.tag not in multiple:
            _fail('<' + node.tag + '> contains duplicate <' + child.tag + '>.')
    if node.tag != 'note' and node.text and node.text.strip():
        _fail('<' + node.tag + '> contains unexpected text.')
    return node


def _metadata(node):
    result = {}
    value = node.find('metadata')
    if value is None:
        return result
    _check(value, (), {'md'}, {'md'})
    if len(value) > 128:
        _fail('metadata exceeds 128 fields.')
    for item in value:
        _check(item, {'key', 'value', 'editable', 'type', 'displayName', 'description', 'source'})
        key = _text(item.get('key'), 'metadata key', 256)
        if key in result:
            _fail('metadata keys must be unique.')
        result[key] = item.get('value', '')
    return result


def _reference_label(value):
    value = _text(value, 'media reference', 4096)
    try:
        parsed = urlsplit(value)
    except ValueError:
        _fail('media reference is not a valid opaque URL label.')
    if parsed.scheme.lower() not in {'', 'file', 'http', 'https'}:
        _fail('media reference uses an unsupported URL scheme.')
    decoded = unquote(parsed.path)
    if '\x00' in decoded or '\\' in decoded or '..' in decoded.split('/'):
        _fail('media references cannot contain path traversal or backslashes.')
    return value


def _xml(document):
    if not isinstance(document, (str, bytes)):
        _fail('upload a standalone .fcpxml UTF-8 document.')
    try:
        data = document.encode('utf-8') if isinstance(document, str) else document
        text = data.decode('utf-8')
    except UnicodeError:
        _fail('documents must be valid UTF-8.')
    if not 1 <= len(data) <= MAX_BYTES:
        _fail('document exceeds the 8 MiB limit.')
    # FCP exports this name-only declaration. No external/internal DTD is read.
    cleaned = re.sub(r'<!DOCTYPE\s+fcpxml\s*>', '', text)
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)', cleaned, re.I):
        _fail('DTD references, entities and internal subsets are unsupported.')
    if re.search(r'<\?(?!xml\s)', cleaned, re.I):
        _fail('XML processing instructions are unsupported.')
    parser = ET.XMLPullParser(events=('start', 'end'))
    depth = count = 0
    root = None
    try:
        for offset in range(0, len(cleaned), 16384):
            parser.feed(cleaned[offset:offset+16384])
            for event, node in parser.read_events():
                if event == 'start':
                    depth += 1; count += 1
                    if root is None:
                        root = node
                    if depth > MAX_DEPTH or count > MAX_ELEMENTS or len(node.attrib) > 32:
                        _fail('XML exceeds its depth, element or attribute budget.')
                    if not isinstance(node.tag, str) or '{' in node.tag or ':' in node.tag:
                        _fail('namespaced or executable XML is unsupported.')
                    if any(len(k) > 100 or len(v) > 8192 for k, v in node.attrib.items()):
                        _fail('XML attribute is too large.')
                else:
                    depth -= 1
        parser.close()
    except ET.ParseError as error:
        _fail('invalid XML: ' + str(error)[:180])
    if root is None or root.tag != 'fcpxml' or root.get('version') not in {'1.9', '1.10'}:
        _fail('only standalone FCPXML 1.9 and 1.10 documents are supported.')
    return root, hashlib.sha256(data).hexdigest()


class Document:
    def __init__(self, document):
        self.root, self.sha256 = _xml(document)
        _check(self.root, {'version'}, {'resources', 'library', 'event', 'project', 'import-options'}, {'event'})
        resources = self.root.find('resources')
        if resources is None:
            _fail('the document requires explicit resources.')
        _check(resources, (), {'format', 'asset', 'media'}, {'format', 'asset', 'media'})
        if len(resources) > 1024:
            _fail('the resource inventory exceeds 1,024 items.')
        self.resources = {}
        for node in resources:
            ident = _id(node.get('id'))
            if ident in self.resources:
                _fail('resource IDs must be unique.')
            self.resources[ident] = node
        self.formats, self.assets, self.media = {}, {}, {}
        for ident, node in self.resources.items():
            if node.tag == 'format':
                self.formats[ident] = self.format(node)
        for ident, node in self.resources.items():
            if node.tag == 'asset':
                self.assets[ident] = self.asset(node)
            elif node.tag == 'media':
                _check(node, {'id', 'name', 'uid', 'modDate'}, {'sequence'})
                if len(node) != 1:
                    _fail('compound media must contain one explicit sequence; external media IDs are not loaded.')
                self.media[ident] = node
        if len(self.assets) > 512 or len(self.media) > 63:
            _fail('at most 512 assets and 63 compound resources can be reviewed.')
        projects = []
        def visit(node):
            if node.tag == 'project':
                _check(node, {'name', 'uid', 'id', 'modDate'}, {'sequence'})
                if len(node) != 1:
                    _fail('a project must contain one sequence.')
                projects.append(node); return
            if node.tag == 'library':
                _check(node, {'location', 'colorProcessing'}, {'event'}, {'event'})
                if node.get('colorProcessing', 'standard') != 'standard':
                    _fail('wide-gamut and HDR library color processing is unsupported.')
            elif node.tag == 'event':
                _check(node, {'name', 'uid'}, {'project'}, {'project'})
            for child in node:
                if child.tag in {'project', 'library', 'event'}:
                    visit(child)
        visit(self.root)
        if len(projects) != 1:
            _fail('choose a project-only XML containing exactly one project timeline.')
        self.project = projects[0]
        self.name = _text(self.project.get('name', 'Imported FCPXML'), 'project name')
        options = self.root.find('import-options')
        if options is not None:
            _check(options, (), {'option'}, {'option'})
            for option in options:
                _check(option, {'key', 'value'})
        self.warnings = [
            'Only already-imported project media is linked. FCPXML file paths, bookmarks, library locations and web addresses are never opened.',
            'Connected items become independent native lanes at their exact positions. Final Cut Pro magnetic follow relationships are not native editing relationships.',
            'Import returns an unsaved candidate; applying it is one undoable change. Existing sequences stay in the sequence library.',
            'Document/media identities and source clocks are retained as provenance. Notes, descriptive metadata and role labels are not native authoring or mixer fields.',
        ]
        if options is not None or self.root.find('library') is not None:
            self.warnings.append('Library/import-location directives are descriptive only and are not executed.')

    def format(self, node):
        _check(node, {'id', 'name', 'frameDuration', 'fieldOrder', 'width', 'height', 'paspH', 'paspV', 'colorSpace', 'projection', 'stereoscopic'})
        width = _integer(node.get('width'), 'format width', 16, 8192)
        height = _integer(node.get('height'), 'format height', 16, 8192)
        if width % 2 or height % 2 or width * height > 33554432:
            _fail('format dimensions require even sizes within the native canvas limit.')
        period = time_value(node.get('frameDuration'), 'format frameDuration')
        if period <= 0:
            _fail('format frameDuration must be positive.')
        rate = parse_rate({'numerator': period.denominator, 'denominator': period.numerator})
        if node.get('fieldOrder', 'progressive') != 'progressive':
            _fail('interlaced formats require an explicit progressive conversion.')
        if _integer(node.get('paspH', '1'), 'pixel aspect numerator', 1, 65536) != _integer(node.get('paspV', '1'), 'pixel aspect denominator', 1, 65536):
            _fail('non-square pixel aspect requires an explicit conversion.')
        if node.get('projection', 'none') != 'none' or node.get('stereoscopic', 'mono') != 'mono':
            _fail('360 and stereo formats are unsupported.')
        if node.get('colorSpace', '1-1-1 (Rec. 709)') not in {'1-1-1 (Rec. 709)', '1-1-1'}:
            _fail('only explicit SDR Rec.709 formats are supported.')
        return {'width': width, 'height': height, 'rate': rate}

    def asset(self, node):
        _check(node, {'id', 'name', 'uid', 'start', 'duration', 'hasVideo', 'format', 'hasAudio', 'videoSources', 'audioSources', 'audioChannels', 'audioRate'}, {'media-rep', 'metadata'}, {'media-rep'})
        reps = list(node.findall('media-rep'))
        originals = [r for r in reps if r.get('kind', 'original-media') == 'original-media']
        if len(originals) != 1:
            _fail('each asset requires exactly one original-media representation.')
        for rep in reps:
            _check(rep, {'kind', 'sig', 'src', 'suggestedFilename'}, {'bookmark'})
            if rep.get('kind', 'original-media') not in {'original-media', 'proxy-media'}:
                _fail('unknown media representation.')
            _reference_label(rep.get('src'))
            bookmark = rep.find('bookmark')
            if bookmark is not None:
                if bookmark.attrib or list(bookmark):
                    _fail('invalid media bookmark.')
        has_video = _bool(node.get('hasVideo', '0'), 'asset hasVideo')
        has_audio = _bool(node.get('hasAudio', '0'), 'asset hasAudio')
        if not has_video and not has_audio:
            _fail('an asset must declare picture or sound.')
        if has_video and node.get('format') not in self.formats:
            _fail('picture assets need an explicit supported format.')
        if node.get('videoSources', '1') != '1':
            _fail('multi-video-stream assets are unsupported.')
        metadata = _metadata(node)
        digest = metadata.get(SHA_KEY)
        if digest is not None and not re.fullmatch('[a-f0-9]{64}', digest):
            _fail('invalid media SHA-256 metadata.')
        duration = time_value(node.get('duration'), 'asset duration') if node.get('duration') is not None else None
        if duration is not None and duration <= 0:
            _fail('asset duration must be positive.')
        return {'node': node, 'name': _text(node.get('name', node.get('id')), 'asset name'),
                'start': time_value(node.get('start', '0s'), 'asset start'), 'duration': duration,
                'has_video': has_video, 'has_audio': has_audio, 'format': self.formats.get(node.get('format')),
                'target': originals[0].get('src'), 'sha256': digest,
                'audio_sources': _integer(node.get('audioSources', '1'), 'audio sources', 1, 255),
                'audio_channels': _integer(node.get('audioChannels', '2'), 'audio channels', 1, 64),
                'audio_rate': _integer(node.get('audioRate', '48000'), 'audio sample rate', 8000, 384000)}

    def references(self):
        counts = {}
        visited = set()
        def visit(node, path=()):
            if node.tag in {'asset-clip', 'video', 'audio'}:
                ident = node.get('ref')
                if ident not in self.assets:
                    _fail('a story element refers to an absent media asset.')
                counts[ident] = counts.get(ident, 0) + 1
            if node.tag == 'ref-clip':
                ident = node.get('ref')
                if ident not in self.media or ident in path or len(path) >= 8:
                    _fail('a compound reference is absent, cyclic or exceeds eight levels.')
                if ident not in visited:
                    visited.add(ident); visit(self.media[ident], path + (ident,))
            for child in node:
                visit(child, path)
        visit(self.project)
        return [{'target': ident, 'display_target': self.assets[ident]['target'], 'name': self.assets[ident]['name'],
                 'uses': count, 'hashes': [self.assets[ident]['sha256']] if self.assets[ident]['sha256'] else []}
                for ident, count in counts.items()]


def inspect_fcpxml(document):
    parsed = Document(document)
    return {'format': 'fcpxml', 'version': parsed.root.get('version'), 'name': parsed.name,
            'references': parsed.references(), 'sha256': parsed.sha256, 'warnings': parsed.warnings}



_GRID_CACHE = {}


def _picture_sampling(source_in, speed, duration, source_rate, project_rate_value, sampling):
    # FFmpeg's native fps stage rounds *input* timestamps. This is not a
    # general nearest evaluation of an FCP source-time curve. Admit only grids
    # whose decoded counter behavior has an independent discrete oracle.
    if source_rate != project_rate_value or (Fraction(source_in)*source_rate).denominator != 1:
        _fail('picture interchange requires matching source/project rates and an integer source-frame in point.')
    if speed not in {Fraction(1,4),Fraction(1,2),Fraction(1),Fraction(2)}:
        _fail('picture time maps support only proven 0.25×/0.5× floor-repeat, 1×, and exact-clock 2× grids; other speeds require an explicit render.')
    if speed < 1 and (Fraction(duration)*speed*source_rate).denominator != 1:
        _fail('slow picture maps require an integral consumed source-frame extent; partial repeat tails cannot preserve the selected duration.')
    if speed < 1 and sampling != 'floor':
        _fail('slow picture maps require explicit floor sampling; native repetition is not general nearest-neighbor interpolation.')


def _exact_double_grid(asset, directory, rate, last_frame):
    if not 1 <= last_frame <= 4096:
        _fail('2× picture exchange requires a proven source window within the first 4,096 source frames; render longer windows explicitly.')
    path = _media_path(directory,asset['path'])
    before = path.stat()
    identity = (str(path),before.st_size,before.st_mtime_ns,before.st_ctime_ns,before.st_ino,rate.numerator,rate.denominator)
    if _GRID_CACHE.get(identity,0) >= last_frame:
        return
    try:
        result = subprocess.run([_executable('ffprobe'),'-v','error','-protocol_whitelist','file,pipe',
            '-select_streams','v:0','-read_intervals','%+#'+str(last_frame+64),'-show_entries',
            'stream=time_base,avg_frame_rate,r_frame_rate:frame=pts,best_effort_timestamp','-show_frames','-of','json',str(path)],
            capture_output=True,check=True,timeout=8)
        if len(result.stdout) > 1024*1024:
            _fail('source clock proof exceeded its bounded output budget.')
        value = json.loads(result.stdout)
        streams = value.get('streams',[])
        if len(streams) != 1:
            raise ValueError('one picture stream required')
        stream = streams[0]
        clock = Fraction(stream['time_base'])
        if Fraction(stream['avg_frame_rate']) != rate.fraction or Fraction(stream['r_frame_rate']) != rate.fraction:
            raise ValueError('source rate declarations differ')
        frames = value.get('frames',[])
        if any(frame.get('pts') != frame.get('best_effort_timestamp') for frame in frames):
            raise ValueError('decoded timestamps require estimation')
        times = [Fraction(frame['pts'])*clock for frame in frames]
        if len(times) < last_frame or any(times[index] != Fraction(index,1)/rate.fraction for index in range(last_frame)):
            raise ValueError('decoded presentation timestamps are not exact consecutive frame ticks')
    except (OSError,subprocess.SubprocessError,ValueError,KeyError,TypeError,ZeroDivisionError) as error:
        _fail('2× picture source clock is not proven exact; quantized, variable-rate or ambiguous timestamps require an explicit render. '+str(error)[:160])
    after = path.stat()
    if (before.st_size,before.st_mtime_ns,before.st_ctime_ns,before.st_ino) != (after.st_size,after.st_mtime_ns,after.st_ctime_ns,after.st_ino):
        _fail('source media changed during clock verification.')
    if len(_GRID_CACHE) >= 128:
        _GRID_CACHE.pop(next(iter(_GRID_CACHE)))
    _GRID_CACHE[identity] = last_frame


class Importer:
    def __init__(self, document, project, project_dir, asset_map):
        self.doc = Document(document)
        self.base = io._validated_project(project, project_dir)
        self.directory = project_dir
        self.owned = {a['id']: a for a in self.base['assets']}
        refs = {r['target'] for r in self.doc.references()}
        if asset_map is None:
            asset_map = {}
        if not isinstance(asset_map, dict) or len(asset_map) > 512 or any(k not in refs or not isinstance(v, str) or v not in self.owned for k, v in asset_map.items()):
            _fail('media mapping must name referenced XML resource IDs and already-imported asset IDs.')
        self.mapping = dict(asset_map)
        hashes = {}
        for ident in refs:
            source = self.doc.assets[ident]
            if ident not in self.mapping:
                if not source['sha256']:
                    _fail('relink ' + ident + ' (' + source['name'] + ') to an already-imported asset.')
                matches = []
                for asset_id, asset in self.owned.items():
                    if asset_id not in hashes:
                        hashes[asset_id] = io._sha256(_media_path(project_dir, asset['path']))
                    if hashes[asset_id] == source['sha256']:
                        matches.append(asset_id)
                if len(matches) != 1:
                    _fail('media hash for ' + ident + ' has no unique imported match; choose an explicit relink.')
                self.mapping[ident] = matches[0]
            actual = self.owned[self.mapping[ident]]
            if source['has_video'] != (actual['kind'] in {'video', 'image'}) or source['has_audio'] != bool(actual['has_audio']):
                _fail('relinked media component types differ for ' + ident + '.')
            if source['format'] and (actual['width'], actual['height']) != (source['format']['width'], source['format']['height']):
                _fail('relinked picture dimensions differ for ' + ident + '.')
            if actual['kind'] == 'video' and Fraction(actual['fps']) != source['format']['rate'].fraction:
                _fail('relinked source frame rate differs for ' + ident + '.')
            if source['sha256'] and io._sha256(_media_path(project_dir, actual['path'])) != source['sha256']:
                self.doc.warnings.append('Explicit relink for ' + ident + ' uses different content from its recorded SHA-256; type, dimensions and source windows are still checked.')
        sequence = self.doc.project.find('sequence')
        fmt = self.doc.formats.get(sequence.get('format'))
        if fmt is None:
            _fail('the project sequence requires a supported format resource.')
        self.rate, self.width, self.height = fmt['rate'], fmt['width'], fmt['height']
        self.sequences, self.compounds, self.origins = {}, {}, {}
        self.events = 0

    def format_matches(self, ident):
        if ident not in self.doc.formats:
            _fail('an item refers to an absent format.')
        fmt = self.doc.formats[ident]
        if (fmt['rate'], fmt['width'], fmt['height']) != (self.rate, self.width, self.height):
            _fail('nested/container formats must match the project clock and dimensions; explicitly conform them first.')

    def timing(self, node, duration, origin, source_rate=None):
        start = time_value(node.get('start', '0s'), 'clip start')
        lower, upper, speed, reverse = start, start + duration, Fraction(1), False
        conform = node.find('conform-rate')
        sampling = None
        if conform is not None:
            _check(conform, {'scaleEnabled', 'srcFrameRate', 'frameSampling'})
            if _bool(conform.get('scaleEnabled', '1'), 'rate conform scaleEnabled'):
                _fail('automatic rate conform is unsupported; disable rate scaling explicitly.')
            if conform.get('srcFrameRate') is not None:
                labels = {'23.98': Fraction(24000,1001), '24': Fraction(24), '25': Fraction(25), '29.97': Fraction(30000,1001), '30': Fraction(30), '47.95': Fraction(48000,1001), '48': Fraction(48), '50': Fraction(50), '59.94': Fraction(60000,1001), '60': Fraction(60)}
                if conform.get('srcFrameRate') not in labels or source_rate is not None and labels[conform.get('srcFrameRate')] != source_rate:
                    _fail('rate conform source rate conflicts with the linked media.')
            sampling = conform.get('frameSampling', 'floor')
        elif source_rate is not None and source_rate != self.rate.fraction:
            _fail('mixed-rate picture needs explicit conform-rate scaleEnabled="0" and supported frame sampling.')
        mapping = node.find('timeMap')
        if mapping is not None:
            _check(mapping, {'frameSampling', 'preservesPitch'}, {'timept'}, {'timept'})
            if not _bool(mapping.get('preservesPitch', '1'), 'timeMap preservesPitch'):
                _fail('varispeed pitch changes are unsupported by this interchange; use pitch-preserving constant retimes.')
            if not 2 <= len(mapping) <= 128:
                _fail('a time map needs 2–128 collinear linear points.')
            points = []
            for point in mapping:
                _check(point, {'time', 'value', 'interp'})
                if point.get('interp', 'smooth2') != 'linear':
                    _fail('smooth, ramp and freeze time maps are unsupported; every point must be linear.')
                points.append((time_value(point.get('time'), 'time point'), time_value(point.get('value'), 'source time point')))
            if any(b[0] <= a[0] for a, b in zip(points, points[1:])):
                _fail('time map output points must increase strictly.')
            slope = (points[-1][1] - points[0][1]) / (points[-1][0] - points[0][0])
            if not Fraction(1,4) <= abs(slope) <= 4 or any(y != points[0][1] + (x-points[0][0])*slope for x,y in points):
                _fail('only a single bounded positive linear speed is supported; ramps and holds require an explicit render.')
            if start < points[0][0] or start + duration > points[-1][0]:
                _fail('the entire selected clip range must lie inside its explicit time map.')
            if slope < 0:
                _fail('negative time maps require an external Final Cut Pro numbered-frame sampling oracle; reverse XML exchange is not certified.')
            if conform is not None and conform.get('frameSampling','floor') != mapping.get('frameSampling','floor'):
                _fail('conform-rate and timeMap frameSampling must match, as required by FCPXML.')
            first = points[0][1] + (start-points[0][0])*slope
            last = first + duration*slope
            lower, upper, speed, reverse = min(first,last), max(first,last), abs(slope), slope < 0
            sampling = mapping.get('frameSampling', 'floor')
        if sampling not in {None, 'floor', 'nearest-neighbor'}:
            _fail('frame blending and optical-flow sampling cannot be exchanged as native constant retimes.')
        # Floor and nearest agree only on an integral source-frame grid. An
        # arbitrary floor curve must not silently become native nearest-neighbor.
        if source_rate is not None:
            _picture_sampling(lower-origin,speed,duration,source_rate,self.rate.fraction,sampling or 'floor')
        if lower < origin:
            _fail('a selected source window precedes its media/timecode origin.')
        return {'in': _native_number((lower-origin)*self.rate.fraction, 'source in'),
                'speed': _native_number(speed, 'speed'), 'reverse': reverse}, start, upper

    def adjustments(self, node, picture, source_size):
        result = {}
        conform = node.find('adjust-conform')
        if conform is not None:
            _check(conform, {'type'})
            if not picture or conform.get('type', 'fit') != 'fit':
                _fail('only picture spatial conform fit is supported.')
        transform = node.find('adjust-transform')
        if transform is not None:
            _check(transform, {'enabled', 'position', 'scale', 'rotation', 'anchor'})
            if not picture or not _bool(transform.get('enabled', '1'), 'transform enabled'):
                _fail('disabled or audio-only transforms are unsupported; remove the unused adjustment explicitly.')
            position = _pair(transform.get('position', '0 0'), 'position', -1000, 1000)
            scale = _pair(transform.get('scale', '1 1'), 'scale', .02, 4)
            rotation = _number(transform.get('rotation', '0'), 'rotation', -360, 360)
            if _pair(transform.get('anchor', '0 0'), 'anchor', -1000, 1000) != (0,0) or scale[0] != scale[1]:
                _fail('noncentral anchors and nonuniform scale are unsupported.')
            if (position != (0,0) or scale != (1,1) or rotation) and source_size != (self.width,self.height):
                _fail('nonidentity transforms require source and sequence dimensions to match; explicitly conform the source first.')
            result.update(x=position[0]*self.height/(100*self.width), y=-position[1]/100,
                          scale=scale[0], rotation=-rotation)
        blend = node.find('adjust-blend')
        if blend is not None:
            _check(blend, {'amount', 'mode'})
            if not picture or blend.get('mode', 'normal') != 'normal':
                _fail('only normal picture compositing is supported.')
            result['opacity'] = _number(blend.get('amount', '1'), 'opacity', 0, 1)
        volume = node.find('adjust-volume')
        if volume is not None:
            _check(volume, {'amount'})
            amount = volume.get('amount', '0dB')
            if not amount.endswith('dB'):
                _fail('audio level must be a static dB value.')
            result['volume'] = 10 ** (_number(amount[:-2], 'audio dB', -120, 12.041199826559248) / 20)
            if result['volume'] > 4 + 1e-12:
                _fail('audio level exceeds native 4× gain.')
            result['volume'] = min(4, result['volume'])
        return result

    def finish_sequence(self, ident, name, clips, duration, origin, tc_format='NDF'):
        picture_keys = sorted({c['_z'] for c in clips if c['_picture']})
        sound_keys = sorted({c['_z'] for c in clips if not c['_picture']})
        if len(picture_keys) > 16 or len(sound_keys) > 16 or len(clips) > 256:
            _fail('each sequence supports at most 256 clips and 16 picture/16 audio lanes.')
        lanes = {}
        for clip in clips:
            key = (clip['_picture'], clip['_z'])
            lane = picture_keys.index(clip['_z']) if clip['_picture'] else -1-sound_keys.index(clip['_z'])
            for prior in lanes.setdefault(key, []):
                if clip['start'] < prior['start']+prior['duration'] and prior['start'] < clip['start']+clip['duration']:
                    _fail('overlapping items on the same FCPXML lane are ambiguous; use separate explicit connected lanes.')
            lanes[key].append(clip)
            clip['track'] = lane
        for clip in clips:
            clip.pop('_z'); clip.pop('_picture')
            if clip['start'] + clip['duration'] > duration:
                _fail('an item exceeds its containing sequence; an explicit trim is required.')
        tracks = [{'id': i, 'name': ('FCPXML V'+str(i+1)) if i >= 0 else ('FCPXML A'+str(-i)), 'mute':False, 'solo':False, 'locked':False, 'gain':1}
                  for i in sorted({c['track'] for c in clips})]
        self.sequences[ident] = {'id':ident, 'name':name, 'clips':clips, 'titles':[], 'tracks':tracks, 'captions':[], 'sequence_duration':duration}
        self.origins[ident] = {'tcStart':time_string(origin), 'tcFormat':tc_format}
        return ident

    def sequence(self, node, name, path=()):
        _check(node, {'format','duration','tcStart','tcFormat','audioLayout','audioRate','renderFormat','keywords'}, {'note','spine','metadata'})
        self.format_matches(node.get('format'))
        if node.get('audioLayout', 'stereo') != 'stereo' or node.get('audioRate', '48k') != '48k':
            _fail('sequence output must be stereo at 48 kHz.')
        tc_format = node.get('tcFormat', 'NDF')
        if tc_format not in {'NDF','DF'} or tc_format == 'DF' and self.rate.fraction not in {Fraction(30000,1001),Fraction(60000,1001)}:
            _fail('drop-frame display requires an exact NTSC-compatible project clock.')
        origin = time_value(node.get('tcStart','0s'),'sequence timecode origin')
        if (origin*self.rate.fraction).denominator != 1:
            _fail('sequence timecode origin must be a whole project frame.')
        spine = node.find('spine')
        if spine is None:
            _fail('a sequence needs a primary spine.')
        clips = []
        end = self.spine(spine, clips, -origin, (), path, primary=True)
        duration = _frames(time_value(node.get('duration'),'sequence duration'),self.rate,'sequence duration',True) if node.get('duration') is not None else end
        if duration < end:
            _fail('the declared sequence duration truncates authored content; trim it explicitly.')
        _metadata(node)
        return self.finish_sequence(uuid.uuid4().hex, name, clips, duration, origin, tc_format)

    def spine(self, node, clips, shift, z, path, primary=False):
        _check(node, {'lane','offset','name','format'}, _STORY-{'spine'}, _STORY-{'spine'})
        if node.get('format') is not None:
            self.format_matches(node.get('format'))
        if primary and (_integer(node.get('lane','0'),'primary lane',-64,64) != 0 or time_value(node.get('offset','0s')) != 0):
            _fail('a sequence primary spine must use its default lane and offset.')
        intervals, end = [], 0
        for item in node:
            if _integer(item.get('lane','0'),'spine item lane',-64,64) != 0:
                _fail('spine items must be contained lane 0; place connections inside their anchor.')
            offset = time_value(item.get('offset','0s'),'spine item offset')
            duration = self.duration(item)
            for a,b in intervals:
                if offset < b and a < offset+duration:
                    _fail('primary/secondary spine overlaps require a transition or separate connected lanes, which cannot be silently flattened.')
            intervals.append((offset,offset+duration))
            end = max(end, self.item(item, clips, shift+offset, z, path))
        return end

    def duration(self, node):
        if node.get('duration') is not None:
            result = time_value(node.get('duration'),'clip duration')
        elif node.tag == 'asset-clip' and node.get('ref') in self.doc.assets:
            result = self.doc.assets[node.get('ref')]['duration']
        else:
            result = None
        if result is None or result <= 0:
            _fail('story elements require an explicit positive duration (or an asset duration).')
        _frames(result,self.rate,'clip duration')
        return result

    def item(self, node, clips, location, z, path):
        self.events += 1
        if self.events > MAX_EVENTS or len(path) >= 8:
            _fail('the document exceeds 4,096 authored items or eight nested levels.')
        allowed = set(_BASE_ATTRS)
        if node.tag in {'asset-clip','ref-clip'}:
            allowed |= {'ref','srcEnable','audioStart','audioDuration','modDate'}
        if node.tag == 'asset-clip':
            allowed |= {'format','tcStart','tcFormat','audioRole','videoRole'}
        elif node.tag == 'ref-clip':
            allowed |= {'useAudioSubroles'}
        elif node.tag in {'video','audio'}:
            allowed |= {'ref','srcID','role'}
            if node.tag == 'audio':
                allowed |= {'srcCh','outCh'}
        elif node.tag == 'clip':
            allowed |= {'format','audioStart','audioDuration','tcStart','tcFormat','modDate'}
        elif node.tag == 'gap':
            allowed.discard('lane')
        else:
            _fail('unsupported story element '+node.tag)
        children = _STORY | _TIMING | _ADJUST | _DESCRIPTIVE
        if node.tag == 'gap':
            children = (_STORY-{'gap'}) | _DESCRIPTIVE
        elif node.tag == 'audio':
            children = (_STORY-{'gap'}) | _TIMING | {'note','adjust-volume'}
        elif node.tag == 'video':
            children = (_STORY-{'gap'}) | _TIMING | {'note','adjust-conform','adjust-transform','adjust-blend'}
        elif node.tag != 'clip':
            children.discard('gap')
        _check(node,allowed,children,_STORY)
        if not _bool(node.get('enabled','1'),'clip enabled'):
            _fail('disabled story elements must be removed or enabled explicitly before this interchange.')
        if node.get('format') is not None:
            self.format_matches(node.get('format'))
        if node.get('tcFormat') not in {None,'NDF','DF'}:
            _fail('unsupported clip timecode display format.')
        if node.get('useAudioSubroles','0') != '0' or node.get('srcID','1') != '1' or node.get('srcCh') is not None or node.get('outCh') is not None:
            _fail('role-based or custom source/channel audio routing is unsupported.')
        duration = self.duration(node)
        start_frame, duration_frames = _frames(location,self.rate,'timeline position',True), _frames(duration,self.rate,'clip duration')
        local_start = time_value(node.get('start','0s'),'clip start')
        if node.get('audioStart') is not None and time_value(node.get('audioStart')) != local_start or node.get('audioDuration') is not None and time_value(node.get('audioDuration')) != duration:
            _fail('J/L audio splits require explicit separate audio and video elements.')
        anchors = [child for child in node if child.tag in _STORY and _integer(child.get('lane','0'),'connected lane',-64,64) != 0]
        contained = [child for child in node if child.tag in _STORY and child not in anchors]
        if contained and node.tag != 'clip':
            _fail('only clip containers accept contained lane-0 story elements.')
        if node.find('timeMap') is not None and anchors:
            _fail('anchored descendants on a retimed parent must be made independent explicitly before interchange.')
        extent = start_frame+duration_frames
        if node.tag != 'gap':
            source_rate = self.rate.fraction
            if node.tag in {'asset-clip','video','audio'}:
                ident = node.get('ref')
                if ident not in self.mapping:
                    _fail('missing media relink for '+str(ident))
                resource, actual = self.doc.assets[ident], self.owned[self.mapping[ident]]
                mode = node.get('srcEnable','all') if node.tag == 'asset-clip' else ('video' if node.tag == 'video' else 'audio')
                if mode not in {'all','video','audio'}:
                    _fail('unsupported source enable mode.')
                picture = mode != 'audio' and resource['has_video']
                sound = mode != 'video' and resource['has_audio']
                if not picture and not sound or mode == 'video' and not picture or mode == 'audio' and not sound:
                    _fail('selected source component does not exist.')
                if sound and (resource['audio_sources'] != 1 or resource['audio_channels'] not in {1,2} or len(actual.get('audio_streams',[])) != 1 or actual.get('audio_channels') != resource['audio_channels'] or actual.get('audio_sample_rate') != resource['audio_rate']):
                    _fail('audio requires one matching mono/stereo stream with its actual sample rate.')
                source_origin = resource['start']
                source_size = (actual.get('width'),actual.get('height'))
                source_rate = resource['format']['rate'].fraction if picture and actual['kind'] != 'image' else None
                reference = {'asset_id':self.mapping[ident]}
                timing, local_start, upper = self.timing(node,duration,source_origin,source_rate)
                if actual['kind'] == 'image':
                    if timing['in'] != 0 or timing['speed'] != 1 or timing['reverse']:
                        _fail('stills require zero source in and normal speed.')
                elif resource['duration'] is None or upper-source_origin > resource['duration']:
                    _fail('selected media window exceeds the declared asset extent.')
                if picture and timing['speed'] == 2 and actual['kind'] != 'image':
                    _exact_double_grid(actual,self.directory,self.rate,int((upper-source_origin)*self.rate.fraction))
                provenance = {'document_sha256':self.doc.sha256,'resource_id':ident,'source_start':time_string(source_origin),
                              'media_reference':resource['target'], 'source_sha256':io._sha256(_media_path(self.directory,actual['path']))}
            elif node.tag == 'ref-clip':
                ident = node.get('ref')
                if ident not in self.doc.media or ident in path:
                    _fail('absent or cyclic compound reference.')
                if ident not in self.compounds:
                    self.compounds[ident] = self.sequence(self.doc.media[ident].find('sequence'),_text(self.doc.media[ident].get('name',ident),'compound name'),path+(ident,))
                child_id = self.compounds[ident]
                source_origin = time_value(self.origins[child_id]['tcStart'])
                timing,local_start,upper = self.timing(node,duration,source_origin,self.rate.fraction)
                if upper-source_origin > Fraction(self.sequences[child_id]['sequence_duration'],1)/self.rate.fraction:
                    _fail('compound source window exceeds its sequence.')
                mode = node.get('srcEnable','all')
                if mode not in {'all','video','audio'}:
                    _fail('unsupported compound component mode.')
                picture,sound = mode != 'audio',mode != 'video'
                source_size = (self.width,self.height)
                reference = {'sequence_id':child_id}
                provenance = {'document_sha256':self.doc.sha256,'resource_id':ident,'source_start':time_string(source_origin)}
            else:
                if len(contained) != 1:
                    _fail('generic clip containers need exactly one contained primary item or spine.')
                child = contained[0]
                child_offset = time_value(child.get('offset','0s'))
                # Keep the container's own selected window; contained items are
                # rendered in a real nested sequence, so trimming/alpha remain live.
                source_origin = min(local_start,child_offset)
                child_clips = []
                if child.tag == 'spine':
                    child_end = self.spine(child,child_clips,child_offset-source_origin,(),path+('container',))
                else:
                    child_end = self.item(child,child_clips,child_offset-source_origin,(),path+('container',))
                timing,local_start,upper = self.timing(node,duration,source_origin,self.rate.fraction)
                child_end = max(child_end,_frames(upper-source_origin,self.rate,'container extent',True))
                child_id = self.finish_sequence(uuid.uuid4().hex,_text(node.get('name','FCPXML container'),'container name'),child_clips,child_end,source_origin)
                reference = {'sequence_id':child_id}; picture = sound = True
                source_size = (self.width,self.height)
                provenance = {'document_sha256':self.doc.sha256,'source_start':time_string(source_origin)}
            adjustment = self.adjustments(node,picture,source_size)
            if not sound and adjustment.get('volume',1) != 1:
                _fail('audio gain is attached to a picture-only element.')
            clip = {'id':uuid.uuid4().hex,**reference,'start':start_frame,'duration':duration_frames,
                    **timing,**adjustment,'_picture':picture,'_z':z+(0,), 'fcpxml':provenance}
            if not sound:
                clip['volume'] = 0
            clips.append(clip)
        for child in anchors:
            lane = _integer(child.get('lane'),'connected lane',-64,64)
            offset = time_value(child.get('offset','0s'),'connected offset')
            child_location = location+offset-local_start
            if child.tag == 'spine':
                extent = max(extent,self.spine(child,clips,child_location,z+(lane,),path))
            else:
                extent = max(extent,self.item(child,clips,child_location,z+(lane,),path))
        _metadata(node)
        return extent

    def run(self):
        active = self.sequence(self.doc.project.find('sequence'),self.doc.name)
        old = sequence_views(self.base)
        old_nonempty = any(sequence_duration(s) or s.get('clips') or s.get('titles') or s.get('captions') for s in old.values())
        if (project_rate(self.base),self.base['width'],self.base['height']) != (self.rate,self.width,self.height):
            if old_nonempty or self.base.get('sequences') or self.base.get('multicam_groups'):
                _fail('existing sequences share the project clock/canvas. Import this different format into an empty project.')
            old = {}
        candidate = copy.deepcopy(self.base)
        selected = self.sequences[active]
        candidate.update(name=self.doc.name, fps=self.rate.fps, frame_rate=self.rate.as_dict(),width=self.width,height=self.height,
                         sequence_id=active,sequence_name=selected['name'])
        for key in ('clips','titles','tracks','captions','sequence_duration'):
            candidate[key] = copy.deepcopy(selected[key])
        candidate.pop('caption_style',None); candidate.pop('otio_dissolve',None)
        candidate['sequences'] = list(old.values()) + [s for ident,s in self.sequences.items() if ident != active]
        settings = candidate.setdefault('settings',{})
        origins = {}
        retained = self.base.get('settings',{}).get('fcpxml')
        if retained is not None:
            if not isinstance(retained,dict) or retained.get('version') != 1 or not isinstance(retained.get('sequence_origins'),dict) or len(retained['sequence_origins']) > 64:
                _fail('invalid retained FCPXML timecode provenance; it cannot be silently discarded.')
            for ident,item in retained['sequence_origins'].items():
                if ident not in old:
                    continue
                if not isinstance(item,dict) or set(item) != {'tcStart','tcFormat'} or item['tcFormat'] not in {'DF','NDF'}:
                    _fail('invalid retained sequence timecode origin.')
                prior_origin = time_value(item['tcStart'],'retained sequence origin')
                if (prior_origin*self.rate.fraction).denominator != 1 or item['tcFormat'] == 'DF' and self.rate.fraction not in {Fraction(30000,1001),Fraction(60000,1001)}:
                    _fail('retained sequence timecode does not match the project clock.')
                origins[ident] = copy.deepcopy(item)
        origins.update(self.origins)
        settings['fcpxml'] = {'version':1,'document_sha256':self.doc.sha256,'sequence_origins':origins,
                              'source_version':self.doc.root.get('version'),'connected_relationships':'independent_native_lanes'}
        settings['timecode_mode'] = 'df' if self.origins[active]['tcFormat'] == 'DF' else 'ndf'
        if settings.get('image_precision') == 'float32' or settings.get('transparent_background'):
            _fail('import into an SDR project with an opaque movie background; HDR/scene-linear project settings do not translate through this workflow.')
        return {'project':io._validated_project(candidate,self.directory),'warnings':list(dict.fromkeys(self.doc.warnings)),
                'format':'fcpxml','document_sha256':self.doc.sha256}


def import_fcpxml(document, project, project_dir, asset_map=None):
    return Importer(document,project,project_dir,asset_map).run()


def _num(value):
    return format(float(value), '.17g')


def _media_extent(asset):
    """Recover a bounded source-clock fraction from FFprobe's decimal duration.

    Clip positions never use this approximation: they are exact native frame
    fractions. The extent is only the source availability declaration, resolved
    to within one nanosecond of the probed duration.
    """
    raw = Fraction(str(asset['duration']))
    value = raw.limit_denominator(1_000_000_000)
    if value <= 0 or abs(value-raw) > Fraction(1,1_000_000_000):
        _fail('source duration cannot be declared on a bounded rational clock.')
    time_string(value)
    return value


class Exporter:
    def __init__(self, project, project_dir):
        self.project = io._validated_project(project,project_dir)
        self.directory = project_dir
        self.rate = project_rate(self.project)
        self.width,self.height = self.project['width'],self.project['height']
        if self.project.get('settings',{}).get('image_precision') == 'float32' or self.project.get('settings',{}).get('transparent_background'):
            _fail('scene-linear/HDR or transparent project output is not represented by this SDR XML workflow.')
        self.views = sequence_views(self.project)
        self.assets = {a['id']:a for a in self.project['assets']}
        self.root = ET.Element('fcpxml',version='1.10')
        self.resources = ET.SubElement(self.root,'resources')
        self.formats,self.media,self.compounds = {},{},{}
        self.hashes = {}
        self.warnings = [
            'FCPXML exchanges the active timeline and reachable compound sequences using public edits. Media is referenced, not embedded; relink project-relative media URLs in the receiving editor.',
            'Independent native lanes are exported as connections to a full-duration gap spine. No magnetic-follow editing relationship or inactive sequence library is promised.',
            'Only the documented SDR subset is exchanged. Apple DTD validation does not certify import/render behavior in an installed Final Cut Pro application.',
            'The native final audio limiter and tempo/filter implementations are not encoded in XML. Receiving-editor audio DSP is not certified sample-identical; use rendered stems when that processing must be preserved.',
        ]
        self.origins = {}
        provenance = self.project.get('settings',{}).get('fcpxml')
        if provenance is not None:
            if not isinstance(provenance,dict) or provenance.get('version') != 1 or not isinstance(provenance.get('sequence_origins'),dict) or len(provenance['sequence_origins']) > 64:
                _fail('invalid retained FCPXML timecode provenance.')
            for ident,item in provenance['sequence_origins'].items():
                if ident not in self.views:
                    continue
                if not isinstance(item,dict) or set(item) != {'tcStart','tcFormat'} or item['tcFormat'] not in {'DF','NDF'}:
                    _fail('invalid retained sequence timecode origin.')
                value = time_value(item['tcStart'],'retained sequence origin')
                if (value*self.rate.fraction).denominator != 1:
                    _fail('retained sequence origin is not on a project frame.')
                self.origins[ident] = (value,item['tcFormat'])

    def resource_id(self):
        return 'r'+str(len(self.resources)+1)

    def format(self,width,height,rate):
        key = width,height,rate.numerator,rate.denominator
        if key not in self.formats:
            ident = self.resource_id()
            ET.SubElement(self.resources,'format',id=ident,name=f'CINEMATICUM {width}x{height} {rate.ffmpeg}',
                          frameDuration=time_string(1/rate.fraction),width=str(width),height=str(height),
                          fieldOrder='progressive',colorSpace='1-1-1 (Rec. 709)')
            self.formats[key] = ident
        return self.formats[key]

    def asset(self,clip):
        asset = self.assets[clip['asset_id']]
        if asset['id'] not in self.hashes:
            self.hashes[asset['id']] = io._sha256(_media_path(self.directory,asset['path']))
        origin = Fraction(0)
        provenance = clip.get('fcpxml')
        if provenance is not None:
            if not isinstance(provenance,dict):
                _fail('invalid clip source-clock provenance.')
            if provenance.get('source_start') is not None:
                if provenance.get('source_sha256') == self.hashes[asset['id']]:
                    origin = time_value(provenance['source_start'],'retained media origin')
                else:
                    self.warnings.append('A relinked clip has different media bytes; its stale source timecode origin was reset to zero.')
        key = asset['id'],origin
        if key in self.media:
            return self.media[key],origin,asset
        picture = asset['kind'] in {'video','image'}
        if asset['kind'] not in {'video','audio','image'}:
            _fail('render scene resources to movie media before XML interchange.')
        fmt = None
        if picture:
            source_rate = self.rate if asset['kind'] == 'image' else parse_rate(Fraction(asset['fps']))
            fmt = self.format(asset['width'],asset['height'],source_rate)
        ident = self.resource_id()
        extent = Fraction(self.rate.max_timeline_frames(21600),1)/self.rate.fraction if asset['kind'] == 'image' else _media_extent(asset)
        attrs = {'id':ident,'name':asset['name'],'start':time_string(origin),'duration':time_string(extent),
                 'hasVideo':'1' if picture else '0','hasAudio':'1' if asset['has_audio'] else '0'}
        if picture:
            attrs.update(format=fmt,videoSources='1')
        if asset['has_audio']:
            attrs.update(audioSources=str(len(asset['audio_streams'])),audioChannels=str(asset['audio_channels']),audioRate=str(asset['audio_sample_rate']))
        node = ET.SubElement(self.resources,'asset',attrs)
        label = _reference_label(quote(asset['path'],safe='/'))
        ET.SubElement(node,'media-rep',kind='original-media',src=label)
        metadata = ET.SubElement(node,'metadata')
        ET.SubElement(metadata,'md',key=SHA_KEY,value=self.hashes[asset['id']])
        self.media[key] = ident
        return ident,origin,asset

    def check_clip(self,clip,asset):
        if clip['reverse']:
            _fail('native reverse requires an external Final Cut Pro numbered-frame endpoint oracle before FCPXML export; render that clip or use native/OTIO interchange.')
        if any(clip.get(k) is not None for k in ('compositor','tracking','planar_motion','color_pipeline','learned_recipe','learned_bindings','retime','multicam')):
            _fail('clip graphs, tracking, color pipelines, learned bindings, multicamera and speed ramps must be rendered explicitly before FCPXML export.')
        if clip['grade'] != _ZERO_GRADE or any(clip['effects'].values()) or clip['keyframes']:
            _fail('grades, effects and keyframes are not represented by this FCPXML subset.')
        audio = clip['audio']
        if audio['fade_in'] or audio['fade_out'] or audio['pan'] or audio.get('channels') is not None or audio.get('stream_index') is not None:
            _fail('audio fades, pan, channel mapping or selected streams need an explicit rendered stem.')
        picture = clip['track'] >= 0
        sound = bool(asset['has_audio']) and clip['volume'] != 0
        if sound and (len(asset.get('audio_streams',[])) != 1 or asset.get('audio_channels') not in {1,2}) and asset['kind'] != 'sequence':
            _fail('active audio needs one mono/stereo stream for FCPXML export.')
        if not picture and not sound:
            _fail('zero-gain audio-only clips have no exact public mute representation in this subset; remove or render them explicitly.')
        if picture and any(clip[k] != value for k,value in (('x',0),('y',0),('scale',1),('rotation',0))) and (asset['width'],asset['height']) != (self.width,self.height):
            _fail('nonidentity transforms need matching source/sequence dimensions for exact Apple coordinate conversion.')
        if not picture and any(clip[k] != value for k,value in (('x',0),('y',0),('scale',1),('rotation',0),('opacity',1))):
            _fail('remove unused picture adjustments from audio-only clips before interchange.')
        return picture,sound

    def clip(self,parent,clip,origin,lane):
        if clip.get('sequence_id'):
            child_id = clip['sequence_id']
            ref = self.compound(child_id)
            source_origin = self.origins.get(child_id,(Fraction(0),'NDF'))[0]
            asset = {'kind':'sequence','has_audio':True,'width':self.width,'height':self.height}
            tag,name = 'ref-clip',self.views[child_id]['name']
        else:
            ref,source_origin,asset = self.asset(clip)
            tag,name = 'asset-clip',asset['name']
        picture,sound = self.check_clip(clip,asset)
        duration = Fraction(clip['duration'],1)/self.rate.fraction
        sampling = 'nearest-neighbor'
        if picture and asset['kind'] != 'image':
            source_rate = self.rate.fraction if asset['kind'] == 'sequence' else Fraction(asset['fps'])
            sampling = 'floor' if clip['speed'] in {.25,.5} else 'nearest-neighbor'
            _picture_sampling(Fraction(str(clip['in']))/self.rate.fraction,Fraction(str(clip['speed'])),duration,source_rate,self.rate.fraction,sampling)
            if clip['speed'] == 2 and asset['kind'] != 'sequence':
                _exact_double_grid(asset,self.directory,self.rate,int(Fraction(str(clip['in']))+clip['duration']*Fraction(str(clip['speed']))))
        source_start = source_origin + Fraction(str(clip['in']))/self.rate.fraction
        speed = Fraction(str(clip['speed']))
        # The adjusted local clock begins at the selected source start. A
        # positive constant map then declares the exact selected source extent.
        attrs = {'ref':ref,'name':name,'lane':str(lane),'offset':time_string(origin+Fraction(clip['start'],1)/self.rate.fraction),
                 'start':time_string(source_start),'duration':time_string(duration),
                 'srcEnable':'all' if picture and sound else ('video' if picture else 'audio')}
        node = ET.SubElement(parent,tag,attrs)
        ET.SubElement(node,'conform-rate',scaleEnabled='0',frameSampling=sampling)
        if speed != 1:
            mapping = ET.SubElement(node,'timeMap',frameSampling=sampling,preservesPitch='1')
            ET.SubElement(mapping,'timept',time=time_string(source_start),value=time_string(source_start),interp='linear')
            ET.SubElement(mapping,'timept',time=time_string(source_start+duration),value=time_string(source_start+duration*speed),interp='linear')
        if picture:
            ET.SubElement(node,'adjust-conform',type='fit')
            if any(clip[k] != value for k,value in (('x',0),('y',0),('scale',1),('rotation',0))):
                ET.SubElement(node,'adjust-transform',position=_num(clip['x']*100*self.width/self.height)+' '+_num(-clip['y']*100),
                              scale=_num(clip['scale'])+' '+_num(clip['scale']),rotation=_num(-clip['rotation']),anchor='0 0')
            if clip['opacity'] != 1:
                ET.SubElement(node,'adjust-blend',amount=_num(clip['opacity']),mode='normal')
        if sound and clip['volume'] != 1:
            ET.SubElement(node,'adjust-volume',amount=_num(20*math.log10(clip['volume']))+'dB')

    def sequence(self,parent,ident):
        value = self.views[ident]
        if value.get('titles') or value.get('captions') or value.get('otio_dissolve'):
            _fail('titles, captions and transitions need explicit rendered elements before FCPXML export.')
        if any(t.get('mute') or t.get('solo') or t.get('gain',1) != 1 for t in value.get('tracks',[])):
            _fail('track mute/solo/gain relationships require explicit clip levels or rendered stems before FCPXML export.')
        duration = Fraction(sequence_duration(value),1)/self.rate.fraction
        origin,tc_format = self.origins.get(ident,(Fraction(0),'DF' if self.project.get('settings',{}).get('timecode_mode') == 'df' else 'NDF'))
        if tc_format == 'DF' and self.rate.fraction not in {Fraction(30000,1001),Fraction(60000,1001)}:
            _fail('retained drop-frame origin does not match the project clock.')
        fmt = self.format(self.width,self.height,self.rate)
        node = ET.SubElement(parent,'sequence',format=fmt,duration=time_string(duration),tcStart=time_string(origin),tcFormat=tc_format,audioLayout='stereo',audioRate='48k')
        spine = ET.SubElement(node,'spine')
        if duration == 0:
            return node
        gap = ET.SubElement(spine,'gap',name='Independent CINEMATICUM lanes',offset=time_string(origin),start=time_string(origin),duration=time_string(duration))
        placed = {}
        for clip in value.get('clips',[]):
            lane = clip['track']+1 if clip['track'] >= 0 else clip['track']
            for prior in placed.setdefault(lane,[]):
                if clip['start'] < prior['start']+prior['duration'] and prior['start'] < clip['start']+clip['duration']:
                    _fail('same-track overlaps need separate native lanes before this FCPXML export.')
            placed[lane].append(clip)
        for clip in sorted(enumerate(value.get('clips',[])),key=lambda item:(item[1]['track'],item[0])):
            item = clip[1]
            self.clip(gap,item,origin,item['track']+1 if item['track'] >= 0 else item['track'])
        return node

    def compound(self,ident):
        if ident not in self.compounds:
            resource = self.resource_id()
            node = ET.SubElement(self.resources,'media',id=resource,name=self.views[ident]['name'])
            self.compounds[ident] = resource
            self.sequence(node,ident)
        return self.compounds[ident]

    def run(self):
        project = ET.SubElement(self.root,'project',name=self.project['name'])
        self.sequence(project,self.project.get('sequence_id','main'))
        ET.indent(self.root,space='  ')
        document = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n'+ET.tostring(self.root,encoding='unicode')+'\n'
        if len(document.encode('utf-8')) > MAX_BYTES:
            _fail('export exceeds the 8 MiB document limit.')
        # Structural admission is symmetric; no hidden native snapshot exists.
        Document(document).references()
        return {'document':document,'warnings':list(dict.fromkeys(self.warnings)),'format':'fcpxml'}


def export_fcpxml(project,project_dir):
    return Exporter(project,project_dir).run()
