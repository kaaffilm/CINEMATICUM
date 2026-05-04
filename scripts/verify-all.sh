#!/usr/bin/env bash
set -euo pipefail

# scripts/verify-all.sh is the master battery entrypoint.

bash scripts/verify-cinematic-jurisdiction.sh
python3 -m unittest tests/test_cinematic_jurisdiction.py

bash scripts/verify-cinematic-issuance-docket.sh
python3 -m unittest tests/test_cinematic_issuance_docket.py

bash scripts/verify-release-candidate-law.sh
python3 -m unittest tests/test_release_candidate_law.py

bash scripts/verify-authority-acceptance-law.sh
python3 -m unittest tests/test_authority_acceptance_law.py

bash scripts/verify-outsider-replay-bundle-law.sh
python3 -m unittest tests/test_outsider_replay_bundle_law.py

bash scripts/verify-current-state-index.sh
python3 -m unittest tests/test_current_state_index.py

bash scripts/verify-master-progression.sh
python3 -m unittest tests/test_master_progression.py

bash scripts/verify-object-registry.sh
python3 -m unittest tests/test_object_registry.py

bash scripts/verify-object-registry-fresh.sh
python3 -m unittest tests/test_object_registry_freshness.py

bash scripts/verify-repository-status-seal.sh
python3 -m unittest tests/test_repository_status_seal.py

bash scripts/verify-public-inspection-dossier.sh
python3 -m unittest tests/test_public_inspection_dossier.py

bash scripts/verify-public-inspection-negative-proof.sh
python3 -m unittest tests/test_public_inspection_negative_proof.py

bash scripts/verify-authority-precedence-lattice.sh
python3 -m unittest tests/test_authority_precedence_lattice.py

bash scripts/verify-state-transition-gate.sh
python3 -m unittest tests/test_state_transition_gate.py

bash scripts/verify-required-authority-objects.sh
python3 -m unittest tests/test_required_authority_objects.py

bash scripts/verify-transition-attempt-rejection-ledger.sh
python3 -m unittest tests/test_transition_attempt_rejection_ledger.py

bash scripts/verify-public-perimeter-sentinel.sh
python3 -m unittest tests/test_public_perimeter_sentinel.py

bash scripts/verify-outsider-clone-replay.sh
python3 -m unittest tests/test_outsider_clone_replay.py

bash scripts/verify-authority-object-template-kit.sh
python3 -m unittest tests/test_authority_object_template_kit.py

bash scripts/verify-authority-object-instantiation-gate.sh
python3 -m unittest tests/test_authority_object_instantiation_gate.py

bash scripts/verify-authority-object-admission-docket.sh
python3 -m unittest tests/test_authority_object_admission_docket.py

bash scripts/verify-authority-object-admission-request-schema.sh
python3 -m unittest tests/test_authority_object_admission_request_schema.py

bash scripts/verify-authority-object-admission-request-validator.sh
python3 -m unittest tests/test_authority_object_admission_request_validator.py

bash scripts/verify-authority-object-admission-request-rejection-corpus.sh
python3 -m unittest tests/test_authority_object_admission_request_rejection_corpus.py

bash scripts/verify-authority-object-admission-rejection-taxonomy.sh
python3 -m unittest tests/test_authority_object_admission_rejection_taxonomy.py

bash scripts/verify-authority-object-admission-decision-ledger.sh
python3 -m unittest tests/test_authority_object_admission_decision_ledger.py

bash scripts/verify-authority-object-admission-enforcement-gate.sh
python3 -m unittest tests/test_authority_object_admission_enforcement_gate.py
bash scripts/verify-authority-object-admission-closure-seal.sh
python3 -m unittest tests/test_authority_object_admission_closure_seal.py
bash scripts/verify-authority-object-admission-intake-order.sh
python3 -m unittest tests/test_authority_object_admission_intake_order.py
bash scripts/verify-authority-object-admission-intake-validation-gate.sh
python3 -m unittest tests/test_authority_object_admission_intake_validation_gate.py
bash scripts/verify-authority-object-admission-intake-rejection-ledger.sh
python3 -m unittest tests/test_authority_object_admission_intake_rejection_ledger.py
bash scripts/verify-authority-object-admission-intake-finality-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_finality_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-gate.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_gate.py
bash scripts/verify-authority-object-admission-intake-reopening-request-schema.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_schema.py
bash scripts/verify-authority-object-admission-intake-reopening-request-validator.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_validator.py
bash scripts/verify-authority-object-admission-intake-reopening-request-rejection-corpus.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_rejection_corpus.py
bash scripts/verify-authority-object-admission-intake-reopening-request-rejection-taxonomy.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-decision-ledger.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_rejection_taxonomy.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_decision_ledger.py
bash scripts/verify-authority-object-admission-intake-reopening-request-closure-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_closure_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-finality-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_finality_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-terminal-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_terminal_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-permanence-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_permanence_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-continuity-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_continuity_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-gate.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_gate.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-closure-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_closure_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-finality-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_finality_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-terminal-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_terminal_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-permanence-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_permanence_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-future-continuity-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_future_continuity_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-outsider-replay-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_outsider_replay_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-terminal-closure-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_terminal_closure_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-issuance-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_issuance_seal.py
bash scripts/verify-master-verification-manifest-closure.sh
python3 -m unittest tests/test_master_verification_manifest_closure.py

printf "CINEMATICUM VERIFY ALL: PASS\n"
bash scripts/verify-authority-object-admission-intake-reopening-request-enforcement-gate.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_enforcement_gate.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-authority-satisfaction-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_authority_satisfaction_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-advancement-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_advancement_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-release-candidate-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-media-admission-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-audience-artifact-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-proof-artifact-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_release_candidate_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_media_admission_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_audience_artifact_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_proof_artifact_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-outsider-replay-passage-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_outsider_replay_passage_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-terminal-closure-index-seal.sh
python3 tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_terminal_closure_index_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-public-replay-index-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_public_replay_index_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-public-inspection-verdict-seal.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_public_inspection_verdict_seal.py
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-zero-perimeter-completion-index.sh
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_zero_perimeter_completion_index.py
bash scripts/verify-non-star-seal-redundancy-stop-rule.sh
python3 -m unittest tests/test_non_star_seal_redundancy_stop_rule.py
bash scripts/verify-current-zero-ledger-no-further-advancement-proof.sh
python3 -m unittest tests/test_current_zero_ledger_no_further_advancement_proof.py
bash scripts/verify-open-real-case-authority-intake.sh
python3 -m unittest tests/test_open_real_case_authority_intake.py
bash scripts/verify-real-case-authority-intake-docket.sh
python3 -m unittest tests/test_real_case_authority_intake_docket.py
bash scripts/verify-real-case-authority-object-slot-index.sh
python3 -m unittest tests/test_real_case_authority_object_slot_index.py
bash scripts/verify-real-case-authority-object-admission-request-schema.sh
python3 -m unittest tests/test_real_case_authority_object_admission_request_schema.py
bash scripts/verify-real-case-authority-object-admission-request-validator.sh
bash scripts/verify-real-case-authority-object-admission-request-rejection-corpus.sh
python3 -m unittest tests/test_real_case_authority_object_admission_request_validator.py
python3 -m unittest tests/test_real_case_authority_object_admission_request_rejection_corpus.py
bash scripts/verify-real-case-authority-object-admission-rejection-taxonomy.sh
python3 -m unittest tests/test_real_case_authority_object_admission_rejection_taxonomy.py
bash scripts/verify-real-case-authority-object-admission-decision-ledger.sh
python3 -m unittest tests/test_real_case_authority_object_admission_decision_ledger.py
