"""情绪日记业务。

对峙原版 `EmotionDiaryService`。

两处**看起来像不一致但必须保留**的地方：
1. `/my` 的 `aiEmotionAnalysis` 返回**解析后的对象**；
   管理端 `/admin/page` 返回**原始 JSON 字符串**。
2. `/my` 的排序是 `diary_date` 倒序；管理端是 `created_at` 倒序。

日记保存时会跑一次规则层危机检测（不依赖大模型是否可用）。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.crisis import detect
from app.models import EmotionDiary, User
from app.schemas import DiaryIn, DiaryQuery, DiaryRow
from app.services import crisis as crisis_service


def _dt(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def _preview(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    return text if len(text) <= limit else text[:limit] + "..."


def _parse_json(raw: str | None) -> Any:
    """解析失败返回 None（原版也是 catch 住给 null）。"""
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


# ===========================================================================
# 写
# ===========================================================================


def create_or_update(db: Session, user_id: int, payload: DiaryIn) -> tuple[EmotionDiary, int]:
    """同一用户同一天仅一条，存在即更新。

    Returns:
        (日记, 规则层危机命中等级)。等级随响应回传（DiaryOut.crisisLevel），
        让前端能像对话/量表那样当场给出求助资源 —— 之前这条路径上
        用户什么都看不到，是三条危机触发路径里唯一断掉的一条。
        （模型层 riskLevel >= 2 的升级走 analyze_and_attach，另行补记事件。）
    """
    existing = db.scalar(
        select(EmotionDiary)
        .where(EmotionDiary.user_id == user_id, EmotionDiary.diary_date == payload.diary_date)
        .limit(1)
    )

    now = datetime.now()
    if existing is None:
        diary = EmotionDiary(
            user_id=user_id,
            diary_date=payload.diary_date,
            created_at=now,
            updated_at=now,
        )
        db.add(diary)
    else:
        diary = existing
        diary.updated_at = now

    diary.mood_score = payload.mood_score
    diary.dominant_emotion = payload.dominant_emotion
    diary.emotion_triggers = payload.emotion_triggers
    diary.diary_content = payload.diary_content
    diary.sleep_quality = payload.sleep_quality
    diary.stress_level = payload.stress_level
    db.commit()
    db.refresh(diary)

    # 规则层危机检测；命中即落 crisis_event，可被管理端跟进
    signal = detect(payload.diary_content)
    if signal.is_crisis:
        crisis_service.record_if_needed(
            db, user_id, None, diary.id, "DIARY", signal, payload.diary_content
        )
    return diary, signal.level


def delete(db: Session, diary_id: int) -> bool:
    diary = db.get(EmotionDiary, diary_id)
    if diary is None:
        return False
    db.delete(diary)
    db.commit()
    return True


# ===========================================================================
# 读
# ===========================================================================


def my_list(db: Session, user_id: int) -> list[DiaryRow]:
    diaries = list(
        db.scalars(
            select(EmotionDiary)
            .where(EmotionDiary.user_id == user_id)
            .order_by(EmotionDiary.diary_date.desc())
        ).all()
    )
    return [
        DiaryRow(
            id=d.id,
            diary_date=d.diary_date.isoformat() if d.diary_date else None,
            mood_score=d.mood_score,
            dominant_emotion=d.dominant_emotion,
            emotion_triggers=d.emotion_triggers,
            diary_content=d.diary_content,
            sleep_quality=d.sleep_quality,
            stress_level=d.stress_level,
            created_at=_dt(d.created_at),
            ai_emotion_analysis=_parse_json(d.ai_emotion_analysis),
        )
        for d in diaries
    ]


def admin_page(db: Session, query: DiaryQuery) -> dict[str, Any]:
    conditions = []

    # keyword 按用户名/邮箱模糊匹配，先定位用户再筛日记
    if query.keyword and query.keyword.strip():
        kw = f"%{query.keyword}%"
        user_ids = list(
            db.scalars(select(User.id).where(or_(User.username.like(kw), User.email.like(kw)))).all()
        )
        if not user_ids:
            return {"records": [], "total": 0}
        conditions.append(EmotionDiary.user_id.in_(user_ids))

    total = db.scalar(select(func.count()).select_from(EmotionDiary).where(*conditions)) or 0
    diaries = list(
        db.scalars(
            select(EmotionDiary)
            .where(*conditions)
            .order_by(EmotionDiary.created_at.desc())
            .offset((max(1, query.current_page) - 1) * query.size)
            .limit(query.size)
        ).all()
    )

    user_ids = list({d.user_id for d in diaries if d.user_id})
    users: dict[int, User] = {}
    if user_ids:
        users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()}

    records = []
    for d in diaries:
        u = users.get(d.user_id or 0)
        records.append(
            DiaryRow(
                id=d.id,
                user_id=d.user_id,
                username=u.username if u else None,
                nickname=u.nickname if u else None,
                diary_date=d.diary_date.isoformat() if d.diary_date else None,
                mood_score=d.mood_score,
                dominant_emotion=d.dominant_emotion,
                emotion_triggers=d.emotion_triggers,
                diary_content=d.diary_content,
                diary_content_preview=_preview(d.diary_content, 50),
                sleep_quality=d.sleep_quality,
                stress_level=d.stress_level,
                # 注意：管理端给的是**原始字符串**，不是解析后的对象
                ai_emotion_analysis=d.ai_emotion_analysis,
                created_at=_dt(d.created_at),
                updated_at=_dt(d.updated_at),
            )
        )
    return {"records": records, "total": total}


# ===========================================================================
# AI 情绪分析（事务外执行，失败不影响日记保存）
# ===========================================================================


async def analyze_and_attach(db: Session, user_id: int, diary: EmotionDiary | None) -> EmotionDiary | None:
    """调 AI 做结构化情绪分析并回填。

    对应 Java 版 `EmotionDiaryService.analyzeAndAttach`：
    · 失败只记日志，**日记本身照常保存成功**
    · 模型的 `riskLevel >= 2` 时补记一条危机事件（模型层升级，与规则层互补）
    """
    import logging

    from app.services import ai as ai_service

    logger = logging.getLogger(__name__)

    if diary is None:
        return None
    try:
        analysis = await ai_service.analyze_emotion(diary)
        if analysis:
            diary.ai_emotion_analysis = analysis
            diary.ai_analysis_updated_at = datetime.now()
            db.commit()
            db.refresh(diary)
            _record_llm_risk(db, user_id, diary.id, analysis)
    except Exception as exc:  # noqa: BLE001
        logger.warning("日记AI分析失败(不影响保存): %s", exc)
    return diary


def _record_llm_risk(db: Session, user_id: int, diary_id: int, analysis_json: str) -> None:
    """模型层升级：解析 AI 返回的 riskLevel，达到阈值则补记危机事件。"""
    import json
    import logging

    from app.core.crisis import CrisisSignal
    from app.services import ai as ai_service

    logger = logging.getLogger(__name__)

    try:
        level = ai_service.extract_risk_level(analysis_json)
        if level is None or level < ai_service.LLM_RISK_THRESHOLD:
            return

        summary = None
        try:
            summary = json.loads(analysis_json).get("summary")
        except (ValueError, TypeError):
            pass

        crisis_service.record_if_needed(
            db,
            user_id,
            None,
            diary_id,
            "DIARY",
            CrisisSignal(level=level, trigger_type="LLM", matched_terms=["model-risk-level"]),
            summary,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("解析 AI 风险等级失败: %s", exc)
