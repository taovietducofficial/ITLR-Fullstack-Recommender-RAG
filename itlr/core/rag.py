"""Educational RAG: tuned retrieval with multi-field fusion, BM25, MMR."""

import re

from itlr.core.recommender import (
    detect_category_from_query,
    extract_query_tokens,
    normalize_text,
    parse_topics,
    reciprocal_rank_fusion,
    row_to_dict,
    search_by_query,
    title_keyword_overlap,
    topic_containment,
    topic_jaccard,
)
def item_to_document(row):
    return (
        f"Tiêu đề: {row['title']}\n"
        f"Loại: {row['type']}\n"
        f"Chuyên mục: {row['category']}\n"
        f"Chủ đề: {row['topics']}\n"
        f"Mô tả: {row['description']}\n"
        f"Giảng viên/Tác giả: {row['instructor']}\n"
        f"Nền tảng: {row['platform']}\n"
        f"Liên kết: {row['link']}"
    )


TOPIC_ALIASES = {
    "ml": "machine learning trí tuệ nhân tạo",
    "ai": "trí tuệ nhân tạo artificial intelligence",
    "dl": "deep learning neural network",
    "nlp": "natural language processing xử lý ngôn ngữ",
    "cv": "computer vision thị giác máy tính",
    "devops": "devops ci cd docker kubernetes triển khai",
    "k8s": "kubernetes container orchestration",
    "db": "database sql nosql cơ sở dữ liệu",
    "fe": "frontend react vue angular javascript",
    "be": "backend api server node",
    "sec": "security an ninh mang cybersecurity",
    "cloud": "cloud aws gcp azure điện toán đám mây",
    "blockchain": "blockchain web3 ethereum crypto",
    "mobile": "android ios flutter react native",
    "data": "data science khoa học dữ liệu analytics",
    "network": "mạng máy tính tcp ip routing",
    "os": "hệ điều hành linux windows",
    "test": "kiểm thử testing qa automation",
}


def expand_query(query, categories=None):
    parts = [query]
    norm = normalize_text(query)

    for alias, expansion in TOPIC_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", norm):
            parts.append(expansion)

    if categories:
        for category in categories:
            cat_norm = normalize_text(category)
            if cat_norm in norm or any(
                t in cat_norm.split() for t in norm.split() if len(t) > 3
            ):
                parts.append(category)

    keywords = extract_query_tokens(query)
    if keywords:
        parts.append(" ".join(keywords))
        parts.append(" ".join(keywords))

    return " ".join(parts)


def enrich_query_with_history(query, history, max_turns=4):
    if not history:
        return query
    user_msgs = [m["content"] for m in history[-max_turns:] if m["role"] == "user"]
    if not user_msgs:
        return query
    return f"{' '.join(user_msgs[-2:])} {query}"


