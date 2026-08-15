# -*- coding: utf-8 -*-
"""importer 覆盖：

- stem_similarity：相同 1.0 / 空串 0.0 / 完全不同低于阈值 / 微调字符越过阈值边界；
- normalize_stack：别名映射与白名单；
- parse_text：标签行（答案：/技术栈：/知识点：）、缺字段、--- 与空行分隔多题、
  JSON 输入、坏 JSON 落入 leftovers；
- clean_pdf_text：控制符 / 页码行 / 重复页眉清除，问句不被误删；
- _split_for_llm：按段落切块不切段落、超长段落硬切（优先换行处下刀）；
- llm_extract / llm_enrich / extract_questions_with_llm：走 FakeLLM 的三条 LLM 路径。
"""
import pytest

from agents import importer
from agents.importer import (
    SIMILARITY_THRESHOLD,
    _split_for_llm,
    clean_pdf_text,
    normalize_stack,
    parse_text,
    stem_similarity,
)


# ---------------------------------------------------------------------------
# stem_similarity
# ---------------------------------------------------------------------------

class TestStemSimilarity:
    def test_identical_returns_one(self):
        assert stem_similarity("什么是 Python 的 GIL？", "什么是 Python 的 GIL？") == 1.0

    def test_punctuation_and_case_ignored(self):
        """归一化去标点/空白/大小写后应判同。"""
        a = "什么是 Python 的 GIL？"
        b = "什么是python的gil"
        assert stem_similarity(a, b) == 1.0

    def test_empty_returns_zero(self):
        assert stem_similarity("", "任意题干") == 0.0
        assert stem_similarity("任意题干", "   ") == 0.0

    def test_completely_different_below_threshold(self):
        sim = stem_similarity("什么是 Python 的 GIL 全局解释器锁", "Vue3 的响应式原理是怎样实现的")
        assert sim < SIMILARITY_THRESHOLD, f"完全不同的题干相似度应低于阈值，实际 {sim}"

    def test_minor_edit_crosses_threshold(self):
        """长题干仅改个别字符，相似度应越过 0.85 阈值（判重）。"""
        a = "请详细解释 Python 中 GIL 的原理以及它对多线程性能的影响"
        b = "请详细解释 Python 中 GIL 的机制以及它对多线程性能的影响"  # 原理→机制
        sim = stem_similarity(a, b)
        assert sim >= SIMILARITY_THRESHOLD, f"微调字符后相似度应 >= 0.85，实际 {sim}"

    def test_short_single_char_normalized(self):
        """归一化后只剩 1 个字符：_bigrams 兜底不抛错。"""
        assert stem_similarity("锁", "锁") == 1.0


# ---------------------------------------------------------------------------
# normalize_stack
# ---------------------------------------------------------------------------

class TestNormalizeStack:
    @pytest.mark.parametrize("raw,expected", [
        ("Python", "python"), ("py", "python"), ("后端", "python"),
        ("Vue", "vue3"), ("VUE3", "vue3"), ("前端", "vue3"),
        ("大模型", "agent"), ("LLM", "agent"),
        ("MySQL", "database"), ("数据库", "database"),
    ])
    def test_aliases(self, raw, expected):
        assert normalize_stack(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "  ", "golang", "Java"])
    def test_unrecognized_returns_none(self, raw):
        assert normalize_stack(raw) is None


# ---------------------------------------------------------------------------
# parse_text
# ---------------------------------------------------------------------------

