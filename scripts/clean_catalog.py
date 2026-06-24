"""Làm sạch mô tả/tiêu đề/link trong catalog THẬT (offline, không cần API).

Sửa các "rác" do dịch máy:
  - Gộp TỪ LẶP liên tiếp trong title/description ("thuật thuật thuật" -> "thuật").
  - Link không phải http(s) ("Đang cập nhật", rỗng) -> "" để không render link hỏng.

Dùng chung bộ làm sạch với recommender (itlr.core.recommender.clean_display_text/clean_link)
nên hiển thị chatbot và dữ liệu nguồn nhất quán.

Chạy:
    python scripts/clean_catalog.py                     # làm sạch file mặc định (real_vi)
    python scripts/clean_catalog.py path/to/file.csv    # chỉ định file khác
Tự lưu backup `<tên>.beforeclean.csv` trước khi ghi đè (không đụng backup cũ).
"""
import csv
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from itlr.core.recommender import clean_display_text, clean_link  # noqa: E402

DEFAULT = Path(__file__).resolve().parent.parent / "data" / "it_learning_items_real_vi.csv"
TEXT_COLS = ("title", "description")


def main(path):
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"Không thấy file: {path}")
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)

    n_text, n_link = 0, 0
    for row in rows:
        for col in TEXT_COLS:
            if col in row and row[col] is not None:
                cleaned = clean_display_text(row[col])
                if cleaned != row[col]:
                    n_text += 1
                    row[col] = cleaned
        if "link" in row:
            cleaned = clean_link(row["link"])
            if cleaned != str(row["link"]).strip():
                n_link += 1
            row["link"] = cleaned

    backup = path.with_suffix(".beforeclean.csv")
    if not backup.exists():
        shutil.copy2(path, backup)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[clean] {path.name}: {len(rows)} dòng | sửa text={n_text} | làm sạch link={n_link}")
    print(f"[clean] backup: {backup.name}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
