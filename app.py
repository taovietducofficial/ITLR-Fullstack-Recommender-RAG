"""Entrypoint tiện lợi — chạy: `python app.py` để mở web API (FastAPI) tại http://localhost:8000.

Tương đương `python -m itlr.api` / `uvicorn itlr.api.server:app`. File mỏng cố ý: chỉ ủy
quyền cho `itlr.api.__main__.main()` (đã tự thiết lập HF offline + dọn nhiễu console).
Giữ ở thư mục gốc cho quen tay; deploy (Heroku/Procfile) dùng trực tiếp uvicorn.
"""

from itlr.api.__main__ import main

if __name__ == "__main__":
    main()
