"""Tiện ích nạp RankContext dùng chung cho các script đánh giá (tránh lặp code).

Gói load_engine (model/ann/reranker/embeddings) + retrieval_model + popularity CF thành
một RankContext (pipeline.py). Nạp artifacts MỘT lần qua load_engine (@lru_cache).
"""

from __future__ import annotations

import pickle

from itlr import config
from itlr.core import pipeline as P


def build_rank_context(with_ltr: bool = False) -> P.RankContext:
    from itlr.engine import load_engine

    engine = load_engine()
    retrieval_model = pickle.load(open(config.artifact("retrieval_model.pkl"), "rb"))
    si = engine.search_index
    ctx = P.RankContext(
        item_list=engine.items,
        retrieval_model=retrieval_model,
        embeddings=si["embeddings"],
        embed_model=engine.model,
        char_vectorizer=si["char_vectorizer"],
        char_matrix=si["char_matrix"],
        query_prefix=si.get("query_prefix", ""),
        ann=si.get("ann"),
        reranker=si.get("reranker"),
        cf_popularity=engine.cf_model.get("popularity"),
    )
    if with_ltr:
        attach_ltr_scorer(ctx)
    return ctx


def attach_ltr_scorer(ctx: P.RankContext) -> bool:
    """Nạp artifacts/ltr.pkl (nếu có) và gắn ctx.ltr_scorer. Trả True nếu thành công."""
    import os

    path = config.artifact("ltr.pkl")
    if not os.path.exists(path):
        return False
    from itlr.eval import ltr_features as LF

    bundle = pickle.load(open(path, "rb"))
    booster = bundle["booster"]
    with_cross = bundle.get("with_cross", True)

    def scorer(query, positions):
        vectors = LF.query_score_vectors(ctx, query)
        X = LF.extract_features(ctx, query, list(positions), vectors=vectors, with_cross=with_cross)
        return booster.predict(X)

    ctx.ltr_scorer = scorer
    return True
