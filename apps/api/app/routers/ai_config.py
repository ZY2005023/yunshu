"""API 管理路由 —— AI 服务配置（管理端，全部需要 ADMIN）。

参考 one-api / new-api 渠道管理的形态：
· GET  /api/admin/ai-config       当前生效配置（密钥只有掩码 + 来源徽标）
· PUT  /api/admin/ai-config       保存配置，**即时生效**（不重启）
· POST /api/admin/ai-config/test  一键测试连通性（极小请求，回显时延与回复）

⚠️ 为什么密钥响应里永远只有掩码：管理端 XSS 一旦得手，回显原文等于
把最高价值凭据送给攻击者（这个项目所有 v-html 都过白名单，但纵深防御
的原则是——能不给的信息就不给）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.result import Result
from app.deps import CurrentUser, get_db, require_admin
from app.schemas import AiConfigOut, AiConfigTestOut, AiConfigUpdateIn
from app.services import ai_config as ai_config_service

router = APIRouter(prefix="/api/admin/ai-config", tags=["API 管理"])


@router.get("", response_model=Result[AiConfigOut], summary="当前 AI 服务配置")
def get_config(
    _admin: Annotated[CurrentUser, Depends(require_admin)],
) -> Result[AiConfigOut]:
    """密钥只露尾 4 位；sources 标明每个字段来自数据库还是环境变量。"""
    return Result.ok(AiConfigOut(**ai_config_service.get_config()))


@router.put("", response_model=Result[AiConfigOut], summary="保存 AI 服务配置")
def update_config(
    payload: AiConfigUpdateIn,
    _admin: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[AiConfigOut]:
    """部分更新：空字段保持原值；api_key 留空 = 不修改现有 Key。

    保存即生效 —— 后续的对话 / 日记分析 / 连通性测试都会立即用新配置，
    不需要重启服务。
    """
    return Result.ok(AiConfigOut(**ai_config_service.update_config(db, payload)))


@router.post("/test", response_model=Result[AiConfigTestOut], summary="测试连通性")
async def test_config(
    _admin: Annotated[CurrentUser, Depends(require_admin)],
) -> Result[AiConfigTestOut]:
    """用当前生效配置发一个极小请求。失败也返回 200 + ok=false，
    错误信息已翻译成管理员能看懂的一句话（401/404/超时/连不上）。"""
    return Result.ok(AiConfigTestOut(**await ai_config_service.test_connection()))


__all__ = ["router"]
