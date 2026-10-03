"""量表计分测试 —— PHQ-9 / GAD-7。

这些用例的作用是**锁死公开标准的计分与分级**，任何一条挂掉都意味着
量表结果不再可信（也就失去了临床参考价值）。

最要紧的是 PHQ-9 第 9 题：**自伤念头得分 > 0 就必须预警，与总分无关**。
"""

from __future__ import annotations

import pytest

from app.core.scale import (
    DISCLAIMER,
    GAD7_CODE,
    GAD7_QUESTIONS,
    PHQ9_CODE,
    PHQ9_QUESTIONS,
    PHQ9_SELF_HARM_INDEX,
    ScaleResult,
    questions_of,
    score,
    score_gad7,
    score_phq9,
)


def _phq9(fill: int, ninth: int = 0) -> list[int]:
    """构造 PHQ-9 答案：前 8 题填 fill，第 9 题填 ninth。"""
    answers = [fill] * 9
    answers[PHQ9_SELF_HARM_INDEX] = ninth
    return answers


class TestQuestionBanks:
    def test_phq9_has_nine_questions(self):
        assert len(PHQ9_QUESTIONS) == 9

    def test_gad7_has_seven_questions(self):
        assert len(GAD7_QUESTIONS) == 7

    def test_phq9_ninth_is_self_harm(self):
        """第 9 题必须是自伤念头 —— 位置变了危机判定就全错。"""
        assert "伤害自己" in PHQ9_QUESTIONS[PHQ9_SELF_HARM_INDEX]
        assert PHQ9_SELF_HARM_INDEX == 8

    def test_questions_of(self):
        assert questions_of("PHQ9") == PHQ9_QUESTIONS
        assert questions_of("phq9") == PHQ9_QUESTIONS  # 大小写不敏感
        assert questions_of("GAD7") == GAD7_QUESTIONS

    def test_unknown_scale_rejected(self):
        with pytest.raises(ValueError, match="不支持的量表"):
            questions_of("BDI")


class TestPhq9Scoring:
    def test_all_zero(self):
        r = score_phq9([0] * 9)
        assert r.total == 0
        assert r.level == "无或极轻微"
        assert r.max_total == 27

    def test_all_three(self):
        r = score_phq9([3] * 9)
        assert r.total == 27
        assert r.level == "重度"

    @pytest.mark.parametrize(
        ("total", "expected"),
        [
            (0, "无或极轻微"),
            (4, "无或极轻微"),   # 上界
            (5, "轻度"),         # 下界
            (9, "轻度"),
            (10, "中度"),
            (14, "中度"),
            (15, "中重度"),
            (19, "中重度"),
            (20, "重度"),
            (27, "重度"),
        ],
    )
    def test_level_boundaries(self, total: int, expected: str):
        """★ 分级边界逐档验证 —— 0/4/5/9/10/14/15/19/20/27 都要对。"""
        # 顺序填满即可。前 8 题最多 24 分，所以 25 分以上必然会用到第 9 题，
        # 那会连带置上 self_harm_risk —— 但这里只断言分级，不受影响。
        # （自伤标记的边界在 TestSelfHarmRisk 里单独覆盖。）
        answers = [0] * 9
        idx, remain = 0, total
        while remain > 0:
            take = min(3, remain)
            answers[idx] = take
            remain -= take
            idx += 1
        assert sum(answers) == total
        result = score_phq9(answers)
        assert result.total == total
        assert result.level == expected

    def test_result_shape(self):
        r = score_phq9([1] * 9)
        assert isinstance(r, ScaleResult)
        assert r.code == PHQ9_CODE
        assert r.name == "PHQ-9 抑郁症筛查量表"
        assert r.answers == [1] * 9
        assert r.disclaimer == DISCLAIMER


