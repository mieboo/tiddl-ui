from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from base64 import b64decode
import importlib.metadata
import io
import json
import logging
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import sys
import time
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4
import zipfile

import aiohttp
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
import uvicorn

from tiddl.cli.config import APP_PATH, CONFIG
from tiddl.cli.utils.resource import TidalResource
from tiddl.core.utils import parse_track_stream
from tiddl.core.utils.const import track_qualities
from tiddl.core.utils.spec import StreamSpec
from tiddl.web.auth_routes import router as auth_router
from tiddl.web.users import (
    DOWNLOAD_QUOTA_BYTES,
    DOWNLOAD_QUOTA_WINDOW,
    TRAFFIC_KIND_DOWNLOAD,
    TRAFFIC_KIND_PLAY,
    User,
    ensure_bootstrap_admin,
    get_current_user,
    get_users,
    require_admin,
)
from tiddl.web.giveaway import GiveawayStore
from tiddl.web.player import (
    _artist_dicts,
    cover_is_bright,
    format_duration,
    image_url,
    is_protected_stream,
    player_quality_tiers,
    player_track,
)
from tiddl.web.tidal_http import (
    _tidal_post,
)
from tiddl.web.accounts import (
    ACCOUNTS_DIR,
    ACCOUNT_SETTINGS_FILE,
    LEGACY_ACCOUNT_ID,
    AccountHealth,
    account_context,
    account_health,
    account_ids,
    account_info,
    account_loads,
    account_path,
    available_account_ids,
    is_authentication_error,
    load_account_settings,
    save_account_settings,
    select_account,
)
from tiddl.web.drm import (
    DRM_UA,
    browser_prefers_aac,
    transcode_atmos_to_stereo,
    v2_drm_manifest,
    v2_formats_for_quality,
)
from tiddl.web.preview import (
    build_preview,
    detect_download_options,
    search_catalog,
    search_result,
)
from tiddl.web.state import (
    Job,
    PlayerSession,
    job_order,
    jobs,
    player_sessions,
    request_stats,
)
from tiddl.web.telemetry import _write_telemetry, telemetry_throttled
from tiddl.web.health import (
    check_account_health,
    check_account_subscription,
    health_monitor,
)
from tiddl.web.tasks import (
    bandwidth_balancer,
    bandwidth_snapshot,
    create_job,
    handle_output_line,
)
from tiddl.web.bandwidth import (
    load_config,
    save_config,
)


STATIC_DIR = Path(__file__).parent / "static"
log = logging.getLogger(__name__)

# 赠送账号池目标大小:启动时补齐(已领取的保留,不足则新增到该数量)
GIVEAWAY_POOL_SIZE = 10

GIVEAWAY_STORE = GiveawayStore(APP_PATH / "giveaway_state.json")


def get_giveaway() -> GiveawayStore:
    return GIVEAWAY_STORE


@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    global health_monitor_task, bandwidth_balancer_task
    # 首次启动创建初始 admin(环境变量 TIDDL_ADMIN_USERNAME/PASSWORD,否则随机生成并记日志)
    try:
        ensure_bootstrap_admin()
    except Exception as exc:
        log.warning("Failed to bootstrap admin user: %s", exc)
    # 启动时补齐赠送账号池(已领取的保留,补足到 10 个)
    try:
        get_giveaway().ensure_accounts(get_users(), count=GIVEAWAY_POOL_SIZE)
    except Exception as exc:
        log.warning("Failed to ensure giveaway accounts: %s", exc)
    health_monitor_task = asyncio.create_task(health_monitor())
    bandwidth_balancer_task = asyncio.create_task(bandwidth_balancer())
    try:
        yield
    finally:
        health_monitor_task.cancel()
        bandwidth_balancer_task.cancel()
        with suppress(asyncio.CancelledError):
            await health_monitor_task
            await bandwidth_balancer_task


