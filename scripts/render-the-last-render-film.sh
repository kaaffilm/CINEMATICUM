#!/usr/bin/env bash
set -euo pipefail
python3 scripts/qc-no-toy-stack.py
python3 scripts/render-the-last-render-film.py
python3 scripts/qc-final-film.py
