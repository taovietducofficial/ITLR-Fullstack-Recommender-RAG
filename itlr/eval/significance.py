"""Kiểm định thống kê cho hiệu số metric giữa hai cấu hình (Trụ cột B5).

Mọi tuyên bố "A tốt hơn B" cần kèm bằng chứng thống kê, không phải may rủi. Module cài:
  - paired_bootstrap : khoảng tin cậy bootstrap cho hiệu số trung bình (per-query).
  - paired_t_test    : t-test bắt cặp (cùng tập truy vấn) -> p-value hai phía.
  - compare          : gộp cả hai + cờ significant.

numpy thuần; t-test dùng xấp xỉ phân phối t qua scipy nếu có, fallback chuẩn (z) nếu không.
"""

from __future__ import annotations

import math
from typing import Dict, Sequence

import numpy as np


def paired_bootstrap(
    scores_a: Sequence[float],
    scores_b: Sequence[float],
    n_boot: int = 10000,
    ci: float = 0.95,
    seed: int = 13,
) -> Dict[str, float]:
    """Bootstrap bắt cặp trên hiệu số per-query (A − B).

    Trả mean_diff + khoảng tin cậy [lo, hi] + p-value bootstrap hai phía (tỉ lệ mẫu
    bootstrap có dấu ngược với mean_diff, nhân đôi).
    """
    a = np.asarray(scores_a, dtype="float64")
    b = np.asarray(scores_b, dtype="float64")
    assert a.shape == b.shape, "Hai cấu hình phải đo trên CÙNG tập truy vấn (bắt cặp)."
    diff = a - b
    n = diff.size
    if n == 0:
        return {"mean_diff": 0.0, "ci_low": 0.0, "ci_high": 0.0, "p_value": 1.0}

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    boot_means = diff[idx].mean(axis=1)

    alpha = 1.0 - ci
    lo = float(np.quantile(boot_means, alpha / 2))
    hi = float(np.quantile(boot_means, 1 - alpha / 2))

    mean_diff = float(diff.mean())
    # p-value bootstrap hai phía: tỉ lệ mẫu vượt qua 0 theo hướng ngược lại
    if mean_diff >= 0:
        p = 2.0 * float(np.mean(boot_means <= 0))
    else:
        p = 2.0 * float(np.mean(boot_means >= 0))
    p = min(1.0, p)
    return {"mean_diff": mean_diff, "ci_low": lo, "ci_high": hi, "p_value": p}


def _t_sf(t: float, df: int) -> float:
    """Hàm sống sót (survival) hai phía cho phân phối t. Dùng scipy nếu có."""
    try:
        from scipy import stats

        return float(2 * stats.t.sf(abs(t), df))
    except Exception:
        # fallback: xấp xỉ chuẩn (đủ tốt khi df lớn)
        return float(2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2)))))


def paired_t_test(scores_a: Sequence[float], scores_b: Sequence[float]) -> Dict[str, float]:
    """Paired t-test trên hiệu số per-query -> t-statistic + p-value hai phía."""
    a = np.asarray(scores_a, dtype="float64")
    b = np.asarray(scores_b, dtype="float64")
    diff = a - b
    n = diff.size
    if n < 2:
        return {"t_stat": 0.0, "p_value": 1.0, "mean_diff": float(diff.mean()) if n else 0.0}
    mean = diff.mean()
    sd = diff.std(ddof=1)
    if sd == 0:
        # mọi hiệu số bằng nhau: khác biệt xác định (p≈0 nếu mean≠0)
        return {"t_stat": float("inf") if mean != 0 else 0.0,
                "p_value": 0.0 if mean != 0 else 1.0, "mean_diff": float(mean)}
    t = mean / (sd / math.sqrt(n))
    return {"t_stat": float(t), "p_value": _t_sf(t, n - 1), "mean_diff": float(mean)}


def compare(
    scores_a: Sequence[float],
    scores_b: Sequence[float],
    alpha: float = 0.05,
    n_boot: int = 10000,
) -> Dict[str, float]:
    """So sánh đầy đủ A vs B: bootstrap CI + t-test + cờ significant (p < alpha)."""
    boot = paired_bootstrap(scores_a, scores_b, n_boot=n_boot, ci=1 - alpha)
    tt = paired_t_test(scores_a, scores_b)
    return {
        "mean_a": float(np.mean(scores_a)) if len(scores_a) else 0.0,
        "mean_b": float(np.mean(scores_b)) if len(scores_b) else 0.0,
        "mean_diff": boot["mean_diff"],
        "ci_low": boot["ci_low"],
        "ci_high": boot["ci_high"],
        "p_bootstrap": boot["p_value"],
        "p_ttest": tt["p_value"],
        "t_stat": tt["t_stat"],
        "significant": bool(tt["p_value"] < alpha),
    }


def cohen_kappa(labels_a: Sequence[int], labels_b: Sequence[int]) -> float:
    """Cohen's Kappa — độ đồng thuận giữa hai bộ nhãn (vd nhãn tự động vs người gán).

    Hỗ trợ nhãn rời rạc bất kỳ (nhị phân hoặc graded). 1.0 = đồng thuận hoàn hảo,
    0.0 = bằng mức ngẫu nhiên, < 0 = tệ hơn ngẫu nhiên.
    """
    a = np.asarray(labels_a)
    b = np.asarray(labels_b)
    assert a.shape == b.shape and a.size > 0, "Hai bộ nhãn phải cùng độ dài, khác rỗng."
    classes = sorted(set(a.tolist()) | set(b.tolist()))
    idx = {c: i for i, c in enumerate(classes)}
    n_cls = len(classes)
    conf = np.zeros((n_cls, n_cls), dtype="float64")
    for x, y in zip(a, b):
        conf[idx[x], idx[y]] += 1
    total = conf.sum()
    po = np.trace(conf) / total
    row = conf.sum(axis=1) / total
    col = conf.sum(axis=0) / total
    pe = float(np.sum(row * col))
    if pe >= 1.0:
        return 1.0
    return float((po - pe) / (1 - pe))
