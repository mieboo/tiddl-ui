"""统一的 JSON 原子读写 helper。

消除 users.py / bandwidth.py / giveaway.py 中重复的"tmp+replace+chmod"手写实现,
提供一致的容错读取与原子写入。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any = None) -> Any:
    """容错读取 JSON;文件缺失/损坏时返回 default(不抛异常)。"""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def atomic_write_json(path: Path, data: Any, mode: int = 0o600, indent: int = 2) -> None:
    """原子写 JSON:先写同目录临时文件,再 rename 覆盖,最后 chmod。

    与各存储的既有语义一致(避免半写文件),临时文件名基于目标路径派生。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=indent, ensure_ascii=False)
        os.replace(tmp_name, path)
        try:
            os.chmod(path, mode)
        except OSError:
            pass
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
