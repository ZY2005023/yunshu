"""知识检索测试 —— 2-gram 打分的边界与已知取舍。

⚠️ 这套实现是"够用的粗排"，不是语义匹配。测试里特意包含了一条
**已知失败模式**（同义不同词检索不到），目的是把取舍记录下来，
而不是假装它不存在。
"""

from __future__ import annotations

import pytest

from app.core.retrieval import (
    DEFAULT_TOP_K,
    MIN_RELEVANCE,
    RetrievedChunk,
    rank,
    relevance,
    split_into_chunks,
    tokenize,
)


class TestTokenize:
    def test_two_gram_for_chinese(self):
        assert tokenize("心理健康") == ["心理", "理健", "健康"]

    def test_short_chinese_run_kept_whole(self):
        assert tokenize("焦虑") == ["焦虑"]
        assert tokenize("好") == ["好"]

    def test_english_words_lowercased(self):
        assert tokenize("CBT Therapy") == ["cbt", "therapy"]

    def test_mixed_text(self):
        tokens = tokenize("焦虑 CBT 疗法")
        assert "焦虑" in tokens
        assert "cbt" in tokens
        assert "疗法" in tokens

    def test_punctuation_ignored(self):
        assert tokenize("焦虑，怎么办？") == ["焦虑", "怎么", "么办"]

    def test_empty_input(self):
        assert tokenize(None) == []
        assert tokenize("") == []

    def test_multiple_runs_do_not_cross_boundary(self):
        """"焦虑 睡眠" 不该产生跨空格的 "虑睡"。"""
        assert "虑睡" not in tokenize("焦虑 睡眠")


class TestRelevance:
    def test_perfect_overlap(self):
        tokens = tokenize("焦虑")
        assert relevance(tokens, "焦虑") == pytest.approx(1.0)

    def test_no_overlap(self):
        assert relevance(tokenize("焦虑"), "今天的天气很好") == 0.0

    def test_partial_overlap(self):
        tokens = tokenize("焦虑怎么办")
        score = relevance(tokens, "焦虑的时候可以深呼吸")
        assert 0 < score < 1

    def test_empty_inputs(self):
        assert relevance([], "任何文本") == 0.0
        assert relevance(tokenize("焦虑"), None) == 0.0
        assert relevance(tokenize("焦虑"), "") == 0.0

    def test_longer_text_does_not_inflate_score(self):
        """覆盖率制：往文本里堆字不该让分数变高。"""
        tokens = tokenize("焦虑")
        short = relevance(tokens, "焦虑")
        long = relevance(tokens, "焦虑" + "无关内容" * 50)
        assert long <= short


