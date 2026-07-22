"""Chỉ mục vector ANN (Approximate/Exact Nearest Neighbor) kiểu vector-DB.

Dùng FAISS (IndexFlatIP — inner product trên vector đã chuẩn hóa = cosine, chính xác
và không cần train) làm tầng truy hồi dày (dense) tốc độ cao, mở rộng được lên hàng
triệu mục. Nếu FAISS chưa cài (vd Python quá mới chưa có wheel) -> fallback hnswlib
-> fallback None (caller tự brute-force bằng nhân ma trận như cũ).

Mọi hàm fail-safe: lỗi/không có thư viện -> trả None, hệ thống vẫn chạy.
"""

import os
import pickle

import numpy as np

FAISS_PATH = os.path.join("artifacts", "ann_index.faiss")
HNSW_PATH = os.path.join("artifacts", "ann_index.hnsw")
META_PATH = os.path.join("artifacts", "ann_meta.pkl")


def _try_import_faiss():
    try:
        import faiss  # noqa: F401
        return faiss
    except Exception:
        return None


def _try_import_hnswlib():
    try:
        import hnswlib  # noqa: F401
        return hnswlib
    except Exception:
        return None


def build_ann(embeddings, artifacts_dir="artifacts"):
    """Xây chỉ mục từ ma trận embeddings (n x d, đã chuẩn hóa L2). Ưu tiên FAISS -> hnswlib -> None."""
    embeddings = np.ascontiguousarray(embeddings.astype(np.float32))
    n, d = embeddings.shape

    faiss = _try_import_faiss()
    if faiss is not None:
        index = faiss.IndexFlatIP(d)
        index.add(embeddings)
        faiss.write_index(index, os.path.join(artifacts_dir, "ann_index.faiss"))
        pickle.dump({"backend": "faiss", "n": n, "dim": d},
                    open(os.path.join(artifacts_dir, "ann_meta.pkl"), "wb"))
        return "faiss"

    hnswlib = _try_import_hnswlib()
    if hnswlib is not None:
        index = hnswlib.Index(space="cosine", dim=d)
        index.init_index(max_elements=n, ef_construction=200, M=16)
        index.add_items(embeddings, np.arange(n))
        index.set_ef(64)
        index.save_index(os.path.join(artifacts_dir, "ann_index.hnsw"))
        pickle.dump({"backend": "hnswlib", "n": n, "dim": d},
                    open(os.path.join(artifacts_dir, "ann_meta.pkl"), "wb"))
        return "hnswlib"

    return None


def load_ann(artifacts_dir="artifacts"):
    """Nạp chỉ mục đã build. Trả về dict {backend, index} hoặc None nếu không có/không nạp được."""
    meta_path = os.path.join(artifacts_dir, "ann_meta.pkl")
    if not os.path.exists(meta_path):
        return None
    try:
        meta = pickle.load(open(meta_path, "rb"))
    except Exception:
        return None

    backend = meta.get("backend")
    if backend == "faiss":
        faiss = _try_import_faiss()
        if faiss is None:
            return None
        path = os.path.join(artifacts_dir, "ann_index.faiss")
        if not os.path.exists(path):
            return None
        return {"backend": "faiss", "index": faiss.read_index(path)}

    if backend == "hnswlib":
        hnswlib = _try_import_hnswlib()
        if hnswlib is None:
            return None
        path = os.path.join(artifacts_dir, "ann_index.hnsw")
        if not os.path.exists(path):
            return None
        index = hnswlib.Index(space="cosine", dim=meta["dim"])
        index.load_index(path, max_elements=meta["n"])
        index.set_ef(max(64, 0))
        return {"backend": "hnswlib", "index": index}

    return None


def ann_search(ann, query_vec, top_n=200):
    """Tìm top_n láng giềng. Trả về (indices: np.int64[], scores: cosine float[]) hoặc None."""
    if ann is None:
        return None
    q = np.ascontiguousarray(query_vec.astype(np.float32).reshape(1, -1))
    try:
        if ann["backend"] == "faiss":
            scores, idx = ann["index"].search(q, top_n)
            return idx[0], scores[0]
        if ann["backend"] == "hnswlib":
            labels, distances = ann["index"].knn_query(q, k=top_n)
            return labels[0].astype(np.int64), (1.0 - distances[0])
    except Exception:
        return None
    return None
