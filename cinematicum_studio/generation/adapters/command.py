from __future__ import annotations

import os
import shlex
import subprocess

from .base import GenerationResult


class CommandVideoAdapter:
    name = "command"

    def __init__(self) -> None:
        cmd = os.environ.get("CINEMATICUM_VIDEO_GENERATOR")
        if not cmd:
            raise RuntimeError(
                "CINEMATICUM_VIDEO_GENERATOR is not set. "
                "Set it to a real video generator command accepting "
                "--prompt TEXT --duration SECONDS --out FILE [--seed INT]."
            )
        self.command = cmd

    def generate(
        self,
        *,
        prompt: str,
        duration: int,
        output_path: str,
        seed: int | None = None,
    ) -> GenerationResult:
        cmd = [
            *shlex.split(self.command),
            "--prompt",
            prompt,
            "--duration",
            str(duration),
            "--out",
            output_path,
        ]
        if seed is not None:
            cmd += ["--seed", str(seed)]

        subprocess.run(cmd, check=True)

        return GenerationResult(
            backend=self.name,
            model=os.environ.get("CINEMATICUM_VIDEO_MODEL", "external-video-generator"),
            output_path=output_path,
            seed=seed,
            duration=duration,
        )
