"""数据看板聚合 —— 对齐 Java 版 `DataAnalyticsService`。

聚合在 Python 侧完成（查近 7 天原始数据再分组），与原版一致，不写复杂聚合 SQL。

⚠️ 一个必须留意的语言差异：
Java 的 `Math.round(x)` 等价于 `floor(x + 0.5)`；
Python 内建 `round()` 是**银行家舍入**（round(2.5) == 2，round(3.5) == 4）。
用错会让平均分出现 0.1 的偏差 —— 图表上的数字对不上就是这种问题。
所以这里统一用 `round_half_up()`。
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ConsultationMessage, ConsultationSession, EmotionDiary, User

DAYS = 7
DEFAULT_EMOTION = "平静"


def round_half_up(value: float) -> int:
    """模拟 Java 的 Math.round：floor(x + 0.5)，不是 Python 的银行家舍入。"""
    return math.floor(value + 0.5)


def round1(value: float) -> float:
    """保留一位小数（先放大 10 倍按 Java 规则取整再缩回）。"""
    return round_half_up(value * 10) / 10.0


def overview(db: Session) -> dict[str, Any]:
    today = date.today()
    week_ago = datetime.combine(today - timedelta(days=DAYS - 1), time.min)
    today_start = datetime.combine(today, time.min)

    # ---- 近 7 天原始数据 ----
    new_users_week = list(db.scalars(select(User).where(User.created_at >= week_ago)).all())
    diaries_week = list(
        db.scalars(select(EmotionDiary).where(EmotionDiary.created_at >= week_ago)).all()
    )
    sessions_week = list(
        db.scalars(
            select(ConsultationSession).where(ConsultationSession.started_at >= week_ago)
        ).all()
    )
    # 只统计用户发出的消息（senderType == 1）
    total_messages = (
        db.scalar(
            select(func.count())
            .select_from(ConsultationMessage)
            .where(ConsultationMessage.sender_type == 1)
        )
        or 0
    )

    # ---- 总量 ----
    total_users = db.scalar(select(func.count()).select_from(User)) or 0
    total_diaries = db.scalar(select(func.count()).select_from(EmotionDiary)) or 0
    total_sessions = db.scalar(select(func.count()).select_from(ConsultationSession)) or 0

    active_ids = {d.user_id for d in diaries_week if d.user_id is not None}
    active_ids |= {s.user_id for s in sessions_week if s.user_id is not None}

    mood_scores = [d.mood_score for d in diaries_week if d.mood_score is not None]
    avg_mood = sum(mood_scores) / len(mood_scores) if mood_scores else 0.0

    system_overview = {
        "totalUsers": total_users,
        "activeUsers": len(active_ids),
        "totalDiaries": total_diaries,
        "totalSessions": total_sessions,
        "avgMoodScore": round1(avg_mood),
        "todayNewUsers": sum(
            1 for u in new_users_week if u.created_at and u.created_at > today_start
        ),
        "todayNewDiaries": sum(
            1 for d in diaries_week if d.created_at and d.created_at > today_start
        ),
        "todayNewSessions": sum(
            1 for s in sessions_week if s.started_at and s.started_at > today_start
        ),
    }

    # ---- 按日期分组（近 7 天，含空天）----
    dates = [(today - timedelta(days=i)).isoformat() for i in range(DAYS - 1, -1, -1)]

    diaries_by_date = _group_by_date(diaries_week, "created_at")
    sessions_by_date = _group_by_date(sessions_week, "started_at")
    users_by_date = _group_by_date(new_users_week, "created_at")

    # ---- 情绪热力图：7 行（周一~周日）× 10 列（评分 1~10）----
    grid_data: list[list[dict[str, Any]]] = []
    for y in range(7):
        row: list[dict[str, Any]] = []
        for x in range(10):
            score = x + 1
            cell = [
                d
                for d in diaries_week
                if d.mood_score is not None
                and d.mood_score == score
                and d.created_at is not None
                and d.created_at.weekday() == y  # Python: 0 = 周一，与 Java 一致
            ]
            if cell:
                cell_avg = round1(sum(d.mood_score for d in cell) / len(cell))
                last_emotion = cell[-1].dominant_emotion
                dominant = last_emotion if last_emotion else DEFAULT_EMOTION
            else:
                cell_avg = 0
                dominant = DEFAULT_EMOTION
            row.append(
                {
                    "x": x,
                    "y": y,
                    "value": len(cell),
                    "avgMoodScore": cell_avg,
                    "dominantEmotion": dominant,
                }
            )
        grid_data.append(row)

    # ---- consultationStats ----
    # 注意：Java 原式是 Math.round(totalMessages * 10.0 / totalSessions) / 10.0，
    # 乘 10 已经写在表达式里了，这里不能再套 round1()（那会变成放大 100 倍）
    consultation_stats = {
        "totalSessions": total_sessions,
        "totalMessages": total_messages,
        "avgMessagesPerSession": (
            round_half_up(total_messages * 10.0 / total_sessions) / 10.0
            if total_sessions > 0
            else 0
        ),
    }

    # ---- 三组按天的序列 ----
    daily_trend = []
    for ds in dates:
        day_sessions = sessions_by_date.get(ds, [])
        daily_trend.append(
            {
                "date": ds,
                "sessionCount": len(day_sessions),
                "userCount": len({s.user_id for s in day_sessions if s.user_id is not None}),
            }
        )

    trend_data = []
    for ds in dates:
        day_diaries = diaries_by_date.get(ds, [])
        scores = [d.mood_score for d in day_diaries if d.mood_score is not None]
        trend_data.append(
            {
                "date": ds,
                "avgMoodScore": round1(sum(scores) / len(scores)) if scores else 0,
                "recordCount": len(day_diaries),
            }
        )

    activity_data = []
    for ds in dates:
        diary_users = len(
            {d.user_id for d in diaries_by_date.get(ds, []) if d.user_id is not None}
        )
        consult_users = len(
            {s.user_id for s in sessions_by_date.get(ds, []) if s.user_id is not None}
        )
        activity_data.append(
            {
                "date": ds,
                "newUsers": len(users_by_date.get(ds, [])),
                "diaryUsers": diary_users,
                "consultationUsers": consult_users,
                "activeUsers": max(diary_users, consult_users),
            }
        )

    return {
        "systemOverview": system_overview,
        "emotionHeatmap": {"gridData": grid_data},
        "consultationStats": consultation_stats,
        "dailyTrend": daily_trend,
        "trendData": trend_data,
        "activityData": activity_data,
    }


def _group_by_date(rows: list[Any], attr: str) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = {}
    for item in rows:
        value = getattr(item, attr, None)
        if value is None:
            continue
        grouped.setdefault(value.date().isoformat(), []).append(item)
    return grouped
