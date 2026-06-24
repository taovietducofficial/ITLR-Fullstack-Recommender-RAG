"""Tri thức CNTT cấp sản phẩm cho chatbot — chạy OFFLINE, không cần LLM.

Gồm 4 phần, tất cả tiếng Việt:
  - CONCEPTS : giải thích khái niệm ("X là gì?") + chủ đề catalog để lấy tài nguyên.
  - CAREERS  : lộ trình nghề (milestones kỹ năng theo thứ tự) — Backend, AI, Data...
  - NEXT_SKILL: đồ thị "đã học X -> nên học tiếp" để gợi ý cá nhân hóa.
  - Hàm trợ giúp: nhận diện khái niệm/nghề/kỹ năng trong câu, tính kỹ năng còn thiếu,
    gợi ý kỹ năng tiếp theo, ước lượng thời gian học.

Phần "tài nguyên" luôn được kéo từ catalog thật (qua chatbot), KB chỉ cung cấp
phần định hướng/khái niệm mà dữ liệu khóa học không tự có.
"""

import json
from pathlib import Path

from itlr.core.recommender import normalize_text, strip_accents


def _key(text):
    return strip_accents(normalize_text(text))


# ───────────────────────── KHÁI NIỆM (nạp từ file dữ liệu) ─────────────────────────
# Giải thích khái niệm CNTT tách ra file dữ liệu riêng, dễ mở rộng/biên tập:
#   itlr/chatbot/data/it_glossary.json  (mỗi mục: name, aliases, category, level,
#   definition, topics, related, example). Loader giữ các khóa code cũ đang dùng
#   (name/aliases/def/topics) và bổ sung category/related/example cho câu trả lời giàu hơn.
_GLOSSARY_PATH = Path(__file__).resolve().parent / "data" / "it_glossary.json"


def _load_concepts(path=_GLOSSARY_PATH):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)["concepts"]
    out = {}
    for key, e in raw.items():
        out[key] = {
            "name": e["name"],
            "aliases": e.get("aliases", []),
            "def": e.get("definition", ""),
            "topics": e.get("topics", []),
            "category": e.get("category"),
            "level": e.get("level"),
            "related": e.get("related", []),
            "example": e.get("example"),
        }
    return out


CONCEPTS = _load_concepts()


# ───────────────────────── KHO VAI TRÒ (nạp từ file dữ liệu) ─────────────────────────
# Toàn bộ vai trò IT (lộ trình + phỏng vấn + lương + tư vấn chọn nghề) tách ra file dữ liệu:
#   itlr/chatbot/data/it_roles.json  — thêm vai trò = thêm mục JSON, KHÔNG sửa code.
# CAREERS được DỰNG từ ROLES để giữ tương thích code cũ (name, aliases, milestones=[(stage, skills)]).
_ROLES_PATH = Path(__file__).resolve().parent / "data" / "it_roles.json"


