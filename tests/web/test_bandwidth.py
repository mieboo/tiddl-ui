"""限流与智能带宽均衡(流量记账 + 400Mbps 公平均分)测试。"""

import asyncio
import os
import time

import pytest

from tiddl.web.bandwidth import (
    BALANCE_INTERVAL,
    BandwidthConfig,
    BandwidthThrottle,
    JobRate,
    compute_job_rates,
    load_config,
    read_state,
    save_config,
    write_state,
    BalanceSnapshot,
)
from tiddl.web.users import (
    TRAFFIC_KIND_DOWNLOAD,
    TRAFFIC_KIND_PLAY,
    UsersStore,
)


# ---------------------------------------------------------------------------
# 公平分配算法
# ---------------------------------------------------------------------------


def test_fair_share_splits_cap_evenly_across_users():
    jobs = [
        JobRate("a", "alice", "album 1"),
        JobRate("b", "alice", "album 2"),
        JobRate("c", "bob", "album 3"),
    ]
    cap = 400 * 1_000_000 // 8  # 400 Mbps in bytes/s

    rates = compute_job_rates(jobs, cap)

    # 两个用户均分:每个用户 200Mbps 份额;alice 两个任务再各分一半
    assert abs(rates["a"] - cap / 4) < 1e-6
    assert abs(rates["b"] - cap / 4) < 1e-6
    assert abs(rates["c"] - cap / 2) < 1e-6
    # 总额恰好等于上限
    assert abs(sum(rates.values()) - cap) < 1e-6