app = FastAPI(title="Abducted Tidal Player", docs_url=None, redoc_url=None, lifespan=app_lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(auth_router)
# 后台任务句柄(有 `global` 赋值,必须留在本模块;数据状态见 web.state)
health_monitor_task: asyncio.Task | None = None
bandwidth_balancer_task: asyncio.Task | None = None
PLAYER_SESSION_TTL = 20 * 60
# --- Tidal 限流规避(用户体验优先) ---
# 1) 正常请求零延迟:不加固定 sleep,只在确认被限流/瞬时故障时退避重试
# 2) 并发上限:防突发尖峰(用户并发操作),超出时排队而非同时打 Tidal
ACCOUNTS_DIR = APP_PATH / "accounts"
ACCOUNT_SETTINGS_FILE = ACCOUNTS_DIR / "settings.json"
LEGACY_ACCOUNT_ID = "default"
HOST = os.environ.get("TIDDL_HOST", "127.0.0.1")
PORT = int(os.environ.get("TIDDL_PORT", "8765"))
def app_version() -> str:
    try:
        return importlib.metadata.version("tiddl-ui")
    except importlib.metadata.PackageNotFoundError:
        return "dev"


def candidate_ips() -> list[str]:
    candidates = []
    try:
        import fcntl
        import struct
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            for _, name in socket.if_nameindex():
                try:
                    packed = struct.pack("256s", name[:15].encode())
                    candidates.append(socket.inet_ntoa(fcntl.ioctl(sock.fileno(), 0x8915, packed)[20:24]))
                except OSError:
                    continue
    except (ImportError, OSError):
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            candidates.append(sock.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidates.append(info[4][0])
    except socket.gaierror:
        pass
    return candidates


def lan_addresses(port: int) -> list[str]:
    urls = []
    for ip in candidate_ips():
        if ip in urls or ip.startswith(("127.", "169.254.", "198.18.", "198.19.")):
            continue
        if not ip.startswith(("192.168.", "10.", "172.")):
            continue
        if ip.startswith("172.") and not 16 <= int(ip.split(".")[1]) <= 31:
            continue
        urls.append(f"http://{ip}:{port}")
    return urls


class ResourceDownloadOptions(BaseModel):
    track_quality: Literal["low", "normal", "high", "max"] = "high"
    video_quality: Literal["sd", "hd", "fhd"] = "fhd"
    videos: Literal["none", "allow", "only"] = "none"
    atmos: Literal["none", "allow", "only"] = "none"


class ResourceMetadata(BaseModel):
    title: str = ""
    subtitle: str = ""
    cover: str | None = None
    type: str = ""
    singles: bool = False


class DownloadRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=100)
    track_quality: Literal["low", "normal", "high", "max"] = "high"
    video_quality: Literal["sd", "hd", "fhd"] = "fhd"
    videos: Literal["none", "allow", "only"] = "none"
    atmos: Literal["none", "allow", "only"] = "none"
    threads: int = Field(default=4, ge=1, le=16)
    skip_existing: bool = True
    download_path: str = ""
    output_template: str = ""
    resource_options: list[ResourceDownloadOptions] = Field(default_factory=list)
    resource_metadata: list[ResourceMetadata] = Field(default_factory=list)

    @field_validator("urls")
    @classmethod
    def clean_urls(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if not cleaned:
            raise ValueError("Add at least one Tidal URL or resource ID.")
        allowed = re.compile(r"^(?:https?://(?:listen\.)?tidal\.com/)?(?:browse/)?(?:(?:track|video|album|playlist|artist|mix)/[A-Za-z0-9-]+|album/\d+/track/\d+)(?:\?.*)?$")
        invalid = [value for value in cleaned if not allowed.match(value)]
        if invalid:
            raise ValueError(f"Unsupported Tidal resource: {invalid[0]}")
        return cleaned


class PreviewRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=20)

    @field_validator("urls")
    @classmethod
    def clean_urls(cls, values: list[str]) -> list[str]:
        return DownloadRequest.clean_urls(values)


class PlayerResolveRequest(BaseModel):
    track_id: str = Field(pattern=r"^\d+$")
    quality: Literal["LOW", "HIGH", "LOSSLESS", "HI_RES_LOSSLESS"] = "HIGH"
    allow_atmos: bool = False
    drm: bool = False  # 浏览器支持 EME/Widevine 时请求 v2 DRM 播放(seek 更流畅)
    aac_only: bool = False  # 浏览器无法解码 FLAC-in-MSE(Widevine CDM 不支持/Firefox parser bug)时降级 AAC-LC
    no_images: bool = False  # 省流量模式:跳过封面亮度分析等一切图片请求


class PlayerResourceRequest(BaseModel):
    resource: str

    @field_validator("resource")
    @classmethod
    def clean_resource(cls, value: str) -> str:
        cleaned = value.strip()
        if not re.fullmatch(r"(?:https?://(?:listen\.)?tidal\.com/)?(?:browse/)?(?:(?:track|album)/\d+|album/\d+/track/\d+)(?:\?.*)?", cleaned):
            raise ValueError("Player supports Tidal tracks and albums.")
        return cleaned


def cli_command(*args: str) -> list[str]:
    return [sys.executable, "-c", "from tiddl.cli.app import app; app()", *args]


def player_resource(resource_value: str) -> list[dict]:
    resource = TidalResource.from_string(resource_value)
    api = account_context().api
    if resource.type == "track":
        return [player_track(api.get_track(resource.id))]
    if resource.type == "album":
        # 附带专辑主艺人,避免专辑卡用第一首曲目的艺人(可能含 feat 合作艺人)。
        # 作曲厂牌专辑(HOYO-MIX)主艺人在单数 artist 字段,复数 artists 里可能是演唱者。
        album = api.get_album(resource.id)
        album_artists = _artist_dicts(album, prefer_singular=True)
        collection = api.get_album_items(resource.id, limit=100)
        return [
            {**player_track(entry.item), "album_artists": album_artists}
            for entry in collection.items
            if entry.type == "track"
        ]
    raise ValueError("Player supports Tidal tracks and albums.")


def resolve_player_stream(track_id: str, quality: str, account_id: str, allow_atmos: bool = False, no_images: bool = False, aac_only: bool = False) -> tuple[PlayerSession, dict, dict | None]:
    api = account_context(account_id).api
    track = api.get_track(track_id)
    if not track.allowStreaming or not track.streamReady:
        raise ValueError("This track is not available for streaming.")
    try:
        tidal_session_id = api.get_session().sessionId
    except Exception as exc:
        log.debug("Failed to create Tidal session, streaming without session id: %s", exc)
        tidal_session_id = None
    stream = None
    urls = []
    extension = ""
    manifest = {}
    last_error: Exception | None = None
    atmos_only = False
    for candidate in player_quality_tiers(quality):
        try:
            candidate_stream = api.get_track_stream(
                track_id, candidate, session_id=tidal_session_id
            )
            if candidate_stream.audioMode == "DOLBY_ATMOS":
                # 浏览器无法解码 eac3/ac4;确认 Atmos-only 后提前跳出 v1 循环,
                # 直接走下方 v2 AAC-LC 直连兜底(避免逐档重试拖慢首播)。
                # 普通曲目(第一档即非 Atmos)不受影响,会正常 break。
                atmos_only = True
                break
            candidate_urls, candidate_extension = parse_track_stream(candidate_stream)
            if candidate_stream.manifestMimeType != "application/vnd.tidal.bts" or len(candidate_urls) != 1:
                raise ValueError("This quality uses a segmented stream that the web player cannot play yet.")
            candidate_manifest = json.loads(b64decode(candidate_stream.manifest).decode("utf-8"))
            if is_protected_stream(candidate_manifest):
                raise ValueError("This protected stream cannot be played in the web player.")
            stream = candidate_stream
            urls = candidate_urls
            extension = candidate_extension
            manifest = candidate_manifest
            break
        except Exception as exc:
            last_error = exc
    local_path: str | None = None
    transcoded = False
    drm_bundle: dict | None = None
    if stream is None:
        if atmos_only:
            # 只有 Atmos 流:优先用 v2 AAC-LC DASH 直连(零带宽,浏览器 MSE 播放),
            # 仅当 v2 不可用时才回退到后端 ffmpeg 转码。
            try:
                drm_bundle = v2_drm_manifest(track_id, account_id, v2_formats_for_quality(quality, aac_only=aac_only))
                if drm_bundle:
                    session = PlayerSession(
                        id=uuid4().hex,
                        track_id=track_id,
                        account_id=account_id,
                        url="",
                        mime_type=drm_bundle["mime_type"],
                        codec=drm_bundle["codec"],
                        quality=quality,
                        audio_mode="STEREO",
                        bit_depth=drm_bundle.get("bit_depth"),
                        sample_rate=drm_bundle.get("sample_rate"),
                        expires_at=time.time() + PLAYER_SESSION_TTL,
                        drm=drm_bundle,
                    )
                    lyrics = None
                    try:
                        lyric_data = api.get_track_lyrics(track_id)
                        lyrics = {"text": lyric_data.lyrics, "subtitles": lyric_data.subtitles, "rtl": lyric_data.isRightToLeft}
                    except Exception as exc:
                        log.debug("Failed to load lyrics for track %s: %s", track_id, exc)
                    return session, player_track(track), lyrics, (False if no_images else cover_is_bright(player_track(track)["cover"]))
            except Exception as exc:
                log.debug("v2 AAC-LC direct manifest failed for %s: %s", track_id, exc)
            # 兜底:后端 ffmpeg 转码 Atmos → 立体声 AAC
            atmos_urls: list[str] = []
            try:
                atmos_stream = api.get_track_stream(track_id, "LOW", session_id=tidal_session_id)
                atmos_urls, _ = parse_track_stream(atmos_stream)
            except Exception as exc:
                log.debug("Failed to fetch Atmos stream for transcode of %s: %s", track_id, exc)
            if not atmos_urls:
                raise last_error or ValueError("This track is only available as Dolby Atmos, and no playable stream could be resolved.")
            local_path = transcode_atmos_to_stereo(track_id, atmos_urls[0])
            transcoded = True
            stream = atmos_stream
            urls = [local_path]
            extension = ".m4a"
            manifest = {"mimeType": "audio/mp4", "codecs": "mp4a.40.2", "encryptionType": "NONE"}
        else:
            raise last_error or ValueError("No compatible stream quality is available.")
    if transcoded:
        url = local_path
    else:
        url = urls[0]
        parsed_url = urlparse(url)
        if parsed_url.scheme != "https" or not parsed_url.hostname:
            raise ValueError("Tidal returned an invalid stream URL.")
    codec = manifest.get("codecs", "")
    mime_type = manifest.get("mimeType") or ("audio/flac" if extension == ".flac" else "audio/mp4")
    session = PlayerSession(
        id=uuid4().hex,
        track_id=track_id,
        account_id=account_id,
        url=url,
        mime_type=mime_type,
        codec=codec,
        quality=stream.audioQuality,
        audio_mode=stream.audioMode,
        bit_depth=stream.bitDepth,
        sample_rate=stream.sampleRate,
        expires_at=time.time() + PLAYER_SESSION_TTL,
        transcoded=transcoded,
        local_path=local_path,
    )
    lyrics = None
    try:
        lyric_data = api.get_track_lyrics(track_id)
        lyrics = {"text": lyric_data.lyrics, "subtitles": lyric_data.subtitles, "rtl": lyric_data.isRightToLeft}
    except Exception as exc:
        log.debug("Failed to load lyrics for track %s: %s", track_id, exc)
    return session, player_track(track), lyrics, (False if no_images else cover_is_bright(player_track(track)["cover"]))


def download_command(
    request: DownloadRequest,
    url: str,
    options: ResourceDownloadOptions | None = None,
    singles: bool = False,
) -> list[str]:
    options = options or ResourceDownloadOptions(
        track_quality=request.track_quality,
        video_quality=request.video_quality,
        videos=request.videos,
        atmos=request.atmos,
    )
    command = cli_command(
        "download",
        "--track-quality", options.track_quality,
        "--video-quality", options.video_quality,
        "--videos", options.videos,
        "--dolby-atmos", options.atmos,
        "--threads-count", str(request.threads),
    )
    if url.startswith("artist/"):
        command.extend(["--singles", "only" if singles else "none"])
    if not request.skip_existing:
        command.append("--no-skip")
    if request.download_path.strip():
        command.extend(["--path", str(Path(request.download_path).expanduser().resolve())])
    if request.output_template.strip():
        command.extend(["--output", request.output_template.strip()])
    command.extend(["url", url])
    return command


def _static_version() -> str:
    """Cache-busting version derived once from static file mtimes."""
    if not hasattr(_static_version, "cache"):
        mtimes = [path.stat().st_mtime for path in STATIC_DIR.iterdir() if path.is_file()]
        _static_version.cache = str(int(max(mtimes, default=0)))
    return _static_version.cache


def page_response(name: str) -> HTMLResponse:
    html = (STATIC_DIR / name).read_text(encoding="utf-8")
    version = _static_version()
    html = re.sub(r'(src|href)="(/static/[^"]+)"', rf'\1="\2?v={version}"', html)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/")
async def index() -> HTMLResponse:
    return page_response("spa.html")


@app.get("/downloads")
async def downloads_page() -> HTMLResponse:
    return page_response("spa.html")


@app.get("/admin")
async def admin_page() -> HTMLResponse:
    return page_response("admin.html")


@app.get("/player")
async def player_page() -> HTMLResponse:
    return page_response("spa.html")


@app.get("/giveaway")
async def giveaway_page() -> HTMLResponse:
    return page_response("giveaway.html")


class GiveawayClaimRequest(BaseModel):
    fp: str = Field(min_length=40, max_length=64, description="Browser fingerprint hash")


@app.get("/api/giveaway/status")
async def giveaway_status(fp: str = Query(min_length=40, max_length=64)) -> dict:
    """查询某浏览器指纹的领取状态(不泄露密码)。"""
    return get_giveaway().status(fp)


@app.post("/api/giveaway/claim")
async def giveaway_claim(request: GiveawayClaimRequest) -> dict:
    """领取一个赠送账号;已领取则不再给密码。"""
    return get_giveaway().claim(request.fp)


@app.get("/manifest.webmanifest")
async def webmanifest() -> JSONResponse:
    return JSONResponse({
        "name": "Abducted Tidal Player",
        "short_name": "ATP",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#0b0c0e",
        "theme_color": "#0b0c0e",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
            {"src": "/static/icon.svg", "sizes": "any", "type": "image/svg+xml"},
        ],
    })


