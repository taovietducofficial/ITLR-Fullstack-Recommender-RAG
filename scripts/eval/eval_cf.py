"""Đánh giá Collaborative Filtering đúng chuẩn (Trụ cột B6).

Chạy hai giao thức trên cf_model + interactions:
  - Leave-one-out (che 1 tương tác/user) — so CF với baseline popularity.
  - Temporal split (quá khứ -> tương lai).

Kết quả ghi ra reports/cf_eval.md.

Cách chạy:
    python scripts/eval/eval_cf.py
    python scripts/eval/eval_cf.py --max-users 500
"""

from __future__ import annotations

import argparse
import os
import pickle
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd  # noqa: E402

from itlr import config  # noqa: E402
from itlr.eval import cf_eval  # noqa: E402


def build_histories(item_list, max_users=None):
    """Dựng {user_id: [positions]} từ interactions.csv (không phụ thuộc demo histories trong cf_model)."""
    id_to_pos = {int(i): p for p, i in enumerate(item_list["item_id"].astype(int).to_numpy())}
    inter = pd.read_csv(config.INTERACTIONS_CSV)
    inter = inter[inter["item_id"].isin(id_to_pos)]
    hist = defaultdict(list)
    for r in inter.itertuples():
        hist[int(r.user_id)].append(id_to_pos[int(r.item_id)])
    # KHÔNG cắt theo max_users ở đây: train item_sim cần TOÀN bộ user cho đủ mật độ;
    # việc giới hạn số user ĐÁNH GIÁ do từng hàm eval tự xử lý qua tham số max_users.
    return {u: v for u, v in hist.items() if len(v) >= 4}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-users", type=int, default=800)
    args = ap.parse_args()

    item_list = pickle.load(open(config.artifact("item_list.pkl"), "rb")).reset_index(drop=True)
    cf_model = pickle.load(open(config.artifact("cf_model.pkl"), "rb"))
    histories = build_histories(item_list)
    print(f"Train CF từ {len(histories)} user (>= 4 tương tác); đánh giá tối đa {args.max_users} user")

    print("Leave-one-out (CF)...")
    loo = cf_eval.leave_one_out(cf_model, item_list, histories, max_users=args.max_users)
    print("Leave-one-out (popularity baseline)...")
    pop = cf_eval.popularity_baseline_loo(cf_model, item_list, histories, max_users=args.max_users)
    print("Temporal split (CF, có rò rỉ — tham khảo)...")
    temp = cf_eval.temporal_split(cf_model, item_list, histories, max_users=args.max_users)
    print("Temporal split (CF, KHÔNG rò rỉ — train lại từ TRAIN)...")
    temp_clean = cf_eval.temporal_split_clean(item_list, histories, max_users=args.max_users)

    lines = ["# Đánh giá Collaborative Filtering (B6)\n",
             f"*Số user đánh giá: {int(loo.get('n_users', 0))} (leave-one-out), "
             f"{int(temp.get('n_users', 0))} (temporal split).*\n",
             "## Leave-one-out — CF vs Popularity baseline\n",
             "| Metric | CF item-based | Popularity baseline |",
             "|---|---|---|"]
    for k in ["HitRate@1", "HitRate@5", "HitRate@10", "MRR"]:
        lines.append(f"| {k} | {loo.get(k,0):.4f} | {pop.get(k,0):.4f} |")
    lines.append("")
    lines.append("## Temporal split (train quá khứ → test tương lai)\n")
    lines.append("| Metric | KHÔNG rò rỉ (train lại) | Có rò rỉ (tham khảo) |")
    lines.append("|---|---|---|")
    for k in ["Recall@1", "Recall@5", "Recall@10", "NDCG@10", "MAP"]:
        if k in temp_clean or k in temp:
            lines.append(f"| {k} | {temp_clean.get(k, float('nan')):.4f} | {temp.get(k, float('nan')):.4f} |")
    lines.append("\n*Cột **KHÔNG rò rỉ** train lại item_sim CHỈ trên phần quá khứ của mọi user "
                 "(held-out không tham gia đồng-xuất-hiện) — đây là con số đáng tin để báo cáo. "
                 "Cột có rò rỉ dùng cf_model train trên TOÀN bộ tương tác nên lạc quan quá mức.*")
    lines.append("\n*Lưu ý: interactions.csv không có timestamp -> temporal split dùng thứ tự dòng "
                 "làm proxy thời gian (đã nêu giả định trong itlr/eval/cf_eval.py). Leave-one-out ở "
                 "trên dùng cf_model gốc nên CŨNG có rò rỉ — diễn giải thận trọng, ưu tiên cột không rò rỉ.*")

    out = config.ROOT / "reports" / "cf_eval.md"
    os.makedirs(out.parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("\n== Leave-one-out ==")
    for k in ["HitRate@1", "HitRate@5", "HitRate@10", "MRR"]:
        print(f"  {k}: CF={loo.get(k,0):.4f}  Pop={pop.get(k,0):.4f}")
    print("== Temporal split (KHÔNG rò rỉ | có rò rỉ) ==")
    for k in ["Recall@5", "Recall@10", "NDCG@10", "MAP"]:
        if k in temp_clean:
            print(f"  {k}: {temp_clean[k]:.4f} | {temp.get(k, float('nan')):.4f}")
    print("\n-> reports/cf_eval.md")


if __name__ == "__main__":
    main()
