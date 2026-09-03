"""服务器端遥测写入(共享模块)。

前端 /api/telemetry 与后端任务(tasks.py)共用同一个落盘通道:
- app.py 的 telemetry 端点:接收前端批量打点(播放/DRM/点击/操作/下载请求)
- tasks.py 的 run_job/create_job:任务生命周期打点(创建/完成/失败/取消)

日志按用户名标注(TELEMETRY[username]),便于按账号筛选分析。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from tiddl.cli.const import APP_PATH

log = logging.getLogger(__name__)

_telemetry_lock = threading.Lock()
TELEMETRY_LOG = APP_PATH / "telemetry.log"
# 全量遥测限流:每用户每 10 秒最多 1 批,防止某个账号刷日志拖垮磁盘
_telemetry_last_write: dict[str, float] = {}
TELEMETRY_MIN_INTERVAL = 10.0


def _write_telemetry(data: str) -> None:
    try:
        with _telemetry_lock:
            with open(TELEMETRY_LOG, "a", encoding="utf-8", buffering=1) as fh:
                fh.write(data + "\n")
    except Exception as exc:
        log.debug("Failed to write telemetry log: %s", exc)


def log_telemetry(username: str | None, evt: str, data: dict | None = None) -> None:
    """写一条服务器端遥测(任务生命周期等)。不会抛异常。"""
    if not username:
        return
    try:
        payload = {"evt": evt, "data": data or {}}
        line = f"TELEMETRY[{username}] {json.dumps(payload, ensure_ascii=False)[:4000]}"
        print(line, flush=True)
        _write_telemetry(line)
    except Exception as exc:
        log.debug("Failed to log telemetry %s: %s", evt, exc)


def telemetry_throttled(username: str) -> bool:
    """全量遥测限流:同一用户 10 秒内只接受一批,避免刷日志。"""
    now = time.time()
    last = _telemetry_last_write.get(username, 0.0)
    if now - last < TELEMETRY_MIN_INTERVAL:
        return True
    _telemetry_last_write[username] = now
    return False
