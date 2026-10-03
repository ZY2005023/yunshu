"""危机工单「处置工作台」与咨询记录整改的测试。

这一组用例针对的是**原来那套接口的盲区**：
拿到工单只有一个用户 ID 和 120 字片段，管理员无法判断真假。

⚠️ 数据直接用 `session_factory` 写库，不走 AI —— 否则断言会依赖模型输出，
   既慢又不稳定（见 conftest 的 `_no_real_ai_calls`）。
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.models import (
    ConsultationMessage,
    ConsultationSession,
    CrisisEvent,
    EmotionDiary,
    ScaleRecord,
    User,
)

pytestmark = pytest.mark.usefixtures("client")


# ===========================================================================
# 造数据
# ===========================================================================


def _make_user(db, username: str, nickname: str) -> User:
    user = User(
        username=username,
        nickname=nickname,
        password="x",
        user_type=1,
        status=1,
        created_at=datetime.now(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_chat_event(
    db, user_id: int, level: int = 3, terms: str = "自杀", minutes_ago: int = 0
) -> tuple[int, int]:
    """造一个「对话触发」的工单，返回 (event_id, session_id)。"""
    now = datetime.now() - timedelta(minutes=minutes_ago)
    session = ConsultationSession(
        user_id=user_id, session_title="很难熬的一晚", started_at=now
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    long_text = "我最近真的很崩溃，" * 20 + "甚至想过自杀"
    for sender, content in [
        (1, "你好，我想聊聊"),
        (2, "我在这里，慢慢说"),
        (1, long_text),
        (2, "听起来你很痛苦，建议联系专业帮助"),
    ]:
        db.add(
            ConsultationMessage(
                session_id=session.id,
                sender_type=sender,
                message_type=1,
                content=content,
                created_at=now,
            )
        )

    event = CrisisEvent(
        user_id=user_id,
        session_id=session.id,
        source="CHAT",
        level=level,
        trigger_type="KEYWORD",
        matched_terms=terms,
        content_snippet=long_text[:120],
        status="PENDING",
        created_at=now,
        updated_at=now,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event.id, session.id


# ===========================================================================
# 列表富化
# ===========================================================================


class TestCrisisListEnriched:
    def test_page_row_carries_username_not_just_id(
        self, client: TestClient, admin_headers: dict, session_factory
    ):
        """原来列表里只有「用户ID: 52」，管理员没法知道是谁。

        数据本来就在 user 表里，取得到却没取 —— 这是工单不可处置的第一环。
        """
        with session_factory() as db:
            u = _make_user(db, "zhangshan", "张三")
            _make_chat_event(db, u.id)

        row = client.get("/api/admin/crisis/page", headers=admin_headers).json()["data"][
            "records"
        ][0]
        assert row["userId"] == u.id
        assert row["username"] == "zhangshan"
        assert row["nickname"] == "张三"

    def test_no_n_plus_one_on_50_rows(
        self, client: TestClient, admin_headers: dict, session_factory
    ):
        """一页 50 条时必须是批量查，不能逐条查用户。

        这里用「同一用户 50 条工单」来验证富化不会把列表搞挂/超时，
        顺便确认去重逻辑（批量 ids 去重）没问题。
        """
        with session_factory() as db:
            u = _make_user(db, "bulk", "批量")
            for i in range(50):
                _make_chat_event(db, u.id, level=(i % 3) + 1, minutes_ago=i)

        data = client.get(
            "/api/admin/crisis/page", headers=admin_headers, params={"size": 50}
        ).json()["data"]
        assert data["total"] == 50
        assert all(r["username"] == "bulk" for r in data["records"])
        # 等级优先：3 级排在最前
        assert data["records"][0]["level"] == 3


# ===========================================================================
# 处置上下文
# ===========================================================================


class TestCrisisContext:
    def test_requires_admin(self, client: TestClient, auth_headers: dict, session_factory):
        with session_factory() as db:
            u = _make_user(db, "u1", "用户一")
            event_id, _ = _make_chat_event(db, u.id)

        # ⚠️ 权限拒绝走 default 分支 → HTTP 400 + A0300（不是 403，别凭直觉改）
        resp = client.get(f"/api/admin/crisis/{event_id}/context", headers=auth_headers)
        assert resp.status_code == 400
        assert resp.json()["code"] == "A0300"

    def test_source_messages_are_complete_not_truncated(
        self, client: TestClient, admin_headers: dict, session_factory
    ):
        """工单只存了 120 字片段，但处置必须能看到完整原文。"""
        with session_factory() as db:
            u = _make_user(db, "u2", "用户二")
            event_id, session_id = _make_chat_event(db, u.id)

        ctx = client.get(
            f"/api/admin/crisis/{event_id}/context", headers=admin_headers
        ).json()["data"]

        src = ctx["source"]
        assert src["source"] == "CHAT"
        assert src["sessionId"] == session_id
        assert src["sessionTitle"] == "很难熬的一晚"
        assert len(src["messages"]) == 4
        full = [m for m in src["messages"] if "自杀" in (m["content"] or "")]
        assert full, "应包含触发原文"
        # 关键：完整内容（远超 120 字），不是 snippet
        assert len(full[0]["content"]) > 120
        # 触发点被标出来，管理员不用自己在整段对话里找
        assert src["triggerMessageId"] == full[0]["id"]

    def test_history_excludes_current_event_and_shows_recurrence(
        self, client: TestClient, admin_headers: dict, session_factory
    ):
        """是不是复发，是处置时最关键的一问 —— 原来完全没有这个维度。"""
        with session_factory() as db:
            u = _make_user(db, "u3", "用户三")
            old_id, _ = _make_chat_event(db, u.id, level=2, minutes_ago=60)
            new_id, _ = _make_chat_event(db, u.id, level=3, minutes_ago=1)

        ctx = client.get(
            f"/api/admin/crisis/{new_id}/context", headers=admin_headers
        ).json()["data"]

        assert ctx["user"]["crisisCount"] == 2
        assert [h["id"] for h in ctx["history"]] == [old_id], "历史里不应包含本次工单"
        assert ctx["history"][0]["level"] == 2

    def test_context_includes_scales_diaries_and_trend(
        self, client: TestClient, admin_headers: dict, session_factory
    ):
        """量表自伤项与近期日记趋势 —— 判断"恶化"的依据。"""
        with session_factory() as db:
            u = _make_user(db, "u4", "用户四")
            event_id, _ = _make_chat_event(db, u.id)
            db.add(
                ScaleRecord(
                    user_id=u.id,
                    scale_code="PHQ9",
                    scale_name="抑郁筛查",
                    total_score=18,
                    level="重度",
                    self_harm_score=3,
                    self_harm_risk=1,
                    created_at=datetime.now(),
                )
            )
            for score in (2, 3, 2):  # 连续低分
                db.add(
                    EmotionDiary(
                        user_id=u.id,
                        diary_date=datetime.now().date(),
                        mood_score=score,
                        dominant_emotion="低落",
                        diary_content="写不下去了",
                        created_at=datetime.now(),
                    )
                )
            db.commit()

        ctx = client.get(
            f"/api/admin/crisis/{event_id}/context", headers=admin_headers
        ).json()["data"]

        assert ctx["scales"][0]["selfHarmScore"] == 3
        assert ctx["scales"][0]["selfHarmRisk"] == 1
        # 单看某天意义不大，连续低分才是信号
        assert ctx["diaryTrend"]["lowDays"] == 3
        assert ctx["diaryTrend"]["count"] == 3
        assert ctx["diaryTrend"]["avgMood"] == pytest.approx(2.3, abs=0.05)

    def test_checklist_varies_by_level(
        self, client: TestClient, admin_headers: dict, session_factory
    ):
        """处置清单按等级给 —— 新手拿到 3 级工单也知道先做什么。"""
        with session_factory() as db:
            u = _make_user(db, "u5", "用户五")
            e3, _ = _make_chat_event(db, u.id, level=3)
            e1, _ = _make_chat_event(db, u.id, level=1, terms="焦虑")

        c3 = client.get(f"/api/admin/crisis/{e3}/context", headers=admin_headers).json()[
            "data"
        ]
        c1 = client.get(f"/api/admin/crisis/{e1}/context", headers=admin_headers).json()[
            "data"
        ]
        assert any("120" in step for step in c3["checklist"])
        assert c3["checklist"] != c1["checklist"]
        # 3 级才出现「通知家长」这类措施
        codes3 = {m["code"] for m in c3["measureOptions"]}
        codes1 = {m["code"] for m in c1["measureOptions"]}
        assert "CONTACTED_PARENT" in codes3
        assert "CONTACTED_PARENT" not in codes1

    def test_diary_source_returns_diary_not_messages(
        self, client: TestClient, admin_headers: dict, session_factory
    ):
        with session_factory() as db:
            u = _make_user(db, "u6", "用户六")
            diary = EmotionDiary(
                user_id=u.id,
                diary_date=datetime.now().date(),
                mood_score=1,
                diary_content="活着太累了，想结束了",
                created_at=datetime.now(),
            )
            db.add(diary)
            db.commit()
            db.refresh(diary)
            event = CrisisEvent(
                user_id=u.id,
                diary_id=diary.id,
                source="DIARY",
                level=3,
                trigger_type="KEYWORD",
                matched_terms="结束",
                content_snippet="活着太累了",
                status="PENDING",
                created_at=datetime.now(),
            )
            db.add(event)
            db.commit()
            db.refresh(event)

        src = client.get(
            f"/api/admin/crisis/{event.id}/context", headers=admin_headers
        ).json()["data"]["source"]
        assert src["source"] == "DIARY"
        assert src["diaryId"] == diary.id
        assert "想结束了" in src["diary"]["content"]
        assert src["messages"] == []


# ===========================================================================
# 处置措施
# ===========================================================================


class TestHandleMeasures:
    def test_measures_persisted_and_returned(
        self, client: TestClient, admin_headers: dict, session_factory
    ):
        with session_factory() as db:
            u = _make_user(db, "m1", "措施一")
            event_id, _ = _make_chat_event(db, u.id, level=3)

        resp = client.post(
            f"/api/admin/crisis/{event_id}/handle",
            headers=admin_headers,
            json={
                "status": "RESOLVED",
                "handleNote": "已联系",
                "measures": ["READ_CONTEXT", "CONTACTED_STUDENT", "CONTACTED_PARENT"],
            },
        )
        assert resp.json()["code"] == "200"

        row = client.get("/api/admin/crisis/page", headers=admin_headers).json()["data"][
            "records"
        ][0]
        assert set(row["measures"]) == {
            "READ_CONTEXT",
            "CONTACTED_STUDENT",
            "CONTACTED_PARENT",
        }
        # 处置人姓名要显示出来，否则多人值班会重复联系学生
        assert row["handlerName"]

    def test_unknown_measure_is_rejected_not_silently_dropped(
        self, client: TestClient, admin_headers: dict, session_factory
    ):
        """静默丢弃是最危险的形态：管理员以为勾了「已通知家长」，库里却没记录。"""
        with session_factory() as db:
            u = _make_user(db, "m2", "措施二")
            event_id, _ = _make_chat_event(db, u.id, level=3)

        body = client.post(
            f"/api/admin/crisis/{event_id}/handle",
            headers=admin_headers,
            json={"measures": ["CONTACTED_PARENT", "NOT_A_REAL_MEASURE"]},
        ).json()
        assert "未知的处置措施" in body["msg"]

        with session_factory() as db:
            assert db.get(CrisisEvent, event_id).status == "PENDING", "不应被处置掉"


# ===========================================================================
# 跟进记录
# ===========================================================================


class TestFollowUps:
    def test_follow_up_is_append_only_and_reopens_closed_ticket(
        self, client: TestClient, admin_headers: dict, session_factory
    ):
        with session_factory() as db:
            u = _make_user(db, "f1", "跟进一")
            event_id, _ = _make_chat_event(db, u.id, level=3)

        client.post(
            f"/api/admin/crisis/{event_id}/handle",
            headers=admin_headers,
            json={"status": "RESOLVED", "handleNote": "首次联系"},
        )
        # 处置不是一次性的：3 天后复查还要能记
        resp = client.post(
            f"/api/admin/crisis/{event_id}/follow-ups",
            headers=admin_headers,
            json={"content": "3 天后复查：情绪平稳，已预约面谈"},
        )
        assert resp.json()["code"] == "200"

        rows = client.get(
            f"/api/admin/crisis/{event_id}/follow-ups", headers=admin_headers
        ).json()["data"]
        assert len(rows) == 1
        assert "复查" in rows[0]["content"]
        assert rows[0]["operatorName"]

        ctx = client.get(
            f"/api/admin/crisis/{event_id}/context", headers=admin_headers
        ).json()["data"]
        # 已关闭的工单被追加跟进 → 拉回处理中，避免"看起来结案了但没人再跟进"
        assert ctx["event"]["status"] == "HANDLING"
        assert ctx["event"]["followUpCount"] == 1

    def test_empty_follow_up_rejected(
        self, client: TestClient, admin_headers: dict, session_factory
    ):
        with session_factory() as db:
            u = _make_user(db, "f2", "跟进二")
            event_id, _ = _make_chat_event(db, u.id)

        body = client.post(
            f"/api/admin/crisis/{event_id}/follow-ups",
            headers=admin_headers,
            json={"content": "   "},
        ).json()
        assert body["code"] != "200"


# ===========================================================================
# 咨询记录：搜索 + 风险标记
# ===========================================================================


class TestAdminSessionQuery:
    def test_keyword_matches_message_content(
        self, client: TestClient, admin_headers: dict, session_factory
    ):
        """页面副标题写着「可按关键词检索」，但接口原来根本不接受 keyword。"""
        with session_factory() as db:
            u = _make_user(db, "s1", "搜索一")
            hit = ConsultationSession(
                user_id=u.id, session_title="普通闲聊", started_at=datetime.now()
            )
            miss = ConsultationSession(
                user_id=u.id, session_title="今天吃了什么", started_at=datetime.now()
            )
            db.add_all([hit, miss])
            db.commit()
            db.add(
                ConsultationMessage(
                    session_id=hit.id,
                    sender_type=1,
                    content="我最近总是失眠，很难受",
                    created_at=datetime.now(),
                )
            )
            db.add(
                ConsultationMessage(
                    session_id=miss.id,
                    sender_type=1,
                    content="食堂的饭不错",
                    created_at=datetime.now(),
                )
            )
            db.commit()

        data = client.get(
            "/api/psychological-chat/admin/sessions",
            headers=admin_headers,
            params={"keyword": "失眠"},
        ).json()["data"]
        assert data["total"] == 1
        assert data["records"][0]["id"] == hit.id

    def test_keyword_matches_nickname(
        self, client: TestClient, admin_headers: dict, session_factory
    ):
        with session_factory() as db:
            u = _make_user(db, "s2", "小王同学")
            db.add(
                ConsultationSession(
                    user_id=u.id, session_title="x", started_at=datetime.now()
                )
            )
            db.commit()

        data = client.get(
            "/api/psychological-chat/admin/sessions",
            headers=admin_headers,
            params={"keyword": "小王"},
        ).json()["data"]
        assert data["total"] == 1

    def test_risk_flag_and_risk_first_ordering(
        self, client: TestClient, admin_headers: dict, session_factory
    ):
        """默认按时间倒序时，有风险的会话会被淹没 —— 要能按「要不要关心」排序。"""
        with session_factory() as db:
            u = _make_user(db, "s3", "风险三")
            risky_old = ConsultationSession(
                user_id=u.id, session_title="有风险的老会话", started_at=datetime.now() - timedelta(hours=2)
            )
            calm_new = ConsultationSession(
                user_id=u.id, session_title="很平静的新会话", started_at=datetime.now()
            )
            db.add_all([risky_old, calm_new])
            db.commit()
            db.add(
                CrisisEvent(
                    user_id=u.id,
                    session_id=risky_old.id,
                    source="CHAT",
                    level=3,
                    trigger_type="KEYWORD",
                    matched_terms="自杀",
                    status="PENDING",
                    created_at=datetime.now(),
                )
            )
            db.commit()

        default = client.get("/api/psychological-chat/admin/sessions", headers=admin_headers).json()["data"]
        assert default["records"][0]["id"] == calm_new.id, "默认仍是时间倒序"

        first = client.get(
            "/api/psychological-chat/admin/sessions", headers=admin_headers, params={"riskFirst": True}
        ).json()["data"]
        assert first["records"][0]["id"] == risky_old.id
        assert first["records"][0]["riskLevel"] == 3
        assert first["records"][0]["crisisCount"] == 1

        only = client.get(
            "/api/psychological-chat/admin/sessions", headers=admin_headers, params={"riskOnly": True}
        ).json()["data"]
        assert only["total"] == 1
        assert only["records"][0]["id"] == risky_old.id

    def test_risk_only_excludes_calm_sessions(
        self, client: TestClient, admin_headers: dict, session_factory
    ):
        with session_factory() as db:
            u = _make_user(db, "s4", "风险四")
            db.add(
                ConsultationSession(
                    user_id=u.id, session_title="纯粹闲聊", started_at=datetime.now()
                )
            )
            db.commit()

        data = client.get(
            "/api/psychological-chat/admin/sessions", headers=admin_headers, params={"riskOnly": True}
        ).json()["data"]
        assert data["total"] == 0
