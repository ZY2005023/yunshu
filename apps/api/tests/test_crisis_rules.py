"""危机检测规则测试 —— 迁移的"黄金样本"。

这些用例的作用是**证明 Python 版的分级行为与 Java 版一致**。
心理健康场景下漏判是安全事故，所以规则的每个分支都要有用例钉住。

设计取向：宁可误报不可漏报（"我不会自杀的"同样命中）。
"""

from __future__ import annotations

import pytest

from app.core.crisis import (
    LEVEL_ATTENTION,
    LEVEL_CRITICAL,
    LEVEL_NONE,
    LEVEL_WARNING,
    SNIPPET_MAX,
    TRIGGER_KEYWORD,
    detect,
    normalize,
    snippet,
)


class TestNoHit:
    def test_none_input(self):
        assert detect(None).level == LEVEL_NONE

    def test_blank_input(self):
        assert detect("   ").level == LEVEL_NONE

    def test_neutral_text(self):
        signal = detect("今天天气不错，出去走了走")
        assert signal.level == LEVEL_NONE
        assert not signal.is_crisis
        assert signal.trigger_type == "NONE"
        assert signal.matched_terms == []


class TestCritical:
    @pytest.mark.parametrize(
        "text",
        ["我想自杀", "活不下去了", "想死", "已经写好遗书", "打算跳楼", "割腕"],
    )
    def test_critical_terms_give_level_3(self, text: str):
        assert detect(text).level == LEVEL_CRITICAL

    def test_critical_beats_bonus_rules(self):
        """命中 critical 直接 3，不受修饰加权影响。"""
        assert detect("我想自杀").level == LEVEL_CRITICAL
        assert detect("我非常想自杀！！！").level == LEVEL_CRITICAL

    def test_trigger_type_is_keyword(self):
        assert detect("我想自杀").trigger_type == TRIGGER_KEYWORD

    def test_matched_terms_are_collected(self):
        signal = detect("我不想活了，想死")
        assert "不想活" in signal.matched_terms or "不想活了" in signal.matched_terms
        assert "想死" in signal.matched_terms

    def test_negation_does_not_exempt(self):
        """★ 关键：否定句也命中。

        对心理场景，假阴性的代价远高于假阳性 —— 误报由人工在工单里标忽略即可。
        别去"智能地"排除否定句。
        """
        assert detect("我不会自杀的").level == LEVEL_CRITICAL


class TestWarning:
    def test_warning_alone_is_level_2(self):
        assert detect("我很绝望").level == LEVEL_WARNING

    @pytest.mark.parametrize("text", ["撑不下去了", "感觉要崩溃", "我讨厌自己", "我是负担"])
    def test_warning_terms(self, text: str):
        assert detect(text).level == LEVEL_WARNING

    def test_warning_with_two_bonus_becomes_critical(self):
        """warning + bonus>=2 → 升级为 3。"""
        assert detect("我非常绝望！！").level == LEVEL_CRITICAL

    def test_warning_with_one_bonus_stays_warning(self):
        """只有 1 点加权不够升级。"""
        assert detect("我非常绝望").level == LEVEL_WARNING


class TestAttention:
    def test_attention_alone_is_level_1(self):
        assert detect("我有点难过").level == LEVEL_ATTENTION

    @pytest.mark.parametrize("text", ["晚上失眠", "压力好大", "很想哭", "觉得孤单", "很无助"])
    def test_attention_terms(self, text: str):
        assert detect(text).level == LEVEL_ATTENTION

    def test_attention_with_two_bonus_becomes_warning(self):
        assert detect("我真的很难过！！").level == LEVEL_WARNING

    def test_attention_with_one_bonus_stays_attention(self):
        assert detect("我真的很难过").level == LEVEL_ATTENTION


class TestBonus:
    """加权规则：程度副词 +1，感叹号每个 +1 但最多算 2 个。"""

    def test_intensifier_counts_one(self):
        assert detect("我真的很难过").level == LEVEL_ATTENTION  # bonus=1，不升级

    def test_two_exclamations_reach_threshold(self):
        # 无程度副词，两个感叹号 → bonus=2
        assert detect("我难过！！").level == LEVEL_WARNING

    def test_single_exclamation_not_enough(self):
        assert detect("我难过！").level == LEVEL_ATTENTION

    def test_exclamation_cap_is_two(self):
        """再多感叹号也只算 2，不会把 attention 一路顶到 critical。"""
        assert detect("我难过！！！！！！！").level == LEVEL_WARNING

    def test_halfwidth_exclamation_counts(self):
        assert detect("我难过!!").level == LEVEL_WARNING

    def test_mixed_half_and_full_width(self):
        assert detect("我难过！!").level == LEVEL_WARNING


class TestNormalization:
    def test_spaces_are_stripped_before_matching(self):
        """「我 想 自 杀」这种拆字绕过也必须命中。"""
        assert detect("我 想 自 杀").level == LEVEL_CRITICAL

    def test_newlines_and_tabs_stripped(self):
        assert detect("我\n想\t自\n杀").level == LEVEL_CRITICAL

    def test_ascii_whitespace_removed(self):
        assert normalize("a b\tc\nd") == "abcd"

    def test_ideographic_space_is_NOT_removed(self):
        """⚠️ 与 Java 保持一致的关键点。

        Java 的 `\\s` 只认 ASCII 空白，全角空格 U+3000 不在其列。
        Python 的 `re` 默认会把它当空白吃掉 —— 那样"自　杀"在两边行为就不同了。
        这里显式用 ASCII 字符类，所以全角空格保留、词不连续、不命中。
        """
        assert normalize("自\u3000杀") == "自\u3000杀"
        assert detect("自\u3000杀").level == LEVEL_NONE

    def test_ideographic_space_between_unrelated_parts_still_hits(self):
        """"我真的　很难过" —— 全角空格保留，但"难过"仍连续，照常命中。"""
        assert detect("我真的\u3000很难过").level == LEVEL_ATTENTION


class TestSnippet:
    def test_none_passthrough(self):
        assert snippet(None) is None

    def test_short_text_unchanged(self):
        assert snippet("  短文本  ") == "短文本"

    def test_long_text_truncated_with_ellipsis(self):
        long_text = "啊" * 200
        result = snippet(long_text)
        assert result is not None
        assert result.endswith("...")
        assert len(result) == SNIPPET_MAX + 3

    def test_exactly_at_limit_not_truncated(self):
        text = "啊" * SNIPPET_MAX
        assert snippet(text) == text


class TestCrisisSignal:
    def test_is_crisis_flag(self):
        assert detect("我想自杀").is_crisis is True
        assert detect("今天很开心").is_crisis is False

    def test_none_signal_shape(self):
        signal = detect("今天很开心")
        assert signal.level == LEVEL_NONE
        assert signal.trigger_type == "NONE"
        assert signal.matched_terms == []
