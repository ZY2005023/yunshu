"""AI 失败重试去重 + 限流器的回归测试。

B4（重试重复）：AI 调用失败后用户重发同一条消息 —— 修复前会
在库和模型记忆里各存两遍（prepare 只认 count==1、记忆在调 API 前写入
且失败不回滚）。修复后：prepare 按「最后一条是否本人发的同一句」判重，
stream_reply 失败时撤回刚记入的记忆。

限流：上线前的硬缺口 —— 登录可无限爆破、AI 接口可被刷。

注意断言的一个陷阱：**业务失败本来就是 code 6000**（"用户名或密码错误"
也是 6000），所以判断限流要看 msg 里的「频繁」，不能只看 code。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.services import ai as ai_service


def _parse_events(text: str) -> list[tuple[str, str]]:
    """把 SSE 报文解析成 [(event, data), ...]（与 test_chat_stream 同款）。"""
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


def _fake_reply(chunks: list[str]):
    async def _gen(conversation_id: str, user_message: str, extra_context: str = ""):
        for c in chunks:
            yield c

    return _gen


@pytest.fixture
def session_id(client: TestClient, auth_headers: dict) -> str:
    body = client.post(
        "/api/psychological-chat/session/start",
        headers=auth_headers,
        json={"initialMessage": "你好"},
    ).json()
    return body["data"]["sessionId"]


def _count_user_messages(client: TestClient, headers: dict, session_id: str, content: str) -> int:
    resp = client.get(f"/api/psychological-chat/sessions/{session_id}/messages", headers=headers)
    messages = resp.json()["data"]["messages"]
    return sum(1 for m in messages if m["senderType"] == 1 and m["content"] == content)


class TestRetryDedup:
    def test_retry_after_failure_saves_once(
        self, client: TestClient, auth_headers: dict, session_id: str, monkeypatch
    ):
        """AI 中途断流 → 重发同一句 → 库里只应有一条。"""
        async def failing_gen(conversation_id: str, user_message: str, extra_context: str = ""):
            yield "部分"
            raise RuntimeError("upstream boom")

        monkeypatch.setattr(ai_service, "stream_reply", failing_gen)
        first = client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": session_id, "userMessage": "我有点累"},
        )
        assert any(e == "error" for e, _ in _parse_events(first.text)), "第一次应降级为 error 事件"

        monkeypatch.setattr(ai_service, "stream_reply", _fake_reply(["抱抱"]))
        client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": session_id, "userMessage": "我有点累"},
        )

        assert _count_user_messages(client, auth_headers, session_id, "我有点累") == 1

    def test_deliberate_repeat_with_reply_in_between_is_kept(
        self, client: TestClient, auth_headers: dict, session_id: str, monkeypatch
    ):
        """AI 正常回复后再发同一句是**合法的新消息**，不能被误伤去重。"""
        monkeypatch.setattr(ai_service, "stream_reply", _fake_reply(["一"]))
        client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": session_id, "userMessage": "在吗"},
        )
        monkeypatch.setattr(ai_service, "stream_reply", _fake_reply(["二"]))
        client.post(
            "/api/psychological-chat/stream",
            headers=auth_headers,
            json={"sessionId": session_id, "userMessage": "在吗"},
        )
        assert _count_user_messages(client, auth_headers, session_id, "在吗") == 2


class TestMemoryDiscard:
    """stream_reply 的记忆回滚 —— 打桩 openai 客户端直接测单元行为。"""

    def _drive(self, coro_factory):
        asyncio.run(coro_factory())

    def test_failure_discards_user_message(self, monkeypatch):
        async def fail_create(**kwargs):
            raise RuntimeError("connect refused")

        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fail_create))
        )
        monkeypatch.setattr(ai_service, "_client", lambda timeout=None: fake_client)

        conv = "conversation_discard_fail"
        ai_service.chat_memory.clear(conv)

        async def run():
            gen = ai_service.stream_reply(conv, "我有点累")
            with pytest.raises(ai_service.AiUnavailable):
                async for _ in gen:
                    pass

        self._drive(run)
        turns = [m for m in ai_service.chat_memory.get(conv) if m["role"] == "user"]
        assert turns == [], "失败后用户消息应被撤回"

    def test_success_keeps_user_message(self, monkeypatch):
        async def ok_create(**kwargs):
            async def _stream():
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="在"))])

            return _stream()

        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=ok_create))
        )
        monkeypatch.setattr(ai_service, "_client", lambda timeout=None: fake_client)

        conv = "conversation_discard_ok"
        ai_service.chat_memory.clear(conv)

        async def run():
            gen = ai_service.stream_reply(conv, "在吗")
            chunks = [c async for c in gen]
            assert chunks == ["在"]

        self._drive(run)
        turns = [m for m in ai_service.chat_memory.get(conv) if m["role"] == "user"]
        assert turns == [{"role": "user", "content": "在吗"}], "成功路径不能误撤回"


class TestLoginRateLimit:
    def test_bruteforce_blocked(self, client: TestClient, registered_user: dict):
        """同一 账号+IP 连续失败超过阈值 → 提示「频繁」（不再无限爆破）。"""
        last_msg = ""
        for _ in range(6):
            resp = client.post(
                "/api/user/login",
                json={"username": registered_user["username"], "password": "wrong-password"},
            )
            last_msg = resp.json()["msg"]
        assert "频繁" in last_msg, f"第 6 次应被限流，实际: {last_msg}"

    def test_limit_is_per_account_not_global(self, client: TestClient, registered_user: dict):
        """另一账号不受同一爆破源影响（按 账号+IP 分桶）。"""
        for _ in range(5):
            client.post(
                "/api/user/login",
                json={"username": registered_user["username"], "password": "wrong-password"},
            )
        resp = client.post(
            "/api/user/login",
            json={"username": "someone_else", "password": "whatever123"},
        )
        assert "频繁" not in resp.json()["msg"], "不该被别的账号的计数连坐"

    def test_env_zero_disables(self, client: TestClient, registered_user: dict, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_LOGIN_PER_MIN", "0")
        for _ in range(10):
            resp = client.post(
                "/api/user/login",
                json={"username": registered_user["username"], "password": "wrong-password"},
            )
            assert "频繁" not in resp.json()["msg"]

    def test_correct_login_not_blocked_by_others_failures(
        self, client: TestClient, registered_user: dict
    ):
        """同一账号被爆破的同时，知道正确密码仍能登录？——不能。
        按账号限流意味着爆破也在锁这个账号，正确密码在第 6 次同样被拦。
        这是刻意的取舍：宁可真用户多等一分钟，不给爆破留窗口。"""
        for _ in range(5):
            client.post(
                "/api/user/login",
                json={"username": registered_user["username"], "password": "wrong-password"},
            )
        resp = client.post(
            "/api/user/login",
            json={"username": registered_user["username"], "password": registered_user["password"]},
        )
        assert "频繁" in resp.json()["msg"]


class TestAiRateLimit:
    def _stream(self, client: TestClient, headers: dict, session_id: str, msg: str):
        return client.post(
            "/api/psychological-chat/stream",
            headers=headers,
            json={"sessionId": session_id, "userMessage": msg},
        )

    def test_stream_rate_limited(
        self, client: TestClient, auth_headers: dict, session_id: str, monkeypatch
    ):
        monkeypatch.setattr(ai_service, "stream_reply", _fake_reply(["好"]))
        monkeypatch.setenv("RATE_LIMIT_AI_PER_MIN", "3")

        limited = []
        for i in range(4):
            resp = self._stream(client, auth_headers, session_id, f"消息 {i}")
            if resp.headers["content-type"].startswith("text/event-stream"):
                # 限流在进入 SSE 之前抛出，走到这里说明没被限
                limited.append(False)
            else:
                limited.append("频繁" in resp.json().get("msg", ""))

        assert limited == [False, False, False, True]

    def test_default_limit_allows_normal_usage(
        self, client: TestClient, auth_headers: dict, session_id: str, monkeypatch
    ):
        """默认阈值（10 次/分钟）下正常连续对话不应被误伤。"""
        monkeypatch.setattr(ai_service, "stream_reply", _fake_reply(["好"]))
        for i in range(5):
            resp = self._stream(client, auth_headers, session_id, f"消息 {i}")
            assert resp.headers["content-type"].startswith("text/event-stream"), (
                f"第 {i + 1} 次被误限流: {resp.json()}"
            )
