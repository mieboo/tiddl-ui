"""URL 预览与搜索(从 web/app.py 抽取)。

build_preview 把用户输入的 Tidal 资源 URL 展开成前端卡片数据,
detect_download_options 根据资源内容推荐下载选项。
依赖 accounts(账号上下文)与 player(纯函数),不依赖 app 路由状态。
"""

from __future__ import annotations

from typing import Literal

from tiddl.cli.utils.resource import TidalResource
from tiddl.web.accounts import account_context
from tiddl.web.player import (
    _artist_dicts,
    format_duration,
    image_url,
)


def preview_item(item, item_type: str | None = None) -> dict:
    artists = ", ".join(artist.name for artist in getattr(item, "artists", []))
    return {
        "id": str(item.id),
        "type": item_type or ("video" if item.__class__.__name__.lower().endswith("video") else "track"),
        "title": item.title,
        "artist": artists,
        "duration": format_duration(item.duration),
        "explicit": bool(getattr(item, "explicit", False)),
    }


def detect_download_options(items: list[dict], source_items: list) -> tuple[dict, list[dict]]:
    has_audio = any(item["type"] in {"track", "album"} for item in items)
    has_video = any(item["type"] == "video" for item in items)
    track_items = [
        entry.item if hasattr(entry, "item") else entry
        for entry in source_items
        if getattr(entry, "type", "track") == "track"
    ]
    tags = {
        tag
        for track in track_items
        for tag in getattr(getattr(track, "mediaMetadata", None), "tags", [])
    }
    modes = {
        mode
        for track in track_items
        for mode in getattr(track, "audioModes", [])
    }
    has_atmos = "DOLBY_ATMOS" in tags or "DOLBY_ATMOS" in modes
    # 音质与 Atmos 整合成一个选择器:track_quality 档位在 Atmos 曲目时附加 "high_atmos" 复合档。
    # 下载侧 v1 明文流上限 44.1kHz/16bit;Atmos 曲目下载走 v1 E-AC-3(与 high 相同产物)。
    track_choices = ["low", "normal", "high"]
    if has_atmos:
        track_choices.append("high_atmos")  # 与 high 同规格,但下载 Atmos 流
    options = {
        "track_quality": "high_atmos" if has_atmos else "high",
        "video_quality": "fhd",
        "videos": "allow" if has_audio and has_video else ("only" if has_video else "none"),
    }
    specs = [
        {
            "key": "track_quality",
            "value": options["track_quality"],
            "choices": track_choices if has_audio else [],
        },
        {
            "key": "video_quality",
            "value": options["video_quality"],
            "choices": ["sd", "hd", "fhd"] if has_video else [],
        },
        {
            "key": "videos",
            "value": options["videos"],
            "choices": (
                ["none", "allow", "only"]
                if has_audio and has_video
                else (["only"] if has_video else ["none"])
            ),
        },
    ]
    return options, specs


def build_preview(urls: list[str]) -> list[dict]:
    api = account_context().api
    result = []

    def card(resource, input_index: int, items: list, source_items: list, title: str, subtitle: str, cover: str | None, truncated: bool, singles: bool = False, kind: str = "") -> dict:
        options, specs = detect_download_options(items, source_items)
        return {
            "resource": str(resource),
            "input_index": input_index,
            "type": resource.type,
            "title": title,
            "subtitle": subtitle,
            "cover": cover,
            "items": items,
            "truncated": truncated,
            "download_options": options,
            "specs": specs,
            "singles": singles,
            "kind": kind,
        }

    def artist_album_card_items(collection: object) -> list[dict]:
        return [
            {
                "id": str(album.id),
                "type": "album",
                "title": album.title,
                "artist": ", ".join(artist.name for artist in album.artists),
                "duration": format_duration(album.duration),
                "explicit": album.explicit,
            }
            for album in collection.items
        ]

    for input_index, value in enumerate(urls):
        resource = TidalResource.from_string(value)
        items = []
        truncated = False
        album_kind = ""
        if resource.type == "track":
            entity = api.get_track(resource.id)
            title = entity.title
            subtitle = ", ".join(artist.name for artist in entity.artists)
            cover = image_url(entity.album.cover)
            items = [preview_item(entity, "track")]
            source_items = [entity]
        elif resource.type == "video":
            entity = api.get_video(resource.id)
            title = entity.title
            subtitle = ", ".join(artist.name for artist in entity.artists)
            cover = image_url(entity.imageId)
            items = [preview_item(entity, "video")]
            source_items = [entity]
        elif resource.type == "album":
            entity = api.get_album(resource.id)
            collection = api.get_album_items(resource.id, limit=100)
            title = entity.title
            subtitle = ", ".join(artist.name for artist in entity.artists)
            cover = image_url(entity.cover)
            items = [preview_item(entry.item, entry.type) for entry in collection.items]
            source_items = collection.items
            truncated = collection.totalNumberOfItems > len(items)
            album_kind = getattr(entity, "type", "") or ""
        elif resource.type == "playlist":
            entity = api.get_playlist(resource.id)
            collection = api.get_playlist_items(resource.id, limit=100)
            title = entity.title
            subtitle = entity.description or "Playlist"
            cover = image_url(entity.squareImage or entity.image)
            items = [preview_item(entry.item, entry.type) for entry in collection.items]
            source_items = collection.items
            truncated = collection.totalNumberOfItems > len(items)
        elif resource.type == "mix":
            collection = api.get_mix_items(resource.id, limit=100)
            title = "Tidal mix"
            subtitle = f"{collection.totalNumberOfItems} items"
            cover = image_url(collection.items[0].item.album.cover) if collection.items else None
            items = [preview_item(entry.item, entry.type) for entry in collection.items]
            source_items = collection.items
            truncated = collection.totalNumberOfItems > len(items)
        else:
            entity = api.get_artist(resource.id)
            cover = image_url(entity.picture)
            albums = api.get_artist_albums(resource.id, limit=100, filter="ALBUMS")
            singles = api.get_artist_albums(resource.id, limit=100, filter="EPSANDSINGLES")
            result.append(card(resource, input_index, artist_album_card_items(albums), [], entity.name, "Artist releases", cover, albums.totalNumberOfItems > len(albums.items)))
            result.append(card(resource, input_index, artist_album_card_items(singles), [], entity.name, "Singles & EPs", cover, singles.totalNumberOfItems > len(singles.items), singles=True))
            continue
        result.append(card(resource, input_index, items, source_items, title, subtitle, cover, truncated, kind=album_kind))
    return result


def search_result(item, resource_type: Literal["track", "album"]) -> dict:
    # 专辑单数优先(作曲厂牌如 HOYO-MIX),曲目复数优先(展示演唱者)
    artists = _artist_dicts(item, prefer_singular=(resource_type == "album"))
    all_names = [a["name"] for a in artists] or [a.name for a in (getattr(item, "artists", []) or [])]
    cover_id = item.album.cover if resource_type == "track" else item.cover
    return {
        "resource": f"{resource_type}/{item.id}",
        "type": resource_type,
        "title": item.title,
        "subtitle": ", ".join(all_names),
        "artists": artists,
        "cover": image_url(cover_id, 160),
        "explicit": bool(getattr(item, "explicit", False)),
    }


def search_catalog(query: str, limit: int = 6) -> list[dict]:
    api = account_context().api
    results = api.get_search(query=query)
    combined = [
        *(search_result(item, "track") for item in results.tracks.items[:limit]),
        *(search_result(item, "album") for item in results.albums.items[:limit]),
    ]
    return combined
