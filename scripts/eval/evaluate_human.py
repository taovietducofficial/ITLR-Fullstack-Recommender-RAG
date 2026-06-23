"""Đánh giá trên NHÃN VÀNG NGƯỜI GÁN + đo đồng thuận auto vs người (Trụ cột B3).

Hai đầu ra chính:
  1) Cohen's Kappa giữa nhãn tự động (auto_grade) và nhãn người (human_label) -> chứng minh
     quy trình sinh nhãn tự động (B2) đáng tin tới mức nào (tức số liệu TRAIN không rác).
  2) (tùy chọn --with-ranking) Metric xếp hạng của các cấu hình trên TEST set người gán
     theo lối pooled evaluation — đây là con số SẠCH (không vòng tròn).

`data/eval/human_judgments.csv` cần cột: query_id, query, item_id, auto_grade, human_label.
human_label trống -> bỏ qua (chưa gán). Nếu file đang là mô phỏng (--simulate-human ở
make_judgments) thì Kappa phản ánh mức nhiễu mô phỏng, KHÔNG dùng cho khóa luận chính thức.

Cách chạy:
    python scripts/eval/evaluate_human.py                 # chỉ Cohen's Kappa (nhanh, không cần model)
    python scripts/eval/evaluate_human.py --with-ranking  # + metric pooled trên test người gán
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from itlr import config  # noqa: E402
from itlr.eval import metrics as M, significance  # noqa: E402


def load_human(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df["human_label"].notna() & (df["human_label"].astype(str).str.strip() != "")]
    df["human_label"] = df["human_label"].astype(int)
    df["auto_bin"] = (df["auto_grade"].astype(int) >= 1).astype(int)
    return df


def kappa_report(df: pd.DataFrame) -> dict:
    kappa = significance.cohen_kappa(df["auto_bin"].tolist(), df["human_label"].tolist())
    agree = float((df["auto_bin"] == df["human_label"]).mean())
    # confusion
    tp = int(((df["auto_bin"] == 1) & (df["human_label"] == 1)).sum())
    tn = int(((df["auto_bin"] == 0) & (df["human_label"] == 0)).sum())
    fp = int(((df["auto_bin"] == 1) & (df["human_label"] == 0)).sum())
    fn = int(((df["auto_bin"] == 0) & (df["human_label"] == 1)).sum())
    return {"kappa": kappa, "raw_agreement": agree, "n": len(df),
            "tp": tp, "tn": tn, "fp": fp, "fn": fn}


def ranking_on_human(df: pd.DataFrame):
    """Pooled evaluation: với mỗi truy vấn, xếp hạng các item ĐÃ GÁN bằng từng cấu hình,
    dùng human_label làm sự thật -> NDCG@5/P@3/MAP. So Full vs lexical (kèm kiểm định)."""
    from itlr.core import pipeline as P
    from itlr.engine import load_engine
    import pickle

    engine = load_engine()
    retrieval_model = pickle.load(open(config.artifact("retrieval_model.pkl"), "rb"))
    si = engine.search_index
    ctx = P.RankContext(
        item_list=engine.items, retrieval_model=retrieval_model,
        embeddings=si["embeddings"], embed_model=engine.model,
        char_vectorizer=si["char_vectorizer"], char_matrix=si["char_matrix"],
        query_prefix=si.get("query_prefix", ""), ann=si.get("ann"), reranker=si.get("reranker"),
    )
    pos_for_id = {int(i): p for p, i in enumerate(engine.items["item_id"].astype(int).to_numpy())}
    id_for_pos = engine.items["item_id"].astype(int).to_numpy()

    configs = P.ablation_configs()
    sel = {"BM25 only": configs["BM25 only"],
           "Embeddings (E5)": configs["Embeddings (E5)"],
           "+ Cross-Encoder": configs["+ Cross-Encoder"]}

    per_cfg_ndcg = defaultdict(list)
    agg = {}
    for name, cfg in sel.items():
        rows = []
        for qid, group in df.groupby("query_id"):
            query = group["query"].iloc[0]
            labeled = {int(r.item_id): int(r.human_label) for r in group.itertuples()}
            ranking = P.rank(ctx, query, cfg, top_n=2000)
            # giữ thứ tự hệ thống, chỉ trên item đã gán
            ranked_ids = [int(id_for_pos[p]) for p in ranking if int(id_for_pos[p]) in labeled]
            # item đã gán nhưng hệ không xếp -> nối đuôi (rel theo nhãn)
            tail = [i for i in labeled if i not in set(ranked_ids)]
            rels = [labeled[i] for i in ranked_ids] + [labeled[i] for i in tail]
            n_rel = sum(labeled.values())
            if n_rel == 0:
                continue
            row = M.per_query_metrics(rels, n_rel, ks=(1, 3, 5))
            rows.append(row)
            per_cfg_ndcg[name].append(row["NDCG@5"])
        agg[name] = M.evaluate_run(rows)
    return agg, per_cfg_ndcg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-ranking", action="store_true")
    args = ap.parse_args()

    path = config.data_file("eval/human_judgments.csv")
    df = load_human(path)
    if df.empty:
        print(f"[!] {path}: chưa có human_label nào được gán. Hãy gán tay cột human_label "
              f"(1=liên quan, 0=không) rồi chạy lại.")
        return

    rep = kappa_report(df)
    print("== Đồng thuận nhãn tự động vs người gán (B3) ==")
    print(f"  N cặp đã gán : {rep['n']}")
    print(f"  Cohen's Kappa: {rep['kappa']:.4f}")
    print(f"  Đồng thuận thô: {rep['raw_agreement']:.4f}")
    print(f"  Confusion (auto×human): TP={rep['tp']} TN={rep['tn']} FP={rep['fp']} FN={rep['fn']}")
    interp = ("rất tốt" if rep["kappa"] >= 0.8 else "tốt" if rep["kappa"] >= 0.6
              else "vừa" if rep["kappa"] >= 0.4 else "yếu")
    print(f"  -> Mức đồng thuận: {interp}")

    lines = ["# Đánh giá trên nhãn người gán (B3)\n",
             f"- N cặp đã gán: **{rep['n']}**",
             f"- **Cohen's Kappa (auto vs người): {rep['kappa']:.4f}** ({interp})",
             f"- Đồng thuận thô: {rep['raw_agreement']:.4f}",
             f"- Confusion auto×human: TP={rep['tp']} TN={rep['tn']} FP={rep['fp']} FN={rep['fn']}\n"]

    if args.with_ranking:
        print("\nNạp model + đánh giá pooled trên test người gán...")
        agg, per_cfg = ranking_on_human(df)
        lines.append("## Metric xếp hạng trên TEST người gán (pooled)\n")
        keys = ["P@3", "NDCG@5", "MAP", "MRR"]
        lines.append("| Cấu hình | " + " | ".join(keys) + " |")
        lines.append("|---|" + "|".join(["---"] * len(keys)) + "|")
        for name, a in agg.items():
            print(f"  [{name}] NDCG@5={a.get('NDCG@5',0):.4f} P@3={a.get('P@3',0):.4f}")
            lines.append(f"| {name} | " + " | ".join(f"{a.get(k,0):.4f}" for k in keys) + " |")
        # kiểm định Full(+CE) vs BM25
        if "+ Cross-Encoder" in per_cfg and "BM25 only" in per_cfg:
            cmp = significance.compare(per_cfg["+ Cross-Encoder"], per_cfg["BM25 only"])
            lines.append(f"\n**+ Cross-Encoder vs BM25 (NDCG@5):** Δ={cmp['mean_diff']:+.4f}, "
                         f"p(t-test)={cmp['p_ttest']:.4g}, "
                         f"{'có ý nghĩa (p<0.05)' if cmp['significant'] else 'chưa có ý nghĩa'}.")

    out = config.ROOT / "reports" / "human_eval.md"
    os.makedirs(out.parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n-> reports/human_eval.md")


if __name__ == "__main__":
    main()
