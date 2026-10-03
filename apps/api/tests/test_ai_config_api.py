"""「API 管理」接口（/api/admin/ai-config）回归测试。

被测能力：运营期 AI 配置（base_url / model / api_key）页面上改、即时生效。
测试不依赖真实 AI 供应商 —— 连通性测试通过 monkeypatch `_ping` 模拟
成功 / 401 / 超时，验证的是**本层逻辑**：掩码、部分更新、生效链路、
错误翻译与权限边界。

⚠️ 这组用例必须与本地 MySQL 里 sys_config 的真实内容隔离 ——
conftest 的 client 夹具每次都会触发 lifespan 从库加载覆盖，
这里统一 monkeypatch 成 no-op，让断言只反映用例自己写入的状态。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import runtime_config
from app.services import ai_config as ai_config_service
from app.services import ai as ai_service


@pytest.fixture(autouse=True)
def _isolate_runtime_config(monkeypatch):
    """每个用例前清空运行时覆盖，并让 lifespan 的库加载变 no-op ——
    否则本地 MySQL 若已配好真实 Key，用例会被环境里的值污染。"""
    runtime_config.clear()
    monkeypatch.setattr(ai_config_service, "load_overrides_from_db", lambda db: 0)
    yield
    runtime_config.clear()


class TestPermission:
    def test_requires_admin(self, client: TestClient, auth_headers: dict):
        """普通用户 → HTTP 400 + A0300（对齐 @PreAuthorize 契约，不是 403）。"""
        resp = client.get("/api/admin/ai-config", headers=auth_headers)
        assert resp.status_code == 400
        assert resp.json()["code"] == "A0300"

    def test_anonymous_rejected(self, client: TestClient):
        resp = client.get("/api/admin/ai-config")
        assert resp.status_code == 401


class TestGetConfig:
    def test_key_never_returned_in_plaintext(self, client: TestClient, admin_headers: dict):
        """保存后再读 —— 响应里只能出现掩码，原文绝不能回显。"""
        secret = "sk-test-1234567890abcdef"
        resp = client.put(
            "/api/admin/ai-config",
            headers=admin_headers,
            json={"baseUrl": "https://api.example.com/v1", "model": "test-model", "apiKey": secret},
        )
        assert resp.json()["code"] == "200"

        resp = client.get("/api/admin/ai-config", headers=admin_headers)
        data = resp.json()["data"]
        assert data["apiKeySet"] is True
        assert data["configured"] is True
        assert data["apiKeyMasked"] == "****cdef"
        assert secret not in resp.text, "API Key 原文出现在了响应里"
        assert data["sources"]["ai.api_key"] == "database"

    def test_unconfigured_state(self, client: TestClient, admin_headers: dict):
        resp = client.get("/api/admin/ai-config", headers=admin_headers)
        data = resp.json()["data"]
        assert data["apiKeySet"] is False
        assert data["configured"] is False
        assert data["apiKeyMasked"] == ""


class TestUpdateConfig:
    def test_partial_update_keeps_key(
        self, client: TestClient, admin_headers: dict
    ):
        """改模型名不必重新粘贴密钥：apiKey 留空 = 保持原值。"""
        client.put(
            "/api/admin/ai-config",
            headers=admin_headers,
            json={"baseUrl": "https://api.example.com/v1", "model": "m1", "apiKey": "sk-aaaaaaaa-bbbbbbbb"},
        )
        resp = client.put(
            "/api/admin/ai-config",
            headers=admin_headers,
            json={"model": "m2", "apiKey": ""},
        )
        data = resp.json()["data"]
        assert data["model"] == "m2"
        assert data["apiKeySet"] is True, "留空 Key 后被清掉了"
        assert data["baseUrl"] == "https://api.example.com/v1"

    def test_takes_effect_immediately(self, client: TestClient, admin_headers: dict):
        """保存后 settings.ai 立即读到新值 —— 这是「不重启生效」的核心链路。"""
        assert ai_service.is_configured() is False
        client.put(
            "/api/admin/ai-config",
            headers=admin_headers,
            json={"apiKey": "sk-live-key-123456", "model": "deepseek-chat"},
        )
        assert ai_service.is_configured() is True
        assert ai_service.settings.ai.api_key == "sk-live-key-123456"
        assert ai_service.settings.ai.model == "deepseek-chat"

    def test_invalid_base_url_rejected(self, client: TestClient, admin_headers: dict):
        resp = client.put(
            "/api/admin/ai-config",
            headers=admin_headers,
            json={"baseUrl": "ftp://not-http"},
        )
        assert resp.json()["code"] == "6000"
        assert "http" in resp.json()["msg"]

    def test_short_key_rejected(self, client: TestClient, admin_headers: dict):
        resp = client.put(
            "/api/admin/ai-config",
            headers=admin_headers,
            json={"apiKey": "abc"},
        )
        assert resp.json()["code"] == "6000"


class TestConnection:
    def _configure(self, client: TestClient, admin_headers: dict) -> None:
        resp = client.put(
            "/api/admin/ai-config",
            headers=admin_headers,
            json={"apiKey": "sk-test-ping-123456", "model": "test-model"},
        )
        assert resp.json()["code"] == "200"

    def test_reports_unconfigured(self, client: TestClient, admin_headers: dict):
        resp = client.post("/api/admin/ai-config/test", headers=admin_headers)
        data = resp.json()["data"]
        assert data["ok"] is False
        assert "未配置" in data["error"]

    def test_success_path(self, client: TestClient, admin_headers: dict, monkeypatch):
        self._configure(client, admin_headers)

        async def fake_ping(cfg):
            return "连接正常"

        monkeypatch.setattr(ai_config_service, "_ping", fake_ping)
        resp = client.post("/api/admin/ai-config/test", headers=admin_headers)
        data = resp.json()["data"]
        assert data["ok"] is True
        assert data["reply"] == "连接正常"
        assert data["latencyMs"] >= 0

    def test_auth_error_translated(self, client: TestClient, admin_headers: dict, monkeypatch):
        self._configure(client, admin_headers)

        async def bad_ping(cfg):
            raise RuntimeError("Error code: 401 - {'errcode': 'invalid_api_key'}")

        monkeypatch.setattr(ai_config_service, "_ping", bad_ping)
        resp = client.post("/api/admin/ai-config/test", headers=admin_headers)
        data = resp.json()["data"]
        assert data["ok"] is False
        assert "认证失败" in data["error"], "401 应翻译成可读文案"
