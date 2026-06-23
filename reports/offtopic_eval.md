# Đánh giá cổng off-topic của chatbot (Trụ cột H)

*Bộ test: 40 câu (20 IT / 20 ngoài lĩnh vực). Tín hiệu cổng = `query_relevance_max`.*

- **AUC (ROC) = 0.9925**
- Điểm TB: IT = 0.736 · ngoài lĩnh vực = 0.335

| Ngưỡng | Precision | Recall | F1 |
|---|---|---|---|
| 0.55 (hiện tại) | 0.947 | 0.900 | 0.923 |
| **0.440 (tối ưu F1)** | 0.952 | 1.000 | 0.976 |

### Bảng quét ngưỡng (trích)
| Ngưỡng | P | R | F1 |
|---|---|---|---|
| 0.40 | 0.833 | 1.000 | 0.909 |
| 0.45 | 0.952 | 1.000 | 0.976 |
| 0.50 | 0.950 | 0.950 | 0.950 |
| 0.55 | 0.947 | 0.900 | 0.923 |
| 0.60 | 0.944 | 0.850 | 0.895 |
| 0.65 | 1.000 | 0.750 | 0.857 |
| 0.70 | 1.000 | 0.700 | 0.824 |

*Kết luận: ngưỡng cổng được biện minh bằng **dữ liệu** (tối ưu F1 + AUC) thay vì cảm tính. Mở rộng bộ test -> con số đáng tin hơn.*