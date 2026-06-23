"""Khung đánh giá khoa học cho hệ gợi ý (Trụ cột B của kế hoạch nâng cấp).

Các module:
  - metrics.py       : metric xếp hạng chuẩn ngành (Precision/Recall/NDCG/MAP/MRR/HitRate).
  - diversity.py     : metric "beyond-accuracy" (Coverage/ILD/Novelty/Serendipity/Gini).
  - significance.py  : kiểm định thống kê (paired bootstrap, paired t-test, CI 95%).
  - cf_eval.py       : đánh giá Collaborative Filtering (leave-one-out, temporal split).
  - off_policy.py    : counterfactual / off-policy evaluation (IPS / SNIPS / Doubly Robust).

Tất cả viết bằng numpy thuần — không thêm dependency nặng. Mọi metric đo trên các
mảng độ liên quan (relevance) đã được xếp theo thứ hạng do hệ trả về.
"""

from itlr.eval import metrics  # noqa: F401
