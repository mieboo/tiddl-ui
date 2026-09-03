"""Tidal HTTP 基础设施:全局并发信号量 + 限流退避重试。

从 web/app.py 抽取的纯基础设施,不依赖业务状态(账号/缓存/路由),
供 DRM manifest、账号探测等复用。
"""

from __future__ import annotations

import logging
import threading
import time
import requests

log = logging.getLogger(__name__)

TIDAL_MAX_CONCURRENCY = 3      # 全局并发 Tidal 请求上限
TIDAL_MAX_RETRIES = 3          # 仅限流信号时的重试次数
TIDAL_RETRY_BASE = 1.0         # 指数退避基数(秒)
TIDAL_RETRY_CAP = 8.0          # 退避上限(秒)
_tidal_semaphore = threading.BoundedSemaphore(TIDAL_MAX_CONCURRENCY)


def _tidal_retryable(status_code: int | None = None, exc: Exception | None = None) -> bool:
    """判断是否为可退避重试的限流/瞬时故障(其余错误直接返回,不拖慢体验)。"""
    if status_code is not None and status_code in (408, 429, 500, 502, 503, 504):
        return True
    if exc is not None:
        from requests.exceptions import ConnectionError, RequestException, Timeout
        if isinstance(exc, (ConnectionError, Timeout)):
            return True
        # DataDome 常以连接重置(RemoteDisconnected)形式出现
        if isinstance(exc, RequestException):
            text = str(exc)
            return any(m in text.lower() for m in ("connection", "reset", "timed out", "remote"))
    return False


def _tidal_retry_delay(attempt: int) -> float:
    return min(TIDAL_RETRY_BASE * (2 ** attempt), TIDAL_RETRY_CAP)


def _tidal_request(method: str, url: str, *, params=None, data=None, headers=None, timeout: int = 45):
    """带限流退避的 HTTP 请求(GET/POST 共用)。正常一次返回零延迟;
    仅限流/瞬时故障指数退避重试。"""
    with _tidal_semaphore:
        last_resp = None
        for attempt in range(TIDAL_MAX_RETRIES):
            try:
                resp = requests.request(method, url, params=params, data=data, headers=headers, timeout=timeout)
                if _tidal_retryable(status_code=resp.status_code):
                    last_resp = resp
                    if attempt < TIDAL_MAX_RETRIES - 1:
                        time.sleep(_tidal_retry_delay(attempt))
                        continue
                return resp
            except Exception as exc:
                if _tidal_retryable(exc=exc) and attempt < TIDAL_MAX_RETRIES - 1:
                    time.sleep(_tidal_retry_delay(attempt))
                    continue
                raise
        return last_resp


def _tidal_get(url: str, *, params=None, headers=None, timeout: int = 45):
    """带限流退避的 GET。"""
    return _tidal_request("GET", url, params=params, headers=headers, timeout=timeout)


def _tidal_post(url: str, *, data=None, headers=None, timeout: int = 60):
    """带限流退避的 POST。"""
    return _tidal_request("POST", url, data=data, headers=headers, timeout=timeout)