def _read_proc_line(path: str, key: str) -> int | None:
    try:
        for line in Path(path).read_text().splitlines():
            if line.startswith(key + ":"):
                return int(line.split(":", 1)[1].split()[0])
    except (FileNotFoundError, ValueError, IndexError):
        pass
    return None


CPU_SAMPLE_INTERVAL_S = 0.25  # CPU 采样间隔(两次 /proc/stat 读取间等待)


def system_stats() -> dict:
    """轻量系统状态采集(Linux /proc)。"""
    mem_total = _read_proc_line("/proc/meminfo", "MemTotal")
    mem_avail = _read_proc_line("/proc/meminfo", "MemAvailable")
    uptime_s = None
    try:
        uptime_s = float(Path("/proc/uptime").read_text().split()[0])
    except (FileNotFoundError, ValueError, IndexError):
        pass
    # CPU: 采样两次 /proc/stat 的 idle/total
    def _cpu():
        try:
            fields = Path("/proc/stat").read_text().splitlines()[0].split()[1:]
            idle = sum(int(v) for v in fields[3:])
            total = sum(int(v) for v in fields)
            return idle, total
        except (FileNotFoundError, ValueError, IndexError):
            return None, None
    cpu_usage = None
    idle1, total1 = _cpu()
    if idle1 is not None:
        time.sleep(CPU_SAMPLE_INTERVAL_S)
        idle2, total2 = _cpu()
        if total2 and total2 > total1:
            cpu_usage = round(100.0 * (1 - (idle2 - idle1) / (total2 - total1)), 1)
    download_path = CONFIG.download.download_path
    disk_path = download_path
    while not disk_path.exists() and disk_path != disk_path.parent:
        disk_path = disk_path.parent
    try:
        disk = shutil.disk_usage(disk_path)
    except OSError:
        disk = None
    return {
        "cpu_percent": cpu_usage,
        "mem_total": mem_total,
        "mem_avail": mem_avail,
        "mem_used_percent": round(100.0 * (mem_total - mem_avail) / mem_total, 1) if mem_total and mem_avail else None,
        "uptime_s": round(uptime_s) if uptime_s else None,
        "disk_free": disk.free if disk else None,
        "disk_used": disk.used if disk else None,
        "python_version": platform.python_version(),
        "version": app_version(),
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "process_count": len(_list_processes()),
    }


def _list_processes() -> list[dict]:
    out = []
    for pid in sorted(_iter_pids()):
        cmdline = _read_cmdline(pid)
        if not cmdline:
            continue
        out.append({"pid": pid, "cmd": cmdline})
    return out


def _iter_pids():
    try:
        for p in Path("/proc").iterdir():
            if p.name.isdigit():
                yield int(p.name)
    except (FileNotFoundError, OSError):
        return


def _read_cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").strip()
        return raw.decode("utf-8", "replace")[:160]
    except (FileNotFoundError, OSError):
        return ""


@app.get("/api/status")
async def status(request: Request, user: User = Depends(get_current_user)) -> dict:
    accounts = [account_info(account_id) for account_id in account_ids()]
    enabled_accounts = [
        account
        for account in accounts
        if account["enabled"] and account["health_status"] != "unhealthy"
    ]
    download_path = CONFIG.download.download_path
    disk_path = download_path
    while not disk_path.exists() and disk_path != disk_path.parent:
        disk_path = disk_path.parent
    port = request.url.port or (443 if request.url.scheme == "https" else 80)
    username = user.username
    result = {
        "tidal_ready": bool(enabled_accounts),
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "download_path": str(download_path),
        "disk_free": shutil.disk_usage(disk_path).free,
        "python_version": platform.python_version(),
        "version": app_version(),
        "host": HOST,
        "port": port,
        "lan_urls": lan_addresses(port),
        "is_admin": user.is_admin,
        "username": username,
        # 下载配额(每用户 12h 窗口)
        "quota_limit": DOWNLOAD_QUOTA_BYTES,
        "quota_used": get_users().download_usage_bytes(username),
        "quota_remaining": get_users().download_remaining_bytes(username),
        "quota_window": DOWNLOAD_QUOTA_WINDOW,
    }
    # Tidal 账号池细节仅管理员可见,普通用户不暴露数量/国家/登录态
    if user.is_admin:
        result["authenticated"] = bool(enabled_accounts)
        result["country_code"] = enabled_accounts[0]["country_code"] if enabled_accounts else None
        result["account_count"] = len(accounts)
    return result


@app.post("/api/auth/login")
async def login(_admin: User = Depends(require_admin)) -> dict:
    active = next((job for job in jobs.values() if job.kind == "login" and job.status in {"queued", "running"}), None)
    if active:
        return active.public()
    account_id = uuid4().hex[:10]
    return create_job(
        "login",
        "Add Tidal account",
        cli_command("auth", "login", "--no-browser"),
        account_id=account_id,
        env={"TIDDL_AUTH_FILE": str(account_path(account_id))},
    ).public()


@app.post("/api/auth/logout")
async def logout(_admin: User = Depends(require_admin)) -> dict:
    available = account_ids()
    if not available:
        raise HTTPException(status_code=404, detail="No Tidal accounts are signed in.")
    account_id = available[0]
    return create_job(
        "logout",
        "Sign out",
        cli_command("auth", "logout", "--force"),
        account_id=account_id,
        env={"TIDDL_AUTH_FILE": str(account_path(account_id))},
    ).public()


