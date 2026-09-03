from pathlib import Path
from pytest import raises

from tiddl.cli.config import load_config_file, Config, CONFIG_FILENAME


def write_config(tmp_path: Path, content: str) -> Path:
    cfg_path = tmp_path / CONFIG_FILENAME
    cfg_path.write_text(content)
    return cfg_path


def test_missing_file_default_config(tmp_path: Path):
    cfg_file = tmp_path / "nonexistent.toml"
    cfg = load_config_file(cfg_file)

    assert isinstance(cfg, Config)


def test_valid_config_file(tmp_path: Path):
    cfg_file = write_config(
        tmp_path,
        """
        enable_cache = false
        debug = true

        [download]
        track_quality = "max"
        threads_count = 8
        """,
    )

    cfg = load_config_file(cfg_file)

    assert cfg.enable_cache is False
    assert cfg.debug is True
    assert cfg.download.track_quality == "max"
    assert cfg.download.threads_count == 8


def test_match_existing_path_case_config(tmp_path: Path):
    cfg_file = write_config(
        tmp_path,
        """
        [download]
        match_existing_path_case = true
        """,
    )

    cfg = load_config_file(cfg_file)

    assert cfg.download.match_existing_path_case is True


def test_invalid_type_raises(tmp_path: Path):
    cfg_file = write_config(
        tmp_path,
        """
        enable_cache = "not_a_bool"
        """,
    )

    with raises(Exception):
        load_config_file(cfg_file)


def test_invalid_track_quality_raises(tmp_path: Path):
    cfg_file = write_config(
        tmp_path,
        """
        [download]
        track_quality = "ultra"
        """,
    )

    with raises(Exception):
        load_config_file(cfg_file)


def test_get_config_lazy_and_injectable(tmp_path, monkeypatch):
    """P1-4: get_config 惰性加载缓存 + set_config_for_tests 可注入(不改 51 处引用)。"""
    from tiddl.cli.config import get_config, set_config_for_tests, Config

    # 注入自定义配置
    injected = Config(debug=True)
    set_config_for_tests(injected)
    try:
        assert get_config() is injected
        # 清空缓存 → 重新读盘(用默认路径,不报错即可)
        set_config_for_tests(None)
        cfg = get_config()
        assert isinstance(cfg, Config)
    finally:
        set_config_for_tests(None)
