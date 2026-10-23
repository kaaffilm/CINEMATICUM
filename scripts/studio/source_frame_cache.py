"""Byte-bounded original-source RGBA windows with decoder-owned picture PTS.

No timeline, grade, effect, or project-rate resampling enters this cache. An
index records real decoded source timestamps; a second decoder's showinfo must
match every delivered raw picture. The authoring client owns CPU/GPU retention.
This is opaque Standard8 SDR preview storage, not HDR/mastering certification.
"""
from __future__ import annotations

from array import array
from bisect import bisect_right
from collections import OrderedDict
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time

VERSION = 1
DIRECTORY = 'source-frames'
MAX_INDEX_FRAMES = 240_000
MAX_INDEX_TEXT_BYTES = 24 * 1024 ** 2
MAX_WINDOW_FRAMES = 120
MAX_RAW_BYTES = 96 * 1024 ** 2
MAX_CACHE_BYTES = 512 * 1024 ** 2
MAX_PIXELS = 4096 * 2160
MAX_EDGE = 4096
DISK_RESERVE = 64 * 1024 ** 2
FORMAT_WHITELIST = 'mov,matroska,avi,mpeg,mpegts,mxf,m4v'
HASH = re.compile(r'[a-f0-9]{64}')
ID = re.compile(r'[A-Za-z0-9_-]{1,128}')
_VERIFIED = OrderedDict()
_VERIFIED_LOCK = threading.Lock()


class SourceCacheCancelled(RuntimeError):
    pass


def _cancel(event):
    if event is not None and event.is_set():
        raise SourceCacheCancelled('Source-picture cache preparation cancelled.')


def _digest(path, event=None, deadline=None):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            _cancel(event)
            if deadline is not None and time.monotonic() > deadline:
                raise RuntimeError('Source-picture verification exceeded its preparation deadline.')
            value.update(block)
    return value.hexdigest()


def _verified(path, expected, event=None, deadline=None):
    _cancel(event); stat = path.stat()
    key = (str(path), stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, expected)
    with _VERIFIED_LOCK:
        if key in _VERIFIED:
            _VERIFIED.move_to_end(key); return True
    if _digest(path, event, deadline) != expected:
        return False
    with _VERIFIED_LOCK:
        _VERIFIED[key] = True
        while len(_VERIFIED) > 256:
            _VERIFIED.popitem(last=False)
    return True


def _json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n')


