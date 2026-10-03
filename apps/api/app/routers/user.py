"""用户模块 —— 10 个接口。

| 权限 | 路径                          |
|------|-------------------------------|
| 🔓   | POST /api/user/login            |
| 🔓   | POST /api/user/add              |
| 🔓   | POST /api/user/refresh          |
| 🔑   | GET  /api/user/current          |
| 🔑   | POST /api/user/logout           |
| 🔑   | POST /api/user/password         |
| 🔑   | PUT  /api/user/profile          |
| 👑   | GET  /api/user/admin/page       |
| 👑   | PUT  /api/user/admin/{id}/status    |
| 👑   | POST /api/user/admin/{id}/password  |

👑 = 需要管理员（原版没有这一组，是本次补的 —— 详见 README 第六节）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.result import Result
from app.deps import (
    CurrentUser,
    get_current_token,
    get_current_user,
    get_db,
    require_admin,
    revoke_token,
    verify_refresh_token,
)
from app.schemas import (
    AdminResetPasswordIn,
    AdminUserRow,
    LoginIn,
    LoginOut,
    PageOut,
    PasswordChangeIn,
    ProfileUpdateIn,
    RegisterIn,
    TokenRefreshIn,
    UserDetail,
    UserStatusIn,
)
from app.services import user as user_service

router = APIRouter(prefix="/api/user", tags=["用户"])


@router.post("/login", response_model=Result[LoginOut], summary="登录")
def login(
    payload: LoginIn,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Result[LoginOut]:
    # 限流：防爆破（账号维度）+ 防同 IP 撞库（网络维度）。阈值见 core/ratelimit.py。
    from app.core.ratelimit import login_ip_limiter, login_limiter

    client_ip = request.client.host if request.client else "unknown"
    login_limiter.check(f"{client_ip}|{payload.username}")
    login_ip_limiter.check(client_ip)
    return Result.ok(user_service.login(db, payload))


@router.post("/add", response_model=Result[UserDetail], summary="注册")
def register(payload: RegisterIn, db: Annotated[Session, Depends(get_db)]) -> Result[UserDetail]:
    return Result.ok(user_service.register(db, payload))


@router.post("/refresh", response_model=Result[LoginOut], summary="刷新访问令牌")
def refresh(payload: TokenRefreshIn, db: Annotated[Session, Depends(get_db)]) -> Result[LoginOut]:
    from app.core.errors import TOKEN_ACCESS_FORBIDDEN, TOKEN_BLOCKED
    from app.core.exceptions import BusinessError

    user_id, _issued_at = verify_refresh_token(payload.refresh_token)
    # 账号被删除或禁用时不再续期
    detail = user_service.get_user_detail(db, user_id)
    if detail.status != 1:
        raise BusinessError(TOKEN_ACCESS_FORBIDDEN, "账号状态异常，请重新登录")
    if not detail.username:
        raise BusinessError(TOKEN_BLOCKED, "登录状态已失效，请重新登录")

    user = db.get(user_service.User, user_id)
    return Result.ok(user_service.build_login_out(user))


@router.get("/current", response_model=Result[UserDetail], summary="当前登录用户")
def current(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[UserDetail]:
    return Result.ok(user_service.get_user_detail(db, user.user_id))


@router.post("/logout", response_model=Result[None], summary="退出登录")
def logout(request: Request, payload: TokenRefreshIn | None = None) -> Result[None]:
    """body 可选。有 refreshToken 就一并吊销。"""
    revoke_token(get_current_token(request))
    if payload and payload.refresh_token:
        revoke_token(payload.refresh_token)
    return Result.ok()


@router.post("/password", response_model=Result[None], summary="修改密码")
def change_password(
    request: Request,
    payload: PasswordChangeIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[None]:
    from app.core.exceptions import BusinessError

    if payload.new_password != payload.confirm_password:
        raise BusinessError("两次输入的新密码不一致")
    user_service.change_password(db, user.user_id, payload.old_password, payload.new_password)
    # 除了「全量下线」（service 里已调 revoke_all_before），还要**显式吊销当前这个 token**。
    #
    # 原因：JWT 的 iat 只有秒级精度，而 revoke_all_before 的比较留了 999ms 容差
    # （不这样会让「同一秒内新登录拿到的 token」被误伤，见 blacklist 里的说明）。
    # 于是与改密**同一秒**签发的那个旧 token 恰好落在容差内、拦不住。
    # 但改密请求本身必然带着一个 token，它总该立即失效 —— 这里单独补上。
    revoke_token(get_current_token(request))
    return Result.ok()


# ===========================================================================
# 个人资料
# ===========================================================================


@router.put("/profile", response_model=Result[UserDetail], summary="更新个人资料")
def update_profile(
    payload: ProfileUpdateIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[UserDetail]:
    """只能改昵称/头像/手机/性别/生日。

    username、email、userType、status **不可改**（service 里的白名单控制），
    否则普通用户能自行提权或解禁。
    """
    return Result.ok(user_service.update_profile(db, user.user_id, payload))


# ===========================================================================
# 管理端：用户管理
#
# 原版完全没有这一组 —— 结果是 `deps.py` 里 `status != 1 → 403` 的校验
# 永远不会触发（没有任何途径把 status 改成非 1），
# 而前端「忘记密码」又指引用户去找管理员重置，管理员却没有这个能力。
# ===========================================================================


@router.get("/admin/page", response_model=Result[PageOut[AdminUserRow]], summary="用户分页")
def admin_page(
    _admin: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    current_page: Annotated[int, Query(alias="currentPage", ge=1)] = 1,
    size: Annotated[int, Query(ge=1)] = 10,
    keyword: str | None = None,
    user_type: Annotated[int | None, Query(alias="userType")] = None,
    status: int | None = None,
) -> Result[PageOut[AdminUserRow]]:
    """keyword 同时匹配用户名 / 昵称 / 邮箱。**不返回密码字段。**"""
    data = user_service.admin_page(db, current_page, size, keyword, user_type, status)
    return Result.ok(
        PageOut[AdminUserRow](
            records=[AdminUserRow.model_validate(u, by_name=True) for u in data["records"]],
            total=data["total"],
        )
    )


@router.put("/admin/{user_id}/status", response_model=Result[None], summary="启用/禁用用户")
def admin_set_status(
    user_id: int,
    payload: UserStatusIn,
    admin: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[None]:
    """0 = 禁用，1 = 正常。禁用会立即吊销该用户的全部令牌。

    不能改自己的状态，也不能禁掉最后一个可用管理员（防止把自己锁在门外）。
    """
    user_service.set_status(db, user_id, payload.status, admin.user_id)
    return Result.ok()


@router.post(
    "/admin/{user_id}/password",
    response_model=Result[None],
    summary="重置用户密码",
)
def admin_reset_password(
    user_id: int,
    payload: AdminResetPasswordIn,
    admin: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[None]:
    """不需要原密码。这就是「忘记密码」缺的那个出口。

    重置后该用户全部令牌失效，并顺带解除禁用状态。
    """
    user_service.admin_reset_password(db, user_id, payload.new_password, admin.user_id)
    return Result.ok()


__all__ = ["router", "settings"]
