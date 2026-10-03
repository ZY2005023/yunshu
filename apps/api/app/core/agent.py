"""意图路由 —— 把用户输入分派给五类 Agent。

对应《系统改造方案》P2 第 5 项「Agent 路由」：
    拆为 危机 / 信息 / 资源 / 评估 / 转介 五类 + 意图路由，**危机优先**。

设计取舍：
    先用**规则路由**，不上模型分类器。理由：
    · 危机通道绝不能依赖模型判断 —— 模型超时/降级时它必须仍然可用，
      所以危机识别直接复用规则层（core/crisis.py），零延迟零成本；
    · 其余四类的区分度靠关键词足够（"怎么预约" vs "有什么方法"），
      真要做细可以后置一个轻量分类器，但不影响现在的接口形状。

    route() 的签名和返回结构是按"将来可能换成模型分类"设计的：
    调用方只关心 (agent, confidence)，不关心怎么算出来的。

⚠️ 危机优先级不可动摇：
    只要规则层判定为危机（level > 0），无论文本里还包含什么其他特征，
    一律走 CRISIS —— 哪怕它在问"考试焦虑怎么办"。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final

from app.core.crisis import detect as crisis_detect


class AgentType(str, Enum):
    CRISIS = "CRISIS"          # 危机干预：安抚 + 求助资源 + 强制留痕
    ASSESSMENT = "ASSESSMENT"  # 评估引导：引导去做标准化量表
    REFERRAL = "REFERRAL"      # 转介：怎么找咨询师 / 预约 / 校心理中心
    RESOURCE = "RESOURCE"      # 资源：想看书/文章/自助材料
    INFO = "INFO"              # 信息：知识性提问（默认）


AGENT_LABELS: Final[dict[str, str]] = {
    AgentType.CRISIS.value: "危机干预",
    AgentType.ASSESSMENT.value: "心理评估",
    AgentType.REFERRAL.value: "转介引导",
    AgentType.RESOURCE.value: "资源推荐",
    AgentType.INFO.value: "知识解答",
}

# ===========================================================================
# 各 Agent 的提示词补充
#
# 注意：CRISIS 的补充内容不在这里 —— 它在 services/crisis.py 的
# CRISIS_PROMPT_CLAUSE，由 ai._system_prompt() 恒定拼上。
# 原因是危机要求必须在**任何**模式下都生效，而不只是路由到 CRISIS 时生效。
# ===========================================================================

AGENT_PROMPT_CLAUSES: Final[dict[str, str]] = {
    AgentType.ASSESSMENT.value: (
        "\n\n【当前场景：心理评估】用户想了解自己的心理状态或想做测评。请：\n"
        "1. 不要凭对话给出任何诊断性判断（不说「你这是抑郁症」这类话）；\n"
        "2. 说明标准化量表（如 PHQ-9 抑郁筛查、GAD-7 焦虑筛查）比聊天更能反映状态；\n"
        "3. 主动引导用户到本系统的「心理测评」功能做一次自评；\n"
        "4. 强调量表结果是筛查不是诊断，高分需要专业人员进一步评估。"
    ),
    AgentType.REFERRAL.value: (
        "\n\n【当前场景：转介引导】用户想找人帮忙或不知道怎么求助。请：\n"
        "1. 明确肯定「主动求助」这件事本身很有力量，不要说成「问题很严重才需要」；\n"
        "2. 具体告诉他可以去哪：学校心理健康教育中心（通常免费、保密）、"
        "辅导员、校医院，必要时拨打心理援助热线 12356；\n"
        "3. 如果用户担心「别人会知道」，说明咨询的保密原则与例外情形；\n"
        "4. 可以帮他把「要说什么」理一理，降低开口的门槛。"
    ),
    AgentType.RESOURCE.value: (
        "\n\n【当前场景：资源推荐】用户想看资料或自助材料。请：\n"
        "1. 优先推荐本系统知识库里已有的文章（如果参考资料里有相关内容）；\n"
        "2. 推荐自助方法时给出可操作的具体步骤，不要只给名词；\n"
        "3. 提醒自助材料不能替代专业帮助。"
    ),
    AgentType.INFO.value: (
        "\n\n【当前场景：知识解答】用户在问一个知识性问题。请：\n"
        "1. 把概念讲清楚，避免术语堆砌；\n"
        "2. 讲完知识后回到用户自身的处境，问问他具体遇到了什么；\n"
        "3. 不要停留在科普，留意他的情绪状态。"
    ),
}

DEFAULT_AGENT = AgentType.INFO

# ===========================================================================
# 关键词表
# ===========================================================================

_ASSESSMENT_TERMS: Final[tuple[str, ...]] = (
    "量表", "测评", "测试", "测一测", "评估", "phq", "gad",
    "我是不是抑郁", "我是不是焦虑", "算不算抑郁", "算不算焦虑",
    "有没有抑郁", "有没有焦虑", "心理健康测试", "自评",
)

_REFERRAL_TERMS: Final[tuple[str, ...]] = (
    "预约", "咨询师", "心理医生", "精神科", "看医生", "挂号", "就诊",
    "找谁", "找谁聊", "去哪里看", "心理健康中心", "心理咨询中心",
    "辅导员", "老师帮忙", "怎么求助", "求助", "转介", "介绍个",
)

_RESOURCE_TERMS: Final[tuple[str, ...]] = (
    "推荐", "有什么书", "看书", "书单", "文章", "资料", "自助",
    "练习", "方法汇总", "教程", "材料", "视频", "课程",
)

# 判定置信度
CONFIDENCE_CRISIS = 1.0
CONFIDENCE_MULTI_HIT = 0.85
CONFIDENCE_SINGLE_HIT = 0.7
CONFIDENCE_DEFAULT = 0.4

# ★ 路由的危机阈值是 level >= 2，**不是** level > 0。
#   规则层的 level 1 是「关注级」（命中"焦虑""失眠"这类词），
#   用来弹求助卡片合理（宁可误报），但拿它劫持路由就过头了 ——
#   实测「推荐几本关于焦虑的书」会被判成危机。
#   注意这与 SSE 里 crisis 卡片的触发条件（level > 0）**刻意不同**：
#   卡片宁可多弹，路由不能乱转。
CRISIS_ROUTING_LEVEL = 2

# 多命中阈值
MULTI_HIT_THRESHOLD = 2


@dataclass(frozen=True)
class AgentDecision:
    """路由结果。

    调用方只需要 agent；confidence / matched / reason 用于日志与调试 —— 
    出问题时能回答"为什么走了这个 Agent"比结果本身更重要。
    """

    agent: AgentType
    confidence: float
    matched: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def label(self) -> str:
        return AGENT_LABELS.get(self.agent.value, self.agent.value)

    def prompt_clause(self) -> str:
        return AGENT_PROMPT_CLAUSES.get(self.agent.value, "")

    def as_payload(self) -> dict[str, object]:
        """给前端/SSE 的载荷。"""
        return {
            "agent": self.agent.value,
            "label": self.label,
            "confidence": self.confidence,
        }


def _hits(text: str, terms: tuple[str, ...]) -> list[str]:
    return [t for t in terms if t in text]


def route(text: str | None) -> AgentDecision:
    """判定该走哪个 Agent。

    优先级：危机 > 评估 > 转介 > 资源 > 信息（默认）
    """
    if not text or not text.strip():
        return AgentDecision(DEFAULT_AGENT, CONFIDENCE_DEFAULT, [], "空输入，走默认")

    normalized = text.lower()

    # 1) 危机最高优先级 —— 复用规则层，不重复实现
    signal = crisis_detect(text)
    if signal.level >= CRISIS_ROUTING_LEVEL:
        return AgentDecision(
            AgentType.CRISIS,
            CONFIDENCE_CRISIS,
            list(signal.matched_terms),
            f"规则层判定 level={signal.level}（阈值 {CRISIS_ROUTING_LEVEL}）",
        )

    # 2) 余下四类按命中数打分
    candidates = (
        (AgentType.ASSESSMENT, _hits(normalized, _ASSESSMENT_TERMS)),
        (AgentType.REFERRAL, _hits(normalized, _REFERRAL_TERMS)),
        (AgentType.RESOURCE, _hits(normalized, _RESOURCE_TERMS)),
    )

    best_agent: AgentType | None = None
    best_hits: list[str] = []
    for agent, hits in candidates:
        if len(hits) > len(best_hits):
            best_agent, best_hits = agent, hits

    if best_agent is None:
        return AgentDecision(DEFAULT_AGENT, CONFIDENCE_DEFAULT, [], "未命中特征词，走默认")

    confidence = (
        CONFIDENCE_MULTI_HIT if len(best_hits) >= MULTI_HIT_THRESHOLD else CONFIDENCE_SINGLE_HIT
    )
    return AgentDecision(best_agent, confidence, best_hits, f"命中特征词 {best_hits}")


def all_agents() -> list[dict[str, str]]:
    """五类 Agent 的清单（供前端展示或调试）。"""
    return [
        {"agent": a.value, "label": AGENT_LABELS[a.value]}
        for a in (
            AgentType.CRISIS,
            AgentType.INFO,
            AgentType.RESOURCE,
            AgentType.ASSESSMENT,
            AgentType.REFERRAL,
        )
    ]
