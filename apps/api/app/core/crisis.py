"""危机检测规则层 —— 逐字对齐 Java 版 `AiService/CrisisDetectionService`。

这是整个迁移里**后果最严重**的一块：漏判的代价不是 bug，是安全事故。
所以规则、阈值、甚至 Set 的迭代顺序都按原样搬，不做任何"优化"。

‼️ 一个容易忽略的差异：
Java 的 `\\s` 只匹配 ASCII 空白 `[ \\t\\n\\x0B\\f\\r]`，
而 Python 的 `re` 默认 `\\s` 是 Unicode 语义，会连全角空格 `\\u3000` 一起吃掉。
两边归一化结果不同，就可能一边命中一边漏判。
所以这里显式用 `_ASCII_WS`，不用 `\\s`。

设计取向（原话）：**宁可误报不可漏报**。
例如"我不会自杀的"同样命中 —— 心理健康场景下假阴性的代价远高于假阳性，
误报由人工在工单里标记忽略即可。别去"智能地"排除否定句。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Java `\\s+` 的真实语义：只认这 6 个 ASCII 空白字符
_ASCII_WS = re.compile(r"[ \t\n\x0B\f\r]+")

LEVEL_NONE = 0
LEVEL_ATTENTION = 1
LEVEL_WARNING = 2
LEVEL_CRITICAL = 3

TRIGGER_KEYWORD = "KEYWORD"
TRIGGER_NONE = "NONE"

DEDUP_MINUTES = 5
SNIPPET_MAX = 120

# ---------------------------------------------------------------------------
# 关键词词库
# ---------------------------------------------------------------------------

CRITICAL_TERMS: tuple[str, ...] = (
    "自杀", "自尽", "轻生", "不想活", "不想活了", "活不下去", "活着没意思", "活着没意义",
    "去死", "想死", "死了算了", "不如死了", "结束生命", "结束自己", "了断", "解脱了",
    "遗书", "遗言", "跳楼", "跳河", "割腕", "上吊", "烧炭", "安眠药自杀", "服毒",
)

WARNING_TERMS: tuple[str, ...] = (
    "绝望", "没有希望", "看不到希望", "撑不下去", "熬不下去", "扛不住", "崩溃",
    "自残", "自伤", "伤害自己", "讨厌自己", "恨自己", "我是负担", "拖累别人",
    "没人在乎我", "没人需要我", "消失就好了", "活着是多余的",
)

ATTENTION_TERMS: tuple[str, ...] = (
    "难过", "焦虑", "失眠", "压力好大", "压力太大", "想哭", "孤单", "无助",
    "提不起劲", "身心俱疲",
)

INTENSIFIER = re.compile("非常|特别|极其|极度|太|好想|真的|一直|每天|无时无刻")

# 半角 ! 和全角 ！ 都算，对应 Java 的 `c == '！' || c == '!'`
_EXCLAMATION_MARKS = ("!", "！")


@dataclass(frozen=True)
class CrisisSignal:
    """规则层检测结果。level == 0 表示未命中。"""

    level: int = LEVEL_NONE
    trigger_type: str = TRIGGER_NONE
    matched_terms: list[str] = field(default_factory=list)

    @property
    def is_crisis(self) -> bool:
        return self.level > 0

    @classmethod
    def none(cls) -> "CrisisSignal":
        return cls(LEVEL_NONE, TRIGGER_NONE, [])


def normalize(text: str) -> str:
    """去掉空白后进行匹配。

    为什么要去空白："我 想 自 杀" 这种绕过也必须命中。
    为什么用 ASCII 空白而非 `\\s`：见模块顶部说明。
    """
    return _ASCII_WS.sub("", text)


def hit_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    """命中了哪些词。保持词库原有顺序（对应 Java 的 LinkedHashSet）。"""
    return [t for t in terms if t in text]


def detect(text: str | None) -> CrisisSignal:
    """规则层检测。

    分级逻辑（**不要改动判定边界**）：
        critical 命中       → 3
        warning 命中         → bonus >= 2 ? 3 : 2
        attention 命中       → bonus >= 2 ? 2 : 1
        都没命中             → 0
    """
    if text is None or not text.strip():
        return CrisisSignal.none()

    normalized = normalize(text)

    critical_hits = hit_terms(normalized, CRITICAL_TERMS)
    warning_hits = hit_terms(normalized, WARNING_TERMS)
    attention_hits = hit_terms(normalized, ATTENTION_TERMS)

    # 所有命中词的并集，顺序为 critical → warning → attention
    all_hits: list[str] = []
    for group in (critical_hits, warning_hits, attention_hits):
        for term in group:
            if term not in all_hits:
                all_hits.append(term)

    bonus = 0
    if INTENSIFIER.search(normalized):
        bonus += 1
    exclamations = sum(1 for c in normalized if c in _EXCLAMATION_MARKS)
    bonus += min(exclamations, 2)

    if critical_hits:
        level = LEVEL_CRITICAL
    elif warning_hits:
        level = LEVEL_CRITICAL if bonus >= 2 else LEVEL_WARNING
    elif attention_hits:
        level = LEVEL_WARNING if bonus >= 2 else LEVEL_ATTENTION
    else:
        level = LEVEL_NONE

    if level == LEVEL_NONE:
        return CrisisSignal.none()

    return CrisisSignal(level, TRIGGER_KEYWORD, all_hits)


def snippet(text: str | None) -> str | None:
    """只留片段，避免把整段私密倾诉再复制一份到危机事件表里。

    超长时截断到 120 字符并追加 "..."，与原版一致。
    """
    if text is None:
        return None
    trimmed = text.strip()
    return trimmed if len(trimmed) <= SNIPPET_MAX else trimmed[:SNIPPET_MAX] + "..."
