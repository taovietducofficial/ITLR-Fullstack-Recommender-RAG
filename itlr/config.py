"""Cấu hình đường dẫn TẬP TRUNG — độc lập với thư mục làm việc hiện tại (CWD).

Mọi nơi cần tới artifacts/ hoặc data/ nên dùng các hằng/hàm ở đây thay vì hardcode
đường dẫn tương đối, để chạy được dù gọi từ thư mục nào (`python -m itlr.pipelines...`).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # thư mục gốc dự án (chứa itlr/)
ARTIFACTS_DIR = ROOT / "artifacts"
DATA_DIR = ROOT / "data"
ITEMS_CSV = DATA_DIR / "it_learning_items.csv"
INTERACTIONS_CSV = DATA_DIR / "interactions.csv"


def artifact(name: str) -> str:
    """Đường dẫn tuyệt đối tới một file trong artifacts/."""
    return str(ARTIFACTS_DIR / name)


def data_file(name: str) -> str:
    """Đường dẫn tuyệt đối tới một file trong data/."""
    return str(DATA_DIR / name)
