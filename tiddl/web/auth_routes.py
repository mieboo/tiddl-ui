"""平台用户认证与管理路由(从 web/app.py 抽取,APIRouter 模式)。

包含:登录/改密/登出/当前用户、TOTP 两步验证、平台用户 CRUD。
依赖 users.py 的用户域逻辑,不依赖 app 内部状态。
"""

from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from tiddl.web.users import (
    DOWNLOAD_QUOTA_BYTES,
    DOWNLOAD_QUOTA_WINDOW,
    SESSION_COOKIE,
    User,
    generate_totp_secret,
    get_current_user,
    get_sessions,
    get_users,
    require_admin,
    totp_provisioning_uri,
    verify_password,
    verify_totp,
)

router = APIRouter()


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    totp: str | None = Field(default=None, min_length=6, max_length=6)


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=6, max_length=256)
    is_admin: bool = False


class UserPatchRequest(BaseModel):
    password: str | None = Field(default=None, min_length=6, max_length=256)
    is_admin: bool | None = None
    enabled: bool | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=6, max_length=256)


class TotpSetupRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


@router.post("/api/user/login")
async def user_login(request: LoginRequest, response: Response) -> dict:
    store = get_users()
    user = store.get(request.username)
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    if not user.enabled:
        raise HTTPException(status_code=403, detail="This account is disabled.")
    if user.totp_enabled:
        if not request.totp or not verify_totp(user.totp_secret or "", request.totp):
            raise HTTPException(status_code=401, detail="Two-factor code required or invalid.")
    user.last_login = time.time()
    store.save()
    token = get_sessions().create(user.username)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
        path="/",
    )
    return user.public()


@router.post("/api/user/password")
async def user_change_password(request: ChangePasswordRequest, response: Response, user: User = Depends(get_current_user)) -> dict:
    store = get_users()
    current = store.get(user.username)
    if not current or not verify_password(request.current_password, current.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    if request.new_password == request.current_password:
        raise HTTPException(status_code=400, detail="New password must differ from the current password.")
    store.set_password(user.username, request.new_password)
    # 改密后吊销其他会话,保留当前会话
    sessions = get_sessions()
    for token, (username, _expires) in list(sessions._sessions.items()):
        if username == user.username:
            sessions._sessions.pop(token, None)
    token = sessions.create(user.username)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
        path="/",
    )
    return store.get(user.username).public()


@router.post("/api/user/logout")
async def user_logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        get_sessions().delete(token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/api/user/me")
async def user_me(user: User = Depends(get_current_user)) -> dict:
    return user.public()


def _totp_qr_data_url(uri: str) -> str | None:
    """Render a TOTP provisioning URI as a PNG data URL using segno."""
    try:
        import base64
        import io
        import segno
        qr = segno.make(uri, error="m")
        buf = io.BytesIO()
        qr.save(buf, kind="png", scale=8, border=2)
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


@router.get("/api/user/totp/setup")
async def totp_setup(user: User = Depends(require_admin)) -> dict:
    store = get_users()
    if user.totp_enabled:
        return {"enabled": True}
    secret = store.get(user.username).totp_secret or generate_totp_secret()
    if not store.get(user.username).totp_secret:
        store.set_totp_secret(user.username, secret)
    uri = totp_provisioning_uri(user.username, secret)
    return {
        "enabled": False,
        "secret": secret,
        "uri": uri,
        "qr": _totp_qr_data_url(uri),
    }


@router.post("/api/user/totp/enable")
async def totp_enable(request: TotpSetupRequest, user: User = Depends(require_admin)) -> dict:
    store = get_users()
    secret = store.get(user.username).totp_secret
    if not secret:
        raise HTTPException(status_code=400, detail="No TOTP secret initialized.")
    if not verify_totp(secret, request.code):
        raise HTTPException(status_code=400, detail="Invalid two-factor code.")
    store.set_totp_enabled(user.username, True)
    return store.get(user.username).public()


@router.post("/api/user/totp/disable")
async def totp_disable(user: User = Depends(require_admin)) -> dict:
    store = get_users()
    store.set_totp_secret(user.username, None)
    store.set_totp_enabled(user.username, False)
    return store.get(user.username).public()


def user_summary(user: User) -> dict:
    """平台用户视图,附带各时间窗口的流量使用(下载/播放,字节)。"""
    data = user.public()
    data["traffic"] = get_users().traffic_summary(user.username)
    data["quota"] = {
        "limit": DOWNLOAD_QUOTA_BYTES,
        "used": get_users().download_usage_bytes(user.username),
        "remaining": get_users().download_remaining_bytes(user.username),
        "window": DOWNLOAD_QUOTA_WINDOW,
    }
    return data


@router.get("/api/users")
async def list_users(_admin: User = Depends(require_admin)) -> dict:
    return {"users": [user_summary(u) for u in get_users().list()]}


@router.post("/api/users")
async def create_user(request: UserCreateRequest, _admin: User = Depends(require_admin)) -> dict:
    store = get_users()
    if store.get(request.username):
        raise HTTPException(status_code=409, detail="User already exists.")
    user = store.create(request.username, request.password, is_admin=request.is_admin)
    return user.public()


@router.patch("/api/users/{username}")
async def patch_user(username: str, request: UserPatchRequest, admin: User = Depends(require_admin)) -> dict:
    store = get_users()
    user = store.get(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if username == admin.username and (request.is_admin is False or request.enabled is False):
        raise HTTPException(status_code=400, detail="You cannot demote or disable your own account.")
    if request.password is not None:
        store.set_password(username, request.password)
    if request.is_admin is not None:
        store.set_admin(username, request.is_admin)
    if request.enabled is not None:
        store.set_enabled(username, request.enabled)
    return store.get(username).public()


@router.delete("/api/users/{username}")
async def delete_user(username: str, admin: User = Depends(require_admin)) -> dict:
    store = get_users()
    if username == admin.username:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")
    if not store.get(username):
        raise HTTPException(status_code=404, detail="User not found.")
    get_sessions().revoke_user(username)
    store.delete(username)
    return {"ok": True}
