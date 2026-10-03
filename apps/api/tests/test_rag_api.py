"""RAG 集成测试：切片索引 → 检索 → SSE 注入与来源下发。

链路里最容易出错的两处：
1. 文章改了但切片没重建 → 检索到旧内容（测试用"改完再检索"覆盖）
2. 检索命中了却没告诉前端来源 → 用户不知道答案依据（测试用 sources 事件覆盖）
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.services import ai as ai_service

ANXIETY_ARTICLE = {
    "title": "缓解考试焦虑的方法",
    "content": "考试焦虑是很常见的反应。深呼吸练习、规律作息、适度运动都能帮助缓解。"
    "如果焦虑持续影响生活，建议寻求专业帮助。",
    "summary": "考试焦虑的应对方法",
}

SLEEP_ARTICLE = {
    "title": "如何改善睡眠",
    "content": "保持规律作息、睡前远离手机、避免咖啡因，都有助于改善睡眠质量。",
    "summary": "睡眠改善建议",
}


def _make_category(client: TestClient, admin_headers: dict) -> int:
    """文章需要 category_id，直接用 SQL 造一个分类。"""

    # 用接口没有创建分类的能力（原版也没有），直接走 db
    return 1  # 占位，下面用 db session 覆盖


@pytest.fixture
def article_setup(client: TestClient, admin_headers: dict, db_engine):
    """插入一个分类，返回其 id。"""
    from sqlalchemy.orm import Session, sessionmaker

    from app.models import KnowledgeCategory

    Session_ = sessionmaker(bind=db_engine, class_=Session, expire_on_commit=False)
    with Session_() as db:
        c = KnowledgeCategory(category_name="情绪管理", sort_order=1, status=1)
        db.add(c)
        db.commit()
        db.refresh(c)
        return c.id


def _create_article(client: TestClient, headers: dict, cat_id: int, payload: dict) -> str:
    body = client.post(
        "/api/knowledge/article",
        headers=headers,
        json={"categoryId": cat_id, **payload},
    ).json()
    assert body["code"] == "200", body
    return body["data"]["id"]


def _fake_reply(chunks: list[str]):
    async def _gen(conversation_id: str, user_message: str, extra_context: str = ""):
        for c in chunks:
            yield c

    return _gen


def _parse_events(text: str) -> list[tuple[str, str]]:
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event, data = None, []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data.append(line[len("data:") :].strip())
        if event:
            events.append((event, "\n".join(data)))
    return events


class TestReindexEndpoint:
    def test_requires_admin(self, client: TestClient, auth_headers: dict):
        resp = client.post("/api/knowledge/admin/reindex", headers=auth_headers)
        assert resp.status_code == 400
        assert resp.json()["code"] == "A0300"

    def test_reindex_empty(self, client: TestClient, admin_headers: dict):
        body = client.post("/api/knowledge/admin/reindex", headers=admin_headers).json()
        assert body["code"] == "200"
        assert body["data"] == {"articles": 0, "chunks": 0}

    def test_reindex_counts_articles_and_chunks(
        self, client: TestClient, admin_headers: dict, article_setup: int
    ):
        _create_article(client, admin_headers, article_setup, ANXIETY_ARTICLE)
        body = client.post("/api/knowledge/admin/reindex", headers=admin_headers).json()
        assert body["data"]["articles"] == 1
        assert body["data"]["chunks"] >= 1


class TestChunkLifecycle:
    def test_article_create_builds_chunks(
        self, client: TestClient, admin_headers: dict, article_setup: int, db_engine
    ):
        article_id = _create_article(client, admin_headers, article_setup, ANXIETY_ARTICLE)

        from sqlalchemy.orm import Session, sessionmaker

        from app.models import KnowledgeChunk

        Session_ = sessionmaker(bind=db_engine, class_=Session, expire_on_commit=False)
        with Session_() as db:
            chunks = db.query(KnowledgeChunk).filter(
                KnowledgeChunk.article_id == article_id
            ).all()
            assert len(chunks) >= 1
            assert any("考试焦虑" in (c.content or "") for c in chunks)

    def test_article_update_rebuilds_chunks(
        self, client: TestClient, admin_headers: dict, article_setup: int, db_engine
    ):
        """★ 改了正文必须重建切片，否则检索到的是旧内容。"""
        article_id = _create_article(client, admin_headers, article_setup, ANXIETY_ARTICLE)

        client.put(
            f"/api/knowledge/article/{article_id}",
            headers=admin_headers,
            json={
                "categoryId": article_setup,
                "title": "冥想入门",
                "content": "冥想可以帮助你专注当下的呼吸，减少杂念。",
                "status": 1,
            },
        )

        from sqlalchemy.orm import Session, sessionmaker

        from app.models import KnowledgeChunk

        Session_ = sessionmaker(bind=db_engine, class_=Session, expire_on_commit=False)
        with Session_() as db:
            chunks = db.query(KnowledgeChunk).filter(
                KnowledgeChunk.article_id == article_id
            ).all()
            joined = "".join(c.content or "" for c in chunks)
            assert "冥想" in joined
            assert "考试焦虑" not in joined, "旧切片必须被清掉"

    def test_article_delete_removes_chunks(
        self, client: TestClient, admin_headers: dict, article_setup: int, db_engine
    ):
        article_id = _create_article(client, admin_headers, article_setup, ANXIETY_ARTICLE)
        client.delete(f"/api/knowledge/article/{article_id}", headers=admin_headers)

        from sqlalchemy.orm import Session, sessionmaker

        from app.models import KnowledgeChunk

        Session_ = sessionmaker(bind=db_engine, class_=Session, expire_on_commit=False)
        with Session_() as db:
            left = db.query(KnowledgeChunk).filter(
                KnowledgeChunk.article_id == article_id
            ).count()
            assert left == 0

    def test_draft_article_not_indexed(
        self, client: TestClient, admin_headers: dict, article_setup: int, db_engine
    ):
        """草稿不该被检索到。"""
        _create_article(
            client, admin_headers, article_setup, {**ANXIETY_ARTICLE, "status": 0}
        )
        body = client.post("/api/knowledge/admin/reindex", headers=admin_headers).json()
        assert body["data"] == {"articles": 0, "chunks": 0}


class TestSseSourcesEvent:
    def _start_session(self, client: TestClient, headers: dict) -> str:
        return client.post(
            "/api/psychological-chat/session/start",
            headers=headers,
            json={"initialMessage": "你好"},
        ).json()["data"]["sessionId"]

    def test_sources_event_when_hit(
        self, client: TestClient, auth_headers: dict, admin_headers: dict,
        article_setup: int, monkeypatch
    ):
        """★ 问题命中知识库时，应在 AI 回复之前下发来源。"""
        _create_article(client, admin_headers, article_setup, ANXIETY_ARTICLE)
        monkeypatch.setattr(ai_service, "stream_reply", _fake_reply(["嗯"]))

        sid = self._start_session(client, auth_headers)
        resp = client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": sid, "userMessage": "考试焦虑怎么办"},
        )

        events = _parse_events(resp.text)
        names = [e for e, _ in events]
        assert "sources" in names
        assert names.index("sources") < names.index("message"), "来源应早于正文下发"

        payload = json.loads(dict(events)["sources"])
        assert payload["code"] == "200"
        sources = payload["data"]["sources"]
        assert len(sources) >= 1
        assert sources[0]["title"] == "缓解考试焦虑的方法"
        assert "articleId" in sources[0]

    def test_no_sources_event_when_no_hit(
        self, client: TestClient, auth_headers: dict, admin_headers: dict,
        article_setup: int, monkeypatch
    ):
        _create_article(client, admin_headers, article_setup, SLEEP_ARTICLE)
        monkeypatch.setattr(ai_service, "stream_reply", _fake_reply(["嗯"]))

        sid = self._start_session(client, auth_headers)
        resp = client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": sid, "userMessage": "量子力学的测不准原理"},
        )
        names = [e for e, _ in _parse_events(resp.text)]
        assert "sources" not in names
        # agent 事件总是有的，sources 才需要命中才有
        assert "agent" in names

    def test_rag_context_passed_to_model(
        self, client: TestClient, auth_headers: dict, admin_headers: dict,
        article_setup: int, monkeypatch
    ):
        """★ 检索到的内容必须真的传进模型调用，而不只是发给前端。"""
        _create_article(client, admin_headers, article_setup, ANXIETY_ARTICLE)
        captured: dict = {}

        async def _capture(conversation_id: str, user_message: str, extra_context: str = ""):
            captured["context"] = extra_context
            yield "收到"

        monkeypatch.setattr(ai_service, "stream_reply", _capture)

        sid = self._start_session(client, auth_headers)
        client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": sid, "userMessage": "考试焦虑怎么办"},
        )

        assert captured.get("context"), "extra_context 不该为空"
        assert "参考资料" in captured["context"]
        assert "缓解考试焦虑的方法" in captured["context"]

    def test_no_context_when_no_hit(
        self, client: TestClient, auth_headers: dict, admin_headers: dict,
        article_setup: int, monkeypatch
    ):
        _create_article(client, admin_headers, article_setup, SLEEP_ARTICLE)
        captured: dict = {}

        async def _capture(conversation_id: str, user_message: str, extra_context: str = ""):
            captured["context"] = extra_context
            yield "收到"

        monkeypatch.setattr(ai_service, "stream_reply", _capture)

        sid = self._start_session(client, auth_headers)
        client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": sid, "userMessage": "量子力学的测不准原理"},
        )
        # extra_context 里始终会有 agent 的场景约束，但**不该**含参考资料
        assert "参考资料" not in captured.get("context", "")

    def test_stream_still_works_without_rag(
        self, client: TestClient, auth_headers: dict, monkeypatch
    ):
        """知识库为空时，对话流程必须完全不受影响。"""
        monkeypatch.setattr(ai_service, "stream_reply", _fake_reply(["你好", "呀"]))

        sid = self._start_session(client, auth_headers)
        resp = client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": sid, "userMessage": "嗨"},
        )
        names = [e for e, _ in _parse_events(resp.text)]
        assert names == ["agent", "message", "message", "done"]
