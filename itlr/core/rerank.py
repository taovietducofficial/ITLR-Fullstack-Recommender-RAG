"""Cross-Encoder reranker — tầng 2 của truy hồi 2 tầng (retrieve → rerank).

Chuẩn hiện đại cho tìm kiếm chất lượng cao: bi-encoder (embeddings) truy hồi nhanh
top-N, rồi cross-encoder chấm điểm TỪNG cặp (truy vấn, tài liệu) để xếp lại top-K.
Cross-encoder chính xác hơn nhiều vì xử lý truy vấn + tài liệu CÙNG LÚC, nhưng nặng
nên chỉ áp cho vài chục ứng viên.

Fail-safe: thiếu thư viện/không tải được model -> trả None ở get_reranker(),
caller giữ nguyên thứ tự embeddings (hệ thống vẫn chạy bình thường).
"""

import os

_RERANKER = None

DEFAULT_RERANKER = "BAAI/bge-reranker-base"


def get_reranker():
    """Nạp (lười, một lần) CrossEncoder. Trả về model hoặc None nếu không khả dụng."""
    global _RERANKER
    if _RERANKER is not None:
        return _RERANKER or None

    if os.environ.get("DISABLE_RERANKER"):
        _RERANKER = False
        return None

    name = os.environ.get("RERANKER_MODEL", DEFAULT_RERANKER)
    try:
        from sentence_transformers import CrossEncoder

        _RERANKER = CrossEncoder(name, max_length=512)
    except Exception:
        _RERANKER = False
        return None
    return _RERANKER


def _sigmoid(x):
    import numpy as np

    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype="float64")))


def rerank(query, candidates, text_of, top_k=None, reranker=None):
    """Xếp lại danh sách ứng viên bằng cross-encoder.

    - query:       chuỗi truy vấn (đã chuẩn hóa/sửa lỗi nếu muốn)
    - candidates:  list bất kỳ
    - text_of:     hàm map candidate -> đoạn văn bản tài liệu để chấm
    - reranker:    CrossEncoder (nếu None sẽ tự get_reranker())
    Trả về: list (candidate, rerank_score_in_0_1) đã xếp giảm dần. Nếu reranker
    không khả dụng -> trả candidates nguyên thứ tự với score None.
    """
    if not candidates:
        return []
    model = reranker if reranker is not None else get_reranker()
    if model is None:
        return [(c, None) for c in (candidates if top_k is None else candidates[:top_k])]

    pairs = [[query, text_of(c)] for c in candidates]
    try:
        raw = model.predict(pairs, convert_to_numpy=True, show_progress_bar=False)
    except Exception:
        return [(c, None) for c in (candidates if top_k is None else candidates[:top_k])]

    scores = _sigmoid(raw)
    ranked = sorted(zip(candidates, scores), key=lambda x: float(x[1]), reverse=True)
    if top_k is not None:
        ranked = ranked[:top_k]
    return [(c, float(s)) for c, s in ranked]
