"""认证与权限 —— 对齐 Java 版 `JwtAuthticationFilter` 的 5 步校验链。

原版顺序（**不能调换**）：
    0. 白名单路径直接放行（shouldNotFilter）
    1. token 已单独吊销        → TOKEN_BLOCKED
    2. 签名/有效期校验失败     → TOKEN_INVALID
    3. 签发时间早于全量吊销点  → TOKEN_BLOCKED
    4. 用户查不到              → ACCESS_UNAUTHORIZED
       用户 status != 1        → TOKEN_ACCESS_FORBIDDEN
    5. 写入上下文，放行

注意第 4 步：原版是先把用户**查出来**再校验状态，
所以"token 有效但用户已禁用"拿到的错不是 401 而是 A0231。

另外一个重要差异：Spring Security 的 `hasRole('ADMIN')` 表面上看 role 字符串，
但本项目 JWT 里根本没有 `ROLE_` 前缀 —— 真正的判定是 `roleType == 2`
（见 UserType.ADMIN）。这里直接判 roleType，不照搬 Spring 的角色前缀机制。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.blacklist import token_blacklist
from app.core.config import settings
from app.core.errors import (
    ACCESS_UNAUTHORIZED,
    AUTHORIZED_ERROR,
    TOKEN_ACCESS_FORBIDDEN,
    TOKEN_BLOCKED,
    TOKEN_INVALID,
)
from app.core.security import TYPE_REFRESH, expires_at, validate_access_token, verify
from app.db import get_db
from app.models import User

# UserType / UserStatus
USER_TYPE_NORMAL = 1
USER_TYPE_ADMIN = 2
USER_STATUS_NORMAL = 1


# ===========================================================================
# 白名单（对应 SecurityConfig.PUBLIC_PATHS）
#
# ⚠️ 这个列表在原版被两处引用：SecurityConfig 和 JwtAuthticationFilter。
#    Python 版收敛成一份，避免漏改。
# ===========================================================================

PUBLIC_PATHS: tuple[str, ...] = (
    "/",
    "/api/user/login",
    "/api/user/add",
    "/api/user/refresh",
    "/files/**",
    "/actuator/health",
    "/actuator/health/**",
    "/v3/api-docs/**",
    "/swagger-ui/**",
    "/swagger-ui.html",
    "/error",
)


def ant_match(pattern: str, path: str) -> bool:
    """Spring AntPathMatcher 的最小可用实现（`*` / `**` / `?`）。"""
    pat_segs = pattern.strip("/").split("/") if pattern.strip("/") else []
    path_segs = path.strip("/").split("/") if path.strip("/") else []

    def walk(pi: int, si: int) -> bool:
        while pi < len(pat_segs):
            pat = pat_segs[pi]
            if pat == "**":
                return True
            if si >= len(path_segs):
                return False
            if pat != "*" and pat != "?":
                if "*" in pat or "?" in pat:
                    if not _glob_match(pat, path_segs[si]):
                        return False
                elif pat != path_segs[si]:
                    return False
            if pat == "?" and len(path_segs[si]) != 1:
                return False
            pi += 1
            si += 1
        return si == len(path_segs)

    return walk(0, 0)


def _glob_match(pat: str, seg: str) -> bool:
    """段内通配：`*` 任意长度，`?` 单个字符。"""
    import fnmatch

    return fnmatch.fnmatchcase(seg, pat)


def is_public_path(path: str) -> bool:
    return any(ant_match(p, path) for p in PUBLIC_PATHS)


# ===========================================================================
# 当前用户
# ===========================================================================


@dataclass(frozen=True)
class CurrentUser:
    user_id: int
    username: str
    role_type: int
    token: str

    @property
    def is_admin(self) -> bool:
        return self.role_type == USER_TYPE_ADMIN


def _unauthorized(error, status_code: int = status.HTTP_401_UNAUTHORIZED):
    raise HTTPException(status_code=status_code, detail={"code": error.code,
                                                         "msg": error.msg, "data": None})


def extract_token(request: Request) -> str | None:
    """优先读配置头（默认 Authorization，自动剥 Bearer 前缀），
    为空则回退读 `token` 头（兼容旧客户端）。"""
    cfg = settings.jwt
    header_name = cfg.header or "Authorization"
    prefix = cfg.token_prefix or ""

    value = request.headers.get(header_name) or request.headers.get("token")
    if not value:
        return None
    v = value.strip()
    if prefix and v[: len(prefix)].lower() == prefix.lower():
        v = v[len(prefix) :]
    v = v.strip()
    return v or None


def get_current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> CurrentUser:
    token = extract_token(request)
    if not token:
        _unauthorized(ACCESS_UNAUTHORIZED)

    # 1. 单独吊销
    if token_blacklist.is_revoked(token):
        _unauthorized(TOKEN_BLOCKED)

    # 2. 签名与有效期
    result = validate_access_token(token, settings.jwt.secret)
    if result is None:
        _unauthorized(TOKEN_INVALID)

    # 3. 全量吊销时间点
    if token_blacklist.is_issued_before_revoke(result.user_id, result.issued_at):
        _unauthorized(TOKEN_BLOCKED)

    # 4. 用户存在性与状态
    user = db.get(User, result.user_id)
    if user is None:
        _unauthorized(ACCESS_UNAUTHORIZED)
    if user.status != USER_STATUS_NORMAL:
        _unauthorized(TOKEN_ACCESS_FORBIDDEN)

    # 5. 放行
    request.state.jwt_token = token
    return CurrentUser(
        user_id=result.user_id,
        username=result.username,
        role_type=result.role_type,
        token=token,
    )


def get_current_token(request: Request) -> str | None:
    """取当前请求携带的 token（供注销复用）。"""
    cached = getattr(request.state, "jwt_token", None)
    return cached or extract_token(request)


def require_admin(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    """对应 `@PreAuthorize("hasRole('ADMIN')")`。

    拒绝时的响应对齐原版流程：Spring Security 的 ExceptionTranslationFilter
    先于 @RestControllerAdvice 捕获 AccessDeniedException，走 ResponseUtil.writeError，
    落到 default 分支 → **HTTP 400** + Result(A0300)。（不是 403，别凭直觉改。）
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": AUTHORIZED_ERROR.code, "msg": AUTHORIZED_ERROR.msg, "data": None},
        )
    return user


