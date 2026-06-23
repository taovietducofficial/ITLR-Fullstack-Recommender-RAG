"""Sinh dữ liệu tương tác (user-item) có CẤU TRÚC LATENT để mô phỏng Collaborative Filtering.

NÂNG CẤP (2026-06-23): phiên bản cũ lấy mẫu item theo độ phổ biến thuần -> co-occurrence
KHÔNG mang tín hiệu cộng tác thật, nên CF đánh giá leave-one-out/temporal KHÔNG rò rỉ gần
như bằng 0 (xem reports/cf_eval.md). Phiên bản này dùng **mô hình nhân tử ẩn (latent-factor)**:

  - Mỗi item i có vector ẩn q_i dựng từ chuyên mục + chủ đề (item cùng category/topic -> q gần nhau).
  - Mỗi user u có vector sở thích ẩn p_u lấy quanh một "archetype" (cộng đồng) -> tạo các nhóm
    user có gu tương tự.
  - Xác suất user u tương tác item i ∝ exp(p_u · q_i): user gu giống nhau chọn item q gần nhau
    -> "người học X cũng học Y" XUẤT HIỆN THẬT trong đồng-xuất-hiện -> item-based CF (co-occurrence)
    khôi phục được hàng xóm q_i -> đánh giá KHÔNG rò rỉ có tín hiệu (recall > 0 đáng kể).

Vẫn giữ skew độ phổ biến (một số item hot hơn) cho thực tế. Output/ CLI giữ nguyên.

    python generate_interactions.py [số_user]   # mặc định 1800

Output: data/interactions.csv  (user_id, item_id)
"""

import csv
import os
import sys

import numpy as np
import pandas as pd

from itlr import config
from itlr.core.recommender import parse_topics

SEED = 7
N_USERS = int(sys.argv[1]) if len(sys.argv) > 1 else 1800
MIN_INTERACTIONS, MAX_INTERACTIONS = 8, 40

LATENT_DIM = 24          # số nhân tử ẩn
N_ARCHETYPES = 40        # số "cộng đồng" gu (nhiều hơn số chuyên mục -> tạo nhóm con)
USER_NOISE = 0.35        # độ lệch p_u quanh archetype (nhỏ -> cộng đồng chặt)
SHARPNESS = 6.0          # độ "nhọn" của lựa chọn (cao -> chọn tập item nhất quán hơn)


def build_item_factors(items: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    """q_i = chuẩn hóa( vector_chuyên_mục + Σ vector_chủ_đề + nhiễu nhỏ ). Item cùng
    category/topic -> q gần nhau (đó là nguồn tín hiệu cộng tác)."""
    cats = sorted(items["category"].unique())
    cat_vec = {c: rng.normal(size=LATENT_DIM) for c in cats}
    topic_vec: dict = {}
    item_topics = [parse_topics(t) for t in items["topics"]]
    for ts in item_topics:
        for t in ts:
            if t not in topic_vec:
                topic_vec[t] = rng.normal(size=LATENT_DIM) * 0.8

    q = np.zeros((len(items), LATENT_DIM))
    for i, (cat, ts) in enumerate(zip(items["category"], item_topics)):
        v = cat_vec[cat].copy()
        for t in ts:
            v += topic_vec[t]
        v += rng.normal(size=LATENT_DIM) * 0.15
        n = np.linalg.norm(v)
        q[i] = v / n if n > 0 else v
    return q


def main():
    rng = np.random.default_rng(SEED)
    items = pd.read_csv(config.ITEMS_CSV).dropna(subset=["category", "topics"]).reset_index(drop=True)
    n_items = len(items)
    item_ids = items["item_id"].astype(int).to_numpy()

    q = build_item_factors(items, rng)                       # (n_items, d)
    archetypes = rng.normal(size=(N_ARCHETYPES, LATENT_DIM))  # tâm các cộng đồng gu
    # skew độ phổ biến nội tại (Pareto) -> một số item hot hơn dù cùng độ khớp
    pop_bias = np.log(rng.pareto(2.0, size=n_items) + 1.0)

    rows = []
    for uid in range(1, N_USERS + 1):
        arch = archetypes[rng.integers(0, N_ARCHETYPES)]
        p_u = arch + rng.normal(size=LATENT_DIM) * USER_NOISE
        scores = q @ p_u + 0.3 * pop_bias                    # độ hấp dẫn item với user
        # xác suất chọn ∝ exp(sharpness * z(scores)); softmax ổn định số học
        z = (scores - scores.mean()) / (scores.std() + 1e-9)
        logits = SHARPNESS * z
        logits -= logits.max()
        probs = np.exp(logits)
        probs /= probs.sum()

        k = int(rng.integers(MIN_INTERACTIONS, MAX_INTERACTIONS + 1))
        k = min(k, n_items)
        picks = rng.choice(n_items, size=k, replace=False, p=probs)
        for pos in picks:
            rows.append({"user_id": uid, "item_id": int(item_ids[pos])})

    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(config.INTERACTIONS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["user_id", "item_id"])
        w.writeheader()
        w.writerows(rows)

    n_distinct = len({r["item_id"] for r in rows})
    print(f"Generated {len(rows)} interactions cho {N_USERS} users -> {config.INTERACTIONS_CSV}")
    print(f"  latent-factor (d={LATENT_DIM}, {N_ARCHETYPES} archetypes) | "
          f"TB {len(rows)/N_USERS:.1f} tương tác/user | {n_distinct}/{n_items} item được chạm")


if __name__ == "__main__":
    main()
