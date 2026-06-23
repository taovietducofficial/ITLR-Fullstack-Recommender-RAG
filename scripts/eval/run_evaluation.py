"""Chạy thực nghiệm đánh giá ĐẦU-CUỐI (Trụ cột B — chương Thực nghiệm).

Sinh:
  - reports/results.csv      : metric mọi cấu hình (bảng ablation dạng máy đọc)
  - reports/tables.md        : bảng ablation + kiểm định thống kê (đưa thẳng vào báo cáo)
  - reports/per_query.csv     : NDCG@10 per-query mỗi cấu hình (phục vụ vẽ/kiểm định lại)

Mỗi cấu hình tương ứng một mức của phễu multi-stage (Trụ cột A): TF-IDF only -> BM25 ->
Hybrid lexical -> Embeddings -> +L1 -> +Cross-Encoder -> +RAG-Fusion+MMR (Full).

Cách chạy:
    python scripts/eval/run_evaluation.py                 # đầy đủ
    python scripts/eval/run_evaluation.py --quick         # nhanh (bỏ rerank, ít truy vấn)
    python scripts/eval/run_evaluation.py --no-rerank     # bỏ tầng cross-encoder
"""

from __future__ import annotations

import argparse
import csv
import os
import pickle
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import random  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from itlr import config  # noqa: E402
from itlr.core import pipeline as P  # noqa: E402
from itlr.core.recommender import strip_accents  # noqa: E402
from itlr.eval import diversity, metrics as M, significance  # noqa: E402

KS = (1, 3, 5, 10, 100)
HEADLINE = ["P@5", "R@5", "NDCG@10", "MAP", "MRR", "R@100"]


def perturb_query(query: str, rng: random.Random) -> str:
    """Mô phỏng input tiếng Việt 'đời thực': bỏ dấu + chèn lỗi gõ nhẹ (hoán/xóa ký tự).

    Dùng cho chế độ --noisy: nhãn liên quan GIỮ NGUYÊN, chỉ truy vấn bị nhiễu -> đo độ
    BỀN của hệ (kênh ngữ nghĩa + char n-gram bỏ dấu) so với khớp từ vựng chính xác.
    """
    q = strip_accents(query)            # bỏ dấu (cực phổ biến khi gõ tiếng Việt)
    chars = list(q)
    for i in range(len(chars) - 1):
        r = rng.random()
        if r < 0.04:                    # hoán đổi 2 ký tự liền kề
            chars[i], chars[i + 1] = chars[i + 1], chars[i]
        elif r < 0.06 and chars[i] != " ":  # xóa ký tự
            chars[i] = ""
    return "".join(chars)


def load_qrels(path: str):
    """Đọc qrels -> {qid: {'query':str, 'rel':{item_id:grade}}}."""
    df = pd.read_csv(path)
    qrels = {}
    for qid, group in df.groupby("query_id"):
        qrels[qid] = {
            "query": group["query"].iloc[0],
            "rel": {int(r.item_id): int(r.grade) for r in group.itertuples()},
        }
    return qrels


def build_context() -> P.RankContext:
    """Nạp artifacts qua load_engine (model/ann/reranker) + retrieval_model -> RankContext."""
    from itlr.engine import load_engine
    engine = load_engine()
    retrieval_model = pickle.load(open(config.artifact("retrieval_model.pkl"), "rb"))
    si = engine.search_index
    return P.RankContext(
        item_list=engine.items,
        retrieval_model=retrieval_model,
        embeddings=si["embeddings"],
        embed_model=engine.model,
        char_vectorizer=si["char_vectorizer"],
        char_matrix=si["char_matrix"],
        query_prefix=si.get("query_prefix", ""),
        ann=si.get("ann"),
        reranker=si.get("reranker"),
    )


def grades_for_ranking(positions, id_for_pos, rel_map):
    """Chuyển danh sách vị trí xếp hạng -> mảng grade (0 nếu không nằm trong qrels)."""
    return [rel_map.get(int(id_for_pos[p]), 0) for p in positions]


def evaluate_config(ctx, cfg, qrels, id_for_pos, top_n=500, query_transform=None):
    """Chạy một cấu hình trên toàn bộ truy vấn -> (agg_metrics, per_query_ndcg10, rec_lists)."""
    per_query_rows = []
    ndcg10 = {}
    rec_lists = []
    for qid, q in qrels.items():
        qtext = query_transform(q["query"]) if query_transform else q["query"]
        positions = P.rank(ctx, qtext, cfg, top_n=top_n)
        rels = grades_for_ranking(positions, id_for_pos, q["rel"])
        n_rel = sum(1 for g in q["rel"].values() if g >= 1)
        ideal = list(q["rel"].values())
        row = M.per_query_metrics(rels, n_rel, ks=KS, ideal_rels=ideal)
        per_query_rows.append(row)
        ndcg10[qid] = row["NDCG@10"]
        rec_lists.append(positions[:10])
    agg = M.evaluate_run(per_query_rows)
    return agg, ndcg10, rec_lists


