"""Educational chatbot: unified RAG + recommendation pipeline with conversation history."""

import json
import os
import re
import time
import urllib.request

import itlr.chatbot.knowledge_base as kb
from itlr.chatbot.intent_router import FREE_PLATFORMS, detect_filters, route_intent
from itlr.chatbot.query_understanding import build_query_vocab, intent_note, understand_query
from itlr.core.rag import EducationalRAG, enrich_query_with_history, expand_query, item_to_document
from itlr.core.recommender import (
    QUERY_STOP_WORDS,
    calibrate_confidence,
    multi_query_search,
    normalize_text,
    query_relevance_max,
    row_to_dict,
    search_by_embedding,
    strip_accents,
)


# Cổng off-topic riêng cho CHATBOT — đặt CHẶT hơn tab Tìm kiếm (ABS_RELEVANCE_GATE=0.48)
# theo yêu cầu: thà chặn nhầm vài câu CNTT mơ hồ còn hơn để lọt câu lạc đề. Truy vấn có
# điểm tương đồng cao nhất với catalog < ngưỡng này -> coi là ngoài lĩnh vực -> từ chối.
# (Có thể chỉnh số này để nới/siết độ chặt; off-topic đo được ~0.46-0.48, câu IT >= 0.51.)
CHATBOT_OFFTOPIC_GATE = 0.55

# Thông báo từ chối RÕ RÀNG cho câu ngoài lĩnh vực — KHÔNG kèm tài nguyên/gợi ý lạc đề,
# chỉ nhắc lại phạm vi hỗ trợ + vài ví dụ câu hỏi CNTT hợp lệ để hướng người dùng quay lại.
OFF_TOPIC_MESSAGE = (
    "Xin lỗi, mình là **trợ lý học tập CNTT** nên chỉ trả lời các câu hỏi trong lĩnh vực "
    "công nghệ thông tin (lập trình, web, AI/ML, dữ liệu, cloud, DevOps, an ninh mạng, "
    "mobile, cơ sở dữ liệu...).\n\n"
    "Câu hỏi của bạn có vẻ nằm ngoài phạm vi này nên mình xin phép không trả lời. "
    "Bạn thử hỏi mình một chủ đề CNTT nhé — ví dụ:\n"
    "- *Machine Learning là gì?*\n"
    "- *Lộ trình học Lập trình Web từ cơ bản đến nâng cao*\n"
    "- *Gợi ý khóa học Docker cho người mới bắt đầu*"
)


SUGGESTED_PROMPTS = [
    "Gợi ý khóa học Machine Learning cho người mới bắt đầu",
    "Tìm tài liệu về Docker và Kubernetes",
    "Lộ trình học An ninh mạng từ cơ bản đến nâng cao",
    "So sánh các khóa học về Lập trình Web",
    "DevOps có những tài nguyên nào phù hợp?",
    "Tôi muốn học Deep Learning, nên bắt đầu từ đâu?",
]


def detect_item_type(message):
    if re.search(r"khóa học|khoa hoc|course", message, re.IGNORECASE):
        return "Khóa học"
    if re.search(r"tài liệu|tai lieu|document|sách|sach|giáo trình|giao trinh", message, re.IGNORECASE):
        return "Tài liệu"
    return None


def detect_response_mode(message):
    """Soft classification for response structure — not routing."""
    norm = strip_accents(message)   # bỏ dấu để khớp mẫu (vd "lộ trình" -> "lo trinh")
    # "tu dau"/"tu con so 0" = học từ con số không -> cũng là tín hiệu lộ trình (cạnh "tu zero").
    if re.search(r"lo trinh|roadmap|bat dau|co ban|nang cao|tu zero|tu dau|tu con so 0|learning path", norm):
        return "learning_path"
    if re.search(r"so sanh|compare|khac nhau|difference", norm):
        return "compare"
    # "co ... nao" = "có khóa học/tài liệu nào (về) ..." -> ý liệt kê/tìm kiếm tài nguyên.
    if re.search(r"tim|search|tra cuu|co gi ve|\bco\b .*\bnao\b|liet ke|list|show", norm):
        return "search"
    if re.search(r"goi y|recommend|nen hoc|tu van|phu hop|tuong tu", norm):
        return "recommend"
    return "answer"


# Từ khóa (đã bỏ dấu) để xếp độ khó cho lộ trình học.
_BEGINNER_KW = ["co ban", "nhap mon", "can ban", "beginner", "fundamental",
                "introduction", "bat dau", "zero", "101", "basic", "lam quen"]
_ADVANCED_KW = ["nang cao", "advanced", "chuyen sau", "master", "expert",
                "production", "scale", "toi uu", "kien truc", "architecture"]


_LEVEL_TO_RANK = {"co ban": 0, "trung cap": 1, "nang cao": 2}


def difficulty_rank(item):
    """0 = nền tảng, 1 = trung cấp, 2 = nâng cao.

    Ưu tiên trường `level` THẬT trong catalog (chính xác nhất). Nếu dataset cũ
    không có `level`, mới suy ra từ từ khóa tiêu đề/chủ đề/mô tả (kiểm tra từ khóa
    nền tảng TRƯỚC nâng cao để khóa "Cơ bản đến nâng cao X" vẫn coi là điểm khởi đầu).
    """
    level = strip_accents(str(item.get("level", ""))).strip()
    if level in _LEVEL_TO_RANK:
        return _LEVEL_TO_RANK[level]

    text = strip_accents(
        f"{item.get('title', '')} {item.get('topics', '')} {item.get('description', '')}"
    )
    if any(k in text for k in _BEGINNER_KW):
        return 0
    if any(k in text for k in _ADVANCED_KW):
        return 2
    return 1


def suggest_followups(query, category, all_items, mode=None):
    """Gợi ý câu hỏi tiếp theo theo ngữ cảnh — tránh lặp lại đúng ý vừa hỏi."""
    cat = category or (all_items[0]["category"] if all_items else "lĩnh vực này")
    pool = [
        ("learning_path", f"Lộ trình học {cat} từ cơ bản đến nâng cao"),
        ("compare", f"So sánh các khóa học nổi bật về {cat}"),
        ("recommend", f"Gợi ý tài liệu thực hành {cat} cho người mới"),
        ("answer", f"{cat} cần chuẩn bị kiến thức nền nào trước?"),
        ("search", f"Có những khóa học {cat} nào đáng học nhất?"),
    ]
    picks = [q for m, q in pool if m != mode]
    return picks[:3]


def followup_block(query, category, all_items, mode=None):
    qs = suggest_followups(query, category, all_items, mode=mode)
    lines = "\n".join(f"- {q}" for q in qs)
    return f"\n\n---\n### 💡 Có thể bạn muốn hỏi tiếp\n{lines}"


def dedupe_items(items):
    seen = set()
    result = []
    for item in items:
        key = item["item_id"]
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def matched_keywords(query, item, limit=5):
    """Từ khóa trong truy vấn thực sự xuất hiện ở mục — để giải thích độ bám sát.

    Hiển thị nguyên từ người dùng gõ (không stem) cho dễ đọc; vẫn khớp linh hoạt
    bằng cách so cả gốc đã rút (stem) lẫn từ nguyên trong văn bản mục.
    """
    hay = normalize_text(
        f"{item.get('title', '')} {item.get('topics', '')} "
        f"{item.get('category', '')} {item.get('description', '')}"
    )
    words = [
        w for w in dict.fromkeys(normalize_text(query).split())  # giữ thứ tự, bỏ trùng
        if len(w) > 2 and w not in QUERY_STOP_WORDS
    ]
    hay_tokens = hay.split()
    hits = []
    for w in words:
        # khớp trực tiếp, hoặc khớp tiền tố 5 ký tự (bắt biến thể "learning"/"learn", số nhiều)
        if w in hay or (len(w) >= 5 and any(t.startswith(w[:5]) for t in hay_tokens)):
            hits.append(w)
    return hits[:limit]


def grounding_line(query, item):
    """Một dòng 'Vì sao phù hợp' bám sát từ khóa người dùng hỏi."""
    hits = matched_keywords(query, item)
    if not hits:
        return ""
    kws = ", ".join(f"`{k}`" for k in hits)
    return f"\n\n🎯 **Bám sát câu hỏi của bạn** — khớp trực tiếp các từ khóa: {kws}."


def format_sources_inline(items, limit=5):
    lines = []
    for i, item in enumerate(items[:limit], 1):
        score = f" · {item['score']}% phù hợp" if "score" in item else ""
        lines.append(
            f"**{i}. {item['title']}** — {item['type']} · {item['category']}{score}\n"
            f"> {item['description'][:180]}{'...' if len(item['description']) > 180 else ''}\n"
            f"> 👤 {item['instructor']} · 🌐 {item['platform']}"
        )
    return "\n\n".join(lines)


def topics_list(item):
    """Tách danh sách chủ đề sạch từ trường 'topics' của catalog."""
    return [t.strip() for t in str(item.get("topics", "")).split(",") if t.strip()]


def primary_topic(item):
    """Chủ đề chính (ngôn ngữ/công nghệ) của mục — dùng để đa dạng hóa lộ trình."""
    tl = topics_list(item)
    return strip_accents(tl[0]) if tl else ""


def dominant_category(sources, top=5):
    """Chuyên mục chiếm đa số trong các nguồn truy hồi đầu bảng.

    Đáng tin hơn đoán chuyên mục theo từ khóa truy vấn: nếu truy hồi ngữ nghĩa đã
    trả về toàn mục Machine Learning thì chuyên mục đúng là 'Trí tuệ nhân tạo' bất kể
    câu hỏi diễn đạt thế nào. Trả None nếu không có nguồn.
    """
    from collections import Counter
    cats = [s["item"].get("category") for s in sources[:top] if s.get("item")]
    cats = [c for c in cats if c]
    if not cats:
        return None
    return Counter(cats).most_common(1)[0][0]


def category_stage_items(item_list, category, level, exclude_ids, k, query=None, diversify=True):
    """Lấy thêm mục ĐÚNG CẤP ĐỘ từ chuyên mục trong catalog để lấp đầy giai đoạn.

    Vì truy hồi theo độ tương đồng có thể bỏ sót mục nền tảng (vd 'lập trình cơ bản'
    trả về nhiều mục nâng cao), ta bổ sung trực tiếp từ data file: chọn mục có
    difficulty_rank == level, ưu tiên ĐA DẠNG chủ đề chính (mỗi ngôn ngữ một mục)
    để Giai đoạn 1 không bị trùng (vd 4 khóa C) mà phủ Python, Java, JS...

    Nếu người dùng có nêu công nghệ cụ thể (vd 'Python'), các mục khớp đúng công
    nghệ đó được ưu tiên lên trước rồi mới đa dạng hóa phần còn lại.
    """
    if not category:
        return []
    q_terms = {strip_accents(t) for t in normalize_text(query).split()} if query else set()

    candidates = []
    for _, row in item_list[item_list["category"] == category].iterrows():
        item = row_to_dict(row)
        if item["item_id"] in exclude_ids or difficulty_rank(item) != level:
            continue
        pt = primary_topic(item)
        # khớp công nghệ người dùng hỏi (theo chủ đề chính hoặc tiêu đề) -> ưu tiên cao
        hay = strip_accents(normalize_text(f"{item['title']} {item['topics']}"))
        matches_q = bool(q_terms) and (
            any(t in pt for t in q_terms if len(t) > 2)
            or any(t in hay for t in q_terms if len(t) > 2)
        )
        candidates.append((0 if matches_q else 1, pt, item))

    candidates.sort(key=lambda x: x[0])  # ổn định: mục khớp truy vấn lên trước

    picked, seen_topic, leftover = [], set(), []
    for _, pt, item in candidates:
        if diversify and pt and pt in seen_topic:
            leftover.append(item)
            continue
        seen_topic.add(pt)
        picked.append(item)
        if len(picked) >= k:
            return picked
    for item in leftover:  # chưa đủ chủ đề khác nhau -> bù phần còn lại
        if len(picked) >= k:
            break
        picked.append(item)
    return picked