@app.get("/api/accounts")
async def list_accounts(_admin: User = Depends(require_admin)) -> dict:
    return {"accounts": [account_info(account_id) for account_id in account_ids()]}


@app.post("/api/accounts/{account_id}/check-subscription")
async def check_subscription(account_id: str, _admin: User = Depends(require_admin)) -> dict:
    """手动触发单账号订阅检测(节流由调用者控制)。"""
    if account_id not in account_ids():
        raise HTTPException(status_code=404, detail="Account not found")
    await check_account_subscription(account_id)
    return account_info(account_id)


@app.get("/api/admin/monitor")
async def admin_monitor(_admin: User = Depends(require_admin)) -> dict:
    """实时监控总览:账号池(健康/订阅/负载) + 请求统计 + 系统状态 + 运行路由 + 实时带宽。"""
    accounts = [account_info(account_id) for account_id in account_ids()]
    jobs_snapshot = [
        {"id": job.id, "kind": job.kind, "status": job.status, "label": job.label, "account_id": job.account_id}
        for job in jobs.values()
    ]
    # 实时播放带宽:活跃代理会话的当前速率(字节/秒),按用户聚合
    live = live_session_rates()
    live_sessions = [
        {
            "id": sid,
            "username": player_sessions[sid].username,
            "rate": round(rate),
        }
        for sid, rate in live.items()
        if sid in player_sessions
    ]
    live_by_user: dict[str, float] = {}
    for item in live_sessions:
        if item["username"]:
            live_by_user[item["username"]] = live_by_user.get(item["username"], 0.0) + item["rate"]
    # 下载任务实时速率(CLI 上报的 speed,字节/秒)
    download_speed = 0.0
    for job in jobs.values():
        if job.kind == "download" and job.status == "running":
            download_speed += float(job.speed or 0)
    return {
        "accounts": accounts,
        "request_stats": {
            path: {**stats, "avg_ms": round(stats["total_ms"] / stats["hits"], 1) if stats["hits"] else 0.0}
            for path, stats in sorted(request_stats.items())
        },
        "system": await asyncio.to_thread(system_stats),
        "jobs": jobs_snapshot,
        "routes": [route.path for route in app.routes if getattr(route, "path", "").startswith("/api/")],
        "live": {
            "sessions": live_sessions,
            "by_user": {k: round(v) for k, v in live_by_user.items()},
            "play_bps": round(sum(live_by_user.values())),
            "download_bps": round(download_speed),
            "total_bps": round(sum(live_by_user.values()) + download_speed),
        },
    }


class BandwidthSettingsRequest(BaseModel):
    enabled: bool | None = None
    cap_mbps: int | None = Field(default=None, ge=1, le=10000)


@app.get("/api/admin/bandwidth")
async def admin_bandwidth(_admin: User = Depends(require_admin)) -> dict:
    """限流/带宽管理:当前配置 + 实时调度快照 + 各账号流量一览。"""
    config = load_config()
    snapshot = bandwidth_snapshot()
    store = get_users()
    users = [
        {
            "username": u.username,
            "traffic": store.traffic_summary(u.username),
        }
        for u in store.list()
    ]
    return {
        "enabled": config.enabled,
        "cap_mbps": config.cap_mbps,
        "cap_bytes_per_sec": config.cap_bytes_per_sec,
        "active_users": snapshot["active_users"],
        "jobs": snapshot["jobs"],
        "per_user": snapshot["per_user"],
        "state_file": snapshot["state_file"],
        "users": users,
    }


@app.patch("/api/admin/bandwidth")
async def update_bandwidth(request: BandwidthSettingsRequest, _admin: User = Depends(require_admin)) -> dict:
    """更新限流配置(开关/总带宽上限 Mbps)。"""
    config = load_config()
    if request.enabled is not None:
        config.enabled = request.enabled
    if request.cap_mbps is not None:
        config.cap_mbps = request.cap_mbps
    save_config(config)
    return {"enabled": config.enabled, "cap_mbps": config.cap_mbps}


@app.patch("/api/accounts/{account_id}")
async def update_account(account_id: str, enabled: bool, _admin: User = Depends(require_admin)) -> dict:
    if account_id not in account_ids():
        raise HTTPException(status_code=404, detail="Account not found")
    settings = load_account_settings()
    settings[account_id] = enabled
    save_account_settings(settings)
    if enabled:
        await check_account_health(account_id)
    return account_info(account_id)


@app.post("/api/accounts/{account_id}/health")
async def refresh_account_health(account_id: str, _admin: User = Depends(require_admin)) -> dict:
    if account_id not in account_ids():
        raise HTTPException(status_code=404, detail="Account not found")
    await check_account_health(account_id)
    return account_info(account_id)


@app.post("/api/accounts/{account_id}/logout")
async def logout_account(account_id: str, _admin: User = Depends(require_admin)) -> dict:
    if account_id not in account_ids():
        raise HTTPException(status_code=404, detail="Account not found")
    return create_job(
        "logout",
        f"Sign out {account_id}",
        cli_command("auth", "logout", "--force"),
        account_id=account_id,
        env={"TIDDL_AUTH_FILE": str(account_path(account_id))},
    ).public()


@app.post("/api/downloads")
async def download(request: DownloadRequest, user: User = Depends(get_current_user)) -> dict:
    created = []
    # 下载配额:每 12 小时 2GB,超限拒绝新任务(配额检查优先于账号检查)
    store = get_users()
    remaining = store.download_remaining_bytes(user.username)
    if remaining <= 0:
        raise HTTPException(status_code=429, detail="Download quota reached. Try again in a few hours.")
    available = available_account_ids()
    if not available:
        raise HTTPException(status_code=401, detail="Add and enable at least one Tidal account.")
    store.record_downloads(user.username, len(request.urls))
    loads = {account_id: account_loads(account_id)[0] for account_id in available}
    for index, url in enumerate(request.urls):
        resource = TidalResource.from_string(url)
        options = request.resource_options[index] if index < len(request.resource_options) else None
        metadata = request.resource_metadata[index] if index < len(request.resource_metadata) else ResourceMetadata()
        account_id = select_account(loads)
        loads[account_id] += 1
        job = create_job(
            "download",
            metadata.title or str(resource),
            download_command(request, url, options, singles=metadata.singles and resource.type == "artist"),
            account_id=account_id,
            env={"TIDDL_AUTH_FILE": str(account_path(account_id))},
            subtitle=metadata.subtitle,
            cover=metadata.cover,
            resource_type=metadata.type or resource.type,
            username=user.username,
        )
        created.append(job.public())
    return {"jobs": created, "count": len(created)}


