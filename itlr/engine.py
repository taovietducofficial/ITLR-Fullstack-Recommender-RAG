"""Engine nạp artifacts & expose API thuần Python — ĐỘC LẬP framework (không Streamlit).

Đây là đường nạp artifacts DUY NHẤT cho mọi lớp trình bày (web API FastAPI, CLI, hay
code khác). Toàn bộ giao diện Streamlit cũ đã được gỡ bỏ — hệ thống chạy thuần FastAPI.

Toàn bộ logic lõi (truy hồi ngữ nghĩa, RAG, chatbot có cổng off-topic + khái niệm-trước,
Collaborative Filtering) được giữ nguyên — engine chỉ gói lại cho tiện gọi.
"""

import pickle
from functools import lru_cache

from itlr import config
from itlr.core.recommender import recommend_for_user, search_by_embedding


class RecommenderEngine:
    """Gói gọn artifacts + 3 năng lực: tìm kiếm ngữ nghĩa · chatbot · gợi ý CF."""

    def __init__(self, items, model, search_index, cf_model, chatbot):
        self.items = items
        self.model = model
        self.search_index = search_index
        self.cf_model = cf_model
        self.chatbot = chatbot

    # ── Tab Tìm kiếm ──────────────────────────────────────────────────────────
    def search(self, query, item_type=None, min_pct=90):
        """Tìm kiếm ngữ nghĩa — logic hiểu truy vấn của tab Tìm kiếm.

        Mở rộng viết tắt + sửa lỗi chính tả + bổ sung tên/chủ đề khái niệm (nếu truy vấn
        là một khái niệm trong glossary), rồi truy hồi qua `search_by_embedding`.
        Trả dict: {results, display, note, corrected}.
        """
        from itlr.chatbot.knowledge_base import CONCEPTS, safe_concept_match
        from itlr.chatbot.query_understanding import understand_query

        if not query or not query.strip():
            return {"results": [], "display": "", "note": "", "corrected": False}

        understanding = understand_query(query, self.search_index.get("vocab") or frozenset())
        search_query = understanding["corrected"] or query

        # Nếu truy vấn là một KHÁI NIỆM (vd "DBA", "RLHF", "SE") -> bổ sung tên đầy đủ +
        # chủ đề để truy hồi đúng. safe_concept_match: không nhận nhầm "em bé"/"ai là ca sĩ".
        matched = None
        mkey = safe_concept_match(query)
        if mkey:
            matched = CONCEPTS[mkey]
            search_query = f"{search_query} {matched['name']} {' '.join(matched.get('topics', []))}"

        notes = []
        if understanding["expansions"]:
            notes.append("mở rộng: " + ", ".join(understanding["expansions"]))
        if matched:
            notes.append(f"khái niệm: {matched['name']}")

        results = search_by_embedding(
            search_query, self.items, self.model, self.search_index["embeddings"],
            char_vectorizer=self.search_index["char_vectorizer"],
            char_matrix=self.search_index["char_matrix"],
            item_type=item_type, min_relevance=min_pct / 100.0,
            query_prefix=self.search_index.get("query_prefix", ""),
            ann=self.search_index.get("ann"),
            reranker=self.search_index.get("reranker"),
        )
        return {
            "results": results,
            "display": understanding["display"],
            "note": " · ".join(notes),
            "corrected": bool(understanding["corrections"] or notes),
        }

    # ── Tab Chatbot ───────────────────────────────────────────────────────────
    def chat(self, message, history=None):
        """Trả lời chatbot (off-topic gate + khái niệm-trước đã nằm trong EducationalChatbot)."""
        return self.chatbot.chat(message, history=history or [])

    def chat_stream(self, message, history=None):
        """Bản STREAMING: generator yield (event, data) — xem EducationalChatbot.chat_stream."""
        yield from self.chatbot.chat_stream(message, history=history or [])

    # ── Tab Dành cho bạn (Collaborative Filtering) ─────────────────────────────
    def personas(self):
        """Danh sách hồ sơ người dùng mô phỏng: [{uid, label}]."""
        labels = self.cf_model["labels"]
        return [{"uid": int(u), "label": labels[u]} for u in labels]

    def for_you(self, persona_uid, interested_item_ids=None, top_n=12):
        """Gợi ý CF cho một persona. `interested_item_ids` = các item_id user vừa bấm 'Quan tâm'
        trong phiên (chuyển sang vị trí và nối vào lịch sử để feed học thêm)."""
        histories = self.cf_model["histories"]
        id_to_pos = self.cf_model["id_to_pos"]
        uid = int(persona_uid)
        base = list(histories.get(uid, []))
        extra = [id_to_pos[int(i)] for i in (interested_item_ids or []) if int(i) in id_to_pos]
        recs = recommend_for_user(base + extra, self.cf_model, self.items, top_n=top_n)
        return {"recs": recs}


@lru_cache(maxsize=1)
def load_engine():
    """Nạp toàn bộ artifacts MỘT LẦN (cache process-level) và dựng RecommenderEngine.

    Ném FileNotFoundError nếu thiếu artifacts -> caller hiển thị hướng dẫn build.
    """
    items = pickle.load(open(config.artifact("item_list.pkl"), "rb")).reset_index(drop=True)
    meta = pickle.load(open(config.artifact("search_meta.pkl"), "rb"))
    retrieval_model = pickle.load(open(config.artifact("retrieval_model.pkl"), "rb"))
    cf_model = pickle.load(open(config.artifact("cf_model.pkl"), "rb"))
    search_index = {
        "embeddings": pickle.load(open(config.artifact("embeddings.pkl"), "rb")),
        "char_vectorizer": pickle.load(open(config.artifact("char_vectorizer.pkl"), "rb")),
        "char_matrix": pickle.load(open(config.artifact("char_matrix.pkl"), "rb")),
        "query_prefix": meta.get("query_prefix", ""),
    }

    from sentence_transformers import SentenceTransformer

    from itlr.chatbot.chatbot import EducationalChatbot
    from itlr.core.ann import load_ann
    from itlr.core.rerank import get_reranker

    model = SentenceTransformer(meta["model_name"])
    ann = load_ann()           # FAISS nếu đã build + cài; None -> brute-force
    reranker = get_reranker()  # cross-encoder nếu khả dụng; None -> bỏ tầng rerank
    search_index["ann"] = ann
    search_index["reranker"] = reranker

    chatbot = EducationalChatbot(
        items, retrieval_model, search_index=search_index, embed_model=model,
        query_prefix=search_index["query_prefix"], ann=ann, reranker=reranker,
    )
    # Vốn từ để mở rộng viết tắt / sửa lỗi chính tả cho ô Tìm kiếm (giống chatbot).
    search_index["vocab"] = chatbot.vocab
    return RecommenderEngine(items, model, search_index, cf_model, chatbot)
