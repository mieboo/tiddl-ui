import pytest
import json

from pydantic import BaseModel
from pytest_mock import MockerFixture
from pathlib import Path

from tiddl.core.api.client import TidalClient, ApiError


def test_tidal_client_init(mocker: MockerFixture):
    mock_cached_session = mocker.patch("tiddl.core.api.client.CachedSession")
    mock_session = mock_cached_session.return_value

    client = TidalClient(
        token="test-token",
        cache_name="test_cache",
        omit_cache=True,
        debug_path=Path("/tmp/debug"),
    )

    mock_cached_session.assert_called_once_with(
        cache_name="test_cache", always_revalidate=True
    )

    assert client.token == "test-token"
    assert client.debug_path == Path("/tmp/debug")
    assert client.session is mock_session
    assert mock_session.headers["Authorization"] == "Bearer test-token"
    assert mock_session.headers["Accept"] == "application/json"


@pytest.mark.parametrize("omit_cache", [True, False])
def test_omit_cache_flag(mocker: MockerFixture, omit_cache: bool):
    mock_cached_session = mocker.patch("tiddl.core.api.client.CachedSession")
    TidalClient("token", "cache", omit_cache=omit_cache)
    mock_cached_session.assert_called_once_with(
        cache_name="cache", always_revalidate=omit_cache
    )


class DummyModel(BaseModel):
    foo: str


def test_fetch_success(mocker: MockerFixture, tmp_path: Path):
    mock_session = mocker.Mock()
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.from_cache = False
    mock_response.json.return_value = {"foo": "bar"}
    mock_session.get.return_value = mock_response

    mocker.patch("tiddl.core.api.client.API_URL", "https://api.test")
    client = TidalClient("token", tmp_path / "cache", debug_path=tmp_path)
    client.session = mock_session

    result = client.fetch(DummyModel, "albums/123", {"limit": 10}, expire_after=999)
    assert result.foo == "bar"

    mock_session.get.assert_called_once_with(
        "https://api.test/albums/123",
        params={"limit": 10},
        expire_after=999,
    )

    debug_file = tmp_path / "albums/123.json"
    assert debug_file.exists()

    content = json.loads(debug_file.read_text())
    assert content["status_code"] == 200
    assert content["endpoint"] == "albums/123"
    assert content["params"]["limit"] == 10
    assert content["data"]["foo"] == "bar"


def test_fetch_error_raises_api_error(mocker: MockerFixture, tmp_path: Path):
    mock_session = mocker.Mock()
    mock_response = mocker.Mock()
    mock_response.status_code = 400
    mock_response.from_cache = False
    mock_response.json.return_value = {
        "status": 400,
        "subStatus": "Bad request",
        "userMessage": "user_message",
    }
    mock_session.get.return_value = mock_response

    client = TidalClient("token", tmp_path / "cache")
    client.session = mock_session

    with pytest.raises(ApiError):
        client.fetch(DummyModel, "bad/endpoint")


def test_fetch_401_retries_bounded_when_token_expiry_fails(
    mocker: MockerFixture, tmp_path: Path
):
    """P0-1: 401 + on_token_expiry 返回 None 时,递归必须有上限,不能无限递归。"""
    mock_session = mocker.Mock()
    mock_response = mocker.Mock()
    mock_response.status_code = 401
    mock_response.from_cache = False
    mock_session.get.return_value = mock_response

    mocker.patch("tiddl.core.api.client.API_URL", "https://api.test")
    # on_token_expiry 永远返回 None(token 刷新失败)
    client = TidalClient(
        "token", tmp_path / "cache", on_token_expiry=lambda: None
    )
    client.session = mock_session

    with pytest.raises(ApiError):
        client.fetch(DummyModel, "albums/123")

    # 最多应调用 1 + MAX_RETRIES 次(首次 + 递归),绝不能无限
    assert mock_session.get.call_count <= 1 + 5
