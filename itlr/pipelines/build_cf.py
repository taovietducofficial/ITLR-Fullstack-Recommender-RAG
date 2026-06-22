"""Xây Collaborative Filtering model (item-based) từ data/interactions.csv.

Thuật toán: co-occurrence "người học X cũng học Y" + chuẩn hóa cosine, giữ top-K
láng giềng mỗi item (sparse, tránh ma trận 10000x10000 dày).

    python build_cf.py

Output: artifacts/cf_model.pkl
Chạy SAU build_model.py (cần item_list.pkl để căn id <-> vị trí) và generate_interactions.py.
"""

import pickle
from collections import Counter

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

from itlr import config

TOP_K = 50          # số láng giềng giữ lại mỗi item
N_DEMO_USERS = 40   # số persona đưa ra cho dropdown demo


def top_k_per_row(sim, k):
    """Giữ lại k giá trị lớn nhất mỗi hàng của ma trận CSR."""
    sim = sim.tocsr()
    data, indices, indptr = [], [], [0]
    for r in range(sim.shape[0]):
        start, end = sim.indptr[r], sim.indptr[r + 1]
        row_data = sim.data[start:end]
        row_idx = sim.indices[start:end]
        if len(row_data) > k:
            keep = np.argpartition(row_data, -k)[-k:]
            row_data, row_idx = row_data[keep], row_idx[keep]
        data.extend(row_data)
        indices.extend(row_idx)
        indptr.append(len(data))
    return csr_matrix((data, indices, indptr), shape=sim.shape)


def main():
    item_list = pickle.load(open(config.artifact("item_list.pkl"), "rb")).reset_index(drop=True)
    pos_to_id = item_list["item_id"].astype(int).to_numpy()
    id_to_pos = {int(iid): pos for pos, iid in enumerate(pos_to_id)}
    n_items = len(item_list)

    inter = pd.read_csv(config.INTERACTIONS_CSV)
    inter = inter[inter["item_id"].isin(id_to_pos)]
    user_codes, _ = pd.factorize(inter["user_id"])
    item_pos = inter["item_id"].map(id_to_pos).to_numpy()
    n_users = user_codes.max() + 1

    # Ma trận user-item nhị phân
    R = csr_matrix(
        (np.ones(len(inter)), (user_codes, item_pos)),
        shape=(n_users, n_items),
    )
    R.data[:] = 1.0  # đảm bảo nhị phân

    # Co-occurrence items x items + chuẩn hóa cosine
    cooc = (R.T @ R).tocoo()
    pop = np.asarray(R.sum(axis=0)).ravel()          # số user đã tương tác mỗi item
    mask = (cooc.row != cooc.col) & (cooc.data > 0)
    r, c, v = cooc.row[mask], cooc.col[mask], cooc.data[mask]
    denom = np.sqrt(pop[r] * pop[c])
    denom[denom == 0] = 1.0
    sim = csr_matrix((v / denom, (r, c)), shape=(n_items, n_items))
    sim = top_k_per_row(sim, TOP_K)

    # Lịch sử + nhãn persona cho demo (chọn user có lịch sử đa dạng)
    histories, labels = {}, {}
    cats = item_list["category"].to_numpy()
    grouped = inter.groupby("user_id")["item_id"].apply(list)
    for uid, ids in grouped.items():
        positions = [id_to_pos[int(i)] for i in ids if int(i) in id_to_pos]
        if len(positions) < 5:
            continue
        histories[int(uid)] = positions
        top_cat = Counter(cats[positions]).most_common(1)[0][0]
        labels[int(uid)] = top_cat

    demo_users = sorted(histories.keys(),
                        key=lambda u: len(histories[u]), reverse=True)[:N_DEMO_USERS]

    cf_model = {
        "item_sim": sim,
        "popularity": pop,
        "pos_to_id": pos_to_id,
        "id_to_pos": id_to_pos,
        "histories": {u: histories[u] for u in demo_users},
        "labels": {u: labels[u] for u in demo_users},
    }
    pickle.dump(cf_model, open(config.artifact("cf_model.pkl"), "wb"))

    print(f"CF model: {n_users} users x {n_items} items")
    print(f"  item_sim nnz={sim.nnz} (top-{TOP_K}/item) | demo users={len(demo_users)}")
    print(f"  item phổ biến nhất: {int(pop.max())} user tương tác")


if __name__ == "__main__":
    main()
