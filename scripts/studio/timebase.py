"""Exact project clocks shared by editing, rendering, previews and 3D delivery.

Timeline positions remain integer frames. A frame rate is a reduced rational,
never a rounded display label. Audio samples are rounded at absolute timeline
boundaries; subtracting those boundaries prevents a succession of cuts from
accumulating independently rounded sample lengths.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math


_STANDARD_LABELS = {23.976: (24000, 1001), 29.97: (30000, 1001),
                    59.94: (60000, 1001), 119.88: (120000, 1001)}
_MAX_COMPONENT = 1_000_000


def _fraction(value, label="Time"):
    if isinstance(value, bool) or not isinstance(value, (int, float, Fraction)):
        raise ValueError(f"{label} must be a finite number.")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{label} must be a finite number.")
        return Fraction(str(value))
    return Fraction(value)


@dataclass(frozen=True)
class FrameRate:
    numerator: int
    denominator: int = 1

    def __post_init__(self):
        if (type(self.numerator) is not int or type(self.denominator) is not int
                or not 1 <= self.numerator <= _MAX_COMPONENT
                or not 1 <= self.denominator <= _MAX_COMPONENT):
            raise ValueError("Frame-rate numerator and denominator must be integers from 1 to 1,000,000.")
        divisor = math.gcd(self.numerator, self.denominator)
        object.__setattr__(self, "numerator", self.numerator // divisor)
        object.__setattr__(self, "denominator", self.denominator // divisor)

    @property
    def fraction(self):
        return Fraction(self.numerator, self.denominator)

    @property
    def fps(self):
        return self.numerator if self.denominator == 1 else self.numerator / self.denominator

    @property
    def ffmpeg(self):
        return f"{self.numerator}/{self.denominator}"

    @property
    def time_base(self):
        return f"{self.denominator}/{self.numerator}"

    @property
    def conform_time_base(self):
        """A high-resolution clock containing an integer number of ticks/frame.

        AVTB's microseconds cannot represent every project frame exactly. A
        fractional trim then changes which side of an fps rounding tie a PTS
        lands on. Keep project-frame shifts integral before the fps filter and
        keep the AVRational denominator within its signed 32-bit bound.
        """
        subdivisions = min(10_000, (2 ** 31 - 1) // self.numerator)
        return f"1/{self.numerator * subdivisions}"

    @property
    def expression(self):
        return f"({self.numerator}/{self.denominator})"

    @property
    def blender_fps(self):
        return max(1, round(self.fraction))

    @property
    def blender_fps_base(self):
        return float(Fraction(self.blender_fps * self.denominator, self.numerator))

    def as_dict(self):
        return {"numerator": self.numerator, "denominator": self.denominator}

    def seconds_for_frames(self, frames):
        return _fraction(frames, "Frame position") / self.fraction

    def seconds_decimal(self, frames):
        # AVOption duration parsers accept decimal seconds, not expressions.
        # Seventeen significant digits retain the whole double when an option
        # eventually converts to its own integer time base.
        return format(float(self.seconds_for_frames(frames)), ".17g")

    def seconds_expression(self, frames):
        value = self.seconds_for_frames(frames)
        return f"({value.numerator}/{value.denominator})"

    def samples_for_frames(self, frames, sample_rate=48000):
        if type(sample_rate) is not int or not 1 <= sample_rate <= 384000:
            raise ValueError("Audio sample rate must be an integer from 1 to 384,000.")
        return round(self.seconds_for_frames(frames) * sample_rate)

    def sample_span(self, start, duration, sample_rate=48000):
        return (self.samples_for_frames(_fraction(start) + _fraction(duration), sample_rate)
                - self.samples_for_frames(start, sample_rate))

    def frames_for_seconds(self, seconds, rounding="nearest"):
        value = _fraction(seconds) * self.fraction
        if rounding == "floor":
            return math.floor(value)
        if rounding == "ceil":
            return math.ceil(value)
        if rounding != "nearest":
            raise ValueError("Frame rounding must be nearest, floor or ceil.")
        return round(value)

    def max_timeline_frames(self, seconds):
        return self.frames_for_seconds(seconds, "floor")


def parse_rate(value=24, *, maximum=60):
    """Accept a rational object, integer fps or recognized decimal rate label.

    Explicit rational values may use any positive ratio in the supported range.
    Rounded decimal labels 23.976/29.97/59.94 normalize to their broadcast clocks;
    other fractional numbers need numerator/denominator to make intent explicit.
    """
    if isinstance(value, FrameRate):
        rate = value
    elif isinstance(value, Fraction):
        rate = FrameRate(value.numerator, value.denominator)
    elif isinstance(value, dict):
        if set(value) != {"numerator", "denominator"}:
            raise ValueError("frame_rate must contain numerator and denominator only.")
        rate = FrameRate(value["numerator"], value["denominator"])
    elif isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        if value == int(value):
            rate = FrameRate(int(value))
        else:
            rate = None
            for label, (numerator, denominator) in _STANDARD_LABELS.items():
                if abs(value - label) < 1e-9 or abs(value - numerator / denominator) < 1e-9:
                    rate = FrameRate(numerator, denominator)
                    break
            if rate is None:
                raise ValueError("Fractional frame rates need an exact frame_rate numerator/denominator, or 23.976, 29.97 or 59.94.")
    else:
        raise ValueError("Frame rate must be a number or an exact numerator/denominator object.")
    if not 1 <= rate.fraction <= maximum:
        raise ValueError(f"Frame rate must be between 1 and {maximum} frames per second.")
    return rate


def project_rate(project, *, maximum=60):
    """Read the canonical clock and reject contradictory legacy fps metadata."""
    if not isinstance(project, dict):
        raise ValueError("Project must be an object.")
    if "frame_rate" not in project:
        return parse_rate(project.get("fps", 24), maximum=maximum)
    rate = parse_rate(project["frame_rate"], maximum=maximum)
    if "fps" in project:
        value = project["fps"]
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value)):
            raise ValueError("Project fps must be a finite number matching frame_rate.")
        if abs(value - rate.fps) > 1e-9:
            try:
                same = parse_rate(value, maximum=maximum) == rate
            except ValueError:
                same = False
            if not same:
                raise ValueError("Project fps conflicts with its exact frame_rate. Supply matching values.")
    return rate
