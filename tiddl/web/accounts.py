"""Tidal 账号池管理(从 web/app.py 抽取)。

包含账号路径/设置/负载/选择与上下文构造等**纯数据函数**,
不依赖 FastAPI 应用实例或任务状态,供路由与 DRM 层复用。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from rich.console import Console

from tiddl.cli.config import APP_PATH
from tiddl.cli.ctx import ContextObject
from tiddl.cli.utils.auth.core import load_auth_data
from tiddl.web.state import jobs

log = logging.getLogger(__name__)

ACCOUNTS_DIR = APP_PATH / "accounts"
ACCOUNT_SETTINGS_FILE = ACCOUNTS_DIR / "settings.json"
LEGACY_ACCOUNT_ID = "default"


@dataclass
class AccountHealth:
    status: Literal["unknown", "checking", "healthy", "degraded", "unhealthy"] = "unknown"
    failures: int = 0
    checked_at: str | None = None
    error: str | None = None
    # 订阅检测(用自有 client 探测 v2 manifest: FULL=有效, PREVIEW=过期/无权限)
    subscription: Literal["unknown", "checking", "active", "expired"] = "unknown"
    subscription_checked_at: str | None = None
    subscription_error: str | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "failures": self.failures,
            "checked_at": self.checked_at,
            "error": self.error,
            "subscription": self.subscription,
            "subscription_checked_at": self.subscription_checked_at,
            "subscription_error": self.subscription_error,
        }


account_health: dict[str, AccountHealth] = {}


def account_path(account_id: str) -> Path:
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
    if not ACCOUNTS_DIR.exists():
        return []
    ids = [p.stem.removeprefix("auth_") for p in ACCOUNTS_DIR.glob("auth_*.json")]
    return sorted(ids)


def account_loads(account_id: str) -> tuple[int, int]:
    """返回 (当前负载, 总配额);文件缺失按 (0, 0) 处理。"""
    try:
        data = json.loads(account_path(account_id).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return 0, 0
    return data.get("loads", 0), data.get("load_limit", 0)


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
        # 兼容旧字段(部分路由仍用)
        "loads": account_loads(account_id)[0],
        "load_limit": account_loads(account_id)[1],
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
        loads = {account_id: account_loads(account_id)[0] for account_id in available}
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
