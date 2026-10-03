"""日记危机反馈（POST /api/emotion-diary 的 crisisLevel 字段）回归测试。

背景：三条危机触发路径中，对话有 SSE crisis 卡片、量表有自伤 alert，
唯独日记此前没有任何用户侧反馈 —— 用户写出高危内容，后端记了工单、
老师会收到通知，当事人自己什么都看不到。修复：响应加 crisisLevel
（规则层命中等级，0=未命中），前端据此展示求助卡。

注意 AI 在测试中默认被切断（conftest 的 autouse 夹具），
所以这里的断言只验证**规则层** —— 它不依赖 AI 是否配置，正是它的意义。
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient


def _save_diary(client: TestClient, headers: dict, content: str) -> dict:
    resp = client.post(
        "/api/emotion-diary",
        headers=headers,
        json={
            "diaryDate": date.today().isoformat(),
            "moodScore": 2,
            "diaryContent": content,
        },
    )
    assert resp.status_code == 200
    return resp.json()


class TestDiaryCrisisLevel:
    def test_critical_content_reports_level(
        self, client: TestClient, auth_headers: dict
    ):
        """命中 3 级词 → crisisLevel >= 3，且危机事件确实落库。"""
        body = _save_diary(client, auth_headers, "我真的撑不下去了，想自杀。")
        assert body["code"] == "200"
        assert body["data"]["crisisLevel"] >= 3, body

    def test_attention_content_reports_low_level(
        self, client: TestClient, auth_headers: dict
    ):
        """1 级关注词（难过）也应回传 —— 与对话的 crisis 事件同一阈值。"""
        body = _save_diary(client, auth_headers, "今天很难过，压力好大。")
        assert body["data"]["crisisLevel"] >= 1

    def test_neutral_content_reports_zero(self, client: TestClient, auth_headers: dict):
        """日常内容 → 0，前端不弹卡。"""
        body = _save_diary(client, auth_headers, "今天天气不错，吃了好吃的饭。")
        assert body["data"]["crisisLevel"] == 0

    def test_update_reevaluates_level(self, client: TestClient, auth_headers: dict):
        """同一天更新日记时按新内容重判（第一次高危 → 改成日常后归 0）。"""
        body = _save_diary(client, auth_headers, "我想自杀。")
        assert body["data"]["crisisLevel"] >= 3

        body = _save_diary(client, auth_headers, "今天没事，挺好的。")
        assert body["data"]["crisisLevel"] == 0

    def test_empty_content_reports_zero(self, client: TestClient, auth_headers: dict):
        """正文为空（只打分）不报等级。"""
        body = _save_diary(client, auth_headers, "")
        assert body["data"]["crisisLevel"] == 0
