"""密码口径一致性（schemas.LoginIn / services.user._validated_password）的回归测试。

两条真实事故场景：

1. **改密允许 64 位、登录只收 50 位**：设了 51-64 位密码的用户会被
   参数校验永远拦在登录之外，而且校验失败是 HTTP 200 + code 400，
   用户看到的只是"参数错误"——账号死锁且无从排查。
2. **新密码不 strip、登录输入却 strip**：粘贴密码带一个尾空格，
   存进去的是带空格的哈希，登录时输入被 strip —— 永远"用户名或密码错误"。
   （注册与管理员重置本就 strip，唯独自助改密漏了 —— 已统一到
   `_validated_password`。）

所有登录/改密动作都走真实 HTTP 层（TestClient），让 schema 校验参与断言。
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _change_password(
    client: TestClient, headers: dict, old: str, new: str
):
    return client.post(
        "/api/user/password",
        headers=headers,
        json={"oldPassword": old, "newPassword": new, "confirmPassword": new},
    )


def _login(client: TestClient, username: str, password: str):
    return client.post("/api/user/login", json={"username": username, "password": password})


class TestPasswordMaxLengthConsistency:
    def test_55_char_password_set_via_profile_then_login(
        self, client: TestClient, auth_headers: dict, registered_user: dict
    ):
        """改密设 55 位密码 → 用它登录必须成功（LoginIn max 已对齐到 64）。"""
        long_pwd = "x" * 55

        resp = _change_password(client, auth_headers, registered_user["password"], long_pwd)
        assert resp.json()["code"] == "200", resp.text

        resp = _login(client, registered_user["username"], long_pwd)
        assert resp.json()["code"] == "200", f"51-64 位密码被登录接口拒绝: {resp.text}"

    def test_64_char_password_admin_reset_then_login(
        self, client: TestClient, admin_headers: dict, session_factory, registered_user: dict
    ):
        """管理员重置 64 位密码（密码管理器的常见长度）→ 用户能登录。"""
        pwd = "Aa1!" + "z" * 60  # 恰好 64 位

        with session_factory() as db:
            from app.models import User

            target_id = db.query(User).filter(User.username == registered_user["username"]).one().id

        resp = client.post(
            f"/api/user/admin/{target_id}/password",
            headers=admin_headers,
            json={"newPassword": pwd},
        )
        assert resp.json()["code"] == "200", resp.text

        resp = _login(client, registered_user["username"], pwd)
        assert resp.json()["code"] == "200"


class TestPasswordWhitespaceConsistency:
    def test_new_password_stripped_before_storing(
        self, client: TestClient, auth_headers: dict, registered_user: dict
    ):
        """改密时粘贴的密码带首尾空格 → 存 strip 后的哈希，登录（输入被 strip）能对上。"""
        resp = _change_password(
            client, auth_headers, registered_user["password"], "  plain123  "
        )
        assert resp.json()["code"] == "200", resp.text

        resp = _login(client, registered_user["username"], "plain123")
        assert resp.json()["code"] == "200", "登录会 strip 输入，存储侧也必须是 strip 后的哈希"

    def test_all_whitespace_password_rejected(
        self, client: TestClient, auth_headers: dict, registered_user: dict
    ):
        """"      "（6 个空格）能通过 schema 的 min_length=6，服务层必须拦住。"""
        resp = _change_password(client, auth_headers, registered_user["password"], "      ")
        body = resp.json()
        assert body["code"] != "200"
        assert "空白" in body["msg"]

    def test_register_all_whitespace_password_rejected(self, client: TestClient):
        """注册同理：6 个空格不是合法密码。"""
        resp = client.post(
            "/api/user/add",
            json={
                "username": "bob_whitespace",
                "email": "bob@example.com",
                "password": "      ",
                "confirmPassword": "      ",
            },
        )
        assert resp.json()["code"] != "200"

    def test_admin_reset_all_whitespace_rejected(
        self, client: TestClient, admin_headers: dict, session_factory, registered_user: dict
    ):
        """管理员重置成全空白必须被服务层拦下（目标是真实存在的用户，
        才能走到 _validated_password，而不是先被 6002 挡掉）。"""
        with session_factory() as db:
            from app.models import User

            target_id = db.query(User).filter(User.username == registered_user["username"]).one().id

        resp = client.post(
            f"/api/user/admin/{target_id}/password",
            headers=admin_headers,
            json={"newPassword": "      "},
        )
        body = resp.json()
        assert body["code"] != "200"
        assert "空白" in body["msg"]
