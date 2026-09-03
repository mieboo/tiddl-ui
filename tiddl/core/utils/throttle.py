"""跨进程限速器(纯漏桶实现,不依赖 web 层)。

从 ``TIDDL_BANDWIDTH_STATE`` 指向的共享状态文件按 ``TIDDL_JOB_ID`` 读取速率,
供 CLI 下载器逐块调用,实现调度器的动态公平分配。

放在 core 层是为了打破 ``cli → web`` 的循环依赖:
CLI 下载器只需要这个限速器,不应被迫导入整个 web 包。
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from tiddl.core.utils.jsonio import read_json

log = logging.getLogger(__name__)

# CLI 侧读取速率的缓存时间(秒),避免每块都读文件
RATE_POLL_INTERVAL = 0.5


class BandwidthThrottle:
    """漏桶限速器,供 CLI 下载器逐块调用。

    - 速率从 ``TIDDL_BANDWIDTH_STATE`` 指向的共享文件按 job_id 读取,
      每隔 ``RATE_POLL_INTERVAL`` 刷新一次,支持调度器动态调整。
    - 未配置/文件缺失/速率 <= 0 时表示不限速,原样放行(不阻塞)。
    - 采用"下次可发送时间"漏桶:每个块占用 ``size/rate`` 秒,
      严格保证平均速率不超过分配值(不因 sleep 期间累积 token 而超速)。
    """

    def __init__(
        self,
        state_path: str | os.PathLike | None = None,
        job_id: str | None = None,
    ) -> None:
        self.state_path = str(state_path) if state_path is not None else os.environ.get("TIDDL_BANDWIDTH_STATE")
        self.job_id = job_id or os.environ.get("TIDDL_JOB_ID")
        self._next_send = 0.0  # 下一次允许发送数据的单调时钟
        self._last_poll = 0.0
        self._rate: float = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.state_path and self.job_id)

    def _poll_rate(self) -> float:
        """读取当前 job 的分配速率(带缓存)。失败返回 0(不限速)。"""
        now = time.monotonic()
        if now - self._last_poll < RATE_POLL_INTERVAL:
            return self._rate
        self._last_poll = now
        try:
            state: dict[str, Any] = read_json(Path(self.state_path), default={}) or {}
            if not state.get("enabled", True):
                self._rate = 0.0
                return self._rate
            job = state.get("jobs", {}).get(self.job_id) or {}
            self._rate = float(job.get("rate_bytes_per_sec", 0.0) or 0.0)
        except Exception as exc:
            log.debug("BandwidthThrottle poll failed: %s", exc)
            self._rate = 0.0
        return self._rate

    async def pace(self, size: int) -> None:
        """等待足够时间,使本任务实际速率不超过当前分配值。"""
        if not self.enabled or size <= 0:
            return
        rate = self._poll_rate()
        if rate <= 0:
            return
        now = time.monotonic()
        delay = max(0.0, self._next_send - now)
        if delay:
            await _sleep(delay)
            now = time.monotonic()
        self._next_send = max(now, self._next_send) + size / rate


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
