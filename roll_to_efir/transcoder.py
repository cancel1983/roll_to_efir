"""ffmpeg command construction and process helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Callable

from .preset import EprPreset


@dataclass(frozen=True)
class TranscodeJob:
    source: Path
    preset: EprPreset
    output: Path
    ffmpeg: str = "ffmpeg"


def find_ffmpeg() -> str | None:
    """Return the ffmpeg executable path if it is available on PATH."""

    return shutil.which("ffmpeg")


def default_output_path(source: str | Path) -> Path:
    """Build a safe default MXF output path next to the source file."""

    source_path = Path(source)
    return source_path.with_name(f"{source_path.stem}_efir.mxf")


def build_ffmpeg_command(job: TranscodeJob) -> list[str]:
    """Create an ffmpeg command that turns ``source`` into an MXF file."""

    preset = job.preset
    command = [job.ffmpeg, "-y", "-hide_banner", "-i", str(job.source)]

    video_filters: list[str] = []
    if preset.width and preset.height:
        video_filters.append(f"scale={preset.width}:{preset.height}")
    if preset.interlaced is True:
        video_filters.append("format=yuv422p")

    if video_filters:
        command.extend(["-vf", ",".join(video_filters)])

    command.extend(["-c:v", preset.video_codec or "mpeg2video"])
    if preset.frame_rate:
        command.extend(["-r", _fraction_to_ffmpeg(preset.frame_rate)])
    if preset.video_bitrate:
        command.extend(["-b:v", str(preset.video_bitrate)])
    if preset.video_codec in {None, "mpeg2video"}:
        command.extend(["-pix_fmt", "yuv422p"])
    if preset.interlaced is True:
        command.extend(["-flags", "+ildct+ilme", "-top", "1"])

    command.extend(["-c:a", preset.audio_codec or "pcm_s16le"])
    command.extend(["-ar", str(preset.audio_sample_rate or 48_000)])
    command.extend(["-ac", str(preset.audio_channels or 2)])
    if preset.audio_bitrate and (preset.audio_codec or "pcm_s16le") not in {"pcm_s16le", "pcm_s24le"}:
        command.extend(["-b:a", str(preset.audio_bitrate)])

    command.extend(["-f", "mxf", str(job.output)])
    return command


def run_transcode(job: TranscodeJob, on_output: Callable[[str], None] | None = None) -> int:
    """Run ffmpeg and stream stderr/stdout lines to an optional callback."""

    process = subprocess.Popen(
        build_ffmpeg_command(job),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        if on_output:
            on_output(line.rstrip())
    return process.wait()


def _fraction_to_ffmpeg(value) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"
