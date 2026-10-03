"""标准化量表路由 —— 5 个接口（P2-6）。

| 权限 | 路径                      | 说明         |
|------|---------------------------|--------------|
| 🔑   | GET  /api/scale/questions | 下发题目     |
| 🔑   | POST /api/scale/submit    | 提交并计分   |
| 🔑   | GET  /api/scale/my        | 我的历史     |
| 🔑   | GET  /api/scale/my/latest | 最近一次     |
| 🔑   | GET  /api/scale/trend     | 分数趋势     |

题目文案由后端统一下发（前端不内置），避免两端各写一份导致不一致 ——
量表的措辞改变会影响结果可比性。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.result import Result
from app.deps import CurrentUser, get_current_user, get_db, require_admin
from app.schemas import (
    ScaleHistoryRow,
    ScaleQuestionsOut,
    ScaleResultOut,
    ScaleSubmitIn,
    ScaleTrendPoint,
)
from app.services import scale as scale_service

router = APIRouter(prefix="/api/scale", tags=["心理量表"])


@router.get("/questions", response_model=Result[ScaleQuestionsOut], summary="量表题目")
def get_questions(
    _user: Annotated[CurrentUser, Depends(get_current_user)],
    code: Annotated[str, Query(description="PHQ9 或 GAD7")] = "PHQ9",
) -> Result[ScaleQuestionsOut]:
    return Result.ok(scale_service.questions(code))


@router.post("/submit", response_model=Result[ScaleResultOut], summary="提交量表")
def submit(
    payload: ScaleSubmitIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[ScaleResultOut]:
    """计分并落库。PHQ-9 第 9 题 > 0 时会同时补记一条危机事件。"""
    return Result.ok(
        scale_service.submit(db, user.user_id, payload.scale_code, payload.answers)
    )


@router.get("/my", response_model=Result[list[ScaleHistoryRow]], summary="我的量表历史")
def my_history(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    code: Annotated[str | None, Query()] = None,
) -> Result[list[ScaleHistoryRow]]:
    return Result.ok(scale_service.my_history(db, user.user_id, code))


@router.get("/my/latest", response_model=Result[ScaleResultOut | None], summary="最近一次结果")
def my_latest(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    code: Annotated[str, Query()] = "PHQ9",
) -> Result[ScaleResultOut | None]:
    """没做过该量表时返回 code=200 + data=null。"""
    return Result.ok(scale_service.latest(db, user.user_id, code))


@router.get("/trend", response_model=Result[list[ScaleTrendPoint]], summary="分数趋势")
def trend(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    code: Annotated[str | None, Query()] = None,
) -> Result[list[ScaleTrendPoint]]:
    """按日期升序，供前端画折线图。"""
    return Result.ok(scale_service.trend(db, user.user_id, code))


@router.get("/admin/page", response_model=Result[dict], summary="量表记录分页（管理端）")
def admin_page(
    _admin: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    current_page: Annotated[int, Query(alias="currentPage", ge=1)] = 1,
    size: Annotated[int, Query(ge=1)] = 10,
    code: Annotated[str | None, Query()] = None,
    only_self_harm: Annotated[bool, Query(alias="onlySelfHarm")] = False,
) -> Result[dict]:
    """`onlySelfHorm=true` 只看自伤项命中的记录，方便优先跟进。"""
    return Result.ok(
        scale_service.admin_page(db, current_page, size, code, only_self_harm)
    )
