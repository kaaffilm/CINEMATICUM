# Source integrity and repeatable verification

`source-integrity.json` records SHA-256 and byte length for the tracked Studio
source, tests, native and web code, runtime locks and documentation, plus the
root README and Studio verification workflow. `source_integrity.py` owns the
explicit suffix and exclusion policy, and copies that policy into the manifest.
The manifest excludes itself, generated evidence, binary outputs, media,
temporary test fixtures and virtual environments. It has no timestamp or
self-referential commit ID, so the same source reproduces identical bytes.

Check a Git checkout without modifying it:

```bash
python3 -I scripts/studio/source_integrity.py --check
```

The check fails for changed bytes, missing or newly tracked source, untracked
source within scope (including ignored source), unsafe symlink paths, or a
modified manifest scope. It never hashes or adopts untracked files into the
manifest. Stage intentional source additions first, finish documentation, then
regenerate and check before committing the frozen source:

```bash
python3 -I scripts/studio/source_integrity.py --write
python3 -I scripts/studio/source_integrity.py --check
```

The source version is read as a literal from `server.py`, without importing the
server. This is a reproducibility check against an explicit source inventory;
it is not a signature or a substitute for reviewing a changed manifest.

## Actual engines and skipped-test policy

The Studio workflow uses Ubuntu 24.04 and Python 3.11. Its fresh verification
venv installs the six packages in
`verification-linux-x86_64.requirements.txt` with exact versions, published
SHA-256 wheel hashes, binary-only installation and dependency resolution.
Hashes also cover CPython 3.12 Linux x86_64 for local reproduction. The OpenCV
and NumPy versions match the current tracking installer. Official metadata at
[PyPI](https://pypi.org/pypi/opencv-python-headless/4.11.0.86/json) permits NumPy
2.3.5 with this OpenCV version on both Python versions.

`fetch_verification_raw.py --output /absolute/path/to/camera-fixture.KDC`
fetches the real Kodak DC50 RAW test input from rawpy's immutable
upstream commit and checks its exact length and SHA-256. The binary stays in
the runner's temporary directory. Its [upstream attribution](https://github.com/letmaik/rawpy/blob/a39c2e7a44911889c3360891012f862f904ba551/test/README.txt)
identifies the rawsamples.ch camera sample and CC BY-NC-SA 4.0 license. It is a
verification input, not production footage or a bundled application asset.

Run the full discoverable suite with the isolated venv interpreter:

```bash
CINEMATICUM_RAW_TEST_FILE=/absolute/path/to/authentic-camera-raw \
  /absolute/path/to/venv/bin/python -I scripts/studio/run_verification.py \
  --report /absolute/path/to/verification-report.json
```

The runner verifies installed versions and venv isolation, binds both imaging
and tracking workers to that interpreter, and fails on every skipped test,
including class-level setup skips. Thus missing OpenCV cannot turn the planar
inference suite into an apparently passing run. An explicit local
`--allow-missing-raw` permits only the exact genuine-RAW test and its missing
fixture reason when no RAW path was supplied. CI never selects that exception.
Expected failures also fail the release runner. JSON receipts record runtime
versions, RAW identity, executed-test count and all exceptions.

macOS UI/download/playback and Blender executable harnesses are separate
acceptance commands; Python discovery does not certify those native gates.
