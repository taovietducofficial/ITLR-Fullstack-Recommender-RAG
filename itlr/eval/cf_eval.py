"""Đánh giá Collaborative Filtering đúng chuẩn (Trụ cột B6).

Hai giao thức:
  - leave_one_out : che 1 tương tác của mỗi user, đo khả năng model gợi ý lại đúng item.
  - temporal_split: train trên quá khứ, test trên tương lai (tránh "rò rỉ tương lai").

Tái dùng `recommend_for_user` và cấu trúc cf_model (item_sim, id_to_pos...). Vì interactions
hiện không có timestamp, temporal_split mô phỏng bằng thứ tự dòng (proxy thời gian) — đã ghi
rõ giả định để báo cáo trung thực.
"""

from __future__ import annotations

import random
from typing import Dict, List, Sequence

import numpy as np
from scipy.sparse import csr_matrix

from itlr.core.recommender import recommend_for_user
from itlr.eval import metrics as M


# ─────────────────────────────────────────────────────────────────────────────
# Tái dựng độ tương đồng item-based KHÔNG RÒ RỈ (chỉ từ tương tác TRAIN)
# ─────────────────────────────────────────────────────────────────────────────
def build_item_sim(train_pairs: Sequence[tuple], n_items: int, top_k: int = 50):
    """Dựng item_sim cosine co-occurrence + popularity CHỈ từ các cặp (user_pos, item_pos) train.

    Trùng logic build_cf.py để CF được train lại đúng trên tập train -> tránh rò rỉ tương lai
    (held-out interaction KHÔNG tham gia đồng-xuất-hiện). Trả (sim_csr_topk, popularity)."""
    if not train_pairs:
        return csr_matrix((n_items, n_items)), np.zeros(n_items)
    users = np.array([u for u, _ in train_pairs])
    items = np.array([i for _, i in train_pairs])
    # nén user id về 0..n_users-1
    uniq = {u: k for k, u in enumerate(sorted(set(users.tolist())))}
    rows = np.array([uniq[u] for u in users])
    n_users = len(uniq)
    R = csr_matrix((np.ones(len(rows)), (rows, items)), shape=(n_users, n_items))
    R.data[:] = 1.0
    cooc = (R.T @ R).tocoo()
    pop = np.asarray(R.sum(axis=0)).ravel()
    mask = (cooc.row != cooc.col) & (cooc.data > 0)
    r, c, v = cooc.row[mask], cooc.col[mask], cooc.data[mask]
    denom = np.sqrt(pop[r] * pop[c])
    denom[denom == 0] = 1.0
    sim = csr_matrix((v / denom, (r, c)), shape=(n_items, n_items))
    # giữ top-k mỗi hàng
    sim = sim.tocsr()
    data, indices, indptr = [], [], [0]
    for rr in range(sim.shape[0]):
        s, e = sim.indptr[rr], sim.indptr[rr + 1]
        rd, ri = sim.data[s:e], sim.indices[s:e]
        if len(rd) > top_k:
            keep = np.argpartition(rd, -top_k)[-top_k:]
            rd, ri = rd[keep], ri[keep]
        data.extend(rd); indices.extend(ri); indptr.append(len(data))
    return csr_matrix((data, indices, indptr), shape=sim.shape), pop