@app.get("/api/download/browser/{track_id}")
async def browser_download(track_id: str, quality: str = "high", atmos: Literal["none", "allow", "only"] = "allow", user: User = Depends(get_current_user)):
    """浏览器直连下载单曲:服务器只实时解析 Tidal 流并转发字节,不落盘。

    点击绿色按钮 → 浏览器直接保存到本地 Downloads。Atmos 不转码,按 CLI 相同方式
    取原始流(现代播放器均可播放 Atmos FLAC)。加密/DRM 流返回 4xx,前端回退服务器任务。
    atmos=none 跳过 Atmos 曲目;only 只下 Atmos;allow(默认)两者皆可。
    """
    store = get_users()
    if store.download_remaining_bytes(user.username) <= 0:
        raise HTTPException(status_code=429, detail="Download quota reached. Try again in a few hours.")
    available = available_account_ids()
    if not available:
        raise HTTPException(status_code=401, detail="Add and enable at least one Tidal account.")
    account_id = select_account()
    store.record_downloads(user.username, 1)
    try:
        api = account_context(account_id).api
        track = api.get_track(track_id)
        stream = api.get_track_stream(track_id, track_qualities.get(quality, "HIGH"))
        urls, ext = parse_track_stream(stream)
        if not urls:
            raise ValueError("No stream URLs returned.")
        # Atmos 过滤:与 CLI 的 --dolby-atmos 语义一致
        if stream.audioMode == "DOLBY_ATMOS" and atmos == "none":
            raise HTTPException(status_code=422, detail="This track is Dolby Atmos and Atmos is disabled in download settings.")
        if stream.audioMode != "DOLBY_ATMOS" and atmos == "only":
            raise HTTPException(status_code=422, detail="This track is not Dolby Atmos and Atmos-only download is enabled.")
        # 加密/DRM 流浏览器无法保存明文文件 → 让前端回退服务器任务
        try:
            manifest = json.loads(b64decode(stream.manifest).decode("utf-8"))
            if is_protected_stream(manifest):
                raise HTTPException(status_code=422, detail="This track is DRM-protected and cannot be saved via the browser.")
        except HTTPException:
            raise
        except Exception:
            pass
    except HTTPException:
        raise
    except Exception as exc:
        if is_authentication_error(exc):
            asyncio.create_task(check_account_health(account_id))
        raise HTTPException(status_code=502, detail=f"Unable to open stream: {exc}") from exc

    url = urls[0]
    parsed_url = urlparse(url)
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        raise HTTPException(status_code=502, detail="Tidal returned an invalid stream URL.")
    safe_title = re.sub(r'[\\/:*?"<>|\s]+', "_", track.title).strip("_") or f"track_{track_id}"
    filename = f"{safe_title}{ext}"
    client = _get_proxy_session()
    try:
        upstream = await client.get(url, allow_redirects=True)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to reach the Tidal stream: {exc}") from exc
    if upstream.status not in {200, 206}:
        status = upstream.status
        upstream.release()
        raise HTTPException(status_code=502, detail=f"Tidal stream returned HTTP {status}.")

    total = 0

    async def body():
        nonlocal total
        try:
            async for chunk in upstream.content.iter_chunked(64 * 1024):
                total += len(chunk)
                yield chunk
        finally:
            upstream.release()
            if total > 0:
                try:
                    store.record_download_bytes(user.username, total)
                    store.record_traffic(user.username, TRAFFIC_KIND_DOWNLOAD, total)
                except Exception:
                    pass

    return StreamingResponse(
        body(),
        status_code=upstream.status,
        media_type="audio/flac" if ext == ".flac" else "audio/mp4",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/telemetry")
async def telemetry(request: Request, user: User = Depends(get_current_user)) -> dict:
    """接收前端遥测并写入服务器日志,用于排查播放/交互问题。

    任意登录账号启用;限流避免单个账号刷日志。
    同时落盘到 telemetry.log 便于直接拉取分析。
    """
    # 全量启用后加限流:同一用户 10 秒内只接受一批(前端已按 30 条/5s 批量,不影响采集)
    if telemetry_throttled(user.username):
        return {"ok": True, "throttled": True}
    body = await request.body()
    if len(body) > 128 * 1024:
        raise HTTPException(status_code=413, detail="Telemetry payload too large.")
    try:
        data = json.loads(body)
    except Exception:
        data = {"raw": body[:500].decode("utf-8", "replace")}
    line = f"TELEMETRY[{user.username}] {json.dumps(data, ensure_ascii=False)[:6000]}"
    # 直接写 stderr(systemd/journalctl 捕获),避免 root logger INFO 级别被丢弃
    print(line, flush=True)
    _write_telemetry(line)
    return {"ok": True}


@app.post("/api/preview")
async def preview(request: PreviewRequest, _user: User = Depends(get_current_user)) -> dict:
    if not available_account_ids():
        raise HTTPException(status_code=401, detail="Sign in to preview Tidal resources.")
    try:
        resources = await asyncio.to_thread(build_preview, request.urls)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to load preview: {exc}") from exc
    return {"resources": resources}


@app.get("/api/search")
async def search(query: str = Query(min_length=2, max_length=100), _user: User = Depends(get_current_user)) -> dict:
    if not available_account_ids():
        raise HTTPException(status_code=401, detail="Sign in to search Tidal.")
    try:
        results = await asyncio.to_thread(search_catalog, query)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to search Tidal: {exc}") from exc
    return {"results": results}


@app.post("/api/player/resource")
async def add_player_resource(request: PlayerResourceRequest, _user: User = Depends(get_current_user)) -> dict:
    if not available_account_ids():
        raise HTTPException(status_code=401, detail="Sign in to play Tidal.")
    try:
        tracks = await asyncio.to_thread(player_resource, request.resource)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to load tracks: {exc}") from exc
    return {"tracks": tracks}


class MobileResolveRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=100)
    track_quality: Literal["low", "normal", "high", "max"] = "high"


# v1 质量档:移动端原生(ExoPlayer/media_kit)可解 eac3/flac/aac,无需 v2/DRM/license。
# 单文件 BTS 流,URL 原生直连(无 CORS),零服务器带宽。
_MOBILE_QUALITY_MAP = {
    "low": "LOW",
    "normal": "HIGH",
    "high": "LOSSLESS",   # 移动端优先无损 FLAC(单文件)
    "max": "HI_RES_LOSSLESS",
}


def _resolve_track_for_mobile(track_id: str, account_id: str, quality: str) -> dict:
    """Resolve a single track to its v1 plaintext stream URL (native-friendly)."""
    api = account_context(account_id).api
    track = api.get_track(track_id)
    if not track.allowStreaming or not track.streamReady:
        raise ValueError("This track is not available for streaming.")
    quality_v1 = _MOBILE_QUALITY_MAP.get(quality, "LOSSLESS")
    stream = None
    last_error: Exception | None = None
    # 尝试目标质量;Atmos-only 曲目 v1 只给 eac3(明文),原生 media_kit 可解。
    for candidate in [quality_v1, "HIGH", "LOW"]:
        try:
            candidate_stream = api.get_track_stream(track_id, candidate)
            urls, extension = parse_track_stream(candidate_stream)
            if not urls:
                raise ValueError("Empty stream URL")
            stream = candidate_stream
            break
        except Exception as exc:
            last_error = exc
    if stream is None:
        raise last_error or ValueError("No playable stream for track.")
    urls, extension = parse_track_stream(stream)
    if extension == ".flac":
        codec = "flac"
    elif stream.audioMode == "DOLBY_ATMOS":
        codec = "eac3"  # Atmos-only:v1 明文 E-AC3,原生 media_kit 可解
    else:
        codec = "aac"
    return {
        "track_id": str(track_id),
        "title": track.title,
        "artist": ", ".join(a.name for a in track.artists),
        "album": track.album.title,
        "album_id": str(track.album.id),
        "cover": image_url(track.album.cover, 640),
        "duration": track.duration,
        "codec": codec,
        "audio_mode": stream.audioMode,
        "mime_type": ("audio/flac" if extension == ".flac" else "audio/mp4"),
        "extension": extension,
        "quality": stream.audioQuality,
        "url": urls[0],
    }


class MobileStreamRequest(BaseModel):
    track_id: str
    track_quality: Literal["low", "normal", "high", "max"] = "high"


@app.post("/api/mobile/stream")
async def mobile_stream(request: MobileStreamRequest, _user: User = Depends(get_current_user)) -> dict:
    """移动端单曲按需解析:返回该曲目的 v1 明文流 URL(FLAC/AAC/eac3)。
    App 在播放/下载某首时才调用(一次 Tidal 请求),避免批量解析触发限流。
    返回的 url 是单文件,App 用 dio/ExoPlayer 直接播放或下载。
    """
    if not available_account_ids():
        raise HTTPException(status_code=401, detail="Sign in to play Tidal.")
    if not re.fullmatch(r"\d+", request.track_id):
        raise HTTPException(status_code=400, detail="Invalid track id.")
    account_id = select_account()
    try:
        return await asyncio.to_thread(_resolve_track_for_mobile, request.track_id, account_id, request.track_quality)
    except Exception as exc:
        log.debug("Mobile stream resolve failed for %s: %s", request.track_id, exc)
        raise HTTPException(status_code=502, detail=f"Unable to resolve track: {exc}")


