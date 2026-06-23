# Kết quả đánh giá — Bảng ablation per-stage (truy vấn NHIỄU (bỏ dấu + lỗi gõ))

*Số truy vấn: 10. Metric macro-average trên nhãn bán-tự-động (`data/eval/relevance_judgments.csv`).*

> Truy vấn bị **bỏ dấu + chèn lỗi gõ**, nhãn liên quan giữ nguyên. Bảng này đo **độ bền** của hệ trước input tiếng Việt đời thực: khớp từ vựng chính xác (TF-IDF/BM25) sụt mạnh, kênh ngữ nghĩa + char n-gram bỏ dấu giữ được chất lượng.

## Bảng ablation (headline metrics)

| Cấu hình | P@5 | R@5 | NDCG@10 | MAP | MRR | R@100 |
|---|---|---|---|---|---|---|
| TF-IDF only | 0.1400 | 0.0017 | 0.1154 | 0.0473 | 0.3258 | 0.0321 |
| BM25 only | 0.1800 | 0.0027 | 0.1701 | 0.0568 | 0.3686 | 0.0466 |
| Hybrid lexical (TF-IDF+BM25) | 0.2200 | 0.0034 | 0.1400 | 0.0542 | 0.2898 | 0.0338 |
| Embeddings (E5) | 0.2800 | 0.0041 | 0.2266 | 0.2253 | 0.3637 | 0.0751 |
| **+ L1 hybrid signals** | 0.3200 | 0.0048 | 0.2431 | 0.2135 | 0.4240 | 0.0771 |
| + Cross-Encoder | 0.3200 | 0.0048 | 0.2431 | 0.2135 | 0.4240 | 0.0771 |
| + RAG-Fusion + MMR (Full) | 0.1200 | 0.0014 | 0.1215 | 0.2183 | 0.3601 | 0.0888 |

## Kiểm định thống kê — **+ L1 hybrid signals** (tốt nhất) vs baseline (NDCG@10)

| Baseline | NDCG@10 (base) | + L1 hybrid signals − base | CI 95% | p (t-test) | p (bootstrap) | Có ý nghĩa? |
|---|---|---|---|---|---|---|
| TF-IDF only | 0.1154 | +0.1277 | [0.0018, 0.2543] | 0.093 | 0.047 | — |
| BM25 only | 0.1701 | +0.0730 | [-0.0635, 0.2095] | 0.3446 | 0.2976 | — |
| Hybrid lexical (TF-IDF+BM25) | 0.1400 | +0.1031 | [-0.0378, 0.2430] | 0.2042 | 0.151 | — |
| Embeddings (E5) | 0.2266 | +0.0164 | [-0.0167, 0.0550] | 0.4071 | 0.34 | — |
| + Cross-Encoder | 0.2431 | +0.0000 | [0.0000, 0.0000] | 1 | 1 | — |
| + RAG-Fusion + MMR (Full) | 0.1215 | +0.1216 | [0.0169, 0.2288] | 0.06397 | 0.0212 | — |

## Beyond-accuracy (cấu hình Full, top-10)

| Metric | Giá trị |
|---|---|
| Coverage | 0.0181 |
| Gini | 0.9858 |
| ILD | 0.7006 |
