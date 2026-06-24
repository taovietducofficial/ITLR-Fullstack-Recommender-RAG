"""Hiểu & chuẩn hóa truy vấn người dùng TRƯỚC khi phát hiện ý định và truy hồi.

Mục tiêu: dù người dùng gõ sai ("machne lerning", "lap trnh web", "docke"),
thiếu dấu, hay dùng viết tắt (ml, k8s, db), hệ thống vẫn hiểu đúng lĩnh vực,
loại tài nguyên và kiểu câu hỏi -> câu trả lời bám sát ý người dùng hơn.

Lớp này bổ trợ (không thay thế) kênh truy hồi ngữ nghĩa: embeddings/char n-gram
vốn đã chịu lỗi chính tả, nhưng các bộ phát hiện theo luật (mode/category/type)
lại khớp chính xác -> dễ trượt khi gõ sai. Chuẩn hóa ở đây sửa đúng phần đó.
"""

import difflib
import re

from itlr.core.recommender import normalize_text, strip_accents

# Viết tắt / biệt danh phổ biến -> cụm từ chuẩn (key đã bỏ dấu, viết thường).
# Mở rộng được nối vào cuối truy vấn để tăng tín hiệu cho cả detection lẫn retrieval.
ABBREVIATIONS = {
    "ml": "machine learning",
    "ai": "tri tue nhan tao artificial intelligence",
    "dl": "deep learning neural network",
    "nlp": "xu ly ngon ngu tu nhien natural language processing",
    "cv": "computer vision thi giac may tinh",
    "llm": "large language model mo hinh ngon ngu lon",
    "genai": "generative ai tri tue nhan tao tao sinh",
    "k8s": "kubernetes",
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "db": "co so du lieu database",
    "oop": "lap trinh huong doi tuong object oriented",
    "dsa": "cau truc du lieu giai thuat data structures algorithms",
    "ds": "khoa hoc du lieu data science",
    "fe": "frontend lap trinh web",
    "be": "backend api server",
    "devops": "devops ci cd docker kubernetes",
    "k8": "kubernetes",
    "sec": "an ninh mang cybersecurity",
    "infosec": "an ninh mang cybersecurity",
    "pentest": "kiem thu xam nhap penetration testing an ninh mang",
    "ctf": "capture the flag an ninh mang",
    "cloud": "dien toan dam may aws azure gcp",
    "sql": "co so du lieu truy van sql",
    "nosql": "co so du lieu nosql mongodb",
    "api": "backend api server",
    "ui": "giao dien nguoi dung frontend",
    "ux": "trai nghiem nguoi dung",
    " os": "he dieu hanh operating system",
}

# Viết tắt NHẬP NHẰNG (đồng thời là từ tiếng Việt thông dụng) -> chỉ mở rộng khi
# truy vấn chỉ có ĐÚNG một từ, tránh "ai là ca sĩ" bị bơm thành "trí tuệ nhân tạo...".
_AMBIGUOUS_ABBR = {"ai", "be", "ui"}

# Từ điển sửa lỗi chính tả thủ công cho lỗi hay gặp mà fuzzy có thể bỏ sót
# (key đã bỏ dấu, viết thường). Ưu tiên cao hơn fuzzy matching.
COMMON_TYPOS = {
    "phyton": "python", "pythn": "python", "phython": "python", "pyton": "python",
    "javascrip": "javascript", "javscript": "javascript", "javascipt": "javascript",
    "jvascript": "javascript", "jaava": "java",
    "docke": "docker", "dokcer": "docker", "doker": "docker",
    "kubenetes": "kubernetes", "kubernets": "kubernetes", "kubernet": "kubernetes",
    "machin": "machine", "machne": "machine", "mashine": "machine", "mechine": "machine",
    "lerning": "learning", "learing": "learning", "learnin": "learning",
    "reactjs": "react", "nodejs": "node", "vuejs": "vue", "angularjs": "angular",
    "phyton3": "python", "datbase": "database", "databse": "database",
    "algoritm": "algorithm", "algorith": "algorithm", "algorthm": "algorithm",
    "securty": "security", "securit": "security", "secrity": "security",
    "netwok": "network", "netowrk": "network", "netwrok": "network",
    "frontent": "frontend", "fronend": "frontend", "backen": "backend",
    "develper": "developer", "developr": "developer", "programing": "programming",
    "tensorflw": "tensorflow", "pytorh": "pytorch", "pands": "pandas",
    "kafa": "kafka", "spar": "spark", "hadop": "hadoop",
    "laptrinh": "lap trinh", "khoahoc": "khoa hoc", "tailieu": "tai lieu",
    "lotrinh": "lo trinh", "baomat": "bao mat", "mangmaytinh": "mang may tinh",
}

