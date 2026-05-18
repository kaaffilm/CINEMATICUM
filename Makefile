SHELL := /bin/bash
FILM := THE_LAST_RENDER
OUT := dist/films/$(FILM)/$(FILM).mp4
SOURCE_SHOTS := source/films/$(FILM)/shots
NATIVE_BACKEND := $(CURDIR)/scripts/backends/cinematicum-native-comfyui-backend.mjs

.PHONY: help qc-stack qc-source source-shot-one source-shots render qc-final qc list-shots backend-status backend-selftest native-backend-status source-shot-one-native source-shots-native film film-native open clean-local

help:
	@echo "CINEMATICUM real film stack"
	@echo "make qc-stack              - verify production stack"
	@echo "make qc-source             - verify real source shot MP4s"
	@echo "make source-shot-one       - generate one shot using VIDEO_GEN_COMMAND"
	@echo "make source-shots          - generate all shots using VIDEO_GEN_COMMAND"
	@echo "make render                - assemble final film"
	@echo "make qc-final              - verify final film"
	@echo "make film                  - full external backend path"
	@echo "make film-native           - full CINEMATICUM native local ComfyUI path"
	@echo "make list-shots            - list required shot MP4 names"

qc-stack:
	python3 scripts/qc-no-toy-stack.py

qc-source:
	python3 scripts/qc-source-shots.py

source-shot-one:
	python3 scripts/generate-one-source-shot-with-backend.py

source-shots:
	python3 scripts/generate-source-shots-with-backend.py

render:
	bash scripts/render-the-last-render-film.sh

qc-final:
	python3 scripts/qc-final-film.py

qc: qc-stack qc-source render qc-final

list-shots:
	python3 -c 'import json; from pathlib import Path; p=Path("production/THE_LAST_RENDER/shots/shotlist.json"); data=json.loads(p.read_text()); shots=data.get("shots", data); [print(s.get("file") or s.get("filename") or s.get("source") or s.get("path") or (s.get("id","") + ".mp4")) for s in shots]'

backend-status:
	@test -n "$$VIDEO_GEN_COMMAND" || (echo "REAL_BACKEND_NOT_CONFIGURED=true"; echo "SET=VIDEO_GEN_COMMAND=/path/to/real/backend make film"; exit 1)
	@test "$$VIDEO_GEN_COMMAND" != "./scripts/backends/your-real-backend.sh" || (echo "PLACEHOLDER_BACKEND_REFUSED=true"; exit 1)
	@test "$$VIDEO_GEN_COMMAND" != "/actual/executable/backend" || (echo "PLACEHOLDER_BACKEND_REFUSED=true"; exit 1)
	@test "$$VIDEO_GEN_COMMAND" != "/absolute/path/to/real/video/backend" || (echo "PLACEHOLDER_BACKEND_REFUSED=true"; exit 1)
	@test -x "$$VIDEO_GEN_COMMAND" || (echo "BACKEND_EXECUTABLE_NOT_FOUND=$$VIDEO_GEN_COMMAND"; exit 1)
	@echo "VIDEO_GEN_COMMAND=$$VIDEO_GEN_COMMAND"

backend-selftest: backend-status
	@rm -rf /tmp/cinematicum-backend-selftest
	@mkdir -p /tmp/cinematicum-backend-selftest
	@CINEMATICUM_SHOT_ID=backend_contract_selftest CINEMATICUM_PROMPT_JSON=production/THE_LAST_RENDER/prompts/001_service_road_rain.json CINEMATICUM_OUTPUT_MP4=/tmp/cinematicum-backend-selftest/backend_contract_selftest.mp4 "$$VIDEO_GEN_COMMAND"
	@python3 scripts/qc-backend-output.py /tmp/cinematicum-backend-selftest/backend_contract_selftest.mp4

native-backend-status:
	@node "$(NATIVE_BACKEND)" --status

source-shot-one-native: native-backend-status
	VIDEO_GEN_COMMAND="$(NATIVE_BACKEND)" $(MAKE) source-shot-one

source-shots-native: native-backend-status
	VIDEO_GEN_COMMAND="$(NATIVE_BACKEND)" $(MAKE) source-shots

film: qc-stack backend-status backend-selftest source-shots qc-source render qc-final
	@echo "REAL_FILM_READY=$(OUT)"

film-native: qc-stack native-backend-status
	VIDEO_GEN_COMMAND="$(NATIVE_BACKEND)" $(MAKE) film

open:
	open "$(OUT)"

clean-local:
	rm -rf dist/films/$(FILM)