def test_fair_share_empty_or_disabled_returns_no_limits():
    assert compute_job_rates([], 400_000_000 // 8) == {}
    assert compute_job_rates([JobRate("a", "alice")], 0) == {}


def test_fair_share_treats_anonymous_jobs_as_one_group():
    jobs = [JobRate("a", None), JobRate("b", None), JobRate("c", "carol")]
    cap = 400_000_000 // 8
    rates = compute_job_rates(jobs, cap)
    # 两个"虚拟用户"(匿名组 + carol)均分
    assert abs(rates["a"] + rates["b"] - rates["c"]) < 1e-6
    assert abs(sum(rates.values()) - cap) < 1e-6


# ---------------------------------------------------------------------------
# 配置读写
# ---------------------------------------------------------------------------


def test_bandwidth_config_defaults_and_roundtrip(tmp_path):
    cfg = load_config(tmp_path / "missing.json")
    assert cfg.enabled is True
    assert cfg.cap_mbps == 400
    assert cfg.cap_bytes_per_sec == int(400 * 1_000_000 / 8)

    save_config(BandwidthConfig(enabled=False, cap_mbps=700), tmp_path / "bw.json")
    loaded = load_config(tmp_path / "bw.json")
    assert loaded.enabled is False
    assert loaded.cap_mbps == 700


def test_bandwidth_state_write_and_read(tmp_path):
    path = tmp_path / "state.json"
    write_state(
        BalanceSnapshot(
            enabled=True,
            cap_bytes_per_sec=100,
            updated_at=time.time(),
            jobs=[JobRate("j1", "alice", "x", rate_bytes_per_sec=50)],
        ),
        path=path,
    )
    state = read_state(path)
    assert state["enabled"] is True
    assert state["jobs"]["j1"]["rate_bytes_per_sec"] == 50
    # 缺失文件容错
    assert read_state(tmp_path / "nope.json") == {}


# ---------------------------------------------------------------------------
# CLI 侧漏桶限速器
# ---------------------------------------------------------------------------


def test_throttle_disabled_without_env_binding():
    throttle = BandwidthThrottle(state_path=None, job_id=None)
    assert throttle.enabled is False


def test_throttle_paces_at_assigned_rate(tmp_path):
    state_file = tmp_path / "state.json"
    write_state(
        BalanceSnapshot(
            enabled=True,
            cap_bytes_per_sec=1024 * 1024,
            updated_at=time.time(),
            jobs=[JobRate("job1", "alice", "x", rate_bytes_per_sec=1024 * 1024)],
        ),
        path=state_file,
    )
    throttle = BandwidthThrottle(state_path=state_file, job_id="job1")
    assert throttle.enabled is True

    async def main():
        marks = []
        for _ in range(4):
            await throttle.pace(1024 * 1024)
            marks.append(time.monotonic())
        return marks

    marks = asyncio.run(main())
    gaps = [marks[i + 1] - marks[i] for i in range(len(marks) - 1)]
    # 1MiB 块、1MiB/s 配额 → 相邻块启动间隔约 1s(不超过配额)
    assert all(abs(gap - 1.0) < 0.15 for gap in gaps)


def test_throttle_ignores_missing_state(tmp_path):
    throttle = BandwidthThrottle(state_path=tmp_path / "missing.json", job_id="j")

    async def main():
        await throttle.pace(1024 * 1024)

    asyncio.run(main())  # 不应抛异常、不应限速


# ---------------------------------------------------------------------------
# 每用户流量记账
# ---------------------------------------------------------------------------


def test_traffic_accounting_tracks_download_and_play(tmp_path):
    store = UsersStore(path=tmp_path / "users.json")
    store.create("alice", "secret123")

    store.record_traffic("alice", TRAFFIC_KIND_DOWNLOAD, 1000)
    store.record_traffic("alice", TRAFFIC_KIND_PLAY, 500)

    summary = store.traffic_summary("alice")
    assert summary["today"]["download"] == 1000
    assert summary["today"]["play"] == 500
    assert summary["today"]["total"] == 1500
    assert summary["total"]["download"] == 1000
    assert summary["total"]["play"] == 500
    assert summary["total"]["total"] == 1500


def test_traffic_accounting_persists_across_reload(tmp_path):
    store = UsersStore(path=tmp_path / "users.json")
    store.create("bob", "secret123")
    store.record_traffic("bob", TRAFFIC_KIND_DOWNLOAD, 2048)

    # 模拟重启:同一路径重建 store,累计流量应仍在
    store2 = UsersStore(path=tmp_path / "users.json")
    assert store2.traffic_summary("bob")["total"]["download"] == 2048


def test_traffic_ignores_unknown_user(tmp_path):
    store = UsersStore(path=tmp_path / "users.json")
    store.record_traffic("ghost", TRAFFIC_KIND_DOWNLOAD, 100)
    summary = store.traffic_summary("ghost")
    assert summary["total"]["total"] == 0


def test_traffic_summary_windows_by_age(tmp_path):
    import tiddl.web.users as users_mod

    store = UsersStore(path=tmp_path / "users.json")
    store.create("carol", "secret123")
    user = store.get("carol")
    now = time.time()
    # 直接注入不同年龄的记录:今日 / 3 天前(7 天窗口) / 20 天前(30 天窗口)
    user.traffic_usage = [
        [now, TRAFFIC_KIND_DOWNLOAD, 100],
        [now - 3 * 86400, TRAFFIC_KIND_DOWNLOAD, 200],
        [now - 20 * 86400, TRAFFIC_KIND_PLAY, 300],
    ]
    # 生命周期累计计数器与注入记录保持一致(真实路径由 record_traffic 同步更新)
    user.total_download_bytes = 300
    user.total_play_bytes = 300
    summary = store.traffic_summary("carol")
    assert summary["today"]["download"] == 100
    assert summary["week"]["download"] == 200
    assert summary["month"]["play"] == 300
    assert summary["total"]["total"] == 600


def test_traffic_download_quota_records_separately(tmp_path):
    """全量流量记账与 12h 下载配额记账互不影响。"""
    store = UsersStore(path=tmp_path / "users.json")
    store.create("dave", "secret123")

    store.record_traffic("dave", TRAFFIC_KIND_DOWNLOAD, 1024)
    store.record_download_bytes("dave", 4096)

    assert store.download_usage_bytes("dave") == 4096
    assert store.traffic_summary("dave")["total"]["download"] == 1024
