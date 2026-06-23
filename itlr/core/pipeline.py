"""Phễu xếp hạng nhiều tầng (multi-stage ranking) — Trụ cột A.

Chính thức hóa cấu trúc phễu mà hệ thống vốn đã ngầm có, đặt tên rõ ràng và cho phép
BẬT/TẮT độc lập từng tầng (phục vụ ablation + đo chi phí–chất lượng từng tầng):

  Stage 0 — Candidate Generation : lọc thô 50k -> vài trăm (ưu tiên không bỏ sót).
            Nguồn: embeddings (ANN/FAISS) · BM25 · TF-IDF · hoặc hợp nhất RAG-Fusion.
  Stage 1 — L1 Ranking (nhẹ)     : chấm điểm hybrid rẻ (tfidf/bm25/category/topic).
  Stage 2 — L2 Re-ranking (nặng) : Cross-Encoder rerank (hoặc Learning-to-Rank — Trụ cột C).
  Stage 3 — Re-ordering          : đa dạng hóa (MMR) + luật nghiệp vụ.

Khác với các hàm trong recommender.py (hướng HIỂN THỊ — có cổng off-topic, sàn điểm, dải
% 90-100), module này hướng ĐÁNH GIÁ: trả về danh sách VỊ TRÍ item đã xếp hạng đủ dài
(để đo Recall@100/@500), không áp cổng hiển thị. Tái dùng toàn bộ primitive sẵn có.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from itlr.core import recommender as R


# ─────────────────────────────────────────────────────────────────────────────
# Ngữ cảnh đánh giá: gói artifacts cần cho mọi tầng (nạp một lần, tái dùng)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class RankContext:
    item_list: object                       # DataFrame catalog đã tiền xử lý
    retrieval_model: dict                    # {vectorizers, matrices, bm25, categories}
    embeddings: Optional[np.ndarray] = None  # n×d đã chuẩn hóa L2
    embed_model: object = None               # SentenceTransformer (encode truy vấn)
    char_vectorizer: object = None
    char_matrix: object = None
    query_prefix: str = ""
    ann: object = None                       # chỉ mục FAISS (tùy chọn)
    reranker: object = None                  # cross-encoder (tùy chọn)
    ltr_scorer: Optional[Callable] = None    # Trụ cột C: scorer(query, positions)->scores
    cf_popularity: object = None             # vector độ phổ biến (cho đặc trưng LTR)

    # cache nội bộ
    _cat_array: object = None
    _topics_cache: object = None

    def __post_init__(self):
        self._cat_array = self.item_list["category"].to_numpy()
        # tiền xử lý topic mỗi item một lần (tăng tốc tín hiệu topic ở L1)
        self._topics_cache = [R.parse_topics(t) for t in self.item_list["topics"]]


@dataclass
class StageConfig:
    """Cấu hình bật/tắt từng tầng + nguồn ứng viên. Dùng cho cả ablation lẫn production."""
    name: str = "full"
    candidate_source: str = "embedding"      # tfidf | bm25 | lexical | embedding | rag_fusion
    l1_signals: frozenset = field(default_factory=frozenset)  # {category, topic, title, type}
    use_rerank: bool = False                 # Stage 2 cross-encoder
    use_ltr: bool = False                    # Stage 2 Learning-to-Rank (ưu tiên hơn rerank nếu bật)
    use_mmr: bool = False                    # Stage 3 đa dạng hóa
    candidate_k: int = 600                   # số ứng viên Stage 0
    rerank_pool: int = 48                    # số ứng viên đưa vào Stage 2
    mmr_lambda: float = 0.7
    mmr_k: int = 10


# ─────────────────────────────────────────────────────────────────────────────
# Stage 0 — Candidate Generation
# ─────────────────────────────────────────────────────────────────────────────
def _tfidf_scores(ctx: RankContext, query: str) -> np.ndarray:
    return R._fuse_tfidf_scores(query, ctx.retrieval_model["vectorizers"], ctx.retrieval_model["matrices"])


def _bm25_scores(ctx: RankContext, query: str) -> np.ndarray:
    bm25 = ctx.retrieval_model["bm25"]
    return np.asarray(bm25.normalize_scores(bm25.score_query(query)))


def _embedding_scores(ctx: RankContext, query: str) -> np.ndarray:
    """Điểm ngữ nghĩa = max(cosine embeddings, char n-gram bỏ dấu) — giống search_by_embedding."""
    score, _ = R._combined_scores(
        query, ctx.item_list, ctx.embed_model, ctx.embeddings,
        ctx.char_vectorizer, ctx.char_matrix, ctx.query_prefix, ctx.ann,
    )
    return np.asarray(score, dtype="float64")


def _base_scores(ctx: RankContext, query: str, source: str) -> np.ndarray:
    if source == "tfidf":
        return _tfidf_scores(ctx, query)
    if source == "bm25":
        return _bm25_scores(ctx, query)
    if source == "lexical":
        w = R.SCORE_WEIGHTS
        denom = w["tfidf"] + w["bm25"]
        return (w["tfidf"] * _tfidf_scores(ctx, query) + w["bm25"] * _bm25_scores(ctx, query)) / denom
    if source in ("embedding", "rag_fusion"):
        return _embedding_scores(ctx, query)
    raise ValueError(f"Nguồn ứng viên không hợp lệ: {source}")


def candidate_generation(ctx: RankContext, query: str, cfg: StageConfig) -> List[int]:
    """Stage 0: trả về danh sách vị trí item ứng viên (đã xếp theo điểm thô giảm dần)."""
    if cfg.candidate_source == "rag_fusion":
        return _rag_fusion_candidates(ctx, query, cfg)
    scores = _base_scores(ctx, query, cfg.candidate_source)
    k = min(cfg.candidate_k, scores.shape[0])
    top = np.argpartition(scores, -k)[-k:]
    top = top[np.argsort(scores[top])[::-1]]
    return top.tolist()


def _query_variants(query: str) -> List[str]:
    """Sinh biến thể truy vấn cho RAG-Fusion: gốc + bản bỏ dấu (chịu input thiếu dấu).

    Hai biến thể truy hồi độc lập rồi hợp nhất bằng RRF -> bền với cách gõ có/không dấu.
    (Không dùng biến thể đảo cụm: thêm nhiễu mà không thêm tín hiệu.)
    """
    variants = [query]
    bare = R.strip_accents(query)
    if bare != query.lower():
        variants.append(bare)
    return variants


def _rag_fusion_candidates(ctx: RankContext, query: str, cfg: StageConfig) -> List[int]:
    """RAG-Fusion: truy hồi nhiều biến thể truy vấn rồi hợp nhất bằng Reciprocal Rank Fusion."""
    rankings = []
    for q in _query_variants(query):
        s = _embedding_scores(ctx, q)
        k = min(cfg.candidate_k, s.shape[0])
        top = np.argpartition(s, -k)[-k:]
        top = top[np.argsort(s[top])[::-1]]
        rankings.append(top.tolist())
    fused = R.reciprocal_rank_fusion(rankings)        # [(pos, rrf)] giảm dần
    return [pos for pos, _ in fused[:cfg.candidate_k]]


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 — L1 Ranking (nhẹ): bổ sung tín hiệu category/topic/title rẻ
# ─────────────────────────────────────────────────────────────────────────────
def l1_rank(ctx: RankContext, query: str, candidates: Sequence[int], cfg: StageConfig,
            base_scores: Optional[np.ndarray] = None) -> List[tuple]:
    """Chấm lại điểm các ứng viên bằng hybrid nhẹ. Trả [(pos, score)] giảm dần."""
    if not cfg.l1_signals:
        # không thêm tín hiệu -> giữ nguyên thứ tự Stage 0 (gán điểm giảm dần giả lập)
        n = len(candidates)
        return [(p, float(n - i)) for i, p in enumerate(candidates)]

    category_hint = R.detect_category_from_query(query, ctx.retrieval_model["categories"])
    q_topics = set(R.extract_query_tokens(query))
    scored = []
    for p in candidates:
        row = ctx.item_list.iloc[p]
        base = float(base_scores[p]) if base_scores is not None else 0.0
        s = base
        if "category" in cfg.l1_signals and category_hint:
            s += R.SCORE_WEIGHTS["category"] * R.category_bonus(category_hint, row["category"])
        if "topic" in cfg.l1_signals:
            rt = ctx._topics_cache[p]
            s += R.SCORE_WEIGHTS["topic_jaccard"] * R.topic_jaccard(q_topics, rt)
            s += R.SCORE_WEIGHTS["topic_contain"] * R.topic_containment(q_topics, rt)
        if "title" in cfg.l1_signals:
            s += R.SCORE_WEIGHTS["title_overlap"] * R.title_keyword_overlap(query, row["title"])
        scored.append((p, s))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — L2 Re-ranking (nặng): Cross-Encoder hoặc Learning-to-Rank
# ─────────────────────────────────────────────────────────────────────────────
def l2_rerank(ctx: RankContext, query: str, ranked: List[tuple], cfg: StageConfig) -> List[tuple]:
    pool = ranked[: cfg.rerank_pool]
    rest = ranked[cfg.rerank_pool:]

    if cfg.use_ltr and ctx.ltr_scorer is not None and pool:
        positions = [p for p, _ in pool]
        scores = ctx.ltr_scorer(query, positions)
        reranked = sorted(zip(positions, scores), key=lambda x: x[1], reverse=True)
        return reranked + rest

    if cfg.use_rerank and ctx.reranker is not None and pool:
        from itlr.core.rerank import rerank as _rr
        ranked_pool = _rr(
            query, pool,
            text_of=lambda c: R._rerank_doc(ctx.item_list.iloc[c[0]]),
            reranker=ctx.reranker,
        )
        if ranked_pool and ranked_pool[0][1] is not None:
            reranked = [(c[0], float(s)) for c, s in ranked_pool]
            return reranked + rest
    return ranked


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 — Re-ordering: đa dạng hóa MMR
# ─────────────────────────────────────────────────────────────────────────────
def l3_reorder(ctx: RankContext, ranked: List[tuple], cfg: StageConfig) -> List[tuple]:
    if not cfg.use_mmr or ctx.embeddings is None:
        return ranked
    pool = ranked[: max(cfg.rerank_pool, cfg.mmr_k * 3)]
    rest = ranked[len(pool):]
    idxs = [p for p, _ in pool]
    rels = [s for _, s in pool]
    sub = ctx.embeddings[idxs] @ ctx.embeddings[idxs].T
    selected = R.mmr_rerank([(k, rels[k]) for k in range(len(pool))],
                            sub, top_n=cfg.mmr_k, lambda_param=cfg.mmr_lambda)
    chosen = [k for k, _ in selected]
    chosen_set = set(chosen)
    out = [(idxs[k], rels[k]) for k in chosen]
    out += [(idxs[k], rels[k]) for k in range(len(pool)) if k not in chosen_set]
    return out + rest


# ─────────────────────────────────────────────────────────────────────────────
# Phễu đầy đủ
# ─────────────────────────────────────────────────────────────────────────────
def rank(ctx: RankContext, query: str, cfg: StageConfig, top_n: int = 500) -> List[int]:
    """Chạy phễu theo cấu hình -> trả về danh sách VỊ TRÍ item đã xếp hạng (dài tới top_n)."""
    base = None
    if cfg.candidate_source != "rag_fusion":
        base = _base_scores(ctx, query, cfg.candidate_source)
    candidates = candidate_generation(ctx, query, cfg)
    ranked = l1_rank(ctx, query, candidates, cfg, base_scores=base)
    ranked = l2_rerank(ctx, query, ranked, cfg)
    ranked = l3_reorder(ctx, ranked, cfg)
    return [p for p, _ in ranked[:top_n]]


# ─────────────────────────────────────────────────────────────────────────────
# Preset ablation (Trụ cột B — bảng ablation)
# ─────────────────────────────────────────────────────────────────────────────
def ablation_configs() -> Dict[str, StageConfig]:
    """Các cấu hình cho bảng ablation: chứng minh từng thành phần đóng góp bao nhiêu."""
    return {
        "TF-IDF only": StageConfig(name="TF-IDF only", candidate_source="tfidf"),
        "BM25 only": StageConfig(name="BM25 only", candidate_source="bm25"),
        "Hybrid lexical (TF-IDF+BM25)": StageConfig(
            name="Hybrid lexical (TF-IDF+BM25)", candidate_source="lexical"),
        "Embeddings (E5)": StageConfig(name="Embeddings (E5)", candidate_source="embedding"),
        "+ L1 hybrid signals": StageConfig(
            name="+ L1 hybrid signals", candidate_source="embedding",
            l1_signals=frozenset({"category", "topic", "title"})),
        "+ Cross-Encoder": StageConfig(
            name="+ Cross-Encoder", candidate_source="embedding",
            l1_signals=frozenset({"category", "topic", "title"}), use_rerank=True),
        "+ RAG-Fusion + MMR (Full)": StageConfig(
            name="+ RAG-Fusion + MMR (Full)", candidate_source="rag_fusion",
            l1_signals=frozenset({"category", "topic", "title"}),
            use_rerank=True, use_mmr=True),
    }
