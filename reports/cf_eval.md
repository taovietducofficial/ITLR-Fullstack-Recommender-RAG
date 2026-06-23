# Đánh giá Collaborative Filtering (B6)

*Số user đánh giá: 800 (leave-one-out), 800 (temporal split).*

## Leave-one-out — CF vs Popularity baseline

| Metric | CF item-based | Popularity baseline |
|---|---|---|
| HitRate@1 | 0.2500 | 0.0125 |
| HitRate@5 | 0.4925 | 0.0250 |
| HitRate@10 | 0.6112 | 0.0425 |
| MRR | 0.3520 | 0.0186 |

## Temporal split (train quá khứ → test tương lai)

| Metric | KHÔNG rò rỉ (train lại) | Có rò rỉ (tham khảo) |
|---|---|---|
| Recall@1 | 0.0496 | 0.0809 |
| Recall@5 | 0.1746 | 0.2697 |
| Recall@10 | 0.2716 | 0.4083 |
| NDCG@10 | 0.2740 | 0.4280 |
| MAP | 0.1427 | 0.2640 |

*Cột **KHÔNG rò rỉ** train lại item_sim CHỈ trên phần quá khứ của mọi user (held-out không tham gia đồng-xuất-hiện) — đây là con số đáng tin để báo cáo. Cột có rò rỉ dùng cf_model train trên TOÀN bộ tương tác nên lạc quan quá mức.*

*Lưu ý: interactions.csv không có timestamp -> temporal split dùng thứ tự dòng làm proxy thời gian (đã nêu giả định trong itlr/eval/cf_eval.py). Leave-one-out ở trên dùng cf_model gốc nên CŨNG có rò rỉ — diễn giải thận trọng, ưu tiên cột không rò rỉ.*