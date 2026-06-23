"""Cấu hình đường dẫn TẬP TRUNG — độc lập với thư mục làm việc hiện tại (CWD).

Mọi nơi cần tới artifacts/ hoặc data/ nên dùng các hằng/hàm ở đây thay vì hardcode
đường dẫn tương đối, để chạy được dù gọi từ thư mục nào (`python -m itlr.pipelines...`).
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # thư mục gốc dự án (chứa itlr/)
ARTIFACTS_DIR = ROOT / "artifacts"
DATA_DIR = ROOT / "data"

# Cho phép trỏ catalog sang dataset khác qua biến môi trường ITLR_ITEMS_CSV
# (vd rebuild artifacts trên DỮ LIỆU THẬT mà không đụng file synthetic gốc).
# Mặc định: data/it_learning_items.csv (catalog synthetic).
ITEMS_CSV = Path(os.environ.get("ITLR_ITEMS_CSV", DATA_DIR / "it_learning_items.csv"))
INTERACTIONS_CSV = Path(os.environ.get("ITLR_INTERACTIONS_CSV", DATA_DIR / "interactions.csv"))


def artifact(name: str) -> str:
    """Đường dẫn tuyệt đối tới một file trong artifacts/."""
    return str(ARTIFACTS_DIR / name)


def data_file(name: str) -> str:
    """Đường dẫn tuyệt đối tới một file trong data/."""
    return str(DATA_DIR / name)
