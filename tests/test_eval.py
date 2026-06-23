"""Smoke + correctness tests cho khung đánh giá (Trụ cột B–D).

Chỉ kiểm các module numpy thuần (không cần nạp model nặng) -> chạy nhanh, hợp cho CI.
"""

import math

import numpy as np
import pytest

from itlr.eval import diversity, metrics as M, off_policy as OP, significance as S


# ── metrics ──────────────────────────────────────────────────────────────────
def test_precision_recall():
    r = [1, 0, 1, 0]
    assert M.precision_at_k(r, 2) == pytest.approx(0.5)
    assert M.precision_at_k(r, 4) == pytest.approx(0.5)
    assert M.recall_at_k(r, 2, n_relevant=2) == pytest.approx(0.5)
    assert M.recall_at_k(r, 4, n_relevant=2) == pytest.approx(1.0)


def test_average_precision_known():
    # rels [1,0,1,0], 2 relevant -> (1/1 + 2/3)/2 = 0.8333
    assert M.average_precision([1, 0, 1, 0], 2) == pytest.approx(0.8333, abs=1e-4)


def test_mrr():
    assert M.reciprocal_rank([0, 0, 1]) == pytest.approx(1 / 3)
    assert M.reciprocal_rank([1, 0, 0]) == pytest.approx(1.0)
    assert M.reciprocal_rank([0, 0, 0]) == pytest.approx(0.0)


def test_ndcg_perfect_and_bounds():
    assert M.ndcg_at_k([2, 1, 0], 3) == pytest.approx(1.0)
    val = M.ndcg_at_k([0, 1, 2], 3, ideal_rels=[2, 1, 0])
    assert 0.0 <= val < 1.0


def test_ndcg_empty():
    assert M.ndcg_at_k([], 5) == 0.0
    assert M.ndcg_at_k([0, 0], 2) == 0.0


def test_evaluate_rankings_aggregates():
    agg = M.evaluate_rankings([[2, 0, 1], [1, 1, 0]], [2, 2], ks=(1, 3))
    assert "NDCG@3" in agg and "MAP" in agg and "MRR" in agg
    assert 0 <= agg["NDCG@3"] <= 1


# ── diversity ────────────────────────────────────────────────────────────────
def test_coverage():
    assert diversity.catalog_coverage([[0, 1], [1, 2]], n_items=10) == pytest.approx(0.3)


def test_ild_orthogonal_vs_identical():
    emb = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]])
    # item 0 và 1 trực giao -> ILD = 1; item 0 và 2 trùng -> ILD = 0
    assert diversity.intra_list_diversity([0, 1], emb) == pytest.approx(1.0)
    assert diversity.intra_list_diversity([0, 2], emb) == pytest.approx(0.0)


def test_gini_uniform_is_low():
    # phân bố đều -> Gini ~ 0
    lists = [[i] for i in range(10)]
    assert diversity.gini_index(lists, 10) == pytest.approx(0.0, abs=1e-9)


# ── significance ─────────────────────────────────────────────────────────────
def test_paired_ttest_clear_difference():
    a = [0.9, 0.85, 0.88, 0.92, 0.87]
    b = [0.5, 0.55, 0.52, 0.49, 0.51]
    res = S.compare(a, b)
    assert res["mean_diff"] > 0
    assert res["significant"] is True
    assert res["p_ttest"] < 0.05


def test_paired_ttest_no_difference():
    a = [0.5, 0.6, 0.4, 0.55, 0.45]
    res = S.paired_t_test(a, a)
    assert res["p_value"] == pytest.approx(1.0)


def test_cohen_kappa_perfect_and_chance():
    assert S.cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]) == pytest.approx(1.0)
    # đối nghịch hoàn toàn -> kappa âm
    assert S.cohen_kappa([1, 1, 0, 0], [0, 0, 1, 1]) < 0


def test_bootstrap_ci_contains_mean():
    a = [0.8, 0.7, 0.9, 0.85, 0.75]
    b = [0.6, 0.5, 0.7, 0.65, 0.55]
    res = S.paired_bootstrap(a, b, n_boot=2000)
    assert res["ci_low"] <= res["mean_diff"] <= res["ci_high"]


# ── off-policy ───────────────────────────────────────────────────────────────
def test_ips_unbiased_on_matching_policies():
    # nếu target == behavior thì w=1 -> IPS = CTR trung bình
    r = np.array([1.0, 0.0, 1.0, 0.0])
    p = np.array([0.5, 0.5, 0.5, 0.5])
    assert OP.ips(r, p, p) == pytest.approx(0.5)
    assert OP.snips(r, p, p) == pytest.approx(0.5)


def test_ips_reweights():
    r = np.array([1.0, 0.0])
    b = np.array([0.5, 0.5])
    t = np.array([1.0, 0.0])     # target dồn hết khối lượng vào action thắng
    # IPS = mean([2*1, 0]) = 1.0
    assert OP.ips(r, b, t) == pytest.approx(1.0)


def test_doubly_robust_recovers_with_perfect_model():
    r = np.array([1.0, 0.0, 1.0])
    b = np.array([0.5, 0.5, 0.5])
    t = np.array([0.5, 0.5, 0.5])
    q = r.copy()                 # mô hình reward hoàn hảo
    v = r.copy()
    # w=1, r-q=0 -> DR = mean(v) = mean(r)
    assert OP.doubly_robust(r, b, t, q, v) == pytest.approx(float(np.mean(r)))


def test_effective_sample_size_bounds():
    b = np.full(100, 0.5)
    ess = OP.effective_sample_size(b, b)
    assert ess == pytest.approx(100.0)


def test_evaluate_policy_structure():
    rng = np.random.default_rng(0)
    n = 200
    r = (rng.random(n) < 0.4).astype(float)
    b = rng.uniform(0.2, 0.8, n)
    t = rng.uniform(0.2, 0.8, n)
    res = OP.evaluate_policy(r, b, t, q_logged=r, v_target=r, n_boot=200)
    for est in ("IPS", "SNIPS", "DR"):
        assert est in res and "ci_low" in res[est] and "ci_high" in res[est]