# Vốn từ CNTT chuẩn dùng làm đích cho fuzzy correction (đã bỏ dấu, viết thường).
# Được bổ sung động từ category + topic của catalog trong build_query_vocab().
_SEED_VOCAB = {
    "python", "java", "javascript", "typescript", "kotlin", "swift", "golang", "rust",
    "react", "angular", "vue", "svelte", "nextjs", "node", "express", "django", "flask",
    "spring", "laravel", "flutter",
    "machine", "learning", "deep", "neural", "network", "tensorflow", "pytorch", "keras",
    "pandas", "numpy", "scikit", "transformer", "regression", "classification",
    "docker", "kubernetes", "jenkins", "terraform", "ansible", "microservice", "container",
    "database", "mongodb", "postgresql", "mysql", "redis", "elasticsearch", "kafka",
    "spark", "hadoop", "airflow", "snowflake",
    "security", "cybersecurity", "cryptography", "firewall", "malware", "penetration",
    "vulnerability", "owasp", "network", "protocol", "router",
    "algorithm", "structure", "recursion", "dynamic", "graph", "sorting", "searching",
    "frontend", "backend", "fullstack", "developer", "programming", "framework",
    "android", "mobile", "blockchain", "ethereum", "cloud", "serverless", "lambda",
    "analytics", "visualization", "statistics", "regression",
    # từ nghề nghiệp / vai trò — KHÔNG để fuzzy sửa nhầm (vd "engineer"->"engine")
    "engineer", "engineering", "developer", "scientist", "analyst", "fullstack",
    "roadmap", "career", "intern", "fresher", "junior", "senior",
    # tiếng Việt (đã bỏ dấu) — các cụm hay gõ sai/thiếu dấu
    "lap", "trinh", "khoa", "hoc", "tai", "lieu", "lo", "trinh", "co", "ban", "nang",
    "cao", "nhap", "mon", "du", "lieu", "tri", "tue", "nhan", "tao", "bao", "mat",
    "mang", "may", "tinh", "dien", "toan", "dam", "may", "giai", "thuat", "cau", "truc",
    "phat", "trien", "web", "game", "kiem", "thu", "huong", "dan", "thuc", "hanh",
    # từ chức năng / so sánh / nghi vấn tiếng Việt (bỏ dấu) — BẢO VỆ khỏi fuzzy sửa nhầm
    # (vd "so sanh"->"sanh" từng bị sửa bậy thành "san"). Chỉ đánh dấu là "từ đúng".
    "sanh", "khac", "nhau", "nao", "voi", "cho", "cua", "mot", "cac", "nhung", "hay",
    "hoac", "the", "khi", "khong", "duoc", "lam", "biet", "hieu",
}


def build_query_vocab(retrieval_model=None, item_list=None):
    """Dựng vốn từ chuẩn (bỏ dấu) làm đích sửa lỗi chính tả.

    Gộp: seed vocab + tên chuyên mục + khóa trong topic_index của catalog.
    Chỉ giữ token độ dài >= 3 để fuzzy không sửa nhầm từ ngắn.
    """
    vocab = set(_SEED_VOCAB)

    def _add_phrase(text):
        for tok in strip_accents(normalize_text(text)).split():
            if len(tok) >= 3 and tok.isalpha():
                vocab.add(tok)

    if retrieval_model:
        for cat in retrieval_model.get("categories", []):
            _add_phrase(cat)
        for topic in retrieval_model.get("topic_index", {}):
            _add_phrase(topic)
    if item_list is not None:
        for cat in item_list["category"].unique():
            _add_phrase(cat)

    # BẢO VỆ mọi thuật ngữ/viết tắt trong từ điển glossary khỏi bị fuzzy sửa nhầm
    # (vd "olap"->"lap", "rlhf"->...). Thêm token alias vào vốn từ đích -> coi là từ đúng.
    try:
        from itlr.chatbot.knowledge_base import CONCEPTS
        for entry in CONCEPTS.values():
            for alias in entry.get("aliases", []):
                _add_phrase(alias)
    except Exception:
        pass

    return frozenset(v for v in vocab if len(v) >= 3)


def _correct_token(tok, vocab):
    """Trả về (token_đã_sửa, bool_có_sửa). Bảo toàn từ tiếng Việt có dấu."""
    bare = strip_accents(tok)

    # 1) Lỗi chính tả thường gặp (ưu tiên cao nhất)
    if bare in COMMON_TYPOS:
        return COMMON_TYPOS[bare], True

    # 2) Từ đã đúng (có trong vốn từ) -> giữ nguyên
    if bare in vocab:
        return tok, False

    # 3) Chỉ fuzzy với token kiểu "tiếng Anh/không dấu", đủ dài, để tránh
    #    làm hỏng từ tiếng Việt có dấu (vd "lập", "trình").
    if len(bare) >= 4 and bare.isalpha() and tok == bare:
        match = difflib.get_close_matches(bare, vocab, n=1, cutoff=0.84)
        if match and match[0] != bare:
            return match[0], True

    return tok, False


