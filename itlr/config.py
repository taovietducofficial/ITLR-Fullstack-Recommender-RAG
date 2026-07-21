"""Cấu hình đường dẫn TẬP TRUNG — độc lập với thư mục làm việc hiện tại (CWD).

Mọi nơi cần tới var/artifacts/ hoặc var/data/ nên dùng các hằng/hàm ở đây thay vì hardcode
đường dẫn tương đối, để chạy được dù gọi từ thư mục nào (`python -m itlr.pipelines...`).
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = ROOT / "var" / "artifacts"
DATA_DIR = ROOT / "var" / "data"

ITEMS_CSV = Path(os.environ.get("ITLR_ITEMS_CSV", DATA_DIR / "it_learning_items.csv"))
INTERACTIONS_CSV = Path(os.environ.get("ITLR_INTERACTIONS_CSV", DATA_DIR / "interactions.csv"))


def artifact(name: str) -> str:
    """Đường dẫn tuyệt đối tới một file trong var/artifacts/."""
    return str(ARTIFACTS_DIR / name)


def data_file(name: str) -> str:
    """Đường dẫn tuyệt đối tới một file trong var/data/."""
    return str(DATA_DIR / name)
