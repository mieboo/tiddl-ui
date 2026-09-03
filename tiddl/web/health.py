"""账号健康监控与订阅检测(从 web/app.py 抽取)。

依赖 accounts(账号上下文/健康状态)、drm(订阅探测)、auth 工具,不依赖 app 路由。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from tiddl.cli.utils.auth.core import load_auth_data, save_auth_data
from tiddl.core.auth import AuthAPI
from tiddl.web.accounts import (
    AccountHealth,
    account_context,
    account_health,
    account_ids,
    account_path,
    is_authentication_error,
    load_account_settings,
    save_account_settings,
)
from tiddl.web.drm import probe_subscription

log = logging.getLogger(__name__)

HEALTH_CHECK_INTERVAL = 60
HEALTH_FAILURE_THRESHOLD = 3
# 订阅检测节流:每 N 轮健康检查跑一次订阅探测,且逐账号间隔错开(避免触发 Tidal 限流)
SUBSCRIPTION_CHECK_CYCLES = 10
SUBSCRIPTION_PROBE_DELAY = 15


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


async def check_account_subscription(account_id: str) -> AccountHealth:
    health = account_health.setdefault(account_id, AccountHealth())
    health.subscription = "checking"
    try:
        result = await asyncio.to_thread(probe_subscription, account_id)
    except Exception as exc:
        health.subscription = "unknown"
        health.subscription_error = str(exc)[:240]
    else:
        health.subscription = result
        health.subscription_error = None
        if result == "expired":
            # 订阅过期 → 立即停用账号(持久化),避免继续被负载均衡选中
            settings = load_account_settings()
            if settings.get(account_id, True):
                settings[account_id] = False
                save_account_settings(settings)
            health.status = "unhealthy"
            health.error = "Tidal subscription expired; account disabled."
            log.warning("Tidal subscription expired for account %s — disabled", account_id)
    health.subscription_checked_at = datetime.now(timezone.utc).isoformat()
    return health


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
    # 节流:健康探测 60s 一轮;订阅检测更低频(默认每 10 轮=10 分钟一次),
    # 且逐账号串行、间隔错开,避免同时打 Tidal v2 API 触发限流。
    subscription_cycle = 0
    while True:
        ids = account_ids()
        if ids:
            await asyncio.gather(*(check_account_health(account_id) for account_id in ids))
            subscription_cycle += 1
            if subscription_cycle >= SUBSCRIPTION_CHECK_CYCLES:
                subscription_cycle = 0
                for index, account_id in enumerate(ids):
                    await check_account_subscription(account_id)
                    if index < len(ids) - 1:
                        await asyncio.sleep(SUBSCRIPTION_PROBE_DELAY)
        await asyncio.sleep(HEALTH_CHECK_INTERVAL)
