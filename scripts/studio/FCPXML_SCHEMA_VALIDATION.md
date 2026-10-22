# Independent FCPXML schema acceptance

The shipping importer/exporter uses Python's standard library. Its independent
schema gate uses a separate, explicit lxml runtime and Apple's unmodified
FCPXML **1.10** DTD. The gate does not import the product parser and never uses
input-supplied DTDs, external entities or network resolution. A missing runtime,
changed fixture, invalid schema or absent actual export fails; none is skipped.

## Exact independent inputs

| Input | Pinned identity |
| --- | --- |
| lxml | 6.1.1, native Linux x86_64 CPython 3.12 manylinux_2_26/_2_28 wheel, 5,240,367 bytes |
| Wheel SHA-256 | `ebe6af670449830d6d9b752c256a983291c766a1365ba5d5460048f9e33a7818` |
| Runtime/compiled libxml2 | 2.14.6 |
| Official Apple Markdown | 41,495 bytes, SHA-256 `b4ed24c7dfbb84fb81bdb6880029f007b7784459256b9b489397d7264dc5735a` |
| Extracted DTD | 40,206 bytes, SHA-256 `6044527401b6cc92a9d86383437794d8de801c1904b6d08409ce81720fd23f33` |

The source URL is Apple's
[Document Type Definition](https://developer.apple.com/documentation/professional-video-applications/document-type-definition.md).
Extraction uses the sole Swift-fenced DTD block plus one final newline, with
the original copyright notice preserved. The wheel is pinned from
[official PyPI metadata](https://pypi.org/pypi/lxml/6.1.1/json).
The [lxml DTD API](https://lxml.de/validation.html#dtd) performs the independent
grammar check. All byte counts, URLs and hashes are in
`fcpxml-schema-validation-lock.json`.

The bootstrap creates a **new test-only directory and isolated venv**. It
downloads/verifies the exact wheel and Apple document, verifies the extracted
DTD, installs the wheel using hashes with no index/dependency lookup, runs
`pip check`, and records actual lxml/libxml2/module identities. It does not
change the application or the shared verification runtime.

## Reproduce

Use native Linux x86_64 Python 3.12 and a fresh absolute destination:

```sh
python3 -I -B scripts/studio/bootstrap_fcpxml_schema_validation.py \
  --root /absolute/new-fcpxml-validator
```

For a previously downloaded exact wheel and Apple Markdown, optional
`--wheel /absolute/pinned.whl` and `--apple-document /absolute/pinned.md`
avoid downloading; the same immutable hashes still apply. Existing roots are
refused so previous results cannot be overwritten or silently reused.

After the actual phased browser workflow, validate its exact hand-authored
input and completed downloaded export:

```sh
/absolute/new-fcpxml-validator/runtime/bin/python -I -B \
  scripts/studio/validate_fcpxml_schema.py \
  --dtd /absolute/new-fcpxml-validator/FCPXMLv1_10.dtd \
  --hand-fixture /absolute/fcpxml-acceptance/prepare/ENGINE_TEST_input.fcpxml \
  --export /absolute/fcpxml-acceptance/author/ENGINE_TEST_exported.fcpxml \
  --report /absolute/new-schema-report.json
```

Both input roles are mandatory and must name distinct regular files. Each
document is limited to 8 MiB, 100,000 nodes and depth 64; there are at most
32 explicitly supplied files. The gate first proves the actual DTD accepts an
independent minimal positive control and rejects an invalid element. It also
requires rejection of external DTD/entity inputs and a 1.9 version claim.
It then validates every supplied document, records all schema diagnostics and
rechecks input/DTD/validator identities before passing.

The product's 1.9 import compatibility is a separately tested common subset.
This gate certifies **1.10 grammar only**. DTD success does not establish
source-time mapping, rendered picture/audio equality, physical file-panel
interaction or actual Final Cut Pro application interoperability; the media
and Studio UI acceptance provide their own distinct evidence.