def format_item_detailed(item, idx=None, query=None):
    """Khối mô tả CHI TIẾT cho một mục — chỉ dùng dữ liệu thật từ catalog.

    Gồm: tiêu đề, loại/chuyên mục/%phù hợp, MÔ TẢ ĐẦY ĐỦ (không cắt), liệt kê
    từng chủ đề, giảng viên/tác giả, nền tảng, từ khóa khớp câu hỏi, và link.
    """
    head = f"{idx}. " if idx is not None else ""
    score = f" · **{item['score']}% phù hợp**" if "score" in item else ""
    lvl = f" · 🎚️ {item['level']}" if item.get("level") else ""
    parts = [f"**{head}{item['title']}**  \n`{item['type']}`{lvl} · 📂 {item['category']}{score}"]

    desc = str(item.get("description", "")).strip()
    if desc:
        parts.append(f"> {desc}")  # mô tả đầy đủ, không cắt

    tl = topics_list(item)
    if tl:
        parts.append("🧩 **Chủ đề bạn sẽ học:** " + " · ".join(f"`{t}`" for t in tl))

    meta = []
    if item.get("instructor"):
        meta.append(f"👤 {item['instructor']}")
    if item.get("platform"):
        meta.append(f"🌐 {item['platform']}")
    if meta:
        parts.append(" · ".join(meta))

    if query:
        hits = matched_keywords(query, item)
        if hits:
            parts.append("🎯 **Khớp câu hỏi:** " + ", ".join(f"`{k}`" for k in hits))

    if item.get("link"):
        parts.append(f"🔗 [Mở tài nguyên này →]({item['link']})")

    return "\n\n".join(parts)


def format_items_detailed(items, start=1, query=None):
    blocks = [
        format_item_detailed(it, idx=i, query=query)
        for i, it in enumerate(items, start)
    ]
    return "\n\n".join(blocks)


def stage_overview(items):
    """Tổng hợp số liệu THẬT của riêng các mục trong một giai đoạn (chỉ từ catalog).

    Trả về đoạn markdown: số khóa học/tài liệu, chủ đề trọng tâm, nền tảng,
    và 'kỹ năng đạt được' = hợp các chủ đề của đúng những mục này.
    """
    if not items:
        return ""
    facts = aggregate_facts(items)
    skills = []
    for it in items:
        for t in topics_list(it):
            if t not in skills:
                skills.append(t)

    lines = [
        f"> 📦 **Tài nguyên giai đoạn:** {facts['courses']} khóa học · {facts['docs']} tài liệu"
    ]
    if facts["platforms"]:
        lines.append(f"> 🌐 **Nền tảng:** {', '.join(facts['platforms'])}")
    if skills:
        lines.append(f"> ✅ **Kỹ năng đạt được:** {', '.join(skills[:8])}")
    return "\n".join(lines)


# Ngữ cảnh lĩnh vực — giúp câu trả lời "có kiến thức nền" như trợ lý thật, không chỉ liệt kê.
CATEGORY_CONTEXT = {
    "An ninh mạng": "An ninh mạng (Cybersecurity) là việc bảo vệ hệ thống, mạng và dữ liệu khỏi tấn công. Bạn sẽ đi qua các mảng như bảo mật web, kiểm thử xâm nhập (pentest), mã hóa và phòng thủ hệ thống.",
    "Cơ sở dữ liệu": "Cơ sở dữ liệu là nền tảng lưu trữ và truy vấn dữ liệu của mọi ứng dụng. Lĩnh vực này bao trùm SQL/NoSQL, thiết kế schema, tối ưu truy vấn và quản trị dữ liệu.",
    "Cấu trúc dữ liệu & Giải thuật": "Cấu trúc dữ liệu & Giải thuật (DSA) là tư duy cốt lõi của lập trình hiệu quả và là phần cực kỳ quan trọng khi phỏng vấn. Bạn sẽ học mảng, cây, đồ thị, sắp xếp, tìm kiếm và cách tối ưu độ phức tạp.",
    "DevOps": "DevOps kết nối phát triển và vận hành để giao phần mềm nhanh và ổn định. Trọng tâm gồm CI/CD, container (Docker/Kubernetes), hạ tầng dạng mã (IaC) và giám sát.",
    "Dữ liệu lớn": "Dữ liệu lớn (Big Data) tập trung xử lý khối lượng dữ liệu khổng lồ vượt khả năng công cụ truyền thống. Bạn sẽ tiếp cận Hadoop, Spark, Kafka, data warehouse và xử lý luồng.",
    "Khoa học dữ liệu": "Khoa học dữ liệu biến dữ liệu thô thành hiểu biết và quyết định. Nó kết hợp thống kê, trực quan hóa, xử lý dữ liệu (Pandas) và mô hình hóa.",
    "Khoa học máy tính": "Khoa học máy tính là nền tảng lý thuyết của ngành: hệ điều hành, kiến trúc máy tính, mạng, trình biên dịch và lý thuyết tính toán. Đây là kiến thức gốc giúp bạn hiểu sâu mọi công nghệ phía trên.",
    "Kỹ thuật phần mềm": "Kỹ thuật phần mềm tập trung vào cách xây dựng phần mềm chất lượng, dễ bảo trì ở quy mô lớn. Bạn sẽ học kiến trúc, design pattern (SOLID, MVC), microservices và quy trình phát triển.",
    "Lập trình": "Lập trình là kỹ năng nền tảng để biến ý tưởng thành phần mềm. Phần này giúp bạn nắm vững cú pháp ngôn ngữ, tư duy giải quyết vấn đề và viết code sạch.",
    "Lập trình Mobile": "Lập trình Mobile là phát triển ứng dụng cho điện thoại (iOS, Android). Bạn sẽ tiếp cận Swift/Kotlin hoặc framework đa nền tảng như Flutter, React Native.",
    "Lập trình Web": "Lập trình Web gồm xây dựng giao diện (frontend) và phía máy chủ (backend). Bạn sẽ học HTML/CSS/JS, các framework như React/Vue/Next.js và cách xử lý API, cơ sở dữ liệu.",
    "Phát triển Game": "Phát triển Game kết hợp lập trình, đồ họa và thiết kế trải nghiệm. Trọng tâm gồm engine (Unity/Unreal), vật lý game, gameplay và tối ưu hiệu năng.",
    "Trí tuệ nhân tạo": "Trí tuệ nhân tạo (AI) giúp máy học và ra quyết định từ dữ liệu. Lĩnh vực trải dài machine learning, deep learning, mạng nơ-ron, NLP và các mô hình ngôn ngữ lớn (LLM).",
    "Điện toán đám mây": "Điện toán đám mây cung cấp hạ tầng và dịch vụ qua Internet (AWS, Azure, GCP). Bạn sẽ học triển khai, mở rộng, lưu trữ và kiến trúc hệ thống trên cloud.",
    "Mạng máy tính": "Mạng máy tính là cách các thiết bị kết nối và trao đổi dữ liệu. Bạn sẽ học mô hình TCP/IP/OSI, định tuyến, chuyển mạch, DNS, VPN và xử lý sự cố mạng.",
    "Kiểm thử phần mềm": "Kiểm thử phần mềm đảm bảo chất lượng và độ tin cậy của sản phẩm. Lĩnh vực gồm unit/integration test, tự động hóa (Selenium, Cypress), TDD/BDD và kiểm thử hiệu năng.",
    "Thiết kế UI/UX": "Thiết kế UI/UX tập trung vào trải nghiệm và giao diện người dùng. Bạn sẽ học nghiên cứu người dùng, wireframe, prototype (Figma) và design system.",
    "Blockchain & Web3": "Blockchain & Web3 xây dựng ứng dụng phi tập trung trên sổ cái phân tán. Trọng tâm gồm Ethereum, smart contract (Solidity), DeFi, NFT và DApp.",
    "IoT & Hệ thống nhúng": "IoT & Hệ thống nhúng lập trình cho thiết bị phần cứng và cảm biến. Bạn sẽ làm việc với Arduino, ESP32, MQTT, embedded C và RTOS.",
    "MLOps & AI Engineering": "MLOps đưa mô hình AI/ML vào vận hành thực tế một cách ổn định. Trọng tâm gồm triển khai, giám sát mô hình, CI/CD cho ML, MLflow và LLMOps.",
    "Quản trị hệ thống & Linux": "Quản trị hệ thống & Linux vận hành máy chủ và hạ tầng. Bạn sẽ thành thạo Linux, shell scripting, SSH, Nginx/Apache, ảo hóa và giám sát.",
    "Quản lý dự án CNTT": "Quản lý dự án CNTT điều phối con người và tiến độ để giao sản phẩm. Bạn sẽ học Agile, Scrum, Kanban, quản lý rủi ro và công cụ như Jira.",
    "AR/VR & Thực tế ảo": "AR/VR tạo trải nghiệm thực tế tăng cường và thực tế ảo. Trọng tâm gồm Unity XR, ARKit/ARCore, mô hình 3D và tương tác không gian.",
    "Đồ họa máy tính": "Đồ họa máy tính nghiên cứu cách máy tính tạo và xử lý hình ảnh. Bạn sẽ học OpenGL/Vulkan, shader, rendering, ray tracing và lập trình GPU.",
    "Phân tích nghiệp vụ (BA)": "Phân tích nghiệp vụ là cầu nối giữa nghiệp vụ và kỹ thuật. Bạn sẽ học thu thập yêu cầu, mô hình hóa quy trình (UML/BPMN), use case và viết tài liệu.",
    "Điện toán lượng tử": "Điện toán lượng tử dùng quy luật cơ học lượng tử để tính toán vượt giới hạn máy tính cổ điển. Bạn sẽ tiếp cận qubit, cổng lượng tử, Qiskit và các thuật toán Shor/Grover.",
}

# Ngữ cảnh theo từ khóa (key đã bỏ dấu để khớp với strip_accents).
TOPIC_CONTEXT = {
    "machine learning": "Machine Learning dạy máy tự rút quy luật từ dữ liệu thay vì lập trình thủ công từng luật.",
    "deep learning": "Deep Learning dùng mạng nơ-ron nhiều lớp, đặc biệt mạnh với ảnh, ngôn ngữ và dữ liệu phi cấu trúc.",
    "docker": "Docker đóng gói ứng dụng vào container để chạy đồng nhất ở mọi môi trường.",
    "kubernetes": "Kubernetes tự động điều phối và mở rộng hàng loạt container ở quy mô lớn.",
    "react": "React là thư viện UI dạng component được dùng phổ biến nhất cho frontend.",
    "python": "Python dễ học, đa dụng và là ngôn ngữ chủ lực cho AI/ML lẫn khoa học dữ liệu.",
    "javascript": "JavaScript là ngôn ngữ của web, chạy được cả ở trình duyệt lẫn máy chủ (Node.js).",
    "sql": "SQL là ngôn ngữ chuẩn để truy vấn và thao tác dữ liệu quan hệ.",
    "owasp": "OWASP tổng hợp các lỗ hổng bảo mật web phổ biến nhất mà lập trình viên cần phòng tránh.",
    "llm": "LLM (mô hình ngôn ngữ lớn) là nền tảng của các trợ lý AI hiện đại như ChatGPT, Claude.",
    "spark": "Apache Spark xử lý dữ liệu lớn song song, nhanh hơn nhiều so với MapReduce truyền thống.",
    "kafka": "Apache Kafka là nền tảng truyền dữ liệu theo luồng (streaming) thời gian thực.",
    "tcp": "TCP/IP là bộ giao thức nền tảng giúp các máy tính giao tiếp qua mạng.",
    "neural network": "Mạng nơ-ron mô phỏng cách não bộ liên kết tín hiệu để học các mẫu phức tạp.",
}

