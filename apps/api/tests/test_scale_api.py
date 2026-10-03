"""量表接口端到端测试。

重点验证三件事：
1. 题目由后端统一下发（前端不内置）
2. 计分落库后，历史 / 趋势能正确取回
3. ★ PHQ-9 第 9 题 > 0 会补记危机工单（source = SCALE）
"""

from __future__ import annotations

from fastapi.testclient import TestClient

PHQ9_SAFE = [1, 1, 1, 1, 1, 1, 1, 1, 0]      # 总分 8 → 轻度，第 9 题 0
PHQ9_RISK = [0, 0, 0, 0, 0, 0, 0, 0, 3]      # 总分 3 → 极轻微，但第 9 题 3
GAD7_MILD = [1, 1, 1, 1, 1, 0, 0]            # 总分 5 → 轻度


class TestQuestions:
    def test_requires_login(self, client: TestClient):
        resp = client.get("/api/scale/questions")
        assert resp.status_code == 401

    def test_phq9_shape(self, client: TestClient, auth_headers: dict):
        body = client.get("/api/scale/questions?code=PHQ9", headers=auth_headers).json()
        data = body["data"]
        assert data["code"] == "PHQ9"
        assert len(data["questions"]) == 9
        assert data["options"] == ["完全不会", "好几天", "一半以上的天数", "几乎每天"]
        assert "12356" in data["disclaimer"]

    def test_gad7_shape(self, client: TestClient, auth_headers: dict):
        data = client.get("/api/scale/questions?code=GAD7", headers=auth_headers).json()["data"]
        assert len(data["questions"]) == 7

    def test_default_is_phq9(self, client: TestClient, auth_headers: dict):
        data = client.get("/api/scale/questions", headers=auth_headers).json()["data"]
        assert data["code"] == "PHQ9"

    def test_unknown_scale_is_business_error(self, client: TestClient, auth_headers: dict):
        body = client.get("/api/scale/questions?code=BDI", headers=auth_headers).json()
        assert body["code"] == "6000"
        assert "不支持的量表" in body["msg"]


class TestSubmit:
    def test_phq9_scoring(self, client: TestClient, auth_headers: dict):
        body = client.post(
            "/api/scale/submit", headers=auth_headers,
            json={"scaleCode": "PHQ9", "answers": PHQ9_SAFE},
        ).json()
        data = body["data"]
        assert data["total"] == 8
        assert data["level"] == "轻度"
        assert data["maxTotal"] == 27
        assert data["selfHarmRisk"] is False
        assert data["createdAt"] is not None

    def test_gad7_scoring(self, client: TestClient, auth_headers: dict):
        data = client.post(
            "/api/scale/submit", headers=auth_headers,
            json={"scaleCode": "GAD7", "answers": GAD7_MILD},
        ).json()["data"]
        assert data["total"] == 5
        assert data["level"] == "轻度"
        assert data["maxTotal"] == 21

    def test_wrong_answer_count_rejected(self, client: TestClient, auth_headers: dict):
        body = client.post(
            "/api/scale/submit", headers=auth_headers,
            json={"scaleCode": "PHQ9", "answers": [1, 2, 3]},
        ).json()
        assert body["code"] == "6000"
        assert "需要 9 个答案" in body["msg"]

    def test_out_of_range_answer_rejected(self, client: TestClient, auth_headers: dict):
        body = client.post(
            "/api/scale/submit", headers=auth_headers,
            json={"scaleCode": "PHQ9", "answers": [9] + [0] * 8},
        ).json()
        assert "必须在 0-3 之间" in body["msg"]

    def test_requires_login(self, client: TestClient):
        resp = client.post("/api/scale/submit", json={"scaleCode": "PHQ9", "answers": PHQ9_SAFE})
        assert resp.status_code == 401


