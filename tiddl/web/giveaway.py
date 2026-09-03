# 赠送账号管理:自动生成 N 个本站登录账号,先到先得。
# 基于浏览器指纹(哈希)防重复领取:同一指纹只能领取一次,且密码仅显示一次。
import hashlib
import secrets
import threading
import time
from pathlib import Path

from tiddl.cli.const import APP_PATH
from tiddl.core.utils.jsonio import atomic_write_json, read_json

# 默认路径必须基于 APP_PATH(裸相对路径会随启动目录漂移导致状态丢失)
GIVEAWAY_FILE = APP_PATH / "giveaway_state.json"


def _load(path: Path) -> dict:
    return read_json(path, default={}) or {}


def _save(path: Path, state: dict) -> None:
    atomic_write_json(path, state, mode=0o600)


class GiveawayStore:
    """赠送账号池。state 结构:
    {
      "accounts": [ {"username":..., "password":..., "claimed_by": <fp_hash|None>, "claimed_at": <ts|None>} ],
      "claims": { <fp_hash>: {"username":..., "claimed_at":..., "password_revealed": bool} }
    }
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._state = _load(path)

    def ensure_accounts(self, users, count: int = 5, prefix: str = "gift") -> None:
        """确保存在 count 个未发放的赠送账号;缺失则自动创建到 users store。
        自愈:状态文件中引用已不存在的用户(跨环境残留)时,回滚该领取并原位补齐。
        """
        with self._lock:
            accounts = self._state.setdefault("accounts", [])
            claims = self._state.setdefault("claims", {})
            # 1) 自愈:引用到已不存在用户的账号 → 回滚领取并原位替换为全新账号
            healed = []
            for account in accounts:
                user_exists = users.get(account["username"]) is not None
                if user_exists:
                    healed.append(account)
                    continue
                if account.get("claimed_by"):
                    claims.pop(account["claimed_by"], None)
                healed.append(self._make_account(users, prefix))
            accounts[:] = healed
            # 2) 补齐到 count 个
            for _ in range(len(accounts), count):
                accounts.append(self._make_account(users, prefix))
            _save(self.path, self._state)

    @staticmethod
    def _make_account(users, prefix: str) -> dict:
        """创建一个新赠送账号(user store + 状态),避免与现有用户名冲突。"""
        for _ in range(20):
            username = f"{prefix}{secrets.token_hex(3)}"
            if users.get(username) is not None:
                continue
            password = secrets.token_urlsafe(9)
            try:
                users.create(username, password, is_admin=False)
            except ValueError:
                continue
            return {"username": username, "password": password, "claimed_by": None, "claimed_at": None}
        raise RuntimeError("Unable to allocate giveaway account")

    def status(self, fp_hash: str) -> dict:
        """返回某个指纹的领取状态(不泄露密码)。"""
        with self._lock:
            claims = self._state.setdefault("claims", {})
            account = claims.get(fp_hash)
            available = sum(1 for a in self._state.get("accounts", []) if not a.get("claimed_by"))
            total = len(self._state.get("accounts", []))
            return {
                "total": total,
                "available": available,
                "claimed": bool(account),
                "username": account.get("username") if account else None,
                "password_revealed": bool(account and account.get("password_revealed")),
            }

    def claim(self, fp_hash: str) -> dict:
        """领取一个账号。返回 {username, password, newly};已领则不重复给密码。"""
        with self._lock:
            claims = self._state.setdefault("claims", {})
            accounts = self._state.get("accounts", [])
            # 已领取
            if fp_hash in claims:
                info = claims[fp_hash]
                return {
                    "newly": False,
                    "revealed": bool(info.get("password_revealed")),
                    "username": info.get("username"),
                    "password": None,
                }
            # 找未领取账号
            for account in accounts:
                if not account.get("claimed_by"):
                    account["claimed_by"] = fp_hash
                    account["claimed_at"] = time.time()
                    claims[fp_hash] = {
                        "username": account["username"],
                        "claimed_at": time.time(),
                        "password_revealed": True,
                    }
                    _save(self.path, self._state)
                    return {
                        "newly": True,
                        "revealed": True,
                        "username": account["username"],
                        "password": account["password"],
                    }
            # 已领完
            return {"newly": False, "revealed": False, "username": None, "password": None, "sold_out": True}


def fingerprint_hash(*parts: str) -> str:
    """把浏览器指纹原始串拼起来做 SHA-256,得到不还原的指纹哈希。"""
    raw = "|".join(p or "" for p in parts if p)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
