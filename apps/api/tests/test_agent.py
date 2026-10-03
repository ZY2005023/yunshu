"""意图路由测试。

最要紧的两条：
1. **危机优先不可动摇** —— 文本里同时含危机词和其他特征时，必须走 CRISIS
2. **level 1 不劫持路由** —— 「推荐几本关于焦虑的书」是资源请求，不是危机
"""

from __future__ import annotations

import pytest

from app.core.agent import (
    AGENT_LABELS,
    CRISIS_ROUTING_LEVEL,
    AgentType,
    all_agents,
    route,
)


class TestCrisisRouting:
    @pytest.mark.parametrize(
        "text",
        ["我不想活了", "想死", "已经写好遗书", "觉得活不下去", "我很绝望，撑不住了"],
    )
    def test_crisis_texts(self, text: str):
        assert route(text).agent == AgentType.CRISIS

    def test_crisis_confidence_is_max(self):
        assert route("我想自杀").confidence == 1.0

    def test_crisis_beats_other_features(self):
        """★ 文本里既有危机词又有测评/资源特征时，危机必须赢。"""
        d = route("我想自杀，能推荐几本书吗，或者怎么做测评")
        assert d.agent == AgentType.CRISIS

    def test_crisis_beats_resource_request(self):
        d = route("有没有关于自杀干预的资料推荐")
        assert d.agent == AgentType.CRISIS, "含危机词时不能因为'推荐'走资源"

    def test_crisis_reason_mentions_level(self):
        d = route("我想自杀")
        assert "level" in d.reason

    def test_matched_terms_populated(self):
        d = route("我想自杀")
        assert d.matched, "危机路由应带上命中的关键词，便于排查"


class TestAttentionLevelDoesNotHijack:
    """★ level 1 是「关注级」，不该劫持路由 —— 这是实测发现的 bug。"""

    def test_anxiety_book_request_is_resource(self):
        """曾经被判成 CRISIS，因为"焦虑"命中了 level 1。"""
        d = route("推荐几本关于焦虑的书")
        assert d.agent == AgentType.RESOURCE

    def test_insomnia_question_is_info(self):
        d = route("我最近失眠，该怎么办")
        assert d.agent != AgentType.CRISIS

    def test_routing_threshold_is_two(self):
        assert CRISIS_ROUTING_LEVEL == 2, "路由阈值改了会连带影响误判率"

    def test_warning_level_still_routes_to_crisis(self):
        """level 2（预警）必须仍然走危机。"""
        d = route("我觉得撑不下去了")
        assert d.agent == AgentType.CRISIS


class TestAssessmentRouting:
    @pytest.mark.parametrize(
        "text",
        [
            "我想做个心理测评",
            "有没有抑郁量表",
            "PHQ-9 是什么",
            "我是不是抑郁了",
            "想测一测自己的焦虑程度",
        ],
    )
    def test_assessment_texts(self, text: str):
        assert route(text).agent == AgentType.ASSESSMENT

    def test_assessment_multi_hit_raises_confidence(self):
        d = route("我想做心理测评，有没有量表")
        assert d.confidence >= 0.85


class TestReferralRouting:
    @pytest.mark.parametrize(
        "text",
        [
            "怎么预约心理咨询",
            "学校心理健康中心在哪",
            "我想找个咨询师聊聊",
            "不知道该找谁帮忙",
        ],
    )
    def test_referral_texts(self, text: str):
        assert route(text).agent == AgentType.REFERRAL


class TestResourceRouting:
    @pytest.mark.parametrize(
        "text",
        ["推荐几本关于焦虑的书", "有没有自助资料", "想看一些放松练习的教程"],
    )
    def test_resource_texts(self, text: str):
        assert route(text).agent == AgentType.RESOURCE


class TestDefaultRouting:
    @pytest.mark.parametrize(
        "text",
        ["压力大怎么办", "今天天气不错", "你好", "最近有点累"],
    )
    def test_falls_back_to_info(self, text: str):
        assert route(text).agent == AgentType.INFO

    def test_empty_input(self):
        d = route("")
        assert d.agent == AgentType.INFO
        assert d.confidence == 0.4

    def test_none_input(self):
        assert route(None).agent == AgentType.INFO


class TestDecisionPayload:
    def test_label_lookup(self):
        assert route("我想自杀").label == "危机干预"
        assert route("今天天气不错").label == "知识解答"

    def test_prompt_clause_for_non_crisis(self):
        clause = route("推荐几本书").prompt_clause()
        assert "资源推荐" in clause

    def test_crisis_prompt_clause_is_empty_here(self):
        """危机的要求不在路由层 —— 它在 crisis.CRISIS_PROMPT_CLAUSE，
        由 ai._system_prompt() 恒定拼上，保证任何模式下都生效。"""
        assert route("我想自杀").prompt_clause() == ""

    def test_as_payload_shape(self):
        payload = route("我想做个测评").as_payload()
        assert set(payload.keys()) == {"agent", "label", "confidence"}
        assert payload["agent"] == "ASSESSMENT"

    def test_decision_is_frozen(self):
        d = route("今天天气不错")
        with pytest.raises(Exception):
            d.confidence = 0.1  # type: ignore[misc]


class TestAgentCatalogue:
    def test_five_agents(self):
        assert len(all_agents()) == 5

    def test_all_types_covered(self):
        listed = {a["agent"] for a in all_agents()}
        assert listed == {a.value for a in AgentType}

    def test_labels_present(self):
        for a in all_agents():
            assert a["label"]
            assert a["agent"] in AGENT_LABELS
