"""SSE 流式对话测试。

重点验证三件事：
1. **事件序列**：crisis 必须在 message 之前，done 必须是最后一条
2. **done 的 data 是裸 `{}`** —— 这是最容易复制错的一处
3. **降级行为**：AI 不可用时发 error 事件并保持连接正常结束，不能裸崩

没有真实 API key，所以正常路径靠 monkeypatch 打桩；
真实调用失败的那条路径反而可以真实测。
"""

from __future__ import annotations


import pytest
from fastapi.testclient import TestClient

from app.services import ai as ai_service


def _parse_events(text: str) -> list[tuple[str, str]]:
    """把 SSE 报文解析成 [(event, data), ...]。"""
    events: list[tuple[str, str]] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event = None
        data_lines = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        if event is not None:
            events.append((event, "\n".join(data_lines)))
    return events


@pytest.fixture
def session_id(client: TestClient, auth_headers: dict) -> str:
    body = client.post(
        "/api/psychological-chat/session/start",
        headers=auth_headers,
        json={"initialMessage": "你好"},
    ).json()
    return body["data"]["sessionId"]


def _fake_reply(chunks: list[str]):
    # 注意签名要和 ai.stream_reply 保持一致（第三参是 RAG 注入的参考资料）
    async def _gen(conversation_id: str, user_message: str, extra_context: str = ""):
        for c in chunks:
            yield c

    return _gen


class TestEventSequence:
    def test_normal_stream(self, client: TestClient, auth_headers: dict, session_id: str, monkeypatch):
        monkeypatch.setattr(ai_service, "stream_reply", _fake_reply(["你", "好", "呀"]))

        resp = client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": session_id, "userMessage": "我有点累"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        events = _parse_events(resp.text)
        names = [e for e, _ in events]
        # 第一段固定是 agent（意图路由结果），然后是正文，最后 done
        assert names == ["agent", "message", "message", "message", "done"]

    def test_done_data_is_bare_empty_object(
        self, client: TestClient, auth_headers: dict, session_id: str, monkeypatch
    ):
        """★ 最容易复制错的一处：done 的 data 是 `{}`，不是 Result 包装。"""
        monkeypatch.setattr(ai_service, "stream_reply", _fake_reply(["嗨"]))

        resp = client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": session_id, "userMessage": "在吗"},
        )
        events = dict(_parse_events(resp.text))
        assert events["done"] == "{}"
        assert "code" not in events["done"]

    def test_message_payload_shape(
        self, client: TestClient, auth_headers: dict, session_id: str, monkeypatch
    ):
        monkeypatch.setattr(ai_service, "stream_reply", _fake_reply(["片段"]))

        resp = client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": session_id, "userMessage": "嗨"},
        )
        events = dict(_parse_events(resp.text))
        assert '"code":"200"' in events["message"].replace(" ", "")
        assert '"content":"片段"' in events["message"].replace(" ", "")
        assert '"type":"normal"' in events["message"].replace(" ", "")

    def test_crisis_event_precedes_messages(
        self, client: TestClient, auth_headers: dict, session_id: str, monkeypatch
    ):
        """★ 危机卡片必须在 AI 回复之前下发。"""
        monkeypatch.setattr(ai_service, "stream_reply", _fake_reply(["我在", "听"]))

        resp = client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": session_id, "userMessage": "我不想活了"},
        )
        events = _parse_events(resp.text)
        names = [e for e, _ in events]
        assert names[0] == "crisis"
        assert names[-1] == "done"
        assert names.count("crisis") == 1

    def test_crisis_card_content(
        self, client: TestClient, auth_headers: dict, session_id: str, monkeypatch
    ):
        monkeypatch.setattr(ai_service, "stream_reply", _fake_reply(["嗯"]))

        resp = client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": session_id, "userMessage": "我想自杀"},
        )
        crisis_data = dict(_parse_events(resp.text))["crisis"]
        assert '"level":3' in crisis_data.replace(" ", "")
        assert "12356" in crisis_data
        assert "免责声明" in crisis_data

    def test_no_crisis_event_for_neutral_text(
        self, client: TestClient, auth_headers: dict, session_id: str, monkeypatch
    ):
        monkeypatch.setattr(ai_service, "stream_reply", _fake_reply(["嗯"]))

        resp = client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": session_id, "userMessage": "今天天气不错"},
        )
        names = [e for e, _ in _parse_events(resp.text)]
        assert "crisis" not in names