class TestSelfHarmCrisisLink:
    """★ 这是量表模块最重要的行为。"""

    def test_ninth_question_creates_crisis_ticket(
        self, client: TestClient, auth_headers: dict, admin_headers: dict
    ):
        client.post(
            "/api/scale/submit", headers=auth_headers,
            json={"scaleCode": "PHQ9", "answers": PHQ9_RISK},
        )

        page = client.get("/api/admin/crisis/page", headers=admin_headers).json()
        assert page["data"]["total"] == 1
        event = page["data"]["records"][0]
        assert event["source"] == "SCALE"
        assert event["triggerType"] == "SCALE"
        assert event["level"] == 3          # 第 9 题 3 分 → 危机
        assert "PHQ9-Q9" in event["matchedTerms"]

    def test_score_one_on_ninth_is_warning_level(
        self, client: TestClient, auth_headers: dict, admin_headers: dict
    ):
        """第 9 题 1 分 → level 2（预警），不是 3。"""
        client.post(
            "/api/scale/submit", headers=auth_headers,
            json={"scaleCode": "PHQ9", "answers": [0] * 8 + [1]},
        )
        event = client.get("/api/admin/crisis/page", headers=admin_headers).json()["data"]["records"][0]
        assert event["level"] == 2

    def test_high_total_without_ninth_creates_no_ticket(
        self, client: TestClient, auth_headers: dict, admin_headers: dict
    ):
        """总分 24（重度）但第 9 题 0 分 —— 不产生自伤工单。

        不是说此人无风险（分级仍是重度），只是该量表的自伤项未得分。
        """
        client.post(
            "/api/scale/submit", headers=auth_headers,
            json={"scaleCode": "PHQ9", "answers": [3] * 8 + [0]},
        )
        page = client.get("/api/admin/crisis/page", headers=admin_headers).json()
        assert page["data"]["total"] == 0

    def test_result_still_flags_risk_to_user(
        self, client: TestClient, auth_headers: dict
    ):
        data = client.post(
            "/api/scale/submit", headers=auth_headers,
            json={"scaleCode": "PHQ9", "answers": PHQ9_RISK},
        ).json()["data"]
        assert data["selfHarmRisk"] is True
        assert data["selfHarmScore"] == 3
        assert "12356" in data["disclaimer"]


class TestHistoryAndTrend:
    def test_history_is_descending(self, client: TestClient, auth_headers: dict):
        for answers in ([0] * 8 + [0], [1] * 8 + [0], [2] * 8 + [0]):
            client.post("/api/scale/submit", headers=auth_headers,
                        json={"scaleCode": "PHQ9", "answers": answers})

        rows = client.get("/api/scale/my", headers=auth_headers).json()["data"]
        assert len(rows) == 3
        # 最近提交的在前
        assert rows[0]["totalScore"] == 16

    def test_history_filter_by_code(self, client: TestClient, auth_headers: dict):
        client.post("/api/scale/submit", headers=auth_headers,
                    json={"scaleCode": "PHQ9", "answers": [0] * 9})
        client.post("/api/scale/submit", headers=auth_headers,
                    json={"scaleCode": "GAD7", "answers": [0] * 7})

        rows = client.get("/api/scale/my?code=GAD7", headers=auth_headers).json()["data"]
        assert len(rows) == 1
        assert rows[0]["scaleCode"] == "GAD7"

    def test_latest(self, client: TestClient, auth_headers: dict):
        client.post("/api/scale/submit", headers=auth_headers,
                    json={"scaleCode": "PHQ9", "answers": [1] * 8 + [0]})
        client.post("/api/scale/submit", headers=auth_headers,
                    json={"scaleCode": "PHQ9", "answers": [3] * 8 + [0]})

        data = client.get("/api/scale/my/latest?code=PHQ9", headers=auth_headers).json()["data"]
        assert data["total"] == 24

    def test_latest_when_never_taken(self, client: TestClient, auth_headers: dict):
        body = client.get("/api/scale/my/latest?code=PHQ9", headers=auth_headers).json()
        assert body["code"] == "200"
        assert body["data"] is None

    def test_trend_is_ascending(self, client: TestClient, auth_headers: dict):
        for answers in ([0] * 8 + [0], [2] * 8 + [0]):
            client.post("/api/scale/submit", headers=auth_headers,
                        json={"scaleCode": "PHQ9", "answers": answers})

        points = client.get("/api/scale/trend", headers=auth_headers).json()["data"]
        assert len(points) == 2
        assert points[0]["totalScore"] == 0
        assert points[1]["totalScore"] == 16
        assert len(points[0]["date"]) == 10  # YYYY-MM-DD


