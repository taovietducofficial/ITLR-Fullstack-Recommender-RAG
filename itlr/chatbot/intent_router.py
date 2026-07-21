"""Định tuyến intent cho chatbot — phân loại câu hỏi + trích 'slot' (nghề, khái niệm,
kỹ năng đã học...) để gọi handler chuyên biệt.

Chạy SAU lớp hiểu truy vấn (sửa lỗi chính tả/viết tắt) và TRƯỚC truy hồi ngữ nghĩa:
nếu khớp một intent có giá trị cao (định nghĩa, so sánh, lộ trình nghề, kỹ năng còn
thiếu, học gì tiếp, ước lượng thời gian, thống kê), trả intent đó để chatbot soạn câu
trả lời định hướng; nếu không, trả (None, {}) để rơi về pipeline tìm tài nguyên hiện có.
"""

import re

from itlr.chatbot.knowledge_base import (
    clean_known,
    extract_skills,
    find_career,
    find_concepts,
    find_roadmap_field,
    find_role_key,
)
from itlr.core.recommender import normalize_text, strip_accents


def _split_comparison(query):
    """Tách 2 thực thể trong câu so sánh: 'Java vs Python', 'so sánh MongoDB và PostgreSQL'."""
    s = normalize_text(query)
    s = re.sub(r"^.*?\bso sanh\b\s*", "", strip_accents(s))
    parts = re.split(r"\s+(?:vs|versus|hay|va|with|hoac)\s+", s)
    parts = [p.strip(" ?.,") for p in parts if p.strip()]
    return parts[:2] if len(parts) >= 2 else []


_KNOWN_SIGNAL = re.compile(
    r"da hoc|da biet|biet roi|thanh thao|\bda co\b|hoc xong|nam vung|nam duoc|"
    r"co kinh nghiem|da nam|tung hoc|tung lam|da lam|dang biet"
)


def _known_skills(query, career_key):
    """Kỹ năng user ĐÃ CÓ — chỉ trích khi câu có tín hiệu sở hữu; ngược lại rỗng."""
    if not _KNOWN_SIGNAL.search(strip_accents(normalize_text(query))):
        return []
    return clean_known(extract_skills(query), career_key)


def route_intent(query):
    """Trả (intent, slots). intent ∈ {admin_stat, skill_gap, next_skill, time_estimate,
    career_path, comparison, definition} hoặc None nếu không khớp -> dùng pipeline cũ."""
    q = strip_accents(normalize_text(query))
    career_key, _ = find_career(query)

    if re.search(r"phong van|interview|cau hoi tuyen dung|khi di phong van|hoi gi khi phong van", q):
        role = find_role_key(query)
        if role:
            return "interview", {"role": role}

    if re.search(r"\bluong\b|muc luong|thu nhap|\bsalary\b|tra luong|luong bong", q):
        role = find_role_key(query)
        if role:
            return "salary", {"role": role}

    if re.search(r"(hop|phu hop).{0,15}(nghe|vai tro|nganh|cong viec)|"
                 r"nen (hoc|theo|chon|lam).{0,12}(nghe|nganh|vai tro) gi|"
                 r"\bchon nghe\b|toi nen lam (nghe )?gi", q):
        return "career_guidance", {}

    if re.search(r"khong biet (nen )?(hoc|bat dau|lam) gi|moi bat dau ma khong biet|"
                 r"moi vao nghe it|newbie.*khong biet", q) \
            and not find_role_key(query) and not find_concepts(query):
        return "career_guidance", {}

    if re.search(r"bao nhieu (khoa|tai lieu|muc|mon|loai|tai nguyen)|thong ke|nhieu nhat|"
                 r"pho bien nhat|xem nhieu|goi y nhieu|top \d|hay nhat .* nao", q):
        return "admin_stat", {"raw": query}

    if career_key and re.search(r"con thieu|thieu gi|thieu ky nang|thieu nhung|con yeu|"
                                r"can bo sung|can hoc gi de|can gi de", q):
        return "skill_gap", {"career": career_key, "known": _known_skills(query, career_key)}

    if re.search(r"hoc gi tiep|hoc gi nua|hoc gi sau|tiep theo (nen )?hoc|sau do hoc gi|"
                 r"nen hoc gi (tiep|nua)|hoc tiep cai gi|buoc tiep theo", q):
        return "next_skill", {"known": extract_skills(query)}

    if re.search(r"bao lau|mat bao lau|may thang|bao nhieu thang|bao nhieu lau|"
                 r"bao gio (thi )?(di lam|thanh|xong)", q):
        return "time_estimate", {
            "career": career_key,
            "concepts": find_concepts(query),
            "skills": extract_skills(query),
            "level": _detect_level(q),
        }

    if career_key and re.search(r"muon tro thanh|tro thanh|muon lam|de lam|lam .*(developer|engineer|ky su)|"
                                r"lo trinh|roadmap|theo nghe|huong nghiep|developer|engineer|ky su", q):
        return "career_path", {"career": career_key, "known": _known_skills(query, career_key)}

    roadmap_kw = re.search(r"lo trinh|roadmap|nhap mon|hoc tu dau|tu con so 0|tu co ban den", q)
    explain_kw = re.search(r"vi sao|tai sao|\bla gi\b|giai thich|nhu the nao|hoat dong|de lam gi", q)
    if roadmap_kw and not explain_kw:
        field_career = find_roadmap_field(query)
        if field_career:
            return "career_path", {"career": field_career,
                                   "known": _known_skills(query, field_career)}

    if re.search(r"\bvs\b|\bversus\b|so sanh|khac nhau|khac gi|khac .* o diem|nen dung cai nao|"
                 r"\bhay\b .*\?", q):
        ents = _split_comparison(query)
        concs = find_concepts(query)
        if len(ents) == 2 or len(concs) >= 2:
            return "comparison", {"entities": ents, "concepts": concs[:3]}

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
