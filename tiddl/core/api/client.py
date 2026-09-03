import json
from logging import getLogger
from pathlib import Path
from threading import BoundedSemaphore
from typing import Any, Type, TypeVar, Callable, Optional

from pydantic import BaseModel
from time import sleep

from requests.exceptions import JSONDecodeError
from requests_cache import (
    CachedSession,
    StrOrPath,
    NEVER_EXPIRE,
)

from .exceptions import ApiError

T = TypeVar("T", bound=BaseModel)

API_URL = "https://api.tidal.com/v1"
MAX_RETRIES = 5
RETRY_DELAY = 2
# 全局并发上限:限制同时进行的 Tidal 请求数(防用户并发操作触发限流)。
# 只限制并发排队,不增加单次请求延迟,不影响前端体验。
TIDAL_CONCURRENCY = 6
_tidal_slot = BoundedSemaphore(TIDAL_CONCURRENCY)

log = getLogger(__name__)


# TODO add token expiry check
# maybe refactor to aiohttp.ClientSession
class TidalClient:
    _token: str
    debug_path: Path | None
    session: CachedSession
    on_token_expiry: Optional[Callable[[], str | None]]

    def __init__(
        self,
        token: str,
        cache_name: StrOrPath,
        omit_cache: bool = False,
        debug_path: Path | None = None,
        on_token_expiry: Optional[Callable[[], str | None]] = None,
    ) -> None:
        self.on_token_expiry = on_token_expiry
        self.debug_path = debug_path
        self.session = CachedSession(
            cache_name=cache_name, always_revalidate=omit_cache
        )
        self.session.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        self._token = token

    @property
    def token(self):
        return self._token

    @token.setter
    def token(self, token: str):
        self._token = token
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
            }
        )

    def fetch(
        self,
        model: Type[T],
        endpoint: str,
        params: dict[str, Any] = {},
        expire_after: int = NEVER_EXPIRE,
        headers: dict[str, str] | None = None,
        _attempt: int = 1,
    ) -> T:
        """
        Fetch data from the API endpoint
        and parse it into the given Pydantic model.
        """

        request_kwargs = {"params": params, "expire_after": expire_after}
        if headers:
            request_kwargs["headers"] = headers
        with _tidal_slot:
            res = self.session.get(f"{API_URL}/{endpoint}", **request_kwargs)

        if res.status_code == 401 and self.on_token_expiry:
            if _attempt >= MAX_RETRIES:
                log.error(f"Token refresh failed after {MAX_RETRIES} attempts")
                raise ApiError(
                    status=res.status_code,
                    subStatus="0",
                    userMessage="Token refresh failed.",
                )

            token = self.on_token_expiry()

            if token:
                self.token = token

            return self.fetch(
                model=model,
                endpoint=endpoint,
                params=params,
                expire_after=expire_after,
                headers=headers,
                _attempt=_attempt + 1,
            )

        log.debug(
            f"{endpoint} {params} '{'HIT' if res.from_cache else 'MISS'}' [{res.status_code}]",
        )

        try:
            data = res.json()
        except JSONDecodeError as e:
            if _attempt >= MAX_RETRIES:
                log.error(f"JSON decode failed after {MAX_RETRIES} attempts: {e}")
                raise ApiError(
                    status=res.status_code,
                    subStatus="0",
                    userMessage="Response body does not contain valid json.",
                )

            log.warning(f"JSON decode error, retrying {_attempt}/{MAX_RETRIES}")
            sleep(RETRY_DELAY)

            return self.fetch(
                model=model,
                endpoint=endpoint,
                params=params,
                expire_after=expire_after,
                headers=headers,
                _attempt=_attempt + 1,
            )

        if self.debug_path:
            file = self.debug_path / f"{endpoint}.json"
            file.parent.mkdir(parents=True, exist_ok=True)

            file.write_text(
                json.dumps(
                    {
                        "status_code": res.status_code,
                        "endpoint": endpoint,
                        "params": params,
                        "data": data,
                    },
                    indent=2,
                )
            )

        if res.status_code != 200:
            log.error(f"{endpoint=}, {params=}, {data=}")
            raise ApiError(**data)

        return model.model_validate(data)
