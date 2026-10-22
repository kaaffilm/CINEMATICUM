# Scene processing version 1

The Studio scene-processing tool authors an acyclic, typed data graph saved in
the project. Paths identify scene locations, not host files. Scene evaluation
is deterministic and branch-local; an explicit render action starts Cycles.

## Document and operations

Source assets contain validated CINEMATICUM scene data. Graph nodes support
source placement, merge, grouping, transforms, material and attribute edits,
named sets, pruning, camera selection, scoped contexts, time warping and asset
variants. Filters select scene paths and sets. Context values have declared
types and bounds; `frame` and `fps` have explicit built-in definitions.

Evaluation preserves stable location paths and returns the selected camera,
sets, attributes and transformed scene. Invalid references, cycles, ambiguous
locations, unsupported data and exceeded budgets fail before rendering.

| Resource | Limit |
| --- | ---: |
| Nodes | 128 |
| Assets | 32 |
| Evaluated locations | 512 |
| Hierarchy depth | 32 |
| Dispatch tasks | 64 |
| Graph document | 8 MiB |
| Evaluated document | 64 MiB |
| Output artifact | 8 GiB |

## Execution and persistence

Editing/applying a graph uses the shared project and undo history. The actual
render retains `graph.json`, `evaluation.json`, the authored scene, `.blend`,
preview, optional linear-master package and a receipt that binds their bytes.
Portable project archives include the graph's owned assets and results.

Distributed execution uses explicitly paired TLS workers and fixed typed
operations. A durable SQLite dispatcher records immutable request identities,
bounded task dependencies, results and cancellation. Retried observation does
not manufacture another completed task. Retrieved artifacts must match the
authenticated result hashes before publication into the project.

The implementation does not provide arbitrary Python execution, a Gaffer
plugin interpreter, general USD/Alembic exchange, an unbounded scheduler or
production-farm certification. `test_scene_processing.py`,
`test_scene_dispatch_store.py` and the browser harness exercise the actual
contracts. Their executed results belong to the exact verification freeze.
