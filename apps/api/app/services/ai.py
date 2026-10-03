"""AI 服务 —— DeepSeek 调用 + 多轮记忆 + 流式输出。

对齐 Java 版 `PsychologicalSupportService` + `PromptManage` + `CrisisResources`。

与原版的映射关系：

| Java (Spring AI)                       | Python                          |
|----------------------------------------|---------------------------------|
| `ChatClient.prompt().user().stream()`  | `AsyncOpenAI.chat.completions`  |
| `ChatMemory` + `MessageChatMemoryAdvisor` | `ConversationMemory`（下方）  |
| `doOnNext` / `doOnComplete` 副作用     | async generator 的循环体与收尾  |
| `onErrorResume` 降级                   | 上层 try/except 发 error 事件   |

模型走 DeepSeek —— 它兼容 OpenAI 协议，换个 base_url 即可，不需要 LangChain。
这个项目的 AI 调用本质就是一次 HTTP + 一段历史，引入 LangChain 是净负担。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# ===========================================================================
# 系统提示词（逐字对齐 PromptManage.PSYCHOLOGICAL_SUPPORT_SYSTEM_PROMPT）
# ===========================================================================

PSYCHOLOGICAL_SUPPORT_SYSTEM_PROMPT = (
    "你是一位专业、温暖、有同理心的AI心理健康助手，专门为大学生提供心理支持和情感疏导。\n"
    "\n你的角色特点：\n"
    "- 温暖友善，富有同理心\n"
    "- 专业但不冷漠，平易近人\n"
    "- 善于倾听，不急于给出建议\n"
    "- 鼓励积极思考，但不忽视负面情绪\n"
    "\n对话原则：\n"
    "1. 首先表达理解和共情\n"
    "2. 帮助用户梳理情绪和想法\n"
    "3. 提供温和的建议和应对策略\n"
    "4. 鼓励寻求专业帮助（如果需要）\n"
    "5. 强调用户的价值和潜力\n"
    "\n特殊注意：\n"
    "- 如果检测到自杀倾向，优先表达关心，鼓励寻求专业帮助\n"
    "- 对于严重的心理问题，建议联系学校心理咨询中心\n"
    "- 保持积极但现实的态度\n"
    "- 避免空洞的安慰，提供具体的帮助\n"
    "\n回复要求：\n"
    "- 语言温暖自然，贴近大学生群体\n"
    "- 长度适中，不要过长或过短\n"
    "- 可以适当使用表情符号增加亲和力\n"
    "- 结合大学生的生活场景给出建议\n"
    "\n重要：请全程使用简体中文(Chinese)进行温暖的交流和回复。"
)

EMOTION_ANALYSIS_PROMPT_TEMPLATE = """你是专业心理分析师。根据用户的情绪日记给出结构化分析。
日记数据：
日期：{diary_date}
情绪评分(1-10)：{mood_score}
主要情绪：{dominant_emotion}
触发因素：{emotion_triggers}
内容：{diary_content}
睡眠质量(1-5)：{sleep_quality}
压力水平(1-5)：{stress_level}

请严格只返回如下 JSON（不要任何其他文字、不要markdown代码块）：
{{"primaryEmotion":"情绪名称","riskLevel":0,"summary":"一句话总结用户今天的状态","suggestion":"一段温暖的关怀建议","improvementSuggestions":["可执行的小建议1","可执行的小建议2"]}}