def temporal_split_clean(
    item_list,
    histories: Dict[int, Sequence[int]],
    test_ratio: float = 0.3,
    top_n: int = 10,
    ks: Sequence[int] = (1, 5, 10),
    top_k_neighbors: int = 50,
    max_users: int | None = None,
) -> Dict[str, float]:
    """Temporal split KHÔNG RÒ RỈ: gom phần TRAIN của MỌI user -> train lại item_sim, rồi đo
    trên phần test (tương lai) của từng user. Đây là con số CF đáng tin nhất để báo cáo."""
    # Train item_sim từ phần quá khứ của MỌI user (mật độ đủ lớn); chỉ ĐÁNH GIÁ trên subset.
    uids = list(histories.keys())
    n_items = len(item_list)

    train_pairs = []
    test_map = {}
    for ucode, uid in enumerate(uids):
        hist = list(histories[uid])
        if len(hist) < 4:
            continue
        cut = max(1, int(len(hist) * (1 - test_ratio)))
        train, test = hist[:cut], set(hist[cut:])
        for p in train:
            train_pairs.append((ucode, p))         # quá khứ -> luôn vào tập train sim
        if test and (max_users is None or len(test_map) < max_users):
            test_map[ucode] = (train, test)        # chỉ một subset dùng để đo

    sim, pop = build_item_sim(train_pairs, n_items, top_k=top_k_neighbors)
    cf_model = {"item_sim": sim, "popularity": pop,
                "id_to_pos": {int(i): p for p, i in enumerate(item_list["item_id"].astype(int).to_numpy())}}

    recall_at: Dict[int, List[float]] = {k: [] for k in ks}
    ndcg_list, map_list = [], []
    for ucode, (train, test) in test_map.items():
        ranked = recommend_for_user(train, cf_model, item_list, top_n=max(max(ks), top_n))
        id_to_pos = cf_model["id_to_pos"]
        ranked_pos = [id_to_pos[int(r["item_id"])] for r in ranked if int(r["item_id"]) in id_to_pos]
        rels = [1.0 if p in test else 0.0 for p in ranked_pos]
        n_rel = len(test)
        for k in ks:
            recall_at[k].append(M.recall_at_k(rels, k, n_rel))
        ndcg_list.append(M.ndcg_at_k(rels, max(ks), ideal_rels=[1.0] * n_rel))
        map_list.append(M.average_precision(rels, n_rel))

    out = {f"Recall@{k}": float(np.mean(v)) if v else 0.0 for k, v in recall_at.items()}
    out["NDCG@%d" % max(ks)] = float(np.mean(ndcg_list)) if ndcg_list else 0.0
    out["MAP"] = float(np.mean(map_list)) if map_list else 0.0
    out["n_users"] = float(len(map_list))
    return out


def _recommend_positions(history_positions, cf_model, item_list, top_n, exclude=None):
    """Bọc recommend_for_user nhưng trả về VỊ TRÍ item (để so với held-out position)."""
    recs = recommend_for_user(history_positions, cf_model, item_list, top_n=top_n, exclude=exclude)
    id_to_pos = cf_model["id_to_pos"]
    return [id_to_pos[int(r["item_id"])] for r in recs if int(r["item_id"]) in id_to_pos]


def leave_one_out(
    cf_model: dict,
    item_list,
    histories: Dict[int, Sequence[int]],
    top_n: int = 10,
    ks: Sequence[int] = (1, 5, 10),
    max_users: int | None = None,
    seed: int = 7,
) -> Dict[str, float]:
    """Leave-one-out: với mỗi user, che 1 item (ngẫu nhiên cố định seed), train trên phần
    còn lại, đo HitRate@K / MRR / NDCG@K trên item bị che.
    """
    rng = random.Random(seed)
    uids = list(histories.keys())
    if max_users:
        uids = uids[:max_users]

    hit_at: Dict[int, List[float]] = {k: [] for k in ks}
    mrr_list: List[float] = []
    ndcg_list: List[float] = []

    for uid in uids:
        hist = list(histories[uid])
        if len(hist) < 2:
            continue
        held = rng.choice(hist)
        train = [p for p in hist if p != held]
        ranked_pos = _recommend_positions(train, cf_model, item_list, top_n=max(ks))
        rels = [1.0 if p == held else 0.0 for p in ranked_pos]
        for k in ks:
            hit_at[k].append(M.hit_rate_at_k(rels, k))
        mrr_list.append(M.reciprocal_rank(rels))
        ndcg_list.append(M.ndcg_at_k(rels, max(ks), ideal_rels=[1.0]))

    out = {f"HitRate@{k}": float(np.mean(v)) if v else 0.0 for k, v in hit_at.items()}
    out["MRR"] = float(np.mean(mrr_list)) if mrr_list else 0.0
    out["NDCG@%d" % max(ks)] = float(np.mean(ndcg_list)) if ndcg_list else 0.0
    out["n_users"] = float(len(mrr_list))
    return out