@app.get("/api/mobile/lyrics/{track_id}")
async def mobile_lyrics(track_id: str, _user: User = Depends(get_current_user)) -> dict:
    """移动端歌词:返回该曲的歌词/字幕(带时间轴)。无歌词时返回空。"""
    if not re.fullmatch(r"\d+", track_id):
        raise HTTPException(status_code=400, detail="Invalid track id.")
    if not available_account_ids():
        raise HTTPException(status_code=401, detail="Sign in to play Tidal.")
    try:
        account_id = select_account()
        api = account_context(account_id).api
        lyrics = await asyncio.to_thread(api.get_track_lyrics, int(track_id))
        return {
            "track_id": track_id,
            "lyrics": lyrics.lyrics,
            "subtitles": lyrics.subtitles,
            "rtl": lyrics.isRightToLeft,
        }
    except Exception as exc:
        log.debug("Mobile lyrics failed for %s: %s", track_id, exc)
        return {"track_id": track_id, "lyrics": "", "subtitles": "", "rtl": False}


# 单次批量解析上限:专辑/歌单曲目过多时截断,避免一次性大量请求触发 Tidal 限流。
# App 应优先用 /api/mobile/stream 按需逐首解析。
MOBILE_RESOLVE_LIMIT = 30


@app.post("/api/mobile/resolve")
async def mobile_resolve(request: MobileResolveRequest, user: User = Depends(get_current_user)) -> dict:
    """移动端解析:资源(单曲/专辑/歌单/艺人/mix)→ 每首曲目的 v1 明文流 URL(原生直连,零服务器带宽)。
    返回的 url 是单文件(FLAC/AAC/eac3),App 用 dio/ExoPlayer 直接播放或下载。
    """
    if not available_account_ids():
        raise HTTPException(status_code=401, detail="Sign in to play Tidal.")
    get_users().record_downloads(user.username, len(request.urls))
    account_id = select_account()
    api = account_context(account_id).api
    result: list[dict] = []
    for url in request.urls:
        resource = TidalResource.from_string(url)
        track_ids: list[str] = []
        album_artists: list[dict] = []
        if resource.type == "track":
            track_ids = [resource.id]
        elif resource.type == "album":
            album = api.get_album(resource.id)
            album_artists = _artist_dicts(album, prefer_singular=True)
            collection = api.get_album_items(resource.id, limit=100)
            track_ids = [str(entry.item.id) for entry in collection.items if entry.type == "track"]
        elif resource.type == "playlist":
            collection = api.get_playlist_items(resource.id, limit=100)
            track_ids = [str(entry.item.id) for entry in collection.items if entry.type == "track"]
        elif resource.type == "mix":
            collection = api.get_mix_items(resource.id, limit=100)
            track_ids = [str(entry.item.id) for entry in collection.items if entry.type == "track"]
        elif resource.type == "artist":
            # 艺人:取其专辑(含 EP/单曲)的曲目,最多 10 张专辑避免请求过多。
            album_ids: list[str] = []
            for filt in ("ALBUMS", "EPSANDSINGLES"):
                albums = api.get_artist_albums(resource.id, limit=100, filter=filt)
                album_ids += [str(a.id) for a in albums.items]
                if len(album_ids) >= 10:
                    break
            for album_id in album_ids[:10]:
                try:
                    album = api.get_album(album_id)
                    coll = api.get_album_items(album_id, limit=100)
                    album_artists = _artist_dicts(album, prefer_singular=True)
                    for entry in coll.items:
                        if entry.type == "track":
                            track_ids.append(str(entry.item.id))
                except Exception as exc:
                    log.debug("Artist album %s failed: %s", album_id, exc)
        else:
            raise HTTPException(status_code=400, detail=f"Mobile does not support resource type: {resource.type}")
        # 截断:避免歌单/艺人曲目过多时一次性大量请求触发限流
        if len(result) + len(track_ids) > MOBILE_RESOLVE_LIMIT:
            track_ids = track_ids[: max(0, MOBILE_RESOLVE_LIMIT - len(result))]
            if not track_ids:
                break
        for track_id in track_ids:
            try:
                entry = _resolve_track_for_mobile(str(track_id), account_id, request.track_quality)
                if album_artists:
                    entry["artists"] = album_artists
                result.append(entry)
            except Exception as exc:
                log.debug("Mobile resolve failed for track %s: %s", track_id, exc)
    if not result:
        raise HTTPException(status_code=502, detail="Unable to resolve any playable stream.")
    return {"tracks": result, "count": len(result)}



@app.get("/api/player/artist/{artist_id}")
async def player_artist(artist_id: str, _user: User = Depends(get_current_user)) -> dict:
    if not available_account_ids():
        raise HTTPException(status_code=401, detail="Sign in to browse artists.")
    if not re.fullmatch(r"\d+", artist_id):
        raise HTTPException(status_code=404, detail="Artist not found")

    def load() -> dict:
        api = account_context().api
        artist = api.get_artist(artist_id)

        def entries(collection: object) -> list[dict]:
            def album_artists(album) -> list[dict]:
                # 专辑单数优先:作曲厂牌(HOYO-MIX)主艺人在单数字段,复数里可能是演唱者
                return _artist_dicts(album, prefer_singular=True)

            def artist_label(album) -> str:
                return ", ".join(name["name"] for name in album_artists(album))

            return [
                {
                    "id": str(album.id),
                    "title": album.title,
                    "artist": artist_label(album),
                    "artist_id": album_artists(album)[0]["id"] if album_artists(album) else "",
                    "artists": album_artists(album),
                    "year": str(album.releaseDate.year) if getattr(album, "releaseDate", None) else "",
                    "duration": album.duration,
                    "track_count": getattr(album, "numberOfTracks", 0),
                    "cover": image_url(album.cover, 320),
                }
                for album in collection.items
            ]

        albums = api.get_artist_albums(artist_id, limit=100, filter="ALBUMS")
        singles = api.get_artist_albums(artist_id, limit=100, filter="EPSANDSINGLES")
        # 艺人参与的曲目(含作为演唱者/合作艺人参与的作品,如 HOYO-MiX 专辑里的 Mika Kobayashi)
        try:
            top_tracks = api.get_artist_top_tracks(artist_id, limit=100)
            tracks = [player_track(track) for track in top_tracks.items]
        except Exception as exc:
            log.debug("Failed to load artist top tracks for %s: %s", artist_id, exc)
            tracks = []
        return {
            "id": str(artist_id),
            "name": artist.name,
            "picture": image_url(artist.picture, 320),
            "albums": entries(albums),
            "singles": entries(singles),
            "tracks": tracks,
        }

    try:
        return await asyncio.to_thread(load)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to load artist: {exc}") from exc


