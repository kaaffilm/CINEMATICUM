FILM=THE_LAST_RENDER

check:
	python3 scripts/qc-no-toy-stack.py

source-qc:
	python3 scripts/qc-source-shots.py

render:
	bash scripts/render-the-last-render-film.sh

final-qc:
	python3 scripts/qc-final-film.py

open:
	open dist/films/$(FILM)/$(FILM).mp4

clean-local:
	rm -rf dist/films/$(FILM)
