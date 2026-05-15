SHELL := /bin/bash

FILM := THE_LAST_RENDER
OUT := dist/films/$(FILM)/$(FILM).mp4
SOURCE_SHOTS := source/films/$(FILM)/shots

.PHONY: help qc-stack qc-source render qc-final qc list-shots open clean-local

help:
	echo "CINEMATICUM real film stack"
	echo ""
	echo "make qc-stack    - verify no-toy production stack exists"
	echo "make qc-source   - verify required source shot MP4s exist"
	echo "make render      - assemble real source shots or use VIDEO_GEN_COMMAND"
	echo "make qc-final    - verify final rendered MP4"
	echo "make qc          - run stack/source/final QC"
	echo "make list-shots  - print required source shot filenames"
	echo "make open        - open final film"

qc-stack:
	python3 scripts/qc-no-toy-stack.py

qc-source:
	python3 scripts/qc-source-shots.py

render:
	bash scripts/render-the-last-render-film.sh

qc-final:
	python3 scripts/qc-final-film.py

qc: qc-stack qc-source qc-final

list-shots:
	python3 -c 'import json; from pathlib import Path; p=Path("production/THE_LAST_RENDER/shots/shotlist.json"); data=json.loads(p.read_text()); shots=data.get("shots", data); [print(s.get("file") or s.get("filename") or s.get("source") or s.get("path") or (s.get("id","") + ".mp4")) for s in shots]' 

open:
	open "$(OUT)"

clean-local:
	rm -rf dist/films/$(FILM)