def _load_roles(path=_ROLES_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


_ROLES_DATA = _load_roles()
ROLES = _ROLES_DATA["roles"]                       # nguồn đầy đủ: description/roadmap/interview/salary
CAREER_GUIDANCE = _ROLES_DATA.get("career_guidance", [])  # [(sở thích, gợi ý vai trò)]

CAREERS = {
    key: {
        "name": r["name"],
        "aliases": r["aliases"],
        "milestones": [(s["stage"], s["skills"]) for s in r["roadmap"]],
    }
    for key, r in ROLES.items()
}



# ───────────────────────── ĐỒ THỊ "HỌC TIẾP" ─────────────────────────
# đã thạo kỹ năng (key) -> gợi ý học tiếp theo (theo thứ tự ưu tiên).
NEXT_SKILL = {
    "python": ["OOP", "SQL", "Git", "Data Structures"],
    "oop": ["Data Structures", "Design Pattern", "SQL"],
    "java": ["OOP", "Spring Boot", "SQL", "Data Structures"],
    "javascript": ["TypeScript", "React", "Node.js"],
    "html": ["CSS", "JavaScript"],
    "css": ["JavaScript", "React"],
    "react": ["TypeScript", "State Management", "Testing"],
    "sql": ["Database", "Data Warehouse", "ETL"],
    "database": ["MongoDB", "Redis", "Data Warehouse"],
    "data structures": ["Algorithms", "Dynamic Programming"],
    "git": ["CI/CD", "Docker"],
    "docker": ["Kubernetes", "CI/CD"],
    "machine learning": ["Deep Learning", "Scikit-learn", "Feature Engineering"],
    "deep learning": ["NLP", "Computer Vision", "PyTorch"],
    "etl": ["Airflow", "Spark", "Data Warehouse"],
    "spark": ["Kafka", "Data Lake"],
    "linux": ["Docker", "Networking", "Bash"],
    "networking": ["Web Security", "TCP/IP"],
}


# Phán xét ngắn cho các cặp so sánh kinh điển (key = frozenset token chuẩn hóa).
COMPARISONS = {
    frozenset({"java", "python"}): "**Python** dễ học, cú pháp ngắn, mạnh ở AI/Data & dựng nhanh; **Java** tĩnh kiểu, hiệu năng ổn định, mạnh ở hệ thống lớn/Android doanh nghiệp. → Mới bắt đầu hoặc làm AI/Data chọn Python; backend doanh nghiệp/Android chọn Java.",
    frozenset({"react", "angular"}): "**React** là thư viện UI linh hoạt, hệ sinh thái lớn, dễ bắt đầu; **Angular** là framework đầy đủ (TypeScript, DI, router) hợp dự án lớn cần khuôn khổ chặt. → Linh hoạt & cộng đồng chọn React; đội lớn cần chuẩn hóa chọn Angular.",
    frozenset({"mongodb", "postgresql"}): "**MongoDB** (NoSQL document) schema linh hoạt, mở rộng ngang; **PostgreSQL** (SQL quan hệ) nhất quán ACID mạnh, truy vấn phức tạp. → Dữ liệu linh hoạt chọn MongoDB; giao dịch/nhất quán chọn PostgreSQL.",
    frozenset({"mongodb", "mysql"}): "**MongoDB** lưu document linh hoạt, mở rộng ngang dễ; **MySQL** quan hệ, ACID, hợp dữ liệu có cấu trúc & giao dịch. → Schema thay đổi nhiều chọn MongoDB; cần nhất quán chọn MySQL.",
    frozenset({"docker", "vm"}): "**Docker** (container) chia sẻ kernel host nên nhẹ, khởi động trong giây; **VM** ảo hóa cả hệ điều hành nên nặng nhưng cô lập mạnh hơn. → Triển khai app/microservices chọn Docker; cần cô lập OS hoàn toàn chọn VM.",
    frozenset({"sql", "nosql"}): "**SQL** (quan hệ) schema chặt, ACID, truy vấn mạnh; **NoSQL** schema linh hoạt, mở rộng ngang, hợp dữ liệu phi cấu trúc/quy mô lớn. → Dữ liệu có cấu trúc/giao dịch chọn SQL; linh hoạt/quy mô lớn chọn NoSQL.",
}

# Bí danh -> token chuẩn để tra COMPARISONS.
_COMPARE_CANON = {
    "java": "java", "python": "python", "react": "react", "reactjs": "react",
    "angular": "angular", "angularjs": "angular", "vue": "vue",
    "mongodb": "mongodb", "mongo": "mongodb", "postgresql": "postgresql", "postgres": "postgresql",
    "mysql": "mysql", "docker": "docker", "container": "docker",
    "vm": "vm", "virtual machine": "vm", "may ao": "vm",
    "sql": "sql", "nosql": "nosql",
}


def canon_entity(text):
    """Quy một thực thể so sánh về token chuẩn (java/react/...) nếu nhận diện được."""
    q = _key(text)
    for alias in sorted(_COMPARE_CANON, key=len, reverse=True):
        if alias in q.split() or (" " in alias and alias in q):
            return _COMPARE_CANON[alias]
    return None


def comparison_verdict(a_text, b_text):
    """Phán xét cặp so sánh nếu nằm trong COMPARISONS, ngược lại None."""
    a, b = canon_entity(a_text), canon_entity(b_text)
    if a and b:
        return COMPARISONS.get(frozenset({a, b}))
    return None


def find_concepts(query):
    """Trả về list khái niệm (key CONCEPTS) được nhắc trong câu.

    Xếp hạng theo độ dài alias KHỚP DÀI NHẤT (đặc trưng hơn) -> 'sql injection' thắng
    'sql', để handler 'X là gì?' chọn đúng khái niệm cụ thể nhất.
    """
    # Chuẩn hóa ký hiệu trước khi bỏ dấu/dấu câu: "c++"->cpp, "c#"->csharp, để C/C++/C#
    # phân biệt được (normalize_text vốn bỏ '+'/'#' -> cả ba sẽ thành 'c').
    pre = str(query).lower().replace("c++", "cpp").replace("c#", "csharp")
    q = _key(pre)
    q_tokens = q.split()
    scored = []
    for key, info in CONCEPTS.items():
        best = 0
        for a in info["aliases"]:
            ka = _key(a)
            # cụm nhiều từ: khớp chuỗi con; từ đơn: khớp đúng token (tránh 'ai' dính 'training')
            hit = (ka in q) if " " in ka else (ka in q_tokens)
            if hit:
                best = max(best, len(ka))
        if best:
            scored.append((best, key))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [key for _, key in scored]


def safe_concepts(query, limit=4):
    """MỌI khái niệm khớp truy vấn một cách AN TOÀN (cùng quy tắc safe_concept_match nhưng
    trả NHIỀU key, theo thứ tự alias khớp dài nhất). Dùng để nêu khái niệm cho TẤT CẢ từ khóa
    CNTT trong câu (viết tắt/viết thường/viết hoa đều bắt được vì so khớp đã bỏ dấu + thường).

    Token đơn chỉ được tin khi alias >= 3 ký tự HOẶC truy vấn đúng MỘT từ -> tránh 'be'/'ai'
    trong câu nhiều từ bị nhận nhầm. Trả list key (có thể rỗng)."""
    pre = str(query).lower().replace("c++", "cpp").replace("c#", "csharp")
    qn = strip_accents(normalize_text(pre))
    toks = qn.split()
    if not toks:
        return []
    single = len(toks) == 1
    out = []
    for key in find_concepts(query):
        for a in sorted(CONCEPTS[key]["aliases"], key=len, reverse=True):
            ka = _key(a)
            hit = (ka in qn) if " " in ka else (ka in toks and (len(ka) >= 3 or single))
            if hit:
                out.append(key)
                break
        if len(out) >= limit:
            break
    return out


def safe_concept_match(query):
    """Khái niệm khớp truy vấn AN TOÀN (1 key tốt nhất) — bọc safe_concepts. Trả key hoặc None."""
    keys = safe_concepts(query, limit=1)
    return keys[0] if keys else None


def find_career(query):
    """Trả về (career_key, info) nếu câu nhắc một nghề, ngược lại (None, None)."""
    q = _key(query)
    best = None
    for key, info in CAREERS.items():
        for a in sorted(info["aliases"], key=len, reverse=True):
            if _key(a) in q:
                if best is None or len(a) > best[2]:
                    best = (key, info, len(a))
                break
    return (best[0], best[1]) if best else (None, None)


# LĨNH VỰC/viết tắt -> career_key, dùng cho câu LỘ TRÌNH khi find_career (khớp tên nghề) trượt
# ("lộ trình AI", "học web từ đầu", "lộ trình BA/QA"). Dựng từ field_aliases trong it_roles.json;
# find_roadmap_field khớp theo TỪ cho alias ngắn (an toàn hơn substring) -> 'ai' không dính 'email'.
FIELD_TO_CAREER = {key: r.get("field_aliases", []) for key, r in ROLES.items()}


def find_roadmap_field(query):
    """Khớp LĨNH VỰC trần (AI/web/data...) -> career_key scaffold gần nhất; None nếu không khớp.

    Khớp theo TỪ (token) cho alias 1 từ để 'ai' không dính 'training'/'email'; cụm nhiều từ khớp
    chuỗi con. Ưu tiên alias dài hơn (đặc trưng hơn). Chỉ nên gọi cho câu đã xác định là LỘ TRÌNH.
    """
    q = strip_accents(normalize_text(query))
    tok_list = q.split()
    toks = set(tok_list)
    # 'ba' nhập nhằng (Business Analyst vs số 3): bỏ nếu là 'ba <đơn vị>' ("ba tháng", "ba khóa").
    _ambig_unit = {"thang", "tuan", "nam", "ngay", "buoi", "gio", "khoa", "muc", "phan", "loai"}
    best = None  # (career_key, len)
    for career, terms in FIELD_TO_CAREER.items():
        for t in terms:
            tk = strip_accents(t)
            if " " in tk:
                hit = tk in q
            else:
                hit = tk in toks
                if hit and tk == "ba":
                    idx = tok_list.index("ba")
                    if idx + 1 < len(tok_list) and tok_list[idx + 1] in _ambig_unit:
                        hit = False
            if hit and (best is None or len(tk) > best[1]):
                best = (career, len(tk))
    return best[0] if best else None


def find_role_key(query):
    """Vai trò được nhắc trong câu (cho intent phỏng vấn/lương): ưu tiên tên nghề (find_career,
    khớp chuỗi con), rồi tới field alias (find_roadmap_field, khớp theo từ). None nếu không có."""
    key, _ = find_career(query)
    return key or find_roadmap_field(query)


def role_interview(key):
    return (ROLES.get(key) or {}).get("interview", [])


def role_salary(key):
    return (ROLES.get(key) or {}).get("salary", [])


def role_description(key):
    return (ROLES.get(key) or {}).get("description", "")


def role_roadmap(key):
    """Roadmap đầy đủ [{stage, duration, skills}] để handler hiển thị kèm thời lượng."""
    return (ROLES.get(key) or {}).get("roadmap", [])


# Vốn kỹ năng nhận diện được = mọi kỹ năng trong CAREERS + tên khái niệm + NEXT_SKILL.
def _build_skill_vocab():
    vocab = {}
    def add(name):
        vocab[_key(name)] = name
    for info in CAREERS.values():
        for _, skills in info["milestones"]:
            for s in skills:
                add(s)
    for info in CONCEPTS.values():
        add(info["name"].split("(")[0].strip())
        for a in info["aliases"]:
            vocab.setdefault(_key(a), info["name"].split("(")[0].strip())
    for k, outs in NEXT_SKILL.items():
        vocab.setdefault(_key(k), k.upper() if len(k) <= 3 else k.title())
        for o in outs:
            vocab.setdefault(_key(o), o)
    return vocab

SKILL_VOCAB = _build_skill_vocab()


def extract_skills(text):
    """Nhận diện các kỹ năng người dùng nêu (đã học / đang có) trong câu/hồ sơ."""
    q = _key(text)
    out, seen = [], set()
    for ka, name in sorted(SKILL_VOCAB.items(), key=lambda x: len(x[0]), reverse=True):
        hit = (ka in q) if " " in ka else (ka in q.split())
        if hit and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def clean_known(known, career_key=None):
    """Bỏ khỏi danh sách 'đã học' những từ thực ra là TÊN NGHỀ (vd 'Backend' trong
    'trở thành Backend Developer') để không đánh dấu nhầm là kỹ năng đã có."""
    if not career_key:
        return list(dict.fromkeys(known))
    bad = set()
    for a in CAREERS[career_key]["aliases"]:
        bad.update(_key(a).split())
    return [k for k in dict.fromkeys(known) if _key(k) not in bad]


def career_skill_gap(known, career_key):
    """Kỹ năng CÒN THIẾU để theo nghề, giữ thứ tự lộ trình. known: iterable tên kỹ năng."""
    known_keys = {_key(k) for k in known}
    gap = []
    for _, skills in CAREERS[career_key]["milestones"]:
        for s in skills:
            if _key(s) not in known_keys and s not in gap:
                gap.append(s)
    return gap


def next_skills(known, limit=6):
    """Gợi ý kỹ năng học tiếp dựa trên đồ thị NEXT_SKILL từ những gì đã học."""
    known_keys = {_key(k) for k in known}
    out, seen = [], set(known_keys)
    for k in known:
        for nxt in NEXT_SKILL.get(_key(k), []):
            if _key(nxt) not in seen:
                seen.add(_key(nxt))
                out.append(nxt)
    return out[:limit]


# ───────────────────────── ƯỚC LƯỢNG THỜI GIAN ─────────────────────────
# giờ học điển hình theo cấp độ (tự học ~10h/tuần).
_HOURS_BY_LEVEL = {"co ban": 50, "trung cap": 100, "nang cao": 160}


def estimate_skill_time(level_text="co ban"):
    lv = strip_accents(str(level_text)).strip().lower()
    hours = _HOURS_BY_LEVEL.get(lv, 80)
    weeks = round(hours / 10)
    return hours, weeks


def estimate_career_time(career_key):
    """Tổng ước lượng cho cả lộ trình nghề: (giờ, tháng) — dạng khoảng."""
    n_skills = sum(len(s) for _, s in CAREERS[career_key]["milestones"])
    hours = n_skills * 35  # ~35h/kỹ năng trung bình
    months_low = round(hours / 12 / 4.3)   # ~12h/tuần
    months_high = round(hours / 8 / 4.3)   # ~8h/tuần
    return hours, months_low, months_high
