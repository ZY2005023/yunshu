"""AI 服务配置管理 —— 「API 管理」页的业务层。

参考 one-api / new-api 等 LLM 网关的渠道管理形态：
· 页面上改 base_url / api_key / model，保存即生效（不走 .env、不重启）；
· 密钥只写不读 —— 保存后响应里永远是掩码，页面上能看到"配没配、尾4位"；
· 一键测试连通性（拿当前生效配置发一个极小请求，回显时延与模型回复）。

三层取值优先级（config.Settings.ai 同步实现）：
    数据库 sys_config（运营期改动） > 环境变量 .env（部署期默认） > 代码默认值

⚠️ 密钥在库里的存储形态与 .env 一致是**明文**（加密存储需要额外 KMS，
不属于本项目当前的安全水位）。防护措施：接口仅 ADMIN、响应掩码、
日志零输出。若将来引入字段级加密，从这一处收口即可。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import runtime_config
from app.core.exceptions import BusinessError
from app.models import SysConfig
from app.services import ai as ai_service

logger = logging.getLogger(__name__)

# 本模块管理的全部配置键。**新键要同时加进 VALID_KEYS** ——
# 白名单外的一律拒绝（管理页传什么存什么等于开了个任意配置注入口）。
CONFIG_KEYS: tuple[str, ...] = ("ai.base_url", "ai.model", "ai.api_key")

BASE_URL_MIN = 8  # api_key / base_url 的最小长度下限，挡手滑


# ===========================================================================
# 数据库 ↔ 覆盖层
# ===========================================================================


def _read_values(db: Session) -> dict[str, str]:
    rows = db.scalars(select(SysConfig).where(SysConfig.config_key.in_(CONFIG_KEYS))).all()
    return {r.config_key: (r.config_value or "") for r in rows if r.config_value}


def _apply_values(values: dict[str, str]) -> None:
    runtime_config.set_many(values)


def load_overrides_from_db(db: Session) -> int:
    """启动时把 sys_config 的值灌进运行时覆盖层。返回条数。"""
    values = _read_values(db)
    _apply_values(values)
    return len(values)


def _upsert(db: Session, key: str, value: str) -> None:
    row = db.scalar(select(SysConfig).where(SysConfig.config_key == key))
    if row is None:
        db.add(SysConfig(config_key=key, config_value=value))
    else:
        row.config_value = value


# ===========================================================================
# 读（掩码）
# ===========================================================================


def mask_key(key: str) -> str:
    """密钥掩码：只露尾 4 位。空值返回空串，太短的整体打码。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"****{key[-4:]}"


def _field_source(key: str) -> str:
    """字段当前值来自哪一层：database / env / default。前端据此显示来源徽标。"""
    if runtime_config.get(key) is not None:
        return "database"
    env_names = {"ai.api_key": "AI_API_KEY", "ai.base_url": "AI_BASE_URL", "ai.model": "AI_MODEL"}
    import os

    return "env" if os.getenv(env_names.get(key, ""), "") else "default"


def get_config() -> dict[str, Any]:
    """当前生效配置。**密钥只给掩码**，页面上永远拿不到原文。"""
    cfg = ai_service.settings.ai
    return {
        "baseUrl": cfg.base_url,
        "model": cfg.model,
        "apiKeyMasked": mask_key(cfg.api_key),
        "apiKeySet": bool(cfg.api_key),
        "configured": ai_service.is_configured(),
        "sources": {key: _field_source(key) for key in CONFIG_KEYS},
    }


# ===========================================================================
# 写
# ===========================================================================


def update_config(db: Session, payload: Any) -> dict[str, Any]:
    """保存配置（部分更新：没传 / 传空的字段保持原值）。

    api_key 特殊语义：空 = 保持现有值不变（页面上是"留空则不修改"）。
    这样管理员只想改模型名时不需要重新粘贴密钥。
    """
    base_url = (payload.base_url or "").strip()
    model = (payload.model or "").strip()
    api_key = (payload.api_key or "").strip()

    if base_url:
        if not base_url.lower().startswith(("http://", "https://")):
            raise BusinessError("Base URL 必须以 http:// 或 https:// 开头")
        _upsert(db, "ai.base_url", base_url)
    if model:
        _upsert(db, "ai.model", model)
    if api_key:
        if len(api_key) < BASE_URL_MIN:
            raise BusinessError(f"API Key 长度不合法（至少 {BASE_URL_MIN} 位）")
        _upsert(db, "ai.api_key", api_key)

    db.commit()
    # 保存即生效：重读全量并应用（不经过 load_overrides_from_db ——
    # 测试会把后者替换成 no-op 来隔离环境，这里必须走独立的 _apply 路径）
    _apply_values(_read_values(db))

    logger.info(
        "AI 服务配置已更新: baseUrl=%s, model=%s, apiKey=%s",
        base_url or "(不变)",
        model or "(不变)",
        mask_key(api_key) if api_key else "(不变)",
    )
    return get_config()


# ===========================================================================
# 连通性测试
# ===========================================================================

TEST_TIMEOUT_SECONDS = 20.0
TEST_PROMPT = "请回复「连接正常」四个字。"


async def test_connection() -> dict[str, Any]:
    """用当前生效配置发一个极小请求，验证可达性。

    参考 one-api 渠道管理的「测试」按钮：结果带回时延与模型回复摘要，
    管理员在保存前/后都能一键确认「这组配置真的能用」。
    """
    cfg = ai_service.settings.ai
    if not cfg.api_key:
        return {"ok": False, "latencyMs": 0, "error": "API Key 未配置", "model": cfg.model}

    started = time.monotonic()
    try:
        reply = await _ping(cfg)
    except Exception as exc:  # noqa: BLE001 —— 任何上游错误都转成可读结果，不 500
        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.warning("AI 配置测试失败: %s", exc)
        return {"ok": False, "latencyMs": elapsed_ms, "error": _readable_error(exc), "model": cfg.model}

    elapsed_ms = int((time.monotonic() - started) * 1000)
    return {"ok": True, "latencyMs": elapsed_ms, "reply": (reply or "")[:100], "model": cfg.model}


async def _ping(cfg: Any) -> str:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=cfg.api_key, base_url=cfg.base_url, timeout=TEST_TIMEOUT_SECONDS)
    resp = await client.chat.completions.create(
        model=cfg.model,
        messages=[{"role": "user", "content": TEST_PROMPT}],
        max_tokens=16,
    )
    return resp.choices[0].message.content if resp.choices else ""


def _readable_error(exc: Exception) -> str:
    """把 openai SDK 的异常压成管理员能看懂的一句话。"""
    text = str(exc)
    lowered = text.lower()
    if "401" in text or "unauthorized" in lowered or "invalid_api_key" in lowered:
        return "认证失败（401）：API Key 不正确或已失效"
    if "404" in text and ("model" in lowered or "not_found" in lowered):
        return "模型不存在（404）：检查模型名称是否属于该供应商"
    if "timed out" in lowered or "timeout" in lowered:
        return f"连接超时：{int(TEST_TIMEOUT_SECONDS)} 秒内未收到响应，检查 Base URL 与网络"
    if "connect" in lowered and ("refused" in lowered or "failed" in lowered):
        return "连接失败：Base URL 不可达（地址写错或网络不通）"
    return text[:200] or "未知错误"
