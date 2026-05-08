from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GenerationResult:
    backend: str
    model: str
    output_path: str
    seed: int | None
    duration: int
    width: int | None = None
    height: int | None = None
    fps: int | None = None


class VideoGenerationAdapter(Protocol):
    name: str

    def generate(
        self,
        *,
        prompt: str,
        duration: int,
        output_path: str,
        seed: int | None = None,
    ) -> GenerationResult:
        ...
