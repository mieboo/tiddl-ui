import asyncio
import json
import os
import shutil
import time
from logging import getLogger
from pathlib import Path
from tempfile import NamedTemporaryFile

import aiofiles
import aiohttp

from tiddl.cli.config import VIDEOS_FILTER_LITERAL, ATMOS_FILTER_LITERAL
from tiddl.cli.utils.download import get_existing_track_filename
from tiddl.cli.utils.path import resolve_existing_path_case
from tiddl.core.api import ApiError, TidalAPI
from tiddl.core.api.models import StreamVideoQuality, Track, TrackQuality, Video
from tiddl.core.utils import parse_track_stream, parse_video_stream
from tiddl.core.utils.const import (
    TRACK_QUALITY_LITERAL,
    VIDEO_QUALITY_LITERAL,
    track_qualities,
    video_qualities,
)
from tiddl.core.utils.ffmpeg import convert_to_mp4, extract_flac
from tiddl.core.utils.spec import StreamSpec

from .output import RichOutput

log = getLogger(__name__)

CHUNK_SIZE = 1024**2
# 进度采样间隔(秒):至少间隔这么久才计算一次下载速度
SPEED_SAMPLE_INTERVAL_S = 0.25
# 分段下载的进度上限:单段未完成时显示 99%,避免误报 100%
MULTI_SEGMENT_PROGRESS_CAP = 0.99


def emit_web_event(event: str, **data) -> None:
    if os.environ.get("TIDDL_WEB_EVENTS") == "1":
        print(
            "TIDDL_EVENT " + json.dumps({"event": event, **data}, ensure_ascii=False),
            flush=True,
        )

track_qualities_color: dict[TrackQuality, str] = {
    "LOW": "[gray]96 kbps",
    "HIGH": "[gray]320 kbps",
    "LOSSLESS": "[cyan]",
    "HI_RES_LOSSLESS": "[yellow]",
}

video_qualities_color: dict[StreamVideoQuality, str] = {
    "LOW": "[gray]360p",
    "MEDIUM": "[cyan]720p",
    "HIGH": "[yellow]1080p",
}


