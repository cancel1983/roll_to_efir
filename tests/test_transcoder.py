from fractions import Fraction
from pathlib import Path

from roll_to_efir.preset import EprPreset
from roll_to_efir.transcoder import TranscodeJob, build_ffmpeg_command, default_output_path


def test_default_output_path_adds_efir_suffix():
    assert default_output_path("/tmp/source.mov") == Path("/tmp/source_efir.mxf")


def test_build_ffmpeg_command_uses_preset_values():
    preset = EprPreset(
        path=Path("preset.epr"),
        width=1920,
        height=1080,
        frame_rate=Fraction(25, 1),
        video_codec="mpeg2video",
        video_bitrate=50_000_000,
        audio_codec="pcm_s16le",
        audio_sample_rate=48_000,
        audio_channels=2,
        interlaced=True,
    )
    command = build_ffmpeg_command(TranscodeJob(Path("in.mp4"), preset, Path("out.mxf"), ffmpeg="ffmpeg"))

    assert command == [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-i",
        "in.mp4",
        "-vf",
        "scale=1920:1080,format=yuv422p",
        "-c:v",
        "mpeg2video",
        "-r",
        "25",
        "-b:v",
        "50000000",
        "-pix_fmt",
        "yuv422p",
        "-flags",
        "+ildct+ilme",
        "-top",
        "1",
        "-c:a",
        "pcm_s16le",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-f",
        "mxf",
        "out.mxf",
    ]
