"""Trích đặc trưng cho Learning-to-Rank (Trụ cột C).

Mỗi cặp (query, item) -> vector ~15 đặc trưng kết hợp tín hiệu từ vựng, ngữ nghĩa, cấu
trúc metadata và độ phổ biến. Toàn bộ đặc trưng đều BIẾN THIÊN theo item trong cùng một
truy vấn (cần thiết cho lambdarank — đặc trưng hằng theo nhóm không cho tín hiệu xếp hạng).

Tái dùng nguyên các primitive trong recommender.py + RankContext (pipeline.py).
"""

from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from itlr.core import recommender as R

FEATURE_NAMES: List[str] = [
    "tfidf", "bm25", "emb_cos", "char_cos", "cross_enc",
    "category_match", "topic_jaccard", "topic_contain", "title_overlap",
    "type_is_course", "n_topics", "desc_len", "popularity", "level_rank", "title_len",
]

_LEVEL_RANK = {"cơ bản": 0.0, "trung cấp": 0.5, "nâng cao": 1.0}


def query_score_vectors(ctx, query: str) -> Dict[str, object]:
    """Tính sẵn các vector điểm toàn-catalog cho một truy vấn (tfidf/bm25/emb/char) + phụ trợ."""
    vec = {}
    vec["tfidf"] = R._fuse_tfidf_scores(query, ctx.retrieval_model["vectorizers"],
                                        ctx.retrieval_model["matrices"])
    bm25 = ctx.retrieval_model["bm25"]
    vec["bm25"] = np.asarray(bm25.normalize_scores(bm25.score_query(query)))

    q_emb = ctx.embed_model.encode(
        [f"{ctx.query_prefix}{query.lower()}"], normalize_embeddings=True, convert_to_numpy=True)[0]
    vec["emb"] = ctx.embeddings @ q_emb

    if ctx.char_vectorizer is not None and ctx.char_matrix is not None:
        q_char = ctx.char_vectorizer.transform([R.strip_accents(query)])
        vec["char"] = cosine_similarity(q_char, ctx.char_matrix).ravel()
    else:
        vec["char"] = np.zeros(len(ctx.item_list))

    vec["cat_hint"] = R.detect_category_from_query(query, ctx.retrieval_model["categories"])
    vec["q_topics"] = set(R.extract_query_tokens(query))
    return vec


def _cross_scores(ctx, query: str, positions: Sequence[int]) -> Dict[int, float]:
    """Điểm cross-encoder cho các vị trí (nếu reranker khả dụng); thiếu -> 0."""
    if ctx.reranker is None or not positions:
        return {}
    from itlr.core.rerank import rerank as _rr
    pool = [(p,) for p in positions]
    ranked = _rr(query, pool, text_of=lambda c: R._rerank_doc(ctx.item_list.iloc[c[0]]),
                 reranker=ctx.reranker)
    out = {}
    for c, s in ranked:
        out[c[0]] = float(s) if s is not None else 0.0
    return out


def extract_features(ctx, query: str, positions: Sequence[int],
                     vectors: Dict | None = None, with_cross: bool = True) -> np.ndarray:
    """Trả ma trận (len(positions), len(FEATURE_NAMES)) đặc trưng cho các item."""
    v = vectors or query_score_vectors(ctx, query)
    cross = _cross_scores(ctx, query, positions) if with_cross else {}
    cat_hint = v["cat_hint"]
    q_topics = v["q_topics"]
    pop = np.asarray(ctx.cf_popularity) if getattr(ctx, "cf_popularity", None) is not None else None

    rows = []
    il = ctx.item_list
    for p in positions:
        row = il.iloc[p]
        rt = ctx._topics_cache[p]
        cat_match = R.category_bonus(cat_hint, row["category"]) if cat_hint else 0.0
        topics_str = str(row["topics"])
        n_topics = topics_str.count(",") + 1 if topics_str.strip() else 0
        desc_len = min(len(str(row["description"])) / 500.0, 2.0)
        title_len = min(len(str(row["title"])) / 80.0, 2.0)
        level = _LEVEL_RANK.get(str(row.get("level", "")).strip().lower(), 0.25)
        popularity = float(np.log1p(pop[p])) if pop is not None else 0.0
        rows.append([
            float(v["tfidf"][p]),
            float(v["bm25"][p]),
            float(v["emb"][p]),
            float(v["char"][p]),
            float(cross.get(p, 0.0)),
            float(cat_match),
            R.topic_jaccard(q_topics, rt),
            R.topic_containment(q_topics, rt),
            R.title_keyword_overlap(query, row["title"]),
            1.0 if row["type"] == "Khóa học" else 0.0,
            float(n_topics),
            desc_len,
            popularity,
            level,
            title_len,
        ])
    return np.asarray(rows, dtype="float64")
