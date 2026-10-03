"""RAG 服务：切片索引 + 检索 + 上下文拼装。

链路：知识文章 →（切片）→ knowledge_chunk →（检索）→ top-k 片段
      → 拼进系统提示词 → 模型据此回答 → 前端展示来源

设计取舍（重要）：
    用 2-gram 粗排而非向量库，原因是当前语料量小、且不想引入新依赖。
    失败模式是"同义不同词检索不到"（见 tests/test_retrieval.py 的
    test_known_limitation_synonyms）。升级路径是把 retrieve() 换成向量检索，
    上层（chat 路由、提示词拼装）完全不用改。

⚠️ 注入了检索内容的回答，必须**允许模型说"资料里没有"**，
   否则它会拿片段硬凑答案 —— 心理场景下编造信息比说"不知道"危险得多。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.retrieval import DEFAULT_TOP_K, RetrievedChunk, rank, split_into_chunks
from app.models import KnowledgeArticle, KnowledgeChunk

logger = logging.getLogger(__name__)

# 只检索已发布的文章（status == 1），草稿不该被引用
PUBLISHED_STATUS = 1

# 拼进提示词的片段上限，避免上下文过长
MAX_CONTEXT_CHARS = 1500


def reindex_article(db: Session, article_id: str) -> int:
    """重建某篇文章的切片。返回写入的切片数。"""
    article = db.get(KnowledgeArticle, article_id)
    if article is None:
        return 0

    # 先删旧切片（文章内容可能已经变了）
    for old in db.scalars(
        select(KnowledgeChunk).where(KnowledgeChunk.article_id == article_id)
    ).all():
        db.delete(old)

    pieces = split_into_chunks(article.content or "")
    for index, piece in enumerate(pieces):
        db.add(KnowledgeChunk(article_id=article_id, chunk_index=index, content=piece))

    db.commit()
    return len(pieces)


def reindex_all(db: Session) -> dict[str, int]:
    """重建全部已发布文章的切片。用于初始化或手动触发。"""
    articles = list(
        db.scalars(
            select(KnowledgeArticle).where(KnowledgeArticle.status == PUBLISHED_STATUS)
        ).all()
    )

    # 清空后重建，避免已删文章的残留切片
    for old in db.scalars(select(KnowledgeChunk)).all():
        db.delete(old)
    db.commit()

    total = 0
    for article in articles:
        pieces = split_into_chunks(article.content or "")
        for index, piece in enumerate(pieces):
            db.add(KnowledgeChunk(article_id=article.id, chunk_index=index, content=piece))
        total += len(pieces)

    db.commit()
    logger.info("知识库重建切片完成：%d 篇文章 / %d 个片段", len(articles), total)
    return {"articles": len(articles), "chunks": total}


def retrieve(db: Session, query: str, top_k: int = DEFAULT_TOP_K) -> list[RetrievedChunk]:
    """检索与 query 最相关的知识片段。

    取全部已发布文章的切片做粗排 —— 当前语料量下开销可忽略；
    将来切片数上到万级时应改为"先按关键词筛候选，再精排"。
    """
    if not query or not query.strip():
        return []

    rows = db.execute(
        select(
            KnowledgeChunk.article_id,
            KnowledgeChunk.content,
            KnowledgeArticle.title,
            KnowledgeArticle.status,
        )
        .join(KnowledgeArticle, KnowledgeArticle.id == KnowledgeChunk.article_id)
        .where(KnowledgeArticle.status == PUBLISHED_STATUS)
    ).all()

    candidates = [(article_id, title, content, "") for article_id, content, title, _ in rows]
    return rank(query, candidates, top_k=top_k)


def build_context(chunks: list[RetrievedChunk]) -> str:
    """把检索片段拼成给模型看的参考资料块。

    明确标注"参考资料"并允许模型说没有 —— 见模块顶部说明。
    """
    if not chunks:
        return ""

    parts: list[str] = []
    used = 0
    for i, chunk in enumerate(chunks, start=1):
        title = chunk.source_title or "未命名资料"
        block = f"[资料{i}]《{title}》\n{chunk.content}"
        if used + len(block) > MAX_CONTEXT_CHARS:
            break
        parts.append(block)
        used += len(block)

    if not parts:
        return ""

    body = "\n\n".join(parts)
    return (
        "\n\n【参考资料】以下是知识库中与本话题相关的资料，请优先参考它们来回答：\n\n"
        f"{body}\n\n"
        "注意：\n"
        "1. 如果资料与用户的问题无关，就忽略它们，按你自己的专业判断回答；\n"
        "2. 资料没有覆盖到的部分，不要强行编造，可以直接说「这方面资料里没有提到」；\n"
        "3. 不要向用户复述「根据资料1」这类措辞，自然地融入回答即可。"
    )


def sources_payload(chunks: list[RetrievedChunk]) -> list[dict[str, Any]]:
    """给前端的来源列表（去重，按分数排序）。"""
    seen: set[Any] = set()
    result: list[dict[str, Any]] = []
    for chunk in chunks:
        if chunk.source_id in seen:
            continue
        seen.add(chunk.source_id)
        result.append(
            {
                "articleId": chunk.source_id,
                "title": chunk.source_title,
                "score": chunk.score,
            }
        )
    return result
