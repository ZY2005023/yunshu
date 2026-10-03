"""标准化心理量表：PHQ-9（抑郁）与 GAD-7（焦虑）。

题目与分级均为**公开标准**，不要"优化"或改文案 —— 改了就不再是可比的量表结果，
临床参考价值也就没了。

计分规则：
    每题 0-3 分（PHQ-9 九题、GAD-7 七题），总分即各题之和。

⚠️ 安全相关：
    PHQ-9 第 9 题问的是"有不如死掉或用某种方式伤害自己的念头"。
    **该题只要 > 0 就必须触发危机预警**，不受总分影响 ——
    一个总分很低但第 9 题得 3 分的人，风险远高于总分高但第 9 题得 0 分的人。
    这是临床共识，也是这个模块最不能出错的地方。

    本模块只负责计分与判级，**不负责展示结论**。任何结果都应配合
    "量表不能替代诊断"的免责声明使用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

# ===========================================================================
# 选项（两个量表共用）
# ===========================================================================

OPTIONS: Final[tuple[str, ...]] = ("完全不会", "好几天", "一半以上的天数", "几乎每天")

MIN_SCORE = 0
MAX_SCORE = 3

# ===========================================================================
# PHQ-9
# ===========================================================================

PHQ9_CODE = "PHQ9"
PHQ9_NAME = "PHQ-9 抑郁症筛查量表"

PHQ9_QUESTIONS: Final[tuple[str, ...]] = (
    "做事时提不起劲或没有兴趣",
    "感到心情低落、沮丧或绝望",
    "入睡困难、睡不安稳或睡眠过多",
    "感觉疲倦或没有活力",
    "食欲不振或吃太多",
    "觉得自己很糟，或觉得自己是个失败者，或让自己或家人失望",
    "对事物专注有困难，例如阅读报纸或看电视时",
    "动作或说话速度缓慢到别人已经察觉，或正好相反——烦躁坐立不安、动来动去比平常更明显",
    "有不如死掉或用某种方式伤害自己的念头",
)

# 第 9 题（下标 8）：自伤/自杀念头
PHQ9_SELF_HARM_INDEX: Final[int] = 8

PHQ9_MAX_TOTAL = 27

# (下界, 上界, 等级名)
PHQ9_LEVELS: Final[tuple[tuple[int, int, str], ...]] = (
    (0, 4, "无或极轻微"),
    (5, 9, "轻度"),
    (10, 14, "中度"),
    (15, 19, "中重度"),
    (20, 27, "重度"),
)

# ===========================================================================
# GAD-7
# ===========================================================================

GAD7_CODE = "GAD7"
GAD7_NAME = "GAD-7 广泛性焦虑量表"

GAD7_QUESTIONS: Final[tuple[str, ...]] = (
    "感觉紧张、焦虑或急切",
    "不能停止或控制担忧",
    "对各种各样的事情担忧过多",
    "很难放松下来",
    "由于不安而无法静坐",
    "变得容易烦恼或急躁",
    "感到似乎将有可怕的事情发生而害怕",
)

GAD7_MAX_TOTAL = 21

GAD7_LEVELS: Final[tuple[tuple[int, int, str], ...]] = (
    (0, 4, "无或极轻微"),
    (5, 9, "轻度"),
    (10, 14, "中度"),
    (15, 21, "重度"),
)

DISCLAIMER = (
    "量表结果仅供参考，不能替代专业诊断。"
    "如果你的分数让你感到困扰，或出现伤害自己的念头，请及时联系专业人员或拨打心理援助热线 12356。"
)


@dataclass(frozen=True)
class ScaleResult:
    """量表计分结果。"""

    code: str
    name: str
    total: int
    level: str
    answers: list[int] = field(default_factory=list)
    max_total: int = 0
    # ★ PHQ-9 第 9 题 > 0 —— 无论总分多少都必须预警
    self_harm_risk: bool = False
    self_harm_score: int = 0
    disclaimer: str = DISCLAIMER

    @property
    def needs_crisis_alert(self) -> bool:
        return self.self_harm_risk


def _level_of(total: int, levels: tuple[tuple[int, int, str], ...], fallback: str) -> str:
    for low, high, name in levels:
        if low <= total <= high:
            return name
    # 超出量表范围（理论上不会发生，输入已校验）
    return levels[-1][2] if total > levels[-1][1] else fallback


def _validate(answers: list[int], expected_len: int, code: str) -> None:
    if len(answers) != expected_len:
        raise ValueError(f"{code} 需要 {expected_len} 个答案，收到 {len(answers)} 个")
    for i, a in enumerate(answers):
        if not isinstance(a, int) or isinstance(a, bool):
            raise ValueError(f"{code} 第 {i + 1} 题答案必须是整数，收到 {a!r}")
        if not MIN_SCORE <= a <= MAX_SCORE:
            raise ValueError(f"{code} 第 {i + 1} 题答案必须在 {MIN_SCORE}-{MAX_SCORE} 之间，收到 {a}")


def score_phq9(answers: list[int]) -> ScaleResult:
    """PHQ-9 计分。answers 为 9 个 0-3 的整数。"""
    _validate(answers, len(PHQ9_QUESTIONS), PHQ9_CODE)
    total = sum(answers)
    self_harm = answers[PHQ9_SELF_HARM_INDEX]
    return ScaleResult(
        code=PHQ9_CODE,
        name=PHQ9_NAME,
        total=total,
        level=_level_of(total, PHQ9_LEVELS, "无或极轻微"),
        answers=list(answers),
        max_total=PHQ9_MAX_TOTAL,
        self_harm_risk=self_harm > 0,
        self_harm_score=self_harm,
    )


def score_gad7(answers: list[int]) -> ScaleResult:
    """GAD-7 计分。answers 为 7 个 0-3 的整数。"""
    _validate(answers, len(GAD7_QUESTIONS), GAD7_CODE)
    total = sum(answers)
    return ScaleResult(
        code=GAD7_CODE,
        name=GAD7_NAME,
        total=total,
        level=_level_of(total, GAD7_LEVELS, "无或极轻微"),
        answers=list(answers),
        max_total=GAD7_MAX_TOTAL,
    )


SUPPORTED_SCALES: Final[dict[str, tuple[str, tuple[str, ...], object]]] = {
    PHQ9_CODE: (PHQ9_NAME, PHQ9_QUESTIONS, score_phq9),
    GAD7_CODE: (GAD7_NAME, GAD7_QUESTIONS, score_gad7),
}


def score(code: str, answers: list[int]) -> ScaleResult:
    """按量表代码计分。未知代码抛 ValueError。"""
    entry = SUPPORTED_SCALES.get(code.upper())
    if entry is None:
        raise ValueError(f"不支持的量表：{code}（可用：{', '.join(SUPPORTED_SCALES)}）")
    scorer = entry[2]
    return scorer(answers)  # type: ignore[operator]


def questions_of(code: str) -> tuple[str, ...]:
    entry = SUPPORTED_SCALES.get(code.upper())
    if entry is None:
        raise ValueError(f"不支持的量表：{code}")
    return entry[1]
