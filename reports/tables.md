# Kết quả đánh giá — Bảng ablation per-stage (truy vấn sạch)

*Số truy vấn: 12. Metric macro-average trên nhãn bán-tự-động (`data/eval/relevance_judgments.csv`).*

> Lưu ý: nhãn tự động ≈ khớp topic chính xác nên các cấu hình từ vựng (TF-IDF/BM25) gần chạm trần — bảng sạch chủ yếu xác nhận **recall** của tầng sinh ứng viên. Khác biệt phương pháp thể hiện rõ ở bảng **truy vấn nhiễu** (`tables_noisy.md`) và trên **nhãn người gán** (`evaluate_human.py`). Cấu hình **Full** thêm MMR -> đánh đổi một phần độ chính xác lấy **đa dạng** (xem mục beyond-accuracy); **+ Cross-Encoder** là mốc độ-chính-xác cao nhất.

## Bảng ablation (headline metrics)

| Cấu hình | P@5 | R@5 | NDCG@10 | MAP | MRR | R@100 |
|---|---|---|---|---|---|---|
| TF-IDF only | 0.1000 | 0.0034 | 0.1025 | 0.0063 | 0.3004 | 0.0196 |
| BM25 only | 0.1500 | 0.0046 | 0.1060 | 0.0063 | 0.3904 | 0.0183 |
| Hybrid lexical (TF-IDF+BM25) | 0.1500 | 0.0046 | 0.1119 | 0.0066 | 0.4124 | 0.0183 |
| Embeddings (E5) | 0.2500 | 0.0071 | 0.1747 | 0.0645 | 0.3449 | 0.1033 |
| **+ L1 hybrid signals** | 0.2500 | 0.0071 | 0.1760 | 0.0648 | 0.3449 | 0.1033 |
| + Cross-Encoder | 0.2500 | 0.0071 | 0.1760 | 0.0648 | 0.3449 | 0.1033 |
| + RAG-Fusion + MMR (Full) | 0.0500 | 0.0021 | 0.0423 | 0.0348 | 0.1789 | 0.0593 |

## Kiểm định thống kê — **+ L1 hybrid signals** (tốt nhất) vs baseline (NDCG@10)

| Baseline | NDCG@10 (base) | + L1 hybrid signals − base | CI 95% | p (t-test) | p (bootstrap) | Có ý nghĩa? |
|---|---|---|---|---|---|---|
| TF-IDF only | 0.1025 | +0.0735 | [-0.0038, 0.1492] | 0.1023 | 0.0642 | — |
| BM25 only | 0.1060 | +0.0700 | [-0.0050, 0.1452] | 0.1131 | 0.077 | — |
| Hybrid lexical (TF-IDF+BM25) | 0.1119 | +0.0640 | [-0.0103, 0.1385] | 0.1365 | 0.0942 | — |
| Embeddings (E5) | 0.1747 | +0.0013 | [0.0000, 0.0038] | 0.3388 | 0.6822 | — |
| + Cross-Encoder | 0.1760 | +0.0000 | [0.0000, 0.0000] | 1 | 1 | — |
| + RAG-Fusion + MMR (Full) | 0.0423 | +0.1337 | [0.0538, 0.2141] | 0.01028 | 0.0002 | ✅ p<0.05 |

## Beyond-accuracy (cấu hình Full, top-10)

| Metric | Giá trị |
|---|---|
| Coverage | 0.0215 |
| Gini | 0.9835 |
| ILD | 0.7756 |
