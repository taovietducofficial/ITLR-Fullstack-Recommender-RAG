"""Re-pickle artifacts để (1) đóng dấu phiên bản scikit-learn hiện hành và
(2) cập nhật ĐƯỜNG DẪN MODULE sau khi tái cấu trúc sang package itlr/.

Vì sao cần: pickle lưu lớp/hàm tùy biến theo đường dẫn module (vd hàm tokenizer
`recommender_utils.tokenize`, lớp `bm25_utils.BM25Index`). Sau khi di chuyển code
sang `itlr.core.*`, các pickle cũ trỏ tới module CŨ -> ModuleNotFoundError khi nạp.

Cách xử lý: tạm ALIAS tên module cũ -> module mới trong sys.modules để nạp được,
rồi DUMP LẠI. Khi dump, pickle ghi theo `__module__` thật của đối tượng (đã là
`itlr.core.*`) -> artifact trỏ đường dẫn MỚI, không cần alias ở lần chạy sau, và
KHÔNG refit/đổi dữ liệu (số hàng giữ nguyên, đồng bộ embeddings/ann).

Chạy MỘT lần sau tái cấu trúc:  python -m itlr.utils.repickle
"""

import pickle
import sys
import warnings

from itlr import config
from itlr.core import ann as _ann
from itlr.core import bm25 as _bm25
from itlr.core import embeddings as _embeddings
from itlr.core import rag as _rag
from itlr.core import recommender as _recommender
from itlr.core import rerank as _rerank
from itlr.chatbot import knowledge_base as _kb
from itlr.chatbot import query_understanding as _qu

_ALIASES = {
    "recommender_utils": _recommender,
    "bm25_utils": _bm25,
    "embedding_utils": _embeddings,
    "ann_utils": _ann,
    "rerank_utils": _rerank,
    "rag_utils": _rag,
    "knowledge_base": _kb,
    "query_understanding": _qu,
}

TARGETS = [
    "retrieval_model.pkl",
    "tfidf_vectorizer.pkl",
    "tfidf_matrix.pkl",
    "char_vectorizer.pkl",
    "cf_model.pkl",
    "item_list.pkl",
]


def main():
    for old, mod in _ALIASES.items():
        sys.modules.setdefault(old, mod)

    for name in TARGETS:
        path = config.artifact(name)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                with open(path, "rb") as f:
                    obj = pickle.load(f)
            with open(path, "wb") as f:
                pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
            print(f"[OK] re-pickled {name}")
        except FileNotFoundError:
            print(f"[skip] không thấy {name}")
        except Exception as e:  # pragma: no cover
            print(f"[ERR] {name}: {e!r}")


if __name__ == "__main__":
    main()
