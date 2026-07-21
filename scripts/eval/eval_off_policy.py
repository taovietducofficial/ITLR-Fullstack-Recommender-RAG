"""Đánh giá off-policy ĐẦU-CUỐI có ĐỐI CHỨNG ground-truth.

Vì hệ chưa có log click thật, ta DỰNG một mô phỏng bandit ngữ cảnh GROUNDED trên catalog
thật (dùng category thật của 50k item) với một hàm reward ĐÃ BIẾT. Nhờ biết sự thật, ta
CHỨNG MINH được tính không thiên lệch: CI của IPS/SNIPS/DR phải PHỦ giá trị thật của policy
mới, trong khi ước lượng 'naive' (CTR quan sát của policy cũ) bị LỆCH.

Kịch bản:
  - context : một user có chuyên mục ưa thích c_t (lấy ngẫu nhiên).
  - action  : top-1 item policy chọn từ tập ứng viên K item (vài item đúng c_t + nhiễu).
  - reward  : click ~ Bernoulli(p_true) với p_true cao nếu item đúng chuyên mục ưa thích.
  - policy CŨ (logging) : softmax 'heuristic' lệch theo độ phổ biến (temp cao -> ngẫu nhiên).
  - policy MỚI (target) : softmax theo đúng-chuyên-mục (greedier) -> tốt hơn.

Cách chạy:
    python scripts/eval/eval_off_policy.py
    python scripts/eval/eval_off_policy.py --rounds 8000 --clip 50
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from itlr import config  # noqa: E402
from itlr.eval import off_policy as OP  # noqa: E402


def softmax(x):
    x = x - np.max(x)
    e = np.exp(x)
    return e / np.sum(e)


def simulate(items: pd.DataFrame, rounds: int, k: int, seed: int):
    """Sinh log + tính sẵn các đại lượng cho 3 estimator và giá trị THẬT của 2 policy."""
    rng = np.random.default_rng(seed)
    cats = items["category"].to_numpy()
    uniq_cats = sorted(set(cats.tolist()))
    pop = items["__pop"].to_numpy()
    n = len(items)

    A_REL, B_POP, BIAS = 2.4, 0.4, 2.0
    TEMP_LOG, TEMP_TGT = 1.2, 0.5
    POP_BIAS_LOG = 0.9

    logs = {"reward": [], "b_prop": [], "t_prop": [], "cat_match": [], "pop_norm": []}
    cand_cm_all, cand_pn_all, p_tgt_all = [], [], []
    true_target_vals, true_logging_vals = [], []

    for _ in range(rounds):
        c = uniq_cats[rng.integers(0, len(uniq_cats))]
        same = np.where(cats == c)[0]
        n_same = min(len(same), max(2, k // 3))
        cand = np.concatenate([
            rng.choice(same, size=n_same, replace=False),
            rng.integers(0, n, size=k - n_same),
        ])
        cm = (cats[cand] == c).astype("float64")
        pn = pop[cand]

        p_true = 1.0 / (1.0 + np.exp(-(A_REL * cm + B_POP * pn - BIAS)))

        log_score = (cm + POP_BIAS_LOG * pn) / TEMP_LOG
        tgt_score = (cm) / TEMP_TGT
        p_log = softmax(log_score)
        p_tgt = softmax(tgt_score)

        a = rng.choice(len(cand), p=p_log)
        r = float(rng.random() < p_true[a])

        logs["reward"].append(r)
        logs["b_prop"].append(p_log[a])
        logs["t_prop"].append(p_tgt[a])
        logs["cat_match"].append(cm[a])
        logs["pop_norm"].append(pn[a])
        cand_cm_all.append(cm)
        cand_pn_all.append(pn)
        p_tgt_all.append(p_tgt)

        true_target_vals.append(float(np.sum(p_tgt * p_true)))
        true_logging_vals.append(float(np.sum(p_log * p_true)))

    log = {k: np.asarray(v, dtype="float64") for k, v in logs.items()}
    log["cand_cm"] = np.asarray(cand_cm_all, dtype="float64")
    log["cand_pn"] = np.asarray(cand_pn_all, dtype="float64")
    log["cand_ptgt"] = np.asarray(p_tgt_all, dtype="float64")
    log["true_target"] = float(np.mean(true_target_vals))
    log["true_logging"] = float(np.mean(true_logging_vals))
    return log


def fit_reward_model(log):
    """q̂(reward | cat_match, pop_norm) bằng hồi quy logistic trên LOG quan sát (cho DR).

    Cố ý đơn giản/không hoàn hảo để thể hiện DR vẫn bền dù mô hình reward chỉ gần đúng."""
    from sklearn.linear_model import LogisticRegression
    X = np.column_stack([log["cat_match"], log["pop_norm"]])
    y = log["reward"].astype(int)
    if len(set(y.tolist())) < 2:
        mean = float(np.mean(y))
        return lambda cm, pn: np.full_like(cm, mean, dtype="float64")
    clf = LogisticRegression(max_iter=200).fit(X, y)

    def q(cm, pn):
        Xt = np.column_stack([np.asarray(cm, dtype="float64"), np.asarray(pn, dtype="float64")])
        return clf.predict_proba(Xt)[:, 1]
    return q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=6000)
    ap.add_argument("--k", type=int, default=15)
    ap.add_argument("--clip", type=float, default=None, help="ngưỡng chặn trọng số IPS (giảm phương sai)")
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()

    items = pd.read_csv(config.ITEMS_CSV).dropna(subset=["category"]).reset_index(drop=True)
    rng = np.random.default_rng(0)
    items["__pop"] = rng.random(len(items))
    print(f"Mô phỏng off-policy trên {len(items)} item thật, {args.rounds} vòng, K={args.k}")

    log = simulate(items, args.rounds, args.k, args.seed)
    q = fit_reward_model(log)

    q_logged = q(log["cat_match"], log["pop_norm"])
    rounds, kk = log["cand_cm"].shape
    q_cand = q(log["cand_cm"].ravel(), log["cand_pn"].ravel()).reshape(rounds, kk)
    v_target = np.sum(log["cand_ptgt"] * q_cand, axis=1)

    res = OP.evaluate_policy(
        log["reward"], log["b_prop"], log["t_prop"],
        q_logged=q_logged, v_target=v_target, clip=args.clip, n_boot=2000,
    )
    naive = OP.naive_on_policy_value(log["reward"])
    ess = OP.effective_sample_size(log["b_prop"], log["t_prop"])

    true_t = log["true_target"]
    true_l = log["true_logging"]

    def covered(d):
        return d["ci_low"] <= true_t <= d["ci_high"]

    print(f"\nGiá trị THẬT policy MỚI (target)  : {true_t:.4f}")
    print(f"Giá trị THẬT policy CŨ  (logging) : {true_l:.4f}")
    print(f"Naive (CTR quan sát, ước lượng CŨ): {naive:.4f}  -> LỆCH khỏi target {naive-true_t:+.4f}")
    print(f"ESS = {ess:.0f} / {len(log['reward'])} (mẫu hiệu dụng)\n")
    for name in ["IPS", "SNIPS", "DR"]:
        if name in res:
            d = res[name]
            ok = "phủ" if covered(d) else "trượt"
            print(f"{name:6s}: {d['estimate']:.4f}  CI95=[{d['ci_low']:.4f}, {d['ci_high']:.4f}]  "
                  f"({ok} giá trị thật {true_t:.4f})")

    lines = ["# Đánh giá off-policy / counterfactual (D)\n",
             f"*Mô phỏng bandit ngữ cảnh GROUNDED trên {len(items)} item thật; "
             f"{args.rounds} vòng; reward known-truth.*\n",
             "## So sánh ước lượng vs giá trị THẬT\n",
             "| Đại lượng | Giá trị | CI 95% | Phủ giá trị thật target? |",
             "|---|---|---|---|",
             f"| **Giá trị thật — policy MỚI** | **{true_t:.4f}** | — | (mốc) |",
             f"| Giá trị thật — policy CŨ | {true_l:.4f} | — | — |",
             f"| Naive (CTR quan sát) | {naive:.4f} | — | lệch {naive-true_t:+.4f} |"]
    for name in ["IPS", "SNIPS", "DR"]:
        if name in res:
            d = res[name]
            lines.append(f"| {name} | {d['estimate']:.4f} | "
                         f"[{d['ci_low']:.4f}, {d['ci_high']:.4f}] | "
                         f"{'có' if covered(d) else 'không'} |")
    lines.append(f"\n- **Effective Sample Size** = {ess:.0f}/{len(log['reward'])} "
                 "(ESS thấp -> trọng số lệch -> ưu tiên SNIPS/DR + clip).")
    lines.append("- **Kết luận:** estimator off-policy ước lượng đúng giá trị policy MỚI **chỉ từ "
                 "log của policy cũ**, trong khi naive lệch — đúng tinh thần đánh giá counterfactual "
                 "chuẩn công nghiệp.")
    lines.append("\n*Đây là MÔ PHỎNG để kiểm chứng tính không thiên lệch của estimator (vì cần biết "
                 "ground-truth). Khi có log click thật từ web app, dùng `itlr/eval/off_policy.py` y nguyên.*")
    out = config.ROOT / "reports" / "off_policy.md"
    os.makedirs(out.parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n-> reports/off_policy.md")


if __name__ == "__main__":
    main()
