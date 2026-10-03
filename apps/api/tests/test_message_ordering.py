"""消息排序稳定性（consultation.list_messages / last_message）的回归测试。

背景：`consultation_message.created_at` 在 MySQL 里是**秒级** DATETIME，
Python 侧写入 `datetime.now()`（含微秒）会被截断到秒。AI 短回复经常和
用户消息落在**同一秒**，排序若只有 `created_at` 一个键，同秒内的返回
顺序由数据库自行决定 —— 用户消息和 AI 回复可能显示颠倒。

坦白说：SQLite 测试对 tie 顺序的返回通常是插入序（= id 序），
所以这个用例在**旧代码上也大概率能过**。它钉住的是行为契约：
同秒消息必须按 id（写入顺序）稳定排列 —— 把「排序键必须带 id」
变成用例明确断言的约定，防止后续重构把它丢掉。
真要在 MySQL 上复现旧行为的乱序，需要同秒批量插入 + 非聚簇索引顺序，
SQLite 内存库给不了这个条件。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import sessionmaker

from app.models import ConsultationMessage, ConsultationSession, User
from app.services import consultation as consultation_service


def _make_session_with_same_second_messages(session_factory: sessionmaker, username: str):
    """一个会话 + 三条 created_at 完全相同的消息（按 id 顺序：用户→AI→用户）。"""
    db = session_factory()
    try:
        user = db.query(User).filter(User.username == username).one()
        session = ConsultationSession(
            user_id=user.id, session_title="排序测试", started_at=datetime(2026, 1, 1, 12, 0, 0)
        )
        db.add(session)
        db.commit()

        same_second = datetime(2026, 1, 1, 12, 0, 1)
        rows = [
            ConsultationMessage(session_id=session.id, sender_type=1, content="第一句", created_at=same_second),
            ConsultationMessage(session_id=session.id, sender_type=2, content="AI回复", created_at=same_second),
            ConsultationMessage(session_id=session.id, sender_type=1, content="第二句", created_at=same_second),
        ]
        db.add_all(rows)
        db.commit()
        return session.id
    finally:
        db.close()


class TestMessageOrdering:
    def test_same_second_messages_keep_insertion_order(
        self, session_factory: sessionmaker, registered_user: dict
    ):
        session_id = _make_session_with_same_second_messages(session_factory, registered_user["username"])
        db = session_factory()
        try:
            rows = consultation_service.list_messages(db, session_id)
        finally:
            db.close()

        contents = [r.content for r in rows]
        assert contents == ["第一句", "AI回复", "第二句"], f"同秒消息顺序不稳定: {contents}"

    def test_last_message_picks_latest_id_on_tie(
        self, session_factory: sessionmaker, registered_user: dict
    ):
        session_id = _make_session_with_same_second_messages(session_factory, registered_user["username"])
        db = session_factory()
        try:
            last = consultation_service.last_message(db, session_id)
        finally:
            db.close()

        assert last is not None
        assert last.content == "第二句", "同秒并列时应取 id 最大（最后写入）的一条"

    def test_session_list_preview_uses_latest_message(
        self, session_factory: sessionmaker, registered_user: dict
    ):
        """会话列表的「最后一条消息」预览同样要在同秒并列时取最新一条。"""
        session_id = _make_session_with_same_second_messages(session_factory, registered_user["username"])
        db = session_factory()
        try:
            user = db.query(User).filter(User.username == registered_user["username"]).one()
            page = consultation_service.page_of_user(db, user.id, 1, 10)
        finally:
            db.close()

        row = next(r for r in page["records"] if r.id == session_id)
        assert (row.last_message_content or "").startswith("第二句")
