# CINEMATICUM 0.13 CI and installed-tool binding review

**Review complete: the one concrete acceptance-tool defect is corrected. No outstanding concrete defect was found in the requested scope.** No tests, source edits, native calls or remote operations were performed by this reviewer.

## Finding and correction

The original external guard test inferred its accepted Git source with `BASE.parents[4]`. This worked only at the repository-relative tool location and could not validate the documented external copied-tool directory. The original source hash was `4212221fb032b3c6c964a83718e30c49ec5ad38b166de7331d0528467ada0710`; the initial finding is preserved in `cinematicum-013-ci-binding-review-01.json`.

The owner changed only the guard test, its binding documentation and prepared identity record. It now requires an explicit absolute accepted source and retains actual Git core/tree verification:

```sh
CINEMATICUM_ACCEPTED_SOURCE=/absolute/clean/accepted/source \
python3 -I -B /absolute/external/tools/test_installed_readiness_phased_guards.py
```

Corrected test SHA256: `5132e6e2cf7b0e0adf70105b9c88bc6687a6d65476a7ae5d3683cd91bfb907c5`. The retained owner receipt records six actual focused guard tests passing from a genuine external copy, without native execution or an invented native hash. The reviewer inspected that exact diff and receipt without rerunning them.

## Requested binding checks

- CI explicitly checks out the PR head SHA (or event SHA), then verifies its declared source inventory.
- The Lensfun pinned commit, 116,602-byte fixture and SHA256 agree with the retained original source; CI uses a fresh test-only directory and passes the profile explicitly.
- The independent schema environment uses the exact CPython 3.12 lxml 6.1.1 wheel, isolated offline hash-checked installation and matching libxml2 2.14.6. Apple document and extracted 1.10 DTD size/hash pins match retained acceptance. Actual imported/downloaded XML is validated in an explicit CI gate; missing or mismatched dependencies fail.
- The readiness template retains unset core/tree/manifest/native constants and refuses native acceptance until bound. Exact runner/controller pins match actual source and retained controller compilation.
- The external coordinator reads accepted source from the pinned installation receipt and can run without altering the accepted core. Ownership, no-active-job, read-only endpoint, ordinary termination, private baseline and final whole-bundle/project preservation guards remain intact.

Workflow SHA256: `d23ef75db3f80bd9f1bc400ca52d03d653ed45391360147f2ec1fa64ca1279d7`. Unchanged coordinator SHA256: `4a9e19cd07837a5e2376aa0a407416f83dda6af16babeccf066cf0ebba20b0d7`. Full inspected identities, exact wheel/document/DTD pins and the retained correction receipt are recorded in `cinematicum-013-ci-binding-review.json`.

This is a source review, not a certificate of 0.13 native workflows, full regression, installation or executed CI.