class TestParseText:
    def test_empty_input(self):
        assert parse_text("") == ([], [])
        assert parse_text("   \n  ") == ([], [])

    def test_full_labels(self):
        """带 答案：/技术栈：/知识点： 标签的完整题目。"""
        text = "什么是 GIL？\n答案：GIL 是全局解释器锁。\n技术栈：python\n知识点：GIL"
        items, leftovers = parse_text(text)
        assert leftovers == []
        assert len(items) == 1
        item = items[0]
        assert item["stem"] == "什么是 GIL？"
        assert item["answer"] == "GIL 是全局解释器锁。"
        assert item["tech_stack"] == "python"
        assert item["knowledge_point"] == "GIL"

    def test_answer_label_multiline(self):
        """答案：行之后到下一标签行之间的内容都算答案。"""
        text = "什么是 GIL？\n答案：第一行答案。\n第二行还是答案。\n技术栈：python"
        items, _ = parse_text(text)
        assert items[0]["answer"] == "第一行答案。\n第二行还是答案。"

    def test_english_and_halfwidth_labels(self):
        """英文 key + 半角冒号也要识别。"""
        text = "What is GIL?\nAnswer: Global Interpreter Lock.\ntech_stack: python"
        items, _ = parse_text(text)
        assert items[0]["answer"] == "Global Interpreter Lock."
        assert items[0]["tech_stack"] == "python"

    def test_missing_optional_fields(self):
        """缺答案/技术栈时条目仍解析出来，字段缺席交给后续补全。"""
        items, _ = parse_text("什么是装饰器？")
        assert len(items) == 1
        assert items[0]["stem"] == "什么是装饰器？"
        assert "answer" not in items[0]
        assert "tech_stack" not in items[0]

    def test_dash_separator_multiple_questions(self):
        """--- 分隔多题。"""
        text = "题目一是什么？\n答案：答案一。\n---\n题目二是什么？\n答案：答案二。"
        items, _ = parse_text(text)
        assert [i["stem"] for i in items] == ["题目一是什么？", "题目二是什么？"]

    def test_blank_line_separator(self):
        """空行分段也能拆出多题。"""
        text = "题目一是什么？\n答案：答案一。\n\n题目二是什么？\n答案：答案二。"
        items, _ = parse_text(text)
        assert len(items) == 2

    def test_json_array_input(self):
        text = '[{"question": "什么是 GIL？", "answer": "全局解释器锁", "tech_stack": "python"}]'
        items, leftovers = parse_text(text)
        assert leftovers == []
        assert items[0]["stem"] == "什么是 GIL？"
        assert items[0]["answer"] == "全局解释器锁"

    def test_json_input_skips_entries_without_stem(self):
        text = '[{"answer": "没有题干"}, {"stem": "有题干"}]'
        items, _ = parse_text(text)
        assert [i["stem"] for i in items] == ["有题干"]

    def test_broken_json_goes_to_leftovers(self):
        """形如 JSON 但解析失败：整体交给 LLM。"""
        text = '[{"question": " broken json"'
        items, leftovers = parse_text(text)
        assert items == []
        assert leftovers == [text]

    def test_unparseable_chunk_goes_to_leftovers(self):
        """没有任何题干内容的纯标签块进 leftovers。"""
        text = "题目是什么？\n\n答案：只有答案没有题干的那一行之前是空段"
        # 第一段可解析，第二段以标签行开头、无题干 -> leftovers
        items, leftovers = parse_text("正常题目是什么？\n\n答案：孤儿答案行")
        assert [i["stem"] for i in items] == ["正常题目是什么？"]
        assert leftovers == ["答案：孤儿答案行"]


# ---------------------------------------------------------------------------
# clean_pdf_text
# ---------------------------------------------------------------------------

