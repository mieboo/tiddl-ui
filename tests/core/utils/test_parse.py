import base64
import pytest
from pydantic import BaseModel

from tiddl.core.api.models import TrackStream
from tiddl.core.utils.parse import parse_track_stream, parse_manifest_XML


class FakeAudioQuality(str):
    pass


def _track_stream(mime: str, manifest: str, audio_mode: str = "STEREO") -> TrackStream:
    # TrackStream 字段按需构造,缺省用空值
    return TrackStream(
        manifest=base64.b64encode(manifest.encode()).decode(),
        manifestMimeType=mime,
        audioQuality="LOSSLESS",
        trackId="123",
        assetPresentation="FULL",
        audioMode=audio_mode,
        manifestHash="h",
    )


def test_parse_track_stream_unknown_mime_rejected_by_model():
    """P0-9: manifestMimeType 是 Literal 类型,未知 MIME 在模型层即被拒绝。"""
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        _track_stream("application/unknown+xml", "{}")


def test_parse_manifest_xml_segments():
    """P0-9: 解析 XML timeline 生成段 URL;维持现有 0 起始行为(未验证 Tidal 真实段号前不改)。"""
    xml = """<?xml version="1.0"?>
    <MPD xmlns="urn:mpeg:dash:schema:mpd:2011">
      <Period>
        <AdaptationSet>
          <Representation codecs="flac">
            <SegmentTemplate media="seg_$Number$.flac">
              <SegmentTimeline>
                <S t="0" d="4000" r="3"/>
              </SegmentTimeline>
            </SegmentTemplate>
          </Representation>
        </AdaptationSet>
      </Period>
    </MPD>"""
    urls, codecs = parse_manifest_XML(xml)
    # r=3 → 共 4 段;维持 range(0, total+1) 现行为(0..4 共5个,首个为 seg_0)
    assert len(urls) == 5
    assert urls[0] == "seg_0.flac"
    assert urls[-1] == "seg_4.flac"
    assert codecs == "flac"


def test_parse_track_stream_flac_codec_always_flac_extension():
    """扩展名由 codec 决定:v1 请求 HI_RES_LOSSLESS 实际返回 LOSSLESS(44.1/16 FLAC),
    不存在 flac+HI_RES_LOSSLESS → .m4a 的组合(实测确认);flac 一律 .flac。"""
    import base64 as b64

    manifest = '{"mimeType":"audio/flac","codecs":"flac","encryptionType":"NONE","urls":["https://x/0.flac"]}'
    stream = _track_stream("application/vnd.tidal.bts", manifest)
    stream.audioQuality = "HI_RES_LOSSLESS"  # 即使标记 Hi-Res,flac 内容仍是 .flac
    urls, ext = parse_track_stream(stream)
    assert ext == ".flac"
    assert urls == ["https://x/0.flac"]


def test_parse_track_stream_mp4_codec_m4a_extension():
    import base64 as b64

    manifest = '{"mimeType":"audio/mp4","codecs":"mp4a.40.2","encryptionType":"NONE","urls":["https://x/0.m4a"]}'
    stream = _track_stream("application/vnd.tidal.bts", manifest)
    _, ext = parse_track_stream(stream)
    assert ext == ".m4a"


def test_parse_track_stream_eac3_m4a_extension():
    """Atmos-only 曲目 v1 返回 eac3,解析为 .m4a(实测: Joni Mitchell - River 426175179)。"""
    manifest = '{"mimeType":"audio/mp4","codecs":"eac3","encryptionType":"NONE","urls":["https://x/0.mp4"]}'
    stream = _track_stream("application/vnd.tidal.bts", manifest)
    _, ext = parse_track_stream(stream)
    assert ext == ".m4a"
