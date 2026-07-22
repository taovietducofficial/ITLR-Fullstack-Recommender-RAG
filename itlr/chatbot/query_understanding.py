"""Hiểu & chuẩn hóa truy vấn người dùng TRƯỚC khi phát hiện ý định và truy hồi.

Sửa lỗi gõ sai ("machne lerning", "docke"), thiếu dấu, và viết tắt (ml, k8s, db) để hệ
thống hiểu đúng lĩnh vực/loại tài nguyên/kiểu câu hỏi. Bổ trợ (không thay thế) truy hồi
ngữ nghĩa: embeddings/char n-gram vốn đã chịu lỗi chính tả, nhưng các bộ phát hiện theo
luật (mode/category/type) khớp chính xác nên dễ trượt khi gõ sai — chuẩn hóa ở đây sửa
đúng phần đó.
"""

import difflib
import re

from itlr.core.recommender import normalize_text, strip_accents

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

_AMBIGUOUS_ABBR = {"ai", "be", "ui"}

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
    "engineer", "engineering", "developer", "scientist", "analyst", "fullstack",
    "roadmap", "career", "intern", "fresher", "junior", "senior",
    "lap", "trinh", "khoa", "hoc", "tai", "lieu", "lo", "trinh", "co", "ban", "nang",
    "cao", "nhap", "mon", "du", "lieu", "tri", "tue", "nhan", "tao", "bao", "mat",
    "mang", "may", "tinh", "dien", "toan", "dam", "may", "giai", "thuat", "cau", "truc",
    "phat", "trien", "web", "game", "kiem", "thu", "huong", "dan", "thuc", "hanh",
    "sanh", "khac", "nhau", "nao", "voi", "cho", "cua", "mot", "cac", "nhung", "hay",
    "hoac", "the", "khi", "khong", "duoc", "lam", "biet", "hieu",
}


def build_query_vocab(retrieval_model=None, item_list=None):
    """Vốn từ chuẩn (bỏ dấu) làm đích sửa lỗi chính tả: seed vocab + chuyên mục + topic_index
    của catalog. Chỉ giữ token độ dài >= 3 để fuzzy không sửa nhầm từ ngắn.
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

    if bare in COMMON_TYPOS:
        return COMMON_TYPOS[bare], True

    if bare in vocab:
        return tok, False

    if len(bare) >= 4 and bare.isalpha() and tok == bare:
        match = difflib.get_close_matches(bare, vocab, n=1, cutoff=0.84)
        if match and match[0] != bare:
            return match[0], True

    return tok, False


def understand_query(query, vocab):
    """Phân tích & chuẩn hóa truy vấn. Trả dict: original (gốc), corrected (đã sửa + mở rộng
    viết tắt, dùng cho retrieval/detection), display (đã sửa, không mở rộng, để hiển thị lại
    cho người dùng), corrections (list từ_sai/từ_đúng), expansions (cụm mở rộng viết tắt).
    """
    query = re.sub(r"(?i)c\+\+", "cpp", str(query))
    query = re.sub(r"(?i)c#", "csharp", query)
    tokens = normalize_text(query).split()
    corrected_tokens = []
    corrections = []
    expansions = []
    expansion_pairs = []

    single_token = len(tokens) == 1
    for tok in tokens:
        bare = strip_accents(tok)
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


_ABBR_READABLE = {
    "ml": "Machine Learning", "ai": "Trí tuệ nhân tạo (AI)", "dl": "Deep Learning",
    "nlp": "Xử lý ngôn ngữ tự nhiên (NLP)", "cv": "Computer Vision", "llm": "Large Language Model",
    "genai": "Generative AI", "k8s": "Kubernetes", "k8": "Kubernetes", "js": "JavaScript",
    "ts": "TypeScript", "py": "Python", "db": "Cơ sở dữ liệu", "oop": "Lập trình hướng đối tượng",
    "dsa": "Cấu trúc dữ liệu & giải thuật", "ds": "Khoa học dữ liệu", "fe": "Frontend",
    "be": "Backend", "sec": "An ninh mạng", "infosec": "An ninh mạng", "pentest": "Kiểm thử xâm nhập",
    "ctf": "Capture The Flag", "cloud": "Điện toán đám mây", "sql": "SQL", "nosql": "NoSQL",
    "api": "API", "ui": "Giao diện người dùng (UI)", "ux": "Trải nghiệm người dùng (UX)",
    "os": "Hệ điều hành", "devops": "DevOps",
}


def _as_sentence(text):
    """Viết hoa chữ đầu để hiển thị như một câu hoàn chỉnh."""
    text = str(text).strip()
    return text[:1].upper() + text[1:] if text else text


def intent_note(understanding):
    """Dòng đặt TRƯỚC câu trả lời xác nhận lại ý hiểu khi có sửa chính tả hoặc nhận diện viết
    tắt. Trả "" nếu truy vấn đã rõ ràng, để không làm rối.
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
