"""Chuẩn bị PHIẾU GÁN NHÃN dễ đọc cho con người + trộn nhãn đã gán trở lại.

Vấn đề: `human_judgments.csv` chỉ có `item_id` -> người gán không phán xét được. Script này:

  --prepare : join item_id -> tiêu đề/chuyên mục/cấp độ/chủ đề/mô tả của catalog, xuất
              `data/eval/labeling_sheet.csv` với cột `human_label` TRỐNG để người điền.
              CỐ Ý KHÔNG đưa cột auto_grade vào phiếu -> tránh thiên lệch (mù với nhãn máy).

  --merge   : đọc phiếu đã điền (`labeling_sheet.csv`), ghi `human_label` trở lại
              `human_judgments.csv` (khớp theo query_id+item_id, giữ auto_grade cho Kappa).

Cách chạy:
    python scripts/eval/prepare_labeling_sheet.py --prepare
    # ... mở data/eval/labeling_sheet.csv (Excel/Google Sheets), điền cột human_label = 1/0 ...
    python scripts/eval/prepare_labeling_sheet.py --merge
    python scripts/eval/evaluate_human.py --with-ranking
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd  # noqa: E402

from itlr import config  # noqa: E402

SHEET = "eval/labeling_sheet.csv"
HUMAN = "eval/human_judgments.csv"


def prepare():
    human = pd.read_csv(config.data_file(HUMAN))
    items = pd.read_csv(config.ITEMS_CSV)
    cols = [c for c in ["item_id", "title", "category", "level", "topics", "description"] if c in items.columns]
    info = items[cols].copy()
    info["description"] = info["description"].astype(str).str.slice(0, 240)

    sheet = human[["query_id", "query", "item_id"]].merge(info, on="item_id", how="left")
    sheet["human_label"] = ""
    sheet = sheet.sort_values(["query_id", "item_id"]).reset_index(drop=True)
    out = config.data_file(SHEET)
    sheet.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"-> {out}")
    print(f"   {len(sheet)} cặp (truy vấn, mục) cần gán. Mở bằng Excel/Sheets, điền cột "
          f"'human_label' = 1 (liên quan) / 0 (không), LƯU dạng CSV, rồi chạy --merge.")
    print("   Mẹo: gán theo từng query_id; KHÔNG đoán theo thứ tự — đọc tiêu đề+mô tả rồi quyết định.")


def merge():
    sheet = pd.read_csv(config.data_file(SHEET))
    human = pd.read_csv(config.data_file(HUMAN))
    sheet = sheet[sheet["human_label"].notna() & (sheet["human_label"].astype(str).str.strip() != "")]
    if sheet.empty:
        print("[!] Phiếu chưa có nhãn nào (cột human_label trống). Hãy gán trước khi --merge.")
        return
    label_map = {(str(r.query_id), int(r.item_id)): int(r.human_label) for r in sheet.itertuples()}
    filled = 0
    new_labels = []
    for r in human.itertuples():
        key = (str(r.query_id), int(r.item_id))
        if key in label_map:
            new_labels.append(label_map[key]); filled += 1
        else:
            new_labels.append(r.human_label if pd.notna(r.human_label) else "")
    human["human_label"] = new_labels
    human.to_csv(config.data_file(HUMAN), index=False, encoding="utf-8")
    print(f"-> cập nhật {config.data_file(HUMAN)}: {filled}/{len(human)} dòng có nhãn người.")
    print("   Tiếp theo: python scripts/eval/evaluate_human.py --with-ranking")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args()
    if args.merge:
        merge()
    else:
        prepare()


if __name__ == "__main__":
    main()
