# Benchmark độ trễ & mở rộng (Trụ cột E)

*12 truy vấn × 30 lần lặp, 1 luồng, CPU. Đo bằng time.perf_counter().*

### Độ trễ từng tầng của phễu

| Thành phần | p50 (ms) | p95 (ms) | p99 (ms) | mean (ms) | QPS (1 luồng) |
|---|---|---|---|---|---|
| Stage0 Candidate Gen (embedding+ANN) | 44.06 | 47.70 | 49.17 | 44.37 | 22.5 |
| Stage1 L1 ranking | 76.20 | 86.95 | 88.94 | 76.99 | 13.0 |
| Stage2 L2 rerank (cross-encoder, pool=48) | 9759.56 | 14657.98 | 25505.33 | 10338.81 | 0.1 |
| Stage2 L2 rerank (LightGBM LTR, pool=48) | 131.53 | 231.59 | 320.19 | 144.16 | 6.9 |
| Stage3 MMR reorder | 1.16 | 2.34 | 2.57 | 1.34 | 747.9 |
| Full (no rerank) | 240.88 | 304.90 | 344.22 | 247.75 | 4.0 |

### FAISS ANN vs Brute-force (Stage-0)

| Thành phần | p50 (ms) | p95 (ms) | p99 (ms) | mean (ms) | QPS (1 luồng) |
|---|---|---|---|---|---|
| FAISS ANN | 58.70 | 85.37 | 93.53 | 61.33 | 16.3 |
| Brute-force (matmul) | 60.35 | 83.20 | 89.80 | 62.40 | 16.0 |

> Ở quy mô 4k×384 trên CPU, Stage-0 bị **chi phí ENCODE truy vấn (SentenceTransformer ~200ms) chi phối**, nên FAISS ANN vs brute-force gần ngang nhau (~**1.02×**): matmul 4k vector vẫn rẻ. Lợi thế ANN (sublinear) chỉ bộc lộ khi N lớn hơn nhiều (hàng triệu) — đây là kết luận trung thực về tradeoff recall–latency ở quy mô hiện tại.

> **Cross-encoder là nút thắt cổ chai đuôi (p99 rất cao trên CPU)**; thay Stage-2 bằng **LightGBM LTR** rẻ hơn ~**74×** ở trung vị — đúng lý do production dùng GBDT ranker thay cross-encoder nặng (nối Trụ cột C↔E).

## Dấu chân bộ nhớ

| Thành phần | MB | Kích thước |
|---|---|---|
| embeddings (float32) | 6.3 | (4088, 384) |
| char n-gram matrix (sparse) | 15.7 | (4088, 21220) |
| ann_index.faiss (on disk) | 6.3 |  |
| retrieval_model.pkl (on disk) | 14.1 |  |
| embeddings.pkl (on disk) | 6.3 |  |
| Process RSS | 1148.0 |  |

*Hướng tối ưu (đã nêu trong kế hoạch): quantization embeddings float32->int8 (~4× giảm bộ nhớ), caching truy vấn phổ biến, batch encoding.*