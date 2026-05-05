from fractions import Fraction

from roll_to_efir.preset import load_epr


def test_load_epr_extracts_common_export_settings(tmp_path):
    preset = tmp_path / "broadcast.epr"
    preset.write_text(
        """
        <Preset>
          <PresetName>EFIR OP1a</PresetName>
          <FrameWidth>1920</FrameWidth>
          <FrameHeight>1080</FrameHeight>
          <FrameRate>25</FrameRate>
          <VideoCodec>MPEG2 Video</VideoCodec>
          <VideoBitRate>50000000</VideoBitRate>
          <FieldOrder>Upper First</FieldOrder>
          <AudioCodec>PCM</AudioCodec>
          <AudioSampleRate>48000</AudioSampleRate>
          <AudioChannels>2</AudioChannels>
        </Preset>
        """,
        encoding="utf-8",
    )

    parsed = load_epr(preset)

    assert parsed.name == "EFIR OP1a"
    assert parsed.width == 1920
    assert parsed.height == 1080
    assert parsed.frame_rate == Fraction(25, 1)
    assert parsed.video_codec == "mpeg2video"
    assert parsed.video_bitrate == 50_000_000
    assert parsed.audio_codec == "pcm_s16le"
    assert parsed.audio_sample_rate == 48_000
    assert parsed.audio_channels == 2
    assert parsed.interlaced is True


def test_load_epr_supports_name_value_style(tmp_path):
    preset = tmp_path / "xmp.epr"
    preset.write_text(
        """
        <Preset>
          <Property name="VideoFrameWidth" value="1280" />
          <Property name="VideoFrameHeight" value="720" />
          <Property name="Timebase" value="30000/1001" />
          <Property name="Progressive" value="true" />
        </Preset>
        """,
        encoding="utf-8",
    )

    parsed = load_epr(preset)

    assert parsed.width == 1280
    assert parsed.height == 720
    assert parsed.frame_rate == Fraction(30000, 1001)
    assert parsed.interlaced is False
