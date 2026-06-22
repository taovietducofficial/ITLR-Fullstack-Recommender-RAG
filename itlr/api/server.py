"""Web API (FastAPI) cho hệ thống gợi ý + chatbot — THAY Streamlit, không cần streamlit.

Chạy:
    uvicorn itlr.api.server:app --host 0.0.0.0 --port 8000
    # hoặc tiện hơn:
    python -m itlr.api

Phơi bày 3 năng lực như tab Streamlit cũ (mọi logic lõi giữ nguyên):
    POST /api/search     — tìm kiếm ngữ nghĩa
    POST /api/chat       — hỏi đáp chatbot (off-topic gate + khái niệm-trước)
    GET  /api/personas   — danh sách hồ sơ mô phỏng (Dành cho bạn)
    POST /api/for-you    — gợi ý Collaborative Filtering theo persona
    GET  /api/suggested  — câu gợi ý + lời chào của chatbot
    GET  /               — trang web HTML 3 tab (gọi các API trên)
"""

import os
import sys

# Console Windows mặc định mã hóa cp1252 -> emoji/tiếng Việt trong log startup gây
# UnicodeEncodeError, làm CHẾT app startup khi chạy bằng uvicorn thật. Ép stdout/stderr
# sang UTF-8 (no-op nếu đã UTF-8). Phải làm TRƯỚC mọi lệnh print/log có ký tự ngoài ASCII.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Dùng model đã cache, không ping HuggingFace -> tránh treo khi mạng chậm/bị chặn.
# Phải đặt TRƯỚC khi nạp transformers.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import itlr.utils.runtime_patches  # noqa: F401,E402  (dọn nhiễu console trước khi nạp model)

from contextlib import asynccontextmanager  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import List, Optional, Union  # noqa: E402

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from itlr.engine import load_engine  # noqa: E402

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _log(msg):
    """In log an toàn — không bao giờ để lỗi mã hóa console làm chết app startup."""
    try:
        print(msg)
    except Exception:
        try:
            import sys as _sys
            _sys.stdout.write(msg.encode("ascii", "replace").decode() + "\n")
        except Exception:
            pass


@asynccontextmanager
async def lifespan(_app):
    """Nạp artifacts ngay khi khởi động để lỗi (thiếu artifacts) lộ sớm, request đầu nhanh."""
    try:
        load_engine()
        _log("[OK] Engine sẵn sàng — API tại http://localhost:8000")
    except FileNotFoundError:
        _log(
            "[!] Chưa có model artifacts. Hãy build trước:\n"
            "    python scripts/build_all.py\n"
            "(hoặc lần lượt build_model -> build_embeddings -> generate_interactions -> build_cf)"
        )
    yield


app = FastAPI(title="IT Learning Recommender API", version="1.0.0", lifespan=lifespan)


# ── Schema request ────────────────────────────────────────────────────────────
class SearchReq(BaseModel):
    query: str
    type: Optional[str] = None          # "Khóa học" | "Tài liệu" | None (Tất cả)
    min_pct: int = 90


class ChatMsg(BaseModel):
    role: str
    content: str


class ChatReq(BaseModel):
    message: str
    history: List[ChatMsg] = []


class ForYouReq(BaseModel):
    persona: Union[int, str]
    interested: List[int] = []          # item_id user vừa bấm "Quan tâm" trong phiên


# ── Endpoints ────────────────────────────────────────────────────────────────
@app.post("/api/search")
def api_search(req: SearchReq):
    eng = load_engine()
    item_type = req.type if req.type in ("Khóa học", "Tài liệu") else None
    return eng.search(req.query, item_type=item_type, min_pct=req.min_pct)


@app.post("/api/chat")
def api_chat(req: ChatReq):
    eng = load_engine()
    history = [{"role": m.role, "content": m.content} for m in req.history]
    result = eng.chat(req.message, history=history)
    # Chỉ trả các trường cần cho UI (response + recommendations + intent).
    return {
        "response": result["response"],
        "recommendations": result.get("recommendations", []),
        "intent": result.get("intent"),
    }


@app.get("/api/personas")
def api_personas():
    return load_engine().personas()


@app.post("/api/for-you")
def api_for_you(req: ForYouReq):
    try:
        return load_engine().for_you(req.persona, interested_item_ids=req.interested)
    except (KeyError, ValueError):
        raise HTTPException(status_code=404, detail="Không tìm thấy persona này.")


@app.get("/api/suggested")
def api_suggested():
    from itlr.chatbot.chatbot import SUGGESTED_PROMPTS, EducationalChatbot

    return {"prompts": SUGGESTED_PROMPTS, "welcome": EducationalChatbot.WELCOME_MESSAGE}


# ── Frontend tĩnh ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
