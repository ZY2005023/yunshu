"""个人中心 + 管理端用户管理 + 危机通知的测试。

这三块都是 2026-10-02 新增的（原版没有），也是补掉三个断链的关键：
  · 用户没有改密入口 → 有接口没 UI，`api/admin.js::changePassword` 曾是死代码
  · 管理员无法管理用户 → `deps.py` 里 `status != 1` 的校验永远不触发
  · 「忘记密码」指引用户找管理员，而管理员没有重置能力 → 死循环
"""

from __future__ import annotations

import pytest

from app.services import notifier


def _register(client, username: str, password: str = "secret123") -> None:
    resp = client.post(
        "/api/user/add",
        json={
            "username": username,
            "email": f"{username}@example.com",
            "password": password,
            "confirmPassword": password,
        },
    )
    assert resp.json()["code"] == "200", resp.text


def _login(client, username: str, password: str = "secret123") -> str:
    resp = client.post(
        "/api/user/login", json={"username": username, "password": password}
    )
    return resp.json()["data"]["token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _obj(resp) -> dict:
    body = resp.json()
    assert body["code"] == "200", body
    return body


# ===========================================================================
# 个人资料
# ===========================================================================


class TestProfile:
    def test_update_profile(self, client, auth_headers):
        resp = client.put(
            "/api/user/profile",
            headers=auth_headers,
            json={"nickname": "新昵称", "phone": "13800138000", "gender": 2},
        )
        data = _obj(resp)["data"]
        assert data["nickname"] == "新昵称"
        assert data["phone"] == "13800138000"
        assert data["gender"] == 2
        assert data["genderDisplayName"] == "女"

    def test_partial_update_keeps_other_fields(self, client, auth_headers, registered_user):
        """只传昵称时，其它字段不能被清空。

        这条很重要：`update_profile` 里对 None 是「跳过」而不是「置空」，
        否则用户改个昵称就会顺手把手机号、生日全抹掉。
        """
        client.put(
            "/api/user/profile",
            headers=auth_headers,
            json={"phone": "13900139000", "nickname": "改前"},
        )
        resp = client.put("/api/user/profile", headers=auth_headers, json={"nickname": "改后"})
        data = _obj(resp)["data"]
        assert data["nickname"] == "改后"
        assert data["phone"] == "13900139000", "只改昵称不应影响手机号"

    def test_cannot_escalate_privilege(self, client, auth_headers):
        """带上 userType / status 也不能提权或自行解禁。

        入参是 `extra="ignore"`，且 service 用白名单只允许 5 个字段 ——
        原版注册接口就是因为直接采信客户端传值，才留下匿名提权漏洞。
        """
        resp = client.put(
            "/api/user/profile",
            headers=auth_headers,
            json={"nickname": "想提权", "userType": 2, "status": 1, "username": "hacked"},
        )
        data = _obj(resp)["data"]
        assert data["userType"] == 1, "不能通过个人资料接口把自己变成管理员"
        assert data["username"] != "hacked", "用户名不可改"

    def test_requires_login(self, client):
        resp = client.put("/api/user/profile", json={"nickname": "x"})
        assert resp.status_code == 401

    def test_invalid_phone_rejected(self, client, auth_headers):
        resp = client.put("/api/user/profile", headers=auth_headers, json={"phone": "12345"})
        # 参数校验失败是 HTTP 200 + code 400（项目约定）
        assert resp.json()["code"] == "400"


# ===========================================================================
# 管理端：用户管理
# ===========================================================================


class TestAdminUserList:
    def test_requires_admin(self, client, registered_user, auth_headers):
        """普通用户访问 → HTTP 400 + A0300（不是 403，原版行为）。

        注意响应体是**顶层** `{code,msg,data}` —— `deps.require_admin` 把错误码塞进
        HTTPException 的 detail，再由 main 的处理器原样透出，不是嵌套在 `detail` 里。
        """
        resp = client.get("/api/user/admin/page", headers=auth_headers)
        assert resp.status_code == 400
        assert resp.json()["code"] == "A0300"

    def test_page_shape(self, client, admin_headers):
        data = _obj(client.get("/api/user/admin/page", headers=admin_headers))["data"]
        assert "records" in data and "total" in data
        assert data["total"] >= 1
        assert data["records"][0]["statusDisplayName"] in ("正常", "禁用")

    def test_never_returns_password(self, client, admin_headers):
        """列表连密码哈希都不能外传。"""
        records = _obj(client.get("/api/user/admin/page", headers=admin_headers))["data"][
            "records"
        ]
        for row in records:
            assert "password" not in row

    def test_keyword_search(self, client, admin_headers):
        _register(client, "searchme")
        data = _obj(
            client.get("/api/user/admin/page", headers=admin_headers, params={"keyword": "searchme"})
        )["data"]
        assert data["total"] == 1
        assert data["records"][0]["username"] == "searchme"

    def test_filter_by_status(self, client, admin_headers):
        data = _obj(
            client.get("/api/user/admin/page", headers=admin_headers, params={"status": 1})
        )["data"]
        assert all(r["status"] == 1 for r in data["records"])


class TestDisableUser:
    def test_disable_kills_tokens_and_blocks_login(self, client, admin_headers):
        """禁用必须**立即**让对方的登录态失效，否则「禁用」形同虚设。"""
        _register(client, "tobedisabled")
        victim_token = _login(client, "tobedisabled")
        assert client.get("/api/user/current", headers=_headers(victim_token)).status_code == 200

        target_id = next(
            r["id"]
            for r in _obj(
                client.get(
                    "/api/user/admin/page", headers=admin_headers, params={"keyword": "tobedisabled"}
                )
            )["data"]["records"]
        )
        _obj(
            client.put(
                f"/api/user/admin/{target_id}/status", headers=admin_headers, json={"status": 0}
            )
        )

        assert client.get("/api/user/current", headers=_headers(victim_token)).status_code == 401
        assert client.post(
            "/api/user/login", json={"username": "tobedisabled", "password": "secret123"}
        ).json()["code"] != "200"

    def test_reenable_allows_login(self, client, admin_headers):
        _register(client, "recover")
        tid = next(
            r["id"]
            for r in _obj(
                client.get("/api/user/admin/page", headers=admin_headers, params={"keyword": "recover"})
            )["data"]["records"]
        )
        client.put(f"/api/user/admin/{tid}/status", headers=admin_headers, json={"status": 0})
        client.put(f"/api/user/admin/{tid}/status", headers=admin_headers, json={"status": 1})
        assert client.post(
            "/api/user/login", json={"username": "recover", "password": "secret123"}
        ).json()["code"] == "200"

    def test_cannot_disable_self(self, client, admin_headers, session_factory):
        """防止管理员把自己锁在门外。"""
        from app.models import User

        with session_factory() as db:
            my_id = db.query(User).filter(User.username == "alice").one().id

        body = client.put(
            f"/api/user/admin/{my_id}/status", headers=admin_headers, json={"status": 0}
        ).json()
        assert body["code"] != "200"
        assert "自己" in body["msg"]

    def test_cannot_leave_no_admin(self, registered_user, session_factory):
        """「至少保留一个可用管理员」这条守卫。

        为什么走服务层而不是打接口：正常接口路径下操作者本人就是一个活跃管理员，
        一定会被算进 `_active_admin_count`，所以这条守卫**在接口层几乎不可能触发**。
        它是防御性的兜底（例如操作者的 user_type 在签发 token 之后被改过）。
        直接调服务层，用「非管理员 operator」来验证守卫本身是有效的。
        """
        from app.models import User
        from app.services import user as user_service

        with session_factory() as db:
            alice = db.query(User).filter(User.username == "alice").one()
            alice.user_type = 2
            alice.status = 1
            db.commit()

            # operator_id=999999 不是管理员 → alice 就是最后一个可用管理员
            with pytest.raises(Exception) as exc:
                user_service.set_status(db, alice.id, 0, operator_id=999999)
            assert "至少保留一个" in str(exc.value)


class TestResetPassword:
    def test_reset_then_login_with_new_password(self, client, admin_headers):
        """这就是「忘记密码」缺的出口：管理员能重置。"""
        _register(client, "forgetful")
        tid = next(
            r["id"]
            for r in _obj(
                client.get(
                    "/api/user/admin/page", headers=admin_headers, params={"keyword": "forgetful"}
                )
            )["data"]["records"]
        )
        _obj(
            client.post(
                f"/api/user/admin/{tid}/password",
                headers=admin_headers,
                json={"newPassword": "brandnew456"},
            )
        )
        assert client.post(
            "/api/user/login", json={"username": "forgetful", "password": "brandnew456"}
        ).json()["code"] == "200"
        assert client.post(
            "/api/user/login", json={"username": "forgetful", "password": "secret123"}
        ).json()["code"] != "200", "旧密码必须失效"

    def test_reset_revokes_existing_tokens_and_untimebans(self, client, admin_headers):
        """重置后对方旧令牌失效，并顺带解除禁用（否则重置了也登不进来）。

        ⚠️ 这里必须 sleep 跨过秒边界。原因：JWT 的 `iat` 只有秒级精度，
        而 `revoke_all_before` 记的是毫秒，`blacklist.is_issued_before_revoke`
        为此留了 999ms 容差 —— 同一秒内的「签发 + 吊销」无法区分。
        真实场景里管理员重置密码必然发生在用户上次登录之后好几秒，
        这里 sleep 是为了让测试反映真实时序，而不是掩盖问题。
        """
        import time

        _register(client, "banned")
        old_token = _login(client, "banned")
        tid = next(
            r["id"]
            for r in _obj(
                client.get(
                    "/api/user/admin/page", headers=admin_headers, params={"keyword": "banned"}
                )
            )["data"]["records"]
        )

        time.sleep(1.1)  # 跨过 iat 的秒级精度边界

        client.put(f"/api/user/admin/{tid}/status", headers=admin_headers, json={"status": 0})
        client.post(
            f"/api/user/admin/{tid}/password",
            headers=admin_headers,
            json={"newPassword": "afterreset9"},
        )

        assert client.get("/api/user/current", headers=_headers(old_token)).status_code == 401
        data = _obj(
            client.get("/api/user/admin/page", headers=admin_headers, params={"keyword": "banned"})
        )["data"]
        assert data["records"][0]["status"] == 1, "重置密码应同时解除禁用"
        assert client.post(
            "/api/user/login", json={"username": "banned", "password": "afterreset9"}
        ).json()["code"] == "200"

    def test_reenable_does_not_revive_old_tokens(self, client, admin_headers):
        """解禁后，禁用前的旧令牌不能复活。

        这是一处容易漏的安全缺口：禁用只让令牌被 `status` 校验拦下，
        令牌本身没进黑名单；状态一回到 1，它就又能用了。
        所以解禁时也必须吊销一次。
        """
        import time

        _register(client, "lockout")
        old_token = _login(client, "lockout")
        tid = next(
            r["id"]
            for r in _obj(
                client.get(
                    "/api/user/admin/page", headers=admin_headers, params={"keyword": "lockout"}
                )
            )["data"]["records"]
        )

        time.sleep(1.1)
        client.put(f"/api/user/admin/{tid}/status", headers=admin_headers, json={"status": 0})
        client.put(f"/api/user/admin/{tid}/status", headers=admin_headers, json={"status": 1})

        assert client.get("/api/user/current", headers=_headers(old_token)).status_code == 401
        # 重新登录拿到的令牌当然应该可用
        fresh = _login(client, "lockout")
        assert client.get("/api/user/current", headers=_headers(fresh)).status_code == 200

    def test_target_not_found(self, client, admin_headers):
        body = client.post(
            "/api/user/admin/999999/password",
            headers=admin_headers,
            json={"newPassword": "whatever123"},
        ).json()
        assert body["code"] != "200"

    def test_requires_admin(self, client, auth_headers):
        resp = client.post(
            "/api/user/admin/1/password", headers=auth_headers, json={"newPassword": "x123456"}
        )
        assert resp.status_code == 400


# ===========================================================================
# 危机通知
# ===========================================================================


class _FakeEvent:
    def __init__(self, **kw):
        self.id = kw.get("id", 1)
        self.user_id = kw.get("user_id", 42)
        self.source = kw.get("source", "CHAT")
        self.level = kw.get("level", 3)
        self.trigger_type = kw.get("trigger_type", "自伤")
        self.matched_terms = kw.get("matched_terms", "不想活了")
        self.content_snippet = kw.get("content_snippet", "我觉得没有意义了")
        from datetime import datetime

        # 项目统一用 naive 本地时间（与库里 DateTime 列、Java LocalDateTime 一致）
        self.created_at = kw.get("created_at", datetime(2026, 10, 2, 15, 30, 0))  # noqa: DTZ001


class TestNotifier:
    def test_message_contains_actionable_fields(self):
        """值班老师需要一眼看到：多严重、哪来的、原话是什么。"""
        text = notifier.build_message(_FakeEvent())
        assert "危机预警" in text
        assert "3 级" in text
        assert "AI 对话" in text
        assert "不想活了" in text
        assert "我觉得没有意义了" in text
        assert "2026-10-02 15:30:00" in text

    def test_source_mapped_to_chinese(self):
        assert "情绪日记" in notifier.build_message(_FakeEvent(source="DIARY"))

    def test_payload_per_platform(self):
        """三家的字段不通用，必须按域名选对格式 —— 搞错就是静默发不出去。"""
        wx = notifier._payload("hello", "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=x")
        assert wx == {"msgtype": "text", "text": {"content": "hello"}}

        dd = notifier._payload("hello", "https://oapi.dingtalk.com/robot/send?access_token=x")
        assert dd == {"msgtype": "text", "text": {"content": "hello"}}, "钉钉与企业微信同形"

        fs = notifier._payload("hello", "https://open.feishu.cn/open-apis/bot/v2/hook/xxx")
        assert fs == {"msg_type": "text", "content": {"text": "hello"}}, "飞书是 msg_type + content.text"

    def test_send_without_webhook_returns_false(self, monkeypatch):
        """未配置时不发、不抛 —— 部署方没配 webhook 不能让业务流程崩。"""
        monkeypatch.setenv("CRISIS_WEBHOOK_URL", "")
        assert notifier.send("test") is False

    def test_notify_without_webhook_does_not_raise(self, monkeypatch, caplog):
        """未配置时必须留下日志，不能静默丢弃 —— 否则没人知道通知功能没生效。"""
        monkeypatch.setenv("CRISIS_WEBHOOK_URL", "")
        with caplog.at_level("WARNING"):
            notifier.notify_crisis(_FakeEvent())
        assert any("CRISIS_WEBHOOK_URL" in r.message for r in caplog.records)

    def test_notify_posts_when_configured(self, monkeypatch):
        """配了就真的发出去，且不阻塞（线程内完成）。"""
        sent: list[str] = []
        monkeypatch.setenv("CRISIS_WEBHOOK_URL", "https://example.com/hook")
        monkeypatch.setattr(notifier, "send", lambda text: sent.append(text) or True)

        notifier.notify_crisis(_FakeEvent())
        # 通知在后台线程里，给它一点时间
        import time

        for _ in range(50):
            if sent:
                break
            time.sleep(0.02)
        assert sent and "危机预警" in sent[0]


@pytest.mark.parametrize("level,expected", [(1, "1 级"), (4, "4 级")])
def test_level_text(level, expected):
    assert expected in notifier.build_message(_FakeEvent(level=level))
