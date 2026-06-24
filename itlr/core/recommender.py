"""Shared preprocessing, retrieval, and recommendation logic (tuned v2)."""

import re
import unicodedata

import numpy as np
from nltk.stem.porter import PorterStemmer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

STEMMER = PorterStemmer()

# Ngưỡng tuyệt đối cho điểm hybrid (max của kênh embeddings & char n-gram).
# Đo lại trên dataset 50k mới: off-topic tiếng Việt (kể cả "cách nấu phở"=0.474,
# "học tiếng anh"=0.460) <= ~0.48; truy vấn IT tiếng Việt >= 0.61, token IT tiếng Anh
# thấp nhất (git) = 0.506. 0.48 nằm trong khoảng trống -> ưu tiên CHẶN off-topic mạnh
# (theo yêu cầu) mà vẫn giữ git/css/sql... và viết tắt (đã mở rộng -> điểm cao).
ABS_RELEVANCE_GATE = 0.48   # điểm cao nhất < ngưỡng này -> ngoài lĩnh vực -> không hiện gì
ABS_ITEM_FLOOR = 0.42       # mục dưới sàn này coi như không liên quan (cắt phần nhiễu)

# Hiệu chỉnh "% phù hợp" hiển thị. Điểm thô (cosine/char) được chuẩn hóa theo truy vấn
# (score/best) rồi ánh xạ qua đường cong lõm vào dải tin cậy cao: mục THỰC SỰ liên quan
# đọc lên 90-100%, đúng kỳ vọng người dùng, trong khi THỨ TỰ xếp hạng vẫn theo điểm thô.
CONFIDENCE_FLOOR = 0.90     # mục trong-lĩnh-vực kém nhất vẫn hiển thị ~90%
CONFIDENCE_BAND_LO = 0.50   # norm <= mức này coi như đáy dải hiển thị


def calibrate_confidence(norm):
    """Ánh xạ norm = score/best (trong [0,1]) -> % hiển thị trong [CONFIDENCE_FLOOR, 1.0].

    Dùng đường cong lõm (t**0.7) để mục đầu bảng rõ ràng đạt ~100% còn các mục liên quan
    còn lại vẫn neo trên ~90%. Không thay đổi thứ tự — chỉ chuẩn hóa con số hiển thị.
    """
    t = (float(norm) - CONFIDENCE_BAND_LO) / (1.0 - CONFIDENCE_BAND_LO)
    t = min(1.0, max(0.0, t))
    return CONFIDENCE_FLOOR + (1.0 - CONFIDENCE_FLOOR) * (t ** 0.7)

STOP_WORDS = {
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for", "with",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may", "might",
    "this", "that", "these", "those", "it", "its", "from", "by", "as", "into",
    "through", "during", "before", "after", "above", "below", "between",
    "va", "voi", "trong", "cho", "cac", "cua", "mot", "nhung", "duoc", "la",
    "co", "khong", "den", "tu", "theo", "tren", "duoi", "nay", "do", "khi",
    "ban", "hoc", "khoa", "tai", "lieu", "huong", "dan", "giao", "trinh",
    "thuc", "hanh", "nang", "cao", "linh", "vuc", "gi", "nao", "ve", "cua",
    "toi", "muon", "can", "hay", "giup", "xin", "cho", "xin",
}

QUERY_STOP_WORDS = STOP_WORDS | {
    "goi", "y", "tim", "kiem", "nen", "tu", "van", "lo", "trinh", "co",
    "recommend", "search", "find", "show", "list", "best", "top",
}

# Related category groups for partial category bonus
RELATED_CATEGORIES = {
    "lập trình": {"lập trình web", "lập trình mobile", "công cụ lập trình"},
    "lập trình web": {"lập trình", "lập trình mobile"},
    "lập trình mobile": {"lập trình", "lập trình web"},
    "trí tuệ nhân tạo": {"khoa học dữ liệu", "công nghệ mới"},
    "khoa học dữ liệu": {"trí tuệ nhân tạo", "cơ sở dữ liệu"},
    "devops": {"điện toán đám mây", "kiểm thử phần mềm"},
    "điện toán đám mây": {"devops", "an ninh mạng"},
    "an ninh mạng": {"mạng máy tính", "điện toán đám mây"},
    "mạng máy tính": {"an ninh mạng"},
    "cơ sở dữ liệu": {"khoa học dữ liệu"},
}

# Tunable fusion weights (optimized for educational catalog)
SCORE_WEIGHTS = {
    "tfidf": 0.42,
    "bm25": 0.18,
    "category": 0.14,
    "topic_jaccard": 0.12,
    "topic_contain": 0.06,
    "title_overlap": 0.05,
    "type_match": 0.03,
}

HYBRID_ITEM_WEIGHTS = {
    "cosine": 0.52,
    "category": 0.20,
    "topic_jaccard": 0.13,
    "topic_contain": 0.08,
    "type_match": 0.04,
    "title_overlap": 0.03,
}


