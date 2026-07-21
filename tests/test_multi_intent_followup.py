import os

os.environ.pop("OPENAI_API_KEY", None)
os.environ["USE_OLLAMA"] = "0"

from itlr.chatbot.chatbot import _resolve_followup, _route_multi

HIST = [
    {"role": "user", "content": "Docker là gì?"},
    {"role": "assistant", "content": "Docker là nền tảng container hóa..."},
]


def test_followup_borrows_concept():
    assert "docker" in _resolve_followup("nó dùng để làm gì?", HIST).lower()


def test_full_query_untouched():
    q = "Lương Backend Developer bao nhiêu?"
    assert _resolve_followup(q, HIST) == q


def test_no_history_untouched():
    assert _resolve_followup("nó dùng để làm gì?", []) == "nó dùng để làm gì?"


def test_multi_intent_split():
    got = _route_multi("Python là gì, so sánh với Java, và cho lộ trình học backend?")
    assert [i for i, _, _ in got] == ["definition", "comparison", "career_path"]


def test_single_comparison_not_split():
    assert _route_multi("so sánh Docker và Kubernetes") == []


def test_plain_search_not_split():
    assert _route_multi("tìm tài liệu về Docker và Kubernetes") == []


def test_single_question_not_split():
    assert _route_multi("Machine Learning là gì?") == []


def test_correction_followup_enriched():
    hist = [{"role": "user", "content": "so sánh python,c++,java"},
            {"role": "assistant", "content": "..."}]
    assert "so sánh" in _resolve_followup("thiếu c++ r", hist)


def test_three_way_comparison_routing():
    from itlr.chatbot.intent_router import route_intent
    intent, slots = route_intent("so sánh python,c++,java")
    assert intent == "comparison" and len(slots["concepts"]) == 3
