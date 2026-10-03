"""情绪日记路由 —— 4 个接口。

| 权限 | 路径                                     |
|------|------------------------------------------|
| 🔑   | POST   /api/emotion-diary                 |
| 🔑   | GET    /api/emotion-diary/my              |
| 👑   | GET    /api/emotion-diary/admin/page      |
| 👑   | DELETE /api/emotion-diary/admin/{id}      |
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.core.result import Result
from app.deps import CurrentUser, get_current_user, get_db, require_admin
from app.schemas import DiaryIn, DiaryOut, DiaryQuery, DiaryRow
from app.services import diary as diary_service

router = APIRouter(prefix="/api/emotion-diary", tags=["情绪日记"])


@router.post("", response_model=Result[DiaryOut], summary="创建或更新日记")
async def save_diary(
    payload: DiaryIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[DiaryOut]:
    """同一用户同一天一条。

    保存后调 AI 做情绪分析并回填 `aiEmotionAnalysis`；
    模型 `riskLevel >= 2` 时补记危机事件。**AI 失败不影响保存**。
    响应额外带 `crisisLevel`（规则层命中等级），前端据此展示求助卡 ——
    与对话的 crisis 事件、量表的自伤 alert 对齐。
    """
    from app.core.ratelimit import ai_limiter

    # 日记保存会触发一次 AI 分析，与对话流同用 AI 限流额度
    ai_limiter.check(f"user:{user.user_id}")
    diary, crisis_level = diary_service.create_or_update(db, user.user_id, payload)
    await diary_service.analyze_and_attach(db, user.user_id, diary)
    out = DiaryOut.model_validate(diary)
    out.crisis_level = crisis_level
    return Result.ok(out)


@router.get("/my", response_model=Result[list[DiaryRow]], summary="我的日记列表")
def my_diaries(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[list[DiaryRow]]:
    return Result.ok(diary_service.my_list(db, user.user_id))


@router.get("/admin/page", response_model=Result[dict], summary="管理端日记分页")
def admin_page(
    query: Annotated[DiaryQuery, Depends()],
    _admin: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[dict]:
    return Result.ok(diary_service.admin_page(db, query))


@router.delete("/admin/{diary_id}", response_model=Result[None], summary="删除日记")
def admin_delete(
    diary_id: Annotated[int, Path()],
    _admin: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[None]:
    diary_service.delete(db, diary_id)
    return Result.ok()
