"""知识库 / 情绪日记 / 危机工单 / 咨询会话 / 文件上传 的端到端测试。

重点验证三件事：
1. 出参字段名与类型（camelCase、code 是字符串）
2. 权限边界（普通用户不能碰 ADMIN 接口，也不能读别人的会话）
3. 原版那些"看起来不一致但必须保留"的行为
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.models import KnowledgeCategory
from app.services import ai as ai_service


def _insert_category(db_engine, name: str = "情绪管理", sort_order: int = 1) -> int:
    from sqlalchemy.orm import Session, sessionmaker

    Session_ = sessionmaker(bind=db_engine, class_=Session, expire_on_commit=False)
    with Session_() as db:
        c = KnowledgeCategory(category_name=name, sort_order=sort_order, status=1)
        db.add(c)
        db.commit()
        db.refresh(c)
        return c.id


# ===========================================================================
# 知识库
# ===========================================================================


class TestKnowledge:
    def test_admin_can_create_article(self, client: TestClient, admin_headers: dict, db_engine):
        cat_id = _insert_category(db_engine)
        body = client.post(
            "/api/knowledge/article",
            headers=admin_headers,
            json={"categoryId": cat_id, "title": "如何应对焦虑", "content": "<p>正文</p>"},
        ).json()
        assert body["code"] == "200"
        assert body["data"]["title"] == "如何应对焦虑"
        assert body["data"]["statusText"] == "已发布"
        assert body["data"]["readCount"] == 0
        # 主键是 UUID 字符串，不是整数
        assert isinstance(body["data"]["id"], str)

    def test_normal_user_cannot_create_article(self, client: TestClient, auth_headers: dict, db_engine):
        cat_id = _insert_category(db_engine)
        resp = client.post(
            "/api/knowledge/article",
            headers=auth_headers,
            json={"categoryId": cat_id, "title": "x", "content": "y"},
        )
        # ⚠️ @PreAuthorize 拒绝走 ResponseUtil default 分支 → HTTP 400（不是 403）
        assert resp.status_code == 400
        assert resp.json()["code"] == "A0300"

    def test_article_list_requires_login(self, client: TestClient):
        resp = client.get("/api/knowledge/article")
        assert resp.status_code == 401
        assert resp.json()["code"] == "A0301"

    def test_article_page_accessible_to_normal_user(
        self, client: TestClient, auth_headers: dict
    ):
        """原版这个接口没有 ADMIN 注解 —— 任何登录用户都能访问，保持原样。"""
        body = client.get("/api/knowledge/article/page", headers=auth_headers).json()
        assert body["code"] == "200"
        assert body["data"]["total"] == 0

    def test_article_detail_increments_read_count(
        self, client: TestClient, admin_headers: dict, db_engine
    ):
        """★ 访问详情即阅读数 +1，这是原版的副作用。"""
        cat_id = _insert_category(db_engine)
        article_id = client.post(
            "/api/knowledge/article",
            headers=admin_headers,
            json={"categoryId": cat_id, "title": "t", "content": "c"},
        ).json()["data"]["id"]

        first = client.get(f"/api/knowledge/article/{article_id}", headers=admin_headers).json()
        assert first["data"]["readCount"] == 1
        second = client.get(f"/api/knowledge/article/{article_id}", headers=admin_headers).json()
        assert second["data"]["readCount"] == 2

    def test_missing_article_returns_200_with_null(
        self, client: TestClient, auth_headers: dict
    ):
        """文章不存在时是 code=200 + data=null，**不是 404**。"""
        body = client.get("/api/knowledge/article/not-exist", headers=auth_headers).json()
        assert body["code"] == "200"
        assert body["data"] is None

    def test_content_is_sanitized_on_write(
        self, client: TestClient, admin_headers: dict, db_engine
    ):
        """入库前必须过 HTML 白名单清洗（纵深防御）。"""
        cat_id = _insert_category(db_engine)
        body = client.post(
            "/api/knowledge/article",
            headers=admin_headers,
            json={
                "categoryId": cat_id,
                "title": "xss",
                "content": '<p onclick="alert(1)">ok</p><script>alert(2)</script>',
            },
        ).json()
        content = body["data"]["content"]
        assert "<script" not in content.lower()
        assert "onclick" not in content.lower()
        assert "ok" in content

    def test_status_update(self, client: TestClient, admin_headers: dict, db_engine):
        cat_id = _insert_category(db_engine)
        article_id = client.post(
            "/api/knowledge/article",
            headers=admin_headers,
            json={"categoryId": cat_id, "title": "t", "content": "c"},
        ).json()["data"]["id"]

        body = client.put(
            f"/api/knowledge/article/{article_id}/status",
            headers=admin_headers,
            json={"status": 0},
        ).json()
        assert body["code"] == "200"

        detail = client.get(f"/api/knowledge/article/{article_id}", headers=admin_headers).json()
        assert detail["data"]["statusText"] == "草稿"

    def test_category_tree(self, client: TestClient, auth_headers: dict, db_engine):
        _insert_category(db_engine, "情绪管理")
        body = client.get("/api/knowledge/category/tree", headers=auth_headers).json()
        assert body["code"] == "200"
        row = body["data"][0]
        assert row["categoryName"] == "情绪管理"
        assert row["statusText"] == "启用"  # 分类是"启用/禁用"，不是"已发布/草稿"
        assert row["articleCount"] == 0


# ===========================================================================
# 情绪日记
# ===========================================================================


class TestDiary:
    PAYLOAD = {
        "diaryDate": "2026-10-01",
        "moodScore": 7,
        "dominantEmotion": "平静",
        "diaryContent": "今天还行",
        "sleepQuality": 4,
        "stressLevel": 2,
    }

    def test_create_and_upsert_same_day(self, client: TestClient, auth_headers: dict):
        first = client.post("/api/emotion-diary", headers=auth_headers, json=self.PAYLOAD).json()
        assert first["code"] == "200"
        assert first["data"]["moodScore"] == 7

        # 同一天再提交应该是更新而不是新增
        second = client.post(
            "/api/emotion-diary", headers=auth_headers, json={**self.PAYLOAD, "moodScore": 3}
        ).json()
        assert second["data"]["id"] == first["data"]["id"]
        assert second["data"]["moodScore"] == 3

        my = client.get("/api/emotion-diary/my", headers=auth_headers).json()
        assert len(my["data"]) == 1

    def test_my_list_shape(self, client: TestClient, auth_headers: dict):
        client.post("/api/emotion-diary", headers=auth_headers, json=self.PAYLOAD)
        row = client.get("/api/emotion-diary/my", headers=auth_headers).json()["data"][0]
        assert row["diaryDate"] == "2026-10-01"
        assert "aiEmotionAnalysis" in row
        assert row["aiEmotionAnalysis"] is None

    def test_mood_score_bounds(self, client: TestClient, auth_headers: dict):
        body = client.post(
            "/api/emotion-diary", headers=auth_headers, json={**self.PAYLOAD, "moodScore": 99}
        ).json()
        assert body["code"] == "400"

    def test_crisis_detection_on_diary(self, client: TestClient, auth_headers: dict):
        """★ 日记正文命中危机规则时必须落一条工单 —— 不依赖 AI 是否可用。"""
        client.post(
            "/api/emotion-diary",
            headers=auth_headers,
            json={**self.PAYLOAD, "diaryContent": "我真的撑不下去了"},
        )
        # 日记接口本身正常返回，危机事件可以在管理端查到
        pending = client.get("/api/admin/crisis/pending/count", headers=auth_headers)
        assert pending.status_code == 400  # 普通用户被拒（A0300）

    def test_admin_page_requires_admin(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/emotion-diary/admin/page", headers=auth_headers)
        assert resp.status_code == 400
        assert resp.json()["code"] == "A0300"


class TestDiaryAiAnalysis:
    """日记保存后的 AI 分析链路（对应 Java 的 analyzeAndAttach + recordLlmRisk）。"""

    PAYLOAD = {
        "diaryDate": "2026-10-01",
        "moodScore": 4,
        "diaryContent": "今天有点累",
    }

    def _mock(self, monkeypatch, payload: dict):
        async def _fake(_diary):
            return json.dumps(payload, ensure_ascii=False)

        monkeypatch.setattr(ai_service, "analyze_emotion", _fake)

    def test_analysis_attached_to_diary(self, client: TestClient, auth_headers: dict, monkeypatch):
        self._mock(monkeypatch, {"primaryEmotion": "疲惫", "riskLevel": 1, "summary": "状态一般"})

        body = client.post("/api/emotion-diary", headers=auth_headers, json=self.PAYLOAD).json()
        assert body["code"] == "200"
        analysis = body["data"]["aiEmotionAnalysis"]
        assert analysis is not None
        assert "疲惫" in analysis

    def test_analysis_visible_in_my_list(self, client: TestClient, auth_headers: dict, monkeypatch):
        self._mock(monkeypatch, {"primaryEmotion": "平静", "riskLevel": 0, "summary": "还行"})

        client.post("/api/emotion-diary", headers=auth_headers, json=self.PAYLOAD)
        row = client.get("/api/emotion-diary/my", headers=auth_headers).json()["data"][0]
        # /my 返回的是**解析后的对象**，不是字符串
        assert isinstance(row["aiEmotionAnalysis"], dict)
        assert row["aiEmotionAnalysis"]["primaryEmotion"] == "平静"

    def test_llm_risk_creates_crisis_ticket(
        self, client: TestClient, auth_headers: dict, admin_headers: dict, monkeypatch
    ):
        """★ 模型层升级：riskLevel >= 2 时补记危机事件，triggerType 是 LLM。"""
        self._mock(
            monkeypatch,
            {"primaryEmotion": "绝望", "riskLevel": 3, "summary": "出现危机信号"},
        )

        client.post("/api/emotion-diary", headers=auth_headers, json=self.PAYLOAD)

        page = client.get("/api/admin/crisis/page", headers=admin_headers).json()
        assert page["data"]["total"] == 1
        event = page["data"]["records"][0]
        assert event["triggerType"] == "LLM"
        assert event["level"] == 3
        assert event["matchedTerms"] == "model-risk-level"

    def test_low_risk_creates_no_ticket(
        self, client: TestClient, auth_headers: dict, admin_headers: dict, monkeypatch
    ):
        self._mock(monkeypatch, {"primaryEmotion": "平静", "riskLevel": 1, "summary": "正常"})

        client.post("/api/emotion-diary", headers=auth_headers, json=self.PAYLOAD)
        page = client.get("/api/admin/crisis/page", headers=admin_headers).json()
        assert page["data"]["total"] == 0

    def test_ai_failure_does_not_break_save(
        self, client: TestClient, auth_headers: dict, monkeypatch
    ):
        """★ AI 挂了，日记本身必须照常保存成功。"""

        async def _boom(_diary):
            raise RuntimeError("AI 服务不可用")

        monkeypatch.setattr(ai_service, "analyze_emotion", _boom)

        body = client.post("/api/emotion-diary", headers=auth_headers, json=self.PAYLOAD).json()
        assert body["code"] == "200"
        assert body["data"]["moodScore"] == 4
        assert body["data"]["aiEmotionAnalysis"] is None

    def test_unconfigured_ai_skips_silently(self, client: TestClient, auth_headers: dict):
        """没配 AI_API_KEY 时（测试环境即如此）分析为 None，不应报错。"""
        body = client.post("/api/emotion-diary", headers=auth_headers, json=self.PAYLOAD).json()
        assert body["code"] == "200"
        assert body["data"]["aiEmotionAnalysis"] is None


# ===========================================================================
# 危机工单
# ===========================================================================


class TestCrisis:
    def test_resources_shape(self, client: TestClient, admin_headers: dict):
        body = client.get("/api/admin/crisis/resources", headers=admin_headers).json()
        data = body["data"]
        assert "12356" in "".join(data["helplines"])
        # helplines 是纯字符串数组，不是对象数组
        assert all(isinstance(h, str) for h in data["helplines"])
        assert "免责声明" in data["disclaimer"]

    def test_pending_count_starts_zero(self, client: TestClient, admin_headers: dict):
        body = client.get("/api/admin/crisis/pending/count", headers=admin_headers).json()
        assert body["data"] == 0

    def test_diary_crisis_creates_ticket_then_handle(
        self, client: TestClient, admin_headers: dict, auth_headers: dict
    ):
        # 普通用户写一条高危日记
        client.post(
            "/api/emotion-diary",
            headers=auth_headers,
            json={
                "diaryDate": "2026-10-01",
                "moodScore": 1,
                "diaryContent": "我想自杀",
            },
        )

        page = client.get("/api/admin/crisis/page", headers=admin_headers).json()
        assert page["data"]["total"] == 1
        event = page["data"]["records"][0]
        assert event["level"] == 3
        assert event["triggerType"] == "KEYWORD"
        assert event["status"] == "PENDING"
        assert event["source"] == "DIARY"
        assert "自杀" in event["matchedTerms"]

        pending = client.get("/api/admin/crisis/pending/count", headers=admin_headers).json()
        assert pending["data"] == 1

        # 处置：不传 status 默认 RESOLVED
        handled = client.post(
            f"/api/admin/crisis/{event['id']}/handle",
            headers=admin_headers,
            json={"handleNote": "已电话联系"},
        ).json()
        assert handled["code"] == "200"

        after = client.get("/api/admin/crisis/page", headers=admin_headers).json()
        assert after["data"]["records"][0]["status"] == "RESOLVED"

    def test_handle_twice_rejected(
        self, client: TestClient, admin_headers: dict, auth_headers: dict
    ):
        client.post(
            "/api/emotion-diary",
            headers=auth_headers,
            json={"diaryDate": "2026-10-01", "moodScore": 1, "diaryContent": "想死"},
        )
        event_id = client.get("/api/admin/crisis/page", headers=admin_headers).json()["data"]["records"][0]["id"]
        client.post(f"/api/admin/crisis/{event_id}/handle", headers=admin_headers, json={})
        again = client.post(f"/api/admin/crisis/{event_id}/handle", headers=admin_headers, json={}).json()
        assert again["msg"] == "该事件已处置，无需重复处理"

    def test_empty_content_no_ticket(self, client: TestClient, admin_headers: dict, auth_headers: dict):
        """普通内容不应产生工单（避免误报刷屏的底线）—— 注：规则层是宁可误报，
        但"今天天气不错"这种明确无信号的必须不命中。"""
        client.post(
            "/api/emotion-diary",
            headers=auth_headers,
            json={"diaryDate": "2026-10-01", "moodScore": 8, "diaryContent": "今天天气不错，出去走了走"},
        )
        page = client.get("/api/admin/crisis/page", headers=admin_headers).json()
        assert page["data"]["total"] == 0


# ===========================================================================
# 咨询会话（含越权防护）
# ===========================================================================


class TestConsultation:
    def test_start_session_shape(self, client: TestClient, auth_headers: dict):
        body = client.post(
            "/api/psychological-chat/session/start",
            headers=auth_headers,
            json={"initialMessage": "你好"},
        ).json()
        data = body["data"]
        assert data["sessionId"].startswith("session_")
        assert data["userHash"] == 1
        assert data["messageCount"] == 1
        assert data["status"] == "ACTIVE"
        assert data["expiryTime"] - data["startTime"] == 86_400_000

    def test_default_title_when_blank(self, client: TestClient, auth_headers: dict):
        client.post(
            "/api/psychological-chat/session/start",
            headers=auth_headers,
            json={"initialMessage": "你好"},
        )
        row = client.get("/api/psychological-chat/sessions", headers=auth_headers).json()["data"]["records"][0]
        # 2026-10-03：品牌名统一为「云舒」，与前端默认标题一致
        assert row["sessionTitle"].startswith("云舒AI助手 - ")

    def test_my_sessions_hides_user_info(self, client: TestClient, auth_headers: dict):
        """用户端不带 username/nickname。"""
        client.post(
            "/api/psychological-chat/session/start",
            headers=auth_headers,
            json={"initialMessage": "你好"},
        )
        row = client.get("/api/psychological-chat/sessions", headers=auth_headers).json()["data"]["records"][0]
        assert row["username"] is None
        assert row["nickname"] is None
        assert row["messageCount"] == 1

    def test_admin_sessions_includes_user_info(self, client: TestClient, admin_headers: dict):
        client.post(
            "/api/psychological-chat/session/start",
            headers=admin_headers,
            json={"initialMessage": "你好"},
        )
        row = client.get("/api/psychological-chat/admin/sessions", headers=admin_headers).json()["data"]["records"][0]
        assert row["username"] == "alice"

    def test_messages_list(self, client: TestClient, auth_headers: dict):
        sid = client.post(
            "/api/psychological-chat/session/start",
            headers=auth_headers,
            json={"initialMessage": "你好"},
        ).json()["data"]["sessionId"]

        body = client.get(
            f"/api/psychological-chat/sessions/{sid}/messages", headers=auth_headers
        ).json()
        assert body["data"]["sessionId"] == sid
        msg = body["data"]["messages"][0]
        assert msg["senderType"] == 1
        assert msg["senderTypeDesc"] == "用户"
        assert msg["content"] == "你好"

    def test_emotion_endpoint_uses_singular_path(self, client: TestClient, auth_headers: dict):
        """⚠️ 路径是单数 session（原版如此，别修正）。"""
        sid = client.post(
            "/api/psychological-chat/session/start",
            headers=auth_headers,
            json={"initialMessage": "你好"},
        ).json()["data"]["sessionId"]

        body = client.get(f"/api/psychological-chat/session/{sid}/emotion", headers=auth_headers).json()
        assert body["code"] == "200"
        assert body["data"]["emotionAnalysis"] is None

    def test_other_user_cannot_read_session(
        self, client: TestClient, auth_headers: dict, db_engine
    ):
        """★ 越权防护：换个 id 不能读别人的私密对话。"""
        sid = client.post(
            "/api/psychological-chat/session/start",
            headers=auth_headers,
            json={"initialMessage": "这是私密倾诉"},
        ).json()["data"]["sessionId"]

        # 另注册一个用户
        client.post(
            "/api/user/add",
            json={
                "username": "eve",
                "email": "eve@example.com",
                "password": "secret123",
                "confirmPassword": "secret123",
            },
        )
        eve_token = client.post(
            "/api/user/login", json={"username": "eve", "password": "secret123"}
        ).json()["data"]["token"]
        eve_headers = {"Authorization": f"Bearer {eve_token}"}

        resp = client.get(f"/api/psychological-chat/sessions/{sid}/messages", headers=eve_headers).json()
        assert resp["code"] == "A0300"
        assert resp["msg"] == "无权访问该会话"

    def test_delete_is_idempotent_for_invalid_id(self, client: TestClient, auth_headers: dict):
        """未落库的临时会话，删除视为成功。"""
        body = client.delete(
            "/api/psychological-chat/sessions/session_not-a-number", headers=auth_headers
        ).json()
        assert body["code"] == "200"

    def test_delete_removes_messages(self, client: TestClient, auth_headers: dict):
        sid = client.post(
            "/api/psychological-chat/session/start",
            headers=auth_headers,
            json={"initialMessage": "你好"},
        ).json()["data"]["sessionId"]

        assert client.delete(f"/api/psychological-chat/sessions/{sid}", headers=auth_headers).json()["code"] == "200"
        assert client.get("/api/psychological-chat/sessions", headers=auth_headers).json()["data"]["total"] == 0


# ===========================================================================
# 文件上传
# ===========================================================================


class TestFileUpload:
    def test_upload_png(self, client: TestClient, auth_headers: dict, tmp_path, monkeypatch):
        monkeypatch.setenv("FILE_UPLOAD_DIR", str(tmp_path))
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
        body = client.post(
            "/api/file/upload",
            headers=auth_headers,
            files={"file": ("a.png", png, "image/png")},
            data={"businessType": "avatar"},
        ).json()
        assert body["code"] == "200"
        data = body["data"]
        assert data["filePath"].startswith("/files/avatar/")
        assert data["url"] == data["filePath"]
        assert data["fileType"] == "IMG"
        assert data["fileSize"] == len(png)
        assert (tmp_path / "avatar").is_dir()

    def test_extension_not_in_whitelist(self, client: TestClient, auth_headers: dict, tmp_path, monkeypatch):
        monkeypatch.setenv("FILE_UPLOAD_DIR", str(tmp_path))
        body = client.post(
            "/api/file/upload",
            headers=auth_headers,
            files={"file": ("evil.svg", b"<svg onload=alert(1)>", "image/svg+xml")},
        ).json()
        assert body["code"] == "5005"

    def test_magic_number_mismatch(self, client: TestClient, auth_headers: dict, tmp_path, monkeypatch):
        """★ 改后缀的伪装文件必须被挡下。"""
        monkeypatch.setenv("FILE_UPLOAD_DIR", str(tmp_path))
        body = client.post(
            "/api/file/upload",
            headers=auth_headers,
            files={"file": ("fake.png", b"this is not a png at all", "image/png")},
        ).json()
        assert body["code"] == "5007"
        assert "不符" in body["msg"]

    def test_path_traversal_in_business_type(self, client: TestClient, auth_headers: dict, tmp_path, monkeypatch):
        """★ businessType 带穿越字符时归到 common，不能写出根目录。"""
        monkeypatch.setenv("FILE_UPLOAD_DIR", str(tmp_path))
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 50
        body = client.post(
            "/api/file/upload",
            headers=auth_headers,
            files={"file": ("a.png", png, "image/png")},
            data={"businessType": "../../etc"},
        ).json()
        assert body["code"] == "200"
        assert body["data"]["filePath"].startswith("/files/common/")

    def test_upload_requires_login(self, client: TestClient):
        resp = client.post("/api/file/upload", files={"file": ("a.png", b"\x89PNG", "image/png")})
        assert resp.status_code == 401
