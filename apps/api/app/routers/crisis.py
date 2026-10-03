"""危机预警路由 —— **全部需要 ADMIN**。

原版是类级 `@PreAuthorize("hasRole('ADMIN')")`，
所以这里每个路由都挂 `require_admin`，别漏。

整改（2026-10-02）新增三个接口，都是为了回答同一个问题：
**管理员拿到工单后，"这人是谁 / 到底发生了什么 / 我该做什么"能不能一屏看全。**
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.result import Result
from app.deps import CurrentUser, get_db, require_admin
from app.schemas import (
    CrisisContextOut,
    CrisisFollowUpIn,
    CrisisFollowUpOut,
    CrisisHandleIn,
    CrisisResourcesOut,
)
from app.services import crisis as crisis_service

router = APIRouter(prefix="/api/admin/crisis", tags=["危机预警"])


@router.get("/page", response_model=Result[dict], summary="危机事件分页")
def page(
    _admin: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    current_page: Annotated[int, Query(alias="currentPage", ge=1)] = 1,
    size: Annotated[int, Query(ge=1)] = 10,
    status: str | None = None,
    level: int | None = None,
    keyword: str | None = None,
) -> Result[dict]:
    """⚠️ size 上限是 **50**（不是全局的 100），原版硬编码如此。

    排序为**等级优先**（3 级永远在最上面），同级内按时间倒序 ——
    否则 1 级误报会和 3 级真警混在同一屏。

    `keyword` 按账号/昵称过滤，供咨询记录「查看该用户工单」跳转使用。
    """
    data = crisis_service.page(db, current_page, size, status, level, keyword)
    return Result.ok(
        {
            "records": crisis_service.enrich_rows(db, list(data["records"])),
            "total": data["total"],
        }
    )


@router.get("/pending/count", response_model=Result[int], summary="待处理数量")
def pending_count(
    _admin: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[int]:
    return Result.ok(crisis_service.pending_count(db))


@router.get("/{event_id}/context", response_model=Result[CrisisContextOut], summary="工单处置上下文")
def context(
    event_id: int,
    _admin: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[CrisisContextOut]:
    """一屏返回处置所需的一切：用户画像 / 历史工单 / 量表 / 日记趋势 /
    触发原文（完整不截断）/ 跟进记录 / 处置清单。

    路由匹配无冲突：`/resources` 与 `/pending/count` 是固定路径且段数不同，
    不会被 `/{event_id}/...` 抢走（`/pending/count` 虽同为两段，但注册在前）。
    """
    return Result.ok(crisis_service.context_of(db, event_id))


@router.get(
    "/{event_id}/follow-ups",
    response_model=Result[list[CrisisFollowUpOut]],
    summary="工单跟进记录",
)
def follow_ups(
    event_id: int,
    _admin: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[list[CrisisFollowUpOut]]:
    return Result.ok([CrisisFollowUpOut(**f) for f in crisis_service.list_follow_ups(db, event_id)])


@router.post(
    "/{event_id}/follow-ups",
    response_model=Result[None],
    summary="追加跟进记录",
)
def add_follow_up(
    event_id: int,
    payload: CrisisFollowUpIn,
    admin: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[None]:
    """处置不是一次性的：联系 → 观察 → 复查 → 转介 → 关闭。

    对已关闭的工单追加跟进会自动把它拉回「处理中」，
    避免"看起来结案了但其实没人再跟进"。
    """
    crisis_service.add_follow_up(db, event_id, admin.user_id, payload.content)
    return Result.ok()


@router.post("/{event_id}/handle", response_model=Result[None], summary="处置危机事件")
def handle(
    event_id: int,
    payload: CrisisHandleIn,
    admin: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[None]:
    """status 为空时默认 RESOLVED；只有 PENDING/HANDLING 可处置。

    measures 是结构化的「已采取措施」编码，非法编码会直接报错
    （不能静默丢弃 —— 否则管理员以为勾了「已通知家长」而库里没记录）。
    """
    crisis_service.handle(
        db, event_id, admin.user_id, payload.status, payload.handle_note, payload.measures
    )
    return Result.ok()


@router.get("/resources", response_model=Result[CrisisResourcesOut], summary="求助资源")
def resources(
    _admin: Annotated[CurrentUser, Depends(require_admin)],
) -> Result[CrisisResourcesOut]:
    """固定内容，不依赖 AI 输出。"""
    data = crisis_service.resources()
    return Result.ok(
        CrisisResourcesOut(
            title=data["title"],
            subtitle=data["subtitle"],
            helplines=data["helplines"],
            disclaimer=data["disclaimer"],
        )
    )


__all__ = ["router"]
