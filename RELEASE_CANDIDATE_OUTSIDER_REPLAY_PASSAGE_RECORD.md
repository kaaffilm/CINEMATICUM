# RELEASE_CANDIDATE_OUTSIDER_REPLAY_PASSAGE_RECORD

This object records passage of the release-candidate outsider replay after the outsider replay execution record.

It asserts:

- `OUTSIDER_REPLAY_EXECUTION_RECORD_PRESENT=true`
- `OUTSIDER_REPLAY_PASSAGE_RECORD_PRESENT=true`
- `OUTSIDER_REPLAY_PASSED=true`

It preserves:

- `RELEASE_CANDIDATE_READY=false`
- `ISSUED=false`
- `MEDIA_PRESENT=false`
- `ADMISSIBILITY_VERDICT_PRESENT=false`
- `TERMINAL_CLOSURE_PRESENT=false`

Next required object:

`RELEASE_CANDIDATE_ADMISSIBILITY_VERDICT_RECORD`
