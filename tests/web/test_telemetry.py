"""Tests for tiddl.web.telemetry: 分账号、分设备遥测存储与查询。"""

import json
import time

import pytest

from tiddl.web import telemetry as tel


@pytest.fixture(autouse=True)
def isolate_store(tmp_path, monkeypatch):
    """每个测试用独立目录,避免污染真实遥测文件。"""
    monkeypatch.setattr(tel, "TELEMETRY_DIR", tmp_path / "telemetry")
    yield


def _mk_event(account, device, evt, ts=None):
    return {
        "ts": ts if ts is not None else time.time(),
        "account": account,
        "device_id": device,
        "session_id": "sess",
        "evt": evt,
        "data": {"x": 1},
    }


class TestWriteAndQuery:
    def test_ingest_batch_partitions_by_account_and_date(self):
        n = tel.ingest_batch("alice", [
            {"t": time.time(), "evt": "play.start", "data": {"tid": "1"}},
            {"t": time.time(), "evt": "search.done", "data": {"q": "petal"}},
        ], device_id="devA")
        assert n == 2
        # 文件按账号+日期分片
        path = tel._current_file("alice")
        assert path.exists()
        lines = path.read_text().splitlines()
        assert len(lines) == 2
        ev = json.loads(lines[0])
        assert ev["account"] == "alice"
        assert ev["device_id"] == "devA"
        assert ev["evt"] == "play.start"

    def test_query_filters_by_account_device_evt(self):
        now = time.time()
        tel.ingest_batch("alice", [
            {"t": now, "evt": "play.start", "data": {}},
            {"t": now, "evt": "quality.select", "data": {}},
        ], device_id="devA")
        tel.ingest_batch("bob", [
            {"t": now, "evt": "play.start", "data": {}},
        ], device_id="devB")

        # 按账号
        assert len(tel.query_telemetry(account="alice")) == 2
        # 按账号+设备
        assert len(tel.query_telemetry(account="alice", device_id="devA")) == 2
        assert len(tel.query_telemetry(account="alice", device_id="devB")) == 0
        # 按事件
        assert len(tel.query_telemetry(account="alice", evt="play.start")) == 1
        assert len(tel.query_telemetry(evt="play.start")) == 2  # 跨账号
        # 按时间窗
        assert len(tel.query_telemetry(since=now - 10, until=now + 10)) == 3
        assert len(tel.query_telemetry(since=now + 100)) == 0

    def test_distinct_devices_aggregates(self):
        now = time.time()
        tel.ingest_batch("alice", [
            {"t": now, "evt": "a", "data": {}},
            {"t": now + 5, "evt": "b", "data": {}},
        ], device_id="devA")
        tel.ingest_batch("alice", [
            {"t": now, "evt": "c", "data": {}},
        ], device_id="devB")
        devices = tel.distinct_devices("alice")
        assert len(devices) == 2
        by_id = {d["device_id"]: d for d in devices}
        assert by_id["devA"]["count"] == 2
        assert by_id["devB"]["count"] == 1

    def test_log_telemetry_skips_empty_username(self):
        # 不写文件、不抛异常
        tel.log_telemetry("", "job.finish")
        tel.log_telemetry(None, "job.finish")
        assert list(tel.TELEMETRY_DIR.glob("**/*.jsonl")) == []

    def test_new_device_id_unique(self):
        a, b = tel.new_device_id(), tel.new_device_id()
        assert a and b and a != b
