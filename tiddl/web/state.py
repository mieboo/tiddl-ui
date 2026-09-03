"""Web 应用共享状态(从 web/app.py 抽取,纯移动零逻辑改动)。

集中 Jobs/PlayerSession 数据类、任务/会话/请求统计全局状态与输出清洗工具,
供 app.py 路由与任务层共用,避免循环导入。
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

log = logging.getLogger(__name__)

ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
LOGIN_URL_RE = re.compile(r"https://[^\s'\"]+")
MAX_LOG_LINES = 500


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
    # 以下字段在拆分 web/app.py 时曾丢失,导致播放时报
    # "PlayerSession.__init__() got an unexpected keyword argument 'transcoded'" —— 已恢复
    traffic_recorded: int = 0
    transcoded: bool = False
    local_path: str | None = None
    drm: dict | None = None


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
    downloaded_total: int = 0
    username: str | None = None
    # 下载任务已完成文件的绝对路径(供"取回到浏览器"使用)
    downloaded_files: list[str] = field(default_factory=list)
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
            "downloaded_total": self.downloaded_total,
            "total": self.total,
            "speed": self.speed,
            "current_item": self.current_item,
            "segment": self.segment,
            "segment_count": self.segment_count,
            "resource_completed": self.resource_completed,
            "resource_total": self.resource_total,
            "logs": list(self.logs),
            "downloaded_files": list(self.downloaded_files),
        }


# 全局任务/会话/请求统计状态(单例,由 app 路由与任务层共享)。
# 注意:health_monitor_task / bandwidth_balancer_task 因 app_lifespan 的
# `global` 赋值必须留在 app.py,不在此模块。
jobs: dict[str, Job] = {}
job_order: deque[str] = deque(maxlen=50)
player_sessions: dict[str, PlayerSession] = {}
# 请求统计:path -> {hits, errors, total_ms, max_ms}
request_stats: dict[str, dict] = {}


def clean_output(value: bytes) -> list[str]:
    text = value.decode("utf-8", errors="replace").replace("\r", "\n")
    text = ANSI_RE.sub("", text)
    return [line.strip() for line in text.splitlines() if line.strip()]
