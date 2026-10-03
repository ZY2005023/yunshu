"""数据看板路由 —— 1 个接口，需要 ADMIN。

原版是类级 `@PreAuthorize("hasRole('ADMIN')")`。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.result import Result
from app.deps import CurrentUser, get_db, require_admin
from app.schemas import AnalyticsOverview
from app.services import analytics as analytics_service

router = APIRouter(prefix="/api/data-analytics", tags=["数据看板"])


@router.get("/overview", response_model=Result[AnalyticsOverview], summary="综合概览")
def overview(
    _admin: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[AnalyticsOverview]:
    return Result.ok(analytics_service.overview(db))
