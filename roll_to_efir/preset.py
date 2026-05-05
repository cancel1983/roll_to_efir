"""Adobe Media Encoder ``.epr`` preset parsing helpers.

EPR files are XML documents, but Adobe changes concrete tag names between
exporters and versions.  The parser below deliberately extracts a small,
well-known set of transcoding settings from tag names, attributes and text
values while keeping the original file optional for later improvements.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
import re
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class EprPreset:
    """Normalized video/audio settings inferred from an Adobe ``.epr`` file."""

    path: Path
    name: str = "Adobe Media Encoder preset"
    width: int | None = None
    height: int | None = None
    frame_rate: Fraction | None = None
    video_codec: str | None = None
    video_bitrate: int | None = None
    audio_codec: str | None = None
    audio_sample_rate: int | None = None
    audio_channels: int | None = None
    audio_bitrate: int | None = None
    interlaced: bool | None = None

    @property
    def frame_rate_text(self) -> str:
        if self.frame_rate is None:
            return "не задано"
        value = float(self.frame_rate)
        if self.frame_rate.denominator == 1:
            return str(self.frame_rate.numerator)
        return f"{value:.3f}".rstrip("0").rstrip(".")

    def summary_lines(self) -> list[str]:
        return [
            f"Пресет: {self.name}",
            f"Видео: {self.video_codec or 'по умолчанию'}",
            f"Размер: {self.width or '—'}×{self.height or '—'}",
            f"Частота кадров: {self.frame_rate_text}",
            f"Видеобитрейт: {_format_bitrate(self.video_bitrate)}",
            f"Развертка: {_format_interlace(self.interlaced)}",
            f"Аудио: {self.audio_codec or 'pcm_s16le'}",
            f"Частота аудио: {self.audio_sample_rate or 48000} Гц",
            f"Каналы: {self.audio_channels or 2}",
            f"Аудиобитрейт: {_format_bitrate(self.audio_bitrate)}",
        ]


def load_epr(path: str | Path) -> EprPreset:
    """Load an Adobe Media Encoder preset and infer ffmpeg-compatible settings."""

    preset_path = Path(path)
    text = preset_path.read_text(encoding="utf-8-sig", errors="replace")
    root = ET.fromstring(text)
    values = _collect_values(root)

    def first_int(*patterns: str) -> int | None:
        for value in _matching_values(values, patterns):
            parsed = _parse_int(value)
            if parsed is not None:
                return parsed
        return None

    def first_rate(*patterns: str) -> Fraction | None:
        for value in _matching_values(values, patterns):
            parsed = _parse_rate(value)
            if parsed is not None:
                return parsed
        return None

    def first_text(*patterns: str) -> str | None:
        for value in _matching_values(values, patterns):
            value = value.strip()
            if value:
                return value
        return None

    def first_interlace() -> bool | None:
        for key, candidates in values.items():
            if re.search("progressive", key, re.IGNORECASE):
                for candidate in candidates:
                    parsed = _parse_bool(candidate)
                    if parsed is not None:
                        return not parsed
            if re.search("field.*order|interlac", key, re.IGNORECASE):
                for candidate in candidates:
                    parsed = _parse_interlace(candidate)
                    if parsed is not None:
                        return parsed
        return None

    return EprPreset(
        path=preset_path,
        name=first_text("preset.*name", "export.*name", "name") or preset_path.stem,
        width=first_int("frame.*width", "video.*width", "width"),
        height=first_int("frame.*height", "video.*height", "height"),
        frame_rate=first_rate("frame.*rate", "timebase", "fps"),
        video_codec=_normalize_video_codec(first_text("video.*codec", "encoder.*video", "codec")),
        video_bitrate=first_int("video.*bit.*rate", "target.*bit.*rate", "bitrate"),
        audio_codec=_normalize_audio_codec(first_text("audio.*codec", "encoder.*audio")),
        audio_sample_rate=first_int("audio.*sample.*rate", "sample.*rate"),
        audio_channels=first_int("audio.*channel", "num.*channel", "channel"),
        audio_bitrate=first_int("audio.*bit.*rate"),
        interlaced=first_interlace(),
    )


def _collect_values(root: ET.Element) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for element in root.iter():
        key = _clean_key(element.tag)
        if element.text and element.text.strip():
            values.setdefault(key, []).append(element.text.strip())
        for attr_name, attr_value in element.attrib.items():
            lowered_name = attr_name.lower()
            if lowered_name in {"name", "key", "id"}:
                text_value = element.text.strip() if element.text else ""
                if text_value:
                    values.setdefault(_clean_key(attr_value), []).append(text_value)
                if "value" in element.attrib:
                    values.setdefault(_clean_key(attr_value), []).append(element.attrib["value"].strip())
            elif lowered_name != "value":
                values.setdefault(_clean_key(attr_name), []).append(attr_value.strip())
    return values


def _matching_values(values: dict[str, list[str]], patterns: tuple[str, ...]):
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    for key, candidates in values.items():
        if any(pattern.search(key) for pattern in compiled):
            yield from candidates


def _clean_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.split("}")[-1].lower())


def _parse_int(value: str) -> int | None:
    match = re.search(r"\d+(?:\.\d+)?", value.replace(",", "."))
    if not match:
        return None
    number = float(match.group(0))
    if number <= 0:
        return None
    if number < 1000 and "bit" in value.lower():
        number *= 1000
    return int(round(number))


def _parse_rate(value: str) -> Fraction | None:
    normalized = value.strip().replace(",", ".")
    if not normalized:
        return None
    rational = re.search(r"(\d+)\s*/\s*(\d+)", normalized)
    if rational:
        denominator = int(rational.group(2))
        return Fraction(int(rational.group(1)), denominator) if denominator else None
    number = re.search(r"\d+(?:\.\d+)?", normalized)
    if not number:
        return None
    fps = float(number.group(0))
    if fps > 1000:  # Adobe timebase-like values are often ticks per second.
        common = {
            23976: Fraction(24000, 1001),
            2997: Fraction(30000, 1001),
            5994: Fraction(60000, 1001),
        }
        return common.get(int(round(fps)), None)
    return Fraction(normalized).limit_denominator(1001)


def _normalize_video_codec(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.lower()
    if "mpeg" in lowered and "2" in lowered:
        return "mpeg2video"
    if "xdcam" in lowered:
        return "mpeg2video"
    if "h.264" in lowered or "h264" in lowered or "avc" in lowered:
        return "libx264"
    if "dnx" in lowered:
        return "dnxhd"
    if "dv" in lowered:
        return "dvvideo"
    return value


def _normalize_audio_codec(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.lower()
    if "pcm" in lowered or "wave" in lowered or "wav" in lowered:
        return "pcm_s16le"
    if "aac" in lowered:
        return "aac"
    if "mpeg" in lowered or "mp2" in lowered:
        return "mp2"
    return value


def _parse_bool(value: str | None) -> bool | None:
    if not value:
        return None
    lowered = value.strip().lower()
    if lowered in {"true", "1", "yes", "on"}:
        return True
    if lowered in {"false", "0", "no", "off"}:
        return False
    return None


def _parse_interlace(value: str | None) -> bool | None:
    if not value:
        return None
    lowered = value.lower()
    if "progress" in lowered or lowered in {"false", "0", "none", "no"}:
        return False
    if "upper" in lowered or "lower" in lowered or "interlac" in lowered or lowered in {"true", "1", "yes"}:
        return True
    return None


def _format_bitrate(value: int | None) -> str:
    if value is None:
        return "не задан"
    if value >= 1_000_000:
        return f"{value / 1_000_000:g} Мбит/с"
    if value >= 1_000:
        return f"{value / 1_000:g} кбит/с"
    return f"{value} бит/с"


def _format_interlace(value: bool | None) -> str:
    if value is None:
        return "по пресету/источнику"
    return "чересстрочная" if value else "progressive"
