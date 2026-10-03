"""量表业务：题目下发 / 计分落库 / 历史与趋势。

★ 与危机系统的接线点：
    PHQ-9 第 9 题（自伤念头）得分 > 0 时，落库后**立即**补记一条危机事件
    （source = "SCALE"）。这是"规则层"的第三条触发路径 ——
    前两条是聊天文本和日记正文，这条来自结构化量表，可靠性更高
    （用户是明确勾选的，不是模型从文本里推断的）。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import scale as scale_core
from app.core.crisis import CrisisSignal
from app.core.exceptions import BusinessError
from app.models import ScaleRecord, User
from app.schemas import (
    ScaleAdminRow,
    ScaleHistoryRow,
    ScaleQuestionsOut,
    ScaleResultOut,
    ScaleTrendPoint,
)
from app.services import crisis as crisis_service

# 第 9 题得分 → 危机等级。
# 1 分（好几天）已足以预警；2 分及以上直接按危机处理。
SELF_HARM_LEVEL_BY_SCORE: dict[int, int] = {1: 2, 2: 3, 3: 3}

CRISIS_SOURCE = "SCALE"


def _dt(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def questions(code: str) -> ScaleQuestionsOut:
    """下发题目与选项。未知量表抛业务异常。"""
    try:
        qs = scale_core.questions_of(code)
        normalized = code.upper()
    except ValueError as exc:
        raise BusinessError(str(exc)) from exc

    entry = scale_core.SUPPORTED_SCALES[normalized]
    return ScaleQuestionsOut(
        code=normalized,
        name=entry[0],  # type: ignore[index]
        questions=list(qs),
        options=list(scale_core.OPTIONS),
        disclaimer=scale_core.DISCLAIMER,
    )


def submit(db: Session, user_id: int, code: str, answers: list[int]) -> ScaleResultOut:
    """计分并落库。答案非法时抛业务异常（不暴露内部细节）。"""
    try:
        result = scale_core.score(code, answers)
    except ValueError as exc:
        raise BusinessError(str(exc)) from exc

    record = ScaleRecord(
        user_id=user_id,
        scale_code=result.code,
        scale_name=result.name,
        answers=json.dumps(result.answers, ensure_ascii=False),
        total_score=result.total,
        level=result.level,
        self_harm_score=result.self_harm_score,
        self_harm_risk=1 if result.self_harm_risk else 0,
        created_at=datetime.now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # ★ 自伤念头：无论总分多少都要留痕
    if result.self_harm_risk:
        level = SELF_HARM_LEVEL_BY_SCORE.get(result.self_harm_score, 3)
        crisis_service.record_if_needed(
            db,
            user_id,
            None,
            None,
            CRISIS_SOURCE,
            CrisisSignal(
                level=level,
                trigger_type="SCALE",
                matched_terms=[f"{result.code}-Q{scale_core.PHQ9_SELF_HARM_INDEX + 1}"],
            ),
            f"{result.code} 自伤项得分 {result.self_harm_score}（总分 {result.total}）",
        )

    return _to_out(record, result.answers)


def _to_out(record: ScaleRecord, answers: list[int] | None = None) -> ScaleResultOut:
    if answers is None:
        try:
            answers = json.loads(record.answers or "[]")
        except (ValueError, TypeError):
            answers = []
    return ScaleResultOut(
        code=record.scale_code or "",
        name=record.scale_name or "",
        total=record.total_score or 0,
        level=record.level or "",
        answers=answers,
        max_total=(
            scale_core.PHQ9_MAX_TOTAL if record.scale_code == scale_core.PHQ9_CODE else scale_core.GAD7_MAX_TOTAL
        ),
        self_harm_risk=bool(record.self_harm_risk),
        self_harm_score=record.self_harm_score or 0,
        disclaimer=scale_core.DISCLAIMER,
        created_at=_dt(record.created_at),
    )


def my_history(db: Session, user_id: int, code: str | None = None) -> list[ScaleHistoryRow]:
    conditions = [ScaleRecord.user_id == user_id]
    if code:
        try:
            conditions.append(ScaleRecord.scale_code == code.upper())
        except (ValueError, AttributeError):
            pass

    records = list(
        db.scalars(
            select(ScaleRecord)
            .where(*conditions)
            .order_by(ScaleRecord.created_at.desc())
        ).all()
    )
    return [
        ScaleHistoryRow(
            id=r.id,
            scale_code=r.scale_code,
            scale_name=r.scale_name,
            total_score=r.total_score,
            level=r.level,
            self_harm_risk=bool(r.self_harm_risk),
            created_at=_dt(r.created_at),
        )
        for r in records
    ]


def latest(db: Session, user_id: int, code: str) -> ScaleResultOut | None:
    record = db.scalar(
        select(ScaleRecord)
        .where(ScaleRecord.user_id == user_id, ScaleRecord.scale_code == code.upper())
        .order_by(ScaleRecord.created_at.desc())
        .limit(1)
    )
    return _to_out(record) if record else None


def trend(db: Session, user_id: int, code: str | None = None) -> list[ScaleTrendPoint]:
    """按日期升序的趋势，用于画折线图。"""
    rows = my_history(db, user_id, code)
    # my_history 是倒序，这里翻回来
    return [
        ScaleTrendPoint(
            date=(r.created_at or "")[:10],
            scale_code=r.scale_code,
            total_score=r.total_score,
            level=r.level,
        )
        for r in reversed(rows)
    ]


def admin_page(
    db: Session,
    current_page: int = 1,
    size: int = 10,
    code: str | None = None,
    only_self_harm: bool = False,
) -> dict[str, Any]:
    """管理端分页。`only_self_harm=True` 只看自伤项命中的记录 ——
    这是心理老师最需要优先跟进的一批。
    """
    from sqlalchemy import func

    conditions = []
    if code:
        conditions.append(ScaleRecord.scale_code == code.upper())
    if only_self_harm:
        conditions.append(ScaleRecord.self_harm_risk == 1)

    total = db.scalar(select(func.count()).select_from(ScaleRecord).where(*conditions)) or 0
    page_size = min(max(1, size), 100)
    records = list(
        db.scalars(
            select(ScaleRecord)
            .where(*conditions)
            .order_by(ScaleRecord.created_at.desc())
            .offset((max(1, current_page) - 1) * page_size)
            .limit(page_size)
        ).all()
    )

    user_ids = list({r.user_id for r in records if r.user_id})
    users: dict[int, User] = {}
    if user_ids:
        users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()}

    rows = []
    for r in records:
        u = users.get(r.user_id or 0)
        rows.append(
            ScaleAdminRow(
                id=r.id,
                user_id=r.user_id,
                username=u.username if u else None,
                nickname=u.nickname if u else None,
                scale_code=r.scale_code,
                scale_name=r.scale_name,
                total_score=r.total_score,
                level=r.level,
                self_harm_risk=bool(r.self_harm_risk),
                created_at=_dt(r.created_at),
            )
        )
    return {"records": rows, "total": total}
