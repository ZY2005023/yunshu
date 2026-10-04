"""危机工单的主动触达。

**为什么需要这个模块**：原来的机制只有「后台页面 + 侧边栏角标」——
管理员不打开后台，就没人知道有人被识别为高风险。
危机检测做得再准，最后一公里断了也等于没识别。

## 设计

- **webhook 优先**：企业微信 / 钉钉 / 飞书的群机器人都只是「POST 一个 JSON」，
  但**三家的字段并不通用**（见 `_payload`），这里按域名自动选对格式。
- **未配置就不发**：`CRISIS_WEBHOOK_URL` 为空时**只写一条日志**。
  不静默丢弃（日志里留痕），但也必须让部署方知道「现在没人被通知」。
- **绝不阻塞、绝不上抛**：发送在后台线程里做，任何异常只记日志。
  通知失败不能让用户的对话或日记保存失败。
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# 网络超时设短一点：这是后台任务，卡住了也只是白等
_TIMEOUT_SECONDS = 5.0

# 等级 → 中文，尽量让值班老师一眼看懂严重程度。
# ⚠️ 只有 1~3 三个等级（见 core/crisis.py 的 LEVEL_ATTENTION/WARNING/CRITICAL）。
#    别再往这里加 4 级 —— 系统根本不会产生那个值。
_LEVEL_TEXT = {
    1: "1 级 · 关注",
    2: "2 级 · 预警",
    3: "3 级 · 高危",
}


def build_message(event: Any, *, app_name: str = "云舒") -> str:
    """把危机事件拼成一段可读文本。纯函数，方便单测。

    有意包含 `content_snippet` —— 值班老师需要看到原话才能判断紧迫程度。
    片段在入库时已被 `core/crisis.py::snippet()` 截断过。
    """
    level = getattr(event, "level", None) or 0
    source = {
        "CHAT": "AI 对话",
        "DIARY": "情绪日记",
    }.get(getattr(event, "source", ""), getattr(event, "source", "") or "未知来源")

    created = getattr(event, "created_at", None)
    when = created.strftime("%Y-%m-%d %H:%M:%S") if isinstance(created, datetime) else "未知时间"

    lines = [
        f"【{app_name} 危机预警】",
        f"等级：{_LEVEL_TEXT.get(level, f'{level} 级')}",
        f"来源：{source}",
        f"触发：{getattr(event, 'trigger_type', None) or '未标注'}",
        f"时间：{when}",
        f"用户ID：{getattr(event, 'user_id', None)}",
    ]

    terms = getattr(event, "matched_terms", None)
    if terms:
        lines.append(f"命中词：{terms}")

    snippet = getattr(event, "content_snippet", None)
    if snippet:
        lines.append(f"内容片段：{snippet}")

    lines.append("")
    lines.append(f"请到管理后台「危机预警」处置；如需转介，联系{settings.crisis.notify_contact}。")
    return "\n".join(lines)


def _payload(text: str, url: str) -> dict[str, Any]:
    """按群机器人的平台拼请求体。

    三家的格式并不通用，实测差异：
      · 企业微信 / 钉钉 → `{"msgtype": "text", "text": {"content": "..."}}`
      · 飞书            → `{"msg_type": "text", "content": {"text": "..."}}`
        （注意是 `msg_type` 带下划线，且正文在 `content.text`）

    企业微信和钉钉形状一样，不用分开。
    """
    if "feishu" in url or "larksuite" in url:
        return {"msg_type": "text", "content": {"text": text}}
    return {"msgtype": "text", "text": {"content": text}}


def send(text: str) -> bool:
    """同步发送。返回是否成功。**不抛异常。**"""
    url = (settings.crisis.webhook_url or "").strip()
    if not url:
        return False
    try:
        import httpx

        resp = httpx.post(url, json=_payload(text, url), timeout=_TIMEOUT_SECONDS)
        # 企业微信/钉钉都用 errcode==0 表示成功，但 HTTP 200 已经够判断"送达了"
        if resp.status_code != 200:
            logger.warning("危机通知发送失败: HTTP %s %s", resp.status_code, resp.text[:200])
            return False
        body: dict[str, Any] = {}
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            # 响应不是 JSON（网关可能返回 HTML 错误页），HTTP 200 已足够判断送达
            logger.debug("危机通知响应不是 JSON，忽略其内容")
        # ⚠️ 三家的成功标志字段**不统一**，只看 errcode 会漏判飞书：
        #   企业微信 / 钉钉 → {"errcode": 0}
        #   飞书            → {"code": 0} 或 {"StatusCode": 0}
        # 飞书的响应里根本没有 errcode，只读 errcode 的话它永远是 None（= 视为成功），
        # 于是**飞书发送失败也会被当成送达** —— 正是那种"群里没人收到但系统说没事"的失效。
        if isinstance(body, dict):
            code = body.get("errcode")
            if code is None:
                code = body.get("code")
            if code is None:
                code = body.get("StatusCode")
            if code not in (None, 0):
                logger.warning("危机通知被拒绝: %s", json.dumps(body, ensure_ascii=False)[:200])
                return False
        logger.info("危机通知已发送")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("危机通知异常: %s", exc)
        return False


def notify_crisis(event: Any) -> None:
    """发出通知。**fire-and-forget**，立刻返回，不阻塞调用方。

    用独立守护线程而不是 asyncio task：调用点既有同步也有异步上下文
    （对话流、日记提交），线程是唯一两边都安全的选择。
    """
    # ⚠️ **测试模式守卫**：自动化测试时关掉外部 webhook，
    # 否则每次触发危机话术都会往群里推一条测试数据，把生产群刷爆。
    # 关法：环境变量 ``SUT_NOTIFY_DISABLED=true``（本地/测试默认开，部署到正式环境删掉这行）。
    import os
    if os.environ.get("SUT_NOTIFY_DISABLED", "").strip().lower() in ("true", "1", "yes"):
        logger.info(
            "SUT_NOTIFY_DISABLED=true → 跳过外部 webhook 推送（id=%s, level=%s）",
            getattr(event, "id", None), getattr(event, "level", None),
        )
        return

    url = (settings.crisis.webhook_url or "").strip()
    if not url:
        # 不静默：留一条日志，让部署方知道现在没人会被通知
        logger.warning(
            "检测到危机事件(id=%s, level=%s)但未配置 CRISIS_WEBHOOK_URL —— "
            "没有任何人会收到通知，只存在于管理后台列表里。",
            getattr(event, "id", None),
            getattr(event, "level", None),
        )
        return

    text = build_message(event)
    threading.Thread(target=send, args=(text,), daemon=True, name="crisis-notify").start()
