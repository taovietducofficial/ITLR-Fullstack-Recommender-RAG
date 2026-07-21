"""Metric "beyond-accuracy" — vượt khỏi độ chính xác thuần.

Đo các phẩm chất mà accuracy không nắm bắt: hệ có phơi bày được nhiều catalog không
(Coverage), kết quả có đa dạng không (Intra-list Diversity), có mới mẻ không (Novelty),
có bất ngờ-mà-vẫn-liên-quan không (Serendipity), và phơi bày item có công bằng không
(Gini / long-tail). Đầu vào là danh sách kết quả (vị trí item) cho nhiều truy vấn.
"""

from __future__ import annotations

from typing import Dict, Sequence

import numpy as np


def catalog_coverage(recommended_lists: Sequence[Sequence[int]], n_items: int) -> float:
    """Tỉ lệ % catalog từng được gợi ý ít nhất một lần qua tất cả truy vấn."""
    if n_items <= 0:
        return 0.0
    seen = set()
    for lst in recommended_lists:
        seen.update(int(i) for i in lst)
    return len(seen) / n_items


def intra_list_diversity(item_indices: Sequence[int], embeddings: np.ndarray) -> float:
    """ILD = 1 − cosine trung bình giữa mọi cặp item trong MỘT danh sách kết quả.

    `embeddings` giả định đã chuẩn hóa L2 (dot = cosine). Cao = đa dạng.
    """
    idx = [int(i) for i in item_indices]
    if len(idx) < 2:
        return 0.0
    vecs = embeddings[idx]
    sims = vecs @ vecs.T
    n = len(idx)
    off_diag_sum = sims.sum() - np.trace(sims)
    avg_sim = off_diag_sum / (n * (n - 1))
    return float(1.0 - avg_sim)


def mean_intra_list_diversity(recommended_lists: Sequence[Sequence[int]], embeddings: np.ndarray) -> float:
    vals = [intra_list_diversity(lst, embeddings) for lst in recommended_lists if len(lst) >= 2]
    return float(np.mean(vals)) if vals else 0.0


def novelty(recommended_lists: Sequence[Sequence[int]], popularity: np.ndarray) -> float:
    """Novelty trung bình = −log2(p(item)) trên các item được gợi ý.

    `popularity[i]` = số lần item i được tương tác (hoặc trọng số phổ biến bất kỳ ≥ 0).
    Item càng hiếm gặp -> novelty càng cao.
    """
    pop = np.asarray(popularity, dtype="float64")
    total = pop.sum()
    if total <= 0:
        return 0.0
    probs = (pop + 1.0) / (total + len(pop))
    vals = []
    for lst in recommended_lists:
        for i in lst:
            vals.append(-np.log2(probs[int(i)]))
    return float(np.mean(vals)) if vals else 0.0


def serendipity(
    recommended_lists: Sequence[Sequence[int]],
    relevant_sets: Sequence[set],
    expected_sets: Sequence[set],
) -> float:
    """Serendipity = tỉ lệ item VỪA liên quan VỪA bất ngờ (không nằm trong tập 'hiển nhiên').

    `relevant_sets[q]`  : item liên quan thật của truy vấn q (nhãn vàng).
    `expected_sets[q]`  : item "hiển nhiên/đoán được" (vd top phổ biến cùng category).
    Item serendipitous = relevant ∧ ∉ expected.
    """
    scores = []
    for lst, rel, exp in zip(recommended_lists, relevant_sets, expected_sets):
        if not lst:
            continue
        good = sum(1 for i in lst if int(i) in rel and int(i) not in exp)
        scores.append(good / len(lst))
    return float(np.mean(scores)) if scores else 0.0


def gini_index(recommended_lists: Sequence[Sequence[int]], n_items: int) -> float:
    """Hệ số Gini của phân bố tần suất gợi ý (0 = công bằng tuyệt đối, 1 = tập trung).

    Cao = vài item chiếm hầu hết lượt phơi bày (thiên lệch phổ biến); thấp = công bằng.
    """
    counts = np.zeros(n_items, dtype="float64")
    for lst in recommended_lists:
        for i in lst:
            counts[int(i)] += 1
    total = counts.sum()
    if total <= 0:
        return 0.0
    sorted_counts = np.sort(counts)
    n = counts.size
    index = np.arange(1, n + 1)
    return float((np.sum((2 * index - n - 1) * sorted_counts)) / (n * total))


def beyond_accuracy_report(
    recommended_lists: Sequence[Sequence[int]],
    n_items: int,
    embeddings: np.ndarray | None = None,
    popularity: np.ndarray | None = None,
) -> Dict[str, float]:
    """Gộp các metric beyond-accuracy chính thành một dict."""
    rep: Dict[str, float] = {
        "Coverage": catalog_coverage(recommended_lists, n_items),
        "Gini": gini_index(recommended_lists, n_items),
    }
    if embeddings is not None:
        rep["ILD"] = mean_intra_list_diversity(recommended_lists, embeddings)
    if popularity is not None:
        rep["Novelty"] = novelty(recommended_lists, popularity)
    return rep