def temporal_split(
    cf_model: dict,
    item_list,
    histories: Dict[int, Sequence[int]],
    test_ratio: float = 0.3,
    top_n: int = 10,
    ks: Sequence[int] = (1, 5, 10),
    max_users: int | None = None,
) -> Dict[str, float]:
    """Temporal split: giữ `1 − test_ratio` đầu lịch sử (quá khứ) để train, phần cuối
    (tương lai) làm test. Thứ tự vị trí trong history đóng vai proxy thời gian.

    Đo Recall@K / NDCG@K / MAP trên tập item tương lai (có thể nhiều item -> graded binary).
    """
    uids = list(histories.keys())
    if max_users:
        uids = uids[:max_users]

    recall_at: Dict[int, List[float]] = {k: [] for k in ks}
    ndcg_list: List[float] = []
    map_list: List[float] = []

    for uid in uids:
        hist = list(histories[uid])
        if len(hist) < 4:
            continue
        cut = max(1, int(len(hist) * (1 - test_ratio)))
        train, test = hist[:cut], set(hist[cut:])
        if not test:
            continue
        ranked_pos = _recommend_positions(train, cf_model, item_list, top_n=max(max(ks), top_n))
        rels = [1.0 if p in test else 0.0 for p in ranked_pos]
        n_rel = len(test)
        for k in ks:
            recall_at[k].append(M.recall_at_k(rels, k, n_rel))
        ndcg_list.append(M.ndcg_at_k(rels, max(ks), ideal_rels=[1.0] * n_rel))
        map_list.append(M.average_precision(rels, n_rel))

    out = {f"Recall@{k}": float(np.mean(v)) if v else 0.0 for k, v in recall_at.items()}
    out["NDCG@%d" % max(ks)] = float(np.mean(ndcg_list)) if ndcg_list else 0.0
    out["MAP"] = float(np.mean(map_list)) if map_list else 0.0
    out["n_users"] = float(len(map_list))
    return out


def popularity_baseline_loo(
    cf_model: dict,
    item_list,
    histories: Dict[int, Sequence[int]],
    ks: Sequence[int] = (1, 5, 10),
    max_users: int | None = None,
    seed: int = 7,
) -> Dict[str, float]:
    """Baseline "gợi ý theo độ phổ biến" trong cùng giao thức leave-one-out — để đối chứng
    CF có thực sự hơn baseline ngây thơ hay không."""
    rng = random.Random(seed)
    pop = np.asarray(cf_model["popularity"], dtype="float64")
    pop_order = np.argsort(pop)[::-1]
    uids = list(histories.keys())
    if max_users:
        uids = uids[:max_users]

    hit_at: Dict[int, List[float]] = {k: [] for k in ks}
    mrr_list: List[float] = []
    for uid in uids:
        hist = list(histories[uid])
        if len(hist) < 2:
            continue
        held = rng.choice(hist)
        train = set(p for p in hist if p != held)
        ranked = [p for p in pop_order if p not in train][:max(ks)]
        rels = [1.0 if p == held else 0.0 for p in ranked]
        for k in ks:
            hit_at[k].append(M.hit_rate_at_k(rels, k))
        mrr_list.append(M.reciprocal_rank(rels))

    out = {f"HitRate@{k}": float(np.mean(v)) if v else 0.0 for k, v in hit_at.items()}
    out["MRR"] = float(np.mean(mrr_list)) if mrr_list else 0.0
    return out
