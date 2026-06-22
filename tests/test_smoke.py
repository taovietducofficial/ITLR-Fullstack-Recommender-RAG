"""Smoke tests — chỉ kiểm logic thuần, KHÔNG cần artifacts/model nặng."""

import importlib

import pytest

MODULES = [
    "itlr.config", "itlr.core.recommender", "itlr.core.bm25", "itlr.core.rag",
    "itlr.chatbot.chatbot", "itlr.chatbot.intent_router", "itlr.chatbot.knowledge_base",
    "itlr.chatbot.query_understanding", "itlr.engine", "itlr.api.server",
]


@pytest.mark.parametrize("mod", MODULES)
def test_module_imports(mod):
    importlib.import_module(mod)


@pytest.mark.parametrize("query,expected", [
    ("Machine Learning là gì?", "definition"),
    ("Java vs Python", "comparison"),
    ("Tôi muốn trở thành Data Engineer", "career_path"),
    ("Tôi đã học Python, OOP nên học gì tiếp?", "next_skill"),
    ("Học Python mất bao lâu?", "time_estimate"),
    ("Có bao nhiêu khóa học AI?", "admin_stat"),
    ("Tìm tài liệu về Docker", None),       # rơi về pipeline tìm tài nguyên
])
def test_route_intent(query, expected):
    from itlr.chatbot.intent_router import route_intent
    intent, _ = route_intent(query)
    assert intent == expected


def test_category_detection_no_collision():
    """'khóa học' (course) KHÔNG được nhận nhầm thành 'Khoa học dữ liệu'."""
    from itlr.core.recommender import detect_category_from_query
    cats = ["Khoa học dữ liệu", "Trí tuệ nhân tạo", "Lập trình"]
    assert detect_category_from_query("khóa học Machine Learning", cats) == "Trí tuệ nhân tạo"
    assert detect_category_from_query("khóa học Python cơ bản", cats) == "Lập trình"


def test_skill_gap_and_next():
    from itlr.chatbot.knowledge_base import career_skill_gap, next_skills
    gap = career_skill_gap(["Python", "SQL"], "data engineer")
    assert "Spark" in gap and "Python" not in gap
    nxt = next_skills(["Python"])
    assert "OOP" in nxt


def test_glossary_loaded():
    """Từ điển khái niệm nạp từ file JSON, đủ lớn & toàn vẹn."""
    from itlr.chatbot.knowledge_base import CONCEPTS
    assert len(CONCEPTS) >= 150
    for c in CONCEPTS.values():
        assert c["name"] and c["def"]
        for r in c.get("related", []):
            assert r in CONCEPTS               # toàn vẹn tham chiếu


def test_find_concepts_specificity():
    """'sql injection' phải thắng 'sql' (alias dài/đặc trưng hơn)."""
    from itlr.chatbot.knowledge_base import find_concepts
    assert find_concepts("sql injection là gì")[0] == "sql_injection"
    assert find_concepts("machine learning là gì")[0] == "machine_learning"
