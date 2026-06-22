"""Sinh dữ liệu tương tác giả (user-item) để mô phỏng Collaborative Filtering.

Mỗi user có 1-2 chuyên mục sở thích; lịch sử "đã xem/học" được lấy mẫu chủ yếu trong
các chuyên mục đó (theo độ phổ biến tiềm ẩn của item) + một ít item ngẫu nhiên để tạo
liên kết chéo (giúp CF khám phá "người học X cũng học Y").

    python generate_interactions.py [số_user]   # mặc định 1500

Output: data/interactions.csv  (user_id, item_id)
"""

import csv
import random
import sys

import pandas as pd

from itlr import config

random.seed(7)

N_USERS = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
MIN_INTERACTIONS, MAX_INTERACTIONS = 8, 40
CROSS_CATEGORY_RATE = 0.15   # tỉ lệ tương tác "lạc" sang chuyên mục khác


def main():
    items = pd.read_csv(config.ITEMS_CSV)
    items = items.dropna().reset_index(drop=True)

    by_category = {}
    for _, row in items.iterrows():
        by_category.setdefault(row["category"], []).append(int(row["item_id"]))
    categories = list(by_category.keys())

    all_ids = items["item_id"].astype(int).tolist()

    # Độ phổ biến tiềm ẩn: một số item "hot" hơn hẳn (phân bố lệch) -> CF có tín hiệu
    popularity = {iid: random.paretovariate(1.3) for iid in all_ids}

    def weighted_sample(pool, k):
        pool = list(pool)
        if k >= len(pool):
            return pool
        weights = [popularity[i] for i in pool]
        chosen, seen = [], set()
        # lấy mẫu không lặp theo trọng số
        while len(chosen) < k and len(seen) < len(pool):
            pick = random.choices(pool, weights=weights, k=1)[0]
            if pick not in seen:
                seen.add(pick)
                chosen.append(pick)
        return chosen

    rows = []
    for uid in range(1, N_USERS + 1):
        n_fav = random.choice([1, 1, 2, 2, 3])
        favs = random.sample(categories, min(n_fav, len(categories)))
        k = random.randint(MIN_INTERACTIONS, MAX_INTERACTIONS)

        fav_pool = [iid for c in favs for iid in by_category[c]]
        n_cross = int(k * CROSS_CATEGORY_RATE)
        n_fav_items = k - n_cross

        picks = set(weighted_sample(fav_pool, n_fav_items))
        picks.update(weighted_sample(all_ids, n_cross))

        for iid in picks:
            rows.append({"user_id": uid, "item_id": iid})

    import os
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(config.INTERACTIONS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["user_id", "item_id"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {len(rows)} interactions cho {N_USERS} users -> {config.INTERACTIONS_CSV}")
    print(f"  Trung bình {len(rows) / N_USERS:.1f} tương tác/user | {len(all_ids)} items | {len(categories)} chuyên mục")


if __name__ == "__main__":
    main()