def understand_query(query, vocab):
    """Phân tích & chuẩn hóa truy vấn.

    Trả về dict:
      - original:    chuỗi gốc người dùng nhập
      - corrected:   chuỗi đã sửa lỗi + nối phần mở rộng viết tắt (cho retrieval/detection)
      - display:     chuỗi đã sửa (KHÔNG kèm mở rộng) để hiển thị lại cho người dùng
      - corrections: list (từ_sai, từ_đúng) đã sửa
      - expansions:  list cụm mở rộng từ viết tắt
    """
    # Canonicalize ký hiệu TRƯỚC normalize_text (vốn bỏ '+'/'#'): "c++"->cpp, "c#"->csharp
    # -> phân biệt C / C++ / C# trong cả định tuyến lẫn hiển thị.
    query = re.sub(r"(?i)c\+\+", "cpp", str(query))
    query = re.sub(r"(?i)c#", "csharp", query)
    tokens = normalize_text(query).split()
    corrected_tokens = []
    corrections = []
    expansions = []
    expansion_pairs = []   # [(viết_tắt, cụm_chuẩn_đọc_được)] -> để minh bạch hóa cho người dùng

    single_token = len(tokens) == 1
    for tok in tokens:
        bare = strip_accents(tok)
        # CHỈ mở rộng viết tắt khi token là ASCII không dấu (tok == bare). Nếu không,
        # từ tiếng Việt CÓ DẤU bị bỏ dấu sẽ khớp nhầm viết tắt: "bé"->"be"->backend,
        # "cứ"->"cu", "ổ"->"o"... -> truy vấn ngoài lĩnh vực bị mở rộng thành IT.
        # Với viết tắt NHẬP NHẰNG (cũng là từ tiếng Việt thông dụng: ai/be/ui), chỉ mở
        # rộng khi đứng MỘT MÌNH -> "ai" (1 từ) = AI, nhưng "ai là ca sĩ" coi như từ thường.
        if tok == bare and bare in ABBREVIATIONS:
            if bare in _AMBIGUOUS_ABBR and not single_token:
                corrected_tokens.append(tok)
            else:
                expansions.append(ABBREVIATIONS[bare])
                expansion_pairs.append(
                    (bare, _ABBR_READABLE.get(bare, ABBREVIATIONS[bare].split(",")[0]))
                )
                corrected_tokens.append(tok)
            continue
        fixed, changed = _correct_token(tok, vocab)
        if changed:
            corrections.append((tok, fixed))
        corrected_tokens.append(fixed)

    display = " ".join(corrected_tokens)
    corrected = display
    if expansions:
        corrected = f"{display} {' '.join(expansions)}"

    return {
        "original": query,
        "corrected": corrected,
        "display": display,
        "corrections": corrections,
        "expansions": expansions,
        "expansion_pairs": expansion_pairs,
    }


# Cụm mở rộng viết tắt trong ABBREVIATIONS gộp cả tiếng Việt lẫn tiếng Anh để tăng tín hiệu
# truy hồi; khi HIỂN THỊ cho người dùng chỉ cần cụm đầu, gọn & dễ đọc.
_ABBR_READABLE = {
    "ml": "Machine Learning", "ai": "Trí tuệ nhân tạo (AI)", "dl": "Deep Learning",
    "nlp": "Xử lý ngôn ngữ tự nhiên (NLP)", "cv": "Computer Vision", "llm": "Large Language Model",
    "genai": "Generative AI", "k8s": "Kubernetes", "k8": "Kubernetes", "js": "JavaScript",
    "ts": "TypeScript", "py": "Python", "db": "Cơ sở dữ liệu", "oop": "Lập trình hướng đối tượng",
    "dsa": "Cấu trúc dữ liệu & giải thuật", "ds": "Khoa học dữ liệu", "fe": "Frontend",
    "be": "Backend", "sec": "An ninh mạng", "infosec": "An ninh mạng", "pentest": "Kiểm thử xâm nhập",
    "ctf": "Capture The Flag", "cloud": "Điện toán đám mây", "sql": "SQL", "nosql": "NoSQL",
    "api": "API", "ui": "Giao diện người dùng (UI)", "ux": "Trải nghiệm người dùng (UX)",
    "os": "Hệ điều hành",
}


def _as_sentence(text):
    """Chuẩn hóa chuỗi đã sửa thành 'câu hoàn chỉnh' để hiển thị: viết hoa chữ đầu."""
    text = str(text).strip()
    return text[:1].upper() + text[1:] if text else text


def intent_note(understanding):
    """Dòng minh bạch hóa ĐẶT TRƯỚC câu trả lời: xác nhận lại Ý HIỂU khi có sửa lỗi chính tả
    HOẶC nhận diện viết tắt. Viết lại thành CÂU HOÀN CHỈNH (viết hoa) cho người dùng, kèm chi
    tiết đã sửa. Trả "" nếu truy vấn đã rõ ràng -> không làm rối.
    """
    corr = understanding.get("corrections") or []
    pairs = understanding.get("expansion_pairs") or []
    if not corr and not pairs:
        return ""
    bits = []
    if corr:
        bits.append("tự sửa chính tả: " + ", ".join(f"*{w}* → **{r}**" for w, r in corr[:5]))
    if pairs:
        bits.append("hiểu viết tắt: " + ", ".join(f"**{a}** = {full}" for a, full in pairs[:5]))
    return (
        f"> 🔎 Mình hiểu ý bạn là: **{_as_sentence(understanding['display'])}**  \n"
        f"> _({' · '.join(bits)})_\n\n"
    )
