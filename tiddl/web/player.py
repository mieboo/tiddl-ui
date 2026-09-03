"""Player 视图的纯函数(从 web/app.py 抽取,不依赖 app 内部状态)。

包含:封面 URL、亮度启发式、时长格式化、艺人归一化、曲目模板化、音质档位。
这些函数只依赖 Tidal API 模型与标准库,可在单元测试中直接使用。
"""

from __future__ import annotations

import logging
import requests

log = logging.getLogger(__name__)


def image_url(image_id: str | None, size: int = 320) -> str | None:
    if not image_id:
        return None
    path = image_id.replace("-", "/")
    return f"https://resources.tidal.com/images/{path}/{size}x{size}.jpg"


def cover_is_bright(url: str | None) -> bool:
    """Average-cover-luminance heuristic (Kugou style): True means the cover
    is bright, so lyrics text should switch to dark colors."""
    if not url:
        return False
    try:
        import io

        from PIL import Image

        response = requests.get(url, timeout=10)
        response.raise_for_status()
        with Image.open(io.BytesIO(response.content)) as image:
            small = image.convert("L").resize((16, 16))
            pixels = list(small.getdata())
        return (sum(pixels) / len(pixels)) >= 140
    except Exception as exc:
        log.debug("Failed to compute cover brightness for %s: %s", url, exc)
        return False


def format_duration(seconds: int) -> str:
    minutes, remaining = divmod(max(seconds, 0), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{remaining:02d}" if hours else f"{minutes}:{remaining:02d}"


def _artist_dicts(obj, prefer_singular: bool = False) -> list[dict]:
    """把 Tidal 艺人字段统一成 [{id, name}]。
    prefer_singular=True 用于专辑:作曲厂牌(如 HOYO-MIX)主艺人在单数字段,
    复数 artists 里可能是演唱者,必须单数优先。
    否则(曲目/常规)复数优先。
    复数列表里优先保留 type==MAIN 的主艺人,过滤掉 FEATURED 合作者。"""
    if prefer_singular:
        singular = getattr(obj, "artist", None)
        if singular is not None and getattr(singular, "id", None) is not None:
            return [{"id": str(singular.id), "name": singular.name}]
    plural = getattr(obj, "artists", None) or []
    if plural:
        def _item(a):
            return {"id": str(a.id), "name": a.name}
        main = [_item(a) for a in plural if getattr(a, "type", None) == "MAIN" and getattr(a, "id", None) is not None]
        rest = [_item(a) for a in plural if getattr(a, "type", None) != "MAIN" and getattr(a, "id", None) is not None]
        return main or rest
    if not prefer_singular:
        singular = getattr(obj, "artist", None)
        if singular is not None and getattr(singular, "id", None) is not None:
            return [{"id": str(singular.id), "name": singular.name}]
    return []


def player_track(item) -> dict:
    artists = [{"id": str(artist.id), "name": artist.name} for artist in item.artists]
    # 单数 artist:作曲厂牌(如 HOYO-MIX)的主艺人常只在这里,复数 artists 里可能是演唱者
    track_artist = (
        {"id": str(item.artist.id), "name": item.artist.name}
        if getattr(item, "artist", None)
        else (artists[0] if artists else {})
    )
    return {
        "id": str(item.id),
        "title": item.title,
        "artist": ", ".join(artist["name"] for artist in artists),
        "artist_id": artists[0]["id"] if artists else "",
        "artists": artists,
        "track_artist": track_artist,
        "album": item.album.title,
        "album_id": str(item.album.id),
        "cover": image_url(item.album.cover, 640),
        "duration": item.duration,
        "track_number": getattr(item, "trackNumber", 0) or 0,
        "explicit": bool(item.explicit),
        "qualities": _track_qualities(item),
        "atmos": "DOLBY_ATMOS" in item.mediaMetadata.tags or "DOLBY_ATMOS" in item.audioModes,
    }


def _track_qualities(item) -> list[str]:
    """曲目真实可用的音质档位(v1 明文 + v2 DRM 能力),Atmos 折叠进档位。

    返回形如 ["LOW","HIGH","LOSSLESS","LOSSLESS_ATMOS","HI_RES_LOSSLESS","HI_RES_LOSSLESS_ATMOS"]:
    - 普通立体声曲目:v1 有 LOW/HIGH/LOSSLESS,HI_RES 取决于 HIRES_LOSSLESS 标签(v1 实际只给 44.1/16)
    - Atmos 曲目:在无损档后附加 "_ATMOS" 复合档 —— 播放走 v2 DRM(FLAC/FLAC_HIRES),下载走 v1 E-AC-3
    - Atmos-only(无 STEREO):只给 Atmos 复合档,不给纯立体声档(没有立体声可播/可下)
    """
    tags = item.mediaMetadata.tags or []
    modes = list(item.audioModes or [])
    atmos = "DOLBY_ATMOS" in tags or "DOLBY_ATMOS" in modes
    has_stereo = "STEREO" in modes
    lossless = atmos or "LOSSLESS" in tags or "HIRES_LOSSLESS" in tags
    hires = atmos or "HIRES_LOSSLESS" in tags
    tiers = ["LOW", "HIGH"]
    if lossless:
        tiers.append("LOSSLESS")
    if hires:
        tiers.append("HI_RES_LOSSLESS")
    # Atmos 曲目:在无损档后追加 Atmos 复合档(有立体声则保留纯立体声档,否则只给 Atmos)
    if atmos:
        if not has_stereo:
            tiers = [t + "_ATMOS" for t in tiers if t in ("LOSSLESS", "HI_RES_LOSSLESS")]
        else:
            tiers = [t for t in tiers if t not in ("LOSSLESS", "HI_RES_LOSSLESS")] + [
                "LOSSLESS_ATMOS",
                "HI_RES_LOSSLESS_ATMOS",
            ]
    return tiers


def player_quality_tiers(quality: str) -> list[str]:
    order = ["HI_RES_LOSSLESS", "LOSSLESS", "HIGH", "LOW"]
    try:
        return order[order.index(quality):]
    except ValueError:
        return ["HIGH", "LOW"]


# 明文/直连门禁:判定 Tidal 流 manifest 是否受 DRM 保护。
# 所有「浏览器直接保存/播放明文流」的路径必须经过此判定,避免把加密流当明文下发。
# 唯一可信来源是 manifest 的 encryptionType;local transcoded 产物由构造方保证 NONE。
def is_protected_stream(manifest: dict) -> bool:
    return manifest.get("encryptionType", "NONE") not in {"NONE", ""}
