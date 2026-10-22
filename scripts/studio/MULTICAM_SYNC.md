# Measured multicamera audio synchronization

The Multicam panel's **Synchronize recorded audio** workflow measures an actual
constant sample offset from the selected audio stream and zero-based channel of
each camera. It decodes PCM at 48 kHz and uses normalized FFT correlation, checks
separated windows, and preserves source receipts and measured waveforms.

Select 2–16 video sources containing distinct common sound, choose the reference
camera, analysis window and offset range, and measure. Review the accepted
offsets and aligned waveforms before creating a cut. The candidate covers only
the common measured window. Fractional source frames preserve the measured
sample offsets. Apply creates one undoable edit; Save persists it. Analysis
channel selection does not change the camera's playback mix. Explicit Source
audio controls choose a different playback stream/channel mapping when needed.

The supported analysis window is 5–120 seconds per camera, with up to 60 seconds
of searched lag and at least four seconds of common sound. Silence, unrelated or
ambiguous periodic sound, inconsistent clock offsets, and mismatched source
presentation origins are refused. No clock-drift correction, optical-flow
retiming, timecode alignment, simultaneous multicamera monitor, or independent
audio-lock mode is implied by this synchronization implementation.

## Acceptance source

`test_multicam_sync.py` covers independent scalar/FFT comparison, signed and
fractional sample offsets, source stream/channel selection, polarity, drift and
ambiguity refusal, owned HTTP jobs/artifacts, cancellation, atomic apply,
save/reopen, archives, and actual rendered picture and PCM.

`test_multicam_sync_browser.cjs` and `test_multicam_sync_macos.py` exercise the
same `macos/MulticamSyncSmoke.js` shipped-control workflow against an actual
backend. The four phases are `prepare`, `author`, `synchronize`, and `render`.
Each coordinator phase has an 18-second foreground limit and closes its owned
backend/browser/jobs. A new evidence directory preserves every prior attempt.
Source inventories, fixture hashes and saved-project hashes bind phases; an
incomplete phase cannot be mistaken for a passed predecessor.

The synthetic ENGINE TEST fixture contains three 12-second cameras. Their
independently generated sound has offsets of +11,819 and −7,517 samples, one
inverted polarity, and a nondefault stream/channel with unrelated sound in the
default stream. Acceptance imports the actual movies, measures these offsets,
applies/undoes/redoes/saves/reopens the edit, switches camera at frame 120, maps
the second camera's playback channels explicitly, and downloads a real ProRes
and PCM movie. Independent full decoding checks all 278 picture frames and all
556,000 stereo sample frames against the original fixture sound.

Example Chromium invocation (absolute paths required):

```sh
node scripts/studio/test_multicam_sync_browser.cjs \
  --python /absolute/numpy-runtime/bin/python \
  --browser /absolute/chromium \
  --evidence /absolute/new-evidence-directory
```

For native acceptance, compile `macos/SmokeTest.swift` separately with `swiftc`.
Write `source_inventory()` from `test_multicam_sync_macos` to a JSON file, then
invoke the native coordinator once for each phase with the same
`--fixture-workspace` and `--source-manifest`, a distinct `--output`, and the
compiled `--binary`. The ordinary CLI refuses non-macOS execution. The browser
driver explicitly labels Chromium evidence and never claims native acceptance.

These helpers do not certify physical mouse/keyboard input, the production Save
panel, the installed application launcher, arbitrary production footage, or
long-running editing sessions. Measured reports, rather than the existence of
the helpers, establish any accepted result.
