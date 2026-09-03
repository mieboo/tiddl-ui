import os
import typer
import asyncio

from pathlib import Path
from logging import getLogger
from dataclasses import dataclass, field
from rich.live import Live

from typing_extensions import Annotated

from tiddl.core.metadata import add_track_metadata, add_video_metadata, Cover

MAX_COVER_SIZE = 1080  # 封面下载最大边长
from tiddl.core.api import ApiError
from tiddl.core.api.models import Album, Track, Video, AlbumItemsCredits
from tiddl.core.utils.format import format_template
from tiddl.core.utils.m3u import save_tracks_to_m3u
from tiddl.core.utils.spec import StreamSpec
from tiddl.cli.config import (
    CONFIG,
    TRACK_QUALITY_LITERAL,
    VIDEO_QUALITY_LITERAL,
    ARTIST_SINGLES_FILTER_LITERAL,
    VALID_M3U_RESOURCE_LITERAL,
    VIDEOS_FILTER_LITERAL,
    ATMOS_FILTER_LITERAL,
)
from tiddl.cli.utils.resource import TidalResource
from tiddl.cli.ctx import Context
from tiddl.cli.commands.auth import refresh
from tiddl.cli.commands.subcommands import register_subcommands


from .downloader import Downloader, emit_web_event
from .output import RichOutput

download_command = typer.Typer(name="download")
register_subcommands(download_command)

log = getLogger(__name__)


@dataclass
class TrackMetadata:
    """Per-track metadata collected while downloading an album/playlist."""

    date: str = ""
    artist: str = ""
    credits: list[AlbumItemsCredits.ItemWithCredits.CreditsEntry] = field(default_factory=list)
    cover: Cover | None = None
    album_review: str = ""


def item_info(item) -> str:
    """Human-readable identifier for error messages (track/video/album)."""
    title = getattr(item, "title", "Unknown")
    info = f"{title} (ID: {item.id})"
    album = getattr(item, "album", None)
    if album:
        info += f", Album ID: {album.id}"
    return info


def report_error(console, exc: Exception, *, info: str = "", raise_errors: bool = False) -> None:
    """Print a consistent error line; re-raise when --raise-errors is set."""
    label = "API Error" if isinstance(exc, ApiError) else "Error"
    suffix = f" ({info})" if info else ""
    console.print(f"[red]{label}:[/] {exc}{suffix}")
    if raise_errors:
        raise exc


def paginate(fetch_page):
    """Yield items across pages of a Tidal collection API call.

    ``fetch_page(offset)`` must return an object exposing ``items``,
    ``limit`` and ``totalNumberOfItems``.
    """
    offset = 0
    while True:
        page = fetch_page(offset)
        yield from page.items
        offset += page.limit
        if offset >= page.totalNumberOfItems:
            break

