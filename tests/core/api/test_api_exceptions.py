import pytest
from typing import Any
from tiddl.core.api.exceptions import ApiError


def test_api_error_attributes():
    data: dict[str, Any] = {
        "status": 1,
        "subStatus": "sub_status",
        "userMessage": "user_message",
    }

    e = ApiError(**data)

    assert isinstance(e, Exception)
    assert e.status == data["status"]
    assert e.sub_status == data["subStatus"]
    assert e.user_message == data["userMessage"]


def test_api_error_raises():
    with pytest.raises(ApiError) as exc:
        raise ApiError(400, "bad_request", "invalid")

    assert exc.value.status == 400
    assert exc.value.sub_status == "bad_request"


def test_api_error_string():
    data: dict[str, Any] = {
        "status": 1,
        "subStatus": "sub_status",
        "userMessage": "user_message",
    }

    e = ApiError(**data)

    assert str(e) == f"{e.user_message}, {e.status}/{e.sub_status}"


def test_api_error_missing_keys_defaults():
    """P0-2: ApiError 构造缺键时不应 TypeError,应给默认值。"""
    e = ApiError(**{"userMessage": "only_message"})
    assert e.status is None
    assert e.sub_status is None
    assert e.user_message == "only_message"

    e2 = ApiError(**{})
    assert e2.status is None
    assert e2.user_message == ""


def test_api_error_extra_keys_absorbed():
    """P0-2: ApiError 多余键应被吸收,不应 TypeError。"""
    e = ApiError(status=400, subStatus="s", userMessage="m", extra="x", path="/p")
    assert e.status == 400