class TestDegradation:
    def test_ai_failure_yields_error_event(
        self, client: TestClient, auth_headers: dict, session_id: str, monkeypatch
    ):
        """★ AI 挂了也不能让连接裸崩，要给一条可读提示。"""

        async def _boom(conversation_id: str, user_message: str, extra_context: str = ""):
            yield "开头"
            raise RuntimeError("upstream 500")

        monkeypatch.setattr(ai_service, "stream_reply", _boom)

        resp = client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": session_id, "userMessage": "嗨"},
        )
        assert resp.status_code == 200
        events = _parse_events(resp.text)
        names = [e for e, _ in events]
        assert names[0] == "agent"
        assert "message" in names, "已经吐出的片段不回收"
        assert names[-1] == "error"
        assert "AI 服务暂时不可用" in dict(events)["error"]
        # 出错时不发 done
        assert "done" not in names

    def test_invalid_session_id(self, client: TestClient, auth_headers: dict):
        resp = client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": "session_not-a-number", "userMessage": "嗨"},
        )
        events = _parse_events(resp.text)
        assert [e for e, _ in events] == ["error"]
        assert "会话ID格式错误" in events[0][1]

    def test_other_user_gets_error_event(self, client: TestClient, auth_headers: dict, session_id: str):
        """越权时也是 error 事件（保持 SSE 协议），不是 HTTP 错误页。"""
        client.post(
            "/api/user/add",
            json={
                "username": "mallory",
                "email": "m@example.com",
                "password": "secret123",
                "confirmPassword": "secret123",
            },
        )
        token = client.post(
            "/api/user/login", json={"username": "mallory", "password": "secret123"}
        ).json()["data"]["token"]

        resp = client.post(
            "/api/psychological-chat/stream",
            headers={"Authorization": f"Bearer {token}"},
            json={"sessionId": session_id, "userMessage": "偷看"},
        )
        events = _parse_events(resp.text)
        assert [e for e, _ in events] == ["error"]
        assert "无权访问该会话" in events[0][1]

    def test_requires_login(self, client: TestClient, session_id: str):
        resp = client.post(
            "/api/psychological-chat/stream",
            json={"sessionId": session_id, "userMessage": "嗨"},
        )
        assert resp.status_code == 401


class TestPersistence:
    def test_reply_is_persisted_after_stream(
        self, client: TestClient, auth_headers: dict, session_id: str, monkeypatch
    ):
        monkeypatch.setattr(ai_service, "stream_reply", _fake_reply(["完整", "回复"]))

        # 注意：内容必须与建会话时的 initialMessage（"你好"）不同，
        # 否则会命中"首条消息已保存"的去重逻辑（见下一个用例）
        client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": session_id, "userMessage": "我最近有点累"},
        )

        messages = client.get(
            f"/api/psychological-chat/sessions/{session_id}/messages", headers=auth_headers
        ).json()["data"]["messages"]
        # initialMessage + 本次用户消息 + AI 回复
        assert len(messages) == 3
        ai_msg = messages[-1]
        assert ai_msg["senderType"] == 2
        assert ai_msg["senderTypeDesc"] == "AI助手"
        assert ai_msg["content"] == "完整回复"
        assert ai_msg["aiModel"] == "deepseek-chat"

    def test_first_message_not_saved_twice(
        self, client: TestClient, auth_headers: dict, session_id: str, monkeypatch
    ):
        """★ 原版的 alreadySaved 逻辑：与建会话时的首条消息内容相同则不重复落库。

        建会话时 `initialMessage` 已经写了一条，用户在前端紧接着发送同一条
        （很常见：点发送后立刻进入对话页），不应产生两条一模一样的记录。
        """
        monkeypatch.setattr(ai_service, "stream_reply", _fake_reply(["嗯"]))

        client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": session_id, "userMessage": "你好"},  # 与 initialMessage 相同
        )

        messages = client.get(
            f"/api/psychological-chat/sessions/{session_id}/messages", headers=auth_headers
        ).json()["data"]["messages"]
        user_msgs = [m for m in messages if m["senderType"] == 1]
        assert len(user_msgs) == 1, "首条消息不应重复落库"
        assert len(messages) == 2  # 1 条用户 + 1 条 AI

    def test_crisis_ticket_created_from_chat(
        self, client: TestClient, auth_headers: dict, admin_headers: dict, session_id: str, monkeypatch
    ):
        monkeypatch.setattr(ai_service, "stream_reply", _fake_reply(["我在"]))

        client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": session_id, "userMessage": "我想自杀"},
        )

        page = client.get("/api/admin/crisis/page", headers=admin_headers).json()
        assert page["data"]["total"] >= 1
        event = page["data"]["records"][0]
        assert event["source"] == "CHAT"
        assert event["level"] == 3
        assert event["sessionId"] is not None

    def test_empty_reply_not_persisted(
        self, client: TestClient, auth_headers: dict, session_id: str, monkeypatch
    ):
        monkeypatch.setattr(ai_service, "stream_reply", _fake_reply([]))

        client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": session_id, "userMessage": "我最近有点累"},
        )
        messages = client.get(
            f"/api/psychological-chat/sessions/{session_id}/messages", headers=auth_headers
        ).json()["data"]["messages"]
        # initialMessage + 用户消息；AI 返回空则不落库
        assert len(messages) == 2
        assert all(m["senderType"] == 1 for m in messages)
