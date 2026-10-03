"""用户业务：登录 / 注册 / 改密。

⚠️ 密码必须用 bcrypt：老库里的哈希是 Java `BCryptPasswordEncoder` 生成的
`$2a$10$...`，换成 pbkdf2 / argon2 会导致全体老用户登录失败。

细节对齐：
· login 里密码做了 `.trim()` 再比对（原版行为）
· changePassword 里原密码**不** trim（原版行为，两边不一样是有历史的，别统一）
· 注册时 **强制 user_type = 1**，堵住原版的任意提权漏洞
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import bcrypt
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ACCOUNT_NOT_FOUND, ACCOUNT_SAME
from app.core.exceptions import BusinessError
from app.core.security import create_access_token, create_refresh_token
from app.models import User
from app.schemas import LoginIn, LoginOut, RegisterIn, UserDetail

# 与 deps.py / 原版 UserType.ADMIN 一致
USER_TYPE_ADMIN = 2

_ROUNDS = 10  # 对应 Spring BCryptPasswordEncoder 的默认 strength


def hash_password(plain: str) -> str:
    # bcrypt 只吃前 72 字节，与 Spring 的实现行为一致（超长静默截断）
    return bcrypt.hashpw(plain.encode("utf-8")[:72], bcrypt.gensalt(rounds=_ROUNDS, prefix=b"2a")).decode()


def _validated_password(plain: str) -> str:
    """新口令的统一入口：strip 后再校验最小长度。

    schema 的 min_length 是对**原始串**判的 —— "      "（6 个空格）能通过
    校验但 strip 后为空；再叠加「登录时输入会 strip」这条既有行为，
    直接落库一个带首尾空格的哈希会让用户永远登不进来。所以三处
    （注册 / 自助改密 / 管理员重置）都必须先 strip 再校验。
    """
    stripped = (plain or "").strip()
    if len(stripped) < 6:
        raise BusinessError("密码需 6 位以上，且不能以空白字符开头结尾")
    return stripped


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def build_login_out(user: User) -> LoginOut:
    cfg = settings.jwt
    token = create_access_token(
        user_id=user.id, username=user.username or "", role_type=user.user_type or 1,
        secret=cfg.secret, expiration_ms=cfg.expiration,
    )
    refresh = create_refresh_token(
        user_id=user.id, username=user.username or "", role_type=user.user_type or 1,
        secret=cfg.secret, expiration_ms=cfg.refresh_expiration,
    )
    return LoginOut(
        token=token,
        refresh_token=refresh,
        role_type=str(user.user_type or 1),  # ⚠️ 字符串
        user_info=UserDetail.model_validate(user, by_name=True),
    )


# 登录时序均衡用的哑哈希：账号不存在时也跑一次 bcrypt，
# 让「账号不存在」和「密码错误」的响应时间一致 —— 否则响应时间差
# 可以被用来探测哪些用户名注册过（提示语相同但 bcrypt 慢 ~100ms）。
_DUMMY_HASH = hash_password("timing-equalizer-dummy-password")


def login(db: Session, payload: LoginIn) -> LoginOut:
    user = db.scalar(
        select(User).where(
            or_(User.username == payload.username, User.email == payload.username)
        )
    )
    if user is None:
        # 账号不存在与密码错误返回同一提示，避免被用来枚举注册用户；
        # 补一次等价哈希抹平时序差（详见 _DUMMY_HASH 说明）
        verify_password(payload.password.strip(), _DUMMY_HASH)
        raise BusinessError("用户名或密码错误")
    if not verify_password(payload.password.strip(), user.password or ""):
        raise BusinessError("用户名或密码错误")
    if not user.is_active:
        raise BusinessError("用户已被禁用，请联系管理员")
    return build_login_out(user)


def register(db: Session, payload: RegisterIn) -> UserDetail:
    if payload.password != payload.confirm_password:
        raise BusinessError("两次输入密码不一致")

    if db.scalar(select(func.count()).select_from(User).where(User.username == payload.username)):
        raise BusinessError(ACCOUNT_SAME, "用户名已存在")
    if db.scalar(select(func.count()).select_from(User).where(User.email == payload.email)):
        raise BusinessError(ACCOUNT_SAME, "邮箱已存在")

    now = datetime.now()
    user = User(
        username=payload.username,
        email=payload.email,
        nickname=payload.nickname,
        phone=payload.phone,
        password=hash_password(_validated_password(payload.password)),
        gender=payload.gender,
        birthday=payload.birthday,
        # ★ 安全修复：强制普通用户。原版此处直接采信客户端传值，
        #   导致匿名白名单接口可被用来注册管理员（见契约清单第六章）
        user_type=1,
        status=1,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        # 并发注册同名时唯一约束兜底（先查后插在并发下有窗口）
        db.rollback()
        raise BusinessError(ACCOUNT_SAME, "用户名或邮箱已存在") from exc
    db.refresh(user)
    return UserDetail.model_validate(user, by_name=True)


def get_user_detail(db: Session, user_id: int) -> UserDetail:
    user = db.get(User, user_id)
    if user is None:
        raise BusinessError(ACCOUNT_NOT_FOUND, "用户不存在")
    return UserDetail.model_validate(user, by_name=True)


def change_password(db: Session, user_id: int, old: str, new: str) -> None:
    from app.core.blacklist import token_blacklist

    user = db.get(User, user_id)
    if user is None:
        raise BusinessError(ACCOUNT_NOT_FOUND, "用户不存在")
    if not verify_password(old, user.password or ""):
        raise BusinessError("原密码不正确")
    # 新密码必须 strip（登录侧会 strip 输入，两边不一致会让用户登不进来）；
    # 旧密码保持不 trim —— 原版行为，见模块顶部说明
    new = _validated_password(new)
    if old == new:
        raise BusinessError("新密码不能与原密码相同")

    user.password = hash_password(new)
    user.updated_at = datetime.now()
    db.commit()

    # 改密即全端下线
    token_blacklist.revoke_all_before(user_id)


# ===========================================================================
# 个人资料
# ===========================================================================

# 允许用户自己改的字段。username / email / user_type / status **不在其中**：
# 开放它们等于把「自行提权」和「自行解禁」的口子开回来（原版注册接口就犯过这个错）。
PROFILE_EDITABLE = ("nickname", "avatar", "phone", "gender", "birthday")


def update_profile(db: Session, user_id: int, payload: Any) -> UserDetail:
    user = db.get(User, user_id)
    if user is None:
        raise BusinessError(ACCOUNT_NOT_FOUND, "用户不存在")

    changed = False
    for field in PROFILE_EDITABLE:
        value = getattr(payload, field, None)
        # None 表示"这次没传"，跳过 —— 否则会把已有值清空
        # （注意：这意味着当前无法把某字段显式清空，属于有意的取舍）
        if value is None:
            continue
        if getattr(user, field) != value:
            setattr(user, field, value)
            changed = True

    if changed:
        user.updated_at = datetime.now()
        db.commit()
        db.refresh(user)
    return UserDetail.model_validate(user, by_name=True)


# ===========================================================================
# 管理端：用户管理
# ===========================================================================

MAX_PAGE_SIZE = 100


def admin_page(
    db: Session,
    current_page: int = 1,
    size: int = 10,
    keyword: str | None = None,
    user_type: int | None = None,
    status: int | None = None,
) -> dict[str, Any]:
    """用户分页。keyword 同时匹配用户名 / 昵称 / 邮箱。"""
    page_no = max(1, current_page)
    page_size = min(max(1, size), MAX_PAGE_SIZE)

    conditions = []
    if keyword and keyword.strip():
        like = f"%{keyword.strip()}%"
        conditions.append(
            or_(User.username.like(like), User.nickname.like(like), User.email.like(like))
        )
    if user_type is not None:
        conditions.append(User.user_type == user_type)
    if status is not None:
        conditions.append(User.status == status)

    total = db.scalar(select(func.count()).select_from(User).where(*conditions)) or 0
    records = list(
        db.scalars(
            select(User)
            .where(*conditions)
            .order_by(User.id.desc())
            .offset((page_no - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return {"records": records, "total": total}


def _active_admin_count(db: Session, exclude_id: int | None = None) -> int:
    conditions = [User.user_type == USER_TYPE_ADMIN, User.status == 1]
    if exclude_id is not None:
        conditions.append(User.id != exclude_id)
    return db.scalar(select(func.count()).select_from(User).where(*conditions)) or 0


def set_status(db: Session, target_id: int, status: int, operator_id: int) -> None:
    """启用 / 禁用账号。禁用会让对方的令牌立即全部失效。

    两处防护，都是为了避免把管理员自己锁在门外：
      · 不能改自己的状态（改完就可能再也登不进来）
      · 不能让系统进入「没有任何可用管理员」的状态
    """
    from app.core.blacklist import token_blacklist

    if status not in (0, 1):
        raise BusinessError("状态值不合法")

    if target_id == operator_id:
        raise BusinessError("不能修改自己的账号状态")

    target = db.get(User, target_id)
    if target is None:
        raise BusinessError(ACCOUNT_NOT_FOUND, "用户不存在")

    if (
        status == 0
        and target.user_type == USER_TYPE_ADMIN
        and _active_admin_count(db, exclude_id=target_id) == 0
    ):
        raise BusinessError("系统需要至少保留一个可用的管理员账号")

    target.status = status
    target.updated_at = datetime.now()
    db.commit()

    # 两个方向都要吊销：
    #   禁用 → 否则已登录的会话在禁用期间还能继续用
    #   解禁 → 否则**禁用前的旧令牌会复活**。禁用只让令牌被 status 校验拦下，
    #          令牌本身并没有进黑名单；一旦状态回到 1，它就又能用了。
    token_blacklist.revoke_all_before(target_id)


def admin_reset_password(
    db: Session, target_id: int, new_password: str, operator_id: int
) -> None:
    """管理员重置他⼈密码。**这就是「忘记密码」缺的那个出口。**

    不需要原密码（用户已经忘了）。重置后对方的所有令牌立即失效。
    另外顺手解开禁用：密码能重置但账号还被禁着，等于没解决问题。
    """
    from app.core.blacklist import token_blacklist

    target = db.get(User, target_id)
    if target is None:
        raise BusinessError(ACCOUNT_NOT_FOUND, "用户不存在")

    target.password = hash_password(_validated_password(new_password))
    if target.status != 1:
        target.status = 1
    target.updated_at = datetime.now()
    db.commit()

    token_blacklist.revoke_all_before(target_id)