def _key(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _asset(project, asset_id):
    if not isinstance(asset_id, str) or not ID.fullmatch(asset_id):
        raise ValueError('Choose one imported picture asset.')
    asset = next((item for item in project.get('assets', []) if item.get('id') == asset_id), None)
    if asset is None or asset.get('kind') != 'video' or not HASH.fullmatch(str(asset.get('sha256', ''))):
        raise ValueError('Source-picture caching requires an imported video with a recorded SHA-256.')
    if project.get('settings', {}).get('image_precision', 'standard8') != 'standard8':
        raise ValueError('Source-picture caching currently requires Standard8 SDR processing.')
    width, height, stream = asset.get('width'), asset.get('height'), asset.get('video_stream_index')
    if any(type(item) is not int for item in (width, height, stream)) or not 0 <= stream <= 255:
        raise ValueError('The admitted picture dimensions or stream identity are unavailable.')
    if min(width, height) < 1 or max(width, height) > MAX_EDGE or width * height > MAX_PIXELS:
        raise ValueError('Source-picture caching supports at most a 4096-pixel edge and 8,847,360 display pixels.')
    if asset.get('color_transfer') != 'iec61966-2-1':
        raise ValueError('Source-picture caching currently requires an explicitly tagged sRGB transfer; ambiguous, BT709-transfer and HDR sources retain native playback.')
    if str(asset.get('pixel_format', '')).startswith(('yuva', 'gbrap', 'rgba', 'bgra', 'argb', 'abgr', 'ya')):
        raise ValueError('This source-picture cache currently supports opaque video only.')
    return asset


def validate_request(project, payload):
    if not isinstance(payload, dict) or set(payload) != {'asset_id', 'start', 'frames'}:
        raise ValueError('Source-picture preparation requires exactly asset_id, start and frames.')
    asset = _asset(project, payload['asset_id'])
    start, frames = payload['start'], payload['frames']
    if isinstance(start, bool) or not isinstance(start, (int, float)) or not math.isfinite(start) or not 0 <= start <= 21_600:
        raise ValueError('Source-picture start must be finite seconds from zero through six hours.')
    if type(frames) is not int or not 1 <= frames <= MAX_WINDOW_FRAMES:
        raise ValueError('Prepare between 1 and 120 decoded source pictures.')
    if width_bytes(asset) > MAX_RAW_BYTES:
        raise ValueError('One decoded source picture exceeds the byte budget.')
    return {'asset_id': asset['id'], 'start': float(start), 'frames': frames}


def width_bytes(asset):
    return asset['width'] * asset['height'] * 4


def _source(project_dir, asset):
    root = Path(project_dir).resolve()
    rel = Path(str(asset.get('path', '')))
    if rel.is_absolute() or len(rel.parts) != 2 or rel.parts[0] != 'media' or '\\' in str(rel) or '\x00' in str(rel):
        raise ValueError('Source pictures must belong to this project media directory.')
    path = root / rel
    if path.parent.is_symlink() or path.is_symlink() or not path.is_file() or path.resolve().parent != root / 'media':
        raise ValueError('The recorded source is missing or outside its owned media directory.')
    return path


def _directory(project_dir):
    root = Path(project_dir).resolve(); path = root / DIRECTORY
    if path.is_symlink() or path.exists() and not path.is_dir():
        raise ValueError('The source-picture cache is not an owned directory.')
    path.mkdir(exist_ok=True)
    return path


def _signal_group(process, sig):
    try:
        if os.name == 'posix':
            os.killpg(process.pid, sig)
        elif process.poll() is None:
            process.terminate() if sig == signal.SIGTERM else process.kill()
    except ProcessLookupError:
        pass


def _run(argv, output, log, event, deadline, byte_limit):
    """Foreground owned child, cancellation, output/log bounds, and reaping."""
    _cancel(event)
    with Path(output).open('wb') as target, Path(log).open('wb') as errors:
        process = subprocess.Popen([str(item) for item in argv], stdin=subprocess.DEVNULL,
                                   stdout=target, stderr=errors, start_new_session=True)
        try:
            while process.poll() is None:
                _cancel(event)
                if time.monotonic() > deadline:
                    raise RuntimeError('Source-picture decoding exceeded its cancellable preparation deadline.')
                if Path(output).stat().st_size > byte_limit or Path(log).stat().st_size > 2 * 1024 ** 2:
                    raise ValueError('Source-picture decoder output exceeded its explicit byte bound.')
                if event is None: time.sleep(.015)
                else: event.wait(.015)
            _cancel(event)
            if process.returncode:
                errors.flush()
                detail = Path(log).read_bytes()[-1800:].decode(errors='replace')
                raise ValueError('The selected source picture decoder failed: ' + detail)
            if Path(output).stat().st_size > byte_limit or Path(log).stat().st_size > 2 * 1024 ** 2:
                raise ValueError('Source-picture decoder output exceeded its explicit byte bound.')
        finally:
            # Only this new session is signalled, including descendants that
            # outlive a failed main process. No caller-supplied PID is accepted.
            _signal_group(process, signal.SIGTERM)
            try: process.wait(timeout=.25)
            except subprocess.TimeoutExpired: pass
            _signal_group(process, signal.SIGKILL)
            process.wait(timeout=.5)


def _tools(scratch, event, deadline):
    result = {}
    for name in ('ffmpeg', 'ffprobe'):
        executable = shutil.which(name)
        if not executable: raise ValueError('Existing FFmpeg and ffprobe are required for source-picture caching.')
        output = scratch / (name + '-version.txt')
        _run([executable, '-version'], output, scratch / (name + '-version.log'), event, deadline, 64 * 1024)
        result[name] = executable
        result[name + '_version'] = output.read_text(errors='replace').splitlines()[0]
    return result


def _header(source, asset, tools, scratch, event, deadline):
    output = scratch / 'stream.json'
    fields = 'stream=index,codec_name,width,height,pix_fmt,sample_aspect_ratio,time_base,color_space,color_transfer,color_primaries,color_range,field_order:stream_side_data=rotation'
    _run([tools['ffprobe'], '-v', 'error', '-protocol_whitelist', 'file,pipe', '-format_whitelist', FORMAT_WHITELIST, '-select_streams', str(asset['video_stream_index']),
          '-show_entries', fields, '-of', 'json', source], output, scratch / 'stream.log', event, deadline, 128 * 1024)
    streams = json.loads(output.read_text()).get('streams', [])
    if len(streams) != 1: raise ValueError('The admitted source video stream is not present.')
    header = streams[0]
    if header.get('index') != asset['video_stream_index']: raise ValueError('The decoded video stream identity changed.')
    base = str(header.get('time_base', ''))
    if not re.fullmatch(r'[1-9][0-9]{0,9}/[1-9][0-9]{0,9}', base):
        raise ValueError('The decoder did not provide a bounded native picture time base.')
    tick = Fraction(base)
    if tick.numerator >= 2 ** 31 or tick.denominator >= 2 ** 31: raise ValueError('The native picture time base is unsupported.')
    if (header.get('color_transfer'), header.get('color_primaries'), header.get('color_space')) != ('iec61966-2-1', 'bt709', 'bt709') or header.get('color_range') not in ('tv', 'pc'):
        raise ValueError('The actual source requires explicit sRGB transfer, BT709 primaries/matrix and known range for this display cache.')
    if str(header.get('pix_fmt', '')).startswith(('yuva', 'gbrap', 'rgba', 'bgra', 'argb', 'abgr', 'ya')):
        raise ValueError('The actual source has alpha; this cache currently supports opaque pictures.')
    if header.get('field_order') not in (None, 'unknown', 'progressive'):
        raise ValueError('Interlaced sources require an explicit deinterlacing policy before caching.')
    sar = str(header.get('sample_aspect_ratio', '1:1'))
    if not re.fullmatch(r'[1-9][0-9]{0,5}:[1-9][0-9]{0,5}', sar):
        raise ValueError('The actual source has no supported display sample aspect ratio.')
    a, b = map(int, sar.split(':')); width = round(int(header['width']) * a / b); height = int(header['height'])
    rotation = next((item['rotation'] for item in header.get('side_data_list', []) if 'rotation' in item), 0)
    if isinstance(rotation, bool) or not isinstance(rotation, (int, float)) or not math.isfinite(rotation) or abs(rotation / 90 - round(rotation / 90)) > 1e-7:
        raise ValueError('Source-picture caching supports orthogonal display rotation only.')
    if abs(round(rotation)) % 180 == 90: width, height = height, width
    if (width, height) != (asset['width'], asset['height']):
        raise ValueError('The actual display rotation/SAR geometry differs from the admitted source.')
    header.update(time_base=f'{tick.numerator}/{tick.denominator}', rotation=rotation,
                  display_width=width, display_height=height)
    return header


def _read_index(directory, key, recipe, event):
    path, receipt_path = directory / (key + '.index'), directory / (key + '.index.json')
    if path.is_symlink() or receipt_path.is_symlink(): raise ValueError('Source indexes cannot be symbolic links.')
    if not path.is_file() or not receipt_path.is_file(): return None
    try:
        if receipt_path.stat().st_size > 128 * 1024: return None
        receipt = json.loads(receipt_path.read_text()); count = receipt['frame_count']
        if receipt['recipe'] != recipe or receipt['cache_key'] != key or type(count) is not int or not 1 <= count <= MAX_INDEX_FRAMES:
            return None
        if path.stat().st_size != count * 16 or not HASH.fullmatch(receipt['sha256']) or not _verified(path, receipt['sha256'], event):
            return None
        values = array('q'); values.frombytes(path.read_bytes())
        if os.sys.byteorder != 'little': values.byteswap()
        pts, duration = values[0::2], values[1::2]
        if any(not -2 ** 53 < stamp < 2 ** 53 or i and stamp <= pts[i-1] for i, stamp in enumerate(pts)) or any(value < 0 for value in duration):
            return None
        return pts, duration
    except (KeyError, TypeError, ValueError, OSError):
        return None


def _index(source, directory, recipe, tools, scratch, event, deadline):
    key = _key(recipe); cached = _read_index(directory, key, recipe, event)
    if cached: return key, cached
    text = scratch / 'index.txt'
    _run([tools['ffprobe'], '-v', 'error', '-protocol_whitelist', 'file,pipe', '-format_whitelist', FORMAT_WHITELIST, '-select_streams', str(recipe['stream_index']),
          '-show_entries', 'frame=pts,pkt_duration,duration:frame_side_data=', '-of', 'compact=p=0:nk=0', source],
         text, scratch / 'index.log', event, deadline, MAX_INDEX_TEXT_BYTES)
    values = array('q'); previous = None
    for line in text.read_text().splitlines():
        _cancel(event)
        if not line.strip(): continue
        fields = dict(part.split('=', 1) for part in line.split('|') if '=' in part)
        stamp = fields.get('pts', '')
        duration = fields.get('duration', fields.get('pkt_duration', '0'))
        if not re.fullmatch(r'-?[0-9]{1,19}', stamp) or not re.fullmatch(r'[0-9]{1,19}', duration):
            raise ValueError('The source decoder did not establish an integer picture PTS/duration.')
        stamp, duration = int(stamp), int(duration)
        if not -2 ** 53 < stamp < 2 ** 53 or duration >= 2 ** 53 or previous is not None and stamp <= previous:
            raise ValueError('Source pictures require strictly increasing, exactly representable decoded PTS.')
        values.extend((stamp, duration)); previous = stamp
        if len(values) // 2 > MAX_INDEX_FRAMES: raise ValueError('The decoded source index exceeds 240,000 pictures.')
    if not values: raise ValueError('No actual pictures were decoded from the selected source.')
    pts, duration = values[0::2], values[1::2]
    if os.sys.byteorder != 'little': values.byteswap()
    binary = scratch / 'index.bin'; binary.write_bytes(values.tobytes())
    receipt = {'version': VERSION, 'cache_key': key, 'recipe': recipe, 'frame_count': len(pts), 'sha256': _digest(binary, event)}
    temporary = scratch / 'index.json'; _json(temporary, receipt); _cancel(event)
    os.replace(binary, directory / (key + '.index')); os.replace(temporary, directory / (key + '.index.json'))
    return key, (pts, duration)


def _validate_receipt(value, key):
    if not isinstance(value, dict) or value.get('version') != VERSION or value.get('cache_key') != key or not HASH.fullmatch(str(value.get('source_sha256', ''))):
        raise ValueError('The source-picture receipt identity is invalid.')
    width, height, count = value.get('width'), value.get('height'), value.get('frame_count')
    if any(type(item) is not int for item in (width, height, count)) or min(width, height) < 1 or max(width, height) > MAX_EDGE or width * height > MAX_PIXELS or not 1 <= count <= MAX_WINDOW_FRAMES:
        raise ValueError('The source-picture receipt geometry/count is invalid.')
    size = width * height * 4
    if value.get('byte_size') != size * count or size * count > MAX_RAW_BYTES or not HASH.fullmatch(str(value.get('sha256', ''))):
        raise ValueError('The source-picture receipt exceeds its exact RGBA byte inventory.')
    if value.get('pixel_format') != 'rgba8' or value.get('opaque') is not True or value.get('source_only') is not True:
        raise ValueError('The source-picture pixel policy is invalid.')
    base = value.get('time_base')
    if not isinstance(base, dict) or set(base) != {'numerator', 'denominator'} or any(not isinstance(item, str) or not re.fullmatch(r'[1-9][0-9]{0,9}', item) for item in base.values()):
        raise ValueError('The source-picture time base is invalid.')
    origin = value.get('origin_pts')
    if not isinstance(origin, str) or not re.fullmatch(r'-?[0-9]{1,16}', origin): raise ValueError('The source-picture origin PTS is invalid.')
    frames = value.get('frames')
    if not isinstance(frames, list) or len(frames) != count: raise ValueError('The source-picture frame inventory is invalid.')
    previous = None
    for i, frame in enumerate(frames):
        if not isinstance(frame, dict) or not all(isinstance(frame.get(name), str) and re.fullmatch(r'-?[0-9]{1,16}', frame[name]) for name in ('pts', 'end_pts')):
            raise ValueError('A cached picture has no exact decoded PTS interval.')
        start, end = int(frame['pts']), int(frame['end_pts'])
        if start >= end or previous is not None and start != previous or frame.get('byte_offset') != i * size or frame.get('byte_size') != size or not HASH.fullmatch(str(frame.get('sha256', ''))):
            raise ValueError('The decoded picture intervals or byte inventory are invalid.')
        previous = end
    recipe = value.get('window_recipe')
    if not isinstance(recipe, dict) or _key(recipe) != key or any(recipe.get(name) != value.get(name) for name in ('source_sha256', 'stream_index', 'width', 'height')) or recipe.get('count') != count:
        raise ValueError('The source-picture recipe does not match its cache key or source inventory.')
    return value


def _read_window(directory, key, event=None):
    path, receipt_path = directory / (key + '.rgba'), directory / (key + '.json')
    if path.is_symlink() or receipt_path.is_symlink(): raise ValueError('Source-picture windows cannot be symbolic links.')
    if not path.is_file() or not receipt_path.is_file(): return None
    try:
        if receipt_path.stat().st_size > 128 * 1024: return None
        receipt = _validate_receipt(json.loads(receipt_path.read_text()), key)
        if path.stat().st_size != receipt['byte_size'] or not _verified(path, receipt['sha256'], event): return None
        return path, receipt
    except (KeyError, TypeError, ValueError, OSError):
        return None


def _usage(directory):
    total = 0
    for path in directory.iterdir():
        if path.is_symlink(): raise ValueError('The owned source-picture cache contains a symbolic link.')
        if path.is_file(): total += path.stat().st_size
        elif path.is_dir() and path.name.startswith('build-'):
            total += sum(item.stat().st_size for item in path.iterdir() if item.is_file() and not item.is_symlink())
    return total


def _reserve(directory, needed, keep=()):
    keep = {keep} if isinstance(keep, str) else set(keep)
    receipts = sorted((path for path in directory.glob('*.json') if HASH.fullmatch(path.stem) or path.name.endswith('.index.json') and HASH.fullmatch(path.name[:-11])), key=lambda path: path.stat().st_mtime)
    for receipt in receipts:
        if _usage(directory) + needed <= MAX_CACHE_BYTES: break
        identity = receipt.name[:-11] if receipt.name.endswith('.index.json') else receipt.stem
        if identity in keep: continue
        raw = directory / (identity + ('.index' if receipt.name.endswith('.index.json') else '.rgba'))
        if receipt.is_symlink() or raw.is_symlink(): raise ValueError('Refusing a symbolic-link cache eviction.')
        raw.unlink(missing_ok=True); receipt.unlink(missing_ok=True)
    if _usage(directory) + needed > MAX_CACHE_BYTES or shutil.disk_usage(directory).free < needed + DISK_RESERVE:
        raise ValueError('The source-picture cache has insufficient owned byte capacity or disk reserve.')


def create_window(project, project_dir, asset_id, start=0, frames=60, progress=None, cancel_event=None):
    request = validate_request(project, {'asset_id': asset_id, 'start': start, 'frames': frames})
    asset = _asset(project, asset_id); source = _source(project_dir, asset); _cancel(cancel_event)
    deadline = time.monotonic() + 120
    if not _verified(source, asset['sha256'], cancel_event, deadline): raise ValueError('The original source changed; relink its recorded bytes before caching.')
    directory = _directory(project_dir)
    _reserve(directory, 2 * MAX_INDEX_TEXT_BYTES)
    with tempfile.TemporaryDirectory(prefix='build-', dir=directory) as temporary:
        scratch = Path(temporary); tools = _tools(scratch, cancel_event, deadline)
        header = _header(source, asset, tools, scratch, cancel_event, deadline)
        recipe = {'version': VERSION, 'source_sha256': asset['sha256'], 'stream_index': asset['video_stream_index'],
                  'width': asset['width'], 'height': asset['height'], 'header': header,
                  'ffmpeg': tools['ffmpeg_version'], 'ffprobe': tools['ffprobe_version'],
                  'policy': 'opaque-rgba8-srgb-bt709-display-sar-autorotation-v1'}
        if progress: progress(.05)
        index_key, (pts, durations) = _index(source, directory, recipe, tools, scratch, cancel_event, deadline)
        base = Fraction(header['time_base']); target = pts[0] + Fraction(str(request['start'])) / base
        first = bisect_right(pts, target) - 1
        if first < 0 or first == len(pts) - 1 and (not durations[first] or target >= pts[first] + durations[first]):
            raise ValueError('The requested source time has no decoder-proven picture interval.')
        count = min(request['frames'], MAX_RAW_BYTES // width_bytes(asset), len(pts) - first)
        # Missing final duration is not inferred from container duration or FPS.
        if first + count == len(pts) and durations[-1] <= 0: count -= 1
        if count < 1: raise ValueError('No decoder-proven source picture remains in this window.')
        window_recipe = {'source_index': index_key, 'source_sha256': asset['sha256'], 'stream_index': asset['video_stream_index'], 'width': asset['width'], 'height': asset['height'], 'first': first, 'count': count, 'pixel_format': 'rgba8'}
        key = _key(window_recipe); cached = _read_window(directory, key, cancel_event)
        if cached:
            if progress: progress(1)
            return {**cached[1], 'asset_id': asset_id, 'cached': True}
        size = width_bytes(asset); _reserve(directory, count * size + 128 * 1024, keep=(key, index_key))
        raw = scratch / 'window.rgba'; log = scratch / 'decode.log'
        timestamp = float(Fraction(pts[first]) * base)
        chain = f"select=gte(pts\\,{pts[first]}),scale={asset['width']}:{asset['height']}:flags=lanczos,setsar=1,format=rgba,showinfo=checksum=0"
        argv = [tools['ffmpeg'], '-hide_banner', '-loglevel', 'info', '-nostdin', '-y', '-threads', '1', '-filter_threads', '1',
                '-copyts', '-noaccurate_seek', '-seek_timestamp', '1', '-ss', format(timestamp, '.17g'), '-protocol_whitelist', 'file,pipe', '-format_whitelist', FORMAT_WHITELIST, '-i', source,
                '-map', f"0:{asset['video_stream_index']}", '-an', '-sn', '-dn', '-vf', chain, '-fps_mode', 'passthrough', '-frames:v', str(count),
                '-c:v', 'rawvideo', '-pix_fmt', 'rgba', '-threads', '1', '-f', 'rawvideo', 'pipe:1']
        if progress: progress(.4)
        _run(argv, raw, log, cancel_event, deadline, count * size)
        if raw.stat().st_size != count * size: raise ValueError('The source decoder did not deliver its exact raw picture inventory.')
        text = log.read_text(errors='replace')
        timebases = re.findall(r'config in time_base: ([0-9]+/[0-9]+)', text)
        shown = re.findall(r'\bn:\s*([0-9]+)\s+pts:\s*(-?[0-9]+).*?\bfmt:rgba\b.*?\bs:([0-9]+)x([0-9]+)\s+i:([A-Za-z])', text)
        if not timebases or Fraction(timebases[-1]) != base or len(shown) < count:
            raise ValueError('The raw decoder did not expose the same native PTS/time-base inventory.')
        for i, (number, stamp, width, height, interlace) in enumerate(shown[:count]):
            if (int(number), int(stamp), int(width), int(height), interlace) != (i, pts[first+i], asset['width'], asset['height'], 'P'):
                raise ValueError('Raw source pixels and independently indexed decoder PTS/geometry disagree.')
        inventory = []
        with raw.open('rb') as source_bytes:
            for i in range(count):
                _cancel(cancel_event); payload = source_bytes.read(size); stamp = pts[first+i]
                if any(value != 255 for value in payload[3::4]): raise ValueError('The actual decoded source has alpha and cannot enter this opaque cache.')
                end = pts[first+i+1] if first+i+1 < len(pts) else stamp + durations[first+i]
                inventory.append({'pts': str(stamp), 'end_pts': str(end), 'byte_offset': i * size, 'byte_size': size, 'sha256': hashlib.sha256(payload).hexdigest()})
        if not _verified(source, asset['sha256'], cancel_event, deadline): raise ValueError('The original changed while its source pictures were decoded.')
        receipt = {'version': VERSION, 'cache_key': key, 'window_recipe': window_recipe, 'source_sha256': asset['sha256'],
                   'stream_index': asset['video_stream_index'], 'width': asset['width'], 'height': asset['height'], 'frame_count': count,
                   'byte_size': count * size, 'sha256': _digest(raw, cancel_event), 'time_base': {'numerator': str(base.numerator), 'denominator': str(base.denominator)},
                   'origin_pts': str(pts[0]), 'frames': inventory, 'pixel_format': 'rgba8', 'opaque': True, 'source_only': True,
                   'policy': recipe['policy'], 'source_metadata': header, 'source_index_frames': len(pts), 'max_raw_bytes': MAX_RAW_BYTES,
                   'decoder_pts_verified': True, 'production_media_accepted': False, 'gpu_residency_certified': False,
                   'created_at': time.time()}
        _validate_receipt(receipt, key); temporary_receipt = scratch / 'window.json'; _json(temporary_receipt, receipt); _cancel(cancel_event)
        os.replace(raw, directory / (key + '.rgba')); os.replace(temporary_receipt, directory / (key + '.json'))
        if progress: progress(1)
        return {**receipt, 'asset_id': asset_id, 'cached': False}


def source_file(project, project_dir, key):
    if not isinstance(key, str) or not HASH.fullmatch(key): raise ValueError('Invalid source-picture cache identity.')
    directory = Path(project_dir).resolve() / DIRECTORY
    if directory.is_symlink() or not directory.is_dir(): raise FileNotFoundError('Verified source pictures are unavailable.')
    cached = _read_window(directory, key)
    if cached:
        path, receipt = cached
        for candidate in project.get('assets', []):
            if candidate.get('sha256') != receipt['source_sha256']: continue
            try:
                asset = _asset(project, candidate['id'])
                if asset['video_stream_index'] != receipt['stream_index'] or (asset['width'], asset['height']) != (receipt['width'], receipt['height']): continue
                if _verified(_source(project_dir, asset), asset['sha256'], deadline=time.monotonic()+10): return path, receipt
            except (KeyError, ValueError, OSError): pass
    raise FileNotFoundError('The source-picture cache no longer matches verified original media.')
