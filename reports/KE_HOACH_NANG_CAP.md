# KẾ HOẠCH NÂNG CẤP KHÓA LUẬN
## Hệ thống Gợi ý & Chatbot Học liệu CNTT — Tầng "Kỹ sư CNTT Xuất sắc / BigTech-caliber"

> Tài liệu này mô tả đầy đủ kế hoạch nâng cấp project từ "một hệ thống chạy được" thành "một đồ án
> nghiên cứu–kỹ thuật có đóng góp đo được, theo đúng cách các team Search/Recommender ở các công ty
> công nghệ hàng đầu xây dựng và đánh giá hệ thống". Mục tiêu: đạt điểm Xuất sắc cao nhất hội đồng.

---

## PHẦN 0 — TẠI SAO CẦN NÂNG CẤP (Bối cảnh & chẩn đoán)

### 0.1. Hiện trạng project

Hệ thống hiện tại **đã rất mạnh về mặt tích hợp công nghệ**:

- Truy hồi ngữ nghĩa bằng **Sentence Embeddings (E5-base)** + tăng tốc bằng **FAISS (ANN)**.
- **Cross-Encoder reranker** (BGE) làm tầng xếp hạng tinh.
- Kỹ thuật RAG hiện đại: **RAG-Fusion (Reciprocal Rank Fusion)**, **MMR**, **CRAG**.
- **Collaborative Filtering** item-based cho mục "Dành cho bạn".
- Cổng chặn câu hỏi ngoài lĩnh vực (off-topic gate).
- Một **web app thực tế** (`web/` — Express + TypeScript + PostgreSQL) với đăng nhập, khóa học,
  tiến độ học, chatbot.

### 0.2. Vì sao điểm CHƯA cao dù code mạnh

Hội đồng (và nhà tuyển dụng BigTech) **không chấm điểm "lắp ghép được thư viện xịn"**. Họ chấm
**phương pháp khoa học và tư duy kỹ sư hệ thống**. Bốn lỗ hổng hiện tại:

| Lỗ hổng | Hiện trạng | Mức nguy hiểm |
|---|---|---|
| **Đánh giá quá sơ sài** | Chỉ ~10 truy vấn gán nhãn tay, đo "category accuracy @top1" | 🔴 Chí mạng |
| **Chưa có đóng góp riêng** | Đang là tích hợp công nghệ SOTA, chưa chứng minh điều gì *của riêng đề tài* | 🔴 Phân biệt Giỏi/Xuất sắc |
| **Dữ liệu 100% synthetic** | Catalog sinh tự động | 🟠 Hội đồng chất vấn đầu tiên |
| **Chatbot/RAG chưa đo định lượng** | Chỉ test thủ công | 🟡 Điểm cộng dễ lấy |

### 0.3. Hai sự thật phải nói thẳng

1. **"Ứng dụng cho BigTech" nghĩa là gì?** — Một khóa luận sẽ KHÔNG được deploy thật ở Google/Meta.
   "BigTech-caliber" ở đây = **kiến trúc, phương pháp đánh giá và kỹ thuật phục vụ mô phỏng đúng
   chuẩn production**. Đây mới là thứ gây ấn tượng với cả giám khảo lẫn phỏng vấn sau này. Khi bảo vệ
   tuyệt đối **không tuyên bố quá** ("hệ thống của em dùng được ở BigTech") — sẽ bị bắt bẻ.

2. **Máy chỉ có CPU** — không train được model neural lớn (two-tower, fine-tune embedding cần GPU).
   NHƯNG đúng những thứ đẳng cấp nhất ngành lại chạy tốt trên CPU: **GBDT Learning-to-Rank**,
   **off-policy evaluation**, **latency engineering**. Đây không phải "đồ thay thế rẻ tiền" — chúng
   là công cụ mà team ranking BigTech dùng thật hằng ngày.

### 0.4. Điều thật sự nâng tầm (khác với "thêm nhiều tính năng")

> Kiến trúc **multi-stage ranking** rõ ràng + đánh giá có **đối chứng/counterfactual** + kỹ thuật
> **serving đo được (latency/scale)** + **MLOps tái lập** + đóng góp được chứng minh bằng **kiểm định
> thống kê**.

