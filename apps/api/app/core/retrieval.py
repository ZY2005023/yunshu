"""知识检索（RAG 的"R"）—— 零依赖的中文友好实现。

为什么不用向量库：
    当前知识库只有个位数文章，向量检索的收益体现不出来，而代价是要引入
    chromadb / faiss 这类新依赖并确定 embedding 方案。先用**字符 2-gram**
    把"检索 → 注入提示词 → 回答附来源"这条链路跑通，等语料量上来了
    再换向量库 —— 上层接口不变。

中文为什么要 2-gram：
    中文没有空格，按空格切词无效。2-gram（"心理" "理健" "健康"）是 CJK
    检索的经典简化做法，不需要词典，对未登录词也友好。
    英文数字则按单词切分。

⚠️ 这套打分的定位是"够用的粗排"，不是精确语义匹配。
   它的失败模式是：问法和原文用词完全对不上时检索不到。
   这是已知取舍，不是 bug。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

# 中文（含扩展区常见字）+ 英文数字
_CJK_RUN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]+")
_WORD = re.compile(r"[A-Za-z0-9]+")

# 单字在 2-gram 里噪音大，长度 1 的中文段单独作为一个 token
MIN_CJK_LEN = 1

# 打分权重：覆盖率占主导，绝对命中数作为微调
COVERAGE_WEIGHT = 0.7
HIT_WEIGHT = 0.3
HIT_SATURATION = 8.0

DEFAULT_TOP_K = 3
# 低于这个分数视为不相关，宁可不给上下文也不要塞入噪音
MIN_RELEVANCE = 0.12


def tokenize(text: str | None) -> list[str]:
    """把文本切成 token：中文取 2-gram，英文数字取小写单词。"""
    if not text:
        return []

    tokens: list[str] = []

    for run in _CJK_RUN.findall(text):
        if len(run) <= 2:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))

    tokens.extend(word.lower() for word in _WORD.findall(text))

    return tokens


def relevance(query_tokens: Sequence[str], text: str | None) -> float:
    """0-1 相关度。query 的 token 有多少比例出现在文本里。"""
    if not query_tokens or not text:
        return 0.0

    text_tokens = set(tokenize(text))
    if not text_tokens:
        return 0.0

    unique_query = set(query_tokens)
    hits = sum(1 for t in unique_query if t in text_tokens)
    if hits == 0:
        return 0.0

    coverage = hits / len(unique_query)
    # 饱和分母取"查询 token 数"（封顶在 HIT_SATURATION），
    # 这样完全覆盖时必然得到 1.0 —— 用固定常数会让短查询永远拿不到满分。
    denominator = max(1, min(len(unique_query), int(HIT_SATURATION)))
    hit_factor = min(hits / denominator, 1.0)

    return round(COVERAGE_WEIGHT * coverage + HIT_WEIGHT * hit_factor, 4)


@dataclass(frozen=True)
class RetrievedChunk:
    """一条检索结果。"""

    score: float
    content: str
    source_id: Any = None
    source_title: str | None = None
    chunk_index: int = 0

    def as_source(self) -> dict[str, Any]:
        """给前端看的来源信息（不带正文，避免响应过大）。"""
        return {
            "articleId": self.source_id,
            "title": self.source_title,
            "chunkIndex": self.chunk_index,
        }


def rank(
    query: str,
    candidates: Iterable[tuple[Any, str | None, str | None, str]],
    top_k: int = DEFAULT_TOP_K,
    min_score: float = MIN_RELEVANCE,
) -> list[RetrievedChunk]:
    """对候选切片打分排序。

    Args:
        query: 用户问题
        candidates: 可迭代的 (source_id, source_title, chunk_content, article_context)
            其中 article_context 用于"标题也算进来"——标题往往最能代表主题。
        top_k: 取前几条
        min_score: 低于此分直接丢弃
    """
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    scored: list[RetrievedChunk] = []
    for index, (source_id, title, content, context) in enumerate(candidates):
        if not content:
            continue
        # 标题的权重天然更高：命中标题通常意味着强相关
        body_score = relevance(query_tokens, content)
        title_score = relevance(query_tokens, title) if title else 0.0
        # 标题命中给 1.25 倍加成，但结果仍封顶在 1.0
        score = min(1.0, body_score + title_score * 0.25)
        if score >= min_score:
            scored.append(
                RetrievedChunk(
                    score=score,
                    content=content,
                    source_id=source_id,
                    source_title=title,
                    chunk_index=index,
                )
            )

    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_k]


def split_into_chunks(text: str | None, max_len: int = 300, overlap: int = 50) -> list[str]:
    """把长文按段落切分，段落过长再按长度硬切。

    保留 overlap 是为了避免答案正好被切在边界上而检索不到。
    """
    if not text or not text.strip():
        return []

    # 先按空行/换行分段，再合并过短的段落
    raw_parts = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]

    merged: list[str] = []
    buffer = ""
    for part in raw_parts:
        if not buffer:
            buffer = part
        elif len(buffer) + len(part) + 1 <= max_len:
            buffer = f"{buffer}\n{part}"
        else:
            merged.append(buffer)
            buffer = part
    if buffer:
        merged.append(buffer)

    # 仍然超长的按窗口硬切
    chunks: list[str] = []
    step = max(1, max_len - overlap)
    for part in merged:
        if len(part) <= max_len:
            chunks.append(part)
            continue
        for start in range(0, len(part), step):
            piece = part[start : start + max_len]
            if piece.strip():
                chunks.append(piece)
            if start + max_len >= len(part):
                break

    return chunks
