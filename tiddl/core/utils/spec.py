"""统一流规格对象(StreamSpec)与码率推导。

把散落在下载器/播放器/模板里的「音质显示逻辑」收敛到这里:
- 有损档位(AAC)码率是固定值 → 查表
- 无损(FLAC)是可变码率 → 显示规格(位深/采样率)而非假码率
- Atmos(E-AC-3)是固定 768kbps 6ch

所有消费点(文件名模板、下载显示、播放器信息面板、音质菜单)
用同一份 StreamSpec,保证显示与真实流一一对应。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from tiddl.core.api.models import TrackStream

# 有损档固定码率(kbps):v1 实际返回,HE-AAC / AAC-LC
LOSSLESS_BITRATES: dict[str, int] = {
    "LOW": 96,
    "HIGH": 320,
}
# Atmos 承载 E-AC-3:固定 768 kbps / 6ch
ATMOS_BITRATE_KBPS = 768

# codec 内部名 → 显示名
CODEC_LABELS: dict[str, str] = {
    "mp4a.40.5": "HE-AAC",
    "mp4a.40.2": "AAC-LC",
    "flac": "FLAC",
    "eac3": "E-AC-3",
    "ac4": "AC-4",
}

# 有损档位 → codec 内部名(v1 实际)
LOSSLESS_CODECS: dict[str, str] = {
    "LOW": "mp4a.40.5",
    "HIGH": "mp4a.40.2",
}

# CLI 档位(小写字面量,或 .upper() 后) → v1 档位枚举
# low/normal/high/max ↔ LOW/HIGH/LOSSLESS/HI_RES_LOSSLESS
_CLI_TO_V1: dict[str, str] = {
    "LOW": "LOW",
    "NORMAL": "HIGH",
    "HIGH": "LOSSLESS",
    "MAX": "HI_RES_LOSSLESS",
}


def normalize_cli_quality(quality: str) -> str:
    """CLI 档位字面量(low/normal/high/max,大小写均可) → v1 档位枚举。

    仅用于文件名模板等「下载前预测」场景(predict 的输入)。
    注意:CLI 的 "HIGH" 表示无损(LOSSLESS),与 v1 枚举的 "HIGH"(320kbps) 语义不同,
    调用方必须按自己手上的语义选择 normalize_cli_quality 或 v1 枚举直通。
    """
    q = (quality or "").upper()
    return _CLI_TO_V1.get(q, q)


@dataclass(slots=True)
class StreamSpec:
    """一首曲目的实际/预测流规格,消费点显示与模板的一一对应来源。

    quality: v1 档位枚举(LOW/HIGH/LOSSLESS/HI_RES_LOSSLESS)
    codec:   manifest 内 codecs 字符串(flac / mp4a.40.2 / eac3 ...)
    bit_depth / sample_rate: 无损才有;有损(AAC)为 None
    bitrate_kbps: 有损查表固定值;无损为 None(不显示假码率)
    audio_mode: STEREO / DOLBY_ATMOS
    extension: .flac / .m4a
    """

    quality: str = "HIGH"
    codec: str = "mp4a.40.2"
    bit_depth: int | None = None
    sample_rate: int | None = None
    bitrate_kbps: int | None = None
    audio_mode: str = "STEREO"
    extension: str = ".m4a"
    extras: dict = field(default_factory=dict)

    # ---- 构建 ------------------------------------------------------------

    @classmethod
    def from_stream(cls, stream: TrackStream, extension: str) -> "StreamSpec":
        """从 v1 真实流响应构建(下载器拿到流后使用)。"""
        quality = stream.audioQuality
        codec = cls._codec_from_stream(stream, extension)
        bit_depth = getattr(stream, "bitDepth", None)
        sample_rate = getattr(stream, "sampleRate", None)
        audio_mode = getattr(stream, "audioMode", "STEREO")
        return cls(
            quality=quality,
            codec=codec,
            bit_depth=bit_depth,
            sample_rate=sample_rate,
            bitrate_kbps=cls._bitrate(quality, codec, audio_mode),
            audio_mode=audio_mode,
            extension=extension,
        )

    @classmethod
    def for_quality(
        cls,
        quality: str,
        audio_mode: str = "STEREO",
        codec: str = "",
        mime_type: str = "",
    ) -> "StreamSpec":
        """按已知档位/模式/编码直接构建(无需真实 stream 对象)。

        供播放器 resolve 等已有规格字段、不想再解析 manifest 的场景使用;
        quality 是 v1 档位枚举(与 from_stream 的 stream.audioQuality 同源,不做 CLI 映射);
        bitrate 按有损查表/Atmos 固定值推导,无损(FLAC)为 None。
        """
        q = (quality or "HIGH").upper()
        ext = ".flac" if mime_type == "audio/flac" or codec == "flac" else ".m4a"
        bit_depth = None
        sample_rate = None
        if codec == "flac" or (not codec and q in ("LOSSLESS", "HI_RES_LOSSLESS")):
            codec = "flac"
            bit_depth = 16
            sample_rate = 44100
        elif not codec:
            codec = "eac3" if audio_mode == "DOLBY_ATMOS" else "mp4a.40.2"
        return cls(
            quality=q,
            codec=codec,
            bit_depth=bit_depth,
            sample_rate=sample_rate,
            bitrate_kbps=cls._bitrate(q, codec, audio_mode),
            audio_mode=audio_mode,
            extension=ext,
        )

    @classmethod
    def predict(cls, quality: str, audio_mode: str = "STEREO") -> "StreamSpec":
        """下载前预测(文件名模板用):预测规则 = v1 实际行为,保证一一对应。

        quality 是 CLI 档位字面量(low/normal/high/max,大小写均可)。
        注意 CLI "high"=无损、"normal"=320kbps,与 v1 枚举语义不同(predict 内部做 CLI→v1 映射)。

        - CLI high/max → FLAC(44.1kHz/16bit;v1 实测 max 也只给 44.1/16)
        - CLI low/normal → AAC(96/320kbps)
        - Atmos(audio_mode=DOLBY_ATMOS)→ E-AC-3(768kbps, .m4a),v1 对 Atmos-only 曲目只给 eac3
        """
        q = normalize_cli_quality(quality)
        if audio_mode == "DOLBY_ATMOS":
            # Atmos-only:v1 无论请求什么档位都只给 E-AC-3
            return cls(
                quality="LOW",
                codec="eac3",
                bit_depth=None,
                sample_rate=None,
                bitrate_kbps=ATMOS_BITRATE_KBPS,
                audio_mode=audio_mode,
                extension=".m4a",
            )
        if q in ("LOSSLESS", "HI_RES_LOSSLESS"):
            return cls(
                quality=q,
                codec="flac",
                bit_depth=16,
                sample_rate=44100,
                bitrate_kbps=None,
                audio_mode=audio_mode,
                extension=".flac",
            )
        if q == "LOW":
            return cls(
                quality=q,
                codec="mp4a.40.5",
                bit_depth=None,
                sample_rate=None,
                bitrate_kbps=96,
                audio_mode=audio_mode,
                extension=".m4a",
            )
        return cls(
            quality=q,
            codec="mp4a.40.2",
            bit_depth=None,
            sample_rate=None,
            bitrate_kbps=320,
            audio_mode=audio_mode,
            extension=".m4a",
        )

    # ---- 码率推导 ---------------------------------------------------------

    @staticmethod
    def _bitrate(quality: str, codec: str, audio_mode: str) -> int | None:
        if codec in ("eac3", "ac4") or audio_mode == "DOLBY_ATMOS":
            return ATMOS_BITRATE_KBPS
        return LOSSLESS_BITRATES.get(quality)

    @staticmethod
    def _codec_from_stream(stream: TrackStream, extension: str) -> str:
        # 与 parse_track_stream 同源:codec 在 manifest JSON 的 codecs 字段
        try:
            import base64
            import json as json_mod

            payload = base64.b64decode(stream.manifest).decode("utf-8", "replace")
            if stream.manifestMimeType == "application/vnd.tidal.bts":
                codec = json_mod.loads(payload).get("codecs", "")
            else:
                # dash+xml:从第一个 Representation 的 codecs 属性取
                from xml.etree.ElementTree import fromstring

                root = fromstring(payload)
                rep = root.find("{urn:mpeg:dash:schema:mpd:2011}Period/{urn:mpeg:dash:schema:mpd:2011}AdaptationSet/{urn:mpeg:dash:schema:mpd:2011}Representation")
                codec = rep.get("codecs", "") if rep is not None else ""
            if codec:
                return codec
        except Exception:
            pass
        return "flac" if extension == ".flac" else "mp4a.40.2"

    # ---- 显示 -------------------------------------------------------------

    @property
    def codec_label(self) -> str:
        return CODEC_LABELS.get(self.codec, self.codec.upper())

    @property
    def bitrate_label(self) -> str:
        """码率显示:有损查表值;无损无码率(返回空,由 spec_label 走规格)。"""
        if self.bitrate_kbps is not None:
            return f"{self.bitrate_kbps} kbps"
        return ""

    @property
    def spec_label(self) -> str:
        """规格显示(一一对应真实流):`FLAC 44.1kHz/16bit` / `AAC-LC 320 kbps`。

        无损 → 规格;有损 → 码率;Atmos 是 codec 属性(eac3/ac4)而非 audio_mode 字段。
        """
        parts = [self.codec_label]
        if self.bit_depth is not None:
            parts.append(f"{self.bit_depth}bit")
        if self.sample_rate is not None:
            parts.append(f"{self.sample_rate / 1000:.1f}kHz")
        if self.bitrate_kbps is not None:
            parts.append(f"{self.bitrate_kbps} kbps")
        if self.codec in ("eac3", "ac4"):
            parts.append("Atmos")
        return " ".join(parts)

    @property
    def quality_label(self) -> str:
        """档位显示名(兼容旧 {item.quality} 语义的替代)。"""
        return self.quality

    def as_template_fields(self) -> dict[str, str | int | None]:
        """模板可用的裸字段(供 extra 注入,避免改 ItemTemplate dataclass)。"""
        return {
            "bit_depth": self.bit_depth,
            "sample_rate": self.sample_rate,
            "bitrate": self.bitrate_label,
            "codec": self.codec_label,
            "spec": self.spec_label,
            "quality": self.quality,
        }
