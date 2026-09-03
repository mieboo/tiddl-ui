"""下载/登录任务执行与带宽均衡(从 web/app.py 抽取)。

依赖 state(任务/会话状态)、users(配额记账)、health(账号健康)、bandwidth(限速),
不依赖 app 路由,避免循环导入。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from tiddl.web.bandwidth import (
    BALANCE_INTERVAL,
    STATE_FILE as BANDWIDTH_STATE_FILE,
    BalanceSnapshot,
    JobRate,
    compute_job_rates,
    load_config,
    write_state,
)
from tiddl.web.health import check_account_health
from tiddl.web.state import (
    LOGIN_URL_RE,
    Job,
    clean_output,
    job_order,
    jobs,
)
from tiddl.web.telemetry import log_telemetry
from tiddl.web.users import TRAFFIC_KIND_DOWNLOAD, get_users

log = logging.getLogger(__name__)


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
            reported = int(event.get("downloaded") or 0)
            # 跨 item 累计:新 item 会从 0 重新上报,按增量累加避免低估
            job.downloaded_total += max(0, reported - job.downloaded)
            job.downloaded = reported
            job.total = event.get("total")
            job.speed = float(event.get("speed") or 0)
            job.segment = event.get("segment")
            job.segment_count = event.get("segment_count")
        elif event.get("event") == "resource_progress":
            job.resource_completed = int(event.get("completed") or 0)
            job.resource_total = int(event.get("total") or 0)
        elif event.get("event") == "download_complete":
            # 下载器完成一个文件时上报绝对路径,记录到 job 供"取回浏览器"使用
            path = event.get("path")
            if path and path not in job.downloaded_files:
                job.downloaded_files.append(path)
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
                # 智能带宽均衡:把共享状态文件与 job id 传给 CLI 子进程,
                # 下载器据此令牌桶限速(仅在存在时生效,普通 CLI 用法不受影响)
                "TIDDL_BANDWIDTH_STATE": str(BANDWIDTH_STATE_FILE),
                "TIDDL_JOB_ID": job.id,
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
        log_telemetry(job.username, "job.finish", {
            "id": job.id, "kind": job.kind, "label": job.label,
            "status": job.status, "return_code": job.return_code,
            "downloaded": job.downloaded_total,
        })
        # 下载配额记账:任务结束(成功/失败/取消)按实际下载字节累计到发起用户
        if job.kind == "download" and job.username and job.downloaded_total > 0:
            try:
                get_users().record_download_bytes(job.username, job.downloaded_total)
                # 全量流量记账(30 天窗口 + 累计,用于管理后台查看每个账号用量)
                get_users().record_traffic(job.username, TRAFFIC_KIND_DOWNLOAD, job.downloaded_total)
            except Exception as exc:
                log.debug("Failed to record download quota for %s: %s", job.username, exc)
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
    username: str | None = None,
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
        username=username,
    )
    jobs[job.id] = job
    job_order.appendleft(job.id)
    log_telemetry(username, "job.create", {
        "id": job.id, "kind": kind, "label": label,
        "resource_type": resource_type, "account_id": account_id,
    })
    asyncio.create_task(run_job(job))
    return job


def bandwidth_jobs() -> list[JobRate]:
    """当前活跃的下载任务(排队/运行中)及其发起用户,供带宽调度使用。"""
    active = []
    for job in jobs.values():
        if job.kind != "download" or job.status not in {"queued", "running"}:
            continue
        active.append(JobRate(job_id=job.id, username=job.username, label=job.label))
    return active


def bandwidth_snapshot() -> dict:
    """管理员视角的带宽调度快照:配置 + 各活跃任务的分配 + 用户份额。"""
    config = load_config()
    job_rates = bandwidth_jobs()
    rates = compute_job_rates(job_rates, config.cap_bytes_per_sec)
    per_user: dict[str, float] = {}
    by_user: dict[str, list[JobRate]] = {}
    for job in job_rates:
        by_user.setdefault(job.username or "__anonymous__", []).append(job)
    for username, user_jobs in by_user.items():
        per_user[username] = sum(rates.get(job.job_id, 0.0) for job in user_jobs)
    return {
        "enabled": config.enabled,
        "cap_mbps": config.cap_mbps,
        "cap_bytes_per_sec": config.cap_bytes_per_sec,
        "active_users": len(by_user),
        "jobs": [
            {
                "job_id": job.job_id,
                "label": job.label,
                "username": job.username,
                "rate_bytes_per_sec": round(rates.get(job.job_id, 0.0), 1),
            }
            for job in job_rates
        ],
        "per_user": per_user,
        "state_file": str(BANDWIDTH_STATE_FILE),
    }


async def bandwidth_balancer() -> None:
    """周期调度:按活跃用户均分总带宽,把各 job 速率写入共享状态文件。

    CLI 下载子进程读取该文件按自己的 job_id 限速,从而实现跨进程的动态均衡。
    """
    while True:
        try:
            config = load_config()
            job_rates = bandwidth_jobs()
            rates = compute_job_rates(job_rates, config.cap_bytes_per_sec)
            snapshot_jobs = [
                JobRate(
                    job_id=job.job_id,
                    username=job.username,
                    label=job.label,
                    rate_bytes_per_sec=rates.get(job.job_id, 0.0),
                )
                for job in job_rates
            ]
            write_state(
                BalanceSnapshot(
                    enabled=config.enabled,
                    cap_bytes_per_sec=config.cap_bytes_per_sec,
                    updated_at=time.time(),
                    jobs=snapshot_jobs,
                )
            )
        except Exception as exc:
            log.warning("Bandwidth balancer iteration failed: %s", exc)
        await asyncio.sleep(BALANCE_INTERVAL)
