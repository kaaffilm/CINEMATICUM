"""Actual original-source decode/cache checks; no production-media claim."""
from __future__ import annotations
from bisect import bisect_right
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import source_frame_cache as cache

FFMPEG, FFPROBE = shutil.which('ffmpeg'), shutil.which('ffprobe')


@unittest.skipUnless(FFMPEG and FFPROBE, 'Existing FFmpeg and ffprobe are required')
class SourceFrameCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='cinematicum-source-cache-ENGINE-TEST-')
        cls.root = Path(cls.temporary.name)
        cls.fixtures = {}
        for name, filters in [('bframes', []), ('vfr', ['-vf', 'select=not(eq(mod(n\\,3)\\,1))'])]:
            path = cls.root / (name + '.mp4')
            result = subprocess.run([FFMPEG, '-v', 'error', '-nostdin', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=64x48:rate=24:duration=3',
                *filters, '-fps_mode', 'vfr', '-c:v', 'libx264', '-g', '24', '-bf', '2', '-pix_fmt', 'yuv420p', '-color_primaries', 'bt709', '-color_trc', 'iec61966-2-1', '-colorspace', 'bt709', '-color_range', 'tv', '-x264-params', 'colorprim=bt709:transfer=iec61966-2-1:colormatrix=bt709:fullrange=off', '-threads', '1', str(path)], capture_output=True, timeout=4)
            if result.returncode: raise RuntimeError(result.stderr.decode())
            cls.fixtures[name] = path
        rotated = cls.root / 'rotated.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-nostdin', '-y', '-display_rotation:v:0', '90', '-i', str(cls.fixtures['bframes']), '-c', 'copy', str(rotated)], check=True, capture_output=True, timeout=3)
        cls.fixtures['rotated'] = rotated
        shifted = cls.root / 'shifted.mp4'
        subprocess.run([FFMPEG, '-v', 'error', '-nostdin', '-y', '-i', str(cls.fixtures['bframes']), '-c', 'copy', '-output_ts_offset', '5', str(shifted)], check=True, capture_output=True, timeout=3)
        cls.fixtures['shifted'] = shifted

    @classmethod
    def tearDownClass(cls): cls.temporary.cleanup()

    def setUp(self):
        self.project_temporary = tempfile.TemporaryDirectory(prefix='cinematicum-source-cache-project-')
        self.project_dir = Path(self.project_temporary.name); (self.project_dir / 'media').mkdir()
        self.addCleanup(self.project_temporary.cleanup)

    def project(self, fixture='bframes'):
        source = self.project_dir / 'media' / 'original.mp4'; shutil.copy2(self.fixtures[fixture], source)
        width, height = (48, 64) if fixture == 'rotated' else (64, 48)
        asset = {'id': 'original', 'kind': 'video', 'path': 'media/original.mp4', 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                 'width': width, 'height': height, 'video_stream_index': 0, 'pixel_format': 'yuv420p', 'color_transfer': 'iec61966-2-1'}
        return {'id': 'ENGINE-TEST-source-cache', 'assets': [asset], 'settings': {'image_precision': 'standard8'}}

    def reference(self, project):
        source = self.project_dir / project['assets'][0]['path']; asset = project['assets'][0]
        probe = subprocess.run([FFPROBE, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=time_base:frame=pts', '-of', 'json', str(source)], check=True, capture_output=True, timeout=3)
        data = json.loads(probe.stdout); pts = [int(frame['pts']) for frame in data['frames']]; base = Fraction(data['streams'][0]['time_base'])
        # Full sequential decode is independent of the cache's seek/select path.
        decoded = subprocess.run([FFMPEG, '-v', 'error', '-nostdin', '-i', str(source), '-map', '0:v:0', '-an',
                    '-vf', f"scale={asset['width']}:{asset['height']}:flags=lanczos,setsar=1,format=rgba", '-fps_mode', 'passthrough',
                    '-threads', '1', '-pix_fmt', 'rgba', '-f', 'rawvideo', 'pipe:1'], check=True, capture_output=True, timeout=3)
        size = asset['width'] * asset['height'] * 4
        self.assertEqual(len(decoded.stdout), len(pts) * size)
        return pts, base, [decoded.stdout[i*size:(i+1)*size] for i in range(len(pts))]

    def assert_window(self, project, start, frames=7):
        pts, base, pixels = self.reference(project); first = bisect_right(pts, pts[0] + Fraction(str(start)) / base) - 1
        result = cache.create_window(project, self.project_dir, 'original', start, frames)
        path, receipt = cache.source_file(project, self.project_dir, result['cache_key']); data = path.read_bytes()
        self.assertEqual(data, b''.join(pixels[first:first+result['frame_count']]))
        self.assertEqual([int(frame['pts']) for frame in result['frames']], pts[first:first+result['frame_count']])
        self.assertEqual(int(result['origin_pts']), pts[0]); self.assertTrue(result['decoder_pts_verified']); self.assertFalse(result['production_media_accepted'])
        for frame, expected in zip(result['frames'], pixels[first:]): self.assertEqual(frame['sha256'], hashlib.sha256(expected).hexdigest())
        return result

    def test_long_gop_bframes_seek_matches_independent_sequential_pixels_and_pts(self):
        project = self.project(); result = self.assert_window(project, 1.5)
        self.assertEqual(result['frame_count'], 7)
        self.assertEqual(int(result['frames'][0]['pts']), 18432)

    def test_vfr_uses_true_predecessor_and_native_intervals(self):
        project = self.project('vfr'); pts, _, _ = self.reference(project)
        self.assertGreater(len(set(b-a for a,b in zip(pts,pts[1:]))), 1)
        result = self.assert_window(project, .405)
        base = Fraction(int(result['time_base']['numerator']), int(result['time_base']['denominator'])); first=result['frames'][0]
        self.assertLessEqual((int(first['pts'])-int(result['origin_pts']))*base, Fraction('0.405'))
        self.assertGreater((int(first['end_pts'])-int(result['origin_pts']))*base, Fraction('0.405'))

    def test_nonzero_native_origin_is_not_relabelled_as_zero(self):
        result = self.assert_window(self.project('shifted'), 1.5)
        self.assertGreater(int(result['origin_pts']), 0)

    def test_rotation_is_normalized_to_admitted_display_geometry(self):
        result = self.assert_window(self.project('rotated'), .5)
        self.assertEqual((result['width'], result['height']), (48, 64))
        self.assertEqual(abs(result['source_metadata']['rotation']), 90)

    def test_window_hit_does_not_run_a_second_index_or_picture_decoder(self):
        project = self.project(); first = cache.create_window(project,self.project_dir,'original',.5,3)
        original = cache._run; commands=[]
        def record(argv,*args): commands.append([str(x) for x in argv]); return original(argv,*args)
        with mock.patch.object(cache,'_run',side_effect=record): second=cache.create_window(project,self.project_dir,'original',.5,3)
        self.assertTrue(second['cached']); self.assertEqual(first['cache_key'],second['cache_key'])
        self.assertFalse(any('-show_entries' in argv and 'frame=pts,pkt_duration,duration:frame_side_data=' in argv or '-vf' in argv for argv in commands))

    def test_mutated_original_and_corrupt_cache_are_not_served(self):
        project=self.project(); result=cache.create_window(project,self.project_dir,'original',.5,3)
        raw=self.project_dir/cache.DIRECTORY/(result['cache_key']+'.rgba');raw.write_bytes(b'x'+raw.read_bytes()[1:])
        with self.assertRaises(FileNotFoundError):cache.source_file(project,self.project_dir,result['cache_key'])
        rebuilt=cache.create_window(project,self.project_dir,'original',.5,3);self.assertFalse(rebuilt['cached'])
        original=self.project_dir/project['assets'][0]['path'];original.write_bytes(original.read_bytes()+b'changed')
        with self.assertRaises(FileNotFoundError):cache.source_file(project,self.project_dir,result['cache_key'])
        with self.assertRaisesRegex(ValueError,'original source changed'):cache.create_window(project,self.project_dir,'original',.5,3)

    def test_raw_window_budget_limits_actual_frame_inventory(self):
        project=self.project();size=64*48*4
        with mock.patch.object(cache,'MAX_RAW_BYTES',size*2):result=cache.create_window(project,self.project_dir,'original',.5,100)
        self.assertEqual(result['frame_count'],2);self.assertEqual(result['byte_size'],size*2)

    def test_hdr_alpha_special_precision_and_bad_requests_fail_closed(self):
        project=self.project()
        for update in ({'color_transfer':'smpte2084'},{'pixel_format':'yuva420p'}):
            candidate=json.loads(json.dumps(project));candidate['assets'][0].update(update)
            with self.subTest(update=update),self.assertRaises(ValueError):cache.validate_request(candidate,{'asset_id':'original','start':0,'frames':2})
        for precision in ('high16','float32'):
            project['settings']['image_precision']=precision
            with self.assertRaises(ValueError):cache.validate_request(project,{'asset_id':'original','start':0,'frames':2})
        project['settings']['image_precision']='standard8'
        for update in ({'frames':True},{'frames':121},{'start':float('nan')},{'start':-1},{'extra':0}):
            with self.subTest(update=update),self.assertRaises(ValueError):cache.validate_request(project,{'asset_id':'original','start':0,'frames':2,**update})

    def test_pre_cancel_has_no_published_cache_or_child(self):
        project=self.project();event=threading.Event();event.set()
        with self.assertRaises(cache.SourceCacheCancelled):cache.create_window(project,self.project_dir,'original',.5,3,cancel_event=event)
        self.assertFalse((self.project_dir/cache.DIRECTORY).exists())

    def test_active_owned_child_cancellation_is_reaped_and_bounded(self):
        output=self.project_dir/'output';log=self.project_dir/'log';event=threading.Event();timer=threading.Timer(.08,event.set);timer.start()
        began=time.monotonic()
        try:
            with self.assertRaises(cache.SourceCacheCancelled):cache._run([sys.executable,'-c','import os,time;print(os.getpid(),flush=True);time.sleep(30)'],output,log,event,time.monotonic()+3,1024)
        finally:timer.cancel();timer.join()
        self.assertLess(time.monotonic()-began,1);pid=int(output.read_text().strip())
        with self.assertRaises(ProcessLookupError):os.kill(pid,0)

    def test_no_partial_publication_when_decoder_pts_disagree(self):
        project=self.project();original=cache._run
        def wrong(argv,output,log,*args):
            original(argv,output,log,*args)
            if '-vf' in argv:log.write_text(log.read_text().replace('pts:   6144','pts:   6145'))
        # A deterministic source clock mismatch must fail instead of assigning
        # the requested timestamp to an unverified decoded surface.
        with mock.patch.object(cache,'_run',side_effect=wrong):
            with self.assertRaisesRegex(ValueError,'PTS/geometry disagree'):cache.create_window(project,self.project_dir,'original',.5,3)
        self.assertEqual(list((self.project_dir/cache.DIRECTORY).glob('*.rgba')),[])
        self.assertEqual(list((self.project_dir/cache.DIRECTORY).glob('build-*')),[])


if __name__ == '__main__':unittest.main()
