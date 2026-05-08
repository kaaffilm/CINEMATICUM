#!/usr/bin/env bash
set -euo pipefail

python3 scripts/regenerate-object-registry.py --write
python3 -m unittest tests/test_authority_object_admission_closure_seal.py
bash scripts/verify-authority-object-admission-closure-seal.sh
python3 -m unittest tests/test_transition_attempt_rejection_ledger.py
python3 -m unittest tests/test_third_future_sound_final_mix_lock_authority_object_instantiation_record.py
python3 -m unittest tests/test_state_transition_gate.py
python3 -m unittest tests/test_state_advancement_execution_record.py
python3 -m unittest tests/test_sixth_future_archivist_proof_chain_lock_authority_object_instantiation_record.py
python3 -m unittest tests/test_seventh_future_outsider_replay_passage_authority_object_instantiation_record.py
python3 -m unittest tests/test_second_future_editorial_timeline_authority_object_instantiation_record.py
python3 -m unittest tests/test_required_authority_objects.py
python3 -m unittest tests/test_repository_status_seal.py
python3 -m unittest tests/test_release_candidate_law.py
python3 -m unittest tests/test_release_candidate_gap_ledger.py
python3 -m unittest tests/test_release_candidate_artifacts_docket.py
python3 -m unittest tests/test_release_candidate_manifest.py
python3 -m unittest tests/test_release_candidate_evidence_bundle.py
python3 -m unittest tests/test_release_candidate_public_inspection_dossier.py
python3 -m unittest tests/test_release_candidate_outsider_replay_plan.py
python3 -m unittest tests/test_release_candidate_terminal_closure_plan.py
python3 -m unittest tests/test_release_candidate_outsider_replay_execution_record.py
python3 -m unittest tests/test_release_candidate_outsider_replay_passage_record.py
python3 -m unittest tests/test_release_candidate_admissibility_verdict_record.py
python3 -m unittest tests/test_release_candidate_terminal_closure_record.py
python3 -m unittest tests/test_release_candidate_ready_state_advancement_request.py
python3 -m unittest tests/test_real_case_authority_object_slot_index.py
python3 -m unittest tests/test_real_case_authority_object_admission_terminal_seal.py
python3 -m unittest tests/test_real_case_authority_object_admission_request_validator.py
python3 -m unittest tests/test_real_case_authority_object_admission_request_schema.py
python3 -m unittest tests/test_real_case_authority_object_admission_request_rejection_corpus.py
python3 -m unittest tests/test_real_case_authority_object_admission_rejection_taxonomy.py
python3 -m unittest tests/test_real_case_authority_object_admission_permanence_seal.py
python3 -m unittest tests/test_real_case_authority_object_admission_future_snapshot_fork_gate.py
python3 -m unittest tests/test_real_case_authority_object_admission_future_continuity_seal.py
python3 -m unittest tests/test_real_case_authority_object_admission_finality_seal.py
python3 -m unittest tests/test_real_case_authority_object_admission_enforcement_gate.py
python3 -m unittest tests/test_real_case_authority_object_admission_decision_ledger.py
python3 -m unittest tests/test_real_case_authority_object_admission_closure_seal.py
python3 -m unittest tests/test_real_case_authority_intake_docket.py
python3 -m unittest tests/test_public_perimeter_sentinel.py
python3 -m unittest tests/test_public_inspection_negative_proof.py
python3 -m unittest tests/test_public_inspection_dossier.py
python3 -m unittest tests/test_outsider_replay_bundle_law.py
python3 -m unittest tests/test_outsider_clone_replay.py
python3 -m unittest tests/test_open_real_case_authority_intake.py
python3 -m unittest tests/test_object_registry_freshness.py
python3 -m unittest tests/test_object_registry.py
python3 -m unittest tests/test_non_star_seal_redundancy_stop_rule.py
python3 -m unittest tests/test_master_verification_manifest_closure.py
python3 -m unittest tests/test_master_progression.py
python3 -m unittest tests/test_future_authority_satisfaction_gate.py
python3 -m unittest tests/test_fourth_future_color_grade_lock_authority_object_instantiation_record.py
python3 -m unittest tests/test_first_future_director_final_cut_authority_object_instantiation_record.py
python3 -m unittest tests/test_first_future_director_final_cut_authority_object_admission_request_validation_record.py
python3 -m unittest tests/test_first_future_director_final_cut_authority_object_admission_request.py
python3 -m unittest tests/test_first_future_director_final_cut_authority_object_admission_decision_record.py
python3 -m unittest tests/test_fifth_future_release_delivery_artifacts_lock_authority_object_instantiation_record.py
python3 -m unittest tests/test_explicit_state_advancement_request.py
python3 -m unittest tests/test_explicit_state_advancement_decision_record.py
python3 -m unittest tests/test_eighth_future_terminal_closure_authority_object_instantiation_record.py
python3 -m unittest tests/test_current_zero_ledger_no_further_advancement_proof.py
python3 -m unittest tests/test_current_state_index.py
python3 -m unittest tests/test_cinematic_jurisdiction.py
python3 -m unittest tests/test_cinematic_issuance_docket.py
python3 -m unittest tests/test_authority_precedence_lattice.py
python3 -m unittest tests/test_authority_object_template_kit.py
python3 -m unittest tests/test_authority_object_instantiation_gate.py
python3 -m unittest tests/test_authority_object_admission_request_validator.py
python3 -m unittest tests/test_authority_object_admission_request_schema.py
python3 -m unittest tests/test_authority_object_admission_request_rejection_corpus.py
python3 -m unittest tests/test_authority_object_admission_rejection_taxonomy.py
python3 -m unittest tests/test_authority_object_admission_intake_validation_gate.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_validator.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_terminal_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_schema.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_rejection_taxonomy.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_rejection_corpus.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_permanence_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_zero_perimeter_completion_index.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_terminal_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_terminal_closure_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_permanence_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_outsider_replay_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_terminal_closure_index_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_release_candidate_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_public_replay_index_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_public_inspection_verdict_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_proof_artifact_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_outsider_replay_passage_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_media_admission_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_issuance_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_authority_satisfaction_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_audience_artifact_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_non_advancement_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_future_continuity_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_finality_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger_closure_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_ledger.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_snapshot_fork_gate.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_future_continuity_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_finality_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_enforcement_gate.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_decision_ledger.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_request_closure_seal.py
python3 -m unittest tests/test_authority_object_admission_intake_reopening_gate.py
python3 -m unittest tests/test_authority_object_admission_intake_rejection_ledger.py
python3 -m unittest tests/test_authority_object_admission_intake_order.py
python3 -m unittest tests/test_authority_object_admission_intake_finality_seal.py
python3 -m unittest tests/test_authority_object_admission_enforcement_gate.py
python3 -m unittest tests/test_authority_object_admission_docket.py
python3 -m unittest tests/test_authority_object_admission_decision_ledger.py
python3 -m unittest tests/test_authority_acceptance_law.py
bash scripts/verify-transition-attempt-rejection-ledger.sh
bash scripts/verify-third-future-sound-final-mix-lock-authority-object-instantiation-record.sh
bash scripts/verify-state-transition-gate.sh
bash scripts/verify-state-advancement-execution-record.sh
bash scripts/verify-sixth-future-archivist-proof-chain-lock-authority-object-instantiation-record.sh
bash scripts/verify-seventh-future-outsider-replay-passage-authority-object-instantiation-record.sh
bash scripts/verify-second-future-editorial-timeline-authority-object-instantiation-record.sh
bash scripts/verify-required-authority-objects.sh
bash scripts/verify-repository-status-seal.sh
bash scripts/verify-release-candidate-law.sh
bash scripts/verify-release-candidate-gap-ledger.sh
bash scripts/verify-release-candidate-artifacts-docket.sh
bash scripts/verify-release-candidate-manifest.sh
bash scripts/verify-release-candidate-evidence-bundle.sh
bash scripts/verify-release-candidate-public-inspection-dossier.sh
bash scripts/verify-release-candidate-outsider-replay-plan.sh
bash scripts/verify-release-candidate-terminal-closure-plan.sh
bash scripts/verify-release-candidate-outsider-replay-execution-record.sh
bash scripts/verify-release-candidate-outsider-replay-passage-record.sh
bash scripts/verify-release-candidate-admissibility-verdict-record.sh
bash scripts/verify-release-candidate-terminal-closure-record.sh
bash scripts/verify-release-candidate-ready-state-advancement-request.sh
bash scripts/verify-real-case-authority-object-slot-index.sh
bash scripts/verify-real-case-authority-object-admission-terminal-seal.sh
bash scripts/verify-real-case-authority-object-admission-request-validator.sh
bash scripts/verify-real-case-authority-object-admission-request-schema.sh
bash scripts/verify-real-case-authority-object-admission-request-rejection-corpus.sh
bash scripts/verify-real-case-authority-object-admission-rejection-taxonomy.sh
bash scripts/verify-real-case-authority-object-admission-permanence-seal.sh
bash scripts/verify-real-case-authority-object-admission-future-snapshot-fork-gate.sh
bash scripts/verify-real-case-authority-object-admission-future-continuity-seal.sh
bash scripts/verify-real-case-authority-object-admission-finality-seal.sh
bash scripts/verify-real-case-authority-object-admission-enforcement-gate.sh
bash scripts/verify-real-case-authority-object-admission-decision-ledger.sh
bash scripts/verify-real-case-authority-object-admission-closure-seal.sh
bash scripts/verify-real-case-authority-intake-docket.sh
bash scripts/verify-public-perimeter-sentinel.sh
bash scripts/verify-public-inspection-negative-proof.sh
bash scripts/verify-public-inspection-dossier.sh
bash scripts/verify-outsider-replay-bundle-law.sh
bash scripts/verify-outsider-clone-replay.sh
bash scripts/verify-open-real-case-authority-intake.sh
bash scripts/verify-object-registry.sh
bash scripts/verify-object-registry-fresh.sh
bash scripts/verify-non-star-seal-redundancy-stop-rule.sh
bash scripts/verify-master-verification-manifest-closure.sh
bash scripts/verify-master-progression.sh
bash scripts/verify-future-authority-satisfaction-gate.sh
bash scripts/verify-fourth-future-color-grade-lock-authority-object-instantiation-record.sh
bash scripts/verify-first-future-director-final-cut-authority-object-instantiation-record.sh
bash scripts/verify-first-future-director-final-cut-authority-object-admission-request.sh
bash scripts/verify-first-future-director-final-cut-authority-object-admission-request-validation-record.sh
bash scripts/verify-first-future-director-final-cut-authority-object-admission-decision-record.sh
bash scripts/verify-fifth-future-release-delivery-artifacts-lock-authority-object-instantiation-record.sh
bash scripts/verify-explicit-state-advancement-request.sh
bash scripts/verify-explicit-state-advancement-decision-record.sh
bash scripts/verify-eighth-future-terminal-closure-authority-object-instantiation-record.sh
bash scripts/verify-current-zero-ledger-no-further-advancement-proof.sh
bash scripts/verify-current-state-index.sh
bash scripts/verify-cinematic-jurisdiction.sh
bash scripts/verify-cinematic-issuance-docket.sh
bash scripts/verify-authority-precedence-lattice.sh
bash scripts/verify-authority-object-template-kit.sh
bash scripts/verify-authority-object-instantiation-gate.sh
bash scripts/verify-authority-object-admission-request-validator.sh
bash scripts/verify-authority-object-admission-request-schema.sh
bash scripts/verify-authority-object-admission-request-rejection-corpus.sh
bash scripts/verify-authority-object-admission-rejection-taxonomy.sh
bash scripts/verify-authority-object-admission-intake-validation-gate.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-validator.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-terminal-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-schema.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-rejection-taxonomy.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-rejection-corpus.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-permanence-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-zero-perimeter-completion-index.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-terminal-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-terminal-closure-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-permanence-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-outsider-replay-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-terminal-closure-index-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-release-candidate-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-public-replay-index-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-public-inspection-verdict-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-proof-artifact-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-outsider-replay-passage-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-media-admission-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-issuance-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-authority-satisfaction-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-audience-artifact-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-non-advancement-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-future-continuity-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-finality-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-ledger-closure-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-snapshot-fork-gate.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-future-continuity-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-finality-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-enforcement-gate.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-decision-ledger.sh
bash scripts/verify-authority-object-admission-intake-reopening-request-closure-seal.sh
bash scripts/verify-authority-object-admission-intake-reopening-gate.sh
bash scripts/verify-authority-object-admission-intake-rejection-ledger.sh
bash scripts/verify-authority-object-admission-intake-order.sh
bash scripts/verify-authority-object-admission-intake-finality-seal.sh
bash scripts/verify-authority-object-admission-enforcement-gate.sh
bash scripts/verify-authority-object-admission-docket.sh
bash scripts/verify-authority-object-admission-decision-ledger.sh
bash scripts/verify-authority-acceptance-law.sh
python3 scripts/regenerate-object-registry.py --check

