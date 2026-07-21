"""Đánh giá counterfactual / off-policy.

Bài toán: từ LOG cũ (sinh bởi policy logging cũ), ước lượng KHÔNG THIÊN LỆCH phần thưởng
(reward/CTR) mà một policy MỚI sẽ đạt — mà không cần triển khai thật. Đây là chuẩn vàng
đánh giá ranking offline ở Google/Meta/Netflix.

Mô hình bandit ngữ cảnh (contextual bandit), mỗi bản ghi log:
  - action       : item được policy cũ hiển thị (top-1).
  - reward        : phản hồi quan sát (1 = click, 0 = không).
  - behavior_prop : p_logging(action | context) — xác suất policy CŨ chọn action đó (propensity).
  - target_prop   : p_target(action | context) — xác suất policy MỚI chọn chính action đó.

Ba estimator:
  - IPS  : trọng số nghịch propensity (không thiên lệch nhưng phương sai cao).
  - SNIPS: IPS tự chuẩn hóa (giảm phương sai, hơi thiên lệch).
  - DR   : Doubly Robust — kết hợp mô hình reward + IPS (bền nhất).

Tất cả kèm khoảng tin cậy bootstrap. numpy thuần.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence

import numpy as np

_EPS = 1e-12


def _weights(behavior_prop, target_prop, clip=None):
    b = np.asarray(behavior_prop, dtype="float64")
    t = np.asarray(target_prop, dtype="float64")
    w = t / np.maximum(b, _EPS)
    if clip is not None:
        w = np.minimum(w, clip)
    return w


def ips(rewards, behavior_prop, target_prop, clip: Optional[float] = None) -> float:
    """Inverse Propensity Scoring: V = mean(w * reward), w = p_target/p_logging."""
    r = np.asarray(rewards, dtype="float64")
    w = _weights(behavior_prop, target_prop, clip)
    return float(np.mean(w * r))


def snips(rewards, behavior_prop, target_prop, clip: Optional[float] = None) -> float:
    """Self-Normalized IPS: V = sum(w*r) / sum(w) — giảm phương sai."""
    r = np.asarray(rewards, dtype="float64")
    w = _weights(behavior_prop, target_prop, clip)
    denom = np.sum(w)
    if denom <= _EPS:
        return 0.0
    return float(np.sum(w * r) / denom)


def doubly_robust(
    rewards,
    behavior_prop,
    target_prop,
    q_logged,
    v_target,
    clip: Optional[float] = None,
) -> float:
    """Doubly Robust: V = mean( v_target + w*(reward − q_logged) ).

    q_logged : reward dự đoán của mô hình cho ĐÚNG action đã log (q̂(x, a_logged)).
    v_target : reward kỳ vọng của mô hình dưới policy mới  E_{a~target}[q̂(x, a)].
    Không thiên lệch nếu MỘT trong hai (propensity HOẶC mô hình reward) đúng -> "doubly robust".
    """
    r = np.asarray(rewards, dtype="float64")
    q = np.asarray(q_logged, dtype="float64")
    v = np.asarray(v_target, dtype="float64")
    w = _weights(behavior_prop, target_prop, clip)
    return float(np.mean(v + w * (r - q)))


def _bootstrap_ci(fn, n, ci=0.95, n_boot=2000, seed=17) -> Dict[str, float]:
    rng = np.random.default_rng(seed)
    vals = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        vals[i] = fn(idx)
    alpha = 1 - ci
    return {
        "estimate": float(fn(np.arange(n))),
        "ci_low": float(np.quantile(vals, alpha / 2)),
        "ci_high": float(np.quantile(vals, 1 - alpha / 2)),
        "se": float(np.std(vals, ddof=1)),
    }


def evaluate_policy(
    rewards: Sequence[float],
    behavior_prop: Sequence[float],
    target_prop: Sequence[float],
    q_logged: Optional[Sequence[float]] = None,
    v_target: Optional[Sequence[float]] = None,
    clip: Optional[float] = None,
    n_boot: int = 2000,
) -> Dict[str, Dict[str, float]]:
    """Ước lượng giá trị policy mới bằng cả 3 estimator + bootstrap CI 95%.

    Trả {'IPS': {...}, 'SNIPS': {...}, 'DR': {...}} (DR chỉ khi có q_logged + v_target).
    """
    r = np.asarray(rewards, dtype="float64")
    b = np.asarray(behavior_prop, dtype="float64")
    t = np.asarray(target_prop, dtype="float64")
    n = len(r)

    out: Dict[str, Dict[str, float]] = {}
    out["IPS"] = _bootstrap_ci(lambda idx: ips(r[idx], b[idx], t[idx], clip), n, n_boot=n_boot)
    out["SNIPS"] = _bootstrap_ci(lambda idx: snips(r[idx], b[idx], t[idx], clip), n, n_boot=n_boot)
    if q_logged is not None and v_target is not None:
        q = np.asarray(q_logged, dtype="float64")
        v = np.asarray(v_target, dtype="float64")
        out["DR"] = _bootstrap_ci(
            lambda idx: doubly_robust(r[idx], b[idx], t[idx], q[idx], v[idx], clip),
            n, n_boot=n_boot)
    return out


def effective_sample_size(behavior_prop, target_prop) -> float:
    """ESS = (Σw)² / Σw² — số mẫu hiệu dụng sau khi tái cân bằng (chẩn đoán phương sai IPS).

    ESS thấp so với N -> phân bố trọng số lệch nặng -> ước lượng IPS không ổn định."""
    w = _weights(behavior_prop, target_prop)
    s1 = np.sum(w)
    s2 = np.sum(w * w)
    if s2 <= _EPS:
        return 0.0
    return float(s1 * s1 / s2)


def naive_on_policy_value(rewards) -> float:
    """Giá trị 'ngây thơ' = CTR trung bình quan sát của policy LOGGING (để đối chiếu thiên lệch)."""
    return float(np.mean(np.asarray(rewards, dtype="float64")))
