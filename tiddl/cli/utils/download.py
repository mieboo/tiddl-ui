from logging import getLogger
from pathlib import Path
from tiddl.core.api.models import TrackQuality

log = getLogger(__name__)

# 无损(FLAC)质量档:预测与实现共用同一份定义,避免分叉(见 P0-4)
FLAC_QUALITIES: list[TrackQuality] = ["LOSSLESS", "HI_RES_LOSSLESS"]


def get_existing_track_filename(
    track_quality: TrackQuality,
    download_quality: TrackQuality,
    file_name: Path,
    audio_mode: str | None = None,
) -> Path:
    """
    Predict track extension.

    与 downloader 实际落盘保持一致:只有 LOSSLESS/HI_RES 且 STEREO 才落盘 .flac,
    Atmos 等非 STEREO 流落盘 .m4a(否则 skip-existing 预测 .flac 实际 .m4a,反复重下)。
    audio_mode 缺省时按旧逻辑(仅音质)预测,保持向后兼容。
    """

    if (
        download_quality in FLAC_QUALITIES
        and track_quality in FLAC_QUALITIES
        and (audio_mode is None or audio_mode == "STEREO")
    ):
        extension = ".flac"
    else:
        extension = ".m4a"

    full_file_name = file_name.with_suffix(extension)

    log.debug(
        f"{track_quality=}, {download_quality=}, {audio_mode=}, {file_name=}, {full_file_name=}"
    )

    return full_file_name
