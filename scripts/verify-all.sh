#!/usr/bin/env bash
set -euo pipefail
python3 scripts/regenerate-object-registry.py --check
bash scripts/verify-current-state-index.sh
bash scripts/verify-repository-status-seal.sh
bash scripts/verify-object-registry.sh
bash scripts/verify-mission-done.sh
python3 -m unittest discover -s tests -p 'test_*.py'
