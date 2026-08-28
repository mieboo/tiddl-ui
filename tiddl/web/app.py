from __future__ import annotations

import asyncio
from collections import deque
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from base64 import b64decode
import json
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

import aiohttp
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
import uvicorn

from tiddl.cli.config import APP_PATH, CONFIG
from tiddl.cli.ctx import ContextObject
from tiddl.cli.utils.auth.core import load_auth_data
from tiddl.cli.utils.auth.core import save_auth_data
from tiddl.cli.utils.resource import TidalResource
from tiddl.core.auth import AuthAPI
from tiddl.core.utils import parse_track_stream
from rich.console import Console


STATIC_DIR = Path(__file__).parent / "static"
ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
LOGIN_URL_RE = re.compile(r"https://[^\s'\"]+")
MAX_LOG_LINES = 500
HEALTH_CHECK_INTERVAL = 60
HEALTH_FAILURE_THRESHOLD = 3
PLAYER_SESSION_TTL = 20 * 60
ACCOUNTS_DIR = APP_PATH / "accounts"
ACCOUNT_SETTINGS_FILE = ACCOUNTS_DIR / "settings.json"
LEGACY_ACCOUNT_ID = "default"
HOST = os.environ.get("TIDDL_HOST", "127.0.0.1")
PORT = int(os.environ.get("TIDDL_PORT", "8765"))


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


class PlayerResourceRequest(BaseModel):
    resource: str

    @field_validator("resource")
    @classmethod
    def clean_resource(cls, value: str) -> str:
        cleaned = value.strip()
        if not re.fullmatch(r"(?:https?://(?:listen\.)?tidal\.com/)?(?:browse/)?(?:(?:track|album)/\d+|album/\d+/track/\d+)(?:\?.*)?", cleaned):
            raise ValueError("Player supports Tidal tracks and albums.")
        return cleaned


@dataclass
class AccountHealth:
    status: Literal["unknown", "checking", "healthy", "degraded", "unhealthy"] = "unknown"
    failures: int = 0
    checked_at: str | None = None
    error: str | None = None


@dataclass
class PlayerSession:
    id: str
    track_id: str
    account_id: str
    url: str
    mime_type: str
    codec: str
    quality: str
    audio_mode: str
    bit_depth: int | None
    sample_rate: int | None
    expires_at: float
    bytes: int = 0


@dataclass
class Job:
    id: str
    kind: Literal["download", "login", "logout"]
    label: str
    command: list[str]
    subtitle: str = ""
    cover: str | None = None
    resource_type: str = ""
    account_id: str | None = None
    env: dict[str, str] = field(default_factory=dict, repr=False)
    status: Literal["queued", "running", "completed", "failed", "cancelled"] = "queued"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None
    return_code: int | None = None
    login_url: str | None = None
    progress: float = 0
    downloaded: int = 0
    total: int | None = None
    speed: float = 0
    current_item: str | None = None
    segment: int | None = None
    segment_count: int | None = None
    resource_completed: int = 0
    resource_total: int = 0
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=MAX_LOG_LINES))
    process: asyncio.subprocess.Process | None = field(default=None, repr=False)

    def public(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "status": self.status,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "return_code": self.return_code,
            "login_url": self.login_url,
            "account_id": self.account_id,
            "subtitle": self.subtitle,
            "cover": self.cover,
            "resource_type": self.resource_type,
            "progress": self.progress,
            "downloaded": self.downloaded,
            "total": self.total,
            "speed": self.speed,
            "current_item": self.current_item,
            "segment": self.segment,
            "segment_count": self.segment_count,
            "resource_completed": self.resource_completed,
            "resource_total": self.resource_total,
            "logs": list(self.logs),
        }


@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    global health_monitor_task
    health_monitor_task = asyncio.create_task(health_monitor())
    try:
        yield
    finally:
        health_monitor_task.cancel()
        with suppress(asyncio.CancelledError):
            await health_monitor_task