Thêm tính năng KHÔNG làm đồ án đẳng cấp hơn. **Độ sâu thực thi + sự nghiêm ngặt khoa học** mới làm được.

---

## PHẦN 1 — KIẾN TRÚC: 9 TRỤ CỘT NÂNG CẤP

Sơ đồ tổng quan thứ tự thực hiện:

```
   [B] Khung đánh giá + Nhãn vàng  ──► nền tảng cho mọi đo lường
            │
            ▼
   [A] Kiến trúc Multi-Stage Ranking ──► xương sống "production"
            │
            ▼
   [C] Learning-to-Rank (đóng góp chính)
            │
            ▼
   [D] Off-Policy Evaluation (WOW factor)
            │
            ▼
   [E] Serving & Scalability ──┐ (làm song song được)
                               │
   [H] Chatbot/RAG eval  ──────┤ (điểm cộng)
   [I] Dữ liệu thật      ──────┘
            │
            ▼
   [F] A/B online  +  [G] MLOps/CI ──► chốt tầng production
```

---

## TRỤ CỘT A — KIẾN TRÚC MULTI-STAGE RANKING ⭐⭐
### (Xương sống "production-grade")

**Ý tưởng cốt lõi:** Mọi hệ recommender quy mô lớn (YouTube, Google Search, Meta Feed) đều dùng
**phễu xếp hạng nhiều tầng** — không thể chấm điểm tinh vi cho hàng triệu item, nên phải lọc dần:
nhiều ứng viên rẻ tiền → ít ứng viên đắt tiền. Hệ hiện tại đã *ngầm* có cấu trúc này; việc của ta là
**chính thức hóa, đặt tên, và đánh giá riêng từng tầng**. Đây là phần khiến đồ án "nói được ngôn ngữ
của ngành".

### Bốn tầng:

| Tầng | Tên | Nhiệm vụ | Công nghệ (đã có) | Metric đo riêng |
|---|---|---|---|---|
| **Stage 0** | Candidate Generation | Lọc thô từ 50k → vài trăm, ưu tiên **không bỏ sót** | FAISS ANN + BM25 | **Recall@100, Recall@500** |
| **Stage 1** | L1 Ranking (nhẹ) | Thu hẹp pool bằng điểm hybrid rẻ | Hybrid score hiện tại | NDCG @ pool |
| **Stage 2** | L2 Re-ranking (nặng) | Xếp hạng tinh top ứng viên | **Learning-to-Rank** (Trụ cột C) + Cross-Encoder | NDCG@10, MAP, MRR (điểm cuối) |
| **Stage 3** | Re-ordering | Đa dạng hóa + luật nghiệp vụ | MMR + cold-start + lọc đã xem | Diversity, Coverage |

### Việc cần làm:
- Vẽ **sơ đồ kiến trúc** phễu 4 tầng (đưa vào báo cáo).
- Lập **bảng "chi phí vs chất lượng" từng tầng** (mỗi tầng tốn bao nhiêu ms, cải thiện metric bao nhiêu).
- Refactor nhẹ [recommender.py](../itlr/core/recommender.py) để mỗi tầng có thể **bật/tắt độc lập**
  (phục vụ ablation). Tái dùng `search_by_embedding`, `multi_query_search`, `recommend_for_user`.

### Vì sao gây ấn tượng:
Cho thấy bạn hiểu **tradeoff recall–precision–latency** ở quy mô lớn, không chỉ "gọi một hàm trả kết quả".

---

## TRỤ CỘT B — KHUNG ĐÁNH GIÁ KHOA HỌC + NHÃN VÀNG NGƯỜI GÁN ⭐⭐
### (Nền tảng của toàn bộ độ tin cậy)

Đây là chương "Thực nghiệm & Đánh giá" — **phần quyết định điểm nhất** của bất kỳ khóa luận nào về
recommender/IR.

