#!/usr/bin/env bash
set -euo pipefail

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

printf "CINEMATICUM VERIFY ALL: PASS\n"