class TestRank:
    CANDIDATES = [
        (1, "如何应对考试焦虑", "考试前紧张是很正常的，可以试试深呼吸。", ""),
        (2, "改善睡眠质量", "睡前不要看手机，保持规律作息。", ""),
        (3, "认识抑郁情绪", "抑郁不等于心情不好，需要专业评估。", ""),
    ]

    def test_returns_most_relevant_first(self):
        results = rank("考试焦虑怎么办", self.CANDIDATES, top_k=3, min_score=0.0)
        assert results
        assert results[0].source_id == 1

    def test_respects_top_k(self):
        results = rank("焦虑 睡眠 抑郁", self.CANDIDATES, top_k=2, min_score=0.0)
        assert len(results) == 2

    def test_min_score_filters_irrelevant(self):
        results = rank("完全无关的话题", self.CANDIDATES, min_score=0.5)
        assert results == []

    def test_default_min_score_avoids_noise(self):
        """默认阈值下，弱相关的内容不该被塞进上下文。"""
        results = rank("睡眠", self.CANDIDATES, top_k=5)
        for r in results:
            assert r.score >= MIN_RELEVANCE

    def test_title_hit_boosts_score(self):
        """标题命中应有加成 —— 标题通常最能代表主题。"""
        a = rank("考试焦虑", [(1, "考试焦虑应对", "一些内容", "")], min_score=0.0)[0]
        b = rank("考试焦虑", [(1, "其他标题", "一些内容", "")], min_score=0.0)
        assert not b or a.score >= b[0].score

    def test_empty_query(self):
        assert rank("", self.CANDIDATES) == []

    def test_empty_candidates(self):
        assert rank("焦虑", []) == []

    def test_source_payload_shape(self):
        results = rank("考试焦虑", self.CANDIDATES, min_score=0.0)
        payload = results[0].as_source()
        assert set(payload.keys()) == {"articleId", "title", "chunkIndex"}
        assert "content" not in payload, "来源信息不该带正文，避免响应过大"

    def test_result_is_frozen(self):
        r = rank("焦虑", self.CANDIDATES, min_score=0.0)[0]
        with pytest.raises(Exception):
            r.score = 999  # type: ignore[misc]

    def test_known_limitation_synonyms(self):
        """★ 已知取舍：同义不同词检索不到。

        "睡不着" 与 "失眠" 语义相同，但 2-gram 匹配不上。
        这是不用向量库的代价，记录下来；将来换向量库时这条用例应当改成
        "应该能检索到"，并作为升级的验收标准。
        """
        results = rank("我睡不着", [(1, "失眠的应对", "失眠时建议保持规律作息。", "")])
        assert results == [], "当前实现确实检索不到 —— 这是已知限制"

    def test_exact_word_match_works(self):
        results = rank("失眠", [(1, "失眠的应对", "失眠时建议保持规律作息。", "")])
        assert results, "用词一致时应当能检索到"


class TestSplitIntoChunks:
    def test_empty(self):
        assert split_into_chunks(None) == []
        assert split_into_chunks("   ") == []

    def test_short_text_single_chunk(self):
        assert split_into_chunks("很短的一段话") == ["很短的一段话"]

    def test_split_by_blank_line(self):
        text = "第一段。" + "啊" * 200 + "\n\n" + "第二段。" + "哦" * 200
        chunks = split_into_chunks(text, max_len=100)
        assert len(chunks) >= 2

    def test_long_paragraph_is_windowed(self):
        chunks = split_into_chunks("字" * 1000, max_len=300, overlap=50)
        assert len(chunks) > 1
        assert all(len(c) <= 300 for c in chunks)

    def test_overlap_keeps_boundary_content(self):
        """相邻切片要有重叠，避免答案正好被切在边界上。"""
        text = "".join(f"{i:03d}" for i in range(200))
        chunks = split_into_chunks(text, max_len=100, overlap=20)
        assert len(chunks) >= 2
        tail = chunks[0][-20:]
        assert tail in chunks[1]

    def test_no_empty_chunks(self):
        chunks = split_into_chunks("段一\n\n\n\n段二\n\n段三")
        assert all(c.strip() for c in chunks)


class TestEndToEndRetrieval:
    """模拟真实用法：从文章列表里找出与问题最相关的片段。"""

    ARTICLES = [
        (10, "缓解考试焦虑的五个方法", "考试焦虑很常见。深呼吸、规律作息、适度运动都有帮助。" * 3, ""),
        (11, "睡眠与情绪的关系", "长期失眠会加重焦虑和抑郁情绪，建议保持规律作息。" * 3, ""),
        (12, "什么是心理咨询", "心理咨询是专业的助人过程，不是聊天。" * 3, ""),
    ]

    def test_anxiety_question_hits_anxiety_article(self):
        results = rank("考试焦虑怎么办", self.ARTICLES)
        assert results
        assert results[0].source_id == 10

    def test_sleep_question_hits_sleep_article(self):
        results = rank("失眠", self.ARTICLES)
        assert results
        assert results[0].source_id == 11

    def test_unrelated_question_returns_nothing(self):
        assert rank("怎么修电脑", self.ARTICLES) == []

    def test_default_top_k_value(self):
        assert DEFAULT_TOP_K == 3

    def test_chunk_type(self):
        results = rank("焦虑", self.ARTICLES)
        assert isinstance(results[0], RetrievedChunk)
