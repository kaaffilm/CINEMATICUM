# CINEMATICUM — Object Registry Regeneration Guard

PR9 adds a freshness guard for `CINEMATICUM_OBJECT_REGISTRY.json`.

The registry is generated from repository JSON objects. If a future PR adds, removes, or reclassifies a JSON object without regenerating the registry, the guard fails.

## Commands

Regenerate:

    python3 scripts/regenerate-object-registry.py --write

Check freshness:

    bash scripts/verify-object-registry-fresh.sh

Run everything:

    bash scripts/verify-all.sh

## Boundary

The guard does not issue a film.

The guard does not admit media.

The guard does not execute replay.

The guard does not produce an admissibility verdict.