class Downloader:
    api: TidalAPI
    rich_output: RichOutput
    semaphore: asyncio.Semaphore
    track_quality: TrackQuality
    video_quality: StreamVideoQuality
    videos_filter: VIDEOS_FILTER_LITERAL
    skip_existing: bool
    download_path: Path
    scan_path: Path
    match_existing_path_case: bool
    dolby_atmos_filter: ATMOS_FILTER_LITERAL

    def __init__(
        self,
        tidal_api: TidalAPI,
        threads_count: int,
        rich_output: RichOutput,
        track_quality: TRACK_QUALITY_LITERAL,
        video_quality: VIDEO_QUALITY_LITERAL,
        videos_filter: VIDEOS_FILTER_LITERAL,
        skip_existing: bool,
        download_path: Path,
        scan_path: Path,
        match_existing_path_case: bool = False,
        dolby_atmos_filter: ATMOS_FILTER_LITERAL = "none",
    ) -> None:
        self.api = tidal_api
        self.rich_output = rich_output
        self.semaphore = asyncio.Semaphore(threads_count)
        self.track_quality = track_qualities[track_quality]
        self.video_quality = video_qualities[video_quality]
        self.videos_filter = videos_filter
        self.skip_existing = skip_existing
        self.download_path = download_path
        self.scan_path = scan_path
        self.match_existing_path_case = match_existing_path_case
        self.dolby_atmos_filter = dolby_atmos_filter

    async def close(self) -> None:
        """关闭底层 API 会话,释放缓存/连接。

        ``__init__.py`` 的 ``run`` 在全部任务结束后调用 ``await downloader.close()``,
        但该方法在历次重构中缺失,导致下载全部成功后在收尾阶段抛
        ``AttributeError: 'Downloader' object has no attribute 'close'``,
        任务被误标为失败。此处补上(会话是 CachedSession,close 会落盘缓存)。
        """
        try:
            session = getattr(self.api, "session", None)
            if session is not None:
                session.close()
        except Exception as exc:
            log.warning("Failed to close downloader API session: %s", exc)

    def get_path(self, base_path: Path, relative_path: Path) -> Path:
        if self.match_existing_path_case:
            return resolve_existing_path_case(base_path, relative_path)

        return base_path / relative_path

    async def download(
        self, item: Track | Video, file_path: Path
    ) -> tuple[Path | None, bool]:
        """
        returns
        - Path `item_path` path of existing/downloaded item
        - bool `was_downloaded`
        """

        if not item.allowStreaming:
            self.rich_output.console.print(
                f"[red]Can't stream[/] {item.title} ({item.id})"
            )
            return None, False

        if isinstance(item, Track):
            filename = get_existing_track_filename(
                item.audioQuality, self.track_quality, file_path
            )
            existing_file_path = self.get_path(self.scan_path, filename)
            vibrant_color = item.album.vibrantColor

        elif isinstance(item, Video):
            filename = file_path.with_suffix(".mp4")
            existing_file_path = self.get_path(self.scan_path, filename)
            vibrant_color = item.vibrantColor

        vibrant_color = vibrant_color or "gray"

        log.debug(f"{file_path=}, {filename=}, {existing_file_path=}")

        result_message = "[green]Downloaded"

        if existing_file_path.exists():
            result_message = "[cyan]Overwritten"

            if self.skip_existing:
                self.rich_output.show_item_result(
                    result_message="[yellow]Exists",
                    item_description=f"[{vibrant_color}]{item.title}",
                    item_path=existing_file_path,
                )
                emit_web_event("download_complete", item_id=str(item.id), title=item.title, path=str(existing_file_path))
                return existing_file_path, False

        elif (isinstance(item, Video) and self.videos_filter == "none") or (
            isinstance(item, Track) and self.videos_filter == "only"
        ):
            log.debug(f"skipping {item.id} due to {self.videos_filter=}")
            self.rich_output.console.print(
                f"Skipping '{item.title}' due to video filter set to '{self.videos_filter}'"
            )
            return None, False

        should_extract_flac = False

        async with self.semaphore:
            if isinstance(item, Track):
                try:
                    stream = self.api.get_track_stream(
                        track_id=item.id, quality=self.track_quality
                    )

                    log.debug(
                        f"{stream.trackId=}, {stream.audioQuality=}, {stream.audioMode=}"
                    )

                    # Atmos 过滤:filter=none 跳过 Atmos 曲目,**仅当该曲目有 STEREO 替代版本**;
                    # Atmos-only 曲目(元数据 audioModes 无 STEREO)没有立体声可下,应照常下载。
                    # (River 等 Atmos-only 曲目 v1 只给 E-AC-3,若因 filter=none 跳过 → 永远下不了)
                    track_modes = list(getattr(item, "audioModes", []) or [])
                    atmos_only = track_modes and "STEREO" not in track_modes
                    if (
                        self.dolby_atmos_filter == "none"
                        and stream.audioMode == "DOLBY_ATMOS"
                        and not atmos_only
                    ) or (
                        self.dolby_atmos_filter == "only"
                        and stream.audioMode == "STEREO"
                    ):
                        self.rich_output.console.print(
                            f"[blue]Skipping[/] [gray]{item.title}[/] [blue]due to Dolby Atmos filter[/] {self.dolby_atmos_filter}"
                        )
                        return None, False

                except ApiError as e:
                    log.error(f"{item.id=} {e=}")
                    self.rich_output.console.print(
                        f"[red]Error [{vibrant_color}]{item.title}[/] - {e.user_message}"
                    )
                    return None, False

                urls, extension = parse_track_stream(stream)
                download_path = self.get_path(self.download_path, filename)

                # P0-4:预测扩展名必须与实际落盘一致——用实际 audioMode 重新预测 skip 路径,
                # 否则 Atmos 流预测 .flac 实际 .m4a,导致 skip-existing 永远命中失败、反复重下。
                actual_filename = get_existing_track_filename(
                    item.audioQuality, self.track_quality, file_path, audio_mode=stream.audioMode
                )
                actual_existing = self.get_path(self.scan_path, actual_filename)
                if (
                    self.skip_existing
                    and actual_existing.exists()
                    and actual_existing != existing_file_path
                ):
                    self.rich_output.show_item_result(
                        result_message="[yellow]Exists",
                        item_description=f"[{vibrant_color}]{item.title}",
                        item_path=actual_existing,
                    )
                    emit_web_event("download_complete", item_id=str(item.id), title=item.title, path=str(actual_existing))
                    return actual_existing, False

                # 统一规格显示:码率/位深/采样率/编码与真实流一一对应(StreamSpec)
                spec = StreamSpec.from_stream(stream, extension)
                should_extract_flac = spec.extension == ".flac"
                if should_extract_flac:
                    quality_string = f"{track_qualities_color[stream.audioQuality]} {spec.spec_label}"
                else:
                    download_path = download_path.with_suffix(".m4a")
                    if stream.audioMode == "DOLBY_ATMOS":
                        quality_string = f"[blue]{spec.spec_label}[/]"
                    else:
                        quality_string = f"{track_qualities_color[stream.audioQuality]} {spec.spec_label}"

            elif isinstance(item, Video):
                stream = self.api.get_video_stream(
                    video_id=item.id, quality=self.video_quality
                )

                urls, ext = parse_video_stream(stream), ".ts"
                download_path = self.get_path(self.download_path, filename).with_suffix(
                    ext
                )
                quality_string = video_qualities_color[stream.videoQuality]

            task_id = self.rich_output.download_start(
                f"[{vibrant_color}]{item.title} {quality_string}"
            )
            emit_web_event(
                "download_start",
                item_id=str(item.id),
                title=item.title,
                segment_count=len(urls),
            )

            download_path.parent.mkdir(exist_ok=True, parents=True)

            # TODO shouldnt session be reused instead of
            # creating new one on every download?

            try:
                with NamedTemporaryFile(
                    "wb", delete=False, dir=download_path.parent
                ) as tmp:
                    async with aiohttp.ClientSession(trust_env=True) as session:
                        async with aiofiles.open(tmp.name, "wb") as f:
                            downloaded = 0
                            last_bytes = 0
                            last_update = time.monotonic()
                            for segment_index, url in enumerate(urls):
                                async with session.get(url) as resp:
                                    resp.raise_for_status()
                                    content_length = resp.content_length
                                    exact_total = content_length if len(urls) == 1 else None
                                    async for chunk in resp.content.iter_chunked(
                                        CHUNK_SIZE
                                    ):
                                        await f.write(chunk)
                                        downloaded += len(chunk)
                                        self.rich_output.download_advance(
                                            task_id, size=len(chunk)
                                        )
                                        now = time.monotonic()
                                        elapsed = now - last_update
                                        if elapsed >= SPEED_SAMPLE_INTERVAL_S:
                                            speed = (downloaded - last_bytes) / elapsed
                                            if exact_total:
                                                progress = min(downloaded / exact_total, 1.0)
                                            else:
                                                segment_progress = (
                                                    resp.content.total_bytes / content_length
                                                    if content_length
                                                    else 0
                                                )
                                                progress = min(
                                                    (segment_index + segment_progress) / len(urls),
                                                    MULTI_SEGMENT_PROGRESS_CAP,
                                                )
                                            emit_web_event(
                                                "download_progress",
                                                item_id=str(item.id),
                                                title=item.title,
                                                downloaded=downloaded,
                                                total=exact_total,
                                                speed=speed,
                                                progress=progress,
                                                segment=segment_index + 1,
                                                segment_count=len(urls),
                                            )
                                            last_bytes = downloaded
                                            last_update = now
    
                            emit_web_event(
                                "download_progress",
                                item_id=str(item.id),
                                title=item.title,
                                downloaded=downloaded,
                                total=downloaded,
                                speed=0,
                                progress=1.0,
                                segment=len(urls),
                                segment_count=len(urls),
                            )
    
                shutil.move(tmp.name, download_path)
    
                try:
                    download_path.chmod(0o644)
                except OSError:
                    pass
    
                try:
                    if isinstance(item, Track) and should_extract_flac:
                        download_path = extract_flac(download_path)
                    elif isinstance(item, Video):
                        download_path = convert_to_mp4(download_path)
                except Exception as exc:
                    # 转码失败不能伪装成功:删除坏文件并如实返回失败
                    log.error(f"Transcode failed for {item.title}: {exc}")
                    try:
                        if download_path and download_path.exists():
                            download_path.unlink()
                    except OSError:
                        pass
                    self.rich_output.download_finish(task_id=task_id)
                    return None, False

                task = self.rich_output.download_finish(
                    task_id=task_id,
                )

                self.rich_output.show_item_result(
                    result_message=result_message,
                    item_description=task.description,
                    item_path=download_path,
                )

                emit_web_event("download_complete", item_id=str(item.id), title=item.title, path=str(download_path))
                return download_path, True
            finally:
                # 下载/转码异常时清理残留临时文件(delete=False 不会自动删)
                try:
                    if Path(tmp.name).exists():
                        Path(tmp.name).unlink()
                except OSError:
                    pass
