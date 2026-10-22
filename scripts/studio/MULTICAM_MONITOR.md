# Simultaneous cameras and fixed source sound

Select a clip from an existing manual or measured multicamera group. Open
**Multicam → Open simultaneous camera monitor**. The monitor shows the group's
2–16 original cameras (or its selected verified playback proxies) on the shared
timeline clock. Every camera picture is muted; the editor's actual source PCM
transport provides the sound. The monitor has Play/Pause, a shared playhead,
camera cut buttons, a sound selector and Save.

Clicking a different camera makes one undoable picture cut at that playhead.
Playback continues across a live cut. Selecting **Lock to [camera]** and applying
the sound choice fixes sound to that camera for the group's clips, independently
of picture cuts. **Follow picture camera** releases that choice. **Source audio**
then edits the locked camera's original stream and zero-based stereo channel
pair. Clip gain, pan, fades, keyframes and retiming remain timeline controls.
The timeline waveform, live PCM and movie render use the effective sound source.
An affected locked track, including one in an inactive sequence, refuses shared
sound edits.

## Source clock and persistence

`multicam.resolve_audio(project, clip, assets_by_id)` returns an effective sound
clip and asset without modifying the authored picture clip. Its source in point
is `picture_clip.in + sound_angle.in - picture_angle.in`. The timeline start,
duration, speed, reverse, gain and fade offsets remain authored on the clip.

The group's `audio_lock` stores a versioned fixed angle, stream, channel pair and
an explicit binding to every camera's admitted SHA-256, synchronization in point
and exact project rate. Source/group/rate edits that invalidate the binding are
refused. Undo restores the preceding edit; release a lock before changing its
group clock. A trim that extends beyond the locked stream is refused instead
of returning padded or unrelated sound. Opening a monitor and exporting a lock
also verify source bytes against their admitted identities.

Picture cuts that share the same fixed-source clock keep one live PCM decoder.
Overlapping instances retain separate voices. Save/reopen and complete project
archives retain the lock, original media and source clock. Nested movie renders
resolve the same source; NTSC cuts retain the absolute output sample grid.

## Limits

The existing limit remains 16 cameras per group and 64 groups per project.
The interactive monitor uses browser video decoders and the current playback
proxy setting. Unsupported video produces an explicit proxy instruction.
Camera switching retains the existing restriction to ordinary forward,
constant-speed clips before tracking or compositing. Retimed/reversed camera
pictures can be monitored, but reverse sound still requires rendered playback.
This does not add drift correction, timecode synchronization, speed ramps,
optical-flow retiming, decoded GPU caching, or broadcast monitoring. Large
multicamera sessions and extended operation still need production-scale tests.

## Actual acceptance

`test_multicam_monitor.py` has 15 actual-media tests. Its two synthetic ENGINE
TEST cameras encode each source frame as a binary picture counter and contain
independent original PCM streams. The second camera's default sound differs
from its nondefault stereo stream. Tests independently decode all rendered
picture counters and sound samples; they cover fixed sound across cuts,
stream/channel changes, unlock, gain/pan, silent picture sources, nested and
reverse output, pitch-preserving retime, NTSC sample continuity, source/range
refusal, locked inactive tracks and archive relocation.

`test_multicam_monitor_browser.cjs` runs the same portable UI script and Python
coordinator used by native acceptance. It exercises actual simultaneous camera
decoders, unsaved apply, one-step undo/redo, save/reopen, live picture cuts,
AudioWorklet observation of original-source sound, pause/restart, actual export
and actual movie download. The observer has its own calibration signal and a
silent output, so it cannot supply the application's measured sound. Every
downloaded movie frame and stereo sample is independently checked afterward.

The browser runtime must decode H.264. The Playwright-only Chromium 134 used by
the synchronization gate does not contain that decoder and is explicitly
refused here. Chrome for Testing 134.0.6998.35 with Playwright 1.51.1 passed the
actual camera/PCM gate. Browser evidence never certifies native macOS.

```sh
NODE_PATH=/absolute/playwright-1.51.1/node_modules \
node scripts/studio/test_multicam_monitor_browser.cjs \
  --python /absolute/numpy-runtime/bin/python \
  --browser /absolute/chrome-for-testing/chrome \
  --evidence /absolute/new-monitor-evidence
```

The affected regression command is:

```sh
cd scripts/studio
python3 -B -m unittest test_editorial test_audio_source test_pcm_playback \
  test_sequence_playback test_audio_routing test_install_macos \
  test_multicam_monitor -v
```

### Bounded native phases

Compile the existing Swift helper separately. Use an actual NumPy Python and
FFmpeg/FFprobe on PATH. A new explicit evidence directory and a fresh fixture
are required; failed attempts are retained rather than overwritten.

```sh
swiftc -framework Cocoa -framework WebKit scripts/studio/macos/SmokeTest.swift \
  -o /absolute/evidence/NativeSmoke
```

Write the frozen source manifest after all candidate files have been integrated:

```sh
/absolute/numpy-runtime/bin/python -I -B -c \
  'import json,sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from test_multicam_monitor_macos import source_inventory; Path(sys.argv[2]).write_text(json.dumps(source_inventory(),sort_keys=True,indent=2)+"\n")' \
  /absolute/CINEMATICUM/scripts/studio /absolute/evidence/source-manifest.json
```

Run this command once for each phase, in order: **prepare**, **author**, **play**,
**render**. Replace `prepare` in both arguments with the current phase. Each
invocation has an 18-second coordinator budget, at most 14.5 seconds for the
native helper, and closes its own backend, process group and jobs. Run phases
as separate foreground commands when the caller has a 20-second limit.

```sh
/absolute/numpy-runtime/bin/python -B \
  /absolute/CINEMATICUM/scripts/studio/test_multicam_monitor_macos.py \
  --binary /absolute/evidence/NativeSmoke \
  --operation prepare \
  --output /absolute/evidence/prepare \
  --fixture-workspace /absolute/evidence/fixture \
  --source-manifest /absolute/evidence/source-manifest.json
```

Each phase binds the previous success, saved project, original media, independent
truth and exact runtime/web/helper source inventory. Native acceptance remains
pending until measured WKWebView reports pass on the integrated source. These
helpers do not certify physical mouse/keyboard input, the installed launcher,
the production Save panel, arbitrary footage or prolonged editing sessions.