@app.get("/api/player/search-artists")
async def search_artists(query: str = Query(min_length=2, max_length=100), _user: User = Depends(get_current_user)) -> dict:
    if not available_account_ids():
        raise HTTPException(status_code=401, detail="Sign in to search artists.")

    def load() -> list[dict]:
        results = account_context().api.get_search(query=query)
        return [
            {
                "id": str(artist.id),
                "name": artist.name,
                "picture": image_url(artist.picture, 320) if artist.picture else None,
            }
            for artist in results.artists.items[:10]
        ]

    try:
        return {"artists": await asyncio.to_thread(load)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to search artists: {exc}") from exc


@app.post("/api/player/drm-resolve")
@app.post("/api/player/drm-license")
async def drm_license(request: Request, _user: User = Depends(get_current_user)) -> Response:
    """D1 license 代理:接收浏览器 EME 生成的 Widevine challenge(二进制),
    用生成该流 manifest 的同一个账号 Bearer token 转发给 Tidal license 服务器,
    返回 license 给浏览器解密。音频字节仍由浏览器直连 CDN(零带宽);
    这里只转发 ~1.7KB 的 challenge/license。
    """
    challenge = await request.body()
    # 诊断:记录 challenge 长度与头字节(手机 CDM 可能产出 2 字节错误状态,如 08 04)。
    # 不再硬性拒绝 <16 字节,而是转发给 Tidal 看真实上游响应,以区分 CDM 问题 vs Tidal 拒绝。
    print(f"DRM-LICENSE challenge_len={len(challenge)} head={challenge[:8].hex()}", flush=True)
    if not challenge:
        raise HTTPException(status_code=400, detail="Empty Widevine challenge.")
    # 必须用与 resolve 时生成 manifest 相同的账号换 license,否则 Tidal 拒绝。
    # 前端把 resolve 返回的 drm.account_id 随请求带回;缺失或无效时(旧客户端)才回退选号。
    account_id = request.query_params.get("account_id")
    if not account_id or account_id not in available_account_ids():
        account_id = select_account()

    def _proxy() -> tuple[int, bytes]:
        api = account_context(account_id).api
        token = api.client.token
        headers = {
            "Content-Type": "application/octet-stream",
            "Accept": "*/*",
            "Origin": "https://tidal.com",
            "Referer": "https://tidal.com/",
            "User-Agent": DRM_UA,
            "Authorization": f"Bearer {token}",
        }
        resp = _tidal_post(
            "https://api.tidal.com/v2/widevine",
            data=challenge,
            headers=headers,
            timeout=60,
        )
        return resp.status_code, resp.content

    status, license_bytes = await asyncio.to_thread(_proxy)
    if status != 200:
        if status in (401, 403):
            asyncio.create_task(check_account_health(account_id))
        raise HTTPException(status_code=502, detail=f"Tidal license request failed (HTTP {status}).")
    return Response(content=license_bytes, media_type="application/octet-stream")


@app.post("/api/player/resolve")
async def resolve_player(request: PlayerResolveRequest, user: User = Depends(get_current_user), ua: str | None = Header(default=None)) -> dict:
    account_id = select_account()
    get_users().record_play(user.username)
    # v2 DRM(DASH+Widevine,MSE 播放)优先:浏览器支持 EME 时走 v2,seek 流畅、零服务器带宽。
    # 失败(曲目/账号/manifest 异常)自动回退 v1 BTS 单文件流。
    # aac_only:客户端显式要求,或 UA 表明浏览器无法解码 FLAC-in-MSE(Firefox/Safari)时
    # 强制降级 AAC-LC,避免 FLAC bundle 下发后在 MSE append / EME 阶段失败。
    aac_only = request.aac_only or browser_prefers_aac(ua)
    if request.drm:
        try:
            api = account_context(account_id).api
            track = api.get_track(request.track_id)
            if not track.allowStreaming or not track.streamReady:
                raise ValueError("This track is not available for streaming.")
            # v2 格式按音质选择:HI_RES_LOSSLESS 请求 FLAC_HIRES(真 Hi-Res,如 192k/24),
            # LOSSLESS 请求 FLAC,AAC 走 AACLC/HEAACV1;按 v2_formats_for_quality 的降级链自动回退。
            bundle = await asyncio.to_thread(
                v2_drm_manifest, request.track_id, account_id, v2_formats_for_quality(request.quality, aac_only=aac_only)
            )
            lyrics = None
            try:
                lyric_data = api.get_track_lyrics(request.track_id)
                lyrics = {"text": lyric_data.lyrics, "subtitles": lyric_data.subtitles, "rtl": lyric_data.isRightToLeft}
            except Exception as exc:
                log.debug("Failed to load lyrics for track %s: %s", request.track_id, exc)
            t = player_track(track)
            # 按实际返回的 format 反推展示音质(前端据此显示档位)
            fmt = bundle.get("format") or ""
            if fmt == "FLAC_HIRES":
                resolved_quality = "HI_RES_LOSSLESS"
            elif fmt == "FLAC":
                resolved_quality = "LOSSLESS"
            elif fmt == "HEAACV1":
                resolved_quality = "LOW"
            else:
                resolved_quality = "HIGH"
            return {
                "session_id": None,
                "stream_url": None,
                "direct_url": None,
                "mime_type": bundle["mime_type"],
                "codec": bundle["codec"],
                "requested_quality": request.quality,
                "quality": resolved_quality,
                "audio_mode": "DOLBY_ATMOS" if request.allow_atmos else "STEREO",
                "bit_depth": bundle.get("bit_depth"),
                "sample_rate": bundle.get("sample_rate"),
                "bitrate": StreamSpec.for_quality(
                    resolved_quality,
                    "DOLBY_ATMOS" if request.allow_atmos else "STEREO",
                    bundle.get("codec", ""),
                    bundle.get("mime_type", ""),
                ).bitrate_kbps,
                "transcoded": False,
                "cover_bright": (False if request.no_images else await asyncio.to_thread(cover_is_bright, t["cover"])),
                "track": t,
                "lyrics": lyrics,
                "drm": {**{k: bundle[k] for k in ("pssh", "kid", "init_url", "media_url", "media_template", "segment_count", "codec", "mime_type", "duration_s", "sample_rate", "bit_depth", "format")}, "account_id": account_id},            }
        except Exception as exc:
            if is_authentication_error(exc):
                asyncio.create_task(check_account_health(account_id))
            log.debug("v2 resolve failed for %s, falling back to v1: %s", request.track_id, exc)
    try:
        session, track, lyrics, cover_bright = await asyncio.to_thread(
            resolve_player_stream, request.track_id, request.quality, account_id, request.allow_atmos, request.no_images, aac_only
        )
    except Exception as exc:
        if is_authentication_error(exc):
            asyncio.create_task(check_account_health(account_id))
        raise HTTPException(status_code=502, detail=f"Unable to open stream: {exc}") from exc
    session.username = user.username
    now = time.time()
    for session_id in [key for key, value in player_sessions.items() if value.expires_at <= now]:
        player_sessions.pop(session_id, None)
    # 直连优先:非 DRM、非 Atmos、未转码的普通立体声流,直接给浏览器原始 CDN URL,
    # 音频字节不经过服务器(零带宽);Atmos/转码/不确定情况仍走后端代理兜底。
    can_direct = (
        not session.transcoded
        and session.audio_mode == "STEREO"
        and session.mime_type in {"audio/mp4", "audio/flac"}
        and session.local_path is None
        and session.url
    )
    base = {
        "session_id": session.id,
        "stream_url": f"/api/player/stream/{session.id}" if session.url else None,
        "direct_url": session.url if can_direct else None,
        "mime_type": session.mime_type,
        "codec": session.codec,
        "requested_quality": request.quality,
        "quality": session.quality,
        "audio_mode": session.audio_mode,
        "bit_depth": session.bit_depth,
        "sample_rate": session.sample_rate,
        "bitrate": StreamSpec.for_quality(
            session.quality, session.audio_mode, session.codec, session.mime_type
        ).bitrate_kbps,
        "transcoded": session.transcoded,
        "cover_bright": cover_bright,
        "track": track,
        "lyrics": lyrics,
    }
    # Atmos-only 曲目:v2 AAC-LC DASH 直连(浏览器 MSE 播放,零带宽),会话仅用于音质/信息展示
    if session.drm:
        base["drm"] = {k: session.drm[k] for k in ("pssh", "kid", "init_url", "media_url", "media_template", "segment_count", "codec", "mime_type", "duration_s", "sample_rate")}
        base["audio_mode"] = "DOLBY_ATMOS" if request.allow_atmos else "STEREO"
        return base
    if session.url:
        player_sessions[session.id] = session
    return base


def record_session_traffic(session: PlayerSession) -> None:
    """把播放会话本次新传输的字节记入发起用户的流量(防 Range 重复记账)。"""
    if not session.username:
        return
    delta = session.bytes - session.traffic_recorded
    if delta <= 0:
        return
    session.traffic_recorded = session.bytes
    try:
        get_users().record_traffic(session.username, TRAFFIC_KIND_PLAY, delta)
    except Exception as exc:
        log.debug("Failed to record play traffic for %s: %s", session.username, exc)


# 实时会话速率跟踪:记录每个播放会话上次采样的字节数与时间,
# 供 admin monitor 计算"此刻"的带宽(而非会话结束后的累计值)。
_session_rate_samples: dict[str, tuple[float, int]] = {}


def live_session_rates() -> dict[str, float]:
    """返回 {session_id: bytes_per_sec}。基于字节增量/时间差,双采样窗口。"""
    now = time.time()
    rates: dict[str, float] = {}
    expired = []
    for sid, session in list(player_sessions.items()):
        if session.expires_at <= now:
            expired.append(sid)
            continue
        prev = _session_rate_samples.get(sid)
        if prev is None:
            _session_rate_samples[sid] = (now, session.bytes)
            continue
        prev_t, prev_b = prev
        dt = now - prev_t
        if dt >= 1.0:
            rates[sid] = max(0.0, (session.bytes - prev_b) / dt)
            _session_rate_samples[sid] = (now, session.bytes)
    for sid in expired + [k for k in _session_rate_samples if k not in player_sessions]:
        _session_rate_samples.pop(sid, None)
    return rates


# 代理流共享的 aiohttp 会话:seek 的每个 Range 请求复用同一连接池,
# 避免每次拖动进度条都重新 TCP+TLS 握手导致卡顿。
_proxy_http_session: aiohttp.ClientSession | None = None


def _get_proxy_session() -> aiohttp.ClientSession:
    global _proxy_http_session
    if _proxy_http_session is None or _proxy_http_session.closed:
        _proxy_http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=45),
            connector=aiohttp.TCPConnector(limit=64, enable_cleanup_closed=True, ttl_dns_cache=600),
        )
    return _proxy_http_session


