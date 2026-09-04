"""DRM 相关:Widevine manifest 获取/解析、Atmos 降混转码、订阅探测。

依赖关系: accounts(账号上下文) + tidal_http(限流 HTTP),不依赖 app 路由状态。
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Literal

from tiddl.core.utils.ffmpeg import is_ffmpeg_installed
from tiddl.web.accounts import account_context
from tiddl.web.tidal_http import _tidal_get

log = logging.getLogger(__name__)

# Atmos-only 曲目(如 EL CANTANTE DEL GHETTO)在 Tidal 上无论请求什么质量都只有 E-AC-3 流,
# 浏览器无法解码。用 ffmpeg 降混转码为立体声 AAC 缓存,再本地流式播放。
TRANSCODE_CACHE: dict[str, str] = {}
TRANSCODE_DIR = Path(tempfile.gettempdir()) / "tiddl-web-atmos"

DRM_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# v2 manifest 短缓存:同一曲目短窗口内重复播放不再请求 Tidal(更快更稳)。
# 缓存键必须含账号与 formats,避免跨账号/跨格式复用。
TIDAL_MANIFEST_CACHE_TTL = 60
_v2_manifest_cache: dict[tuple[str, str, str], tuple[float, dict]] = {}

# 订阅检测:用账号自有 client 请求一个普通曲目的 v2 manifest,
# 若返回 FULL 表示订阅有效;PREVIEW + FULL_REQUIRES_HIGHER_ACCESS_TIER 表示订阅过期/无权限。
# 注意:必须用自有 client(device-flow)而非官方公开 client(后者对任何账号都只给 PREVIEW)。
SUBSCRIPTION_PROBE_TRACK = "20115564"


def transcode_atmos_to_stereo(track_id: str, url: str) -> str:
    cached = TRANSCODE_CACHE.get(track_id)
    if cached and Path(cached).exists():
        return cached
    if not is_ffmpeg_installed():
        raise ValueError("This track is only available as Dolby Atmos, and ffmpeg is not installed to transcode it.")
    TRANSCODE_DIR.mkdir(parents=True, exist_ok=True)
    output = TRANSCODE_DIR / f"{track_id}.m4a"
    tmp = output.with_suffix(".tmp.m4a")
    # 下载 Atmos 流并降混为双声道 AAC (浏览器可直接播放)
    try:
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", url,
            "-vn", "-ac", "2", "-c:a", "aac", "-b:a", "256k",
            "-movflags", "+faststart",
            str(tmp),
        ], capture_output=True, text=True, timeout=240, check=True)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        if tmp.exists():
            tmp.unlink()
        log.warning("Failed to transcode Atmos stream for track %s: %s", track_id, exc)
        raise ValueError("Could not transcode the Dolby Atmos stream to stereo audio.") from exc
    tmp.replace(output)
    TRANSCODE_CACHE[track_id] = str(output)
    return str(output)


# v2 音质档位映射:前端 PlayerResolveRequest.quality → 请求的 formats(按优先级,降级链)
V2_QUALITY_FORMATS: dict[str, list[str]] = {
    "LOW": ["HEAACV1", "AACLC"],
    "HIGH": ["AACLC", "HEAACV1"],
    "LOSSLESS": ["FLAC", "AACLC", "HEAACV1"],
    "HI_RES_LOSSLESS": ["FLAC_HIRES", "FLAC", "AACLC", "HEAACV1"],
}


def v2_formats_for_quality(quality: str | None, aac_only: bool = False) -> list[str]:
    """把音质档位映射成 v2 formats 列表(含降级链)。未知档位回退 AACLC。

    aac_only=True 时排除 FLAC/FLAC_HIRES(浏览器 Widevine CDM 可能无法解码
    FLAC-in-MP4 的 MSE 流,如 Firefox;此时降级到 AAC-LC,仍零带宽)。
    """
    formats = V2_QUALITY_FORMATS.get(quality or "", ["AACLC"])
    if aac_only:
        formats = [f for f in formats if f not in ("FLAC", "FLAC_HIRES")]
    return formats


def browser_prefers_aac(ua: str | None) -> bool:
    """根据浏览器 User-Agent 判断 v2 播放是否应强制降级到 AAC-LC。

    Firefox 的 MP4 parser 对高采样率(96kHz+) FLAC 分片有 bug(Bugzilla 2060830,
    MSE append 直接 NS_ERROR_FAILURE),其 Widevine CDM 对 FLAC 作为受保护
    音频的支持也不可靠(x-cdm-codecs 不含 flac),且 cbcs 加密方案在 Firefox 上
    长期残缺(Bugzilla 1492377 至今 OPEN)。Safari 的 FLAC-in-MSE 支持也有历史
    问题(WebKit bug 198583)。这类浏览器强制 aac_only,避免 FLAC bundle 下发后
    在 MSE append / EME 阶段失败,降级到 AAC-LC(320kbps,仍零带宽)。
    """
    if not ua:
        return False
    u = ua.lower()
    # Firefox:Gecko 内核,UA 含 "firefox/" 且无 Chromium 标记
    is_firefox = "firefox/" in u and "seamonkey" not in u and "chrome/" not in u and "edg/" not in u and "opr/" not in u
    # 真 Safari(含 "safari/" 且无 Chromium/Gecko 标记)
    is_safari = (
        "safari/" in u
        and "chrome/" not in u
        and "chromium" not in u
        and "edg/" not in u
        and "opr/" not in u
        and "firefox/" not in u
    )
    return is_firefox or is_safari


def v2_drm_manifest(track_id: str, account_id: str, formats: str | list[str] = "AACLC", aac_only: bool = False) -> dict:
    """Fetch the v2 trackManifest (MPEG-DASH) and return a playable DRM bundle.

    formats: 用户期望档位的降级链,如 ["FLAC_HIRES","FLAC","AACLC","HEAACV1"]。
    恒请求全部 formats + adaptive=true,服务端返回该曲目全部可用 Representation;
    本地按 fmt_list 优先级选「用户所选档」的最优 Rep(选 LOW 得 HE-AAC,选 Hi-Res 得 FLAC_HIRES)。
    The init/media URLs are CloudFront-signed and can be fetched by the browser
    directly (plain GET, no custom headers) — zero server bandwidth.

    重要(HAR 实测 2026-09-04):
    1) MPD Representation 带 bandwidth 属性 = 该档真实码率(bps),无损也有(如 FLAC 44.1/16 ≈ 941436)。
    2) 恒请求全 formats + adaptive=true → 缓存键与所选档位无关,切档命中同一缓存(限流规避)。
    """
    import base64
    import html as html_mod
    import io
    import xml.etree.ElementTree as ET

    api = account_context(account_id).api
    token = api.client.token
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
        "Referer": "https://tidal.com/",
        "User-Agent": DRM_UA,
    }
    # 恒请求全量 formats + adaptive=true(实测 2026-09-04):
    # adaptive=true → 服务端返回该曲目全部可用 Representation(菜单枚举+选档);
    # formats 参数 = 期望档位的降级链(如 ["FLAC_HIRES","FLAC","AACLC","HEAACV1"]),
    # 仅用于「从全档里选用户所选档」,不参与请求构造。
    # 缓存键与所选档位无关 → 切档命中同一缓存,零新增 Tidal 请求(限流规避核心)。
    ALL_V2_FORMATS = ["FLAC_HIRES", "FLAC", "AACLC", "HEAACV1"]
    fmt_list = [formats] if isinstance(formats, str) else list(formats)
    request_formats = ALL_V2_FORMATS
    params = {
        "adaptive": "true",  # 枚举全部可用档;选档在本地进行
        "manifestType": "MPEG_DASH",
        "uriScheme": "DATA",
        "usage": "PLAYBACK",
    }
    # Tidal 支持重复 formats 参数(多值)
    import urllib.parse
    query = urllib.parse.urlencode(
        [(k, v) for k, v in params.items()]
        + [("formats", f) for f in request_formats]
    )
    # 缓存键只含账号+曲目:恒请求全 formats → 切任意档命中同一缓存
    cache_key = "ALL"
    # 短缓存:同一账号同一曲目短窗口内重复播放不再请求 Tidal(更快更稳,减少限流)。
    # 缓存键必须含账号:不同账号的 DRM manifest/PSSH 不同,跨账号复用会导致 license 失败。
    #
    # 重要:缓存只存「原始 manifest 解析结果」(与档位无关),选档(best_rep)
    # 必须在缓存外按每次请求的 fmt_list 重算——否则第一次请求(如 LOW)把
    # best_rep=HEAACV1 固化进缓存,后续切 HIGH/LOSSLESS 也命中同一缓存返回
    # 同一个 bundle,表现为「切什么音质都变回同一档位」(线上实测 bug)。
    now = time.time()
    cached = _v2_manifest_cache.get((account_id, track_id, cache_key))
    if cached and now - cached[0] < TIDAL_MANIFEST_CACHE_TTL:
        manifest = cached[1]
    else:
        resp = _tidal_get(
            f"https://openapi.tidal.com/v2/trackManifests/{track_id}?{query}",
            params=None,
            headers=headers,
            timeout=45,
        )
        if resp.status_code != 200:
            raise ValueError(f"Tidal v2 manifest request failed (HTTP {resp.status_code})")
        attr = resp.json()["data"]["attributes"]
        data_uri = attr["uri"]
        payload = data_uri.split(",", 1)[1]
        xml_text = base64.b64decode(payload).decode("utf-8")
        manifest = {
            "root": ET.fromstring(xml_text),
            "pssh": None,
            "kid": None,
        }
        _v2_manifest_cache[(account_id, track_id, cache_key)] = (now, manifest)
    root = manifest["root"]
    ns = {
        "mpd": "urn:mpeg:dash:schema:mpd:2011",
        "cenc": "urn:mpeg:cenc:2013",
    }
    # PSSH/kid 与档位无关,可从原始 manifest 直接提取(缓存内复算,成本可忽略)
    pssh = None
    for cp in root.iter("{urn:mpeg:dash:schema:mpd:2011}ContentProtection"):
        scheme = cp.get("schemeIdUri", "")
        pssh_el = cp.find("cenc:pssh", ns)
        if pssh_el is not None and pssh_el.text:
            if "edef8ba9" in scheme and pssh is None:
                pssh = pssh_el.text.strip()
            elif pssh is None:
                pssh = pssh_el.text.strip()
    if not pssh:
        raise ValueError("No PSSH found in Tidal DRM manifest.")
    kid = None
    for cp in root.iter("{urn:mpeg:dash:schema:mpd:2011}ContentProtection"):
        kid = cp.get("{urn:mpeg:cenc:2013}default_KID") or cp.get("cenc:default_KID")
        if kid:
            break
    # PSSH/kid 已在缓存解析时提取(ns 在上方定义)
    # init / media URLs (escape &amp;)
    def _url(text: str | None) -> str | None:
        return html_mod.unescape(text) if text else None
    init_url = media_url = media_template = None
    codec = mime_type = None
    sample_rate = None
    bit_depth = None
    bandwidth = None  # MPD bandwidth(bps)=该档真实码率,无损也有(HAR 实测)
    actual_format = None
    duration_s = None
    segment_count = 0
    # 收集 Representation:adaptive=true 时服务端返回全部可用档(HAR 实测),
    # 选档按用户期望的降级链(fmt_list)优先 —— 选 LOW 得 HE-AAC,选 Hi-Res 得 FLAC_HIRES,
    # 而非恒选最优档。同时记录全部 available_formats 供菜单校准。
    reps = list(root.iter("{urn:mpeg:dash:schema:mpd:2011}Representation"))

    def _rep_priority(rep) -> int:
        rid = (rep.get("id") or "").split(",")[0].strip()
        try:
            return fmt_list.index(rid)
        except ValueError:
            return len(fmt_list)

    # aac_only(Firefox/Safari 等无法解码 FLAC-in-MSE)时,过滤掉 FLAC 档,
    # 只从 AAC 档里选最优 —— 仍在同一份缓存 manifest 内选择,不新增请求。
    candidate_reps = reps
    if aac_only:
        candidate_reps = [
            rep
            for rep in reps
            if (rep.get("id") or "").split(",")[0].strip() in ("AACLC", "HEAACV1")
        ]
    best_rep = min(candidate_reps, key=_rep_priority) if candidate_reps else None
    if best_rep is not None:
        codec = best_rep.get("codecs")
        if best_rep.get("audioSamplingRate"):
            sample_rate = int(best_rep.get("audioSamplingRate"))
        if best_rep.get("bandwidth"):
            bandwidth = int(best_rep.get("bandwidth"))
        rep_id = best_rep.get("id") or ""
        if rep_id:
            actual_format = rep_id.split(",")[0].strip()
        for part in rep_id.split(","):
            part = part.strip()
            if part.isdigit() and int(part) in (16, 20, 24, 32):
                bit_depth = int(part)
        for st in best_rep.iter("{urn:mpeg:dash:schema:mpd:2011}SegmentTemplate"):
            init_url = _url(st.get("initialization"))
            media_url = _url(st.get("media"))
            if media_url and "$Number$" in media_url:
                media_template = media_url
                media_url = media_url.replace("$Number$", "1")
    # 计算段数:只统计所选档(best_rep)所在 AdaptationSet 的 <S>(各档段数不同,
    # 全部累加会高估(56+55+55+56=222),feed 按高估数拉取超出实际段 → CDN 400)。
    # 优先用 best_rep 自己的 SegmentTemplate;若模板在 AdaptationSet 层级则回退。
    segment_count = 0
    st_rep = best_rep.find("{urn:mpeg:dash:schema:mpd:2011}SegmentTemplate")
    if st_rep is None:
        for parent in root.iter("{urn:mpeg:dash:schema:mpd:2011}AdaptationSet"):
            if best_rep in list(parent):
                for st in parent.iter("{urn:mpeg:dash:schema:mpd:2011}SegmentTemplate"):
                    st_rep = st
                break
    if st_rep is not None:
        for s in st_rep.iter("{urn:mpeg:dash:schema:mpd:2011}S"):
            segment_count += int(s.get("r", "0")) + 1
    duration_text = root.get("mediaPresentationDuration")
    if duration_text:
        # PT4M34.566S
        import re as re_mod
        m = re_mod.match(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", duration_text)
        if m:
            duration_s = (int(m.group(1) or 0) * 60 + float(m.group(2) or 0))
    for aset in root.iter("{urn:mpeg:dash:schema:mpd:2011}AdaptationSet"):
        mime_type = aset.get("mimeType")
        break
    if not init_url or not media_url:
        raise ValueError("Tidal DRM manifest missing segment URLs.")
    bundle = {
        "pssh": pssh,
        "kid": kid,
        "init_url": init_url,
        "media_url": media_url,
        "media_template": media_template or media_url,
        "segment_count": segment_count or 1,
        "codec": codec or "mp4a.40.2",
        "mime_type": mime_type or "audio/mp4",
        "duration_s": duration_s,
        "sample_rate": sample_rate,
        "bit_depth": bit_depth,
        "bandwidth": bandwidth,  # MPD 真实码率(bps),无损也有(HAR 实测)
        # 用户期望档位的降级链(选档用,不参与请求构造)
        "requested_formats": fmt_list,
        "format": actual_format or cache_key,
        # 曲目全部可用档位(菜单校准):adaptive=true 时 reps 含全部档
        "available_formats": sorted(
            {
                (rep.get("id") or "").split(",")[0].strip()
                for rep in reps
                if (rep.get("id") or "").strip()
            },
            key=lambda f: ALL_V2_FORMATS.index(f) if f in ALL_V2_FORMATS else 99,
        ),
        # 每档真实码率映射 format → kbps(菜单显示;同 format 取最高 bandwidth)。
        # 取整与后端 bitrate(round)一致,避免菜单 321 vs 按钮 322 的显示不一致。
        "format_bandwidths": {
            fmt: round(
                max(
                    int(r.get("bandwidth") or 0)
                    for r in reps
                    if (r.get("id") or "").split(",")[0].strip() == fmt
                )
                / 1000
            )
            for fmt in {
                (rep.get("id") or "").split(",")[0].strip()
                for rep in reps
                if (rep.get("id") or "").strip()
            }
        },
    }
    # 缓存已在 193 行存原始 manifest(与档位无关);bundle 是按本次 fmt_list 选档的
    # 结果,不能再覆盖缓存——否则切档会命中上一次选定的档位(线上实测 bug)。
    return bundle


def probe_subscription(account_id: str) -> Literal["active", "expired", "unknown"]:
    import base64 as b64_mod
    api = account_context(account_id).api
    token = api.client.token
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
        "Referer": "https://tidal.com/",
        "User-Agent": DRM_UA,
    }
    resp = _tidal_get(
        f"https://openapi.tidal.com/v2/trackManifests/{SUBSCRIPTION_PROBE_TRACK}",
        params={
            "adaptive": "true",
            "formats": "AACLC",
            "manifestType": "MPEG_DASH",
            "uriScheme": "DATA",
            "usage": "PLAYBACK",
        },
        headers=headers,
        timeout=45,
    )
    if resp.status_code != 200:
        log.warning("subscription probe HTTP %s for %s", resp.status_code, account_id)
        return "unknown"
    attrs = resp.json()["data"]["attributes"]
    presentation = attrs.get("trackPresentation")
    reason = attrs.get("previewReason") or ""
    if presentation == "FULL":
        return "active"
    if presentation == "PREVIEW" and "FULL_REQUIRES_HIGHER_ACCESS_TIER" in reason:
        return "expired"
    return "unknown"