def normalize_text(text):
    text = unicodedata.normalize("NFC", str(text).lower())
    text = re.sub(r"[^\w\sÀ-ỹ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_accents(text):
    """Bỏ dấu tiếng Việt + lowercase (đ->d). Dùng cho khớp ký tự chịu lỗi chính tả/thiếu dấu."""
    text = str(text).lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


# Gộp các TỪ LẶP liên tiếp do dịch máy lỗi: "kỹ thuật thuật thuật toán" -> "kỹ thuật toán".
# \w (Unicode) bắt cả chữ tiếng Việt; backreference \1 + re.I gộp không phân biệt hoa thường.
_REPEAT_WORD_RE = re.compile(r"\b(\w+)(\s+\1\b)+", re.IGNORECASE | re.UNICODE)
# Bỏ KHOẢNG TRẮNG THỪA trước dấu câu. Tách riêng dấu chấm: CHỈ bỏ cách trước '.' khi nó là dấu
# chấm KẾT câu (theo sau là khoảng trắng/hết chuỗi) -> KHÔNG phá " .NET" / " .js" (theo sau là chữ).
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,;:!?])")
_SPACE_BEFORE_PERIOD_RE = re.compile(r"\s+\.(?=\s|$)")
# Thêm cách SAU dấu phẩy/chấm-phẩy/hai-chấm dính chữ: "câu,Xác" -> "câu, Xác" (số thập phân an toàn
# vì yêu cầu CHỮ cái ngay sau, không phải chữ số).
_SPACE_AFTER_COMMA_RE = re.compile(r"([,;:])(?=[A-Za-zÀ-ỹ])")
# Tách CÂU bị dính: <chữ thường>.<Chữ HOA + thường> -> thêm cách. Lookbehind 2 ký tự thường +
# yêu cầu sau dấu chấm là Hoa-rồi-thường (một từ viết hoa bình thường) nên KHÔNG đụng ".NET",
# ".JS", từ viết tắt toàn hoa, hay phần mở rộng file.
_SENTENCE_GLUE_RE = re.compile(r"(?<=[a-zà-ỹ]{2})([.!?])(?=[A-ZÀ-Ỹ][a-zà-ỹ])")


