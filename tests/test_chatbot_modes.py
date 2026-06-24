"""Chốt HÀNH VI định tuyến chế độ trả lời của chatbot (numpy/regex thuần -> chạy nhanh, hợp CI).

Mục tiêu: KHÓA hành vi đã thống nhất để không hồi quy:
  - Câu GIẢI THÍCH ("vì sao / như thế nào / là gì / để làm gì / lợi ích / ưu nhược") -> trả lời
    NGẮN trọng tâm (definition handler HOẶC ép mode="answer"), KHÔNG sinh lộ trình nhiều giai đoạn.
  - Câu LỘ TRÌNH / GỢI Ý / TÌM / SO SÁNH -> giữ đúng chế độ tương ứng (không bị ép về answer).
  - Câu KHUYÊN-CHỌN ("tư vấn lộ trình") -> vẫn ra lộ trình, KHÔNG bị nhầm là giải thích.

Chỉ test hàm thuần (detect_response_mode, _is_explanation_query, route_intent) — KHÔNG nạp model.
"""

import pytest

from itlr.chatbot.chatbot import _is_explanation_query, detect_response_mode
from itlr.chatbot.intent_router import route_intent
from itlr.core.recommender import strip_accents


def effective_mode(query):
    """Tái hiện quyết định chế độ trong EducationalChatbot.chat() cho nhánh KHÔNG dùng LLM:
    1) route_intent thắng trước (definition/comparison/career_path/...);
    2) nếu rơi xuống pipeline tài nguyên: câu giải thích -> 'answer', còn lại -> detect_response_mode.
    Trả 'intent:<name>' nếu một handler intent xử lý, ngược lại trả tên mode.
    """
    intent, _ = route_intent(query)
    if intent:
        return f"intent:{intent}"
    base = detect_response_mode(strip_accents(query).lower())
    return "answer" if _is_explanation_query(query) else base


# ── _is_explanation_query: nhận diện câu giải thích, loại trừ câu khuyên-chọn/so sánh ──
EXPLAIN_TRUE = [
    "vì sao machine learning cho người mới bắt đầu",
    "tại sao nên dùng Docker",
    "Kubernetes hoạt động như thế nào",
    "React dùng để làm gì",
    "lợi ích của machine learning là gì",
    "ưu nhược điểm của microservices",
    "khi nào nên dùng Redis",
    "giải thích cơ chế hoạt động của TCP",
    "bản chất của deep learning là gì",
    "khái niệm REST API",
]

EXPLAIN_FALSE = [
    "Lộ trình học Machine Learning từ cơ bản đến nâng cao",
    "Machine Learning cho người mới bắt đầu",
    "Gợi ý khóa học Docker cho người mới",
    "tư vấn lộ trình học Data Science",     # KHUYÊN-CHỌN: không phải giải thích
    "nên học khóa nào về AI",
    "tìm tài liệu về Kubernetes",
    "so sánh Java và Python",
]


@pytest.mark.parametrize("q", EXPLAIN_TRUE)
def test_explanation_detected(q):
    assert _is_explanation_query(q) is True


@pytest.mark.parametrize("q", EXPLAIN_FALSE)
def test_non_explanation_not_detected(q):
    assert _is_explanation_query(q) is False


# ── detect_response_mode: gồm 2 lỗ hổng cũ đã vá ("từ đầu" -> lộ trình, "có ... nào" -> tìm) ──
@pytest.mark.parametrize("q,expected", [
    ("Lộ trình học Python từ cơ bản đến nâng cao", "learning_path"),
    ("học Python từ đầu", "learning_path"),               # vá: trước đây ra "answer"
    ("có khóa học nào về Spark", "search"),                # vá: trước đây ra "answer"
    ("tìm tài liệu về Docker", "search"),
    ("so sánh React và Vue", "compare"),
    ("gợi ý khóa học phù hợp với tôi", "recommend"),
])
def test_detect_response_mode(q, expected):
    assert detect_response_mode(strip_accents(q).lower()) == expected


# ── Hành vi tổng hợp: câu giải thích KHÔNG BAO GIỜ ra chế độ lộ trình ──
@pytest.mark.parametrize("q", EXPLAIN_TRUE)
def test_explanation_never_learning_path(q):
    mode = effective_mode(q)
    assert mode != "learning_path"
    # phải là trả lời ngắn (definition handler) hoặc mode 'answer'
    assert mode in {"answer", "intent:definition", "intent:comparison"}


def test_why_beginner_query_not_roadmap():
    """Ca cụ thể người dùng báo lỗi: 'vì sao ... cho người mới bắt đầu' KHÔNG ra lộ trình."""
    q = "vì sao machine learning cho người mới bắt đầu"
    # detect_response_mode hiểu nhầm thành lộ trình vì có 'bắt đầu' ...
    assert detect_response_mode(strip_accents(q).lower()) == "learning_path"
    # ... nhưng quyết định cuối cùng phải là trả lời ngắn, không phải lộ trình.
    assert effective_mode(q) != "learning_path"


# ── Câu lộ trình / khuyên-chọn thật sự vẫn ra lộ trình ──
@pytest.mark.parametrize("q", [
    "Lộ trình học Machine Learning từ cơ bản đến nâng cao",
    "tư vấn lộ trình học Data Science",
])
def test_real_roadmap_preserved(q):
    # Câu lộ trình THẬT phải ra LỘ TRÌNH (không bị ép về 'answer'). Sau khi có kho vai trò
    # (it_roles.json), ML/Data Science map sang scaffold Data Scientist (career_path) — vẫn là
    # lộ trình có cấu trúc, KHÔNG phải giải thích ngắn.
    assert effective_mode(q) in {"learning_path", "intent:career_path"}