class TestCleanPdfText:
    def test_control_chars_removed(self):
        text = "正常文字\x01\x0b\x1f\x7f保留\n换行\t制表符"
        cleaned = clean_pdf_text(text)
        assert "\x01" not in cleaned and "\x0b" not in cleaned and "\x7f" not in cleaned
        assert "正常文字保留" in cleaned
        assert "\n" in cleaned and "\t" in cleaned

    @pytest.mark.parametrize("page_line", ["12", "- 12 -", "第 12 页", "—— 3 ——"])
    def test_page_number_lines_removed(self, page_line):
        text = f"正文第一行\n{page_line}\n正文第二行"
        cleaned = clean_pdf_text(text)
        assert page_line not in cleaned
        assert "正文第一行" in cleaned and "正文第二行" in cleaned

    def test_repeated_header_removed(self):
        """重复 >=3 次的短行视为页眉被清除。"""
        header = "某某面试宝典"
        body = "什么是索引？"
        text = "\n".join([header, body, header, "答案是 B 树", header])
        cleaned = clean_pdf_text(text)
        assert header not in cleaned
        assert body in cleaned

    def test_repeated_question_not_removed(self):
        """以问号结尾的短行即使重复也不删（可能是真问题）。"""
        q = "什么是事务？"
        text = "\n".join([q, "答：...", q, "答：...", q])
        cleaned = clean_pdf_text(text)
        assert cleaned.count(q) == 3

    def test_twice_repeated_line_kept(self):
        """只重复 2 次的短行不算页眉。"""
        line = "本章小结"
        text = "\n".join([line, "内容一", line, "内容二"])
        assert clean_pdf_text(text).count(line) == 2


# ---------------------------------------------------------------------------
# _split_for_llm
# ---------------------------------------------------------------------------

class TestSplitForLlm:
    def test_short_text_single_chunk(self):
        text = "段落一\n\n段落二"
        chunks = _split_for_llm(text, max_chars=100)
        assert chunks == ["段落一\n\n段落二"]

    def test_paragraph_boundary_respected(self):
        """累积超限即封块：每个段落保持完整，不被从中间切开。"""
        paras = ["甲" * 30, "乙" * 30, "丙" * 30]
        text = "\n\n".join(paras)
        chunks = _split_for_llm(text, max_chars=70)
        assert len(chunks) == 2
        joined = "\n\n".join(chunks)
        for p in paras:
            assert p in joined, "段落必须完整出现在某个块中"

    def test_oversized_paragraph_hard_cut(self):
        """单段超长时硬切：每块长度 <= max_chars，内容不丢失。"""
        long_para = "字" * 250  # 无换行，只能硬切
        chunks = _split_for_llm(long_para, max_chars=100)
        assert all(len(c) <= 100 for c in chunks), f"硬切后块长超限：{[len(c) for c in chunks]}"
        assert "".join(chunks) == long_para, "硬切不能丢内容"

    def test_oversized_paragraph_prefers_newline_cut(self):
        """超长段落内优先在 max_chars 之前的换行处下刀（但换行点太靠前 <max_chars/2 时仍硬切）。"""
        # 换行在第 50 字（>= 80/2），第一刀应落在换行处
        para = "一" * 50 + "\n" + "二" * 100
        chunks = _split_for_llm(para, max_chars=80)
        assert chunks[0] == "一" * 50, "应优先在换行处下刀"
        assert "".join(chunks) == para.replace("\n", "", 1) or "二" * 100 in "".join(chunks)

    def test_newline_too_early_falls_back_to_hard_cut(self):
        """换行点位于 max_chars 前半段之内时不用它，直接按 max_chars 硬切（现状行为快照）。"""
        para = "一" * 30 + "\n" + "二" * 120  # 换行在第 30 字 < 80/2
        chunks = _split_for_llm(para, max_chars=80)
        assert len(chunks[0]) == 80

    def test_flush_pending_buffer_before_hard_cut(self):
        """硬切前有未封块的小段落：先封块再切大段。"""
        text = "小段落\n\n" + "长" * 250
        chunks = _split_for_llm(text, max_chars=100)
        assert chunks[0] == "小段落"

    def test_blank_paragraphs_skipped(self):
        chunks = _split_for_llm("甲\n\n\n\n乙", max_chars=100)
        assert chunks == ["甲\n\n乙"]


# ---------------------------------------------------------------------------
# LLM 路径（FakeLLM）
# ---------------------------------------------------------------------------