class EducationalRAG:
    """Tuned RAG over IT learning catalog."""

    MIN_RELEVANCE = 12.0

    def __init__(self, item_list, retrieval_model):
        self.item_list = item_list
        self.model = retrieval_model
        self.categories = retrieval_model["categories"]
        self.topic_index = retrieval_model.get("topic_index", {})

    def _topic_index_lookup(self, query):
        """Boost items whose topics directly match query keywords."""
        q_tokens = set(extract_query_tokens(query))
        hits = []
        for topic, item_ids in self.topic_index.items():
            topic_tokens = set(topic.split())
            if q_tokens & topic_tokens or any(t in topic for t in q_tokens if len(t) > 3):
                for item_id in item_ids[:3]:
                    hits.append(item_id)
        return hits

    def _multi_query_retrieve(self, enriched, expanded, item_type=None):
        """RRF fusion across raw, expanded, and field-specific queries."""
        rankings = []

        for q in [enriched, expanded]:
            results = search_by_query(
                self.item_list, self.model, q,
                top_n=15, item_type=item_type, use_mmr=False,
            )
            rankings.append(
                [self.item_list[self.item_list["item_id"] == r["item_id"]].index[0]
                 for r in results]
            )

        topic_hits = self._topic_index_lookup(enriched)
        if topic_hits:
            topic_ranking = []
            for item_id in topic_hits:
                rows = self.item_list[self.item_list["item_id"] == item_id]
                if not rows.empty:
                    topic_ranking.append(rows.index[0])
            if topic_ranking:
                rankings.append(topic_ranking)

        if not rankings:
            return []

        fused = reciprocal_rank_fusion(rankings)
        return fused

    def _rerank_fused(self, query, fused_candidates, item_type=None, category_hint=None):
        """Second-stage reranking with fine-grained signals."""
        q_topics = set(extract_query_tokens(query))
        reranked = []

        for idx, rrf_score in fused_candidates:
            row = self.item_list.iloc[idx]
            if item_type and row["type"] != item_type:
                continue

            row_topics = parse_topics(row["topics"])
            cat_match = 1.0 if category_hint and row["category"] == category_hint else 0.0
            title_ov = title_keyword_overlap(query, row["title"])
            jaccard = topic_jaccard(q_topics, row_topics)
            contain = topic_containment(q_topics, row_topics)

            final = (
                0.30 * min(rrf_score * 30, 1.0)
                + 0.22 * jaccard
                + 0.18 * contain
                + 0.15 * cat_match
                + 0.15 * title_ov
            )
            reranked.append((idx, final))

        reranked.sort(key=lambda x: x[1], reverse=True)
        return reranked

    def detect_category(self, query):
        return detect_category_from_query(query, self.categories)

    def retrieve(self, query, top_k=8, item_type=None, history=None):
        enriched = enrich_query_with_history(query, history)
        expanded = expand_query(enriched, self.categories)
        category_hint = self.detect_category(query)

        fused = self._multi_query_retrieve(enriched, expanded, item_type=item_type)
        if not fused:
            results = search_by_query(
                self.item_list, self.model, expanded,
                top_n=top_k, item_type=item_type, use_mmr=True,
            )
            return [
                {
                    "item": r,
                    "document": item_to_document(
                        self.item_list[self.item_list["item_id"] == r["item_id"]].iloc[0]
                    ),
                    "relevance": r["score"],
                }
                for r in results
            ]

        reranked = self._rerank_fused(
            query, fused[: top_k * 4], item_type=item_type, category_hint=category_hint
        )

        documents = []
        seen_ids = set()
        for idx, final_score in reranked:
            row = self.item_list.iloc[idx]
            item_id = int(row["item_id"])
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            relevance = round(final_score * 100, 1)
            if relevance < self.MIN_RELEVANCE and documents:
                continue

            item = row_to_dict(row, score=final_score)
            documents.append({
                "item": item,
                "document": item_to_document(row),
                "relevance": relevance,
            })
            if len(documents) >= top_k:
                break

        return documents

    REC_CANDIDATE_POOL = 300

    def get_recommendations(self, seed_item_id, top_n=5, exclude_ids=None, query=None):
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity

        from itlr.core.recommender import hybrid_score_v2, category_bonus

        exclude_ids = exclude_ids or set()
        seed_rows = self.item_list[self.item_list["item_id"] == seed_item_id]
        if seed_rows.empty:
            return []

        seed = seed_rows.iloc[0]
        seed_index = seed_rows.index[0]
        seed_topics = parse_topics(seed["topics"])
        seed_category = seed["category"]
        q_topics = set(extract_query_tokens(query or ""))
        tfidf = self.model["matrices"]["full"]
        seed_sim = cosine_similarity(tfidf[seed_index], tfidf).ravel()

        k = min(self.REC_CANDIDATE_POOL + len(exclude_ids) + 1, len(seed_sim))
        top_idx = np.argpartition(seed_sim, -k)[-k:]

        candidates = []
        for i in top_idx:
            i = int(i)
            row = self.item_list.iloc[i]
            if int(row["item_id"]) in exclude_ids or i == seed_index:
                continue
            cosine = float(seed_sim[i])
            score = hybrid_score_v2(
                cosine=cosine,
                category_score=category_bonus(seed_category, row["category"]),
                topics_a=seed_topics,
                topics_b=parse_topics(row["topics"]),
                type_match=1.0 if row["type"] == seed["type"] else 0.0,
                title_overlap=title_keyword_overlap(query or seed["title"], row["title"]),
                query_topics=q_topics or seed_topics,
            )
            candidates.append((i, score, cosine))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return [
            row_to_dict(self.item_list.iloc[i], score=score, tfidf_score=cosine)
            for i, score, cosine in candidates[:top_n]
        ]

    def build_context(self, query, top_k=8, item_type=None, history=None):
        docs = self.retrieve(query, top_k=top_k, item_type=item_type, history=history)
        if not docs:
            return "", []

        parts = [
            f"[Nguồn {i} — độ liên quan {doc['relevance']:.1f}%]\n{doc['document']}"
            for i, doc in enumerate(docs, 1)
        ]
        return "\n\n---\n\n".join(parts), docs
