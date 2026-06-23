"""Metric xếp hạng chuẩn ngành (Information Retrieval / Recommender).

Cài đặt bằng numpy thuần. Quy ước đầu vào:

  - `ranked_rels`: list/array độ liên quan (relevance) của các item THEO ĐÚNG THỨ TỰ
    hệ thống trả về. Relevance là số nguyên không âm (graded): 0 = không liên quan,
    1 = liên quan một phần, 2 = liên quan mạnh. Nhị phân là trường hợp đặc biệt (0/1).
  - `n_relevant`: tổng số item liên quan (rel > 0) tồn tại cho truy vấn đó trong nhãn
    vàng — cần cho Recall và (chuẩn) cho MAP.

Mọi hàm trả về một float trong [0, 1]. Hàm `evaluate_run` gộp nhiều truy vấn -> dict
metric trung bình, kèm chuẩn K ∈ {1, 3, 5, 10, 100}.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence

import numpy as np

DEFAULT_KS = (1, 3, 5, 10, 100)


def _as_array(ranked_rels: Sequence[float]) -> np.ndarray:
    return np.asarray(list(ranked_rels), dtype="float64")


# ─────────────────────────────────────────────────────────────────────────────
# Metric đơn truy vấn (per-query)
# ─────────────────────────────────────────────────────────────────────────────
def precision_at_k(ranked_rels: Sequence[float], k: int) -> float:
    """Tỉ lệ item liên quan (rel > 0) trong K kết quả đầu."""
    if k <= 0:
        return 0.0
    top = _as_array(ranked_rels)[:k]
    if top.size == 0:
        return 0.0
    return float((top > 0).sum()) / k


def recall_at_k(ranked_rels: Sequence[float], k: int, n_relevant: int) -> float:
    """Tỉ lệ item liên quan bắt được trong top-K trên tổng số item liên quan."""
    if n_relevant <= 0 or k <= 0:
        return 0.0
    top = _as_array(ranked_rels)[:k]
    return float((top > 0).sum()) / n_relevant


def hit_rate_at_k(ranked_rels: Sequence[float], k: int) -> float:
    """1.0 nếu có ÍT NHẤT một item liên quan trong top-K, ngược lại 0.0."""
    top = _as_array(ranked_rels)[:k]
    return 1.0 if (top > 0).any() else 0.0


def dcg_at_k(ranked_rels: Sequence[float], k: int) -> float:
    """Discounted Cumulative Gain với gain mũ (2^rel − 1) và chiết khấu log2(rank+1)."""
    rels = _as_array(ranked_rels)[:k]
    if rels.size == 0:
        return 0.0
    gains = (2.0 ** rels) - 1.0
    discounts = 1.0 / np.log2(np.arange(2, rels.size + 2))
    return float(np.sum(gains * discounts))


def ndcg_at_k(ranked_rels: Sequence[float], k: int, ideal_rels: Sequence[float] | None = None) -> float:
    """Normalized DCG@K. `ideal_rels` = toàn bộ relevance khả dĩ (để dựng IDCG lý tưởng).

    Nếu không truyền `ideal_rels`, dùng chính `ranked_rels` đã sắp giảm dần làm lý tưởng
    (đủ dùng khi danh sách trả về đã chứa mọi item liên quan).
    """
    if ideal_rels is None:
        ideal = np.sort(_as_array(ranked_rels))[::-1]
    else:
        ideal = np.sort(_as_array(ideal_rels))[::-1]
    idcg = dcg_at_k(ideal, k)
    if idcg <= 0:
        return 0.0
    return dcg_at_k(ranked_rels, k) / idcg


def average_precision(ranked_rels: Sequence[float], n_relevant: int | None = None) -> float:
    """Average Precision: trung bình precision tại mỗi vị trí có hit liên quan.

    Chuẩn hóa theo `n_relevant` (số item liên quan thật). Nếu None, dùng số hit trong list.
    """
    rels = _as_array(ranked_rels)
    hits = rels > 0
    if not hits.any():
        return 0.0
    cum_hits = np.cumsum(hits)
    ranks = np.arange(1, rels.size + 1)
    precisions = cum_hits / ranks
    denom = n_relevant if (n_relevant and n_relevant > 0) else int(hits.sum())
    return float(np.sum(precisions * hits) / denom)


def reciprocal_rank(ranked_rels: Sequence[float]) -> float:
    """Nghịch đảo thứ hạng của item liên quan ĐẦU TIÊN (0 nếu không có)."""
    rels = _as_array(ranked_rels)
    hit_positions = np.where(rels > 0)[0]
    if hit_positions.size == 0:
        return 0.0
    return 1.0 / (hit_positions[0] + 1)


# ─────────────────────────────────────────────────────────────────────────────
# Gộp nhiều truy vấn (run-level)
# ─────────────────────────────────────────────────────────────────────────────
def per_query_metrics(
    ranked_rels: Sequence[float],
    n_relevant: int,
    ks: Iterable[int] = DEFAULT_KS,
    ideal_rels: Sequence[float] | None = None,
) -> Dict[str, float]:
    """Tính toàn bộ metric cho MỘT truy vấn -> dict {metric_name: value}."""
    out: Dict[str, float] = {}
    for k in ks:
        out[f"P@{k}"] = precision_at_k(ranked_rels, k)
        out[f"R@{k}"] = recall_at_k(ranked_rels, k, n_relevant)
        out[f"NDCG@{k}"] = ndcg_at_k(ranked_rels, k, ideal_rels=ideal_rels)
        out[f"HitRate@{k}"] = hit_rate_at_k(ranked_rels, k)
    out["MAP"] = average_precision(ranked_rels, n_relevant)
    out["MRR"] = reciprocal_rank(ranked_rels)
    return out


def evaluate_run(
    per_query: Sequence[Dict[str, float]],
) -> Dict[str, float]:
    """Trung bình các dict metric per-query thành metric tổng (macro-average)."""
    if not per_query:
        return {}
    keys = per_query[0].keys()
    return {k: float(np.mean([q.get(k, 0.0) for q in per_query])) for k in keys}


def evaluate_rankings(
    rankings: Sequence[Sequence[float]],
    n_relevants: Sequence[int],
    ks: Iterable[int] = DEFAULT_KS,
    ideal_rankings: Sequence[Sequence[float]] | None = None,
) -> Dict[str, float]:
    """Tiện ích: nhận danh sách ranked_rels của nhiều truy vấn -> metric tổng.

    `ideal_rankings[i]` (tùy chọn) = toàn bộ relevance khả dĩ cho truy vấn i (để NDCG
    chuẩn hóa đúng kể cả khi list trả về bị cắt ngắn không chứa hết item liên quan).
    """
    rows: List[Dict[str, float]] = []
    for i, (rels, n_rel) in enumerate(zip(rankings, n_relevants)):
        ideal = ideal_rankings[i] if ideal_rankings is not None else None
        rows.append(per_query_metrics(rels, n_rel, ks=ks, ideal_rels=ideal))
    return evaluate_run(rows)
