"""数据看板测试。

除了接口形状，重点钉住两个容易出错的点：
1. **Java 的 Math.round 与 Python 的 round 行为不同**（银行家舍入）
2. 空数据时也必须返回完整的 7 天序列和 7×10 网格（前端图表不能因为月份第一天空而崩）
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.services.analytics import round_half_up, round1


class TestJavaRound:
    """对齐 Java `Math.round` = floor(x + 0.5)。"""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (2.5, 3),   # Python 内建 round(2.5) 会得到 2 —— 必须区分
            (3.5, 4),   # Python 内建 round(3.5) 会得到 4，巧合一致
            (1.5, 2),
            (0.5, 1),
            (-0.5, 0),
            (2.4, 2),
            (2.6, 3),
        ],
    )
    def test_matches_java_semantics(self, value: float, expected: int):
        assert round_half_up(value) == expected

    def test_python_builtin_would_differ(self):
        """演示差异本身，防止后人"顺手"换成内建 round。"""
        assert round(2.5) == 2
        assert round_half_up(2.5) == 3

    def test_round1(self):
        assert round1(7.25) == 7.3
        assert round1(7.24) == 7.2
        assert round1(0.0) == 0.0


class TestOverview:
    def test_requires_admin(self, client: TestClient, auth_headers: dict):
        resp = client.get("/api/data-analytics/overview", headers=auth_headers)
        assert resp.status_code == 400
        assert resp.json()["code"] == "A0300"

    def test_requires_login(self, client: TestClient):
        resp = client.get("/api/data-analytics/overview")
        assert resp.status_code == 401

    def test_empty_database_shape(self, client: TestClient, admin_headers: dict):
        body = client.get("/api/data-analytics/overview", headers=admin_headers).json()
        assert body["code"] == "200"
        data = body["data"]

        assert set(data.keys()) == {
            "systemOverview",
            "emotionHeatmap",
            "consultationStats",
            "dailyTrend",
            "trendData",
            "activityData",
        }
        overview = data["systemOverview"]
        assert overview["totalUsers"] == 1  # 只有 admin 自己
        assert overview["totalDiaries"] == 0
        assert overview["avgMoodScore"] == 0.0

        # 空库也要有完整的 7 天序列
        assert len(data["dailyTrend"]) == 7
        assert len(data["trendData"]) == 7
        assert len(data["activityData"]) == 7

        # 热力图固定 7 行 × 10 列
        grid = data["emotionHeatmap"]["gridData"]
        assert len(grid) == 7
        assert all(len(row) == 10 for row in grid)
        assert grid[0][0] == {
            "x": 0,
            "y": 0,
            "value": 0,
            "avgMoodScore": 0,
            "dominantEmotion": "平静",
        }

    def test_counts_and_averages(self, client: TestClient, admin_headers: dict, auth_headers: dict):
        # 写两条日记：评分 6 和 8，平均 7.0
        today = date.today()
        for offset, score in ((0, 6), (1, 8)):
            client.post(
                "/api/emotion-diary",
                headers=auth_headers,
                json={
                    "diaryDate": (today - timedelta(days=offset)).isoformat(),
                    "moodScore": score,
                    "dominantEmotion": "平静",
                },
            )

        data = client.get("/api/data-analytics/overview", headers=admin_headers).json()["data"]
        overview = data["systemOverview"]
        assert overview["totalDiaries"] == 2
        assert overview["avgMoodScore"] == 7.0
        assert overview["todayNewDiaries"] == 2

        # 今日那天的趋势里应该有 2 条记录
        today_row = [r for r in data["trendData"] if r["date"] == today.isoformat()][0]
        assert today_row["recordCount"] == 2
        assert today_row["avgMoodScore"] == 7.0

    def test_heatmap_cell_placement(self, client: TestClient, admin_headers: dict, auth_headers: dict):
        """热力图按「创建日星期 × 评分」落格。"""
        today = date.today()
        client.post(
            "/api/emotion-diary",
            headers=auth_headers,
            json={"diaryDate": today.isoformat(), "moodScore": 9, "dominantEmotion": "愉快"},
        )

        grid = client.get("/api/data-analytics/overview", headers=admin_headers).json()["data"][
            "emotionHeatmap"
        ]["gridData"]

        y = today.weekday()  # 0 = 周一
        x = 8  # 评分 9 → 第 9 列（x = score - 1）
        assert grid[y][x]["value"] == 1
        assert grid[y][x]["avgMoodScore"] == 9.0
        assert grid[y][x]["dominantEmotion"] == "愉快"

    def test_session_and_message_stats(self, client: TestClient, admin_headers: dict):
        client.post(
            "/api/psychological-chat/session/start",
            headers=admin_headers,
            json={"initialMessage": "你好"},
        )
        data = client.get("/api/data-analytics/overview", headers=admin_headers).json()["data"]
        stats = data["consultationStats"]
        assert stats["totalSessions"] == 1
        # 只统计用户发出的消息（senderType == 1）
        assert stats["totalMessages"] == 1
        assert stats["avgMessagesPerSession"] == 1.0

    def test_activity_uses_max_of_two_sources(
        self, client: TestClient, admin_headers: dict
    ):
        """activeUsers 取「日记用户数」与「咨询用户数」的较大者（不是求和）。"""
        client.post(
            "/api/psychological-chat/session/start",
            headers=admin_headers,
            json={"initialMessage": "你好"},
        )
        data = client.get("/api/data-analytics/overview", headers=admin_headers).json()["data"]
        today_row = [
            r for r in data["activityData"] if r["date"] == date.today().isoformat()
        ][0]
        assert today_row["diaryUsers"] == 0
        assert today_row["consultationUsers"] == 1
        assert today_row["activeUsers"] == 1
