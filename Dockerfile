# ─────────────────────────────────────────────────────────────────────────────
# Recommender Python (FastAPI + ML) — phục vụ search ngữ nghĩa, chatbot RAG, CF.
# Artifacts (~550MB) KHÔNG bake vào image — mount qua volume (xem docker-compose).
# Model embedding/reranker tải từ HuggingFace ở lần chạy đầu (cần internet) và được
# cache vào volume hf-cache.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libgomp1: cần cho faiss/torch; build-essential: phòng khi có wheel build từ nguồn.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

# Cài dependencies trước (tận dụng cache layer khi chỉ đổi code).
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Mã nguồn (var/artifacts, var/data nạp qua volume lúc chạy, không copy vào image).
COPY itlr ./itlr
COPY scripts ./scripts
COPY pyproject.toml ./

EXPOSE 8000

# Healthcheck: trang gốc "/" trả 200 khi engine đã nạp xong.
# start-period dài vì lần chạy đầu phải tải/ nạp model embedding + reranker.
HEALTHCHECK --interval=20s --timeout=5s --start-period=180s --retries=5 \
  CMD curl -fsS http://localhost:8000/ || exit 1

# Lưu ý: server tự setdefault HF_HUB_OFFLINE=1; compose đặt =0 để tải model lần đầu.
CMD ["uvicorn", "itlr.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