def clean_display_text(text):
    """Làm sạch mô tả/tiêu đề catalog cho HIỂN THỊ (sửa lỗi DỊCH MÁY an toàn, không viết lại câu):
    gộp từ lặp liên tiếp, sửa khoảng trắng quanh dấu câu, tách câu bị dính, viết hoa chữ đầu.
    KHÔNG đụng truy hồi/chấm điểm (chỉ áp ở tầng hiển thị)."""
    s = _REPEAT_WORD_RE.sub(r"\1", str(text))
    s = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", s)
    s = _SPACE_BEFORE_PERIOD_RE.sub(".", s)
    s = _SPACE_AFTER_COMMA_RE.sub(r"\1 ", s)
    s = _SENTENCE_GLUE_RE.sub(r"\1 ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[0].upper() + s[1:] if s else s


def clean_link(link):
    """Chỉ giữ link http(s) hợp lệ; placeholder ('Đang cập nhật') / rỗng -> '' để KHÔNG render
    link hỏng (`[Mở tài nguyên](Đang cập nhật)`)."""
    s = str(link).strip()
    return s if s.lower().startswith(("http://", "https://")) else ""


def maybe_stem(token):
    if token.isascii() and token.isalpha():
        return STEMMER.stem(token)
    return token


def tokenize(text):
    tokens = []
    for raw in normalize_text(text).split():
        token = maybe_stem(raw)
        if len(token) > 1 and token not in STOP_WORDS:
            tokens.append(token)
    bigrams = [f"{tokens[i]}_{tokens[i + 1]}" for i in range(len(tokens) - 1)]
    trigrams = [f"{tokens[i]}_{tokens[i + 1]}_{tokens[i + 2]}" for i in range(len(tokens) - 2)]
    return tokens + bigrams + trigrams


def extract_query_tokens(query):
    return [
        maybe_stem(t)
        for t in normalize_text(query).split()
        if len(t) > 2 and t not in QUERY_STOP_WORDS
    ]


def remove_space(items):
    return [item.replace(" ", "") for item in items]


def repeat(items, times):
    return items * times


def build_field_corpus(items, field):
    """Build corpus for a specific field with tuned weighting."""
    corpus = []
    for _, row in items.iterrows():
        if field == "title":
            tokens = repeat(remove_space(normalize_text(row["title"]).split()), 6)
        elif field == "topics":
            topics = [t.strip() for t in str(row["topics"]).split(",")]
            tokens = repeat(remove_space([normalize_text(t) for t in topics]), 5)
        elif field == "category":
            tokens = repeat(remove_space([row["category"]]), 4)
        else:
            title = remove_space(normalize_text(row["title"]).split())
            description = normalize_text(row["description"]).split()
            category = remove_space([row["category"]])
            topics = remove_space([t.strip() for t in str(row["topics"]).split(",")])
            item_type = remove_space([row["type"]])
            instructor = normalize_text(row["instructor"]).split()
            platform = normalize_text(row["platform"]).split()
            tokens = (
                repeat(title, 6)
                + repeat(topics, 5)
                + repeat(category, 4)
                + repeat(description, 2)
                + repeat(item_type, 2)
                + repeat(instructor, 1)
                + repeat(platform, 1)
            )
        corpus.append(" ".join(tokens))
    return corpus


def tags_to_corpus(items):
    return build_field_corpus(items, "full")


def create_vectorizer():
    return TfidfVectorizer(
        analyzer=tokenize,
        max_features=12000,
        min_df=1,
        max_df=0.88,
        sublinear_tf=True,
        norm="l2",
    )


def compute_similarity(tfidf_matrix):
    return cosine_similarity(tfidf_matrix)


def parse_topics(topics_str):
    return {normalize_text(t) for t in str(topics_str).split(",") if t.strip()}


def topic_jaccard(topics_a, topics_b):
    if not topics_a or not topics_b:
        return 0.0
    union = topics_a | topics_b
    return len(topics_a & topics_b) / len(union)


def topic_containment(query_topics, item_topics):
    """Fraction of query topics found in item topics."""
    if not query_topics:
        return 0.0
    return len(query_topics & item_topics) / len(query_topics)


def title_keyword_overlap(query, title):
    q_tokens = set(extract_query_tokens(query))
    title_norm = normalize_text(title)
    if not q_tokens:
        return 0.0
    hits = sum(1 for t in q_tokens if t in title_norm)
    return hits / len(q_tokens)


def category_bonus(cat_a, cat_b):
    """Exact or related category match score in [0, 1]."""
    if cat_a == cat_b:
        return 1.0
    norm_a = normalize_text(cat_a)
    norm_b = normalize_text(cat_b)
    related = RELATED_CATEGORIES.get(norm_a, set())
    if norm_b in related or norm_a in RELATED_CATEGORIES.get(norm_b, set()):
        return 0.55
    tokens_a = set(norm_a.split())
    tokens_b = set(norm_b.split())
    overlap = len(tokens_a & tokens_b)
    if overlap >= 2:
        return 0.35
    if overlap == 1:
        return 0.15
    return 0.0


def hybrid_score(cosine, same_category, topics_a, topics_b):
    """Legacy hybrid score — delegates to v2."""
    cat_score = 1.0 if same_category else 0.0
    return hybrid_score_v2(
        cosine=cosine,
        category_score=cat_score,
        topics_a=topics_a,
        topics_b=topics_b,
    )


def hybrid_score_v2(
    cosine,
    category_score=0.0,
    topics_a=None,
    topics_b=None,
    type_match=0.0,
    title_overlap=0.0,
    query_topics=None,
):
    """Tuned multi-signal hybrid score for item-item and query-item ranking."""
    topics_a = topics_a or set()
    topics_b = topics_b or set()
    jaccard = topic_jaccard(topics_a, topics_b)
    contain = topic_containment(query_topics or topics_a, topics_b)

    w = HYBRID_ITEM_WEIGHTS
    score = (
        w["cosine"] * cosine
        + w["category"] * category_score
        + w["topic_jaccard"] * jaccard
        + w["topic_contain"] * contain
        + w["type_match"] * type_match
        + w["title_overlap"] * title_overlap
    )
    return min(score, 1.0)


def query_item_score(
    tfidf_score,
    bm25_score,
    query,
    row,
    item_type_filter=None,
):
    """Tuned multi-signal score for query → item retrieval."""
    q_topics = set(extract_query_tokens(query))
    row_topics = parse_topics(row["topics"])
    cat = category_bonus(
        detect_category_from_query(query, [row["category"]]) or "",
        row["category"],
    ) if detect_category_from_query(query, [row["category"]]) else 0.0

    type_match = 0.0
    if item_type_filter and row["type"] == item_type_filter:
        type_match = 1.0

    title_ov = title_keyword_overlap(query, row["title"])
    jaccard = topic_jaccard(q_topics, row_topics)
    contain = topic_containment(q_topics, row_topics)

    w = SCORE_WEIGHTS
    score = (
        w["tfidf"] * tfidf_score
        + w["bm25"] * bm25_score
        + w["category"] * cat
        + w["topic_jaccard"] * jaccard
        + w["topic_contain"] * contain
        + w["title_overlap"] * title_ov
        + w["type_match"] * type_match
    )
    return min(score, 1.0)


# Ánh xạ TỪ KHÓA (đã bỏ dấu, viết thường) -> ĐÚNG tên chuyên mục trong catalog.
# Cần thiết vì tên chuyên mục là tiếng Việt nhưng người dùng hay gõ thuật ngữ tiếng Anh
# ("machine learning", "docker"...) -> khớp theo tên thuần túy sẽ trượt. Đây là TÍN HIỆU
# MẠNH, ưu tiên hơn khớp tên. Cụm nhiều từ (có dấu cách) khớp theo chuỗi con; từ đơn
# khớp đúng token (để "java" không dính "javascript").
KEYWORD_CATEGORY = {
    # Trí tuệ nhân tạo / Machine Learning
    "machine learning": "Trí tuệ nhân tạo", "deep learning": "Trí tuệ nhân tạo",
    "hoc may": "Trí tuệ nhân tạo", "hoc sau": "Trí tuệ nhân tạo",
    "neural network": "Trí tuệ nhân tạo", "mang neuron": "Trí tuệ nhân tạo",
    "tri tue nhan tao": "Trí tuệ nhân tạo", "artificial intelligence": "Trí tuệ nhân tạo",
    "computer vision": "Trí tuệ nhân tạo", "thi giac may tinh": "Trí tuệ nhân tạo",
    "tensorflow": "Trí tuệ nhân tạo", "pytorch": "Trí tuệ nhân tạo",
    "keras": "Trí tuệ nhân tạo", "scikit": "Trí tuệ nhân tạo",
    "transformer": "Trí tuệ nhân tạo", "nlp": "Trí tuệ nhân tạo",
    # MLOps & AI Engineering
    "mlops": "MLOps & AI Engineering", "ai engineering": "MLOps & AI Engineering",
    # Khoa học dữ liệu
    "data science": "Khoa học dữ liệu", "khoa hoc du lieu": "Khoa học dữ liệu",
    "phan tich du lieu": "Khoa học dữ liệu", "data analysis": "Khoa học dữ liệu",
    "pandas": "Khoa học dữ liệu", "truc quan hoa": "Khoa học dữ liệu",
    # Dữ liệu lớn
    "big data": "Dữ liệu lớn", "du lieu lon": "Dữ liệu lớn",
    "spark": "Dữ liệu lớn", "hadoop": "Dữ liệu lớn", "kafka": "Dữ liệu lớn",
    # DevOps
    "devops": "DevOps", "docker": "DevOps", "kubernetes": "DevOps",
    "ci cd": "DevOps", "jenkins": "DevOps", "terraform": "DevOps", "ansible": "DevOps",
    # Điện toán đám mây
    "dien toan dam may": "Điện toán đám mây", "cloud computing": "Điện toán đám mây",
    "serverless": "Điện toán đám mây",
    # An ninh mạng
    "an ninh mang": "An ninh mạng", "bao mat": "An ninh mạng",
    "cybersecurity": "An ninh mạng", "security": "An ninh mạng",
    "pentest": "An ninh mạng", "penetration testing": "An ninh mạng", "owasp": "An ninh mạng",
    # Lập trình Web
    "lap trinh web": "Lập trình Web", "frontend": "Lập trình Web", "backend": "Lập trình Web",
    "react": "Lập trình Web", "angular": "Lập trình Web", "django": "Lập trình Web",
    "flask": "Lập trình Web",
    # Lập trình Mobile
    "lap trinh mobile": "Lập trình Mobile", "android": "Lập trình Mobile",
    "ios": "Lập trình Mobile", "flutter": "Lập trình Mobile", "react native": "Lập trình Mobile",
    # Cơ sở dữ liệu
    "co so du lieu": "Cơ sở dữ liệu", "database": "Cơ sở dữ liệu",
    "mongodb": "Cơ sở dữ liệu", "postgresql": "Cơ sở dữ liệu", "mysql": "Cơ sở dữ liệu",
    # Cấu trúc dữ liệu & Giải thuật
    "cau truc du lieu": "Cấu trúc dữ liệu & Giải thuật", "giai thuat": "Cấu trúc dữ liệu & Giải thuật",
    "thuat toan": "Cấu trúc dữ liệu & Giải thuật", "algorithm": "Cấu trúc dữ liệu & Giải thuật",
    "data structure": "Cấu trúc dữ liệu & Giải thuật",
    # Mạng máy tính
    "mang may tinh": "Mạng máy tính", "networking": "Mạng máy tính",
    # Kiểm thử phần mềm
    "kiem thu": "Kiểm thử phần mềm", "testing": "Kiểm thử phần mềm",
    "automation test": "Kiểm thử phần mềm",
    # Thiết kế UI/UX
    "ui ux": "Thiết kế UI/UX", "thiet ke giao dien": "Thiết kế UI/UX", "figma": "Thiết kế UI/UX",
    # Blockchain & Web3
    "blockchain": "Blockchain & Web3", "web3": "Blockchain & Web3",
    "ethereum": "Blockchain & Web3", "smart contract": "Blockchain & Web3",
    # IoT & Hệ thống nhúng
    "iot": "IoT & Hệ thống nhúng", "he thong nhung": "IoT & Hệ thống nhúng",
    "embedded": "IoT & Hệ thống nhúng", "arduino": "IoT & Hệ thống nhúng",
    # Quản trị hệ thống & Linux
    "linux": "Quản trị hệ thống & Linux", "quan tri he thong": "Quản trị hệ thống & Linux",
    "sysadmin": "Quản trị hệ thống & Linux",
    # Quản lý dự án CNTT
    "quan ly du an": "Quản lý dự án CNTT", "project management": "Quản lý dự án CNTT",
    "agile": "Quản lý dự án CNTT", "scrum": "Quản lý dự án CNTT",
    # AR/VR & Thực tế ảo
    "ar vr": "AR/VR & Thực tế ảo", "thuc te ao": "AR/VR & Thực tế ảo",
    "virtual reality": "AR/VR & Thực tế ảo",
    # Đồ họa máy tính
    "do hoa may tinh": "Đồ họa máy tính", "computer graphics": "Đồ họa máy tính", "opengl": "Đồ họa máy tính",
    # Phân tích nghiệp vụ (BA)
    "phan tich nghiep vu": "Phân tích nghiệp vụ (BA)", "business analyst": "Phân tích nghiệp vụ (BA)",
    # Điện toán lượng tử
    "luong tu": "Điện toán lượng tử", "quantum": "Điện toán lượng tử",
    # Phát triển Game
    "phat trien game": "Phát triển Game", "game development": "Phát triển Game",
    "unity": "Phát triển Game", "unreal": "Phát triển Game",
    # Khoa học máy tính
    "khoa hoc may tinh": "Khoa học máy tính", "computer science": "Khoa học máy tính",
    # Kỹ thuật phần mềm
    "ky thuat phan mem": "Kỹ thuật phần mềm", "software engineering": "Kỹ thuật phần mềm",
    "design pattern": "Kỹ thuật phần mềm",
    # Lập trình (tổng quát / ngôn ngữ)
    "lap trinh": "Lập trình", "python": "Lập trình", "golang": "Lập trình", "rust": "Lập trình",
}


def detect_category_from_query(query, categories):
    """Khớp truy vấn với chuyên mục catalog phù hợp nhất.

    Hai tầng:
      1) Bản đồ từ khóa (KEYWORD_CATEGORY) — tín hiệu mạnh, bắt được cả thuật ngữ
         tiếng Anh ("machine learning", "docker") mà tên chuyên mục tiếng Việt không chứa.
      2) Khớp token tên chuyên mục TRONG KHÔNG GIAN ĐÃ BỎ DẤU và đã LỌC STOPWORD.
         Bỏ dấu + lọc stopword là bắt buộc: nếu không, chữ "học" trong "khóa học" (course)
         sẽ trùng "học" trong "Khoa học dữ liệu"/"Khoa học máy tính" -> nhận nhầm chuyên mục.
    """
    cat_set = set(categories)
    bare = strip_accents(normalize_text(query))
    q_tokens_bare = set(bare.split())

    # 1) Bản đồ từ khóa (ưu tiên) — chấm điểm theo số cụm khớp, cụm dài thắng.
    cat_score = {}
    for phrase, cat in KEYWORD_CATEGORY.items():
        if cat not in cat_set:
            continue
        hit = (phrase in bare) if " " in phrase else (phrase in q_tokens_bare)
        if hit:
            cat_score[cat] = cat_score.get(cat, 0) + (2 if " " in phrase else 1) + len(phrase) / 100.0
    if cat_score:
        return max(cat_score, key=cat_score.get)

    # 2) Khớp tên chuyên mục — bỏ dấu hai phía, loại stopword bên truy vấn.
    query_tokens = {t for t in q_tokens_bare if t not in QUERY_STOP_WORDS}
    if not query_tokens:
        return None

    best_category, best_score = None, 0
    for category in categories:
        cat_bare = strip_accents(normalize_text(category))
        cat_tokens = set(cat_bare.split())
        overlap = len(cat_tokens & query_tokens)
        if len(cat_bare) > 3 and cat_bare in bare:
            overlap += 4
        for token in query_tokens:
            if len(token) > 3 and token in cat_bare:
                overlap += 1
        if overlap > best_score:
            best_score = overlap
            best_category = category

    return best_category if best_score > 0 else None


def reciprocal_rank_fusion(rankings, k=60):
    """Fuse multiple ranked lists using RRF."""
    scores = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def mmr_rerank(candidates, similarity_matrix, top_n=8, lambda_param=0.72):
    """
    Maximal Marginal Relevance reranking for diverse results.
    candidates: list of (index, relevance_score)
    """
    if not candidates:
        return []

    selected = []
    remaining = list(candidates)

    while remaining and len(selected) < top_n:
        best_idx = None
        best_mmr = -1.0

        for idx, rel in remaining:
            if not selected:
                mmr = rel
            else:
                max_sim = max(similarity_matrix[idx][s[0]] for s in selected)
                mmr = lambda_param * rel - (1 - lambda_param) * max_sim
            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = (idx, rel)

        selected.append(best_idx)
        remaining = [(i, r) for i, r in remaining if i != best_idx[0]]

    return selected


def row_to_dict(row, score=None, tfidf_score=None):
    result = {
        "item_id": int(row["item_id"]),
        "title": clean_display_text(row["title"]),
        "type": row["type"],
        "category": row["category"],
        "description": clean_display_text(row["description"]),
        "topics": row["topics"],
        "instructor": row["instructor"],
        "platform": row["platform"],
        "link": clean_link(row["link"]),
    }
    if "level" in row and str(row["level"]).strip():   # trường cấp độ (mới), nếu có
        result["level"] = row["level"]
    if score is not None:
        result["score"] = round(float(score) * 100, 1)
    if tfidf_score is not None:
        result["tfidf_score"] = round(float(tfidf_score) * 100, 1)
    return result


def _fuse_tfidf_scores(query, vectorizers, matrices, weights=None):
    """Multi-field TF-IDF fusion: title + topics + full."""
    weights = weights or {"title": 0.38, "topics": 0.37, "full": 0.25}
    n_docs = matrices["full"].shape[0]
    fused = np.zeros(n_docs)

    for field, weight in weights.items():
        if field not in vectorizers:
            continue
        q_vec = vectorizers[field].transform([query])
        scores = cosine_similarity(q_vec, matrices[field]).flatten()
        fused += weight * scores

    return fused


def search_by_query(
    item_list,
    retrieval_model,
    query,
    top_n=5,
    item_type=None,
    use_mmr=True,
):
    """Advanced query search with multi-field TF-IDF + BM25 + hybrid reranking."""
    vectorizers = retrieval_model["vectorizers"]
    matrices = retrieval_model["matrices"]
    bm25 = retrieval_model["bm25"]
    categories = retrieval_model["categories"]

    tfidf_scores = _fuse_tfidf_scores(query, vectorizers, matrices)
    bm25_raw = bm25.score_query(query)
    bm25_scores = np.array(bm25.normalize_scores(bm25_raw))

    category_hint = detect_category_from_query(query, categories)

    candidates = []
    for i in range(len(item_list)):
        row = item_list.iloc[i]
        if item_type and row["type"] != item_type:
            continue

        cat_score = category_bonus(category_hint, row["category"]) if category_hint else 0.0
        q_topics = set(extract_query_tokens(query))
        row_topics = parse_topics(row["topics"])
        type_match = 1.0 if item_type and row["type"] == item_type else 0.0

        score = (
            SCORE_WEIGHTS["tfidf"] * tfidf_scores[i]
            + SCORE_WEIGHTS["bm25"] * bm25_scores[i]
            + SCORE_WEIGHTS["category"] * cat_score
            + SCORE_WEIGHTS["topic_jaccard"] * topic_jaccard(q_topics, row_topics)
            + SCORE_WEIGHTS["topic_contain"] * topic_containment(q_topics, row_topics)
            + SCORE_WEIGHTS["title_overlap"] * title_keyword_overlap(query, row["title"])
            + SCORE_WEIGHTS["type_match"] * type_match
        )
        candidates.append((i, min(score, 1.0), tfidf_scores[i]))

    candidates.sort(key=lambda x: x[1], reverse=True)

    if use_mmr and len(candidates) > top_n:
        # MMR trên một tập ứng viên nhỏ -> chỉ cần ma trận con, tính tại chỗ từ TF-IDF
        pool = candidates[: top_n * 4]
        pool_idx = [i for i, _, _ in pool]
        sub_sim = cosine_similarity(matrices["full"][pool_idx])
        reranked = mmr_rerank(
            [(local, s) for local, (_, s, _) in enumerate(pool)],
            sub_sim,
            top_n=top_n,
        )
        results = []
        for local, score in reranked:
            gi = pool_idx[local]
            results.append(
                row_to_dict(item_list.iloc[gi], score=score, tfidf_score=tfidf_scores[gi])
            )
        return results

    results = []
    for i, score, tfidf in candidates[:top_n]:
        results.append(row_to_dict(item_list.iloc[i], score=score, tfidf_score=tfidf))
    return results


def recommend_by_query(item_list, retrieval_model, query, top_n=5):
    """Query-based seed finding + hybrid similar-item recommendations."""
    search_results = search_by_query(
        item_list, retrieval_model, query, top_n=3, use_mmr=False
    )
    if not search_results:
        return {"seed": None, "recommendations": []}

    seed = search_results[0]
    seed_rows = item_list[item_list["item_id"] == seed["item_id"]]
    seed_index = seed_rows.index[0]
    seed_row = seed_rows.iloc[0]
    seed_topics = parse_topics(seed_row["topics"])
    seed_category = seed_row["category"]
    matrices = retrieval_model["matrices"]
    seed_sim = cosine_similarity(matrices["full"][seed_index], matrices["full"]).flatten()
    q_topics = set(extract_query_tokens(query))

    candidates = []
    for i, cosine in enumerate(seed_sim):
        if i == seed_index:
            continue
        row = item_list.iloc[i]
        score = hybrid_score_v2(
            cosine=cosine,
            category_score=category_bonus(seed_category, row["category"]),
            topics_a=seed_topics,
            topics_b=parse_topics(row["topics"]),
            type_match=1.0 if row["type"] == seed_row["type"] else 0.0,
            title_overlap=title_keyword_overlap(query, row["title"]),
            query_topics=q_topics,
        )
        candidates.append((i, score, cosine))

    candidates.sort(key=lambda x: x[1], reverse=True)
    recommendations = [
        row_to_dict(item_list.iloc[i], score=score, tfidf_score=cosine)
        for i, score, cosine in candidates[:top_n]
    ]

    return {"seed": seed, "recommendations": recommendations}


def recommend(item_list, similarity, title, top_n=5):
    """Item-to-item recommendations cho tab "Gợi ý theo mục".

    `similarity` là ma trận relevance đã hiệu chỉnh sẵn (embeddings ngữ nghĩa +
    topic/category boost + calibration, sinh bởi build_embeddings.py), nên hiển thị
    trực tiếp — KHÔNG áp lại hybrid_score_v2 để tránh xử lý hai lần.
    """
    index = item_list[item_list["title"] == title].index[0]

    candidates = [
        (i, float(similarity[index][i]))
        for i in range(len(item_list))
        if i != index
    ]
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [
        row_to_dict(item_list.iloc[i], score=score)
        for i, score in candidates[:top_n]
    ]


RERANK_POOL = 32            # số ứng viên đưa vào cross-encoder (tầng 2); cân bằng tốc độ/chất lượng


def _rerank_doc(row):
    """Đoạn văn bản tài liệu cấp cho cross-encoder (lấy từ trường thật của catalog)."""
    return (
        f"{row['title']}. Chuyên mục: {row['category']}. "
        f"Chủ đề: {row['topics']}. {row['description']}"
    )


def _combined_scores(query, item_list, model, embeddings,
                     char_vectorizer, char_matrix, query_prefix, ann):
    """Điểm hybrid mỗi item = max(kênh ngữ nghĩa, kênh ký tự). Trả (score[n], smax)."""
    q_emb = model.encode(
        [f"{query_prefix}{query.lower()}"], normalize_embeddings=True, convert_to_numpy=True
    )[0]
    n = len(item_list)
    if ann is not None:
        from itlr.core.ann import ann_search

        hit = ann_search(ann, q_emb, top_n=min(RERANK_POOL * 4, n))
        if hit is not None:
            idx, sims = hit
            score = np.full(n, -1.0, dtype="float64")
            valid = (idx >= 0) & (idx < n)
            score[idx[valid]] = sims[valid]
        else:
            score = embeddings @ q_emb
    else:
        score = embeddings @ q_emb

    if char_vectorizer is not None and char_matrix is not None:
        q_char = char_vectorizer.transform([strip_accents(query)])
        lexical = cosine_similarity(q_char, char_matrix).ravel()
        score = np.maximum(score, lexical)
    return score, float(score.max())


def _gather_candidates(score, item_list, item_type, limit=None):
    """Ứng viên qua sàn tuyệt đối, sắp giảm dần, lọc theo loại. Trả list (idx, raw)."""
    order = np.argsort(score)[::-1]
    cand = []
    for i in order:
        raw = float(score[i])
        if raw < ABS_ITEM_FLOOR:
            break
        row = item_list.iloc[int(i)]
        if item_type and row["type"] != item_type:
            continue
        cand.append((int(i), raw))
        if limit and len(cand) >= limit:
            break
    return cand


def _rerank_calibrate(query, cand, item_list, fallback_max, reranker):
    """Rerank top pool bằng cross-encoder + hiệu chỉnh % hiển thị. Trả list (idx, conf)."""
    if reranker is not None and cand:
        from itlr.core.rerank import rerank as _rr

        pool = cand[:RERANK_POOL]
        ranked = _rr(
            query, pool,
            text_of=lambda c: _rerank_doc(item_list.iloc[c[0]]),
            reranker=reranker,
        )
        if ranked and ranked[0][1] is not None:
            best = max(s for _, s in ranked) or 1.0
            reranked = [(c[0], calibrate_confidence(s / best)) for c, s in ranked]
            rest = [(i, calibrate_confidence(raw / fallback_max)) for i, raw in cand[RERANK_POOL:]]
            return reranked + rest
    return [(i, calibrate_confidence(raw / fallback_max)) for i, raw in cand]


def _apply_mmr(scored, embeddings, top_n=8, lambda_param=0.7):
    """Đa dạng hóa kết quả bằng Maximal Marginal Relevance (tránh top toàn mục gần trùng)."""
    pool = scored[: min(len(scored), RERANK_POOL)]
    if len(pool) <= top_n:
        return scored
    idxs = [i for i, _ in pool]
    rels = [c for _, c in pool]
    sub = embeddings[idxs] @ embeddings[idxs].T      # cosine (vector đã chuẩn hóa)
    selected = mmr_rerank([(k, rels[k]) for k in range(len(pool))],
                          sub, top_n=top_n, lambda_param=lambda_param)
    chosen = [k for k, _ in selected]
    chosen_set = set(chosen)
    out = [(idxs[k], rels[k]) for k in chosen]
    out += [(idxs[k], rels[k]) for k in range(len(pool)) if k not in chosen_set]
    out += scored[len(pool):]
    return out


def search_by_embedding(
    query,
    item_list,
    model,
    embeddings,
    char_vectorizer=None,
    char_matrix=None,
    item_type=None,
    min_relevance=0.0,
    query_prefix="",
    ann=None,
    reranker=None,
):
    """Tìm kiếm HYBRID 2 TẦNG, chịu lỗi chính tả / thiếu dấu / thiếu từ.

    TẦNG 1 (recall): max(embeddings ngữ nghĩa [ANN/FAISS nếu có], char n-gram bỏ dấu).
    TẦNG 2 (precision): cross-encoder rerank top ứng viên (nếu khả dụng).
    Cổng tuyệt đối off-topic và dải hiển thị 90-100% giữ nguyên.
    """
    score, smax = _combined_scores(
        query, item_list, model, embeddings, char_vectorizer, char_matrix, query_prefix, ann
    )
    if smax < ABS_RELEVANCE_GATE:
        return []
    cand = _gather_candidates(score, item_list, item_type)
    if not cand:
        return []
    scored = _rerank_calibrate(query, cand, item_list, smax, reranker)
    return [
        row_to_dict(item_list.iloc[i], score=conf)
        for i, conf in scored if conf + 1e-9 >= min_relevance
    ]


def multi_query_search(
    queries,
    item_list,
    model,
    embeddings,
    char_vectorizer=None,
    char_matrix=None,
    item_type=None,
    query_prefix="",
    ann=None,
    reranker=None,
    top_k=8,
    use_mmr=True,
    gate_query=None,
):
    """RAG-Fusion: truy hồi nhiều BIẾN THỂ truy vấn rồi hợp nhất bằng RRF.

    Thuật toán hiện đại (RAG-Fusion / Multi-Query Retrieval): mỗi biến thể (gốc /
    đã sửa lỗi+nối lịch sử / mở rộng từ đồng nghĩa) truy hồi độc lập, rồi Reciprocal
    Rank Fusion gộp các bảng xếp hạng -> bền với cách diễn đạt khác nhau. Sau đó
    rerank cross-encoder MỘT lần trên tập đã gộp, và MMR để đa dạng kết quả.

    gate_query: truy vấn TỰ NHIÊN dùng riêng cho cổng off-topic (tránh biến thể mở
    rộng có lặp từ làm thổi phồng điểm char n-gram -> lọt câu ngoài lĩnh vực).

    Trả list item dict (có 'score' %). Rỗng nếu ngoài lĩnh vực.
    """
    seen, qs = set(), []
    for q in queries:                                 # bỏ trùng, giữ thứ tự
        q = (q or "").strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            qs.append(q)
    if not qs:
        return []

    # Cổng off-topic: quyết định bằng truy vấn tự nhiên (gate_query) nếu có, để biến
    # thể mở rộng (lặp từ) không vô tình kéo câu ngoài lĩnh vực qua cổng.
    gate_src = gate_query if gate_query and gate_query.strip() else qs[0]
    _, gate_smax = _combined_scores(
        gate_src, item_list, model, embeddings, char_vectorizer, char_matrix, query_prefix, ann
    )
    if gate_smax < ABS_RELEVANCE_GATE:
        return []

    rankings = []
    for q in qs:
        score, _ = _combined_scores(
            q, item_list, model, embeddings, char_vectorizer, char_matrix, query_prefix, ann
        )
        rankings.append([i for i, _ in _gather_candidates(score, item_list, item_type, limit=RERANK_POOL)])

    fused = reciprocal_rank_fusion(rankings)          # [(idx, rrf_score)] giảm dần
    if not fused:
        return []
    rrf_max = fused[0][1] or 1.0
    pool = [(idx, rrf) for idx, rrf in fused[:RERANK_POOL]]
    scored = _rerank_calibrate(qs[0], pool, item_list, rrf_max, reranker)
    scored += [(idx, calibrate_confidence(rrf / rrf_max)) for idx, rrf in fused[RERANK_POOL:]]

    if use_mmr:
        scored = _apply_mmr(scored, embeddings, top_n=top_k)

    return [row_to_dict(item_list.iloc[i], score=conf) for i, conf in scored[:top_k]]


def query_relevance_max(query, item_list, model, embeddings,
                        char_vectorizer=None, char_matrix=None, query_prefix="", ann=None):
    """Điểm tương đồng CAO NHẤT của truy vấn so với toàn catalog (max kênh ngữ nghĩa/ký tự).

    Dùng làm CỔNG off-topic ở mức truy vấn: smax thấp -> không có mục nào thực sự liên
    quan -> truy vấn nằm NGOÀI lĩnh vực CNTT. Trả về float (0..1). Đây là phiên bản công
    khai của tín hiệu mà `search_by_embedding`/`multi_query_search` dùng nội bộ để chặn.
    """
    _, smax = _combined_scores(
        query, item_list, model, embeddings, char_vectorizer, char_matrix, query_prefix, ann
    )
    return smax


def recommend_for_user(history_positions, cf_model, item_list, top_n=12, exclude=None):
    """Feed "Dành cho bạn" bằng item-based Collaborative Filtering.

    Chấm điểm mỗi item = tổng độ tương đồng CF tới các item trong lịch sử của user
    ("người học X cũng học Y"). Lịch sử rỗng -> fallback theo độ phổ biến (cold-start).
    Điểm hiển thị được chuẩn hóa theo món phù hợp nhất -> "% phù hợp với bạn".
    """
    sim = cf_model["item_sim"]
    pop = cf_model["popularity"].astype(float)
    n = sim.shape[0]
    seen = set(int(p) for p in history_positions) | set(int(e) for e in (exclude or []))

    if history_positions:
        scores = np.asarray(sim[list(history_positions)].sum(axis=0)).ravel()
    else:
        scores = pop.copy()  # người mới: gợi ý phổ biến

    for p in seen:
        if 0 <= p < n:
            scores[p] = -1.0

    cmax = scores.max()
    order = np.argsort(scores)[::-1][:top_n]
    results = []
    for p in order:
        if scores[p] <= 0:
            break
        rel = scores[p] / cmax if cmax > 0 else 0.0
        results.append(row_to_dict(item_list.iloc[int(p)], score=calibrate_confidence(rel)))
    return results


def build_retrieval_model(item_list, vectorizers, matrices, bm25):
    """Package all retrieval components into a single model dict.

    Không lưu ma trận tương đồng N×N (tốn ~N²*8 byte). MMR & seed-similarity
    được tính on-the-fly từ matrices["full"] (TF-IDF thưa) khi cần.
    """
    return {
        "vectorizers": vectorizers,
        "matrices": matrices,
        "bm25": bm25,
        "categories": sorted(item_list["category"].unique().tolist()),
        "topic_index": _build_topic_index(item_list),
    }


def _build_topic_index(item_list):
    index = {}
    for _, row in item_list.iterrows():
        for topic in str(row["topics"]).split(","):
            key = normalize_text(topic.strip())
            if key:
                index.setdefault(key, []).append(int(row["item_id"]))
    return index
