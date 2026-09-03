"""智能带宽均衡(限流)调度器。

设计目标
--------
- 总带宽上限默认 400Mbps(可管理员配置/开关),用于**下载任务**的全局限速。
- 不同平台用户之间**公平均分**:同时活跃的用户数 N → 每个用户分到
  ``cap / N``;同一用户的多个下载任务再均分其份额。
- 调度由 Web 后端后台任务执行:周期性把每个 job 应得速率写入
  ``APP_PATH/bandwidth_state.json``;CLI 下载子进程通过环境变量
  (``TIDDL_BANDWIDTH_STATE`` + ``TIDDL_JOB_ID``)读取自己的速率,
  用令牌桶限速,实现跨进程的动态公平分配。

配置
----
存于 ``APP_PATH/bandwidth.json``:
    {"enabled": true, "cap_mbps": 400}
默认开启、400Mbps。管理员可通过 ``PATCH /api/admin/bandwidth`` 修改。
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tiddl.cli.const import APP_PATH
from tiddl.core.utils.jsonio import atomic_write_json, read_json
from tiddl.core.utils.throttle import BandwidthThrottle, RATE_POLL_INTERVAL

log = logging.getLogger(__name__)

# 总带宽上限(Mbps)默认值
DEFAULT_CAP_MBPS = 400
# 共享速率状态文件名(CLI 子进程轮询)
STATE_FILENAME = "bandwidth_state.json"
# 配置文件名
CONFIG_FILENAME = "bandwidth.json"

STATE_FILE = Path(os.environ.get("TIDDL_BANDWIDTH_STATE_FILE", str(APP_PATH / STATE_FILENAME)))
CONFIG_FILE = Path(os.environ.get("TIDDL_BANDWIDTH_CONFIG_FILE", str(APP_PATH / CONFIG_FILENAME)))

# 调度周期:多久重算一次并刷新共享状态文件(秒)
BALANCE_INTERVAL = 2.0


@dataclass
class BandwidthConfig:
    enabled: bool = True
    cap_mbps: int = DEFAULT_CAP_MBPS

    def to_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "cap_mbps": self.cap_mbps}

    @property
    def cap_bytes_per_sec(self) -> int:
        """Mbps → bytes/s(按 1Mbps = 1_000_000 bit/s 换算)。"""
        return int(self.cap_mbps * 1_000_000 / 8)


def load_config(path: Path = CONFIG_FILE) -> BandwidthConfig:
    raw = read_json(path, default={}) or {}
    try:
        return BandwidthConfig(
            enabled=bool(raw.get("enabled", True)),
            cap_mbps=int(raw.get("cap_mbps", DEFAULT_CAP_MBPS)),
        )
    except ValueError:
        return BandwidthConfig()


def save_config(config: BandwidthConfig, path: Path = CONFIG_FILE) -> None:
    atomic_write_json(path, config.to_dict())


@dataclass
class JobRate:
    """一个下载任务被分配到的限速信息。"""

    job_id: str
    username: str | None
    label: str = ""
    rate_bytes_per_sec: float = 0.0


@dataclass
class BalanceSnapshot:
    """一次调度的结果:总配置 + 各 job 分配。"""

    enabled: bool
    cap_bytes_per_sec: int
    updated_at: float
    jobs: list[JobRate] = field(default_factory=list)

    @property
    def active_users(self) -> int:
        return len({job.username for job in self.jobs if job.username})


def compute_job_rates(
    active_jobs: list[JobRate],
    cap_bytes_per_sec: int,
) -> dict[str, float]:
    """公平分配:活跃用户均分总带宽,同一用户的多任务再均分其份额。

    返回 {job_id: rate_bytes_per_sec}。不活跃时(无任务或配额为 0)返回空映射,
    表示不限速。
    """
    if not active_jobs or cap_bytes_per_sec <= 0:
        return {}
    # 按用户分组
    by_user: dict[str, list[JobRate]] = {}
    anonymous: list[JobRate] = []
    for job in active_jobs:
        if job.username:
            by_user.setdefault(job.username, []).append(job)
        else:
            anonymous.append(job)
    # 匿名任务视作一个虚拟用户组
    if anonymous:
        by_user["__anonymous__"] = anonymous

    user_count = len(by_user)
    if user_count == 0:
        return {}
    per_user = cap_bytes_per_sec / user_count

    rates: dict[str, float] = {}
    for jobs in by_user.values():
        share = per_user / len(jobs)
        for job in jobs:
            rates[job.job_id] = share
    return rates


def write_state(
    snapshot: BalanceSnapshot,
    path: Path = STATE_FILE,
) -> None:
    """把当前调度结果落盘,供 CLI 子进程读取。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": snapshot.updated_at,
        "enabled": snapshot.enabled,
        "cap_bytes_per_sec": snapshot.cap_bytes_per_sec,
        "jobs": {
            job.job_id: {
                "username": job.username,
                "label": job.label,
                "rate_bytes_per_sec": round(job.rate_bytes_per_sec, 1),
            }
            for job in snapshot.jobs
        },
    }
    atomic_write_json(path, payload, indent=None)


def read_state(path: Path = STATE_FILE) -> dict[str, Any]:
    """CLI/管理员读取共享状态(容错:文件缺失/损坏返回空结构)。"""
    return read_json(path, default={}) or {}


# ---------------------------------------------------------------------------
