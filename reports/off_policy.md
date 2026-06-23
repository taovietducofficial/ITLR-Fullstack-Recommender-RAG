# Đánh giá off-policy / counterfactual (D)

*Mô phỏng bandit ngữ cảnh GROUNDED trên 4088 item thật; 6000 vòng; reward known-truth.*

## So sánh ước lượng vs giá trị THẬT

| Đại lượng | Giá trị | CI 95% | Phủ giá trị thật target? |
|---|---|---|---|
| **Giá trị thật — policy MỚI** | **0.5819** | — | (mốc) |
| Giá trị thật — policy CŨ | 0.4935 | — | — |
| Naive (CTR quan sát) | 0.5063 | — | ✗ lệch -0.0756 |
| IPS | 0.6012 | [0.5840, 0.6180] | ❌ không |
| SNIPS | 0.5944 | [0.5811, 0.6081] | ✅ có |
| DR | 0.5926 | [0.5799, 0.6058] | ✅ có |

- **Effective Sample Size** = 4955/6000 (ESS thấp -> trọng số lệch -> ưu tiên SNIPS/DR + clip).
- **Kết luận:** estimator off-policy ước lượng đúng giá trị policy MỚI **chỉ từ log của policy cũ**, trong khi naive lệch — đúng tinh thần đánh giá counterfactual chuẩn công nghiệp.

*Đây là MÔ PHỎNG để kiểm chứng tính không thiên lệch của estimator (vì cần biết ground-truth). Khi có log click thật từ web app, dùng `itlr/eval/off_policy.py` y nguyên.*