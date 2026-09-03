

def test_concurrent_record_download_bytes_no_loss(tmp_path):
    """P0-5: 并发记账不丢数据(有锁保护)。"""
    import threading
    from tiddl.web.users import UsersStore

    store = UsersStore(tmp_path / "users.json")
    store.create("alice", "pw")
    errors = []

    def worker(n):
        try:
            for _ in range(50):
                store.record_download_bytes("alice", 1000)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    # 8 线程 × 50 次 × 1000 字节 = 400000
    assert store.download_usage_bytes("alice") == 400000


def test_try_record_download_atomic_quota(tmp_path):
    """阶段4: try_record_download 原子"检查+记账",配额不足拒绝且不记账。"""
    from tiddl.web.users import DOWNLOAD_QUOTA_BYTES, UsersStore

    store = UsersStore(tmp_path / "users2.json")
    store.create("bob", "pw")

    # 配额充足 → 记账成功
    assert store.try_record_download("bob", 1000) is True
    assert store.download_usage_bytes("bob") == 1000

    # 超出配额 → 拒绝且不记账
    assert store.try_record_download("bob", DOWNLOAD_QUOTA_BYTES) is False
    assert store.download_usage_bytes("bob") == 1000

    # 恰好补满配额 → 成功
    assert store.try_record_download("bob", DOWNLOAD_QUOTA_BYTES - 1000) is True
    assert store.download_usage_bytes("bob") == DOWNLOAD_QUOTA_BYTES

    # 不存在的用户 → False
    assert store.try_record_download("nobody", 1) is False
