"""Build item embeddings + calibration cho ô TÌM KIẾM ngữ nghĩa.

Chạy SAU build_model.py (cần artifacts/item_list.pkl để căn đúng thứ tự với app).
Ghi ra:
  - artifacts/embeddings.pkl     : vector embedding của từng item (float32, n x 384)
  - artifacts/search_meta.pkl    : {model_name, lo, hi} để app mã hóa truy vấn + calibrate

    python build_embeddings.py

Lưu ý: chạy bằng CÙNG Python dùng để chạy app (python hệ thống) để thống nhất môi trường.
"""

import os
import pickle

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from sklearn.feature_extraction.text import TfidfVectorizer

from itlr import config
from itlr.core.embeddings import encode_passages, load_model, meta_from_preset, resolve_preset
from itlr.core.recommender import strip_accents

ARTIFACTS = str(config.ARTIFACTS_DIR)


def build_char_index(items):
    """Char n-gram TF-IDF (bỏ dấu) trên title+topics+category — chịu lỗi chính tả/thiếu dấu."""
    searchable = [
        strip_accents(f"{r['title']} {r['topics']} {r['category']}")
        for _, r in items.iterrows()
    ]
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
    matrix = vec.fit_transform(searchable)
    pickle.dump(vec, open(os.path.join(ARTIFACTS, "char_vectorizer.pkl"), "wb"))
    pickle.dump(matrix, open(os.path.join(ARTIFACTS, "char_matrix.pkl"), "wb"))
    print(f"Đã lưu char_vectorizer.pkl + char_matrix.pkl {matrix.shape}")


def build_text(row):
    """Câu tự nhiên để encode. Lowercase để embedding bất biến với HOA/thường
    (khớp với việc lowercase truy vấn trong search_by_embedding)."""
    return (
        f"{str(row['title']).strip()}. "
        f"Thể loại: {str(row['category']).strip()}. "
        f"Chủ đề: {str(row['topics']).strip()}. "
        f"{str(row['description']).strip()}"
    ).lower()


def main():
    items = pickle.load(open(os.path.join(ARTIFACTS, "item_list.pkl"), "rb")).reset_index(drop=True)
    n = len(items)
    print(f"Items: {n}")

    preset = resolve_preset()
    print(f"Embedding model: {preset['model_name']}")
    model = load_model(preset["model_name"])
    texts = [build_text(row) for _, row in items.iterrows()]
    embeddings = encode_passages(model, texts, preset, batch_size=64, show_progress_bar=True)

    pickle.dump(embeddings, open(os.path.join(ARTIFACTS, "embeddings.pkl"), "wb"))
    pickle.dump(
        meta_from_preset(preset),
        open(os.path.join(ARTIFACTS, "search_meta.pkl"), "wb"),
    )
    print(f"Đã lưu embeddings.pkl {embeddings.shape} + search_meta.pkl")

    try:
        from itlr.core.ann import build_ann

        backend = build_ann(embeddings, ARTIFACTS)
        if backend:
            print(f"Đã build chỉ mục ANN ({backend}) -> ann_index.*")
        else:
            print("Bỏ qua ANN (chưa cài faiss/hnswlib) — app sẽ brute-force như cũ.")
    except Exception as exc:
        print(f"Bỏ qua ANN do lỗi: {exc}")

    build_char_index(items)


if __name__ == "__main__":
    main()
