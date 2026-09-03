import re
from dataclasses import dataclass, field
from datetime import datetime

from tiddl.core.api.models import Track, Video, Album, Playlist
from tiddl.core.utils.sanitize import sanitize_string
from tiddl.core.utils.spec import StreamSpec


def _clean_segment(text: str) -> str:
    """
    Clean a single path segment using sanitize_string plus extra rules
    to keep it safe for Windows / NAS filesystems.

    - Uses sanitize_string for base cleanup.
    - Collapses multiple dots ("..", "...") into a single dot.
    - Removes trailing dots and spaces (Windows forbids them).
    - Collapses multiple spaces into one.
    - Ensures the segment is never empty (uses "_" as fallback).
    """

    text = sanitize_string(text)
    text = re.sub(r"\.{2,}", ".", text)
    text = text.rstrip(" .")
    text = re.sub(r"\s{2,}", " ", text)
    text = text.strip()

    return text or "_"


class Explicit:
    def __init__(self, value: bool | None):
        self.value = value

    def __format__(self, format_spec: str):
        if self.value is None:
            return ""

        features = format_spec.split("; ")

        def get_base():
            for feature in features:
                match feature:
                    case "long":
                        return "explicit" if self.value else ""
                    case "full":
                        return "explicit" if self.value else "clean"

            return "E" if self.value else ""

        base = get_base()

        for feature in features:
            match feature:
                case "upper":
                    return base.upper()

        return base


class UserFormat:
    def __init__(self, value: bool) -> None:
        self.value = value

    def __format__(self, format_spec: str) -> str:
        return format_spec if self.value is True else ""


@dataclass(slots=True)
class AlbumTemplate:
    id: int = 0
    title: str = ""
    artist: str = ""
    artists: str = ""
    date: datetime = datetime.min
    explicit: Explicit = field(default_factory=lambda: Explicit(None))
    master: UserFormat = field(default_factory=lambda: UserFormat(False))
    release: str = ""


@dataclass(slots=True)
class ItemTemplate:
    id: int
    title: str
    title_version: str
    number: int
    volume: int
    version: str
    copyright: str
    bpm: int
    isrc: str
    quality: str
    artist: str
    artists: str
    features: str
    artists_with_features: str
    explicit: Explicit
    dolby: UserFormat
    # 流规格字段(与 StreamSpec 一一对应;下载前为预测值,下载后为真实值)
    bit_depth: str = ""
    sample_rate: str = ""
    bitrate: str = ""
    codec: str = ""
    spec: str = ""
    quality_actual: str = ""


@dataclass(slots=True)
class PlaylistTemplate:
    uuid: str
    title: str
    index: int
    created: datetime
    updated: datetime


def generate_template_data(
    item: Track | Video | None = None,
    album: Album | None = None,
    playlist: Playlist | None = None,
    playlist_index: int = 0,
    quality: str = "",
    spec: "StreamSpec | None" = None,
) -> dict[str, ItemTemplate | AlbumTemplate | PlaylistTemplate | None]:
    """Normalize Tidal API Track/Video + Album data into safe templates.

    spec: 可选 StreamSpec(真实流规格或预测值),填充 item 的规格字段;
    缺省时规格字段为空字符串(不显示)。
    """

    item_template = None
    if item:
        main_artists = sorted(
            [a.name for a in (item.artists or []) if a.type == "MAIN"]
        )
        featured_artists = sorted(
            [a.name for a in (item.artists or []) if a.type == "FEATURED"]
        )

        if isinstance(item, Track):
            version = item.version or ""
            copyright_ = item.copyright or ""
            bpm = item.bpm or 0
            isrc = item.isrc or ""
            dolby = UserFormat("DOLBY_ATMOS" in item.mediaMetadata.tags)
        else:  # Video
            version = ""
            copyright_ = ""
            bpm = 0
            isrc = ""
            dolby = UserFormat(False)

        spec_fields = spec.as_template_fields() if spec is not None else {}

        item_template = ItemTemplate(
            id=item.id,
            title=item.title,
            title_version=f"{item.title} ({version})" if version else item.title,
            number=item.trackNumber,
            volume=item.volumeNumber,
            version=version,
            copyright=copyright_,
            bpm=bpm,
            isrc=isrc,
            quality=quality,
            artist=item.artist.name if item.artist else "",
            artists="; ".join(main_artists),
            features="; ".join(featured_artists),
            artists_with_features="; ".join(main_artists + featured_artists),
            explicit=Explicit(getattr(item, "explicit", None)),
            dolby=dolby,
            bit_depth=spec_fields.get("bit_depth", "") or "",
            sample_rate=spec_fields.get("sample_rate", "") or "",
            bitrate=spec_fields.get("bitrate", "") or "",
            codec=spec_fields.get("codec", "") or "",
            spec=spec_fields.get("spec", "") or "",
            quality_actual=spec_fields.get("quality", "") or "",
        )

    album_template = AlbumTemplate()
    if album:
        album_template = AlbumTemplate(
            id=album.id,
            title=album.title,
            artist=album.artist.name if album.artist else "",
            artists=", ".join(
                a.name for a in (album.artists or []) if a.type == "MAIN"
            ),
            date=album.releaseDate or datetime.min,
            explicit=Explicit(getattr(album, "explicit", None)),
            master=UserFormat(
                "HIRES_LOSSLESS" in album.mediaMetadata.tags and quality == "MAX"
            ),
            release=album.type,
        )

    playlist_template = None
    if playlist:
        playlist_template = PlaylistTemplate(
            uuid=playlist.uuid,
            title=playlist.title,
            index=playlist_index,
            created=datetime.fromisoformat(playlist.created),
            updated=datetime.fromisoformat(playlist.lastUpdated),
        )

    templates: dict[str, ItemTemplate | AlbumTemplate | PlaylistTemplate | None] = {
        "item": item_template,
        "album": album_template,
        "playlist": playlist_template,
    }

    return templates