# Mở đầu thân thiện, xoay vòng theo độ dài câu hỏi để tránh máy móc.
_INTROS = [
    "Câu hỏi rất hay! ",
    "Rất vui được đồng hành cùng bạn. ",
    "Được thôi, để mình gợi ý cho bạn nhé. ",
    "Mình hiểu bạn đang quan tâm chủ đề này. ",
]


def _pick(seq, key):
    return seq[len(str(key)) % len(seq)]


def aggregate_facts(items):
    """Tổng hợp đặc điểm của tập tài nguyên để viết đoạn ngữ cảnh tự nhiên."""
    from collections import Counter

    topic_counter = Counter()
    for it in items:
        for t in str(it.get("topics", "")).split(","):
            t = t.strip()
            if t:
                topic_counter[t] += 1
    courses = sum(1 for i in items if i.get("type") == "Khóa học")
    docs = sum(1 for i in items if i.get("type") == "Tài liệu")
    platforms = []
    for i in items:
        p = i.get("platform")
        if p and p not in platforms:
            platforms.append(p)
    diff = {0: 0, 1: 0, 2: 0}
    for i in items:
        diff[difficulty_rank(i)] += 1
    return {
        "top_topics": [t for t, _ in topic_counter.most_common(5)],
        "courses": courses,
        "docs": docs,
        "platforms": platforms[:4],
        "diff": diff,
    }


def topic_context_snippets(query, items, limit=2):
    hay = strip_accents(query + " " + " ".join(str(i.get("topics", "")) for i in items[:3]))
    out = []
    for key, blurb in TOPIC_CONTEXT.items():
        if key in hay:
            out.append(blurb)
        if len(out) >= limit:
            break
    return out


def build_overview(query, items, category):
    """Bức tranh TÀI NGUYÊN trong catalog (số khóa học/tài liệu, chủ đề, độ trải cấp độ).

    Phần KHÁI NIỆM của lĩnh vực/từ khóa đã tách sang `concept_overview_block` (đặt lên
    đầu câu trả lời) -> ở đây chỉ còn đoạn tổng hợp về tài nguyên, tránh lặp ngữ cảnh.
    """
    facts = aggregate_facts(items)
    agg = f"Trong catalog mình tìm được **{facts['courses']} khóa học** và **{facts['docs']} tài liệu** liên quan"
    if facts["top_topics"]:
        agg += f", xoay quanh các chủ đề như *{', '.join(facts['top_topics'][:4])}*"
    agg += "."
    spread = facts["diff"]
    if spread[0] and spread[2]:
        agg += " Nội dung trải từ mức nền tảng đến nâng cao nên bạn có thể đi theo lộ trình tăng dần."
    return agg


def concept_overview_block(query, items, category):
    """Khối MỞ ĐẦU mọi câu trả lời IT: khái niệm chung của từ khóa, nhìn đa khía cạnh.

    Theo yêu cầu sản phẩm — MỌI câu trả lời cho câu hỏi CNTT phải nêu KHÁI NIỆM cốt lõi
    của từ khóa TRƯỚC, rồi mới tới gợi ý/lộ trình/tìm kiếm. Thứ tự ưu tiên nguồn khái niệm:
      1) Định nghĩa cụ thể trong glossary (kb.CONCEPTS) — chính xác nhất cho từ khóa.
      2) Ngữ cảnh lĩnh vực (CATEGORY_CONTEXT) — khái niệm chung của cả mảng CNTT.
      3) Các đoạn TOPIC_CONTEXT khớp truy vấn — dự phòng.
    "Đa khía cạnh" = gắn định nghĩa từ khóa với bức tranh lĩnh vực + các khái niệm liên quan.
    Trả về chuỗi markdown kết thúc bằng '---' (ngăn cách phần sau), hoặc "" nếu không có gì.
    """
    # Quét TẤT CẢ từ khóa CNTT trong câu (không chỉ 1) -> nêu khái niệm cho từng cái.
    keys = kb.safe_concepts(query, limit=4)
    key = keys[0] if keys else None
    parts, title = [], None

    if key:
        c = kb.CONCEPTS[key]
        title = c["name"]
        if c.get("def"):
            parts.append(c["def"])
        # Đa khía cạnh: đặt khái niệm vào bức tranh lĩnh vực CNTT rộng hơn.
        cat = c.get("category")
        if cat and cat in CATEGORY_CONTEXT and CATEGORY_CONTEXT[cat] not in parts:
            parts.append(CATEGORY_CONTEXT[cat])
        if c.get("example"):
            parts.append(f"💡 **Ví dụ:** {c['example']}")
        rel = [kb.CONCEPTS[r]["name"] for r in c.get("related", []) if r in kb.CONCEPTS]
        if rel:
            parts.append("🔗 **Khái niệm liên quan:** " + ", ".join(f"*{r}*" for r in rel))
        # CÁC TỪ KHÓA KHÁC trong câu: nêu định nghĩa NGẮN (1 câu) cho mỗi từ -> người dùng
        # hiểu rõ mọi thuật ngữ mình hỏi, không chỉ từ khóa chính.
        extra_lines = []
        for k in keys[1:]:
            ce = kb.CONCEPTS[k]
            short = (ce.get("def") or "").split(". ")[0].strip().rstrip(".")
            if short:
                extra_lines.append(f"- **{ce['name']}**: {short}.")
        if extra_lines:
            parts.append("📌 **Các từ khóa khác trong câu hỏi:**\n" + "\n".join(extra_lines))
    else:
        # Không khớp khái niệm cụ thể -> dùng ngữ cảnh lĩnh vực / chủ đề làm khái niệm chung.
        if category and category in CATEGORY_CONTEXT:
            title = category
            parts.append(CATEGORY_CONTEXT[category])
        parts.extend(topic_context_snippets(query, items, limit=2))

    parts = list(dict.fromkeys(p for p in parts if p))  # bỏ trùng, giữ thứ tự
    if not parts:
        return ""
    head = f"## 📖 Khái niệm: {title}\n\n" if title else "## 📖 Khái niệm\n\n"
    return head + "\n\n".join(parts) + "\n\n---\n\n"


def practical_tips(category, all_items):
    """Vài lời khuyên thực hành, có ngữ cảnh theo lĩnh vực."""
    facts = aggregate_facts(all_items)
    tips = []
    if facts["courses"] and facts["docs"]:
        tips.append("Kết hợp **khóa học** (học có hướng dẫn) với **tài liệu** (tra cứu sâu) để hiểu chắc hơn.")
    tips.append("Vừa học vừa làm một **dự án nhỏ** để biến kiến thức thành kỹ năng thực tế.")
    if facts["platforms"]:
        tips.append(f"Các nền tảng đáng tham khảo: {', '.join(facts['platforms'])}.")
    domain_tip = {
        "Trí tuệ nhân tạo": "Nắm vững toán nền (đại số tuyến tính, xác suất) sẽ giúp bạn học AI nhanh hơn rất nhiều.",
        "An ninh mạng": "Luyện tập trên môi trường mô phỏng (CTF, lab) thay vì thử trên hệ thống thật.",
        "Lập trình Web": "Học chắc HTML/CSS/JS trước khi nhảy vào framework để không bị 'hổng gốc'.",
        "DevOps": "Tự dựng một pipeline CI/CD đơn giản là cách học DevOps hiệu quả nhất.",
        "Khoa học dữ liệu": "Thực hành trên bộ dữ liệu thật (Kaggle) để rèn tư duy phân tích.",
        "Cấu trúc dữ liệu & Giải thuật": "Luyện đều trên LeetCode/HackerRank để giải thuật trở thành phản xạ.",
    }.get(category)
    if domain_tip:
        tips.insert(0, domain_tip)
    return "\n".join(f"- {t}" for t in tips[:4])


