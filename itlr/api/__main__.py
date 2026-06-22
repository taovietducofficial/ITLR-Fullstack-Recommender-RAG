"""Cho phép `python -m itlr.api` — chạy server uvicorn tiện lợi (đọc HOST/PORT từ env)."""

import os


def main():
    import uvicorn

    uvicorn.run(
        "itlr.api.server:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        reload=bool(os.environ.get("RELOAD")),
    )


if __name__ == "__main__":
    main()
