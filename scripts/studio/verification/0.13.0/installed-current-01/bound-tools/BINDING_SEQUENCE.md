# Accepted-source and external readiness-tool binding

These 0.13 acceptance tools retain the previously accepted observation,
ownership, termination and preservation methods. Version expectations are
0.13.0/build 14. The actual controller compilation receipt is retained under
`../native-build/controller-build-01.json`; no installed application is certified
by that compilation alone.

`run_installed_readiness_phased.py` is a deliberately fail-closed template. Its
`CORE`, `CORE_TREE`, `CORE_MANIFEST` and `NATIVE_SHA` are unset. It cannot certify
an installation until those identities are known. They must not be filled in
inside the clean committed source used for native or complete-suite acceptance.

The release sequence is:

1. Freeze and commit the intended product, tests, native sources, CI and source
   manifest. Record the exact core commit, tree and manifest SHA-256 externally.
2. Run the bounded native feature phases against that clean source. Retain any
   failed phase and its source identity; a necessary source correction produces
   a new explicit freeze rather than rewriting the earlier evidence.
3. After the native gates pass, run the complete strict frozen suite. Record
   unchanged source and managed runtimes. Build the actual native application
   from the same accepted source, recording its executable SHA-256.
4. Copy this entire tool directory into a fresh owned acceptance directory
   outside the source checkout. Substitute only the four identity constants in
   that external readiness copy with the accepted core/tree/manifest and actual
   native executable hashes. The controller source/binary and launch-runner
   pins already refer to their actual reviewed 0.13 identities.
5. Compare the external helper with the core template, require that only the
   four approved constant assignments changed, and record the before/after
   SHA-256 and exact values. Keep all existing fail-closed guards. Run its
   existing guard regressions on the bound copy, then pass that exact helper
   SHA-256 and core commit in the installation/readiness invocation.
6. Run independent installation, canonical launch and phased installed-runtime
   acceptance using the external tools and the clean accepted source. Each
   report binds the actual source/build/bundle/controller/project identities.
7. A later evidence-only publication commit may preserve the exact external
   bound tool and reports alongside product/source reconciliation. It must not
   relabel an older full-suite report as having tested changed source. Final
   published-source CI remains an explicit gate.

The external tool handoff and its actual hash are separate acceptance artifacts.
This prevents a circular self-reference in which filling in a commit hash
changes a tracked file and invalidates the clean-HEAD build requirement.

The guard test requires an explicit accepted Git checkout, independently of
the external helper directory. After binding the external copy, run:

```sh
CINEMATICUM_ACCEPTED_SOURCE=/absolute/clean/accepted/source \
python3 -I -B /absolute/external/tools/test_installed_readiness_phased_guards.py
```

The test checks that the supplied source actually resolves the pinned core
commit to the pinned Git tree. Missing/relative source paths fail; the helper
directory is never treated as an inferred source checkout. These are portable
guard regressions and do not claim native application execution.