def synthesize_answer(query, sources, recommendations, mode, category=None, item_list=None):
    """Soạn câu trả lời GIÀU NGỮ CẢNH, bám sát catalog, không cần LLM."""
    if not sources:
        return (
            "Tôi chưa tìm thấy tài nguyên phù hợp trong catalog với câu hỏi này. "
            "Tôi chuyên hỗ trợ các chủ đề **CNTT** (lập trình, web, AI/ML, dữ liệu, "
            "cloud, DevOps, an ninh mạng, mobile...).\n\n"
            "Bạn có thể thử:\n"
            "- Nêu rõ lĩnh vực (VD: *Machine Learning*, *DevOps*, *An ninh mạng*)\n"
            "- Chỉ định loại: *khóa học* hoặc *tài liệu*\n"
            "- Mô tả mục tiêu học tập cụ thể hơn"
        )

    top = sources[0]["item"]
    all_items = dedupe_items([s["item"] for s in sources] + recommendations)
    foot = followup_block(query, category, all_items, mode=mode)
    intro = _pick(_INTROS, query)
    overview = build_overview(query, all_items, category)
    tips = practical_tips(category, all_items)
    tips_block = f"\n\n### 🎯 Lời khuyên cho bạn\n{tips}" if tips else ""

    if mode == "learning_path":
        # Xếp theo độ khó (nền tảng -> nâng cao), giữ thứ tự liên quan trong mỗi bậc.
        staged = sorted(enumerate(all_items), key=lambda x: (difficulty_rank(x[1]), x[0]))
        ordered = [it for _, it in staged]
        used = []

        def take(pred, k):
            picked = []
            for it in ordered:
                if it in used:
                    continue
                if pred(it):
                    picked.append(it)
                    used.append(it)
                if len(picked) >= k:
                    break
            return picked

        basics = take(lambda it: difficulty_rank(it) == 0, 3)
        mids = take(lambda it: difficulty_rank(it) == 1, 4)
        adv = take(lambda it: difficulty_rank(it) == 2, 3)

        # Bổ sung mục đúng cấp độ + đa dạng ngôn ngữ TỪ chuyên mục trong catalog,
        # để mỗi giai đoạn đủ mục và phủ nhiều ngôn ngữ (Python, Java, JS...),
        # tránh tình trạng "lập trình cơ bản" mà thiếu mục nền tảng / thiếu Python.
        if item_list is not None and category:
            used_ids = {it["item_id"] for it in used}

            def backfill(stage, level, target):
                need = target - len(stage)
                if need <= 0:
                    return stage
                extra = category_stage_items(
                    item_list, category, level, used_ids, need, query=query
                )
                for it in extra:
                    used_ids.add(it["item_id"])
                return stage + extra

            basics = backfill(basics, 0, 3)
            mids = backfill(mids, 1, 4)
            adv = backfill(adv, 2, 3)

        # Bảo hiểm cuối: nếu vẫn rỗng (không phát hiện chuyên mục), lấy tạm theo độ liên quan.
        basics = basics or take(lambda it: True, 3)
        mids = mids or take(lambda it: True, 4)

        def render_stage(emoji, name, subtitle, goal, items, start):
            if not items:
                return "", start
            head = (
                f"\n\n### {emoji} {name}\n"
                f"_{subtitle}_\n\n"
                f"{stage_overview(items)}\n\n"
                f"🎯 **Mục tiêu giai đoạn:** {goal}\n\n"
            )
            body = format_items_detailed(items, start=start, query=query)
            return head + body, start + len(items)

        out = "## 🗺️ Lộ trình học tập"
        if category:
            out += f" — {category}"
        out += f"\n\n{intro}{overview}\n\n"
        n_stages = sum(1 for s in (basics, mids, adv) if s)
        out += (
            f"Dựa trên *\"{query}\"*, mình thiết kế lộ trình **{n_stages} giai đoạn** dưới đây — "
            f"toàn bộ tài nguyên đều lấy trực tiếp từ catalog ({len(all_items)} mục liên quan), "
            "sắp xếp theo độ khó tăng dần để bạn đi từng bước vững chắc. "
            "Mỗi mục kèm mô tả đầy đủ, chủ đề sẽ học và liên kết truy cập:\n"
        )

        idx = 1
        block, idx = render_stage(
            "🟢", "Giai đoạn 1 — Nền tảng",
            "Nắm vững khái niệm cốt lõi trước khi đi sâu.",
            "Hiểu các khái niệm gốc, làm quen công cụ và hoàn thành bài tập cơ bản đầu tiên.",
            basics[:3], idx,
        )
        out += block
        block, idx = render_stage(
            "🟡", "Giai đoạn 2 — Trung cấp & chuyên môn",
            "Thực hành dự án, đi sâu vào kỹ thuật.",
            "Vận dụng kiến thức vào một dự án thực tế, nắm chắc các kỹ thuật cốt lõi của lĩnh vực.",
            mids[:4], idx,
        )
        out += block
        block, idx = render_stage(
            "🔴", "Giai đoạn 3 — Nâng cao & thực chiến",
            "Tối ưu, kiến trúc, triển khai thực tế.",
            "Làm chủ kiến trúc/triển khai ở quy mô lớn và tối ưu hiệu năng cho bài toán thực.",
            adv[:3], idx,
        )
        out += block

        out += tips_block
        out += (
            "\n\n💪 Cứ đi tuần tự từng giai đoạn, hoàn thành một **dự án nhỏ** ở mỗi bước "
            "rồi mới sang giai đoạn sau — đó là cách tiến bộ nhanh và chắc nhất. Chúc bạn học vui!"
        )
        return out + foot

    if mode == "compare":
        picks = all_items[:5]
        out = f"## ⚖️ So sánh tài nguyên liên quan\n\n{intro}{overview}\n\n"
        out += f"Với *\"{query}\"*, dưới đây là các lựa chọn nổi bật để bạn cân nhắc:\n\n"
        out += format_items_detailed(picks, query=query)
        categories = sorted({i["category"] for i in picks})
        courses = [i for i in picks if i["type"] == "Khóa học"]
        docs = [i for i in picks if i["type"] == "Tài liệu"]
        out += "\n\n### 📊 Nên chọn cái nào?\n"
        out += f"- **Phạm vi:** {len(picks)} tài nguyên thuộc {len(categories)} chuyên mục ({', '.join(categories)}).\n"
        out += f"- **Loại hình:** {len(courses)} khóa học, {len(docs)} tài liệu.\n"
        if courses:
            out += f"- **Muốn học có hướng dẫn bài bản** → ưu tiên *{courses[0]['title']}* trên {courses[0]['platform']}.\n"
        if docs:
            out += f"- **Muốn tra cứu nhanh / tự đọc sâu** → chọn *{docs[0]['title']}*.\n"
        out += "- **Người mới** nên bắt đầu từ mục có chữ *cơ bản/nhập môn*; đã có nền thì nhảy thẳng vào mục *nâng cao*.\n"
        out += tips_block
        return out + foot

    if mode == "search":
        out = f"## 🔍 Kết quả tìm kiếm\n\n{intro}{overview}\n\n"
        out += f"Mình tìm thấy **{len(all_items)}** tài nguyên liên quan đến *\"{query}\"*, "
        out += "xếp theo độ phù hợp giảm dần (kèm mô tả đầy đủ, chủ đề và liên kết):\n\n"
        out += format_items_detailed(all_items[:6], query=query)
        out += tips_block
        return out + foot

    if mode == "recommend":
        out = f"## 💡 Gợi ý học tập\n\n{intro}{overview}\n\n"
        out += (
            f"Phù hợp nhất với yêu cầu của bạn là **{top['title']}** "
            f"({top['type']} · {top['category']}) — và đây là lý do mình chọn nó:\n\n"
        )
        out += f"> {top['description'][:280]}{'...' if len(top['description']) > 280 else ''}\n\n"
        out += f"👤 {top['instructor']} · 🌐 {top['platform']}"
        if str(top.get("topics", "")).strip():
            out += f" · 🏷️ {top['topics']}"
        out += grounding_line(query, top)
        out += "\n\n### Một vài lựa chọn liên quan khác\n\n"
        others = [i for i in all_items if i["item_id"] != top["item_id"]]
        out += format_items_detailed(others[:5], query=query)
        out += tips_block
        return out + foot

    # Mặc định: trả lời trực tiếp + giải thích khái niệm tổng hợp từ catalog
    out = f"## 💬 Trả lời\n\n{intro}{overview}\n\n"
    out += (
        f"Đi vào câu hỏi *\"{query}\"*: nội dung sát nhất trong catalog là "
        f"**{top['title']}** ({top['type']} · {top['category']}). Cụ thể:\n\n"
    )
    out += f"{top['description']}\n\n"
    out += f"- **Giảng viên/Tác giả:** {top['instructor']}\n"
    out += f"- **Nền tảng:** {top['platform']}\n"
    out += f"- **Chủ đề chính:** {top['topics']}\n"
    out += grounding_line(query, top)

    others = [i for i in all_items[1:] if i["item_id"] != top["item_id"]]
    if others:
        out += "\n### 📚 Tài nguyên liên quan khác\n\n"
        out += format_items_detailed(others[:4], query=query)
    out += tips_block
    return out + foot


