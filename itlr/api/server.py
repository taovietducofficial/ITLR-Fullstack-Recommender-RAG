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

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import itlr.utils.runtime_patches  # noqa: F401,E402  (dọn nhiễu console trước khi nạp model)

import json  # noqa: E402
import time  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import List, Optional, Union  # noqa: E402

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse  # noqa: E402
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


def _prewarm_ollama():
    """Nạp sẵn model Ollama vào RAM (chạy NỀN) -> câu hỏi chatbot ĐẦU TIÊN không bị
    cold-start ~90s (nguyên nhân hay gây timeout/'báo lỗi' ở câu đầu).

    Warm khi Ollama LÀ backend đang dùng: bỏ qua nếu đã có API key (OpenAI) hoặc
    USE_OLLAMA bị tắt tường minh. Không cần BẮT BUỘC đặt USE_OLLAMA nữa (khớp _llm_available
    vốn tự phát hiện Ollama)."""
    if os.environ.get("OPENAI_API_KEY"):
        return
    if str(os.environ.get("USE_OLLAMA", "")).lower() in ("0", "false", "no"):
        return
    import threading
    import urllib.request

    def _warm():
        url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        model = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
        payload = json.dumps({"model": model, "messages": [{"role": "user", "content": "ping"}],
                              "stream": False, "keep_alive": "2h",
                              "options": {"num_predict": 1}}).encode()
        try:
            req = urllib.request.Request(f"{url}/api/chat", data=payload,
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=300).read()
            _log(f"[OK] Đã pre-warm Ollama ({model}) — chatbot sẵn sàng trả lời nhanh.")
        except Exception as e:  # noqa: BLE001
            _log(f"[!] Pre-warm Ollama lỗi (bỏ qua): {e}")

    threading.Thread(target=_warm, daemon=True).start()


@asynccontextmanager
async def lifespan(_app):
    """Nạp artifacts ngay khi khởi động để lỗi (thiếu artifacts) lộ sớm, request đầu nhanh."""
    try:
        load_engine()
        _log("[OK] Engine sẵn sàng — API tại http://localhost:8000")
        _prewarm_ollama()
    except FileNotFoundError:
        _log(
            "[!] Chưa có model artifacts. Hãy build trước:\n"
            "    python scripts/build_all.py\n"
            "(hoặc lần lượt build_model -> build_embeddings -> generate_interactions -> build_cf)"
        )
    yield


app = FastAPI(title="IT Learning Recommender API", version="1.0.0", lifespan=lifespan)


_METRICS = {"requests_total": 0, "errors_total": 0, "by_route": {}}


@app.middleware("http")
async def _track_metrics(request: Request, call_next):
    t0 = time.perf_counter()
    _METRICS["requests_total"] += 1
    try:
        resp = await call_next(request)
    except Exception:
        _METRICS["errors_total"] += 1
        raise
    dt_ms = (time.perf_counter() - t0) * 1000.0
    route = request.url.path
    r = _METRICS["by_route"].setdefault(route, {"count": 0, "ms_sum": 0.0, "ms_max": 0.0})
    r["count"] += 1
    r["ms_sum"] += dt_ms
    r["ms_max"] = max(r["ms_max"], dt_ms)
    if resp.status_code >= 500:
        _METRICS["errors_total"] += 1
    return resp


@app.get("/health")
def health():
    """Liveness/readiness: engine đã nạp được artifacts chưa."""
    try:
        load_engine()
        return {"status": "ok", "engine": "ready"}
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Artifacts chưa build (chạy scripts/build_all.py)")


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    """Phơi metric quan sát hệ thống dạng text (đếm request, độ trễ TB/đỉnh mỗi route)."""
    lines = [
        f"requests_total {_METRICS['requests_total']}",
        f"errors_total {_METRICS['errors_total']}",
    ]
    for route, r in sorted(_METRICS["by_route"].items()):
        avg = r["ms_sum"] / r["count"] if r["count"] else 0.0
        safe = route.replace('"', "")
        lines.append(f'route_requests_total{{path="{safe}"}} {r["count"]}')
        lines.append(f'route_latency_ms_avg{{path="{safe}"}} {avg:.2f}')
        lines.append(f'route_latency_ms_max{{path="{safe}"}} {r["ms_max"]:.2f}')
    return "\n".join(lines) + "\n"


class SearchReq(BaseModel):
    query: str
    type: Optional[str] = None
    min_pct: int = 90


class ChatMsg(BaseModel):
    role: str
    content: str


class ChatReq(BaseModel):
    message: str
    history: List[ChatMsg] = []


class ForYouReq(BaseModel):
    persona: Union[int, str]
    interested: List[int] = []


@app.post("/api/search")
def api_search(req: SearchReq):
    eng = load_engine()
    item_type = req.type if req.type in ("Khóa học", "Tài liệu") else None
    return eng.search(req.query, item_type=item_type, min_pct=req.min_pct)


_CHAT_ERROR_MSG = (
    "Xin lỗi, mình gặp trục trặc khi xử lý câu hỏi này. Bạn thử gửi lại hoặc diễn đạt khác giúp mình nhé."
)


@app.post("/api/chat")
def api_chat(req: ChatReq):
    eng = load_engine()
    history = [{"role": m.role, "content": m.content} for m in req.history]
    try:
        result = eng.chat(req.message, history=history)
    except Exception as e:  # noqa: BLE001
        _log(f"[!] /api/chat lỗi: {e}")
        return {"response": _CHAT_ERROR_MSG, "recommendations": [], "intent": "error"}
    return {
        "response": result["response"],
        "recommendations": result.get("recommendations", []),
        "intent": result.get("intent"),
    }


@app.post("/api/chat/stream")
def api_chat_stream(req: ChatReq):
    """Trả lời chatbot dạng STREAMING (SSE). Mỗi frame là 1 dòng `data: {json}` rồi dòng trống.

    Vì sao stream: model local (Ollama) chậm ~30-135s/câu -> nếu chờ cả câu, người dùng thấy
    "treo" và proxy/Heroku (timeout 30s) trả 503 -> frontend báo lỗi. Stream đẩy chữ ngay khi
    sinh (byte chảy sớm) nên không treo & không chạm hard-timeout."""
    eng = load_engine()
    history = [{"role": m.role, "content": m.content} for m in req.history]

    def _frame(obj):
        return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"

    def gen():
        try:
            for ev, data in eng.chat_stream(req.message, history=history):
                if ev == "text":
                    yield _frame({"type": "text", "text": data})
                elif ev == "meta":
                    yield _frame({"type": "meta", "intent": data.get("intent"),
                                  "recommendations": data.get("recommendations", [])})
        except Exception as e:  # noqa: BLE001
            _log(f"[!] /api/chat/stream lỗi: {e}")
            yield _frame({"type": "text", "text": "\n\n_" + _CHAT_ERROR_MSG + "_"})
        yield _frame({"type": "done"})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/admin/reload")
def admin_reload():
    """Nạp lại artifacts NGAY mà KHÔNG cần tắt/mở lại tiến trình.

    Sau khi pipeline cập nhật dữ liệu (scripts/update_data.py) ghi artifacts mới, gọi endpoint này
    để chatbot/tìm kiếm dùng dữ liệu mới: xóa cache load_engine() rồi nạp lại từ artifacts/*.pkl.
    Dùng bởi `scripts/update_data.py --restart`.
    """
    load_engine.cache_clear()
    eng = load_engine()
    n = len(eng.items) if hasattr(eng, "items") else None
    return {"ok": True, "reloaded": True, "items": n}


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


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