class TestSelfHarmRisk:
    """★ PHQ-9 第 9 题：得分 > 0 即触发危机预警，与总分无关。"""

    def test_ninth_scored_one_triggers_alert(self):
        r = score_phq9(_phq9(0, ninth=1))
        assert r.total == 1
        assert r.level == "无或极轻微"
        assert r.self_harm_risk is True
        assert r.needs_crisis_alert is True
        assert r.self_harm_score == 1

    def test_ninth_scored_three_with_low_total(self):
        """总分只有 3 分（极轻微），但第 9 题满分 —— 仍然必须预警。"""
        r = score_phq9(_phq9(0, ninth=3))
        assert r.total == 3
        assert r.level == "无或极轻微"
        assert r.self_harm_risk is True

    def test_high_total_without_ninth_does_not_trigger(self):
        """总分 24（重度），但第 9 题 0 分 —— 不触发自伤预警。

        注意：这**不是**说此人无风险，只是该量表的自伤项未得分。
        分级本身仍是"重度"，该走的流程照样走。
        """
        r = score_phq9(_phq9(3, ninth=0))
        assert r.total == 24
        assert r.level == "重度"
        assert r.self_harm_risk is False
        assert r.needs_crisis_alert is False

    def test_ninth_zero_is_safe(self):
        assert score_phq9(_phq9(2, ninth=0)).self_harm_risk is False


class TestGad7Scoring:
    def test_all_zero(self):
        r = score_gad7([0] * 7)
        assert r.total == 0
        assert r.level == "无或极轻微"
        assert r.max_total == 21

    def test_all_three(self):
        r = score_gad7([3] * 7)
        assert r.total == 21
        assert r.level == "重度"

    @pytest.mark.parametrize(
        ("total", "expected"),
        [
            (0, "无或极轻微"),
            (4, "无或极轻微"),
            (5, "轻度"),
            (9, "轻度"),
            (10, "中度"),
            (14, "中度"),
            (15, "重度"),
            (21, "重度"),
        ],
    )
    def test_level_boundaries(self, total: int, expected: str):
        answers = [0] * 7
        idx, remain = 0, total
        while remain > 0:
            take = min(3, remain)
            answers[idx] = take
            remain -= take
            idx += 1
        assert sum(answers) == total
        assert score_gad7(answers).level == expected

    def test_gad7_has_no_self_harm_flag(self):
        """GAD-7 不含自伤题，所以永远不置该标记。"""
        r = score_gad7([3] * 7)
        assert r.self_harm_risk is False
        assert r.needs_crisis_alert is False

    def test_result_shape(self):
        r = score_gad7([2] * 7)
        assert r.code == GAD7_CODE
        assert r.name == "GAD-7 广泛性焦虑量表"


class TestValidation:
    def test_too_few_answers(self):
        with pytest.raises(ValueError, match="需要 9 个答案"):
            score_phq9([1, 2, 3])

    def test_too_many_answers(self):
        with pytest.raises(ValueError, match="需要 7 个答案"):
            score_gad7([1] * 9)

    def test_score_out_of_range_high(self):
        with pytest.raises(ValueError, match="必须在 0-3 之间"):
            score_phq9([4] + [0] * 8)

    def test_negative_score_rejected(self):
        with pytest.raises(ValueError, match="必须在 0-3 之间"):
            score_gad7([-1] + [0] * 6)

    def test_non_integer_rejected(self):
        with pytest.raises(ValueError, match="必须是整数"):
            score_phq9(["1"] + [0] * 8)  # type: ignore[list-item]

    def test_error_message_points_at_question_number(self):
        """错误信息要指明是第几题，方便定位。"""
        with pytest.raises(ValueError, match="第 3 题"):
            score_phq9([0, 0, 9] + [0] * 6)


class TestDispatch:
    def test_score_by_code(self):
        assert score("PHQ9", [1] * 9).total == 9
        assert score("GAD7", [1] * 7).total == 7

    def test_case_insensitive(self):
        assert score("phq9", [0] * 9).code == PHQ9_CODE

    def test_unknown_code(self):
        with pytest.raises(ValueError, match="不支持的量表"):
            score("MMPI", [1])


class TestDisclaimer:
    def test_disclaimer_mentions_hotline(self):
        assert "12356" in DISCLAIMER

    def test_disclaimer_says_not_diagnosis(self):
        assert "不能替代专业诊断" in DISCLAIMER