def try_llm_response(system_prompt, user_message, history=None):
    """Sinh câu trả lời bằng LLM: ưu tiên Claude (mới nhất) → OpenAI → Ollama.

    Tất cả đều chịu lỗi: thiếu key/lỗi mạng -> trả None để rơi về bộ tổng hợp cục bộ.
    """
    # Lịch sử hội thoại dạng chung (Claude dùng riêng system, không nằm trong messages).
    history_msgs = []
    if history:
        for msg in history[-6:]:
            if msg["role"] in ("user", "assistant"):
                history_msgs.append({"role": msg["role"], "content": msg["content"]})

    # 1) Claude (Anthropic) — LLM hàng đầu hiện nay; mặc định claude-opus-4-8.
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=anthropic_key)
            response = client.messages.create(
                model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8"),
                max_tokens=2000,
                # Prompt caching: ngữ cảnh catalog (lớn, ổn định trong phiên) được cache
                # -> các lượt sau trong 5 phút rẻ & nhanh hơn nhiều.
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=history_msgs + [{"role": "user", "content": user_message}],
            )
            if response.stop_reason == "refusal":
                return None
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            return text or None
        except Exception:
            return None

    messages = [{"role": "system", "content": system_prompt}] + history_msgs
    messages.append({"role": "user", "content": user_message})

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=openai_key)
            response = client.chat.completions.create(
                model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                messages=messages,
                temperature=0.3,
                max_tokens=1200,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return None

    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = _ollama_model()   # OLLAMA_MODEL nếu có sẵn, ngược lại tự chọn model đã pull
    try:
        # num_predict: đủ dài cho lộ trình/giải thích (đổi qua OLLAMA_NUM_PREDICT); để nhanh hơn
        # trên CPU có thể dùng model nhỏ hơn (OLLAMA_MODEL=qwen2.5:1.5b) hoặc giảm num_predict.
        # num_predict 384: đủ cho lộ trình/giải thích mà KHÔNG quá lâu trên CPU; timeout 240 nới
        # biên rộng để câu dài KHÔNG chạm timeout rồi âm thầm rơi về template. Đổi qua env nếu cần.
        num_predict = int(os.environ.get("OLLAMA_NUM_PREDICT", "384"))
        # 210s < timeout web gọi chat (240s) -> recommender luôn trả (câu LLM hoặc fallback template)
        # TRƯỚC khi web bỏ cuộc, tránh 502 "không kết nối". CPU chậm: nên dùng qwen2.5:1.5b cho kịp.
        timeout_s = int(os.environ.get("OLLAMA_TIMEOUT", "210"))
        payload = json.dumps(
            {"model": ollama_model, "messages": messages, "stream": False,
             # keep_alive: giữ model trong RAM 2 giờ -> không cold-start giữa phiên demo.
             "keep_alive": "2h", "options": {"num_predict": num_predict, "temperature": 0.5}}
        ).encode()
        req = urllib.request.Request(
            f"{ollama_url.rstrip('/')}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read())
            return data["message"]["content"].strip()
    except Exception:
        return None


def _history_msgs(history):
    """Chuẩn hóa lịch sử hội thoại về list {role, content} (chỉ user/assistant, 6 lượt gần nhất)."""
    out = []
    for msg in (history or [])[-6:]:
        if msg.get("role") in ("user", "assistant"):
            out.append({"role": msg["role"], "content": msg["content"]})
    return out


def _stream_ollama(messages):
    """Generator: gọi Ollama với stream=true -> yield từng mảnh văn bản NGAY khi sinh.

    Nhờ stream, người dùng thấy chữ chạy sau ~1-2s thay vì chờ cả câu (~30-135s trên CPU),
    và byte chảy sớm giúp VƯỢT hard-timeout 30s của proxy/Heroku (tránh 503 'báo lỗi')."""
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = _ollama_model()
    num_predict = int(os.environ.get("OLLAMA_NUM_PREDICT", "384"))
    timeout_s = int(os.environ.get("OLLAMA_TIMEOUT", "210"))
    payload = json.dumps(
        {"model": ollama_model, "messages": messages, "stream": True,
         "keep_alive": "2h", "options": {"num_predict": num_predict, "temperature": 0.5}}
    ).encode()
    req = urllib.request.Request(
        f"{ollama_url.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        for raw in resp:  # Ollama trả NDJSON: mỗi dòng 1 JSON {message:{content}, done}
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            piece = (obj.get("message") or {}).get("content", "")
            if piece:
                yield piece
            if obj.get("done"):
                break


def try_llm_response_stream(system_prompt, user_message, history=None):
    """Bản STREAMING của try_llm_response: yield từng mảnh văn bản (Claude → OpenAI → Ollama).

    Chịu lỗi: nếu lỗi TRƯỚC khi sinh được mảnh nào -> generator rỗng -> caller rơi về template.
    Nếu lỗi GIỮA chừng -> dừng (người dùng đã có phần đã stream)."""
    history_msgs = _history_msgs(history)

    # 1) Claude (Anthropic) — streaming text deltas.
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=anthropic_key)
            with client.messages.stream(
                model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8"),
                max_tokens=2000,
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=history_msgs + [{"role": "user", "content": user_message}],
            ) as stream:
                for text in stream.text_stream:
                    if text:
                        yield text
        except Exception:
            return
        return

    messages = [{"role": "system", "content": system_prompt}] + history_msgs
    messages.append({"role": "user", "content": user_message})

    # 2) OpenAI — streaming deltas.
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=openai_key)
            stream = client.chat.completions.create(
                model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                messages=messages,
                temperature=0.3,
                max_tokens=1200,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception:
            return
        return

    # 3) Ollama (local) — streaming NDJSON.
    try:
        yield from _stream_ollama(messages)
    except Exception:
        return


# Câu SUY LUẬN / HỘI THOẠI MỞ -> đáng gọi LLM (giải thích, vì sao, nên chọn gì...).
# Câu định nghĩa / gợi ý khóa-tài liệu / lộ trình KHÔNG khớp -> dùng template nhanh (grounded,
# ~1s) thay vì LLM chậm (~90s). Giữ demo nhanh mà vẫn có hội thoại AI cho câu mở.
_REASONING_RE = re.compile(
    r"\btai sao\b|\bvi sao\b|khi nao|hoat dong|nhu the nao|the nao|ra sao|nen dung|co nen|"
    r"nen hoc|lam sao|lam the nao|loi ich|uu diem|nhuoc diem|uu nhuoc|quan trong|so voi|"
    r"anh huong|tu van|loi khuyen|nen chon|khac biet|tai uu|hieu qua hon"
)


def _is_reasoning_query(text):
    """True nếu câu mang tính SUY LUẬN/HỘI THOẠI -> nên để LLM trả lời tự nhiên."""
    return bool(_REASONING_RE.search(strip_accents(str(text).lower())))


# Câu GIẢI THÍCH thuần: người dùng muốn HIỂU chủ đề (lý do / cách thức / định nghĩa / công dụng
# / lợi ích) — chỉ cần CÂU TRẢ LỜI TRỌNG TÂM, KHÔNG phải cả lộ trình nhiều giai đoạn. Bộ mẫu này
# BÁM theo nhóm "definition/giải thích" mà intent_router.route_intent nhận diện, để hành vi NHẤT
# QUÁN dù khái niệm có được nhận ra hay không, và dù có/không có LLM (khi LLM lỗi -> rơi về đây).
# CỐ Ý KHÔNG gồm nhóm KHUYÊN/CHỌN ("tư vấn", "nên học", "nên chọn", "lời khuyên") và SO SÁNH —
# các nhóm đó vẫn hợp lý khi sinh lộ trình / gợi ý / so sánh, không ép về trả lời ngắn.
_EXPLAIN_RE = re.compile(
    r"\bvi sao\b|\btai sao\b|\bsao lai\b|"                                  # vì sao / tại sao
    r"nhu the nao|\bthe nao\b|ra sao|hoat dong|van hanh|\bco che\b|"        # như thế nào / hoạt động
    r"\bla gi\b|\bdinh nghia\b|nghia la|y nghia|khai niem|giai thich|tim hieu ve|"  # là gì / định nghĩa / giải thích
    r"khi nao (nen )?dung|\bde lam gi\b|dung de lam gi|"                    # khi nào dùng / để làm gì
    r"loi ich|uu diem|nhuoc diem|uu nhuoc|ban chat"                        # lợi ích / ưu nhược điểm / bản chất
)


def _is_explanation_query(text):
    """True nếu câu là hỏi GIẢI THÍCH (lý do/cách thức/định nghĩa/công dụng/lợi ích) -> trả lời
    ngắn trọng tâm, KHÔNG gen lộ trình template; KHÔNG bao gồm câu khuyên-chọn/so sánh."""
    return bool(_EXPLAIN_RE.search(strip_accents(str(text).lower())))


_OLLAMA_CACHE = {}  # {"t": <thời điểm probe>, "v": <reachable?>, "models": [<tên model đã pull>]}


def _ollama_reachable():
    """Ollama có đang chạy & gọi được không? Probe /api/tags (timeout NGẮN) + CACHE (TTL 30s),
    đồng thời nhớ danh sách model đã `pull`.

    Mục đích: TRÁNH TREO ~120s mỗi câu khi cấu hình trỏ tới Ollama nhưng không tới được (vd chạy
    trong Docker mà host.docker.internal bị chặn) — phát hiện sớm rồi rơi về template NGAY.
    """
    now = time.time()
    if now - _OLLAMA_CACHE.get("t", 0) > 30:
        base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        try:
            with urllib.request.urlopen(base + "/api/tags", timeout=3) as r:
                data = json.loads(r.read())
            _OLLAMA_CACHE["models"] = [m.get("name", "") for m in data.get("models", [])]
            _OLLAMA_CACHE["v"] = True
        except Exception:
            _OLLAMA_CACHE["models"] = []
            _OLLAMA_CACHE["v"] = False
        _OLLAMA_CACHE["t"] = now
    return _OLLAMA_CACHE["v"]


def _ollama_model():
    """Chọn model Ollama: OLLAMA_MODEL nếu đặt VÀ có sẵn; nếu không, tự lấy model đã `pull` (ưu
    tiên qwen2.5). Tránh mặc định cũ 'llama3.2' (thường CHƯA pull) -> request hỏng -> rơi template."""
    env_model = os.environ.get("OLLAMA_MODEL")
    _ollama_reachable()  # đảm bảo danh sách model đã được cache
    models = _OLLAMA_CACHE.get("models", [])
    if env_model and (not models or env_model in models):
        return env_model
    if not models:
        return env_model or "qwen2.5:3b"
    for pref in ("qwen2.5:3b", "qwen2.5:1.5b"):
        if pref in models:
            return pref
    return next((m for m in models if "qwen2.5" in m), models[0])


def _llm_available():
    """Có LLM dùng được không: có API key (Claude/OpenAI) HOẶC Ollama đang chạy (TỰ PHÁT HIỆN).

    Nhờ tự phát hiện, chạy recommender NGOÀI Docker (Ollama ở localhost:11434) là LLM tự bật,
    không cần đặt cờ; trong Docker không tới được host -> trả False -> dùng template nhanh (không
    treo). Đặt USE_OLLAMA=0/false để TẮT hẳn nhánh Ollama nếu muốn ép dùng template.
    """
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        return True
    if str(os.environ.get("USE_OLLAMA", "")).lower() in ("0", "false", "no"):
        return False
    return _ollama_reachable()


class EducationalChatbot:
    """Unified chatbot: always retrieve → recommend → synthesize."""

    SYSTEM_PROMPT = """Bạn là trợ lý học tập CNTT chuyên nghiệp tên IT Learning Assistant.

QUY TẮC:
1. Trả lời bằng tiếng Việt, rõ ràng, có cấu trúc (dùng markdown: ##, **, danh sách).
2. DÙNG kiến thức Công nghệ thông tin của bạn để GIẢI THÍCH khái niệm, thuật ngữ, viết tắt
   và trò chuyện TỰ NHIÊN với người dùng ở mọi ngữ cảnh trong ngành (lập trình, web, AI/ML,
   dữ liệu, cloud, DevOps, an ninh mạng, mobile, cơ sở dữ liệu, mạng, hệ điều hành, phần cứng...).
2b. CHỈ trả lời trong phạm vi CÔNG NGHỆ THÔNG TIN. Nếu câu hỏi ngoài CNTT, từ chối lịch sự
    và mời người dùng quay lại chủ đề IT. TUYỆT ĐỐI không trả lời chính trị, đời sống, y tế...
3. Khi GỢI Ý khóa học/tài liệu cụ thể: CHỈ trích từ catalog được cung cấp (không bịa tên khóa
   học). Còn phần giải thích kiến thức thì dùng hiểu biết IT của bạn, chính xác và trung thực.
4. Nếu câu hỏi mơ hồ, trả lời dựa trên nguồn liên quan nhất và gợi ý làm rõ.
5. Với câu hỏi về lộ trình: sắp xếp theo thứ tự cơ bản → nâng cao.
6. Với câu hỏi so sánh: nêu điểm khác biệt giữa các tài nguyên.
7. Giữ câu trả lời súc tích nhưng đầy đủ (200-400 từ).
8. Một ĐỊNH NGHĨA ngắn về từ khóa đã hiển thị ở ĐẦU câu trả lời — ĐỪNG lặp lại định nghĩa.
   Hãy TRẢ LỜI TRỰC TIẾP và đi SÂU vào ĐÚNG câu hỏi bằng kiến thức của bạn, như một bài giải
   thích tổng quan rõ ràng (kiểu tóm tắt kiến thức trên web): nếu hỏi "vì sao / lợi ích / khi nào
   / khác gì" thì nêu các LÝ DO, PHÂN TÍCH cụ thể, có VÍ DỤ thực tế; trình bày CÓ CẤU TRÚC (đoạn
   ngắn hoặc gạch đầu dòng). CHỈ nhắc tới khóa học/tài liệu khi người dùng hỏi gợi ý — và khi nhắc
   thì chỉ trích từ catalog được cung cấp. Tuyệt đối KHÔNG né câu hỏi bằng cách liệt kê khóa học."""

    WELCOME_MESSAGE = (
        "Xin chào! Tôi là **IT Learning Assistant** — trợ lý học tập CNTT thông minh.\n\n"
        "Tôi có thể giúp bạn:\n"
        "- 🔍 **Tìm kiếm** khóa học & tài liệu phù hợp\n"
        "- 💡 **Gợi ý** nội dung học tập cá nhân hóa\n"
        "- 🗺️ **Xây dựng lộ trình** học từ cơ bản đến nâng cao\n"
        "- ❓ **Trả lời** câu hỏi về các lĩnh vực CNTT\n\n"
        "Hãy đặt câu hỏi hoặc chọn gợi ý bên dưới!"
    )

    def __init__(self, item_list, retrieval_model, search_index=None, embed_model=None,
                 query_prefix="", ann=None, reranker=None):
        self.item_list = item_list
        self.retrieval_model = retrieval_model
        self.rag = EducationalRAG(item_list, retrieval_model)
        # Kênh truy hồi NGỮ NGHĨA (embeddings) — cùng engine với tab Tìm kiếm,
        # chất lượng cao hơn nhiều BM25/TF-IDF. Tùy chọn để vẫn chạy nếu thiếu artifacts.
        self.search_index = search_index
        self.embed_model = embed_model
        # Công nghệ truy hồi hiện đại (đều tùy chọn, fallback an toàn nếu thiếu):
        #  - query_prefix: tiền tố model embedding yêu cầu (vd "query: " cho E5)
        #  - ann:          chỉ mục FAISS để truy hồi nhanh
        #  - reranker:     cross-encoder xếp lại top kết quả (tầng 2)
        self.query_prefix = query_prefix
        self.ann = ann
        self.reranker = reranker
        # Vốn từ CNTT để sửa lỗi chính tả / mở rộng viết tắt cho lớp hiểu truy vấn.
        self.vocab = build_query_vocab(retrieval_model, item_list)

    def _is_off_topic(self, query, raw=None):
        """True nếu truy vấn nằm NGOÀI lĩnh vực CNTT (không có mục nào trong catalog đủ liên quan).

        Cổng TẬP TRUNG: chạy SỚM trong chat() -> bao trùm MỌI nhánh (định nghĩa, so sánh,
        lộ trình nghề, truy hồi ngữ nghĩa lẫn BM25 dự phòng), nên handler intent không thể
        trả lời câu lạc đề chỉ vì khớp mẫu "X là gì". Quyết định bằng điểm tương đồng cao
        nhất của truy vấn với toàn catalog (cùng tín hiệu engine truy hồi đang dùng).

        Nếu embeddings chưa nạp -> không chấm được điểm ngữ nghĩa -> trả False (không chặn)
        để tránh chặn oan; lúc đó nhánh BM25 vẫn xử lý như cũ.
        """
        # WHITELIST: câu hỏi khớp KHÁI NIỆM trong glossary CNTT (vd "CNTT là gì",
        # "Docker là gì", "BA, SE") luôn TRONG lĩnh vực -> không chặn. Câu meta/định nghĩa
        # khớp catalog khóa-học kém về ngữ nghĩa nên hay bị cổng chặn oan.
        #  - Alias >= 3 ký tự: khớp thường (token cho từ đơn, chuỗi con cho cụm).
        #  - Alias 1-2 ký tự (viết tắt nghề BA/SE/QA/BI/ML/AI): CHỈ nhận khi xuất hiện dạng
        #    CHỮ HOA trong câu gốc -> phân biệt với từ tiếng Việt thường ("ba"=bố, "se"=sẽ,
        #    "ai"=ai) để câu lạc đề không lọt.
        # Chữ HOA lấy từ CÂU GỐC (raw) — search_text đã bị viết thường nên mất tín hiệu này.
        _upper = set(re.findall(r"[A-Z]{2,}", str(raw if raw is not None else query)))
        _pre = str(query).lower().replace("c++", "cpp").replace("c#", "csharp")
        _qn = kb._key(_pre)
        _qn_tokens = _qn.split()
        for ckey in kb.find_concepts(query):
            for a in kb.CONCEPTS.get(ckey, {}).get("aliases", []):
                ka = kb._key(a)
                if not ka:
                    continue
                if len(ka) >= 3:
                    if (ka in _qn) if " " in ka else (ka in _qn_tokens):
                        return False
                elif ka.upper() in _upper:   # viết tắt ngắn -> chỉ nhận khi câu gốc viết HOA
                    return False
        if self.embed_model is None or not self.search_index:
            return False
        smax = query_relevance_max(
            query, self.item_list, self.embed_model,
            self.search_index["embeddings"],
            char_vectorizer=self.search_index.get("char_vectorizer"),
            char_matrix=self.search_index.get("char_matrix"),
            query_prefix=self.query_prefix,
            ann=self.ann,
        )
        return smax < CHATBOT_OFFTOPIC_GATE

    def _semantic_retrieve(self, query, top_k=8, item_type=None, history=None):
        """Truy hồi bằng Sentence Embeddings (có cổng off-topic + chịu lỗi chính tả).

        Trả về cùng cấu trúc nguồn như RAG: [{item, document, relevance}].
        Trả None nếu chưa nạp embeddings (để gọi tầng RAG dự phòng).
        """
        if self.embed_model is None or not self.search_index:
            return None
        # RAG-Fusion: nhiều biến thể truy vấn (gốc / nối lịch sử / mở rộng từ đồng nghĩa)
        # -> truy hồi độc lập rồi hợp nhất RRF + rerank + MMR. Bền với cách diễn đạt khác nhau.
        enriched = enrich_query_with_history(query, history)
        expanded = expand_query(enriched, self.rag.categories)
        variants = [query, enriched, expanded]
        results = multi_query_search(
            variants, self.item_list, self.embed_model,
            self.search_index["embeddings"],
            char_vectorizer=self.search_index.get("char_vectorizer"),
            char_matrix=self.search_index.get("char_matrix"),
            item_type=item_type,
            query_prefix=self.query_prefix,
            ann=self.ann,
            reranker=self.reranker,
            top_k=top_k,
            gate_query=enriched,   # cổng off-topic theo truy vấn tự nhiên (không phải biến thể mở rộng)
        )
        sources = []
        for r in results[:top_k]:
            rows = self.item_list[self.item_list["item_id"] == r["item_id"]]
            if rows.empty:
                continue
            sources.append({
                "item": r,
                "document": item_to_document(rows.iloc[0]),
                "relevance": r.get("score", 0.0),
            })
        return sources

    def chat(self, message, history=None):
        """Trả lời ĐẦY ĐỦ (không stream): {response, intent, sources, recommendations}."""
        kind, p = self._prepare(message, history or [])
        if kind == "final":
            return p
        # Cần LLM -> gọi 1 lần, lỗi/None thì rơi về template (synthesize_answer).
        llm_response = try_llm_response(p["sys_prompt"], p["llm_message"], history=p["history"])
        body = self._assemble_body(llm_response, p)
        return {
            "response": p["prefix"] + body,
            "intent": p["mode"],
            "sources": [s["item"] for s in p["sources"]],
            "recommendations": p["all_recs"],
        }

    def _assemble_body(self, llm_response, p):
        """Thân câu trả lời cho luồng cần-LLM: câu LLM + 'Tài nguyên tham khảo', hoặc template
        đầy đủ khi LLM không trả (None)."""
        if llm_response:
            body = llm_response
            rec_items = dedupe_items([s["item"] for s in p["sources"]] + p["recommendations"])
            if rec_items:
                body += "\n\n---\n### 📚 Tài nguyên tham khảo\n\n"
                body += format_sources_inline(rec_items[:5])
            return body
        return synthesize_answer(
            p["display_query"], p["sources"], p["recommendations"], p["mode"],
            category=p["category"], item_list=self.item_list,
        )

    def chat_stream(self, message, history=None):
        """Bản STREAMING của chat(): generator yield (event, data):
            ("text", <str>)  — mảnh văn bản để hiển thị dần.
            ("meta", {intent, recommendations}) — phát 1 lần ở cuối (vẽ thẻ tài nguyên).

        Luồng "final" (off-topic / handler / không cần LLM) phát nguyên văn 1 lần. Luồng cần-LLM
        phát prefix (khái niệm) trước, rồi stream token LLM; nếu LLM không trả mảnh nào -> phát
        template -> KHÔNG bao giờ ra bong bóng rỗng/lỗi."""
        kind, p = self._prepare(message, history or [])
        if kind == "final":
            yield ("text", p["response"])
            yield ("meta", {"intent": p.get("intent"),
                            "recommendations": p.get("recommendations", [])})
            return
        if p["prefix"]:
            yield ("text", p["prefix"])
        produced = 0
        for chunk in try_llm_response_stream(p["sys_prompt"], p["llm_message"], history=p["history"]):
            if chunk:
                produced += len(chunk)
                yield ("text", chunk)
        if produced == 0:
            # LLM không trả mảnh nào (tắt/lỗi/timeout sớm) -> template đầy đủ.
            yield ("text", synthesize_answer(
                p["display_query"], p["sources"], p["recommendations"], p["mode"],
                category=p["category"], item_list=self.item_list,
            ))
        else:
            rec_items = dedupe_items([s["item"] for s in p["sources"]] + p["recommendations"])
            if rec_items:
                yield ("text", "\n\n---\n### 📚 Tài nguyên tham khảo\n\n"
                       + format_sources_inline(rec_items[:5]))
        yield ("meta", {"intent": p["mode"], "recommendations": p["all_recs"]})

    def _prepare(self, message, history=None):
        """Chạy pipeline tới điểm SINH câu trả lời, dùng chung cho chat() và chat_stream().

        Trả về:
            ("final", result_dict)  — đã có câu trả lời đầy đủ (off-topic / handler intent /
                                      câu tìm-liệt kê không cần LLM).
            ("generate", ctx)       — cần sinh bằng LLM; ctx chứa sys_prompt, llm_message, prefix
                                      (note + khái niệm), sources, recommendations, mode...
        """
        history = history or []

        # 0) HIỂU TRUY VẤN: sửa lỗi chính tả, mở rộng viết tắt, suy luận ý người dùng.
        #    Văn bản đã chuẩn hóa (search_text) được dùng cho MỌI bước phát hiện ý định
        #    lẫn truy hồi -> chịu được "machne lerning", "lap trnh web", "k8s"...
        understanding = understand_query(message, self.vocab)
        search_text = understanding["corrected"]
        display_query = understanding["display"]

        # 0a) CỔNG OFF-TOPIC TẬP TRUNG: chặn câu NGOÀI lĩnh vực CNTT TRƯỚC mọi handler &
        #     truy hồi. Nhờ chạy sớm, nó bao trùm cả định nghĩa/so sánh/lộ trình lẫn nhánh
        #     BM25 dự phòng -> không còn tình trạng handler intent trả lời câu lạc đề chỉ vì
        #     khớp mẫu "X là gì". Dùng search_text (đã sửa lỗi + mở rộng viết tắt) để "k8s",
        #     "machne lerning"... vẫn được nhận đúng là CNTT; KHÔNG nối lịch sử ở đây để một
        #     câu lạc đề đột ngột vẫn bị chặn dù trước đó đang nói chuyện về CNTT.
        if self._is_off_topic(search_text, raw=message):
            return "final", {
                "response": OFF_TOPIC_MESSAGE,
                "intent": "off_topic",
                "sources": [],
                "recommendations": [],
            }

        # 0b) ĐỊNH TUYẾN INTENT ĐỊNH HƯỚNG: định nghĩa, so sánh, lộ trình nghề, kỹ năng
        #     còn thiếu, học gì tiếp, ước lượng thời gian, thống kê. Đây là nhóm câu hỏi
        #     "tạo giá trị" — trả lời định hướng thay vì chỉ liệt kê tài nguyên. Không khớp
        #     -> rơi về pipeline tìm tài nguyên bên dưới.
        #     Dùng DISPLAY (đã sửa lỗi chính tả nhưng CHƯA nối mở rộng viết tắt) để nhận
        #     diện khái niệm/nghề chính xác — tránh "sql"->"co so du lieu" làm lệch khái niệm.
        intent, slots = route_intent(display_query)
        # Khi có LLM (Ollama/Claude): MỌI câu ĐỊNH NGHĨA/GIẢI THÍCH ("X là gì", "giải thích X",
        # "vì sao X", "X hoạt động thế nào"...) đều để LLM trả lời TỰ NHIÊN & ĐI SÂU thay vì in
        # template định nghĩa tĩnh (vốn chỉ in 1 đoạn nghĩa từ glossary -> nông & dễ bị coi là
        # "không trả lời"). Định nghĩa chuẩn của glossary VẪN được chèn ở đầu câu trả lời qua
        # concept_overview_block làm điểm tựa chính xác. KHÔNG có LLM -> giữ template nhanh & grounded.
        if _llm_available() and intent == "definition":
            intent = None
        handler = {
            "definition": self._answer_definition,
            "comparison": self._answer_comparison,
            "career_path": self._answer_career_path,
            "skill_gap": self._answer_skill_gap,
            "next_skill": self._answer_next_skill,
            "time_estimate": self._answer_time_estimate,
            "admin_stat": self._answer_admin_stat,
            "interview": self._answer_interview,
            "salary": self._answer_salary,
            "career_guidance": self._answer_career_guidance,
        }.get(intent)
        if handler:
            result = handler(slots, display_query, message, history)
            if result:
                note0 = intent_note(understanding)
                if note0:
                    result["response"] = note0 + result["response"]
                return "final", result

        item_type = detect_item_type(search_text)
        mode = detect_response_mode(search_text)
        # Hỏi "vì sao / như thế nào / hoạt động ra sao": người dùng chỉ muốn câu trả lời
        # TRỌNG TÂM, không phải cả lộ trình. Ép về chế độ "answer" (ngắn, có khái niệm + 1
        # tài nguyên sát nhất) dù câu có chứa "bắt đầu/cơ bản" làm detect_response_mode hiểu
        # nhầm thành lộ trình. (Khi có LLM, câu suy luận đã đi nhánh LLM nên override này vô hại.)
        if _is_explanation_query(message):
            mode = "answer"
        category = self.rag.detect_category(search_text)

        # 1) Ưu tiên truy hồi NGỮ NGHĨA (embeddings) — khớp ý nghĩa, chịu lỗi chính tả,
        #    tự chặn câu hỏi ngoài lĩnh vực IT. 2) Dự phòng bằng RAG (BM25/TF-IDF) nếu cần.
        sources = self._semantic_retrieve(
            search_text, top_k=8, item_type=item_type, history=history
        )
        # CRAG (Corrective RAG): nếu bộ lọc loại làm rỗng kết quả, tự nới bỏ lọc rồi
        # thử lại trước khi kết luận -> ít khi "không tìm thấy" oan.
        if sources is not None and not sources and item_type:
            sources = self._semantic_retrieve(
                search_text, top_k=8, item_type=None, history=history
            )
        if sources is None:
            # Embeddings KHÔNG khả dụng -> dùng RAG (BM25/TF-IDF) dự phòng.
            context, sources = self.rag.build_context(
                search_text, top_k=8, item_type=item_type, history=history
            )
        else:
            # Embeddings ĐÃ chạy: rỗng nghĩa là ngoài lĩnh vực (cổng off-topic) ->
            # KHÔNG rơi xuống BM25 (vốn không có cổng chặn) -> trả lời "ngoài lĩnh vực".
            context = "\n\n---\n\n".join(
                f"[Nguồn {i} — độ phù hợp {s['relevance']:.0f}%]\n{s['document']}"
                for i, s in enumerate(sources, 1)
            )

        # Chuyên mục SUY TỪ chính kết quả truy hồi ngữ nghĩa (đáng tin hơn đoán theo
        # từ khóa): nếu nguồn toàn mục ML thì chuyên mục là "Trí tuệ nhân tạo" — tránh
        # nhận nhầm "khóa học ..." thành "Khoa học dữ liệu". Lexical chỉ là dự phòng.
        src_cat = dominant_category(sources)
        if src_cat:
            category = src_cat

        recommendations = []
        seen_ids = {s["item"]["item_id"] for s in sources}
        if sources:
            seed_id = sources[0]["item"]["item_id"]
            recommendations = self.rag.get_recommendations(
                seed_id, top_n=5, exclude_ids=seen_ids, query=search_text
            )
            # Chuẩn hóa % gợi ý về cùng dải tin cậy (90-100%) như nguồn truy hồi.
            rmax = max((r.get("score", 0.0) for r in recommendations), default=0.0) or 1.0
            for r in recommendations:
                if "score" in r:
                    r["score"] = round(calibrate_confidence(r["score"] / rmax) * 100, 1)

        # (Đã bỏ khối chèn filter_by_category(...).head(3) ở 95%: nó nhét đại 3 mục
        #  ĐẦU TIÊN của chuyên mục lên đầu nguồn bất kể có liên quan truy vấn hay không
        #  -> kéo theo mục lạc đề ở 95%. Lộ trình trong synthesize_answer đã tự lấp đầy
        #  từng giai đoạn bằng category_stage_items: đúng cấp độ + ưu tiên bám truy vấn.)

        # PREFIX = (note sửa lỗi) + (khái niệm chung). Chèn TRƯỚC thân câu trả lời — giữ ĐÚNG
        # thứ tự bản gốc (note, rồi concept, rồi body). Tách ra đây để chat_stream() phát prefix
        # NGAY trước khi stream token LLM (người dùng thấy khái niệm tức thì, không chờ LLM).
        prefix = ""
        if sources:
            all_items0 = dedupe_items([s["item"] for s in sources] + recommendations)
            concept = concept_overview_block(display_query, all_items0, category)
            if concept:
                prefix = concept + prefix
        note = intent_note(understanding)
        if note:
            prefix = note + prefix

        all_recs = dedupe_items([s["item"] for s in sources] + recommendations)[:6]

        # Trả lời bằng LLM cho câu HỘI THOẠI/ĐỊNH HƯỚNG (suy luận, lộ trình, gợi ý, trả lời chung)
        # -> mỗi câu được trả lời RIÊNG, bám ngữ cảnh, thay vì cùng một template lặp lại. Câu
        # TÌM/LIỆT KÊ thuần (mode "search") giữ template (nhanh + liệt kê chính xác từ catalog).
        # use_llm TỰ PHÁT HIỆN Ollama -> không treo khi Ollama không chạy (fail nhanh -> template).
        use_llm = _llm_available()
        want_llm = use_llm and (mode != "search" or _is_reasoning_query(message))

        ctx = {
            "display_query": display_query, "sources": sources, "recommendations": recommendations,
            "mode": mode, "category": category, "prefix": prefix, "all_recs": all_recs,
            "history": history,
        }

        if not want_llm:
            # Câu tìm/liệt kê thuần (hoặc không có LLM) -> dựng câu trả lời template NGAY.
            body = synthesize_answer(
                display_query, sources, recommendations, mode,
                category=category, item_list=self.item_list,
            )
            return "final", {
                "response": prefix + body, "intent": mode,
                "sources": [s["item"] for s in sources], "recommendations": all_recs,
            }

        # Cần LLM -> dựng system prompt (catalog + gợi ý định dạng theo ý định) để caller sinh.
        # Cấp cho LLM cả câu hỏi gốc lẫn ý đã hiểu để bám sát + chịu lỗi chính tả.
        llm_message = display_query if understanding["corrections"] else message
        # Câu LỘ TRÌNH cần nhiều mục hơn để LLM gắn khóa thật vào từng giai đoạn; câu khác vài mục.
        n_ctx = 8 if mode == "learning_path" else 5
        ctx_lines = "\n".join(
            f"- {s['item'].get('title','')} | {s['item'].get('category','')}"
            f" | {s['item'].get('level','') or 'N/A'}"
            for s in (sources or [])[:n_ctx]
        )
        # Gợi ý ĐỊNH DẠNG theo ý định -> trả lời đúng kiểu câu hỏi (lộ trình/gợi ý/so sánh).
        mode_hint = {
            # LỘ TRÌNH: cho LLM DỰNG lộ trình kiến thức THẬT bằng hiểu biết của model (không bị bó
            # vào vài khóa truy hồi được -> hết "thiếu/sai thứ tự"), rồi GẮN khóa catalog vào giai
            # đoạn phù hợp. Giai đoạn chưa có khóa khớp thì vẫn nêu kiến thức cần học (không bỏ).
            "learning_path": "Người dùng muốn LỘ TRÌNH HỌC. Hãy DỰNG lộ trình kiến thức THẬT theo cấp "
                             "độ cơ bản -> nâng cao bằng hiểu biết của bạn: 3-4 giai đoạn, mỗi giai đoạn "
                             "nêu ngắn các chủ đề/kỹ năng cần học và VÌ SAO theo thứ tự đó. Khi có khóa "
                             "phù hợp trong catalog ở trên thì GẮN vào giai đoạn tương ứng (CHỈ trích "
                             "tên từ catalog, KHÔNG bịa); giai đoạn nào catalog chưa có khóa khớp thì cứ "
                             "nêu kiến thức cần học. TUYỆT ĐỐI không bỏ giai đoạn chỉ vì catalog thiếu khóa.",
            "recommend": "Người dùng muốn GỢI Ý. Chọn 2-3 khóa phù hợp nhất từ catalog và giải thích "
                         "ngắn gọn vì sao chọn (bỏ khóa lạc chủ đề).",
            "compare": "Người dùng muốn SO SÁNH. Nêu khác biệt chính giữa các lựa chọn liên quan.",
            # answer = câu GIẢI THÍCH/PHÂN TÍCH (vì sao/lợi ích/khi nào/là gì...). Ưu tiên trả lời
            # thực chất kiểu "tổng quan trên web", KHÔNG chuyển sang liệt kê khóa học.
            "answer": "Người dùng hỏi một câu cần GIẢI THÍCH/PHÂN TÍCH. Hãy TRẢ LỜI TRỰC TIẾP, đầy "
                      "đủ, có cấu trúc bằng kiến thức của bạn (nêu lý do/phân tích/ví dụ thực tế), "
                      "như một đoạn giải thích tổng quan rõ ràng. KHÔNG chuyển sang liệt kê khóa học; "
                      "phần tài nguyên đã có sẵn ở cuối.",
        }.get(mode, "")
        sys_prompt = self.SYSTEM_PROMPT
        if ctx_lines:
            sys_prompt += f"\n\n## Khóa học liên quan trong catalog (CHỈ trích từ đây khi gợi ý cụ thể):\n{ctx_lines}"
        if mode_hint:
            sys_prompt += f"\n\n## Yêu cầu cho câu trả lời:\n{mode_hint}"

        ctx.update({"sys_prompt": sys_prompt, "llm_message": llm_message})
        return "generate", ctx

    # ══════════════════ HANDLER INTENT ĐỊNH HƯỚNG ══════════════════
    # Mỗi handler trả dict {response, intent, sources, recommendations} hoặc None để
    # rơi về pipeline tìm tài nguyên. Tài nguyên luôn kéo từ catalog thật (_quick_resources).

    def _quick_resources(self, text, k=3, item_type=None, filters=None):
        """Tra cứu tài nguyên NHANH (1 truy vấn embedding, KHÔNG cross-encoder) cho các
        handler định hướng — tránh gọi rerank nhiều lần gây chậm. Trả list item dict."""
        if not text or not text.strip():
            return []
        if self.embed_model is not None and self.search_index:
            items = search_by_embedding(
                text, self.item_list, self.embed_model, self.search_index["embeddings"],
                char_vectorizer=self.search_index.get("char_vectorizer"),
                char_matrix=self.search_index.get("char_matrix"),
                item_type=item_type, query_prefix=self.query_prefix,
                ann=self.ann, reranker=None,
            )
        else:
            from itlr.core.recommender import search_by_query
            items = search_by_query(
                self.item_list, self.retrieval_model, text,
                top_n=max(k + 4, 8), item_type=item_type, use_mmr=True,
            )
        if filters:
            items = self._filter_items(items, filters) or items
        return items[:k]

    @staticmethod
    def _filter_items(items, filters):
        """Lọc theo trình độ / nền tảng / miễn phí (suy từ nền tảng)."""
        out = []
        for it in items:
            if filters.get("level") and str(it.get("level", "")).strip() != filters["level"]:
                continue
            plat = strip_accents(str(it.get("platform", "")))
            if filters.get("platform") and filters["platform"] not in plat:
                continue
            if filters.get("free") and plat not in FREE_PLATFORMS:
                continue
            out.append(it)
        return out

    def _answer_definition(self, slots, display_query, message, history):
        c = kb.CONCEPTS[slots["concept"]]
        filters = detect_filters(message)
        items = self._quick_resources(" ".join(c["topics"]) or c["name"], k=3, filters=filters)
        resp = f"## {c['name']} là gì?\n\n{c['def']}"
        if c.get("example"):
            resp += f"\n\n> 💡 **Ví dụ:** {c['example']}"
        meta = []
        if c.get("category"):
            lvl = f" · 🎚️ {c['level']}" if c.get("level") else ""
            meta.append(f"🏷️ **Lĩnh vực:** {c['category']}{lvl}")
        if c.get("related"):
            rel = [kb.CONCEPTS[r]["name"] for r in c["related"] if r in kb.CONCEPTS]
            if rel:
                meta.append("🔗 **Khái niệm liên quan:** " + ", ".join(f"*{r}*" for r in rel))
        if meta:
            resp += "\n\n" + "  \n".join(meta)
        if items:
            resp += "\n\n---\n\n### 📚 Học ngay trong catalog\n\n" + format_sources_inline(items, 3)
        resp += followup_block(display_query, c.get("category"), items, mode="answer")
        return {"response": resp, "intent": "definition", "sources": items, "recommendations": items}

    def _answer_comparison(self, slots, display_query, message, history):
        concs = slots.get("concepts") or []
        ents = slots.get("entities") or []
        if len(concs) >= 2:
            sides = [(kb.CONCEPTS[c]["name"], kb.CONCEPTS[c]["def"], " ".join(kb.CONCEPTS[c]["topics"]))
                     for c in concs[:2]]
        elif len(ents) == 2:
            sides = [(e.title(), None, e) for e in ents]
        else:
            return None
        verdict = kb.comparison_verdict(sides[0][0], sides[1][0])
        resp = f"## ⚖️ So sánh {sides[0][0]} vs {sides[1][0]}\n"
        if verdict:
            resp += f"\n{verdict}\n"
        items = []
        for name, definition, q in sides:
            resp += f"\n### {name}\n"
            if definition:
                resp += f"{definition}\n"
            its = self._quick_resources(q, k=2)
            items += its
            if its:
                resp += "\n" + format_sources_inline(its, 2) + "\n"
        if not verdict:
            resp += "\n> 💡 Chọn theo nhu cầu dự án & hệ sinh thái nhóm bạn đang dùng."
        items = dedupe_items(items)
        return {"response": resp, "intent": "comparison", "sources": items, "recommendations": items}

    def _answer_career_path(self, slots, display_query, message, history):
        key = slots["career"]
        career = kb.CAREERS[key]
        roadmap = kb.role_roadmap(key)        # [{stage, duration, skills}] để hiển thị thời lượng
        desc = kb.role_description(key)
        known = {kb._key(s) for s in slots.get("known", [])}
        filters = detect_filters(message)
        hours, m_lo, m_hi = kb.estimate_career_time(key)
        resp = f"## 🗺️ Lộ trình trở thành {career['name']}\n\n"
        if desc:
            resp += f"{desc}\n\n"
        resp += (
            f"Lộ trình **{len(career['milestones'])} giai đoạn** từ nền tảng đến nâng cao, "
            f"mỗi kỹ năng kèm tài nguyên thật trong catalog. "
            f"⏱️ Ước lượng tự học: **~{m_lo}–{m_hi} tháng** (~{hours} giờ).\n"
        )
        emojis = ["🟢", "🟡", "🟠", "🔴", "🔵"]
        items = []
        for i, (stage, skills) in enumerate(career["milestones"]):
            badges = " · ".join(
                (f"`{s}` ✅" if kb._key(s) in known else f"`{s}`") for s in skills
            )
            dur = roadmap[i].get("duration") if i < len(roadmap) else ""
            dur_txt = f" · ⏱️ {dur}" if dur else ""
            resp += f"\n### {emojis[i % len(emojis)]} Giai đoạn {i + 1} — {stage}{dur_txt}\n"
            resp += f"**Kỹ năng:** {badges}\n\n"
            its = self._quick_resources(" ".join(skills), k=2, filters=filters)
            items += its
            if its:
                resp += format_sources_inline(its, 2) + "\n"
        if known:
            resp += f"\n> ✅ Bạn đã có: {', '.join(sorted(slots['known']))} — có thể bỏ qua phần tương ứng."
        items = dedupe_items(items)
        resp += (
            f"\n\n> 💡 Hỏi thêm về vai trò này: *\"phỏng vấn {career['name']}\"* · "
            f"*\"lương {career['name']}\"*."
        )
        resp += followup_block(display_query, career["name"], items, mode="learning_path")
        return {"response": resp, "intent": "career_path", "sources": items, "recommendations": items}

    def _answer_interview(self, slots, display_query, message, history):
        """Câu hỏi phỏng vấn thường gặp cho một vai trò + tài nguyên ôn tập từ catalog."""
        key = slots["role"]
        role = kb.ROLES.get(key, {})
        qs = kb.role_interview(key)
        if not qs:
            return None
        resp = f"## 🎤 Phỏng vấn {role.get('name', key)} — câu hỏi thường gặp\n\n"
        if role.get("description"):
            resp += f"{role['description']}\n\n"
        resp += "\n".join(f"{i}. {q}" for i, q in enumerate(qs, 1))
        # Tài nguyên ôn tập: tìm theo kỹ năng GIAI ĐOẠN ĐẦU của vai trò (sát phần cần ôn nhất).
        seed = " ".join(role.get("roadmap", [{}])[0].get("skills", [])) or role.get("name", "")
        items = dedupe_items(self._quick_resources(seed, k=3))
        if items:
            resp += "\n\n### 📚 Tài nguyên ôn tập\n\n" + format_sources_inline(items, 3)
        resp += (
            f"\n\n> 💡 Xem thêm: *\"lộ trình {role.get('name','')}\"* · "
            f"*\"lương {role.get('name','')}\"*."
        )
        return {"response": resp, "intent": "interview", "sources": items, "recommendations": items}

    def _answer_salary(self, slots, display_query, message, history):
        """Mức lương tham khảo theo cấp bậc cho một vai trò."""
        key = slots["role"]
        role = kb.ROLES.get(key, {})
        sal = kb.role_salary(key)
        if not sal:
            return None
        resp = f"## 💰 Mức lương {role.get('name', key)} (tham khảo, VN 2024–2025)\n\n"
        resp += "\n".join(f"- {s} VND/tháng" for s in sal)
        resp += (
            "\n\n> ⚠️ Đây là số liệu THAM KHẢO theo thị trường; thực tế tùy công ty, khu vực và năng lực."
            f"\n\n> 💡 Xem thêm: *\"lộ trình {role.get('name','')}\"* · "
            f"*\"phỏng vấn {role.get('name','')}\"*."
        )
        return {"response": resp, "intent": "salary", "sources": [], "recommendations": []}

    def _answer_career_guidance(self, slots, display_query, message, history):
        """Tư vấn chọn vai trò IT theo sở thích (bảng gợi ý từ it_roles.json)."""
        rows = kb.CAREER_GUIDANCE
        if not rows:
            return None
        resp = "## 🧭 Bạn hợp với vai trò IT nào?\n\nDựa trên điều bạn thích, có thể cân nhắc:\n\n"
        resp += "| Bạn thích... | Nên xem xét |\n|---|---|\n"
        resp += "\n".join(f"| {a} | **{b}** |" for a, b in rows)
        resp += (
            "\n\n> 💡 Chọn được hướng rồi? Hỏi *\"lộ trình [vai trò]\"* để xem chi tiết từng giai đoạn, "
            "hoặc *\"phỏng vấn [vai trò]\"* / *\"lương [vai trò]\"*."
        )
        return {"response": resp, "intent": "career_guidance", "sources": [], "recommendations": []}

    def _answer_skill_gap(self, slots, display_query, message, history):
        career = kb.CAREERS[slots["career"]]
        known_list = slots.get("known", [])
        gap = kb.career_skill_gap(known_list, slots["career"])
        resp = f"## 🎯 Kỹ năng còn thiếu để làm {career['name']}\n\n"
        if known_list:
            resp += f"Bạn đã có: {', '.join(f'`{k}`' for k in known_list)}.\n\n"
        if not gap:
            resp += "Tuyệt vời — bạn đã phủ gần hết kỹ năng cốt lõi của nghề này! Hãy tập trung dự án thực chiến."
            return {"response": resp, "intent": "skill_gap", "sources": [], "recommendations": []}
        resp += f"Bạn nên bổ sung **{len(gap)} kỹ năng** sau (theo thứ tự ưu tiên):\n\n"
        resp += " · ".join(f"`{g}`" for g in gap) + "\n"
        items = []
        for g in gap[:4]:
            items += self._quick_resources(g, k=1)
        items = dedupe_items(items)
        if items:
            resp += "\n\n---\n\n### 📚 Bắt đầu từ những tài nguyên này\n\n" + format_sources_inline(items, 5)
        resp += followup_block(display_query, career["name"], items, mode="recommend")
        return {"response": resp, "intent": "skill_gap", "sources": items, "recommendations": items}

    def _answer_next_skill(self, slots, display_query, message, history):
        known = list(slots.get("known", []))
        for m in history:
            if m.get("role") == "user":
                known += kb.extract_skills(m.get("content", ""))
        known = list(dict.fromkeys(known))
        nxt = kb.next_skills(known)
        resp = "## 🧭 Bạn nên học gì tiếp?\n\n"
        if known and nxt:
            resp += f"Dựa trên những gì bạn đã học ({', '.join(f'`{k}`' for k in known)}), gợi ý học tiếp:\n\n"
        else:
            resp += "Bạn chưa nêu kỹ năng đã học, mình gợi ý lộ trình nền tảng phổ biến:\n\n"
            nxt = ["Python", "OOP", "SQL", "Git", "Data Structures"]
        resp += " → ".join(f"`{s}`" for s in nxt) + "\n"
        items = []
        for s in nxt[:4]:
            items += self._quick_resources(s, k=1)
        items = dedupe_items(items)
        if items:
            resp += "\n\n---\n\n### 📚 Tài nguyên gợi ý\n\n" + format_sources_inline(items, 5)
        return {"response": resp, "intent": "next_skill", "sources": items, "recommendations": items}

    def _answer_time_estimate(self, slots, display_query, message, history):
        if slots.get("career"):
            career = kb.CAREERS[slots["career"]]
            hours, m_lo, m_hi = kb.estimate_career_time(slots["career"])
            resp = (
                f"## ⏱️ Bao lâu để trở thành {career['name']}?\n\n"
                f"Ước lượng tự học: **~{m_lo}–{m_hi} tháng** (~{hours} giờ), tùy tốc độ và nền tảng sẵn có.\n\n"
                f"- Học đều **~8–12 giờ/tuần** → khoảng {m_hi}–{m_lo} tháng.\n"
                f"- Đã có nền lập trình → rút ngắn 30–40%.\n\n"
                f"Gợi ý: bám lộ trình **{len(career['milestones'])} giai đoạn** của nghề này để đi đúng thứ tự."
            )
            return {"response": resp, "intent": "time_estimate", "sources": [], "recommendations": []}
        if slots.get("concepts"):
            c = kb.CONCEPTS[slots["concepts"][0]]
            target, topics = c["name"], " ".join(c["topics"])
        elif slots.get("skills"):
            target = topics = slots["skills"][0]
        else:
            return None
        level = slots.get("level", "co ban")
        hours, weeks = kb.estimate_skill_time(level)
        lv_label = {"co ban": "cơ bản", "trung cap": "trung cấp", "nang cao": "nâng cao"}.get(level, "cơ bản")
        resp = (
            f"## ⏱️ Học {target} mất bao lâu?\n\n"
            f"Ở mức **{lv_label}**, ước lượng **~{weeks} tuần** (~{hours} giờ) nếu học đều ~10 giờ/tuần. "
            f"Thành thạo thực chiến cần thêm thời gian luyện dự án.\n"
        )
        items = self._quick_resources(topics, k=3)
        if items:
            resp += "\n---\n\n### 📚 Bắt đầu với\n\n" + format_sources_inline(items, 3)
        return {"response": resp, "intent": "time_estimate", "sources": items, "recommendations": items}

    def _answer_admin_stat(self, slots, display_query, message, history):
        from itlr.core.recommender import detect_category_from_query

        il = self.item_list
        raw = strip_accents(normalize_text(slots["raw"]))
        sub, type_label = il, "tài nguyên"
        if re.search(r"khoa hoc|course", raw):
            sub, type_label = il[il["type"] == "Khóa học"], "khóa học"
        elif re.search(r"tai lieu|document|sach", raw):
            sub, type_label = il[il["type"] == "Tài liệu"], "tài liệu"

        cat = detect_category_from_query(slots["raw"], self.rag.categories)
        if cat:
            sub2 = sub[sub["category"] == cat]
            resp = (
                f"## 📊 Thống kê\n\nCatalog hiện có **{len(sub2):,}** {type_label} thuộc **{cat}** "
                f"(trên tổng {len(sub):,} {type_label})."
            )
            if "level" in sub2.columns and len(sub2):
                lv = sub2["level"].value_counts()
                resp += "\n\nPhân bố cấp độ:\n" + "\n".join(f"- {k}: {v:,}" for k, v in lv.items())
            return {"response": resp, "intent": "admin_stat", "sources": [], "recommendations": []}

        if re.search(r"nhieu nhat|pho bien|top|hay nhat", raw):
            top = sub["category"].value_counts().head(5)
            lines = "\n".join(f"- **{c}**: {n:,} {type_label}" for c, n in top.items())
            resp = (
                f"## 📊 Top chuyên mục nhiều {type_label} nhất\n\n"
                f"(Tổng **{len(sub):,}** {type_label} trong catalog)\n\n{lines}\n\n"
                f"> Mức độ phổ biến theo lượt xem/tương tác được phản ánh ở tab **✨ Dành cho bạn**."
            )
            return {"response": resp, "intent": "admin_stat", "sources": [], "recommendations": []}

        n_course = int((il["type"] == "Khóa học").sum())
        n_doc = int((il["type"] == "Tài liệu").sum())
        resp = (
            f"## 📊 Thống kê catalog\n\nTổng **{len(il):,}** tài nguyên "
            f"(**{n_course:,}** khóa học · **{n_doc:,}** tài liệu) trải "
            f"**{il['category'].nunique()}** chuyên mục."
        )
        return {"response": resp, "intent": "admin_stat", "sources": [], "recommendations": []}