### B1. Module metric chuẩn ngành — `itlr/eval/metrics.py`
Cài đặt sạch bằng numpy thuần (không thêm dependency nặng):
- **Precision@K** — trong K kết quả đầu, bao nhiêu phần liên quan.
- **Recall@K** — trong tất cả item liên quan, bắt được bao nhiêu phần trong top-K.
- **NDCG@K** (Normalized Discounted Cumulative Gain) — metric quan trọng nhất, thưởng cho việc xếp
  item liên quan lên cao, có tính đến mức độ liên quan (graded).
- **MAP** (Mean Average Precision), **MRR** (Mean Reciprocal Rank), **HitRate@K**.
- K ∈ {1, 3, 5, 10, 100}.

### B2. Bộ nhãn bán-tự-động (dùng để TRAIN/dev) — `data/eval/relevance_judgments.csv`
- 60–100 truy vấn trải đều 26 chuyên mục (mở rộng từ `EVAL_QUERIES` đang có).
- Nhãn **graded** sinh tự động từ catalog: item liên quan mức 2 nếu trùng cả category + topic, mức 1
  nếu chỉ trùng category, mức 0 nếu không.
- Script sinh: `scripts/eval/make_judgments.py`.

### B3. ⭐ BỘ NHÃN VÀNG DO NGƯỜI GÁN (dùng làm TEST set sạch) — `data/eval/human_judgments.csv`
**ĐÂY LÀ ĐIỂM BẢO VỆ THEN CHỐT — bắt buộc phải có.**

*Vấn đề "vòng tròn" (circularity):* Nếu chỉ dùng nhãn tự động (sinh từ "trùng category+topic") để vừa
huấn luyện vừa kiểm thử Learning-to-Rank, thì mô hình thực chất đang học lại đúng cái tín hiệu đã dùng
để tạo nhãn → kết quả đẹp một cách **giả tạo**. Giám khảo sắc sảo hỏi *"nhãn của em ở đâu ra?"* là
toàn bộ con số sụp đổ.

*Cách bịt:*
- **~200–300 cặp (query, item) do người gán tay** (liên quan / không) → dùng làm **TEST set**. Nhãn
  tự động ở B2 chỉ dùng để TRAIN.
- Đo **độ đồng thuận Cohen's Kappa** giữa nhãn tự động và nhãn người → chứng minh quy trình sinh nhãn
  tự động đáng tin.
- Kết quả: một **bộ benchmark gợi ý học liệu CNTT tiếng Việt có nhãn người gán** — đây chính là một
  **đóng góp dữ liệu thật**, rất hiếm và rất đáng giá.

### B4. Metric "beyond-accuracy" — `itlr/eval/diversity.py`
Vượt khỏi độ chính xác thuần túy (ít đồ án ĐH làm → tạo khác biệt rõ):
- **Coverage** — hệ gợi ý được bao nhiêu % catalog (tránh chỉ gợi vài item phổ biến).
- **Intra-list Diversity** — kết quả có đa dạng không (1 − cosine trung bình).
- **Novelty** — gợi ý có mới mẻ không (−log popularity).
- **Serendipity** — bất ngờ nhưng vẫn liên quan.
- **Gini / long-tail** — công bằng phơi bày item (fairness).

### B5. Kiểm định thống kê — `itlr/eval/significance.py`
- **Paired bootstrap + paired t-test + khoảng tin cậy 95%** trên hiệu số metric giữa các cấu hình.
- Mọi tuyên bố "A tốt hơn B" đều kèm **p-value** → khẳng định cải thiện có ý nghĩa thống kê, không
  phải may rủi. Đây là dấu hiệu của tư duy khoa học nghiêm túc.

