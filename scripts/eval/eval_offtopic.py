"""Đánh giá định lượng CỔNG OFF-TOPIC của chatbot.

Hệ dùng `query_relevance_max` (điểm tương đồng cao nhất với catalog) làm cổng: < ngưỡng ->
coi là NGOÀI lĩnh vực CNTT. Script này biến cách chọn ngưỡng "0.55 cảm tính" thành quyết
định DỰA TRÊN DỮ LIỆU: quét ngưỡng trên bộ test gán nhãn (câu IT vs ngoài lĩnh vực), đo
Precision/Recall/F1 + AUC (ROC), và đề xuất ngưỡng tối ưu F1.

Bộ test: data/eval/offtopic_testset.csv (cột query,label — 1=IT, 0=ngoài lĩnh vực).

Cách chạy:
    python scripts/eval/eval_offtopic.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from itlr import config  # noqa: E402
from itlr.core.recommender import query_relevance_max  # noqa: E402


def roc_auc(labels, scores):
    """AUC qua công thức Mann–Whitney U (không cần sklearn)."""
    labels = np.asarray(labels)
    scores = np.asarray(scores)
    pos = scores[labels == 1]
    neg = scores[labels == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(scores)
    ranks = np.empty(len(scores), dtype="float64")
    ranks[order] = np.arange(1, len(scores) + 1)
    rank_pos = ranks[labels == 1].sum()
    auc = (rank_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))
    return float(auc)


def prf_at(labels, scores, thr):
    pred = (np.asarray(scores) >= thr).astype(int)
    labels = np.asarray(labels)
    tp = int(((pred == 1) & (labels == 1)).sum())
    fp = int(((pred == 1) & (labels == 0)).sum())
    fn = int(((pred == 0) & (labels == 1)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return prec, rec, f1


def main():
    df = pd.read_csv(config.data_file("eval/offtopic_testset.csv"))
    print(f"Bộ test off-topic: {len(df)} câu ({int(df.label.sum())} IT / {int((df.label==0).sum())} ngoài lĩnh vực)")
    print("Nạp engine + chấm điểm tương đồng...")

    from itlr.engine import load_engine
    eng = load_engine()
    si = eng.search_index

    scores = []
    for q in df["query"]:
        s = query_relevance_max(
            q, eng.items, eng.model, si["embeddings"],
            char_vectorizer=si["char_vectorizer"], char_matrix=si["char_matrix"],
            query_prefix=si.get("query_prefix", ""), ann=si.get("ann"),
        )
        scores.append(float(s))
    df["score"] = scores
    labels = df["label"].to_numpy()

    auc = roc_auc(labels, scores)
    grid = np.linspace(0.30, 0.80, 51)
    best = max(((t, *prf_at(labels, scores, t)) for t in grid), key=lambda x: x[3])
    cur = prf_at(labels, scores, 0.55)

    print(f"\nAUC (ROC) = {auc:.4f}")
    print(f"Ngưỡng hiện tại 0.55: P={cur[0]:.3f} R={cur[1]:.3f} F1={cur[2]:.3f}")
    print(f"Ngưỡng tối ưu F1 = {best[0]:.3f}: P={best[1]:.3f} R={best[2]:.3f} F1={best[3]:.3f}")
    print("IT score TB:", round(float(df[df.label==1].score.mean()), 3),
          "| ngoài lĩnh vực TB:", round(float(df[df.label==0].score.mean()), 3))

    lines = ["# Đánh giá cổng off-topic của chatbot\n",
             f"*Bộ test: {len(df)} câu ({int(df.label.sum())} IT / {int((df.label==0).sum())} ngoài lĩnh vực). "
             f"Tín hiệu cổng = `query_relevance_max`.*\n",
             f"- **AUC (ROC) = {auc:.4f}**",
             f"- Điểm TB: IT = {df[df.label==1].score.mean():.3f} · ngoài lĩnh vực = {df[df.label==0].score.mean():.3f}\n",
             "| Ngưỡng | Precision | Recall | F1 |",
             "|---|---|---|---|",
             f"| 0.55 (hiện tại) | {cur[0]:.3f} | {cur[1]:.3f} | {cur[2]:.3f} |",
             f"| **{best[0]:.3f} (tối ưu F1)** | {best[1]:.3f} | {best[2]:.3f} | {best[3]:.3f} |"]
    lines.append("\n### Bảng quét ngưỡng (trích)\n| Ngưỡng | P | R | F1 |\n|---|---|---|---|")
    for t in np.linspace(0.40, 0.70, 7):
        p, r, f = prf_at(labels, scores, t)
        lines.append(f"| {t:.2f} | {p:.3f} | {r:.3f} | {f:.3f} |")
    lines.append("\n*Kết luận: ngưỡng cổng được biện minh bằng **dữ liệu** (tối ưu F1 + AUC) thay vì "
                 "cảm tính. Mở rộng bộ test -> con số đáng tin hơn.*")
    out = config.ROOT / "reports" / "offtopic_eval.md"
    os.makedirs(out.parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n-> reports/offtopic_eval.md")


if __name__ == "__main__":
    main()