class TestIsolation:
    def test_user_cannot_see_others_records(
        self, client: TestClient, auth_headers: dict, db_engine
    ):
        from sqlalchemy.orm import Session, sessionmaker

        client.post("/api/scale/submit", headers=auth_headers,
                    json={"scaleCode": "PHQ9", "answers": [3] * 8 + [0]})

        # 另注册一个用户
        client.post("/api/user/add", json={
            "username": "scale_other", "email": "so@example.com",
            "password": "secret123", "confirmPassword": "secret123"})
        token = client.post("/api/user/login",
                            json={"username": "scale_other", "password": "secret123"}
                            ).json()["data"]["token"]

        rows = client.get("/api/scale/my",
                          headers={"Authorization": f"Bearer {token}"}).json()["data"]
        assert rows == []

        Session_ = sessionmaker(bind=db_engine, class_=Session, expire_on_commit=False)
        _ = Session_  # 保持与 conftest 的用法一致，避免未使用告警


class TestAdminPage:
    def test_requires_admin(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/scale/admin/page", headers=auth_headers)
        assert resp.status_code == 400
        assert resp.json()["code"] == "A0300"

    def test_admin_sees_records_with_username(
        self, client: TestClient, admin_headers: dict, auth_headers: dict
    ):
        client.post("/api/scale/submit", headers=auth_headers,
                    json={"scaleCode": "PHQ9", "answers": PHQ9_RISK})

        body = client.get("/api/scale/admin/page", headers=admin_headers).json()
        assert body["data"]["total"] == 1
        row = body["data"]["records"][0]
        assert row["username"] == "alice"      # 带用户名，方便跟进
        assert row["selfHarmRisk"] is True
        assert row["totalScore"] == 3

    def test_only_self_harm_filter(
        self, client: TestClient, admin_headers: dict, auth_headers: dict
    ):
        client.post("/api/scale/submit", headers=auth_headers,
                    json={"scaleCode": "PHQ9", "answers": PHQ9_SAFE})     # 无自伤
        client.post("/api/scale/submit", headers=auth_headers,
                    json={"scaleCode": "PHQ9", "answers": PHQ9_RISK})     # 有自伤

        all_rows = client.get("/api/scale/admin/page", headers=admin_headers).json()["data"]
        assert all_rows["total"] == 2

        risky = client.get("/api/scale/admin/page?onlySelfHarm=true",
                           headers=admin_headers).json()["data"]
        assert risky["total"] == 1
        assert risky["records"][0]["selfHarmRisk"] is True

    def test_code_filter(self, client: TestClient, admin_headers: dict, auth_headers: dict):
        client.post("/api/scale/submit", headers=auth_headers,
                    json={"scaleCode": "PHQ9", "answers": [0] * 9})
        client.post("/api/scale/submit", headers=auth_headers,
                    json={"scaleCode": "GAD7", "answers": [0] * 7})

        body = client.get("/api/scale/admin/page?code=GAD7", headers=admin_headers).json()
        assert body["data"]["total"] == 1
        assert body["data"]["records"][0]["scaleCode"] == "GAD7"


class TestPaginationParams:
    """查询参数必须用 camelCase 的 alias 才能被 FastAPI 收到。

    这个坑很隐蔽：参数名写成 snake_case 时，前端传 currentPage 收不到，
    FastAPI 直接用默认值 1 —— **不报错，但分页永远停在第一页**。
    """

    def test_current_page_alias_works(
        self, client: TestClient, admin_headers: dict, auth_headers: dict
    ):
        for _ in range(3):
            client.post("/api/scale/submit", headers=auth_headers,
                        json={"scaleCode": "PHQ9", "answers": [0] * 9})

        page1 = client.get("/api/scale/admin/page?currentPage=1&size=2",
                           headers=admin_headers).json()["data"]
        page2 = client.get("/api/scale/admin/page?currentPage=2&size=2",
                           headers=admin_headers).json()["data"]

        assert page1["total"] == 3
        assert len(page1["records"]) == 2
        assert len(page2["records"]) == 1, "currentPage=2 必须真的取到第二页"
        ids1 = {r["id"] for r in page1["records"]}
        ids2 = {r["id"] for r in page2["records"]}
        assert not (ids1 & ids2), "两页之间不应有重复记录"