### B6. Đánh giá Collaborative Filtering đúng cách — `itlr/eval/cf_eval.py`
- **Leave-one-out**: che 1 tương tác cuối của mỗi user, đo khả năng model gợi ý lại đúng item bị che.
- **Temporal split**: train trên quá khứ, test trên tương lai (đúng chuẩn production, tránh "rò rỉ
  tương lai").
- Tái dùng dữ liệu tương tác từ [generate_interactions.py](../itlr/data/generate_interactions.py) +
  hàm `recommend_for_user`.

### Bảng ABLATION (đầu ra quan trọng nhất của trụ cột này):

| Cấu hình | P@5 | R@5 | NDCG@10 | MAP | MRR |
|---|---|---|---|---|---|
| TF-IDF only | | | | | |
| BM25 only | | | | | |
| Hybrid lexical (TF-IDF + BM25) | | | | | |
| Embeddings (E5) | | | | | |
| + Cross-Encoder | | | | | |
| **+ RAG-Fusion + MMR (Full)** | | | | | |

→ Bảng này **chứng minh từng thành phần đóng góp bao nhiêu** — chính xác là thứ hội đồng muốn thấy.

---

## TRỤ CỘT C — ĐÓNG GÓP THUẬT TOÁN: LEARNING-TO-RANK ⭐⭐
### (Đóng góp chính của đề tài — CPU-friendly, chuẩn ngành)

**Bối cảnh:** Hiện các trọng số kết hợp tín hiệu (`SCORE_WEIGHTS`, `HYBRID_ITEM_WEIGHTS` trong
recommender.py) đều **chỉnh tay bằng cảm tính**. Đây là điểm yếu — không có cơ sở khoa học.

**Giải pháp:** Thay bằng mô hình **Learning-to-Rank** — cụ thể là **LambdaMART** (cài qua LightGBM
`lambdarank`). Đây *chính là* loại model mà rất nhiều team ranking ở BigTech dùng trong production
(GBDT ranker), nên vừa đẳng cấp vừa khả thi trên CPU.

### Việc cần làm:
- Trích **~15 đặc trưng** cho mỗi cặp (query, item): điểm TF-IDF, BM25, embedding similarity,
  cross-encoder score, category match, topic Jaccard, title overlap, type match, popularity,
  freshness (độ mới)...
- Huấn luyện LightGBM `lambdarank` trên nhãn TRAIN (B2), tối ưu trực tiếp NDCG.
- `scripts/eval/build_ltr.py` → lưu `artifacts/ltr.pkl`; tích hợp làm **Stage-2 scorer** (có cờ bật/tắt).

### Bằng chứng đóng góp (đây là phần ăn điểm):
- **Bảng so sánh LTR vs trọng số chỉnh tay** trên human test set (NDCG/MAP), kèm **kiểm định thống kê**.
- **Feature importance (SHAP)** — biểu đồ cho thấy tín hiệu nào quan trọng nhất khi xếp hạng → tính
  giải thích được (explainability).
- **Score calibration (reliability diagram)** — điểm số mô hình có phản ánh đúng xác suất liên quan không.

### Cách kể chuyện khi bảo vệ:
> "Đề tài học một hàm xếp hạng phi tuyến từ dữ liệu thay vì dùng heuristic chỉnh tay, và chứng minh
> nó vượt baseline có ý nghĩa thống kê."

---

## TRỤ CỘT D — ĐÁNH GIÁ COUNTERFACTUAL / OFF-POLICY ⭐⭐⭐
### (WOW factor — gần như không khóa luận VN nào làm)

**Đây là thứ đưa đồ án lên tầng BigTech thực sự.**

**Vấn đề:** Khi đổi thuật toán ranking, ta muốn biết "nếu triển khai thật thì tốt hơn bao nhiêu?".
Nhưng dữ liệu log cũ được sinh ra bởi *thuật toán cũ* — nếu chỉ đo naive sẽ bị **thiên lệch** (chỉ
thấy được phản hồi trên những item thuật toán cũ từng hiển thị). Đây là bài toán **off-policy
evaluation** — chuẩn vàng để đánh giá ranking offline ở Google, Meta, Netflix.

### Việc cần làm:
- Sinh log có **propensity score** (xác suất một item được hiển thị bởi policy cũ) — bổ sung "logging
  policy" vào [generate_interactions.py](../itlr/data/generate_interactions.py).
- Cài 3 estimator trong `itlr/eval/off_policy.py`:
  - **IPS** (Inverse Propensity Scoring) — hiệu chỉnh thiên lệch bằng nghịch đảo propensity.
  - **SNIPS** (Self-Normalized IPS) — giảm phương sai.
  - **Doubly Robust** — kết hợp mô hình reward + IPS, bền vững nhất.
- Ước lượng **không thiên lệch** reward/CTR của policy mới (LTR) so với policy cũ (heuristic) **chỉ từ
  log cũ**, kèm khoảng tin cậy.

### Vì sao cực kỳ nổi bật:
Off-policy evaluation là kiến thức **bậc cao** (thường ở luận văn thạc sĩ/tiến sĩ hoặc nội bộ BigTech).
Một khóa luận cử nhân làm được điều này một cách đúng đắn là **dấu hiệu rõ ràng của đẳng cấp xuất sắc**.

---

## TRỤ CỘT E — SERVING & SCALABILITY ENGINEERING ⭐⭐
### (Thứ phỏng vấn kỹ sư BigTech hỏi nhiều nhất)

Đo lường và tối ưu **hiệu năng phục vụ** — kỹ năng kỹ sư production cốt lõi.

### Việc cần làm — `scripts/eval/bench_latency.py`:
- **Latency benchmark:** đo **p50 / p95 / p99** (phần trăm vị) cho từng tầng của phễu (Candidate Gen /
  L1 / L2 / Rerank), **QPS** (queries per second), và **memory footprint**.
- **So sánh FAISS ANN vs brute-force**: vẽ đường **recall–latency tradeoff** (ANN nhanh hơn nhưng mất
  bao nhiêu recall?).
- **Tối ưu & đo cải thiện:**
  - **Quantization** embedding (float32 → int8) → giảm bộ nhớ, đo ảnh hưởng tới p99 và recall.
  - **Caching** kết quả truy vấn phổ biến.
  - **Batch encoding**.
- Lập **bảng "Chất lượng vs Độ trễ vs Bộ nhớ"** → chứng minh hiểu tradeoff production.

### Vì sao gây ấn tượng:
Hầu hết đồ án chỉ quan tâm "kết quả đúng không". Đẳng cấp BigTech là quan tâm "**đúng + nhanh + rẻ +
mở rộng được**". Bảng p99 latency nói lên điều đó.

---

## TRỤ CỘT F — ĐÁNH GIÁ ONLINE + A/B TESTING ⭐
### (Qua web app đã có)

Web app `web/` đã ghi nhận enrollment / click / progress → có sẵn hạ tầng phản hồi thật.

### Việc cần làm:
- Logging **implicit feedback** + **A/B testing framework** (chia traffic ngẫu nhiên cho 2 cấu hình
  recommender — ví dụ heuristic vs LTR).
- **Guardrail metrics** (latency, error rate — đảm bảo không làm hỏng trải nghiệm) + **business
  metrics** (CTR, tỉ lệ ghi danh, thời gian xem).
- **Lưu ý thực tế:** đánh giá "online thật" cần lưu lượng người dùng theo thời gian. Nếu không kịp →
  trình bày như **thiết kế thí nghiệm A/B + mô phỏng**, và nối với off-policy evaluation (Trụ cột D)
  để ước lượng kết quả mà không cần người dùng thật.

---

## TRỤ CỘT G — MLOPS & REPRODUCIBILITY ⭐
### (Chuẩn kỹ thuật BigTech)

- **Experiment tracking với MLflow:** log mọi lần chạy đánh giá kèm tham số + metric + artifact →
  truy vết được, so sánh được giữa các thí nghiệm.
- **Model registry + versioning artifacts**; đảm bảo **một lệnh tái lập** mọi con số trong báo cáo.
- **CI cho evaluation** (GitHub Actions `.github/workflows/eval.yml`): mỗi thay đổi code tự động chạy
  bộ eval rút gọn + smoke tests → đảm bảo không gây thoái hóa chất lượng.
- Tận dụng **Docker đã có sẵn** (xem DEPLOY.md) để demo deploy thật; thêm **health/metrics endpoint**
  (observability — quan sát hệ thống đang chạy).

### Vì sao quan trọng:
**Khả năng tái lập (reproducibility)** là tiêu chuẩn vàng của khoa học. "Mọi con số trong báo cáo
chạy lại được bằng một lệnh" là điều hội đồng đánh giá rất cao và phỏng vấn BigTech coi là bắt buộc.

---

## TRỤ CỘT H — ĐÁNH GIÁ CHATBOT/RAG ĐỊNH LƯỢNG ⭐

- **Cổng off-topic:** lập bộ test gán nhãn (câu IT vs câu ngoài lĩnh vực — đã có sẵn nhiều ca trong
  lịch sử phát triển: "nấu phở", "ai là ca sĩ"...). Dùng `query_relevance_max` quét ngưỡng → đo
  **Precision / Recall / F1 + đường ROC** → biện minh con số ngưỡng `0.55` bằng dữ liệu thay vì cảm tính.
- **Chất lượng RAG (theo khung RAGAS):** đo **faithfulness** (câu trả lời có bám nguồn không),
  **answer relevancy**, **context precision/recall** trên một bộ Q&A mẫu, dùng LLM-as-judge (Claude).
- So sánh các phương pháp truy hồi cho chatbot: BM25 (cũ) vs Embeddings vs RAG-Fusion → bảng số liệu.

---

## TRỤ CỘT I — DỮ LIỆU THẬT ⭐
### (Chống chất vấn "dữ liệu giả")

- Nạp một **dataset thật** (Kaggle: "Coursera Courses" / "Udemy Courses" — công khai, không cần crawl)
  vào pipeline; viết adapter về schema hiện tại; rebuild artifacts.
- Viết mục **đối chứng phân phối** synthetic vs thật (độ dài mô tả, phân bố category, từ vựng) → biện
  luận tính đại diện của dữ liệu sinh.
- Kết quả: **vô hiệu hóa câu hỏi công kích số 1** của hội đồng về dữ liệu.

---

## PHẦN 2 — DANH SÁCH FILE SẼ TẠO / SỬA

| Nhóm | File | Trạng thái |
|---|---|---|
| Eval core | `itlr/eval/{metrics,diversity,significance,cf_eval,off_policy}.py` | Mới |
| Đóng góp | `scripts/eval/build_ltr.py`, `artifacts/ltr.pkl` | Mới |
| Chạy thực nghiệm | `scripts/eval/{make_judgments,run_evaluation,eval_offtopic,bench_latency}.py` | Mới |
| Dữ liệu test | `data/eval/{relevance_judgments,human_judgments,offtopic_testset}.csv` | Mới |
| Kiến trúc/serving | sửa nhẹ `itlr/core/recommender.py` (cờ tầng + LTR scorer), `web/src` (A/B + log) | Sửa |
| MLOps | `mlruns/` (MLflow), `.github/workflows/eval.yml`, metrics endpoint | Mới |
| Báo cáo | `reports/{results.csv,tables.md,EVALUATION.md,figures/*.png}` | Mới |

**Tái dùng (không viết lại):** `search_by_query`, `search_by_embedding`, `multi_query_search`,
`recommend_for_user`, `query_relevance_max`, `EVAL_QUERIES`, dữ liệu tương tác đã sinh, FAISS index,
cấu hình Docker.

---

## PHẦN 3 — THỨ TỰ THỰC HIỆN & LÝ DO

1. **B** (metric + nhãn vàng) — nền cho mọi đo lường. Nhãn vàng B3 là gốc của độ tin cậy.
2. **A** (chính thức hóa multi-stage) — narrative xương sống, đo từng tầng.
3. **C** (LTR L2 ranker) — đóng góp chính, dùng nhãn từ B.
4. **D** (off-policy eval) — WOW factor, dùng log + so policy C vs heuristic.
5. **E** (serving/latency) — kỹ thuật production, độc lập, làm song song được.
6. **H + I** (chatbot eval + dữ liệu thật) — điểm cộng.
7. **F + G** (A/B online + MLOps/CI) — chốt tầng production.

**Ước lượng thời gian:** ~3–5 tuần làm tập trung (trên CPU).
**Lõi tạo khác biệt (nếu phải cắt giảm):** giữ bằng mọi giá **A + B + C + D + E**.

---

## PHẦN 4 — ĐỊNH VỊ KHI BẢO VỆ
### (Dùng ngôn ngữ nghiên cứu/kỹ sư, KHÔNG nói "em dùng thư viện X")

Câu định vị mẫu để mở đầu phần trình bày:

> "Đề tài xây một hệ gợi ý học liệu CNTT theo **kiến trúc multi-stage ranking chuẩn production**, kèm
> một **bộ benchmark có nhãn người gán**, được đánh giá bằng các **metric chuẩn ngành** cùng **kiểm
> định thống kê** và **off-policy evaluation** (chuẩn vàng đo ranking trong công nghiệp). Đề tài chứng
> minh mô hình **Learning-to-Rank** vượt heuristic chỉnh tay một cách có ý nghĩa thống kê; đồng thời
> **đo và tối ưu latency/scalability**, và đóng gói quy trình **MLOps tái lập** kèm **A/B testing**."

So sánh hai cách nói cùng một việc:

| ❌ Cách nói tầm thường | ✅ Cách nói đẳng cấp |
|---|---|
| "Em dùng thư viện sentence-transformers" | "Tầng candidate generation dùng truy hồi ngữ nghĩa, đo Recall@500" |
| "Em chỉnh trọng số cho kết quả đẹp" | "Em học hàm xếp hạng bằng LambdaMART, chứng minh vượt baseline với p < 0.05" |
| "Hệ thống chạy nhanh" | "p99 latency là X ms ở QPS = Y, sau quantization giảm bộ nhớ Z%" |
| "Em test thử thấy đúng" | "Đánh giá trên 250 cặp nhãn người gán, Cohen's Kappa = 0.8" |

---

## PHẦN 5 — CÁCH KIỂM CHỨNG (Verification)

1. `python scripts/eval/run_evaluation.py` → sinh `reports/results.csv` + bảng ablation per-stage +
   biểu đồ, chạy không lỗi.
2. NDCG/MAP trên **human test set** (B3): cấu hình Full > baseline, có **p-value** (B5) + Cohen's
   Kappa hợp lệ.
3. `build_ltr.py` → bảng LTR > trọng số tay (kèm kiểm định) + biểu đồ SHAP + reliability diagram.
4. `off_policy.py` → IPS/SNIPS/DR ước lượng reward policy LTR vs heuristic + khoảng tin cậy.
5. `bench_latency.py` → bảng p50/p95/p99 + QPS + memory mỗi tầng; đường FAISS vs brute-force.
6. `eval_offtopic.py` → bảng Precision/Recall/F1 + ROC; điểm RAGAS faithfulness trên bộ Q&A mẫu.
7. MLflow log đủ các run; CI workflow xanh; Docker chạy được + metrics endpoint phản hồi.
8. `python -m pytest` vẫn pass (không phá vỡ hành vi hiện tại); mọi số trong `reports/EVALUATION.md`
   tái lập được bằng đúng các lệnh trên.

---

## PHẦN 6 — RỦI RO & GIỚI HẠN (nên chủ động nêu trong báo cáo)

| Rủi ro / giới hạn | Cách xử lý / biện luận |
|---|---|
| Dữ liệu gốc là synthetic | Có Trụ cột I (dữ liệu thật đối chứng) + nhãn người gán (B3) |
| Không có GPU → không fine-tune neural | Chọn đúng tập kỹ thuật CPU mà BigTech dùng thật (GBDT, off-policy) |
| Không có lưu lượng người dùng thật | A/B trình bày dạng thiết kế + mô phỏng, nối off-policy (D) |
| LTR là kỹ thuật đã biết, không "mới" | Đủ cho khóa luận cử nhân; điểm mạnh là **đánh giá nghiêm ngặt + benchmark có nhãn người** |
| Nguy cơ "vòng tròn" nhãn | Bịt bằng human test set tách biệt + Cohen's Kappa (B3) |

---

*Tài liệu kế hoạch — chưa triển khai code. Khi bạn đồng ý bắt đầu, thứ tự khởi động đề xuất là
Trụ cột B → A → C → D → E.*