class TestLlmPaths:
    async def test_llm_extract(self, fake_llm):
        fake_llm.extract_items = [
            {"stem": "提取的题干", "answer": "提取的答案", "tech_stack": "python", "knowledge_point": "GIL"},
            {"stem": "  "},  # 无题干应被丢弃
        ]
        items = await importer.llm_extract(["无法解析的片段"])
        assert items == [
            {"stem": "提取的题干", "answer": "提取的答案", "tech_stack": "python", "knowledge_point": "GIL"}
        ]

    async def test_llm_extract_empty_chunks_no_call(self, fake_llm):
        assert await importer.llm_extract([]) == []
        assert fake_llm.calls == [], "空片段不应调用 LLM"

    async def test_llm_enrich_fills_missing_fields(self, fake_llm):
        items = [{"stem": "什么是 GIL？"}, {"stem": "完整题", "answer": "已有答案", "tech_stack": "python"}]
        marks = await importer.llm_enrich(items)
        assert items[0]["answer"], "缺答案的题应被补全"
        assert items[0]["tech_stack"] == "python"
        assert set(marks[0]["fields"]) >= {"answer", "tech_stack"}
        # 已有答案+技术栈的题不需要补全
        assert marks[1]["fields"] == []
        assert items[1]["answer"] == "已有答案"

    async def test_llm_enrich_no_call_when_nothing_missing(self, fake_llm):
        items = [{"stem": "完整题", "answer": "有", "tech_stack": "python"}]
        marks = await importer.llm_enrich(items)
        assert marks == [{"fields": []}]
        assert fake_llm.calls == []

    async def test_llm_enrich_custom_response(self, fake_llm):
        """测试可编程：自定义 enrich 返回（如 difficulty / keywords）。"""
        fake_llm.enrich_items = [
            {"index": 0, "answer": "定制答案", "tech_stack": "vue3", "keywords": ["响应式"], "difficulty": "hard"}
        ]
        items = [{"stem": "什么是响应式？"}]
        marks = await importer.llm_enrich(items)
        assert items[0]["tech_stack"] == "vue3"
        assert items[0]["difficulty"] == "hard"
        assert set(marks[0]["fields"]) == {"answer", "tech_stack", "keywords", "difficulty"}

    async def test_extract_questions_with_llm(self, fake_llm):
        """PDF 强制提取路径：清洗 -> 切块 -> 每块一次 LLM。"""
        fake_llm.pdf_items = [{"stem": "PDF 提取的题", "answer": "", "tech_stack": "database"}]
        items, errors = await importer.extract_questions_with_llm("第一章 介绍\n什么是索引？\n答：B 树。")
        assert errors == []
        assert items == [{"stem": "PDF 提取的题", "tech_stack": "database"}]
        assert len(fake_llm.calls) == 1

    async def test_extract_chunk_retries_on_bad_json(self, fake_llm, monkeypatch):
        """单块提取：第一次返回坏 JSON 时要求重出一次（第二次成功）。"""
        from llm import llm_router

        good = '[{"stem": "重试后提取的题"}]'
        responses = iter(["这不是 JSON", good])

        async def flaky_chat(messages, **kwargs):
            return "fake", next(responses)

        monkeypatch.setattr(llm_router, "chat", flaky_chat)
        items, error = await importer._extract_chunk_with_llm("原文", 1)
        assert error is None
        assert items == [{"stem": "重试后提取的题"}]

    async def test_extract_chunk_fails_after_two_bad_json(self, fake_llm, monkeypatch):
        """两次都返回坏 JSON：记入 error，不抛异常拖垮整体。"""
        from llm import llm_router

        async def bad_chat(messages, **kwargs):
            return "fake", "依然不是 JSON"

        monkeypatch.setattr(llm_router, "chat", bad_chat)
        items, error = await importer._extract_chunk_with_llm("原文", 2)
        assert items == []
        assert error is not None and "第 2 块" in error