# ===========================================================================
# 刷新令牌校验（/api/user/refresh 专用，路径已在白名单里）
# ===========================================================================


def verify_refresh_token(refresh_token: str) -> tuple[int, int]:
    """返回 (user_id, issued_at_ms)。

    抛出异常时使用与原版一致的响应体。
    """
    from app.core.security import JwtError

    try:
        payload = verify(refresh_token, settings.jwt.secret)
    except JwtError:
        raise HTTPException(
            status_code=401,
            detail={"code": TOKEN_INVALID.code, "msg": "刷新令牌无效或已过期，请重新登录", "data": None},
        )

    if payload.get("typ") != TYPE_REFRESH:
        raise HTTPException(
            status_code=401,
            detail={"code": TOKEN_INVALID.code, "msg": "令牌类型不正确", "data": None},
        )

    if token_blacklist.is_revoked(refresh_token):
        raise HTTPException(
            status_code=401,
            detail={"code": TOKEN_BLOCKED.code, "msg": "登录状态已失效，请重新登录", "data": None},
        )

    user_id = payload.get("userId")
    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail={"code": TOKEN_INVALID.code, "msg": "刷新令牌内容不完整", "data": None},
        )

    issued_at = int(payload.get("iat", 0)) * 1000
    if token_blacklist.is_issued_before_revoke(int(user_id), issued_at):
        raise HTTPException(
            status_code=401,
            detail={"code": TOKEN_BLOCKED.code, "msg": "登录状态已失效，请重新登录", "data": None},
        )

    return int(user_id), issued_at


def revoke_token(token: str | None) -> None:
    """注销单个 token，按它自身的有效期在名单里留档。"""
    if not token:
        return
    exp = expires_at(token, settings.jwt.secret)
    from app.core.security import JwtError

    if exp <= 0:
        try:
            verify(token, settings.jwt.secret)
        except JwtError:
            exp = 0
    token_blacklist.revoke(token, exp)