@app.get("/api/player/stream/{session_id}")
async def proxy_player_stream(session_id: str, range_header: str | None = Header(default=None, alias="Range"), _user: User = Depends(get_current_user)):
    session = player_sessions.get(session_id)
    if not session or session.expires_at <= time.time():
        player_sessions.pop(session_id, None)
        raise HTTPException(status_code=410, detail="Playback session expired. Start the track again.")
    if session.transcoded and session.local_path:
        # Atmos 转码流:直接读本地转码文件,支持 Range(可拖动进度条)
        return await _serve_transcoded_file(session, range_header)
    headers = {"Range": range_header} if range_header else {}
    client = _get_proxy_session()
    try:
        upstream = await client.get(session.url, headers=headers, allow_redirects=True)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to reach the Tidal stream: {exc}") from exc
    if upstream.status not in {200, 206}:
        status = upstream.status
        upstream.release()
        raise HTTPException(status_code=502, detail=f"Tidal stream returned HTTP {status}.")

    async def body():
        try:
            async for chunk in upstream.content.iter_chunked(64 * 1024):
                session.bytes += len(chunk)
                yield chunk
        finally:
            upstream.release()
            record_session_traffic(session)

    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() in {"content-length", "content-range", "accept-ranges", "etag", "last-modified"}
    }
    response_headers.setdefault("Accept-Ranges", "bytes")
    return StreamingResponse(body(), status_code=upstream.status, media_type=session.mime_type, headers=response_headers)


async def _serve_transcoded_file(session: PlayerSession, range_header: str | None):
    path = Path(session.local_path or "")
    if not path.is_file():
        player_sessions.pop(session.id, None)
        raise HTTPException(status_code=410, detail="Transcoded stream file is no longer available. Start the track again.")
    size = path.stat().st_size

    def _range_bounds() -> tuple[int, int]:
        start, end = 0, size - 1
        if range_header and range_header.startswith("bytes="):
            spec = range_header[6:].split("-", 1)
            try:
                if spec[0]:
                    start = int(spec[0])
                if len(spec) > 1 and spec[1]:
                    end = min(int(spec[1]), size - 1)
            except ValueError:
                pass
            if start > end or start >= size:
                raise HTTPException(status_code=416, detail="Range not satisfiable", headers={"Content-Range": f"bytes */{size}"})
        return start, end

    start, end = _range_bounds()

    async def body():
        try:
            with path.open("rb") as fh:
                fh.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = fh.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    session.bytes += len(chunk)
                    yield chunk
        except OSError:
            pass
        finally:
            record_session_traffic(session)

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Range": f"bytes {start}-{end}/{size}",
        "Content-Length": str(end - start + 1),
    }
    status = 206 if range_header and range_header.startswith("bytes=") else 200
    return StreamingResponse(body(), status_code=status, media_type=session.mime_type, headers=headers)


@app.get("/api/player/speed/{session_id}")
async def player_speed(session_id: str, _user: User = Depends(get_current_user)) -> dict:
    session = player_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Playback session not found")
    return {"bytes": session.bytes, "expired": session.expires_at <= time.time()}


def job_public_for(job: Job, user: User) -> dict:
    """Return a job view; Tidal account_id is only exposed to admins."""
    data = job.public()
    if not user.is_admin:
        data["account_id"] = None
    return data


@app.get("/api/jobs")
async def list_jobs(user: User = Depends(get_current_user)) -> list[dict]:
    return [job_public_for(jobs[job_id], user) for job_id in job_order if job_id in jobs]


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str, user: User = Depends(get_current_user)) -> dict:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Task not found")
    return job_public_for(jobs[job_id], user)


@app.delete("/api/jobs/{job_id}")
async def cancel_job(job_id: str, _user: User = Depends(get_current_user)) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Task not found")
    if job.status not in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Task has already finished")
    job.status = "cancelled"
    if job.process and job.process.returncode is None:
        job.process.terminate()
    return job.public()


def _job_file_access(job: Job, user: User) -> None:
    """取回文件仅限任务所有者或管理员。"""
    if not user.is_admin and job.username != user.username:
        raise HTTPException(status_code=403, detail="Not your download task.")


@app.get("/api/jobs/{job_id}/files")
async def job_files(job_id: str, user: User = Depends(get_current_user)) -> dict:
    """列出该下载任务已完成的文件(供"下载到浏览器")。"""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Task not found")
    _job_file_access(job, user)
    files = []
    for path in job.downloaded_files or []:
        p = Path(path)
        if p.is_file():
            files.append({"name": p.name, "path": str(p), "size": p.stat().st_size})
    return {"files": files}


@app.get("/api/jobs/{job_id}/download")
async def job_download(job_id: str, user: User = Depends(get_current_user)) -> Response:
    """把该任务的已完成文件打包成 ZIP 下载到浏览器(单个任务一个压缩包)。

    服务器端下载的文件默认落在服务器磁盘,浏览器只提交任务看进度;
    此接口把结果取回浏览器,让文件真正进入用户本地 downloads。
    """
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Task not found")
    _job_file_access(job, user)
    files = [Path(p) for p in (job.downloaded_files or []) if Path(p).is_file()]
    if not files:
        raise HTTPException(status_code=404, detail="No downloaded files for this task.")

    buf = io.BytesIO()
    safe_label = re.sub(r"[^\w\u4e00-\u9fff\- ]+", "_", job.label or "download")[:80].strip() or "download"
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for p in files:
            # 归档内用文件名(避免重名冲突加序号)
            name = p.name
            n = 1
            while name in zf.namelist():
                stem, ext = p.stem, p.suffix
                name = f"{stem} ({n}){ext}"
                n += 1
            zf.write(p, arcname=name)
    data = buf.getvalue()
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_label}.zip"'},
    )


def main() -> None:
    uvicorn.run("tiddl.web.app:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
