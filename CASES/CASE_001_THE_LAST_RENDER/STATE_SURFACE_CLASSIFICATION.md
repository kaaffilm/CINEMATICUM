# CASE_001_THE_LAST_RENDER — State Surface Classification

PR6 separates active current truth from layer-status records.

## Active current-state surfaces

- `CINEMATICUM_CURRENT_STATE_INDEX.json`
- `CASES/CASE_001_THE_LAST_RENDER/CURRENT_CASE_STATE.json`

## Layer-status records

- `CASES/CASE_001_THE_LAST_RENDER/RELEASE_CANDIDATE_STATUS.json`
- `CASES/CASE_001_THE_LAST_RENDER/AUTHORITY_ACCEPTANCE_STATUS.json`
- `CASES/CASE_001_THE_LAST_RENDER/OUTSIDER_REPLAY_BUNDLE_STATUS.json`

Layer-status records preserve staged law progression.

They do not outrank the active current-state index.

Current active state:

    OUTSIDER_REPLAY_BUNDLE_LAW_DECLARED

Still false:

    release_candidate_ready=false
    issued=false
    media_present=false
    outsider_replay_passed=false
