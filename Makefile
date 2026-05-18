SHELL := /bin/bash
PYTHON ?= python3

FILM := THE_LAST_RENDER
OUT := dist/films/$(FILM)/$(FILM).mp4
SOURCE_SHOTS := source/films/$(FILM)/shots

.PHONY: help qc-stack qc-source qc-source-media source-shots render qc-final qc list-shots open clean-local backend-status backend-selftest film

help:
	@echo "CINEMATICUM real film stack"
	@echo ""
	@echo "make qc-stack        - verify no-toy production stack exists"
	@echo "make qc-source       - verify required source shot MP4s exist and pass media forensics"
	@echo "make qc-source-media - inspect source shot MP4 realism gates"
	@echo "make source-shots    - generate/acquire required real shot MP4s via VIDEO_GEN_COMMAND"
	@echo "make render          - assemble real source shots"
	@echo "make qc-final        - verify final rendered MP4"
	@echo "make backend-status  - verify backend executable is real"
	@echo "make backend-selftest - verify backend writes a valid realistic MP4"
	@echo "make film            - one-button real film path"
	@echo "make list-shots      - print required source shot filenames"
	@echo "make open            - open final film"

qc-stack:
	$(PYTHON) scripts/qc-no-toy-stack.py

qc-source:
	$(PYTHON) scripts/qc-source-shots.py
	$(PYTHON) scripts/qc-source-shot-media.py

qc-source-media:
	$(PYTHON) scripts/qc-source-shot-media.py

source-shots:
	$(PYTHON) scripts/generate-source-shots-with-backend.py

render:
	bash scripts/render-the-last-render-film.sh

qc-final:
	$(PYTHON) scripts/qc-final-film.py
	$(PYTHON) scripts/qc-final-film-media.py

qc: qc-stack qc-source qc-final

list-shots:
	$(PYTHON) -c 'import json; from pathlib import Path; p=Path("production/THE_LAST_RENDER/shots/shotlist.json"); data=json.loads(p.read_text()); shots=data.get("shots", data); [print(s.get("file") or s.get("filename") or s.get("source") or s.get("path") or (s.get("id","") + ".mp4")) for s in shots]'

open:
	open "$(OUT)"

clean-local:
	rm -rf dist/films/$(FILM)

backend-status:
	@test -n "$$VIDEO_GEN_COMMAND" || (echo "REAL_BACKEND_NOT_CONFIGURED=true"; echo "SET=VIDEO_GEN_COMMAND=/path/to/real/backend make film"; exit 1)
	@test "$$VIDEO_GEN_COMMAND" != "./scripts/backends/your-real-backend.sh" || (echo "PLACEHOLDER_BACKEND_REFUSED=true"; echo "REPLACE=scripts/backends/your-real-backend.sh with a real video backend call"; exit 1)
	@test "$$VIDEO_GEN_COMMAND" != "/absolute/path/to/real/video/backend" || (echo "PLACEHOLDER_BACKEND_REFUSED=true"; echo "USE_ACTUAL_EXECUTABLE_PATH=true"; exit 1)
	@test -x "$$VIDEO_GEN_COMMAND" || (echo "BACKEND_EXECUTABLE_NOT_FOUND=$$VIDEO_GEN_COMMAND"; echo "USE_ACTUAL_EXECUTABLE_PATH=true"; exit 1)
	@echo "VIDEO_GEN_COMMAND=$$VIDEO_GEN_COMMAND"

backend-selftest: backend-status
	@rm -rf /tmp/cinematicum-backend-selftest
	@mkdir -p /tmp/cinematicum-backend-selftest
	@CINEMATICUM_SHOT_ID=backend_contract_selftest \
	 CINEMATICUM_PROMPT_JSON=production/THE_LAST_RENDER/prompts/001_service_road_rain.json \
	 CINEMATICUM_OUTPUT_MP4=/tmp/cinematicum-backend-selftest/backend_contract_selftest.mp4 \
	 "$$VIDEO_GEN_COMMAND"
	@$(PYTHON) scripts/qc-backend-output.py /tmp/cinematicum-backend-selftest/backend_contract_selftest.mp4

film: qc-stack backend-status backend-selftest source-shots qc-source render qc-final
	@echo "REAL_FILM_READY=$(OUT)"

.PHONY: qc-final-media-selftest
qc-final-media-selftest:
	bash scripts/qc-final-film-media-selftest.sh\n
.PHONY: source-shot-one
source-shot-one:
	python3 scripts/generate-one-source-shot-with-backend.py
	python3 scripts/qc-source-shot-media.py source/films/$(FILM)/shots/$${SHOT_ID}.mp4
