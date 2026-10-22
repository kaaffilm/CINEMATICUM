# Ordinary quit during editor startup

The native window now waits for two actual readiness events before preparing
quit: completion of the local document, then the editor's authenticated
bootstrap operation. It saves any dirty project before asking the production
server to reserve shutdown. Active jobs still require the real native **Keep
Working** / **Cancel Jobs and Quit** decision. No elapsed grace period, retry
loop, force termination, token bypass or fabricated job state was added.

## Defect and evidence

The installed 0.10 canonical launch observation reported one ordinary
`NSRunningApplication.terminate()` request which remained open after 15 seconds.
A second ordinary request succeeded about 0.4 seconds later. The final shutdown
receipt recorded `native-quit-no-active-jobs`, with no active or terminal jobs.
The original attempt has no captured JavaScript error or native alert, so its
exact callback failure remains unobserved.

Two genuine startup failures were independently reproduced against the
preserved pre-change page and the exact original native quit expression:

| Actual response boundary | Original result | New behavior |
| --- | --- | --- |
| The local page has committed, but deferred `app.js` has not arrived | `api is not defined` | The pending native request resumes from the document's `didFinish` event |
| `app.js` has loaded, but `/api/bootstrap` has not returned its token and project | HTTP 403: application token is missing or expired | `prepareNativeQuit` awaits the actual bootstrap promise, then sends one authenticated request |

These are verified defects compatible with the installed observation; this
record does not assert that either was conclusively the historical cause.

`didCommit` resets document readiness. A provisional navigation which becomes
a download does not invalidate the document that remains open. Navigation or
WebKit failures cancel a pending quit safely rather than silently leaving its
AppKit termination reply unresolved.

The frontend quit function awaits any existing save, refuses another unfinished
project operation, saves the current dirty draft, and rechecks that the draft is
settled before contacting `/api/prepare-quit`. Failed bootstrap or save leaves
the editor and server open. The server's existing authentication, atomic
admission closure, explicit cancellation decision, worker joins and durable
shutdown receipt are unchanged.

## Verified in the isolated Linux candidate

- The browser gate passed **39/39** checks in **21.651 seconds**, including both
  original failures, real token ordering, a held real save, a genuine concurrent
  project revision conflict, failed-bootstrap refusal, an actual FFmpeg worker,
  explicit cancellation, and byte-preserved source media.
- The existing shutdown/admission race suite passed **5/5** tests.
- Both JavaScript files and all three new Python entry points passed syntax
  checks.
- The native helper's emit-only build retained the production class body
  byte-for-byte. It replaces only the top-level application bootstrap.

The browser result is in `verification/startup-quit/browser-report.json`.
Chromium does not certify AppKit. Native compilation and the following phases
must pass on a Mac before claiming native acceptance or installing this change.

## Bounded actual native acceptance

Build `build_startup_quit.py` with the exact source root, a fresh output folder,
and the expected SHA-256 of `macos/StudioApp.swift`. Its `--emit-only` option
checks source binding without claiming native compilation.

Run `test_startup_quit_macos.py` with the resulting binary, actual Python
interpreter, a fresh evidence folder, and one of these phases:

| Phase | Actual native acceptance |
| --- | --- |
| `app-script` | Request ordinary quit while the local page exists and the real application script is held at an explicit transport barrier |
| `bootstrap` | Request ordinary quit after the script loads and before the real bootstrap token/project response is released |
| `protection` | Start a real FFmpeg render through shipped controls, make an ordinary dirty edit, quit, click actual Keep Working, verify the saved edit and still-running worker, quit again, then click actual Cancel Jobs and Quit |

Each phase owns a fresh ENGINE TEST workspace and a foreground server. The
helper releases its startup barrier as a consequence of the actual native quit
request; an elapsed delay is not its success condition. Native phase deadline
is 13 seconds, followed by at most two seconds of owned graceful failure
cleanup. The outer coordinator has a 17-second observation bound and does not
force-kill a timed-out process. Every phase records source hashes, actual HTTP
quit decisions, shutdown receipts and source preservation. The protection phase
also captures the two actual native alerts and verifies the durable cancelled
job. Existing installed applications and user projects are not touched by these
fixtures.

Canonical installed launch/quit and bundle/project preservation still require
their separate installed-application acceptance after integration.