class DownloadSession:
    """Orchestrates the CLI ``download`` pipeline for one invocation."""

    def __init__(
        self,
        ctx: Context,
        *,
        track_quality: TRACK_QUALITY_LITERAL,
        video_quality: VIDEO_QUALITY_LITERAL,
        skip_existing: bool,
        rewrite_metadata: bool,
        threads_count: int,
        download_path: Path,
        scan_path: Path,
        template: str,
        singles_filter: ARTIST_SINGLES_FILTER_LITERAL,
        videos_filter: VIDEOS_FILTER_LITERAL,
        raise_errors: bool,
        dolby_atmos_filter: ATMOS_FILTER_LITERAL,
    ) -> None:
        self.ctx = ctx
        self.track_quality = track_quality
        self.video_quality = video_quality
        self.skip_existing = skip_existing
        self.rewrite_metadata = rewrite_metadata
        self.threads_count = threads_count
        self.download_path = download_path
        self.scan_path = scan_path
        self.template = template
        self.singles_filter = singles_filter
        self.videos_filter = videos_filter
        self.raise_errors = raise_errors
        self.dolby_atmos_filter = dolby_atmos_filter
        self.rich_output: RichOutput | None = None
        self.downloader: Downloader | None = None

    def write_lrc_file(self, track: Track, lyrics: str, file_path: Path) -> None:
        if not CONFIG.download.write_lrc_file or not lyrics.strip():
            return

        lrc_file_path = file_path.with_suffix(".lrc")

        try:
            with open(lrc_file_path, "w", encoding="utf-8") as f:
                f.write(lyrics)
        except Exception as e:
            log.error(
                f"Failed to write LRC file for track {track.title} (ID: {track.id}): {e}"
            )

    def save_m3u(
        self,
        resource_type: VALID_M3U_RESOURCE_LITERAL,
        filename: str,
        tracks_with_path: list[tuple[Path, Track]],
    ) -> None:
        if not CONFIG.m3u.save:
            return

        if resource_type not in CONFIG.m3u.allowed:
            return

        tracks_with_existing_paths = [
            (path, track)
            for (path, track) in tracks_with_path
            if path and isinstance(track, Track)
        ]

        log.debug(f"{resource_type=}, {filename=}, {len(tracks_with_existing_paths)=}")

        save_tracks_to_m3u(
            tracks_with_path=tracks_with_existing_paths,
            path=self.download_path / filename,
        )

    def get_item_quality(self, item: Track | Video) -> str:
        def predict_item_quality() -> TRACK_QUALITY_LITERAL | VIDEO_QUALITY_LITERAL:
            if isinstance(item, Track):
                if self.track_quality in ["low", "normal"]:
                    return self.track_quality

                if (
                    self.track_quality == "max"
                    and "HIRES_LOSSLESS" not in item.mediaMetadata.tags
                ):
                    return "high"

                return self.track_quality

            elif isinstance(item, Video):
                # TODO add missing Video.quality literals so this function can work properly
                return self.video_quality

            raise TypeError("Unsupported item type")

        return predict_item_quality().upper()

    def run(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        rich_output = RichOutput(self.ctx.obj.console)

        downloader = Downloader(
            tidal_api=self.ctx.obj.api,
            threads_count=self.threads_count,
            rich_output=rich_output,
            track_quality=self.track_quality,
            video_quality=self.video_quality,
            videos_filter=self.videos_filter,
            skip_existing=not self.skip_existing,
            download_path=self.download_path,
            scan_path=self.scan_path,
            match_existing_path_case=CONFIG.download.match_existing_path_case,
            dolby_atmos_filter=self.dolby_atmos_filter,
        )
        self.rich_output = rich_output
        self.downloader = downloader

        with Live(
            rich_output.group,
            refresh_per_second=10,
            console=self.ctx.obj.console,
            transient=True,
        ):

            async def wrapper(r: TidalResource):
                try:
                    await self.handle_resource(r)
                except Exception as e:
                    report_error(self.ctx.obj.console, e, info=str(r), raise_errors=self.raise_errors)

            await asyncio.gather(*(wrapper(r) for r in self.ctx.obj.resources))
            await downloader.close()

        rich_output.show_stats()

    async def handle_item(
        self,
        item: Track | Video,
        file_path: str,
        track_metadata: TrackMetadata | None = None,
    ) -> tuple[Path | None, Track | Video]:
        log.debug(f"{item.id=}, {file_path=}")
        self.rich_output.total_increment()

        if not track_metadata:
            track_metadata = TrackMetadata()

        download_path, was_downloaded = await self.downloader.download(
            item=item, file_path=Path(file_path)
        )

        log.debug(f"{download_path=}, {was_downloaded=}")

        if (
            CONFIG.metadata.enable
            and download_path
            # rewrite metadata when track was skipped due to already existing
            and (self.rewrite_metadata or was_downloaded)
        ):
            if isinstance(item, Track):
                lyrics_subtitles = ""

                if CONFIG.metadata.lyrics or CONFIG.download.write_lrc_file:
                    try:
                        lyrics_subtitles = self.ctx.obj.api.get_track_lyrics(
                            item.id
                        ).subtitles
                    except Exception as e:
                        log.error(e)

                if (
                    not track_metadata.cover
                    and item.album.cover
                    and CONFIG.metadata.cover
                ):
                    track_metadata.cover = Cover(item.album.cover)

                if track_metadata.cover and track_metadata.cover.data is None:
                    track_metadata.cover.fetch_data()

                self.write_lrc_file(item, lyrics_subtitles, download_path)

                add_track_metadata(
                    path=download_path,
                    track=item,
                    lyrics=lyrics_subtitles,
                    album_artist=track_metadata.artist,
                    cover_data=(
                        track_metadata.cover.data
                        if track_metadata.cover
                        else None
                    ),
                    date=track_metadata.date,
                    credits_contributors=track_metadata.credits,
                    comment=track_metadata.album_review,
                )

            elif isinstance(item, Video):
                add_video_metadata(path=download_path, video=item)

        if download_path and CONFIG.download.update_mtime:
            try:
                os.utime(download_path, None)
            except Exception:
                log.warning(f"could not update mtime for {download_path}")

        return download_path, item

    async def handle_resource(self, resource: TidalResource):
        resource_total = 0
        resource_completed = 0

        async def tracked_item(*args, **kwargs):
            nonlocal resource_total, resource_completed
            resource_total += 1
            emit_web_event(
                "resource_progress",
                completed=resource_completed,
                total=resource_total,
            )
            try:
                return await self.handle_item(*args, **kwargs)
            finally:
                resource_completed += 1
                emit_web_event(
                    "resource_progress",
                    completed=resource_completed,
                    total=resource_total,
                )

        async def download_album(album: Album):
            futures = []

            cover: Cover | None = None
            save_cover = ("album" in CONFIG.cover.allowed) and CONFIG.cover.save

            if album.cover and (CONFIG.metadata.cover or save_cover):
                cover = Cover(album.cover, size=CONFIG.cover.size)

            album_review = ""

            if CONFIG.metadata.album_review:
                try:
                    album_review = self.ctx.obj.api.get_album_review(
                        album_id=resource.id
                    ).normalized_text()
                except Exception as e:
                    log.error(e)

            for album_item in paginate(
                lambda o: self.ctx.obj.api.get_album_items_credits(album_id=album.id, offset=o)
            ):
                try:
                    template = self.template or CONFIG.templates.album
                    file_path = format_template(
                        template=template,
                        item=album_item.item,
                        album=album,
                        quality=self.get_item_quality(album_item.item),
                        spec=StreamSpec.predict(self.get_item_quality(album_item.item)),
                    )

                except AttributeError as exc:
                    log.error(f"{exc=}")
                    self.ctx.obj.console.print(
                        f"[red]Wrong Album Template:[/] {exc} ({template=}, {album.id=}, {album_item.item.id=})"
                    )
                    continue

                try:
                    futures.append(
                        tracked_item(
                            item=album_item.item,
                            file_path=file_path,
                            track_metadata=TrackMetadata(
                                cover=cover,
                                date=str(album.releaseDate),
                                artist=(
                                    album.artist.name if album.artist else ""
                                ),
                                credits=album_item.credits,
                                album_review=album_review,
                            ),
                        )
                    )
                except Exception as e:
                    report_error(
                        self.ctx.obj.console, e, info=item_info(album_item.item), raise_errors=self.raise_errors
                    )

            tracks_with_path = await asyncio.gather(*futures)

            self.save_m3u(
                resource_type="album",
                filename=format_template(
                    CONFIG.m3u.templates.album,
                    album=album,
                    type="album",
                ),
                tracks_with_path=tracks_with_path,
            )

            if save_cover and cover:
                cover.save_to_directory(
                    path=self.download_path
                    / format_template(
                        template=CONFIG.cover.templates.album, album=album
                    )
                )

        # resources should be collected from a distinct function
        # that would yield the resources.
        # then we would be able to reuse the logic in the export command

        match resource.type:

            case "track":
                track = self.ctx.obj.api.get_track(resource.id)
                album = self.ctx.obj.api.get_album(track.album.id)

                cover: Cover | None = None
                save_cover = ("track" in CONFIG.cover.allowed) and CONFIG.cover.save

                if album.cover and (CONFIG.metadata.cover or save_cover):
                    cover = Cover(album.cover, size=CONFIG.cover.size)

                await tracked_item(
                    item=track,
                    file_path=format_template(
                        template=self.template or CONFIG.templates.track,
                        item=track,
                        album=album,
                        quality=self.get_item_quality(track),
                        spec=StreamSpec.predict(self.get_item_quality(track)),
                    ),
                    track_metadata=TrackMetadata(
                        cover=cover,
                        date=str(album.releaseDate),
                        artist=album.artist.name if album.artist else "",
                        # credits are missing
                    ),
                )

                if (
                    CONFIG.cover.save
                    and ("track" in CONFIG.cover.allowed)
                    and track.album.cover
                ):
                    Cover(
                        track.album.cover, size=CONFIG.cover.size
                    ).save_to_directory(
                        path=self.download_path
                        / format_template(
                            CONFIG.cover.templates.track, item=track, album=album
                        )
                    )

            case "video":
                video = self.ctx.obj.api.get_video(resource.id)
                template = self.template or CONFIG.templates.video

                if (
                    "{album" in template
                    and video.album
                    and video.album.id is not None
                ):
                    album = self.ctx.obj.api.get_album(video.album.id)
                else:
                    album = None

                await tracked_item(
                    item=video,
                    file_path=format_template(
                        template=template,
                        item=video,
                        album=album,
                        quality=self.get_item_quality(video),
                    ),
                )

            case "mix":
                futures = []

                for mix_item in paginate(
                    lambda o: self.ctx.obj.api.get_mix_items(resource.id, offset=o)
                ):
                    template = self.template or CONFIG.templates.mix

                    try:
                        if "{album" in template:
                            album = self.ctx.obj.api.get_album(
                                mix_item.item.album.id
                            )
                        else:
                            album = None

                        futures.append(
                            tracked_item(
                                item=mix_item.item,
                                file_path=format_template(
                                    template=template,
                                    item=mix_item.item,
                                    album=album,
                                    mix_id=resource.id,
                                    quality=self.get_item_quality(mix_item.item),
                                    spec=StreamSpec.predict(self.get_item_quality(mix_item.item)),
                                ),
                            )
                        )
                    except Exception as e:
                        report_error(
                            self.ctx.obj.console, e, info=item_info(mix_item.item), raise_errors=self.raise_errors
                        )

                tracks_with_path = await asyncio.gather(*futures)

                self.save_m3u(
                    resource_type="mix",
                    filename=format_template(
                        CONFIG.m3u.templates.mix,
                        mix_id=resource.id,
                        type="mix",
                    ),
                    tracks_with_path=tracks_with_path,
                )

            case "album":
                album = self.ctx.obj.api.get_album(album_id=resource.id)
                await download_album(album)

            case "artist":
                futures = []

                async def safe_download_album(album: Album):
                    try:
                        await download_album(album)
                    except Exception as e:
                        report_error(
                            self.ctx.obj.console, e, info=item_info(album), raise_errors=self.raise_errors
                        )

                def get_all_albums(singles: bool):
                    for album in paginate(
                        lambda o: self.ctx.obj.api.get_artist_albums(
                            artist_id=resource.id,
                            offset=o,
                            filter="EPSANDSINGLES" if singles else "ALBUMS",
                        )
                    ):
                        futures.append(safe_download_album(album))

                def get_all_videos():
                    for video in paginate(
                        lambda o: self.ctx.obj.api.get_artist_videos(
                            resource.id, offset=o
                        )
                    ):
                        template = self.template or CONFIG.templates.video

                        try:
                            if "{album" in template and video.album:
                                album = self.ctx.obj.api.get_album(video.album.id)
                            else:
                                album = None

                            futures.append(
                                tracked_item(
                                    item=video,
                                    file_path=format_template(
                                        template=template,
                                        item=video,
                                        album=album,
                                        quality=self.get_item_quality(video),
                                    ),
                                )
                            )
                        except Exception as e:
                            report_error(
                                self.ctx.obj.console, e, info=item_info(video), raise_errors=self.raise_errors
                            )

                if self.videos_filter != "none":
                    get_all_videos()

                if self.videos_filter != "only":
                    if self.singles_filter == "include":
                        get_all_albums(False)
                        get_all_albums(True)
                    else:
                        get_all_albums(self.singles_filter == "only")

                await asyncio.gather(*futures)

            case "playlist":
                futures = []
                playlist_index = 0
                playlist = self.ctx.obj.api.get_playlist(playlist_uuid=resource.id)

                for playlist_item in paginate(
                    lambda o: self.ctx.obj.api.get_playlist_items(
                        playlist_uuid=resource.id, offset=o
                    )
                ):
                    playlist_index += 1
                    template = self.template or CONFIG.templates.playlist

                    try:
                        if "{album" in template:
                            album = self.ctx.obj.api.get_album(
                                playlist_item.item.album.id
                            )
                        else:
                            album = None

                        futures.append(
                            tracked_item(
                                item=playlist_item.item,
                                file_path=format_template(
                                    template=template,
                                    item=playlist_item.item,
                                    album=album,
                                    playlist=playlist,
                                    playlist_index=playlist_index,
                                    quality=self.get_item_quality(
                                        playlist_item.item
                                    ),
                                    spec=StreamSpec.predict(
                                        self.get_item_quality(playlist_item.item)
                                    ),
                                ),
                                track_metadata=TrackMetadata(),
                            )
                        )
                    except Exception as e:
                        report_error(
                            self.ctx.obj.console, e, info=item_info(playlist_item.item), raise_errors=self.raise_errors
                        )

                tracks_with_path = await asyncio.gather(*futures)

                self.save_m3u(
                    resource_type="playlist",
                    filename=format_template(
                        CONFIG.m3u.templates.playlist,
                        playlist=playlist,
                        type="playlist",
                    ),
                    tracks_with_path=tracks_with_path,
                )

                if (
                    CONFIG.cover.save
                    and ("playlist" in CONFIG.cover.allowed)
                    and playlist.squareImage
                ):
                    Cover(
                        playlist.squareImage, size=min(CONFIG.cover.size, MAX_COVER_SIZE)
                    ).save_to_directory(
                        path=self.download_path
                        / format_template(
                            template=CONFIG.cover.templates.playlist,
                            playlist=playlist,
                        )
                    )


@download_command.callback(no_args_is_help=True)
def download_callback(
    ctx: Context,
    TRACK_QUALITY: Annotated[
        TRACK_QUALITY_LITERAL,
        typer.Option(
            "--track-quality",
            "-q",
        ),
    ] = CONFIG.download.track_quality,
    VIDEO_QUALITY: Annotated[
        VIDEO_QUALITY_LITERAL,
        typer.Option(
            "--video-quality",
            "-vq",
        ),
    ] = CONFIG.download.video_quality,
    SKIP_EXISTING: Annotated[
        bool,
        typer.Option(
            "--no-skip",
            "-ns",
            help="Don't skip downloading existing files.",
        ),
    ] = not CONFIG.download.skip_existing,
    REWRITE_METADATA: Annotated[
        bool,
        typer.Option(
            "--rewrite-metadata",
            "-r",
            help="Rewrite metadata for already downloaded tracks.",
        ),
    ] = CONFIG.download.rewrite_metadata,
    THREADS_COUNT: Annotated[
        int,
        typer.Option(
            "--threads-count",
            "-t",
            help="Number of concurrent download threads.",
            min=1,
        ),
    ] = CONFIG.download.threads_count,
    DOWNLOAD_PATH: Annotated[
        Path,
        typer.Option(
            "--path",
            "-p",
            help="Base directory path for all downloads.",
        ),
    ] = CONFIG.download.download_path,
    SCAN_PATH: Annotated[
        Path,
        typer.Option(
            "--scan-path",
            "--sp",
            help="Directory to search for your existing downloads.",
        ),
    ] = CONFIG.download.scan_path,
    TEMPLATE: Annotated[
        str,
        typer.Option(
            "--output",
            "-o",
            help="Format output file template.",
        ),
    ] = "",
    SINGLES_FILTER: Annotated[
        ARTIST_SINGLES_FILTER_LITERAL,
        typer.Option(
            "--singles",
            "-s",
            help="Filter for including artists' singles, used while downloading artist.",
        ),
    ] = CONFIG.download.singles_filter,
    VIDEOS_FILTER: Annotated[
        VIDEOS_FILTER_LITERAL,
        typer.Option(
            "--videos",
            "-vid",
            help="Videos handling: 'none' to exclude, 'allow' to include, 'only' to download videos only.",
        ),
    ] = CONFIG.download.videos_filter,
    RAISE_ERRORS: Annotated[
        bool,
        typer.Option(
            "--raise-errors",
            "-err",
            help="Raise an error on resource download failure. Use for debugging",
        ),
    ] = False,
    DOLBY_ATMOS_FILTER: Annotated[
        ATMOS_FILTER_LITERAL,
        typer.Option(
            "--dolby-atmos",
            "-da",
            help="Dolby Atmos filter, 'none' to exclude, 'allow' to include, 'only' to download only Dolby Atmos, if available.",
        ),
    ] = CONFIG.download.atmos_filter,
):
    """
    Download Tidal resources.
    """

    ctx.invoke(refresh, EARLY_EXPIRE_TIME=600)

    log.debug(f"{ctx.params=}")

    session = DownloadSession(
        ctx=ctx,
        track_quality=TRACK_QUALITY,
        video_quality=VIDEO_QUALITY,
        skip_existing=SKIP_EXISTING,
        rewrite_metadata=REWRITE_METADATA,
        threads_count=THREADS_COUNT,
        download_path=DOWNLOAD_PATH,
        scan_path=SCAN_PATH,
        template=TEMPLATE,
        singles_filter=SINGLES_FILTER,
        videos_filter=VIDEOS_FILTER,
        raise_errors=RAISE_ERRORS,
        dolby_atmos_filter=DOLBY_ATMOS_FILTER,
    )
    ctx.call_on_close(session.run)