app = FastAPI(title="Abducted Tidal Player", docs_url=None, redoc_url=None, lifespan=app_lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
jobs: dict[str, Job] = {}
job_order: deque[str] = deque(maxlen=50)
account_health: dict[str, AccountHealth] = {}
player_sessions: dict[str, PlayerSession] = {}
health_monitor_task: asyncio.Task | None = None


def cli_command(*args: str) -> list[str]:
    return [sys.executable, "-c", "from tiddl.cli.app import app; app()", *args]


def clean_output(value: bytes) -> list[str]:
    text = value.decode("utf-8", errors="replace").replace("\r", "\n")
    text = ANSI_RE.sub("", text)
    return [line.strip() for line in text.splitlines() if line.strip()]


def handle_output_line(job: Job, line: str) -> None:
    if line.startswith("TIDDL_EVENT "):
        try:
            event = json.loads(line.removeprefix("TIDDL_EVENT "))
        except json.JSONDecodeError:
            return
        if event.get("event") == "download_start":
            job.current_item = event.get("title")
            job.progress = 0
            job.downloaded = 0
            job.total = None
            job.speed = 0
        elif event.get("event") == "download_progress":
            job.current_item = event.get("title")
            job.progress = float(event.get("progress") or 0)
            job.downloaded = int(event.get("downloaded") or 0)
            job.total = event.get("total")
            job.speed = float(event.get("speed") or 0)
            job.segment = event.get("segment")
            job.segment_count = event.get("segment_count")
        elif event.get("event") == "resource_progress":
            job.resource_completed = int(event.get("completed") or 0)
            job.resource_total = int(event.get("total") or 0)
        return

    job.logs.append(line)
    if job.kind == "login" and not job.login_url:
        match = LOGIN_URL_RE.search(line)
        if match:
            job.login_url = match.group(0).rstrip(".,)")


async def run_job(job: Job) -> None:
    job.status = "running"
    try:
        job.process = await asyncio.create_subprocess_exec(
            *job.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={
                **os.environ,
                "PYTHONUNBUFFERED": "1",
                "COLUMNS": "120",
                "TERM": "dumb",
                "TIDDL_WEB_EVENTS": "1",
                **job.env,
            },
        )
        assert job.process.stdout is not None
        while line_bytes := await job.process.stdout.readline():
            for line in clean_output(line_bytes):
                handle_output_line(job, line)
        job.return_code = await job.process.wait()
        if job.status != "cancelled":
            job.status = "completed" if job.return_code == 0 else "failed"
    except asyncio.CancelledError:
        job.status = "cancelled"
        raise
    except Exception as exc:
        job.logs.append(f"Unable to run task: {exc}")
        job.status = "failed"
    finally:
        job.finished_at = datetime.now(timezone.utc).isoformat()
        job.process = None
        if job.account_id and (
            (job.kind == "login" and job.status == "completed")
            or (job.kind == "download" and job.status == "failed")
        ):
            asyncio.create_task(check_account_health(job.account_id))


def create_job(
    kind: Literal["download", "login", "logout"],
    label: str,
    command: list[str],
    account_id: str | None = None,
    env: dict[str, str] | None = None,
    subtitle: str = "",
    cover: str | None = None,
    resource_type: str = "",
) -> Job:
    job = Job(
        id=uuid4().hex[:10],
        kind=kind,
        label=label,
        command=command,
        account_id=account_id,
        env=env or {},
        subtitle=subtitle,
        cover=cover,
        resource_type=resource_type,
    )
    jobs[job.id] = job
    job_order.appendleft(job.id)
    asyncio.create_task(run_job(job))
    return job


def account_path(account_id: str) -> Path:
    if account_id == LEGACY_ACCOUNT_ID:
        return APP_PATH / "auth.json"
    if not re.fullmatch(r"[a-f0-9]{10}", account_id):
        raise ValueError("Invalid account ID")
    return ACCOUNTS_DIR / f"auth_{account_id}.json"


def load_account_settings() -> dict[str, bool]:
    try:
        return json.loads(ACCOUNT_SETTINGS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_account_settings(settings: dict[str, bool]) -> None:
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    ACCOUNT_SETTINGS_FILE.write_text(json.dumps(settings, indent=2))


def account_ids() -> list[str]:
    ids = []
    legacy = load_auth_data(account_path(LEGACY_ACCOUNT_ID))
    if legacy.token and legacy.refresh_token:
        ids.append(LEGACY_ACCOUNT_ID)
    if ACCOUNTS_DIR.exists():
        ids.extend(path.stem.removeprefix("auth_") for path in sorted(ACCOUNTS_DIR.glob("auth_*.json")))
    return [account_id for account_id in ids if load_auth_data(account_path(account_id)).token]


def account_info(account_id: str) -> dict:
    auth = load_auth_data(account_path(account_id))
    active = sum(
        job.kind == "download"
        and job.account_id == account_id
        and job.status in {"queued", "running"}
        for job in jobs.values()
    )
    assigned = sum(job.kind == "download" and job.account_id == account_id for job in jobs.values())
    enabled = load_account_settings().get(account_id, True)
    health = account_health.setdefault(account_id, AccountHealth())
    return {
        "id": account_id,
        "user_id": auth.user_id,
        "username": auth.username,
        "country_code": auth.country_code,
        "authenticated": bool(auth.token and auth.refresh_token),
        "enabled": enabled,
        "active_tasks": active,
        "assigned_tasks": assigned,
        "health_status": health.status,
        "health_failures": health.failures,
        "health_checked_at": health.checked_at,
        "health_error": health.error,
    }


def available_account_ids() -> list[str]:
    settings = load_account_settings()
    return [
        account_id
        for account_id in account_ids()
        if settings.get(account_id, True)
        and account_health.get(account_id, AccountHealth()).status != "unhealthy"
    ]


def select_account(loads: dict[str, int] | None = None) -> str:
    available = available_account_ids()
    if not available:
        raise HTTPException(status_code=401, detail="Add and enable at least one Tidal account.")
    if loads is None:
        loads = {
            account_id: sum(
                job.kind == "download"
                and job.account_id == account_id
                and job.status in {"queued", "running"}
                for job in jobs.values()
            )
            for account_id in available
        }
    return min(available, key=lambda account_id: (loads.get(account_id, 0), available.index(account_id)))


def account_context(account_id: str | None = None) -> ContextObject:
    selected = account_id or select_account()
    return ContextObject(
        api_omit_cache=False,
        debug_path=None,
        console=Console(),
        auth_file=account_path(selected),
    )


def is_authentication_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in ("401", "unauthorized", "invalid_grant", "refresh token", "authentication"))


def probe_account(account_id: str) -> None:
    path = account_path(account_id)
    auth = load_auth_data(path)
    if not auth.username and auth.refresh_token:
        refreshed = AuthAPI().refresh_token(auth.refresh_token)
        auth.token = refreshed.access_token
        auth.expires_at = refreshed.expires_in + int(datetime.now(timezone.utc).timestamp())
        auth.username = refreshed.user.username
        auth.country_code = refreshed.user.countryCode
        save_auth_data(auth, path)
    account_context(account_id).api.get_session()


async def check_account_health(account_id: str) -> AccountHealth:
    health = account_health.setdefault(account_id, AccountHealth())
    health.status = "checking"
    try:
        await asyncio.to_thread(probe_account, account_id)
    except Exception as exc:
        health.failures += 1
        health.error = str(exc)[:240]
        health.status = (
            "unhealthy"
            if is_authentication_error(exc) or health.failures >= HEALTH_FAILURE_THRESHOLD
            else "degraded"
        )
    else:
        health.status = "healthy"
        health.failures = 0
        health.error = None
    health.checked_at = datetime.now(timezone.utc).isoformat()
    return health


async def health_monitor() -> None:
    while True:
        ids = account_ids()
        if ids:
            await asyncio.gather(*(check_account_health(account_id) for account_id in ids))
        await asyncio.sleep(HEALTH_CHECK_INTERVAL)


def image_url(image_id: str | None, size: int = 320) -> str | None:
    if not image_id:
        return None
    path = image_id.replace("-", "/")
    return f"https://resources.tidal.com/images/{path}/{size}x{size}.jpg"


def format_duration(seconds: int) -> str:
    minutes, remaining = divmod(max(seconds, 0), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{remaining:02d}" if hours else f"{minutes}:{remaining:02d}"


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
    is_hires = "HIRES_LOSSLESS" in tags
    has_atmos = "DOLBY_ATMOS" in tags or "DOLBY_ATMOS" in modes
    options = {
        "track_quality": "max" if is_hires else "high",
        "video_quality": "fhd",
        "videos": "allow" if has_audio and has_video else ("only" if has_video else "none"),
        "atmos": "allow" if has_atmos else "none",
    }
    specs = [
        {
            "key": "track_quality",
            "value": options["track_quality"],
            "choices": ["low", "normal", "high", "max"] if has_audio else [],
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
        {
            "key": "atmos",
            "value": options["atmos"],
            "choices": ["none", "allow", "only"] if has_atmos else ["none"],
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
    artists = ", ".join(artist.name for artist in getattr(item, "artists", []))
    cover_id = item.album.cover if resource_type == "track" else item.cover
    return {
        "resource": f"{resource_type}/{item.id}",
        "type": resource_type,
        "title": item.title,
        "subtitle": artists,
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


def player_track(item) -> dict:
    return {
        "id": str(item.id),
        "title": item.title,
        "artist": ", ".join(artist.name for artist in item.artists),
        "artist_id": str(item.artists[0].id) if getattr(item, "artists", None) else "",
        "album": item.album.title,
        "album_id": str(item.album.id),
        "cover": image_url(item.album.cover, 640),
        "duration": item.duration,
        "explicit": bool(item.explicit),
        "qualities": [
            quality
            for quality, supported in (
                ("LOW", True),
                ("HIGH", True),
                ("LOSSLESS", "LOSSLESS" in item.mediaMetadata.tags or "HIRES_LOSSLESS" in item.mediaMetadata.tags),
                ("HI_RES_LOSSLESS", "HIRES_LOSSLESS" in item.mediaMetadata.tags),
            )
            if supported
        ],
        "atmos": "DOLBY_ATMOS" in item.mediaMetadata.tags or "DOLBY_ATMOS" in item.audioModes,
    }


def player_resource(resource_value: str) -> list[dict]:
    resource = TidalResource.from_string(resource_value)
    api = account_context().api
    if resource.type == "track":
        return [player_track(api.get_track(resource.id))]
    if resource.type == "album":
        collection = api.get_album_items(resource.id, limit=100)
        return [player_track(entry.item) for entry in collection.items if entry.type == "track"]
    raise ValueError("Player supports Tidal tracks and albums.")


def player_quality_tiers(quality: str) -> list[str]:
    order = ["HI_RES_LOSSLESS", "LOSSLESS", "HIGH", "LOW"]
    try:
        return order[order.index(quality):]
    except ValueError:
        return ["HIGH", "LOW"]


def resolve_player_stream(track_id: str, quality: str, account_id: str, allow_atmos: bool = False) -> tuple[PlayerSession, dict, dict | None]:
    api = account_context(account_id).api
    track = api.get_track(track_id)
    if not track.allowStreaming or not track.streamReady:
        raise ValueError("This track is not available for streaming.")
    try:
        tidal_session_id = api.get_session().sessionId
    except Exception:
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
            if candidate_stream.audioMode == "DOLBY_ATMOS" and not allow_atmos:
                atmos_only = True
                continue
            candidate_urls, candidate_extension = parse_track_stream(candidate_stream)
            if candidate_stream.manifestMimeType != "application/vnd.tidal.bts" or len(candidate_urls) != 1:
                raise ValueError("This quality uses a segmented stream that the web player cannot play yet.")
            candidate_manifest = json.loads(b64decode(candidate_stream.manifest).decode("utf-8"))
            if candidate_manifest.get("encryptionType", "NONE") not in {"NONE", ""}:
                raise ValueError("This protected stream cannot be played in the web player.")
            stream = candidate_stream
            urls = candidate_urls
            extension = candidate_extension
            manifest = candidate_manifest
            break
        except Exception as exc:
            last_error = exc
    if stream is None:
        if atmos_only:
            raise ValueError("This track is only available as Dolby Atmos. Enable Atmos in player settings to play it.")
        raise last_error or ValueError("No compatible stream quality is available.")
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
    )
    lyrics = None
    try:
        lyric_data = api.get_track_lyrics(track_id)
        lyrics = {"text": lyric_data.lyrics, "subtitles": lyric_data.subtitles, "rtl": lyric_data.isRightToLeft}
    except Exception:
        pass
    return session, player_track(track), lyrics


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


def page_response(name: str) -> HTMLResponse:
    html = (STATIC_DIR / name).read_text(encoding="utf-8")
    version = str(int(max(path.stat().st_mtime for path in STATIC_DIR.iterdir() if path.is_file())))
    html = re.sub(r'(src|href)="(/static/[^"]+)"', rf'\1="\2?v={version}"', html)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/")
async def index() -> HTMLResponse:
    return page_response("index.html")


@app.get("/player")
async def player_page() -> HTMLResponse:
    return page_response("player.html")


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


@app.get("/api/status")
async def status(request: Request) -> dict:
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
    return {
        "authenticated": bool(enabled_accounts),
        "country_code": enabled_accounts[0]["country_code"] if enabled_accounts else None,
        "account_count": len(accounts),
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "download_path": str(download_path),
        "disk_free": shutil.disk_usage(disk_path).free,
        "python_version": platform.python_version(),
        "version": "3.4.4",
        "host": HOST,
        "port": port,
        "lan_urls": lan_addresses(port),
    }


@app.post("/api/auth/login")
async def login() -> dict:
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
async def logout() -> dict:
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
async def list_accounts() -> dict:
    return {"accounts": [account_info(account_id) for account_id in account_ids()]}


@app.patch("/api/accounts/{account_id}")
async def update_account(account_id: str, enabled: bool) -> dict:
    if account_id not in account_ids():
        raise HTTPException(status_code=404, detail="Account not found")
    settings = load_account_settings()
    settings[account_id] = enabled
    save_account_settings(settings)
    if enabled:
        await check_account_health(account_id)
    return account_info(account_id)


@app.post("/api/accounts/{account_id}/health")
async def refresh_account_health(account_id: str) -> dict:
    if account_id not in account_ids():
        raise HTTPException(status_code=404, detail="Account not found")
    await check_account_health(account_id)
    return account_info(account_id)


@app.post("/api/accounts/{account_id}/logout")
async def logout_account(account_id: str) -> dict:
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
async def download(request: DownloadRequest) -> dict:
    created = []
    available = available_account_ids()
    if not available:
        raise HTTPException(status_code=401, detail="Add and enable at least one Tidal account.")
    loads = {
        account_id: sum(
            job.kind == "download"
            and job.account_id == account_id
            and job.status in {"queued", "running"}
            for job in jobs.values()
        )
        for account_id in available
    }
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
        )
        created.append(job.public())
    return {"jobs": created, "count": len(created)}


@app.post("/api/preview")
async def preview(request: PreviewRequest) -> dict:
    if not available_account_ids():
        raise HTTPException(status_code=401, detail="Sign in to preview Tidal resources.")
    try:
        resources = await asyncio.to_thread(build_preview, request.urls)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to load preview: {exc}") from exc
    return {"resources": resources}


@app.get("/api/search")
async def search(query: str = Query(min_length=2, max_length=100)) -> dict:
    if not available_account_ids():
        raise HTTPException(status_code=401, detail="Sign in to search Tidal.")
    try:
        results = await asyncio.to_thread(search_catalog, query)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to search Tidal: {exc}") from exc
    return {"results": results}


@app.post("/api/player/resource")
async def add_player_resource(request: PlayerResourceRequest) -> dict:
    if not available_account_ids():
        raise HTTPException(status_code=401, detail="Sign in to play Tidal.")
    try:
        tracks = await asyncio.to_thread(player_resource, request.resource)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to load tracks: {exc}") from exc
    return {"tracks": tracks}


@app.get("/api/player/artist/{artist_id}")
async def player_artist(artist_id: str) -> dict:
    if not available_account_ids():
        raise HTTPException(status_code=401, detail="Sign in to browse artists.")
    if not re.fullmatch(r"\d+", artist_id):
        raise HTTPException(status_code=404, detail="Artist not found")

    def load() -> dict:
        api = account_context().api
        artist = api.get_artist(artist_id)

        def entries(collection: object) -> list[dict]:
            return [
                {
                    "id": str(album.id),
                    "title": album.title,
                    "artist": ", ".join(name.name for name in album.artists),
                    "year": str(album.releaseDate.year) if getattr(album, "releaseDate", None) else "",
                    "duration": album.duration,
                    "cover": image_url(album.cover, 320),
                }
                for album in collection.items
            ]

        albums = api.get_artist_albums(artist_id, limit=100, filter="ALBUMS")
        singles = api.get_artist_albums(artist_id, limit=100, filter="EPSANDSINGLES")
        return {
            "name": artist.name,
            "picture": image_url(artist.picture, 320),
            "albums": entries(albums),
            "singles": entries(singles),
        }

    try:
        return await asyncio.to_thread(load)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to load artist: {exc}") from exc


@app.get("/api/player/search-artists")
async def search_artists(query: str = Query(min_length=2, max_length=100)) -> dict:
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


@app.post("/api/player/resolve")
async def resolve_player(request: PlayerResolveRequest) -> dict:
    account_id = select_account()
    try:
        session, track, lyrics = await asyncio.to_thread(
            resolve_player_stream, request.track_id, request.quality, account_id, request.allow_atmos
        )
    except Exception as exc:
        if is_authentication_error(exc):
            asyncio.create_task(check_account_health(account_id))
        raise HTTPException(status_code=502, detail=f"Unable to open stream: {exc}") from exc
    now = time.time()
    for session_id in [key for key, value in player_sessions.items() if value.expires_at <= now]:
        player_sessions.pop(session_id, None)
    player_sessions[session.id] = session
    return {
        "session_id": session.id,
        "stream_url": f"/api/player/stream/{session.id}",
        "mime_type": session.mime_type,
        "codec": session.codec,
        "requested_quality": request.quality,
        "quality": session.quality,
        "audio_mode": session.audio_mode,
        "bit_depth": session.bit_depth,
        "sample_rate": session.sample_rate,
        "track": track,
        "lyrics": lyrics,
    }


@app.get("/api/player/stream/{session_id}")
async def proxy_player_stream(session_id: str, range_header: str | None = Header(default=None, alias="Range")):
    session = player_sessions.get(session_id)
    if not session or session.expires_at <= time.time():
        player_sessions.pop(session_id, None)
        raise HTTPException(status_code=410, detail="Playback session expired. Start the track again.")
    headers = {"Range": range_header} if range_header else {}
    client = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_connect=15, sock_read=45))
    try:
        upstream = await client.get(session.url, headers=headers, allow_redirects=True)
    except Exception as exc:
        await client.close()
        raise HTTPException(status_code=502, detail=f"Unable to reach the Tidal stream: {exc}") from exc
    if upstream.status not in {200, 206}:
        status = upstream.status
        upstream.release()
        await client.close()
        raise HTTPException(status_code=502, detail=f"Tidal stream returned HTTP {status}.")

    async def body():
        try:
            async for chunk in upstream.content.iter_chunked(64 * 1024):
                session.bytes += len(chunk)
                yield chunk
        finally:
            upstream.release()
            await client.close()

    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() in {"content-length", "content-range", "accept-ranges", "etag", "last-modified"}
    }
    response_headers.setdefault("Accept-Ranges", "bytes")
    return StreamingResponse(body(), status_code=upstream.status, media_type=session.mime_type, headers=response_headers)


@app.get("/api/player/speed/{session_id}")
async def player_speed(session_id: str) -> dict:
    session = player_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Playback session not found")
    return {"bytes": session.bytes, "expired": session.expires_at <= time.time()}


@app.get("/api/jobs")
async def list_jobs() -> list[dict]:
    return [jobs[job_id].public() for job_id in job_order if job_id in jobs]


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Task not found")
    return jobs[job_id].public()


@app.delete("/api/jobs/{job_id}")
async def cancel_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Task not found")
    if job.status not in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Task has already finished")
    job.status = "cancelled"
    if job.process and job.process.returncode is None:
        job.process.terminate()
    return job.public()


def main() -> None:
    uvicorn.run("tiddl.web.app:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
