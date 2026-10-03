"""咨询会话业务 —— 对齐 Java 版 `ConsultationQueryService` + `ConsultationSessionService`
+ `ConsultationMessageService`。

两条硬约束：
1. **归属校验**：所有针对具体会话的读写都必须先过 `require_accessible`，
   否则就是"换个 id 就能读别人私密对话"。
2. **列表上限 50**（不是全局的 100），最后一条消息预览长度 **30**。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AUTHORIZED_ERROR, PARAM_INVALID
from app.core.exceptions import BusinessError
from app.models import ConsultationMessage, ConsultationSession, CrisisEvent, User
from app.schemas import MessageRow, SessionRow

MAX_PAGE_SIZE = 50
PREVIEW_LIMIT = 30

SESSION_ID_PREFIX = "session_"


def _dt(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def preview(content: str | None) -> str | None:
    if content is None:
        return None
    return content if len(content) <= PREVIEW_LIMIT else content[:PREVIEW_LIMIT] + "..."


def parse_session_id(session_id: str | None) -> int | None:
    """从 "session_123" 或 "123" 解析出主键；非法返回 None。"""
    if session_id is None:
        return None
    raw = session_id[len(SESSION_ID_PREFIX) :] if session_id.startswith(SESSION_ID_PREFIX) else session_id
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


# ===========================================================================
# 归属校验
# ===========================================================================


def require_accessible(db: Session, session_id: int | None, current_user_id: int, admin: bool) -> ConsultationSession:
    """仅会话所属用户本人或管理员可访问。"""
    if session_id is None:
        raise BusinessError(PARAM_INVALID, "会话ID不能为空")

    session = db.get(ConsultationSession, session_id)
    if session is None:
        raise BusinessError(PARAM_INVALID, "会话不存在")

    owner = session.user_id == current_user_id
    if not owner and not admin:
        raise BusinessError(AUTHORIZED_ERROR, "无权访问该会话")
    return session


# ===========================================================================
# 会话创建
# ===========================================================================


def create_session(db: Session, user_id: int, session_title: str | None) -> ConsultationSession | None:
    """用户不存在时返回 None（原版如此）。标题为空时生成默认标题。"""
    user = db.get(User, user_id)
    if user is None:
        return None

    now = datetime.now()
    title = session_title
    if not title or not title.strip():
        # 与前端默认标题同品牌（前端是「云舒AI助手 - 时间」，这里只在
        # 前端没传标题时兜底 —— 品牌名必须一致，别再写旧名）
        title = f"云舒AI助手 - {now.strftime('%m-%d %H:%M')}"

    session = ConsultationSession(user_id=user_id, session_title=title, started_at=now)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


# ===========================================================================
# 列表
# ===========================================================================


def page_of_user(db: Session, user_id: int, current_page: int, size: int) -> dict[str, Any]:
    return _page_sessions(db, user_id, current_page, size, with_user_info=False)


def page_of_all(
    db: Session,
    current_page: int,
    size: int,
    keyword: str | None = None,
    risk_first: bool = False,
    risk_only: bool = False,
) -> dict[str, Any]:
    """管理端全站会话列表。

    `keyword` / `risk_first` / `risk_only` 是 2026-10-02 整改新增的：
    原接口**只接受分页参数**，没有任何筛选能力，而页面副标题却写着
    「可按关键词检索」——承诺了不存在的功能。
    """
    return _page_sessions(
        db,
        None,
        current_page,
        size,
        with_user_info=True,
        keyword=keyword,
        risk_first=risk_first,
        risk_only=risk_only,
    )


def _page_sessions(
    db: Session,
    user_id: int | None,
    current_page: int,
    size: int,
    with_user_info: bool,
    keyword: str | None = None,
    risk_first: bool = False,
    risk_only: bool = False,
) -> dict[str, Any]:
    page_no = max(1, current_page)
    page_size = min(max(1, size), MAX_PAGE_SIZE)

    conditions = []
    if user_id is not None:
        # ★ 用户端强制按归属过滤，不加这一条就是全站泄露
        conditions.append(ConsultationSession.user_id == user_id)

    kw = (keyword or "").strip()
    if kw:
        # 三个维度：会话标题 / 用户名或昵称 / 消息正文。
        # 消息正文用子查询而不是 JOIN —— JOIN 会让 count 被消息行数放大。
        like = f"%{kw}%"
        hit_sessions = select(ConsultationMessage.session_id).where(
            ConsultationMessage.content.like(like)
        )
        hit_users = select(User.id).where(
            or_(User.username.like(like), User.nickname.like(like))
        )
        conditions.append(
            or_(
                ConsultationSession.session_title.like(like),
                ConsultationSession.user_id.in_(hit_users),
                ConsultationSession.id.in_(hit_sessions),
            )
        )

    if risk_only:
        conditions.append(
            ConsultationSession.id.in_(
                select(CrisisEvent.session_id).where(CrisisEvent.session_id.isnot(None))
            )
        )

    # 风险等级做成关联子查询，才能**在 SQL 里排序** ——
    # 若在 Python 侧排序，分页会错乱（第 2 页会重复第 1 页的行）。
    risk_level = (
        select(func.max(CrisisEvent.level))
        .where(CrisisEvent.session_id == ConsultationSession.id)
        .correlate(ConsultationSession)
        .scalar_subquery()
    )
    if risk_first:
        order_by = (
            func.coalesce(risk_level, 0).desc(),
            ConsultationSession.started_at.desc(),
        )
    else:
        order_by = (ConsultationSession.started_at.desc(),)

    total = db.scalar(select(func.count()).select_from(ConsultationSession).where(*conditions)) or 0
    sessions = list(
        db.scalars(
            select(ConsultationSession)
            .where(*conditions)
            .order_by(*order_by)
            .offset((page_no - 1) * page_size)
            .limit(page_size)
        ).all()
    )

    session_ids = [s.id for s in sessions]
    count_map = _count_by_sessions(db, session_ids)
    last_map = _last_message_by_sessions(db, session_ids)
    user_map = _load_users(db, sessions) if with_user_info else {}
    risk_map = _risk_by_sessions(db, session_ids)

    now = datetime.now()
    rows: list[SessionRow] = []
    for s in sessions:
        row = SessionRow(
            id=s.id,
            user_id=s.user_id,
            session_title=s.session_title,
            started_at=_dt(s.started_at),
            last_emotion_analysis=s.last_emotion_analysis,
            last_message_content=preview(last_map.get(s.id)),
            message_count=count_map.get(s.id, 0),
            duration_minutes=(
                max(1, int((now - s.started_at).total_seconds() // 60)) if s.started_at else 0
            ),
        )
        if with_user_info:
            u = user_map.get(s.user_id or 0)
            row.username = u.username if u else None
            row.nickname = u.nickname if u else None
            risk = risk_map.get(s.id)
            row.risk_level = risk["level"] if risk else None
            row.crisis_count = risk["count"] if risk else 0
        rows.append(row)

    return {"records": rows, "total": total}


def _count_by_sessions(db: Session, session_ids: list[int]) -> dict[int, int]:
    if not session_ids:
        return {}
    rows = db.execute(
        select(ConsultationMessage.session_id, func.count())
        .where(ConsultationMessage.session_id.in_(session_ids))
        .group_by(ConsultationMessage.session_id)
    ).all()
    return {sid: total for sid, total in rows if sid is not None}


def _last_message_by_sessions(db: Session, session_ids: list[int]) -> dict[int, str]:
    """每个会话的最后一条消息内容。

    先按 (session_id, created_at) 取，再在 Python 侧取每个会话的最新一条 ——
    比在 SQL 里做窗口函数更好移植，数据量受分页上限保护（最多 50 个会话）。
    """
    if not session_ids:
        return {}
    rows = db.execute(
        select(ConsultationMessage.session_id, ConsultationMessage.content, ConsultationMessage.created_at)
        .where(ConsultationMessage.session_id.in_(session_ids))
        # id 兜底：同秒消息顺序必须稳定，否则「最后一条」可能取错
        .order_by(ConsultationMessage.session_id, ConsultationMessage.created_at, ConsultationMessage.id)
    ).all()

    result: dict[int, str] = {}
    for sid, content, _created in rows:
        if sid is not None:
            result[sid] = content or ""
    return result


def _risk_by_sessions(db: Session, session_ids: list[int]) -> dict[int, dict[str, int]]:
    """每个会话触发过的最高危机等级与事件数。

    有了它，咨询记录才能从「按时间浏览」变成「按要不要关心排序」——
    否则有风险的会话会被淹没在大量日常闲聊里。
    """
    if not session_ids:
        return {}
    rows = db.execute(
        select(
            CrisisEvent.session_id,
            func.max(CrisisEvent.level),
            func.count(),
        )
        .where(CrisisEvent.session_id.in_(session_ids))
        .group_by(CrisisEvent.session_id)
    ).all()
    return {
        sid: {"level": int(level or 0), "count": int(n or 0)}
        for sid, level, n in rows
        if sid is not None
    }


def _load_users(db: Session, sessions: list[ConsultationSession]) -> dict[int, User]:
    user_ids = list({s.user_id for s in sessions if s.user_id})
    if not user_ids:
        return {}
    return {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()}


# ===========================================================================
# 消息
# ===========================================================================


def list_messages(db: Session, session_id: int) -> list[MessageRow]:
    messages = list(
        db.scalars(
            select(ConsultationMessage)
            .where(ConsultationMessage.session_id == session_id)
            # ⚠️ 必须带 id 兜底：created_at 在 MySQL 里是秒级 DATETIME，
            #    AI 短回复经常和用户消息落在同一秒，没有次级键时返回顺序不确定，
            #    用户消息和 AI 回复可能显示颠倒（SQLite 测试发现不了）。
            .order_by(ConsultationMessage.created_at.asc(), ConsultationMessage.id.asc())
        ).all()
    )
    return [
        MessageRow(
            id=m.id,
            session_id=m.session_id,
            sender_type=m.sender_type,
            sender_type_desc=m.sender_type_desc(),
            message_type=m.message_type,
            content=m.content,
            emotion_tag=m.emotion_tag,
            ai_model=m.ai_model,
            created_at=_dt(m.created_at),
        )
        for m in messages
    ]


def delete_session(db: Session, session_id: int) -> None:
    """级联删除会话及其消息，同一事务内完成，避免半截数据。"""
    for m in db.scalars(
        select(ConsultationMessage).where(ConsultationMessage.session_id == session_id)
    ).all():
        db.delete(m)
    session = db.get(ConsultationSession, session_id)
    if session is not None:
        db.delete(session)
    db.commit()


# ===========================================================================
# 消息写入（供 SSE 流程调用）
# ===========================================================================


def save_user_message(db: Session, session_id: int, content: str | None, emotion_tag: str | None = None) -> ConsultationMessage:
    msg = ConsultationMessage(
        session_id=session_id,
        sender_type=1,
        message_type=1,
        content=content,
        emotion_tag=emotion_tag,
        created_at=datetime.now(),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def save_ai_message(db: Session, session_id: int, content: str, ai_model: str | None) -> ConsultationMessage:
    msg = ConsultationMessage(
        session_id=session_id,
        sender_type=2,
        message_type=1,
        content=content,
        ai_model=ai_model,
        created_at=datetime.now(),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def message_count(db: Session, session_id: int) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(ConsultationMessage)
            .where(ConsultationMessage.session_id == session_id)
        )
        or 0
    )


def last_message(db: Session, session_id: int) -> ConsultationMessage | None:
    return db.scalar(
        select(ConsultationMessage)
        .where(ConsultationMessage.session_id == session_id)
        # id 兜底的原因同 list_messages：同秒消息的顺序必须稳定
        .order_by(ConsultationMessage.created_at.desc(), ConsultationMessage.id.desc())
        .limit(1)
    )