while IFS= read -r script; do
  bash "$script"

  base="$(basename "$script")"
  base="${base#verify-}"
  base="${base%.sh}"
  test_file="tests/test_${base//-/_}.py"

  if [ -f "$test_file" ]; then
    python3 -m unittest "$test_file"
  fi
done < <(find scripts -maxdepth 1 -type f -name 'verify-*.sh' ! -name 'verify-all.sh' | LC_ALL=C sort)

bash scripts/verify-release-candidate-ready-state-advancement-decision-record.sh
python3 -m unittest tests/test_release_candidate_ready_state_advancement_execution_record.py
bash scripts/verify-release-candidate-ready-state-advancement-execution-record.sh
python3 -m unittest tests/test_release_candidate_ready_current_state_index_advancement_record.py
bash scripts/verify-release-candidate-ready-current-state-index-advancement-record.sh
python3 -m unittest tests/test_release_candidate_ready_state_advancement_decision_record.py
python3 -m unittest tests/test_release_candidate_ready_issuance_unblocking_request.py
bash scripts/verify-release-candidate-ready-issuance-unblocking-request.sh
python3 -m unittest tests/test_release_candidate_ready_issuance_unblocking_decision_record.py
bash scripts/verify-release-candidate-ready-issuance-unblocking-decision-record.sh
bash scripts/verify-release-candidate-ready-issuance-blockade-seal.sh
printf "CINEMATICUM VERIFY ALL: PASS\n"