def format_template(
    template: str,
    item: Track | Video | None = None,
    album: Album | None = None,
    playlist: Playlist | None = None,
    playlist_index: int = 0,
    quality: str = "",
    spec: StreamSpec | None = None,
    with_asterisk_ext: bool = True,
    **extra,
) -> str:
    """
    Raises `AttributeError` on invalid template.
    """

    custom_fields = {"now": datetime.now()}

    data = (
        generate_template_data(
            item=item,
            album=album,
            playlist=playlist,
            playlist_index=playlist_index,
            quality=quality,
            spec=spec,
        )
        | extra
        | custom_fields
    )

    segments: list[str] = []

    for raw_segment in template.split("/"):
        formatted = raw_segment.format(**data)
        cleaned = _clean_segment(formatted)
        segments.append(cleaned)

    path = "/".join(segments)

    if with_asterisk_ext:
        path += ".*"

    return path


# ---------------------------------------------------------------------------
# 模板字段白名单校验(阶段 3,默认关闭;供开发期 --validate-template 使用)
# 把"字段名错误运行时才 AttributeError"的隐性契约变成显式校验。
# ---------------------------------------------------------------------------

# 各模板对象允许的字段名(与 ItemTemplate/AlbumTemplate/PlaylistTemplate 对齐)
_TEMPLATE_FIELD_WHITELIST: dict[str, set[str]] = {
    "item": {
        "id", "title", "title_version", "number", "volume", "version",
        "copyright", "bpm", "isrc", "quality", "artist", "artists",
        "features", "artists_with_features", "explicit", "dolby",
        # 流规格字段(与 StreamSpec 一一对应)
        "bit_depth", "sample_rate", "bitrate", "codec", "spec", "quality_actual",
    },
    "album": {
        "id", "title", "artist", "artists", "date", "explicit", "master", "release",
    },
    "playlist": {
        "uuid", "title", "index", "created", "updated",
    },
}


def validate_template(template: str) -> list[str]:
    """校验模板中的字段引用是否在白名单内(含 `now` 自定义字段与 extra 注入)。

    返回不合法字段名列表;空列表表示通过。不会修改模板,不改变 format_template 行为。
    """
    errors: list[str] = []
    for raw_segment in template.split("/"):
        for match in re.finditer(r"\{([^{}]+)\}", raw_segment):
            field_expr = match.group(1).strip()
            if not field_expr:
                continue
            # 支持 {item.title} / {album.artist} 等对象字段路径,以及裸 {now}
            if "." in field_expr:
                obj, _, field_name = field_expr.partition(".")
                allowed = _TEMPLATE_FIELD_WHITELIST.get(obj)
                if allowed is None:
                    errors.append(field_expr)
                elif field_name not in allowed:
                    errors.append(field_expr)
            elif field_expr != "now":
                # 裸字段名(如 {quality})属于 extra 注入,无法静态校验,跳过
                pass
    return errors
