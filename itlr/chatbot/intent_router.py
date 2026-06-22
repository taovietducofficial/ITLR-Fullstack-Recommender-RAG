"""Định tuyến intent cho chatbot — phân loại câu hỏi + trích 'slot' (nghề, khái niệm,
kỹ năng đã học...) để gọi handler chuyên biệt.

Chạy SAU lớp hiểu truy vấn (sửa lỗi chính tả/viết tắt) và TRƯỚC truy hồi ngữ nghĩa:
nếu khớp một intent có giá trị cao (định nghĩa, so sánh, lộ trình nghề, kỹ năng còn
thiếu, học gì tiếp, ước lượng thời gian, thống kê), trả intent đó để chatbot soạn câu
trả lời định hướng; nếu không, trả (None, {}) để rơi về pipeline tìm tài nguyên hiện có.
"""

import re

from itlr.chatbot.knowledge_base import clean_known, extract_skills, find_career, find_concepts
from itlr.core.recommender import normalize_text, strip_accents


def _split_comparison(query):
    """Tách 2 thực thể trong câu so sánh: 'Java vs Python', 'so sánh MongoDB và PostgreSQL'."""
    s = normalize_text(query)
    s = re.sub(r"^.*?\bso sanh\b\s*", "", strip_accents(s))  # bỏ phần 'so sánh'
    parts = re.split(r"\s+(?:vs|versus|hay|va|with|hoac)\s+", s)
    parts = [p.strip(" ?.,") for p in parts if p.strip()]
    return parts[:2] if len(parts) >= 2 else []


def route_intent(query):
    """Trả (intent, slots). intent ∈ {admin_stat, skill_gap, next_skill, time_estimate,
    career_path, comparison, definition} hoặc None nếu không khớp -> dùng pipeline cũ."""
    q = strip_accents(normalize_text(query))
    career_key, _ = find_career(query)

    # 1) THỐNG KÊ / QUẢN TRỊ — "có bao nhiêu khóa học AI?", "tài liệu nào xem nhiều nhất?"
    if re.search(r"bao nhieu|thong ke|nhieu nhat|pho bien nhat|xem nhieu|goi y nhieu|"
                 r"top \d|hay nhat .* nao", q):
        return "admin_stat", {"raw": query}

    # 2) KỸ NĂNG CÒN THIẾU — "tôi còn thiếu gì để làm Data Engineer?"
    if career_key and re.search(r"con thieu|thieu gi|thieu ky nang|thieu nhung|con yeu|"
                                r"can bo sung|can hoc gi de|can gi de", q):
        return "skill_gap", {"career": career_key, "known": clean_known(extract_skills(query), career_key)}

    # 3) HỌC GÌ TIẾP — "đã học Python, OOP nên học gì tiếp?"
    if re.search(r"hoc gi tiep|hoc gi nua|hoc gi sau|tiep theo (nen )?hoc|sau do hoc gi|"
                 r"nen hoc gi (tiep|nua)|hoc tiep cai gi|buoc tiep theo", q):
        return "next_skill", {"known": extract_skills(query)}

    # 4) THỜI GIAN — "học Python mất bao lâu?", "bao lâu để thành Backend Developer?"
    if re.search(r"bao lau|mat bao lau|may thang|bao nhieu thang|bao nhieu lau|"
                 r"bao gio (thi )?(di lam|thanh|xong)", q):
        return "time_estimate", {
            "career": career_key,
            "concepts": find_concepts(query),
            "skills": extract_skills(query),
            "level": _detect_level(q),
        }

    # 5) LỘ TRÌNH NGHỀ — "tôi muốn trở thành Backend Developer", "roadmap DevOps"
    if career_key and re.search(r"muon tro thanh|tro thanh|muon lam|de lam|lam .*(developer|engineer|ky su)|"
                                r"lo trinh|roadmap|theo nghe|huong nghiep|developer|engineer|ky su", q):
        return "career_path", {"career": career_key, "known": clean_known(extract_skills(query), career_key)}

    # 6) SO SÁNH — "Java vs Python", "MongoDB khác PostgreSQL ở điểm nào?"
    if re.search(r"\bvs\b|\bversus\b|so sanh|khac nhau|khac gi|khac .* o diem|nen dung cai nao|"
                 r"\bhay\b .*\?", q):
        ents = _split_comparison(query)
        concs = find_concepts(query)
        if len(ents) == 2 or len(concs) >= 2:
            return "comparison", {"entities": ents, "concepts": concs[:2]}

    # 7) ĐỊNH NGHĨA / GIẢI THÍCH — "Machine Learning là gì?", "JWT hoạt động thế nào?",
    #    "Tại sao Microservices phổ biến?", "Khi nào nên dùng Redis?". Gated bởi có khái niệm
    #    được nhận diện -> không cướp các câu tìm tài nguyên ("Tìm tài liệu Python").
    if re.search(r"\bla gi\b|\bla nhu the nao\b|the nao la|nghia la gi|giai thich|"
                 r"khai niem|tim hieu ve|hieu the nao ve|\bwhat is\b|\bdinh nghia\b|"
                 r"hoat dong (nhu )?(the nao|ra sao)|\btai sao\b|vi sao|"
                 r"khi nao (nen )?dung|dung de lam gi|de lam gi", q):
        concs = find_concepts(query)
        if concs:
            return "definition", {"concept": concs[0]}

    return None, {}


def _detect_level(q_bare):
    if re.search(r"nang cao|advanced|chuyen sau", q_bare):
        return "nang cao"
    if re.search(r"trung cap|intermediate", q_bare):
        return "trung cap"
    return "co ban"


# Lọc theo nền tảng / miễn phí / trình độ — dùng làm slot phụ cho tìm tài nguyên.
FREE_PLATFORMS = {
    "youtube", "mdn", "freecodecamp", "kaggle", "kaggle learn", "geeksforgeeks",
    "google codelabs", "github skills", "docker docs", "kubernetes.io", "mit opencourseware",
    "leetcode", "hackerrank", "the odin project", "w3schools", "khan academy",
    "linux foundation", "cisco networking academy", "arduino",
}


def detect_filters(query):
    """Trích bộ lọc phụ: nền tảng cụ thể, chỉ-miễn-phí, trình độ. Trả dict (có thể rỗng)."""
    q = strip_accents(normalize_text(query))
    filters = {}
    if re.search(r"mien phi|free|khong mat phi|khong ton tien", q):
        filters["free"] = True
    for plat in ["coursera", "udemy", "youtube", "edx", "datacamp", "kaggle", "pluralsight",
                 "freecodecamp", "linkedin learning"]:
        if plat in q:
            filters["platform"] = plat
            break
    lvl = _detect_level(q)
    if re.search(r"co ban|nguoi moi|beginner|moi bat dau|tu dau|tu so 0|zero", q):
        filters["level"] = "Cơ bản"
    elif lvl == "trung cap":
        filters["level"] = "Trung cấp"
    elif lvl == "nang cao":
        filters["level"] = "Nâng cao"
    return filters
