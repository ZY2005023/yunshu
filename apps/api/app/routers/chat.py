"""心理咨询路由 —— 7 个接口（本次实现 6 个，SSE 流式单独一轮）。

| 权限 | 路径                                                    |
|------|---------------------------------------------------------|
| 🔑   | POST   /api/psychological-chat/session/start             |
| 🔑   | POST   /api/psychological-chat/stream        ← SSE，待实现 |
| 🔑   | GET    /api/psychological-chat/sessions                  |
| 👑   | GET    /api/psychological-chat/admin/sessions            |
| 👤   | DELETE /api/psychological-chat/sessions/{sessionId}      |
| 👤   | GET    /api/psychological-chat/sessions/{sessionId}/messages |
| 👤   | GET    /api/psychological-chat/session/{sessionId}/emotion   |

⚠️ 注意最后一条的路径是**单数 session**，倒数第二条是**复数 sessions**。
原版就是不一致的，**不要"顺手修正"** —— 前端按现有路径调用。

👤 = 会话本人或管理员
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.crisis import detect
from app.core.result import Result
from app.deps import CurrentUser, get_current_user, get_db, require_admin
from app.schemas import (
    EmotionOut,
    MessagesOut,
    SessionStartIn,
    SessionStartOut,
    StreamIn,
)
from app.services import consultation as consultation_service
from app.services import crisis as crisis_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/psychological-chat", tags=["心理咨询"])

SESSION_TTL_MILLIS = 86_400_000  # 会话有效期 24 小时


def _parse_json(raw: str | None):
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


@router.post("/session/start", response_model=Result[SessionStartOut], summary="新建会话")
def start_session(
    payload: SessionStartIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[SessionStartOut]:
    from app.core.exceptions import BusinessError

    session = consultation_service.create_session(db, user.user_id, payload.session_title)
    if session is None:
        raise BusinessError("创建会话失败，请稍后重试")

    consultation_service.save_user_message(db, session.id, payload.initial_message, None)

    # 首条消息往往是风险最高的一段表达，必须走一次规则层检测
    signal = detect(payload.initial_message)
    if signal.is_crisis:
        crisis_service.record_if_needed(
            db, user.user_id, session.id, None, "CHAT", signal, payload.initial_message
        )

    now_ms = int(time.time() * 1000)
    return Result.ok(
        SessionStartOut(
            session_id=f"session_{session.id}",
            user_hash=user.user_id,
            initial_message=payload.initial_message,
            start_time=now_ms,
            expiry_time=now_ms + SESSION_TTL_MILLIS,
            message_count=1,
            status="ACTIVE",
        )
    )


@router.get("/sessions", response_model=Result[dict], summary="我的会话列表")
def my_sessions(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    # ⚠️ 必须写 alias：前端传的是 currentPage，不写的话参数收不到，
    #    永远返回第 1 页（而且不报错，很难发现）
    current_page: Annotated[int, Query(alias="currentPage", ge=1)] = 1,
    size: Annotated[int, Query(ge=1)] = 10,
) -> Result[dict]:
    """只返回当前用户自己的会话（不带 username/nickname）。"""
    return Result.ok(consultation_service.page_of_user(db, user.user_id, current_page, size))


@router.get("/admin/sessions", response_model=Result[dict], summary="全站会话列表")
def all_sessions(
    _admin: Annotated[CurrentUser, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    # ⚠️ 必须写 alias：前端传的是 currentPage，不写的话参数收不到，
    #    永远返回第 1 页（而且不报错，很难发现）
    current_page: Annotated[int, Query(alias="currentPage", ge=1)] = 1,
    size: Annotated[int, Query(ge=1)] = 10,
    keyword: str | None = None,
    risk_first: Annotated[bool, Query(alias="riskFirst")] = False,
    risk_only: Annotated[bool, Query(alias="riskOnly")] = False,
) -> Result[dict]:
    """管理端，附带用户名/昵称与风险标记。

    - `keyword`：匹配会话标题 / 用户名 / 昵称 / 消息正文
    - `riskFirst`：有风险的会话排在最前（默认仍是时间倒序）
    - `riskOnly`：只看产生过危机事件的会话
    """
    return Result.ok(
        consultation_service.page_of_all(
            db, current_page, size, keyword, risk_first, risk_only
        )
    )


@router.delete("/sessions/{session_id}", response_model=Result[None], summary="删除会话")
def delete_session(
    session_id: Annotated[str, Path()],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[None]:
    """**幂等**：解析不出主键（尚未落库的临时会话）直接返回成功。"""
    db_id = consultation_service.parse_session_id(session_id)
    if db_id is None:
        return Result.ok()
    consultation_service.require_accessible(db, db_id, user.user_id, user.is_admin)
    consultation_service.delete_session(db, db_id)
    return Result.ok()


@router.get(
    "/sessions/{session_id}/messages",
    response_model=Result[MessagesOut],
    summary="会话消息列表",
)
def session_messages(
    session_id: Annotated[str, Path()],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[MessagesOut]:
    db_id = consultation_service.parse_session_id(session_id)
    if db_id is None:
        return Result.ok(MessagesOut(session_id=session_id, messages=[]))
    consultation_service.require_accessible(db, db_id, user.user_id, user.is_admin)
    return Result.ok(
        MessagesOut(
            session_id=session_id,
            messages=consultation_service.list_messages(db, db_id),
        )
    )


@router.get(
    "/session/{session_id}/emotion",
    response_model=Result[EmotionOut],
    summary="会话情绪分析",
)
def session_emotion(
    session_id: Annotated[str, Path()],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Result[EmotionOut]:
    """⚠️ 路径是单数 `session`，与上面复数 `sessions` 不同（原版如此）。"""
    db_id = consultation_service.parse_session_id(session_id)
    analysis = None
    if db_id is not None:
        session = consultation_service.require_accessible(db, db_id, user.user_id, user.is_admin)
        analysis = _parse_json(session.last_emotion_analysis)
    return Result.ok(EmotionOut(session_id=session_id, emotion_analysis=analysis))


@router.get("/agents", response_model=Result[list[dict]], summary="Agent 清单")
def agents(
    _user: Annotated[CurrentUser, Depends(get_current_user)],
) -> Result[list[dict]]:
    """五类 Agent 的名称与说明（前端展示、排障用）。"""
    from app.core.agent import all_agents

    return Result.ok(all_agents())


# ===========================================================================
# SSE 流式对话
#
# ⚠️ 整个迁移最容易出错的地方，四条铁律（缺一条前端就坏）：
#   1. 事件名恰好是 crisis / message / done / error，不能多也不能少
#   2. **done 的 data 是裸 "{}"**，不是 Result 包装 —— 前端可能直接判空对象
#   3. 每段之间延时 50ms。少了不会报错，但前端被碎片冲垮（UI 卡死）
#   4. AI 异常要降级成一条 error 事件，绝不能让连接裸崩
# ===========================================================================

DELAY_SECONDS = 0.05  # 对应原版 delayElements(Duration.ofMillis(50))


def _sse(event: str, data: str) -> str:
    """SSE 报文。结尾必须是两个换行，否则浏览器不会派发事件。"""
    return f"event: {event}\ndata: {data}\n\n"


@dataclass
class ChatPreparation:
    db_session_id: int
    user_id: int
    signal: object


def prepare(db: Session, db_session_id: int, user_id: int, user_message: str) -> ChatPreparation:
    """流式对话前的准备：保存用户消息 + 规则层危机检测。

    放在 AI 调用**之前**、且在同一个请求内同步完成 —— 这样 controller 才能在
    AI 应答之前先把危机求助卡片推给前端。
    """
    # 去重判据是「最后一条就是本人发的同一句话」，不能只看 message_count == 1：
    # AI 上游失败后用户重发同一条时，count 已不止 1，旧判据会把同一句
    # 再存一遍（库里和模型记忆里各出现两次，模型会以为用户说了两遍）。
    # AI 正常回复后再发相同内容不受影响 —— 那时最后一条是 AI 回复。
    last = consultation_service.last_message(db, db_session_id)
    already_saved = (
        last is not None
        and last.sender_type == 1
        and last.content == user_message
    )

    if not already_saved:
        consultation_service.save_user_message(db, db_session_id, user_message, None)

    signal = detect(user_message)
    if signal.is_crisis:
        crisis_service.record_if_needed(
            db, user_id, db_session_id, None, "CHAT", signal, user_message
        )
    return ChatPreparation(db_session_id, user_id, signal)


def _crisis_data(level: int) -> str:
    """危机求助卡片。内容全部来自固定常量，不依赖模型输出。"""
    return Result.ok(
        {
            "level": level,
            "title": crisis_service.CARD_TITLE,
            "subtitle": crisis_service.CARD_SUBTITLE,
            "helplines": crisis_service.HELPLINES,
            "disclaimer": crisis_service.DISCLAIMER,
        }
    ).model_dump_json()


async def _error_only(message: str) -> AsyncIterator[str]:
    yield _sse("error", Result.error("500", message, None).model_dump_json())


async def _event_stream(
    db: Session, prep: ChatPreparation, session_id: str, user_message: str
) -> AsyncIterator[str]:
    from app.core.agent import route as agent_route
    from app.services import ai as ai_service
    from app.services import rag as rag_service

    # 1) 危机卡片先发（不受 AI 回复影响，也不会被后续 message 覆盖）
    if getattr(prep.signal, "is_crisis", False):
        yield _sse("crisis", _crisis_data(prep.signal.level))
        await asyncio.sleep(DELAY_SECONDS)

    # 2) 意图路由：决定这一轮由哪类 Agent 应答，并告诉前端
    decision = agent_route(user_message)
    yield _sse("agent", Result.ok(decision.as_payload()).model_dump_json())
    await asyncio.sleep(DELAY_SECONDS)

    # 3) RAG：检索知识库，命中则把资料拼进提示词，并先告诉前端来源
    retrieved = rag_service.retrieve(db, user_message)
    # 顺序有讲究：先场景约束（agent），再参考资料（RAG）
    prompt_extra = decision.prompt_clause() + rag_service.build_context(retrieved)
    if retrieved:
        yield _sse(
            "sources",
            Result.ok({"sources": rag_service.sources_payload(retrieved)}).model_dump_json(),
        )
        await asyncio.sleep(DELAY_SECONDS)

    # 4) AI 流式片段
    conversation_id = ai_service.conversation_id_of(session_id)
    chunks: list[str] = []
    try:
        async for chunk in ai_service.stream_reply(conversation_id, user_message, prompt_extra):
            chunks.append(chunk)
            yield _sse(
                "message",
                Result.ok({"content": chunk, "type": "normal"}).model_dump_json(),
            )
            await asyncio.sleep(DELAY_SECONDS)
    except Exception as exc:  # noqa: BLE001
        # 上游异常（网络/超时/额度）降级为一条可读提示
        logger.warning("AI 流式异常: sessionId=%s, msg=%s", session_id, exc)
        yield _sse(
            "error",
            Result.error("500", "AI 服务暂时不可用，请稍后再试", None).model_dump_json(),
        )
        await asyncio.sleep(DELAY_SECONDS)
        return

    # 3) 落库 + 写记忆（失败只记日志，不影响已经吐给用户的内容）
    reply = "".join(chunks)
    try:
        if reply.strip():
            ai_service.remember_reply(conversation_id, reply)
            consultation_service.save_ai_message(
                db, prep.db_session_id, ai_service.truncate_reply(reply), _model_name()
            )
        else:
            logger.warning("AI 返回内容为空，跳过落库: sessionId=%s", session_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("AI 回复落库失败: sessionId=%s, msg=%s", session_id, exc)

    # 4) 结束事件（注意 data 是裸 {}）
    yield _sse("done", "{}")


def _model_name() -> str:
    from app.core.config import settings

    return settings.ai.model


@router.post("/stream", summary="流式对话（SSE）")
async def stream_chat(
    payload: StreamIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    """返回 text/event-stream。事件序列：crisis? → message* → done | error。"""
    from app.core.exceptions import BusinessError
    from app.core.ratelimit import ai_limiter

    # 限流：AI 接口按用户维度限制频率，防止脚本刷额度
    ai_limiter.check(f"user:{user.user_id}")

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

    db_id = consultation_service.parse_session_id(payload.session_id)
    if db_id is None:
        return StreamingResponse(
            _error_only("会话ID格式错误，请新建会话后重试"),
            media_type="text/event-stream",
            headers=headers,
        )

    try:
        consultation_service.require_accessible(db, db_id, user.user_id, user.is_admin)
    except BusinessError as exc:
        return StreamingResponse(
            _error_only(exc.msg), media_type="text/event-stream", headers=headers
        )

    prep = prepare(db, db_id, user.user_id, payload.user_message)
    return StreamingResponse(
        _event_stream(db, prep, payload.session_id, payload.user_message),
        media_type="text/event-stream",
        headers=headers,
    )