def fmt(v):
    return f"{v:.4f}" if isinstance(v, float) else str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="Nhanh: 20 truy vấn, bỏ rerank")
    ap.add_argument("--no-rerank", action="store_true", help="Bỏ tầng Cross-Encoder")
    ap.add_argument("--noisy", action="store_true",
                    help="Nhiễu hóa truy vấn (bỏ dấu + lỗi gõ) -> đo độ bền (nhãn giữ nguyên)")
    ap.add_argument("--top-n", type=int, default=500)
    ap.add_argument("--max-queries", type=int, default=0)
    ap.add_argument("--judgments", default="eval/relevance_judgments.csv",
                    help="Đường dẫn qrels (tương đối DATA_DIR) — cho phép nhiều benchmark song song")
    ap.add_argument("--tag", default="",
                    help="Hậu tố tên file báo cáo (vd _kw cho benchmark từ khóa) -> tables<tag>.md")
    args = ap.parse_args()
    suffix = args.tag + ("_noisy" if args.noisy else "")
    qtransform = (lambda s: perturb_query(s, random.Random(42))) if args.noisy else None

    qrels = load_qrels(config.data_file(args.judgments))
    if args.quick:
        args.max_queries = args.max_queries or 20
        args.no_rerank = True
    if args.max_queries:
        qrels = dict(list(qrels.items())[: args.max_queries])
    print(f"Đánh giá trên {len(qrels)} truy vấn | K={KS}")

    print("Nạp artifacts (load_engine)...")
    t0 = time.time()
    ctx = build_context()
    id_for_pos = ctx.item_list["item_id"].astype(int).to_numpy()
    n_items = len(ctx.item_list)
    print(f"  xong sau {time.time()-t0:.1f}s | {n_items} items"
          f" | ANN={'có' if ctx.ann is not None else 'không'}"
          f" | reranker={'có' if ctx.reranker is not None else 'không'}")

    configs = P.ablation_configs()
    if args.no_rerank:
        for cfg in configs.values():
            cfg.use_rerank = False

    results = {}
    ndcg_by_cfg = {}
    rec_lists_by_cfg = {}
    for name, cfg in configs.items():
        t = time.time()
        agg, ndcg10, rec_lists = evaluate_config(
            ctx, cfg, qrels, id_for_pos, top_n=args.top_n, query_transform=qtransform)
        results[name] = agg
        ndcg_by_cfg[name] = ndcg10
        rec_lists_by_cfg[name] = rec_lists
        print(f"  [{name}] NDCG@10={agg['NDCG@10']:.4f} P@5={agg['P@5']:.4f} "
              f"MAP={agg['MAP']:.4f} ({time.time()-t:.1f}s)")

    # ── results.csv ──────────────────────────────────────────────────────────
    os.makedirs(config.ROOT / "reports", exist_ok=True)
    metric_keys = list(next(iter(results.values())).keys())
    with open(config.ROOT / "reports" / f"results{suffix}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["config"] + metric_keys)
        for name, agg in results.items():
            w.writerow([name] + [fmt(agg[k]) for k in metric_keys])
    print(f"-> reports/results{suffix}.csv")

    # ── per_query.csv (NDCG@10) ──────────────────────────────────────────────
    with open(config.ROOT / "reports" / f"per_query{suffix}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        names = list(configs.keys())
        w.writerow(["query_id"] + names)
        for qid in qrels:
            w.writerow([qid] + [fmt(ndcg_by_cfg[n][qid]) for n in names])

    # ── kiểm định thống kê: cấu hình TỐT NHẤT (NDCG@10) vs từng baseline ──────
    # Dùng cấu hình NDCG@10 cao nhất làm mốc (không cố định "Full" — vì MMR đánh đổi độ
    # chính xác lấy đa dạng nên Full không phải lúc nào cũng cao nhất; chọn tự động cho
    # bảng kiểm định luôn phản ánh "tốt nhất vs baseline").
    full_name = max(results, key=lambda n: results[n]["NDCG@10"])
    sig_rows = []
    full_scores = [ndcg_by_cfg[full_name][q] for q in qrels]
    for name in configs:
        if name == full_name:
            continue
        base_scores = [ndcg_by_cfg[name][q] for q in qrels]
        cmp = significance.compare(full_scores, base_scores)
        sig_rows.append((name, cmp))

    # ── beyond-accuracy cho cấu hình Full (đa dạng hóa MMR) ──────────────────
    diverse_name = "+ RAG-Fusion + MMR (Full)"
    ba = diversity.beyond_accuracy_report(
        rec_lists_by_cfg.get(diverse_name, rec_lists_by_cfg[full_name]), n_items,
        embeddings=ctx.embeddings,
        popularity=None,
    )

    # ── tables.md ────────────────────────────────────────────────────────────
    write_tables(results, sig_rows, ba, full_name, len(qrels), suffix, args.noisy)
    print(f"-> reports/tables{suffix}.md")
    print(f"\nHoàn tất. Xem reports/tables{suffix}.md để có bảng ablation + kiểm định.")


def write_tables(results, sig_rows, ba, full_name, n_queries, suffix="", noisy=False):
    lines = []
    mode = "NHIỄU (bỏ dấu + lỗi gõ)" if noisy else "sạch"
    lines.append(f"# Kết quả đánh giá — Bảng ablation per-stage (truy vấn {mode})\n")
    lines.append(f"*Số truy vấn: {n_queries}. Metric macro-average trên nhãn bán-tự-động "
                 f"(`data/eval/relevance_judgments.csv`).*\n")
    if noisy:
        lines.append("> Truy vấn bị **bỏ dấu + chèn lỗi gõ**, nhãn liên quan giữ nguyên. "
                     "Bảng này đo **độ bền** của hệ trước input tiếng Việt đời thực: khớp từ "
                     "vựng chính xác (TF-IDF/BM25) sụt mạnh, kênh ngữ nghĩa + char n-gram bỏ dấu "
                     "giữ được chất lượng.\n")
    else:
        lines.append("> Lưu ý: nhãn tự động ≈ khớp topic chính xác nên các cấu hình từ vựng "
                     "(TF-IDF/BM25) gần chạm trần — bảng sạch chủ yếu xác nhận **recall** của tầng "
                     "sinh ứng viên. Khác biệt phương pháp thể hiện rõ ở bảng **truy vấn nhiễu** "
                     "(`tables_noisy.md`) và trên **nhãn người gán** (`evaluate_human.py`). "
                     "Cấu hình **Full** thêm MMR -> đánh đổi một phần độ chính xác lấy **đa dạng** "
                     "(xem mục beyond-accuracy); **+ Cross-Encoder** là mốc độ-chính-xác cao nhất.\n")

    # bảng headline
    lines.append("## Bảng ablation (headline metrics)\n")
    header = "| Cấu hình | " + " | ".join(HEADLINE) + " |"
    sep = "|---|" + "|".join(["---"] * len(HEADLINE)) + "|"
    lines.append(header)
    lines.append(sep)
    for name, agg in results.items():
        cells = [fmt(agg.get(k, 0.0)) for k in HEADLINE]
        bold = "**" if name == full_name else ""
        lines.append(f"| {bold}{name}{bold} | " + " | ".join(cells) + " |")
    lines.append("")

    # kiểm định thống kê (mốc = cấu hình tốt nhất, in đậm ở bảng trên)
    lines.append(f"## Kiểm định thống kê — **{full_name}** (tốt nhất) vs baseline (NDCG@10)\n")
    lines.append(f"| Baseline | NDCG@10 (base) | {full_name} − base | CI 95% | p (t-test) | p (bootstrap) | Có ý nghĩa? |")
    lines.append("|---|---|---|---|---|---|---|")
    for name, c in sig_rows:
        ci = f"[{c['ci_low']:.4f}, {c['ci_high']:.4f}]"
        sig = "✅ p<0.05" if c["significant"] else "—"
        lines.append(f"| {name} | {c['mean_b']:.4f} | {c['mean_diff']:+.4f} | {ci} "
                     f"| {c['p_ttest']:.4g} | {c['p_bootstrap']:.4g} | {sig} |")
    lines.append("")

    # beyond-accuracy
    lines.append("## Beyond-accuracy (cấu hình Full, top-10)\n")
    lines.append("| Metric | Giá trị |")
    lines.append("|---|---|")
    for k, v in ba.items():
        lines.append(f"| {k} | {v:.4f} |")
    lines.append("")

    with open(config.ROOT / "reports" / f"tables{suffix}.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