说明：riskLevel 取值 0=正常 1=需要关注 2=预警 3=危机（出现绝望、自伤倾向等表达时给2或3）。
"""

# 模型层升级阈值：riskLevel >= 2 时补记一条危机事件
LLM_RISK_THRESHOLD = 2

MAX_REPLY_LENGTH = 20_000

_SYSTEM_PROMPT_WITH_CRISIS = None  # 延迟组装，避免和 crisis 模块循环导入


def _system_prompt() -> str:
    global _SYSTEM_PROMPT_WITH_CRISIS
    if _SYSTEM_PROMPT_WITH_CRISIS is None:
        from app.services.crisis import CRISIS_PROMPT_CLAUSE

        _SYSTEM_PROMPT_WITH_CRISIS = PSYCHOLOGICAL_SUPPORT_SYSTEM_PROMPT + CRISIS_PROMPT_CLAUSE
    return _SYSTEM_PROMPT_WITH_CRISIS


class AiUnavailable(Exception):
    """AI 未配置或调用失败。调用方应降级为可读提示，不要让连接裸崩。"""


# ===========================================================================
# 对话记忆
# ===========================================================================

MEMORY_WINDOW = 20  # 对应 Spring AI MessageWindowChatMemory 的默认窗口


class ConversationMemory:
    """按 conversationId 保存多轮历史。

    ⚠️ 进程内内存实现，重启即丢；多实例部署要么改用 Redis，要么接受
    "不同实例看到不同历史"。这与原版 Spring AI 的默认
    InMemoryChatMemoryRepository 行为一致。
    """

    def __init__(self, window: int = MEMORY_WINDOW) -> None:
        self._store: dict[str, list[dict[str, str]]] = {}
        self._window = window

    def add(self, conversation_id: str, messages: list[dict[str, str]]) -> None:
        history = self._store.setdefault(conversation_id, [])
        history.extend(messages)
        # 只保留最近 N 条，防止长对话把上下文撑爆
        if len(history) > self._window:
            self._store[conversation_id] = history[-self._window :]

    def get(self, conversation_id: str) -> list[dict[str, str]]:
        return list(self._store.get(conversation_id, []))

    def discard_last(self, conversation_id: str, role: str) -> None:
        """回滚最近一条指定角色的消息。

        用途：AI 调用失败时撤回刚记入的用户消息 —— 不回滚的话，
        用户重发同一句时历史里会出现两遍，模型会答非所问
        （「你刚才不是已经说过了吗」）。
        """
        history = self._store.get(conversation_id)
        if not history:
            return
        for i in range(len(history) - 1, -1, -1):
            if history[i].get("role") == role:
                del history[i]
                return

    def clear(self, conversation_id: str) -> None:
        self._store.pop(conversation_id, None)


chat_memory = ConversationMemory()


def conversation_id_of(session_id: str) -> str:
    """与原版一致：`conversation_` + sessionId。"""
    return f"conversation_{session_id}"


# ===========================================================================
# 客户端
# ===========================================================================


def is_configured() -> bool:
    return bool(settings.ai.api_key)


def _client(timeout: float | None = None):
    from openai import AsyncOpenAI

    cfg = settings.ai
    if not cfg.api_key:
        raise AiUnavailable("AI_API_KEY 未配置")
    kwargs: dict[str, Any] = {"api_key": cfg.api_key, "base_url": cfg.base_url}
    if timeout is not None:
        kwargs["timeout"] = timeout
    return AsyncOpenAI(**kwargs)


# ===========================================================================
# 流式对话
# ===========================================================================


async def stream_reply(
    conversation_id: str,
    user_message: str,
    extra_context: str = "",
) -> AsyncIterator[str]:
    """逐段吐出 AI 回复。

    `extra_context` 是 RAG 检索到的参考资料，会拼在系统提示词之后；
    传空字符串时行为与原来完全一致。

    副作用：会把用户消息记入历史。**助理回复的历史由调用方在流结束后写入**
    （因为只有调用方知道完整内容）—— 与原版 `doOnComplete` 的职责划分一致。

    Raises:
        AiUnavailable: 未配置或上游报错。由上层转成 SSE 的 error 事件。
    """
    client = _client()
    chat_memory.add(conversation_id, [{"role": "user", "content": user_message}])

    system_content = _system_prompt() + (extra_context or "")
    messages = [{"role": "system", "content": system_content}, *chat_memory.get(conversation_id)]

    try:
        stream = await client.chat.completions.create(
            model=settings.ai.model,
            messages=messages,
            stream=True,
        )
    except Exception as exc:  # noqa: BLE001
        # 调用没成功：撤回刚记入的用户消息，否则重发会重复
        chat_memory.discard_last(conversation_id, "user")
        raise AiUnavailable(str(exc)) from exc

    try:
        async for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                yield content
    except Exception as exc:  # noqa: BLE001
        # 中途断流：本轮对话作废，撤回用户消息让重试从干净状态开始
        chat_memory.discard_last(conversation_id, "user")
        raise AiUnavailable(str(exc)) from exc


def remember_reply(conversation_id: str, reply: str) -> None:
    """把完整回复写入历史。原版在 `doOnComplete` 里做这件事。"""
    if reply and reply.strip():
        chat_memory.add(conversation_id, [{"role": "assistant", "content": reply}])


def truncate_reply(reply: str) -> str:
    """超过 20000 字符截断后再落库，防止异常输出把库撑爆。"""
    return reply if len(reply) <= MAX_REPLY_LENGTH else reply[:MAX_REPLY_LENGTH]


# ===========================================================================
# 情绪分析（结构化输出）
# ===========================================================================


def build_emotion_prompt(diary: Any) -> str:
    return EMOTION_ANALYSIS_PROMPT_TEMPLATE.format(
        diary_date=diary.diary_date,
        mood_score=diary.mood_score,
        dominant_emotion=diary.dominant_emotion,
        emotion_triggers=diary.emotion_triggers,
        diary_content=diary.diary_content,
        sleep_quality=diary.sleep_quality,
        stress_level=diary.stress_level,
    )


def strip_code_fence(raw: str) -> str:
    """模型经常把 JSON 包在 ``` 里，去掉后再入库。"""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


async def analyze_emotion(diary: Any) -> str | None:
    """返回校验过的 JSON 字符串；失败返回 None（不影响日记保存）。"""
    if not is_configured():
        return None
    try:
        client = _client()
        resp = await client.chat.completions.create(
            model=settings.ai.model,
            messages=[{"role": "user", "content": build_emotion_prompt(diary)}],
        )
        raw = resp.choices[0].message.content if resp.choices else None
        if not raw:
            return None
        cleaned = strip_code_fence(raw)
        json.loads(cleaned)  # 校验为合法 JSON 才入库
        return cleaned
    except Exception as exc:  # noqa: BLE001
        logger.warning("日记AI分析失败(不影响保存): %s", exc)
        return None


def extract_risk_level(analysis_json: str | None) -> int | None:
    """从分析结果里取 riskLevel。取不到返回 None。"""
    if not analysis_json:
        return None
    try:
        value = json.loads(analysis_json).get("riskLevel")
        return int(value) if value is not None else None
    except (ValueError, TypeError, AttributeError):
        return None
