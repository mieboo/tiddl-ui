"""Platform user accounts for tiddl-ui.

These are *website* users (who log in to browse/play/download), separate from
the underlying Tidal account pool. Passwords are hashed with the stdlib
(no new dependency), sessions are short-lived opaque tokens held server-side,
and the cookie carries only the session id.

Data lives in ``APP_PATH/users.json`` next to ``accounts/``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import base64

from tiddl.cli.const import APP_PATH
from tiddl.core.utils.jsonio import atomic_write_json, read_json

# 用户认证依赖(FastAPI):app.py 路由通过转发导入复用,避免循环依赖
from fastapi import Depends, HTTPException, Request

log = logging.getLogger(__name__)

USERS_FILE = Path(os.environ.get("TIDDL_USERS_FILE", str(APP_PATH / "users.json")))

SESSION_COOKIE = "tiddl_session"

_PBKDF2_ITERATIONS = 600_000
_SESSION_TTL = 7 * 24 * 3600  # 7 days

# 下载配额:每 12 小时最多 2GB(滑动窗口,按实际下载字节记账)
DOWNLOAD_QUOTA_BYTES = 2 * 1024**3
DOWNLOAD_QUOTA_WINDOW = 12 * 3600

# 全量流量记账(不限速,仅统计):保留最近 30 天的逐笔记录,另有累计总数
TRAFFIC_KIND_DOWNLOAD = "download"
TRAFFIC_KIND_PLAY = "play"
TRAFFIC_RETENTION = 30 * 24 * 3600


@dataclass
class User:
    username: str
    password_hash: str
    is_admin: bool = False
    created_at: float = field(default_factory=time.time)
    last_login: float | None = None
    enabled: bool = True
    # opaque usage counters (incremented by the API layer)
    plays: int = 0
    downloads: int = 0
    # TOTP two-factor (admin), base32 secret
    totp_secret: str | None = None
    totp_enabled: bool = False
    # 下载配额:滑动窗口内的 [ts, bytes] 记录,持久化防止重启绕过
    download_usage: list = field(default_factory=list)
    # 全量流量记账:[[ts, kind, bytes], ...] 保留 30 天;total_* 为累计
    traffic_usage: list = field(default_factory=list)
    total_download_bytes: int = 0
    total_play_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def public(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "is_admin": self.is_admin,
            "created_at": self.created_at,
            "last_login": self.last_login,
            "enabled": self.enabled,
            "plays": self.plays,
            "downloads": self.downloads,
            "totp_enabled": self.totp_enabled,
        }


# ---------------------------------------------------------------------------
# Password hashing (stdlib pbkdf2_hmac, format: pbkdf2_sha256$iter$salt$hash)
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return "pbkdf2_sha256$%d$%s$%s" % (
        _PBKDF2_ITERATIONS,
        salt.hex(),
        digest.hex(),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, hash_hex = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# TOTP (RFC 6238) using only the standard library.
# Secret is stored base32; verifies the current 30s window ±1 step.
# ---------------------------------------------------------------------------


def _totp_code(secret_b32: str, timestamp: float | None = None) -> int:
    key = base64.b32decode(secret_b32.upper().replace(" ", ""))
    counter = int((timestamp if timestamp is not None else time.time()) // 30)
    msg = counter.to_bytes(8, "big")
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF
    return binary % 1_000_000


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def verify_totp(secret_b32: str, code: str, window: int = 1) -> bool:
    try:
        expected = str(_totp_code(secret_b32)).zfill(6)
        candidate = str(code).strip().zfill(6)
        if len(candidate) != 6 or not candidate.isdigit():
            return False
        if hmac.compare_digest(expected, candidate):
            return True
        # allow ±window time steps
        now = time.time()
        for step in range(1, window + 1):
            for offset in (step, -step):
                if hmac.compare_digest(str(_totp_code(secret_b32, now + offset * 30)).zfill(6), candidate):
                    return True
        return False
    except (ValueError, TypeError):
        return False


def totp_provisioning_uri(username: str, secret_b32: str, issuer: str = "ATP") -> str:
    import urllib.parse
    label = urllib.parse.quote(f"{issuer}:{username}")
    secret = urllib.parse.quote(secret_b32)
    return f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"


# ---------------------------------------------------------------------------
# Users store
# ---------------------------------------------------------------------------


class UsersStore:
    def __init__(self, path: Path = USERS_FILE) -> None:
        self.path = path
        self._users: dict[str, User] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        raw = read_json(self.path)
        if not raw:
            return
        for entry in raw.get("users", []):
            user = User(**{k: v for k, v in entry.items() if k in User.__dataclass_fields__})
            self._users[user.username] = user

    def save(self) -> None:
        payload = {"users": [u.to_dict() for u in self._users.values()]}
        atomic_write_json(self.path, payload)

    def get(self, username: str) -> User | None:
        return self._users.get(username)

    def list(self) -> list[User]:
        return sorted(self._users.values(), key=lambda u: u.created_at)

    def create(self, username: str, password: str, is_admin: bool = False) -> User:
        with self._lock:
            if username in self._users:
                raise ValueError("User already exists")
            user = User(
                username=username,
                password_hash=hash_password(password),
                is_admin=is_admin,
            )
            self._users[username] = user
            self.save()
            return user

    def delete(self, username: str) -> None:
        with self._lock:
            self._users.pop(username, None)
            self.save()

    def set_password(self, username: str, password: str) -> None:
        with self._lock:
            user = self._users[username]
            user.password_hash = hash_password(password)
            self.save()

    def set_enabled(self, username: str, enabled: bool) -> None:
        with self._lock:
            user = self._users[username]
            user.enabled = enabled
            self.save()

    def set_admin(self, username: str, is_admin: bool) -> None:
        with self._lock:
            user = self._users[username]
            user.is_admin = is_admin
            self.save()

    def set_totp_secret(self, username: str, secret: str | None) -> None:
        with self._lock:
            user = self._users[username]
            user.totp_secret = secret
            if secret is None:
                user.totp_enabled = False
            self.save()

    def set_totp_enabled(self, username: str, enabled: bool) -> None:
        with self._lock:
            user = self._users[username]
            user.totp_enabled = enabled
            self.save()

    def record_play(self, username: str) -> None:
        with self._lock:
            user = self._users.get(username)
            if user:
                user.plays += 1
                self.save()

    def record_downloads(self, username: str, count: int) -> None:
        with self._lock:
            user = self._users.get(username)
            if user:
                user.downloads += count
                self.save()

    # ---- 下载配额(每 12 小时 2GB,滑动窗口,持久化) ----
    def record_download_bytes(self, username: str, amount: int) -> None:
        with self._lock:
            user = self._users.get(username)
            if not user or amount <= 0:
                return
            now = time.time()
            # 先清理窗口外记录,再追加本次
            user.download_usage = [(ts, b) for ts, b in user.download_usage if now - ts < DOWNLOAD_QUOTA_WINDOW]
            user.download_usage.append([now, amount])
            self.save()

    def try_record_download(self, username: str, amount: int) -> bool:
        """原子"检查配额 + 记账":同一把锁内完成,避免并发下超发。

        返回是否记账成功;配额不足或用户不存在时返回 False 且不记账。
        """
        with self._lock:
            user = self._users.get(username)
            if not user or amount <= 0:
                return False
            now = time.time()
            user.download_usage = [(ts, b) for ts, b in user.download_usage if now - ts < DOWNLOAD_QUOTA_WINDOW]
            used = sum(b for ts, b in user.download_usage)
            if used + amount > DOWNLOAD_QUOTA_BYTES:
                return False
            user.download_usage.append([now, amount])
            self.save()
            return True

    def download_usage_bytes(self, username: str) -> int:
        with self._lock:
            user = self._users.get(username)
            if not user:
                return 0
            now = time.time()
            return sum(b for ts, b in user.download_usage if now - ts < DOWNLOAD_QUOTA_WINDOW)

    def download_remaining_bytes(self, username: str) -> int:
        with self._lock:
            return max(0, DOWNLOAD_QUOTA_BYTES - self.download_usage_bytes(username))

    # ---- 全量流量记账(下载/播放,30 天窗口 + 累计,持久化) ----
    def record_traffic(self, username: str, kind: str, amount: int) -> None:
        with self._lock:
            user = self._users.get(username)
            if not user or amount <= 0:
                return
            now = time.time()
            # 先清理超过保留期的旧记录,再追加本次
            user.traffic_usage = [
                (ts, k, b) for ts, k, b in user.traffic_usage if now - ts < TRAFFIC_RETENTION
            ]
            user.traffic_usage.append([now, kind, amount])
            if kind == TRAFFIC_KIND_PLAY:
                user.total_play_bytes += amount
            else:
                user.total_download_bytes += amount
            self.save()

    def traffic_summary(self, username: str) -> dict[str, Any]:
        """按时间窗口汇总某用户的流量(字节):今天/7天/30天/累计。

        返回形如:{"today": {"download": 0, "play": 0, "total": 0}, ...}
        """
        user = self._users.get(username)
        empty = {
            "today": {"download": 0, "play": 0, "total": 0},
            "week": {"download": 0, "play": 0, "total": 0},
            "month": {"download": 0, "play": 0, "total": 0},
            "total": {"download": 0, "play": 0, "total": 0},
        }
        if not user:
            return empty
        now = time.time()
        day_ago = now - 24 * 3600
        week_ago = now - 7 * 24 * 3600
        month_ago = now - 30 * 24 * 3600
        buckets = {day_ago: "today", week_ago: "week", month_ago: "month"}
        for ts, kind, amount in user.traffic_usage:
            key = "total"
            # 倒序遍历:最新的时间边界优先匹配(今日 > 7天 > 30天)
            for boundary, label in sorted(buckets.items(), reverse=True):
                if ts >= boundary:
                    key = label
                    break
            bucket = empty[key]
            bucket[kind] += amount
            bucket["total"] += amount
        empty["total"]["download"] = user.total_download_bytes
        empty["total"]["play"] = user.total_play_bytes
        empty["total"]["total"] = user.total_download_bytes + user.total_play_bytes
        return empty


_store: UsersStore | None = None


def get_users() -> UsersStore:
    global _store
    if _store is None:
        _store = UsersStore()
    return _store


def ensure_bootstrap_admin() -> None:
    """On first run, create the initial admin from environment variables.

    ``TIDDL_ADMIN_USERNAME`` (default ``admin``) and ``TIDDL_ADMIN_PASSWORD``
    (if unset, a random password is generated and logged once).
    """
    store = get_users()
    if store.list():
        return
    username = os.environ.get("TIDDL_ADMIN_USERNAME", "admin")
    password = os.environ.get("TIDDL_ADMIN_PASSWORD") or secrets.token_urlsafe(12)
    store.create(username, password, is_admin=True)
    if "TIDDL_ADMIN_PASSWORD" not in os.environ:
        log.warning("Created initial admin user '%s' with password: %s", username, password)


# ---------------------------------------------------------------------------
# Sessions (opaque tokens held server-side; cookie carries only the token)
# ---------------------------------------------------------------------------
SESSIONS_FILE = Path(os.environ.get("TIDDL_SESSIONS_FILE", str(APP_PATH / "sessions.json")))


class SessionStore:
    """Server-side session store, persisted to disk so a server restart does
    not log every user out (previously in-memory only)."""

    def __init__(self, path: Path = SESSIONS_FILE) -> None:
        self._path = path
        self._sessions: dict[str, tuple[str, float]] = {}  # token -> (username, expires)
        self._last_save = 0.0
        self._load()

    def _load(self) -> None:
        try:
            data = read_json(self._path) or {}
            now = time.time()
            for token, entry in data.items():
                username = entry.get("username") if isinstance(entry, dict) else entry
                expires = entry.get("expires") if isinstance(entry, dict) else 0
                if username and float(expires) > now:
                    self._sessions[str(token)] = (str(username), float(expires))
        except Exception as exc:
            log.warning("Failed to load sessions: %s", exc)

    def _save(self) -> None:
        try:
            data = {token: {"username": name, "expires": exp} for token, (name, exp) in self._sessions.items()}
            atomic_write_json(self._path, data, indent=None)
        except Exception as exc:
            log.warning("Failed to save sessions: %s", exc)

    def _save_throttled(self) -> None:
        now = time.time()
        if now - self._last_save < 5.0:
            return
        self._last_save = now
        self._save()

    def create(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = (username, time.time() + _SESSION_TTL)
        self._save()
        return token

    def get(self, token: str) -> str | None:
        entry = self._sessions.get(token)
        if not entry:
            return None
        username, expires = entry
        now = time.time()
        if now > expires:
            self._sessions.pop(token, None)
            self._save()
            return None
        # 滑动续期:活跃会话持续有效,并定期落盘(避免每次请求都写文件)
        self._sessions[token] = (username, now + _SESSION_TTL)
        self._save_throttled()
        return username

    def delete(self, token: str) -> None:
        if self._sessions.pop(token, None) is not None:
            self._save()

    def revoke_user(self, username: str) -> None:
        changed = False
        for token, (name, _expires) in list(self._sessions.items()):
            if name == username:
                self._sessions.pop(token, None)
                changed = True
        if changed:
            self._save()

    def touch(self, token: str) -> None:
        entry = self._sessions.get(token)
        if entry:
            self._sessions[token] = (entry[0], time.time() + _SESSION_TTL)
            self._save_throttled()


_sessions: SessionStore | None = None


def get_sessions() -> SessionStore:
    global _sessions
    if _sessions is None:
        _sessions = SessionStore()
    return _sessions


def get_current_user(request: Request) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    username = get_sessions().get(token or "")
    if not username:
        raise HTTPException(status_code=401, detail="Not signed in.")
    user = get_users().get(username)
    if not user or not user.enabled:
        raise HTTPException(status_code=401, detail="Not signed in.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user
