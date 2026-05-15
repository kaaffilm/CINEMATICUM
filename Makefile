.RECIPEPREFIX := >
FILM=THE_LAST_RENDER

.PHONY: check render open status

check:
>python3 scripts/qc-no-toy-stack.py

render:
>bash scripts/render-the-last-render-film.sh

open:
>open dist/films/$(FILM)/$(FILM).mp4

status:
>git status --short
