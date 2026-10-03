"""用户模块端到端测试 —— 6 个接口的行为契约。

每个断言都对应契约清单 2.1 的一条约定，或用例说明里的一条原版行为。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models import User

REGISTER = {
    "username": "bob",
    "email": "bob@example.com",
    "nickname": "鲍勃",
    "password": "secret123",
    "confirmPassword": "secret123",
}


def _register(client: TestClient, **overrides) -> dict:
    payload = {**REGISTER, **overrides}
    return client.post("/api/user/add", json=payload).json()


def _login(client: TestClient, username: str = "bob", password: str = "secret123") -> dict:
    return client.post("/api/user/login", json={"username": username, "password": password}).json()


# ===========================================================================
# 注册
# ===========================================================================


class TestRegister:
    def test_success_shape(self, client: TestClient):
        body = _register(client)
        assert body["code"] == "200"
        assert body["msg"] == "操作成功"
        data = body["data"]
        assert data["username"] == "bob"
        assert data["email"] == "bob@example.com"

    def test_register_forces_normal_user_type(self, client: TestClient):
        """★ 安全修复：即使客户端传 userType=2，也必须落成普通用户。

        原版此处直接采信客户端传值，导致匿名注册接口可用来造管理员。
        """
        body = _register(client, userType=2, username="hacker", email="h@example.com")
        assert body["code"] == "200"
        assert body["data"]["userType"] == 1, "注册接口不得产生管理员"
        assert body["data"]["userTypeDisplayName"] == "普通用户"

    def test_duplicate_username(self, client: TestClient):
        _register(client)
        body = _register(client, email="other@example.com")
        assert body["code"] == "6001"
        assert body["msg"] == "用户名已存在"

    def test_duplicate_email(self, client: TestClient):
        _register(client)
        body = _register(client, username="other")
        assert body["code"] == "6001"
        assert body["msg"] == "邮箱已存在"

    def test_password_mismatch(self, client: TestClient):
        body = _register(client, confirmPassword="different1")
        assert body["msg"] == "两次输入密码不一致"
        # 单参 BusinessException 用的是 ResultCode.BUSINESS_ERROR = 6000（不是 -1）
        assert body["code"] == "6000"

    def test_username_pattern_rejected(self, client: TestClient):
        body = _register(client, username="bad name!")
        assert body["code"] == "400"

    def test_short_password_rejected(self, client: TestClient):
        body = _register(client, password="123", confirmPassword="123")
        assert body["code"] == "400"

    def test_response_has_derived_fields(self, client: TestClient):
        data = _register(client)["data"]
        assert data["genderDisplayName"] == "未知"
        assert data["statusDisplayName"] == "正常"
        assert data["displayName"] == "鲍勃"  # nickname 优先

    def test_display_name_falls_back_to_username(self, client: TestClient):
        body = _register(client, nickname=None, username="nicky", email="n@example.com")
        assert body["data"]["displayName"] == "nicky"


# ===========================================================================
# 登录
# ===========================================================================


class TestLogin:
    def test_success_shape(self, client: TestClient):
        _register(client)
        body = _login(client)
        assert body["code"] == "200"
        data = body["data"]
        assert data["token"]
        assert data["refreshToken"]
        # ⚠️ roleType 是字符串，不是整数
        assert data["roleType"] == "1"
        assert isinstance(data["roleType"], str)
        assert data["userInfo"]["username"] == "bob"

    def test_login_by_email(self, client: TestClient):
        _register(client)
        body = client.post(
            "/api/user/login", json={"username": "bob@example.com", "password": "secret123"}
        ).json()
        assert body["code"] == "200"

    def test_wrong_password_same_message_as_missing_account(self, client: TestClient):
        """账号不存在与密码错误必须同文案，否则能被用来枚举注册用户。"""
        _register(client)
        wrong = _login(client, password="wrongpass")
        missing = _login(client, username="nobody")
        assert wrong["msg"] == missing["msg"] == "用户名或密码错误"

    def test_disabled_user_rejected(self, client: TestClient, db_engine):
        _register(client)
        Session_ = sessionmaker(bind=db_engine, class_=Session, expire_on_commit=False)
        with Session_() as db:
            user = db.query(User).filter(User.username == "bob").one()
            user.status = 0
            db.commit()
        body = _login(client)
        assert body["msg"] == "用户已被禁用，请联系管理员"


# ===========================================================================
# 当前用户
# ===========================================================================


class TestCurrentUser:
    def test_without_token_returns_a0301(self, client: TestClient):
        resp = client.get("/api/user/current")
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] == "A0301"
        assert set(body.keys()) == {"code", "msg", "data"}

    def test_with_token(self, client: TestClient, auth_headers: dict):
        body = client.get("/api/user/current", headers=auth_headers).json()
        assert body["code"] == "200"
        # auth_headers 基于 registered_user fixture（alice）
        assert body["data"]["username"] == "alice"

    def test_garbage_token_returns_a0230(self, client: TestClient):
        resp = client.get("/api/user/current", headers={"Authorization": "Bearer not-a-token"})
        assert resp.status_code == 401
        assert resp.json()["code"] == "A0230"

    def test_legacy_token_header_supported(self, client: TestClient, registered_user: dict):
        """兼容旧客户端：Authorization 为空时回退读 `token` 头。"""
        token = _login(client, registered_user["username"], registered_user["password"])["data"]["token"]
        body = client.get("/api/user/current", headers={"token": token}).json()
        assert body["code"] == "200"


# ===========================================================================
# 退出登录
# ===========================================================================


class TestLogout:
    def test_token_revoked_after_logout(self, client: TestClient, auth_headers: dict):
        assert client.get("/api/user/current", headers=auth_headers).json()["code"] == "200"
        assert client.post("/api/user/logout", headers=auth_headers).json()["code"] == "200"
        resp = client.get("/api/user/current", headers=auth_headers)
        assert resp.status_code == 401
        assert resp.json()["code"] == "A0230"  # 黑名单走的也是 A0230

    def test_logout_without_body_is_allowed(self, client: TestClient, auth_headers: dict):
        """body 可选，这是原版 `@RequestBody(required = false)` 的行为。"""
        assert client.post("/api/user/logout", headers=auth_headers).json()["code"] == "200"


# ===========================================================================
# 刷新令牌
# ===========================================================================


class TestRefresh:
    def test_refresh_returns_new_tokens(self, client: TestClient):
        _register(client)
        old = _login(client)["data"]
        body = client.post("/api/user/refresh", json={"refreshToken": old["refreshToken"]}).json()
        assert body["code"] == "200"
        assert body["data"]["token"]
        assert body["data"]["userInfo"]["username"] == "bob"

    def test_access_token_rejected_as_refresh(self, client: TestClient):
        """防止用 access token 无限续期。"""
        _register(client)
        access = _login(client)["data"]["token"]
        body = client.post("/api/user/refresh", json={"refreshToken": access}).json()
        assert body["code"] == "A0230"
        assert body["msg"] == "令牌类型不正确"

    def test_invalid_refresh_token(self, client: TestClient):
        body = client.post("/api/user/refresh", json={"refreshToken": "garbage.token.value"}).json()
        assert body["code"] == "A0230"
        assert body["msg"] == "刷新令牌无效或已过期，请重新登录"


# ===========================================================================
# 修改密码
# ===========================================================================


class TestChangePassword:
    def test_change_then_old_token_invalid(self, client: TestClient, registered_user: dict):
        headers = {
            "Authorization": f"Bearer {_login(client, registered_user['username'], registered_user['password'])['data']['token']}"
        }
        body = client.post(
            "/api/user/password",
            headers=headers,
            json={
                "oldPassword": registered_user["password"],
                "newPassword": "brandnew123",
                "confirmPassword": "brandnew123",
            },
        ).json()
        assert body["code"] == "200"

        # 改密即全端下线
        assert client.get("/api/user/current", headers=headers).status_code == 401
        # 新密码可登录
        assert _login(client, registered_user["username"], "brandnew123")["code"] == "200"

    def test_confirm_mismatch(self, client: TestClient, auth_headers: dict, registered_user: dict):
        body = client.post(
            "/api/user/password",
            headers=auth_headers,
            json={
                "oldPassword": registered_user["password"],
                "newPassword": "aaaaaa111",
                "confirmPassword": "bbbbbb222",
            },
        ).json()
        assert body["msg"] == "两次输入的新密码不一致"

    def test_wrong_old_password(self, client: TestClient, auth_headers: dict):
        body = client.post(
            "/api/user/password",
            headers=auth_headers,
            json={"oldPassword": "wrongone", "newPassword": "aaaaaa111", "confirmPassword": "aaaaaa111"},
        ).json()
        assert body["msg"] == "原密码不正确"

    def test_same_as_old_rejected(self, client: TestClient, auth_headers: dict, registered_user: dict):
        body = client.post(
            "/api/user/password",
            headers=auth_headers,
            json={
                "oldPassword": registered_user["password"],
                "newPassword": registered_user["password"],
                "confirmPassword": registered_user["password"],
            },
        ).json()
        assert body["msg"] == "新密码不能与原密码相同"


# ===========================================================================
# 密码哈希格式
# ===========================================================================


class TestPasswordHashing:
    def test_stored_hash_is_bcrypt_2a_10(self, client: TestClient, db_engine):
        """老库里是 Java BCryptPasswordEncoder 的 $2a$10$ 哈希，
        新写入的必须同格式，否则两边不能互相验证。"""
        _register(client)
        Session_ = sessionmaker(bind=db_engine, class_=Session, expire_on_commit=False)
        with Session_() as db:
            user = db.query(User).filter(User.username == "bob").one()
            assert user.password.startswith("$2a$10$"), user.password[:20]

    def test_hash_is_not_plaintext(self, client: TestClient, db_engine):
        _register(client)
        Session_ = sessionmaker(bind=db_engine, class_=Session, expire_on_commit=False)
        with Session_() as db:
            user = db.query(User).filter(User.username == "bob").one()
            assert "secret123" not in user.password


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
