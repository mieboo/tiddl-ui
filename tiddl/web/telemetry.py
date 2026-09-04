"""遥测系统:分账号、分设备、全操作事件采集与查询。

数据模型(统一事件):
    {"ts": float, "account": str, "device_id": str, "session_id": str,
     "evt": str, "data": {...}}

存储:JSONL 按账号+日期分片 -> telemetry/{account}/{YYYYMMDD}.jsonl
    - 每行一条事件,可直接 grep/导出,也可用 query_telemetry 结构化过滤
    - 多实例进程写同一文件用全局锁 + 追加模式(OS 原子 append)

采集端:
    - 网页: telemetry.js -> POST /api/telemetry(批量,带 device_id/session_id)
    - 移动端: App 内轻量上报 -> POST /api/telemetry(带 device_id)
    - 后端: tasks.py / app.py 直接调 log_telemetry

查询: /api/admin/telemetry?account=&device=&evt=&since=&until=&limit=
    - 支持按任意维度组合过滤(分析"某账号某设备做了什么")
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from pathlib import Path

from tiddl.cli.const import APP_PATH

log = logging.getLogger(__name__)

TELEMETRY_DIR = APP_PATH / "telemetry"
# 全量遥测限流:每用户每 10 秒最多 1 批,防止某个账号刷日志拖垮磁盘
_telemetry_last_write: dict[str, float] = {}
TELEMETRY_MIN_INTERVAL = 10.0
_write_lock = threading.Lock()


def _account_path(account: str) -> Path:
    """账号分片目录(路径安全:只保留字母数字-_)。"""
    safe = "".join(c for c in account if c.isalnum() or c in "-_") or "unknown"
    return TELEMETRY_DIR / safe


def _current_file(account: str) -> Path:
    return _account_path(account) / (time.strftime("%Y%m%d") + ".jsonl")


def _write_event(event: dict) -> None:
    """写一条事件到账号+日期分片文件。"""
    try:
        with _write_lock:
            path = _current_file(event.get("account") or "unknown")
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8", buffering=1) as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as exc:
        log.debug("Failed to write telemetry event: %s", exc)


def _normalize_event(account: str | None, evt: str, data: dict | None,
                     device_id: str | None = None,
                     session_id: str | None = None) -> dict:
    return {
        "ts": time.time(),
        "account": account or "unknown",
        "device_id": device_id or "",
        "session_id": session_id or "",
        "evt": evt,
        "data": data or {},
    }


def log_telemetry(username: str | None, evt: str, data: dict | None = None,
                  device_id: str | None = None,
                  session_id: str | None = None) -> None:
    """后端直接打点(任务/播放/搜索等)。不会抛异常。"""
    if not username:
        return
    event = _normalize_event(username, evt, data, device_id, session_id)
    _write_event(event)
    # 兼容旧通道:stdout 一行(便于直接 tail 观察)
    print(f"TELEMETRY[{username}] {json.dumps(event, ensure_ascii=False)[:4000]}", flush=True)


def ingest_batch(account: str | None, events: list[dict],
                 device_id: str | None = None,
                 session_id: str | None = None) -> int:
    """前端批量摄入:给每条补 ts/account/device/session 并落盘。返回写入条数。"""
    written = 0
    for e in events or []:
        if not isinstance(e, dict) or not e.get("evt"):
            continue
        ts = float(e.get("t") or time.time())
        # 前端 t 是毫秒(ms),后端统一存秒(s):ms 特征值 > 1e12
        if ts > 1e12:
            ts = ts / 1000.0
        event = {
            "ts": ts,
            "account": account or "unknown",
            "device_id": str(e.get("device_id") or device_id or ""),
            "session_id": str(e.get("session_id") or session_id or ""),
            "evt": str(e["evt"])[:64],
            "data": e.get("data") if isinstance(e.get("data"), dict) else {},
        }
        _write_event(event)
        written += 1
    return written


def telemetry_throttled(username: str) -> bool:
    """全量遥测限流:同一用户 10 秒内只接受一批,避免刷日志。"""
    now = time.time()
    last = _telemetry_last_write.get(username, 0.0)
    if now - last < TELEMETRY_MIN_INTERVAL:
        return True
    _telemetry_last_write[username] = now
    return False


def new_device_id() -> str:
    """生成稳定设备 ID(调用方持久化)。"""
    return uuid.uuid4().hex


def query_telemetry(*, account: str | None = None, device_id: str | None = None,
                    evt: str | None = None,
                    since: float | None = None, until: float | None = None,
                    limit: int = 200) -> list[dict]:
    """按任意维度组合过滤事件(最近优先)。用于 /api/admin/telemetry 与排查。"""
    if account:
        paths = [_account_path(account)]
    else:
        try:
            paths = [p for p in TELEMETRY_DIR.iterdir() if p.is_dir()]
        except FileNotFoundError:
            return []
    out: list[dict] = []
    for p in paths:
        if not p.is_dir():
            continue
        for f in sorted(p.glob("*.jsonl"), reverse=True):
            try:
                with open(f, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ev = json.loads(line)
                        except Exception:
                            continue
                        if account and ev.get("account") != account:
                            continue
                        if device_id and ev.get("device_id") != device_id:
                            continue
                        if evt and ev.get("evt") != evt:
                            continue
                        t = float(ev.get("ts") or 0)
                        if since and t < since:
                            continue
                        if until and t > until:
                            continue
                        out.append(ev)
            except FileNotFoundError:
                continue
            if len(out) >= limit:
                break
        if len(out) >= limit:
            break
    out.sort(key=lambda e: float(e.get("ts") or 0), reverse=True)
    return out[:limit]


def distinct_devices(account: str | None = None) -> list[dict]:
    """按账号聚合设备清单:{account, device_id, first_ts, last_ts, count}。"""
    agg: dict[tuple, dict] = {}
    for ev in query_telemetry(account=account, limit=100000):
        key = (ev.get("account"), ev.get("device_id"))
        if key not in agg:
            agg[key] = {"account": key[0], "device_id": key[1],
                        "first_ts": ev.get("ts"), "last_ts": ev.get("ts"), "count": 0}
        agg[key]["count"] += 1
        agg[key]["last_ts"] = max(agg[key]["last_ts"], ev.get("ts"))
    return sorted(agg.values(), key=lambda d: d["last_ts"] or 0, reverse=True)


# 行为统计:把遥测事件归类为「用户功能」,便于管理员查看"谁用了什么功能多少次"。
# 不在表内的事件仍计入,label 用事件名本身。
EVENT_FEATURE: dict[str, str] = {
    "session.start": "App 启动",
    "auth.login": "登录",
    "auth.logout": "登出",
    "play.start": "播放",
    "play.resolve": "解析流",
    "play.open": "打开流",
    "play.error": "播放失败",
    "quality.select": "切换音质",
    "search.done": "搜索",
    "queue.add_track": "加入队列",
    "queue.remove_track": "移除队列",
    "queue.clear": "清空队列",
    "queue.shuffle": "随机播放",
    "queue.repeat": "循环模式",
    "download.request": "下载请求",
    "fav.add": "收藏",
    "fav.remove": "取消收藏",
    "follow.unfollow": "关注/取关",
    "page.visibility": "页面切换",
    "error.window": "页面错误",
    "console.error": "运行时告警",
}


def feature_stats(*, account: str | None = None, device_id: str | None = None,
                  since: float | None = None, until: float | None = None) -> list[dict]:
    """行为统计:按账号/设备聚合功能使用次数与最后使用时间。

    返回 [{account, device_id, feature, label, count, last_ts}],按 account,count 降序。
    """
    agg: dict[tuple, dict] = {}
    for ev in query_telemetry(account=account, device_id=device_id,
                              since=since, until=until, limit=100000):
        evt = str(ev.get("evt") or "")
        key = (ev.get("account"), ev.get("device_id"), evt)
        if key not in agg:
            agg[key] = {"account": key[0], "device_id": key[1],
                        "evt": evt, "label": EVENT_FEATURE.get(evt, evt),
                        "count": 0, "last_ts": ev.get("ts")}
        agg[key]["count"] += 1
        agg[key]["last_ts"] = max(agg[key]["last_ts"], ev.get("ts"))
    rows = sorted(agg.values(), key=lambda r: (r["account"], -r["count"]))
    return rows
