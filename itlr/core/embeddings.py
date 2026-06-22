"""Lớp trừu tượng cho embedding model — hỗ trợ model SOTA 2024 + tiền tố query/passage.

Mục tiêu: dễ dàng nâng cấp từ MiniLM (2021) lên model hiện đại (multilingual-e5,
BGE-M3) mà không phải sửa rải rác. Một số model (họ E5) BẮT BUỘC thêm tiền tố
"query: " / "passage: " mới đạt chất lượng tối đa — registry này encode đúng quy tắc đó.

Chọn model qua biến môi trường EMBEDDING_MODEL (vd: EMBEDDING_MODEL=e5-base).
App nạp tên model + tiền tố từ artifacts/search_meta.pkl nên không cần sửa code khi đổi.
"""

import os

import numpy as np

# Registry các preset. query_prefix/passage_prefix theo đúng yêu cầu từng họ model.
PRESETS = {
    # 2021 — nhẹ, mặc định cũ (giữ để tương thích ngược)
    "minilm": {
        "model_name": "paraphrase-multilingual-MiniLM-L12-v2",
        "query_prefix": "",
        "passage_prefix": "",
        "dim": 384,
    },
    # 2024 — multilingual E5 (CẦN tiền tố query:/passage:), tiếng Việt tốt hơn hẳn
    "e5-base": {
        "model_name": "intfloat/multilingual-e5-base",
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "dim": 768,
    },
    "e5-large": {
        "model_name": "intfloat/multilingual-e5-large",
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "dim": 1024,
    },
    # 2024 — BGE-M3 (không cần tiền tố), đa ngữ rất mạnh, 1024 chiều
    "bge-m3": {
        "model_name": "BAAI/bge-m3",
        "query_prefix": "",
        "passage_prefix": "",
        "dim": 1024,
    },
}

# Mặc định: e5-base (cân bằng chất lượng/độ nặng). Đổi qua EMBEDDING_MODEL.
DEFAULT_PRESET = "e5-base"


def resolve_preset(name=None):
    """Trả về dict cấu hình preset. name có thể là khóa preset hoặc tên model HF trực tiếp."""
    name = name or os.environ.get("EMBEDDING_MODEL", DEFAULT_PRESET)
    if name in PRESETS:
        return dict(PRESETS[name])
    # Cho phép truyền thẳng tên model HuggingFace (không tiền tố)
    return {"model_name": name, "query_prefix": "", "passage_prefix": "", "dim": None}


def load_model(model_name):
    """Nạp SentenceTransformer (tôn trọng HF_HUB_OFFLINE nếu đã set ở môi trường)."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def encode_passages(model, texts, preset, batch_size=64, show_progress_bar=False):
    """Mã hóa danh sách tài liệu (thêm passage_prefix), trả về float32 đã chuẩn hóa L2."""
    prefix = preset.get("passage_prefix", "")
    prepared = [f"{prefix}{t}" for t in texts] if prefix else list(texts)
    emb = model.encode(
        prepared,
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=show_progress_bar,
    )
    return emb.astype(np.float32)


def encode_query(model, query, preset):
    """Mã hóa MỘT truy vấn (thêm query_prefix), trả về vector float32 chuẩn hóa L2."""
    prefix = preset.get("query_prefix", "")
    text = f"{prefix}{query}"
    return model.encode(
        [text], normalize_embeddings=True, convert_to_numpy=True
    )[0].astype(np.float32)


def meta_from_preset(preset):
    """Thông tin lưu vào search_meta.pkl để app encode truy vấn nhất quán lúc chạy."""
    return {
        "model_name": preset["model_name"],
        "query_prefix": preset.get("query_prefix", ""),
        "passage_prefix": preset.get("passage_prefix", ""),
    }
