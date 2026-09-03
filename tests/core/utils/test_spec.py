"""Tests for tiddl.core.utils.spec: StreamSpec 规格推导、码率查表、模板字段。

目标:显示/模板的比特率、码率、位深、采样率与真实流一一对应。
"""

import base64
from types import SimpleNamespace

import pytest

from tiddl.core.utils.format import format_template, validate_template
from tiddl.core.utils.spec import (
    ATMOS_BITRATE_KBPS,
    StreamSpec,
    normalize_cli_quality,
)


class TestNormalizeQuality:
    @pytest.mark.parametrize(
        ("input", "expected"),
        [
            ("low", "LOW"),
            ("normal", "HIGH"),
            ("high", "LOSSLESS"),
            ("max", "HI_RES_LOSSLESS"),
            ("LOW", "LOW"),
            ("NORMAL", "HIGH"),
            ("HIGH", "LOSSLESS"),  # CLI "high" = 无损
            ("MAX", "HI_RES_LOSSLESS"),
            ("BOGUS", "BOGUS"),  # 未知值原样返回
            ("", ""),
            (None, ""),
        ],
    )
    def test_maps_cli(self, input, expected):
        assert normalize_cli_quality(input) == expected


class TestPredict:
    """下载前预测(文件名模板用),预测规则 = v1 实际行为。"""

    def test_lossless_is_flac_44_1_16(self):
        for q in ("LOSSLESS", "HI_RES_LOSSLESS", "high", "max"):
            s = StreamSpec.predict(q)
            assert s.codec == "flac"
            assert s.extension == ".flac"
            assert s.bit_depth == 16
            assert s.sample_rate == 44100
            assert s.bitrate_kbps is None  # 无损不显示假码率
            assert "FLAC" in s.spec_label

    def test_low_is_96kbps_he_aac(self):
        s = StreamSpec.predict("LOW")
        assert s.codec == "mp4a.40.5"
        assert s.extension == ".m4a"
        assert s.bitrate_kbps == 96
        assert s.bitrate_label == "96 kbps"

    def test_normal_is_320kbps_aac_lc(self):
        s = StreamSpec.predict("normal")
        assert s.codec == "mp4a.40.2"
        assert s.bitrate_kbps == 320
        assert s.spec_label == "AAC-LC 320 kbps"

    def test_atmos_predicts_eac3_768(self):
        # Atmos-only:v1 无论请求什么档位都只给 E-AC-3
        s = StreamSpec.predict("high", audio_mode="DOLBY_ATMOS")
        assert s.codec == "eac3"
        assert s.extension == ".m4a"
        assert s.bitrate_kbps == ATMOS_BITRATE_KBPS
        assert "Atmos" in s.spec_label


class TestForQuality:
    """播放器 resolve 路径:已知规格字段直接构建,不解析 manifest。"""

    def test_flac(self):
        s = StreamSpec.for_quality("LOSSLESS", "STEREO", "flac", "audio/flac")
        assert s.extension == ".flac"
        assert s.bit_depth == 16
        assert s.bitrate_kbps is None

    def test_aac(self):
        s = StreamSpec.for_quality("HIGH", "STEREO", "mp4a.40.2", "audio/mp4")
        assert s.bitrate_kbps == 320
        assert s.bitrate_label == "320 kbps"
        assert s.spec_label == "AAC-LC 320 kbps"

    def test_atmos_eac3(self):
        s = StreamSpec.for_quality("LOW", "DOLBY_ATMOS", "eac3", "audio/mp4")
        assert s.bitrate_kbps == ATMOS_BITRATE_KBPS
        assert s.bitrate_label == "768 kbps"
        assert "Atmos" in s.spec_label

    def test_hires_flac(self):
        s = StreamSpec.for_quality("HI_RES_LOSSLESS", "STEREO", "flac", "audio/flac")
        assert s.quality == "HI_RES_LOSSLESS"
        assert s.spec_label == "FLAC 16bit 44.1kHz"


class TestFromStream:
    def _stream(self, quality, audio_mode="STEREO", codecs="flac", mime="audio/flac"):
        manifest = base64.b64encode(
            f'{{"mimeType":"{mime}","codecs":"{codecs}","encryptionType":"NONE","urls":["https://x/0"]}}'.encode()
        ).decode()
        return SimpleNamespace(
            audioQuality=quality,
            audioMode=audio_mode,
            manifestMimeType="application/vnd.tidal.bts",
            manifest=manifest,
            bitDepth=24 if quality == "HI_RES_LOSSLESS" else 16,
            sampleRate=192000 if quality == "HI_RES_LOSSLESS" else 44100,
        )

    def test_flac_from_stream(self):
        s = StreamSpec.from_stream(self._stream("LOSSLESS"), ".flac")
        assert s.codec == "flac"
        assert s.bit_depth == 16
        assert s.sample_rate == 44100
        assert s.bitrate_kbps is None

    def test_atmos_eac3_from_stream(self):
        s = StreamSpec.from_stream(
            self._stream("LOW", "DOLBY_ATMOS", "eac3", "audio/mp4"), ".m4a"
        )
        assert s.codec == "eac3"
        assert s.bitrate_kbps == 768

    def test_hires_from_stream_keeps_spec(self):
        s = StreamSpec.from_stream(self._stream("HI_RES_LOSSLESS"), ".flac")
        assert s.bit_depth == 24
        assert s.sample_rate == 192000
        assert "24bit" in s.spec_label
        assert "192.0kHz" in s.spec_label


class TestTemplateFields:
    """模板新字段与旧字段兼容性。"""

    def _track(self):
        return SimpleNamespace(
            id=1, title="T", version="", copyright="", bpm=120, isrc="X",
            trackNumber=1, volumeNumber=1, artists=[], artist=None, explicit=False,
            mediaMetadata=SimpleNamespace(tags=[]),
        )

    def _album(self):
        return SimpleNamespace(
            id=9, title="A", artist=None, artists=[], releaseDate=None,
            type="ALBUM", mediaMetadata=SimpleNamespace(tags=[]),
        )

    def test_spec_fields_render(self):
        track, album = self._track(), self._album()
        spec = StreamSpec.predict("max")
        out = format_template(
            "{album.title}/{item.spec}/{item.quality_actual}/{item.bit_depth}/{item.sample_rate}",
            item=track, album=album, quality="MAX", spec=spec, with_asterisk_ext=False,
        )
        assert out == "A/FLAC 16bit 44.1kHz/HI_RES_LOSSLESS/16/44100"

    def test_bitrate_field_lossless_is_empty(self):
        track, album = self._track(), self._album()
        spec = StreamSpec.predict("max")
        # 无损无码率 → bitrate_label 为空
        assert spec.bitrate_label == ""
        assert spec.as_template_fields()["bitrate"] == ""
        # 模板中 bitrate 字段渲染为空,不产生额外文本
        out = format_template("{item.spec}/{item.bitrate}", item=track, album=album, spec=spec, with_asterisk_ext=False)
        assert "FLAC" in out
        assert "kbps" not in out

    def test_old_fields_still_work(self):
        track, album = self._track(), self._album()
        out = format_template("{album.title}/{item.title}", item=track, album=album, with_asterisk_ext=False)
        assert out == "A/T"

    def test_validate_accepts_spec_fields(self):
        errs = validate_template("{item.spec}/{item.bit_depth}/{item.sample_rate}/{item.bitrate}/{item.codec}/{item.quality_actual}")
        assert errs == []
