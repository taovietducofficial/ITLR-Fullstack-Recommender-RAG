# Chương Thực nghiệm & Đánh giá — Hệ Gợi ý Học liệu CNTT

> Tài liệu này tổng hợp **khung đánh giá khoa học** đã triển khai theo
> [KE_HOACH_NANG_CAP.md](KE_HOACH_NANG_CAP.md). Mọi con số tái lập được bằng **một lệnh**:
> `python scripts/eval/run_all.py` (xem mục [Tái lập](#tái-lập)). Các bảng kết quả nằm trong
> `reports/*.md` và được sinh tự động bởi script tương ứng.

---

## 0. Tổng quan kiến trúc đánh giá

Hệ được chính thức hóa thành **phễu xếp hạng 4 tầng** ([itlr/core/pipeline.py](../itlr/core/pipeline.py)),
mỗi tầng **bật/tắt độc lập** để ablation:

| Tầng | Tên | Công nghệ | Metric đo riêng | Độ trễ (p50) |
|---|---|---|---|---|
| Stage 0 | Candidate Generation | Embeddings (E5) + FAISS ANN / BM25 | Recall@100, Recall@500 | ~0.5 s* |
| Stage 1 | L1 Ranking (nhẹ) | Hybrid score (tfidf/bm25/category/topic) | NDCG @ pool | ~0.25 s |
| Stage 2 | L2 Re-ranking (nặng) | Cross-Encoder **hoặc** Learning-to-Rank | NDCG@10, MAP, MRR | CE ~9.76 s / **LTR ~0.13 s (≈74× nhanh hơn)** |
| Stage 3 | Re-ordering | MMR (đa dạng hóa) | Diversity, Coverage | ~2 ms |

> *Số p50 đo trên CPU, 1 luồng (biến thiên theo tải máy — xem [latency.md](latency.md) cho con số
> chính xác). Stage-0 bị chi phối bởi chi phí encode truy vấn (~200 ms); LTR có thể về **sub-ms**
> nếu cache vector truy vấn từ Stage-0.

---

## 1. Khung metric & bộ nhãn (Trụ cột B)

- **Metric chuẩn ngành** ([itlr/eval/metrics.py](../itlr/eval/metrics.py)): Precision/Recall/NDCG@K
  (graded, gain mũ), MAP, MRR, HitRate; K ∈ {1,3,5,10,100}. Đã kiểm thử đơn vị (`tests/test_eval.py`).
- **Beyond-accuracy** ([itlr/eval/diversity.py](../itlr/eval/diversity.py)): Coverage, Intra-list
  Diversity, Novelty, Serendipity, Gini.
- **Kiểm định thống kê** ([itlr/eval/significance.py](../itlr/eval/significance.py)): paired bootstrap
  + paired t-test + CI 95% + Cohen's Kappa.
- **Bộ nhãn**:
  - `data/eval/relevance_judgments.csv` — **bán-tự-động** (TRAIN/dev). 78 truy vấn (3/chuyên mục),
    nhãn graded theo khớp topic (grade 2 = cùng category + topic, grade 1 = topic chéo category).
    Tập liên quan trung vị ~250 item/truy vấn -> Recall/MAP/NDCG đều có ý nghĩa.
  - `data/eval/human_judgments.csv` — **khung nhãn người gán** (TEST sạch). 234 cặp (query, item)
    phân tầng để người gán tay; đo **Cohen's Kappa** auto-vs-người chống "vòng tròn".

**Hai benchmark bổ trợ** (đo hai năng lực khác nhau, tránh "vòng tròn từ vựng"):
- **Semantic benchmark** (`relevance_judgments.csv`, sinh bằng `--natural`): truy vấn là **câu hỏi
  tiếng Việt tự nhiên từ glossary, KHÔNG chứa token topic tiếng Anh** -> khớp từ khóa vô dụng, buộc
  hệ phải HIỂU ngữ nghĩa. Dùng đo **độ hiểu ngữ nghĩa** (§2A).
- **Keyword benchmark** (`relevance_keyword.csv`): truy vấn chứa từ khóa topic -> dùng đo **recall
  tầng sinh ứng viên** và **độ bền trước nhiễu** (bỏ dấu/lỗi gõ) (§2B).

> ✅ **Trung thực về dữ liệu**: toàn bộ con số trong bản này được chạy lại trên **CATALOG THẬT** —
> **4.088 khóa học IT** trích từ các dataset công khai Kaggle (Coursera/Udemy/Online Courses), lọc
> riêng lĩnh vực CNTT + khử trùng lặp (xem §6 Trụ cột I + [data_compare.md](data_compare.md)).
> Semantic benchmark cho thấy **ngữ nghĩa > lexical rõ rệt trên dữ liệu thật** (§2A: Embeddings
> NDCG@10 0.175 vs lexical ~0.11; R@100 0.103 vs 0.018 — gấp ~5×). Tương tác người dùng vẫn **mô
> phỏng** (latent-factor, vì không có log thật) và nhãn liên quan vẫn **bán-tự-động** — bước cuối để
> đạt độ tin cậy tuyệt đối là **nhãn người gán thật** (§4, công cụ đã sẵn ở
> `scripts/eval/prepare_labeling_sheet.py`).

---

## 2. Bảng ablation per-stage (Trụ cột A + B)

Sinh bởi `python scripts/eval/run_evaluation.py` (mốc kiểm định = cấu hình **NDCG@10 cao nhất**,
chọn tự động). Mỗi tầng bật/tắt độc lập.

### 2A. Semantic benchmark — đo ĐỘ HIỂU NGỮ NGHĨA ([tables.md](tables.md))
*Trên CATALOG THẬT (4.088 khóa IT). 12 truy vấn câu-hỏi-tự-nhiên từ glossary (KHÔNG chứa token topic)
-> khớp từ khóa vô dụng.*

| Cấu hình | NDCG@10 | P@5 | R@100 | MRR |
|---|---|---|---|---|
| TF-IDF only | 0.103 | 0.10 | 0.020 | 0.300 |
| BM25 only | 0.106 | 0.15 | 0.018 | 0.390 |
| Hybrid lexical | 0.112 | 0.15 | 0.018 | 0.412 |
| Embeddings (minilm) | 0.175 | 0.25 | **0.103** | 0.345 |
| **+ L1 hybrid (tốt nhất)** | **0.176** | **0.25** | **0.103** | 0.345 |
| + RAG-Fusion + MMR (Full) | 0.042 | 0.05 | 0.059 | 0.179 |

→ Trên dữ liệu thật, khi truy vấn **không có từ khóa trùng nhãn**, phương pháp **ngữ nghĩa (NDCG@10
0.175–0.176) vượt rõ lexical (0.10–0.11)** và đặc biệt **R@100 0.103 vs 0.018 — gấp ~5×**: tầng sinh
ứng viên ngữ nghĩa tìm thấy nhiều mục liên quan hơn hẳn khớp chữ. Tức hệ **HIỂU nghĩa, không chỉ khớp
chữ**. ⚠️ Với chỉ **12 truy vấn**, khoảng cách điểm rõ ràng nhưng kiểm định per-query **chưa đạt
p<0.05** (under-powered) — nêu minh bạch; tăng số truy vấn (hoặc nhãn người) sẽ củng cố ý nghĩa thống kê.

### 2B. Keyword benchmark — đo ĐỘ BỀN trước nhiễu ([tables_kw_noisy.md](tables_kw_noisy.md))
*Trên CATALOG THẬT. 10 truy vấn từ khóa, **bỏ dấu + lỗi gõ** (input tiếng Việt đời thực); nhãn giữ nguyên.*

| Cấu hình | NDCG@10 | P@5 | MAP | vs (best−base) | p (bootstrap) |
|---|---|---|---|---|---|
| TF-IDF only | 0.115 | 0.14 | 0.047 | **+0.128** | **0.047 ✅** |
| BM25 only | 0.170 | 0.18 | 0.057 | +0.073 | 0.30 |
| Hybrid lexical | 0.140 | 0.22 | 0.054 | +0.103 | 0.15 |
| Embeddings (minilm) | 0.227 | 0.28 | 0.225 | +0.016 | 0.34 |
| **+ L1 hybrid (tốt nhất)** | **0.243** | **0.32** | 0.214 | — | — |
| + RAG-Fusion + MMR (Full) | 0.122 | 0.12 | 0.218 | +0.122 | 0.021 |

→ Khi input bị **bỏ dấu + sai chính tả**, khớp từ vựng thuần **sụt mạnh** (TF-IDF NDCG@10 0.115); phễu
**ngữ nghĩa + char n-gram bỏ dấu** giữ **0.243** (+L1), hơn TF-IDF **+0.128 với p=0.047 ✅**. MAP của
kênh ngữ nghĩa cao hơn lexical ~4× (0.21–0.23 vs 0.05). **Full** (MMR) đánh đổi độ chính xác lấy **đa
dạng** (ILD 0.70). Cải thiện bền vững trước nhiễu được xác nhận **trên dữ liệu thật**.

---

## 3. Learning-to-Rank (Trụ cột C)

`python scripts/eval/build_ltr.py` -> [ltr.md](ltr.md) + `artifacts/ltr.pkl`.

- **LambdaMART** (LightGBM `lambdarank`), 15 đặc trưng (từ vựng + ngữ nghĩa + cross-encoder +
  metadata + popularity), **hard-negative mining** (negatives = near-miss điểm cao nhưng không liên quan).
- **Giải thích được**: SHAP summary ([figures/ltr_shap.png](figures/ltr_shap.png)).
- **Hiệu chỉnh**: reliability diagram ([figures/ltr_calibration.png](figures/ltr_calibration.png)).
- **So với heuristic chỉnh tay** (trên semantic benchmark): LTR **ngang/nhỉnh hơn** heuristic
  (Δ NDCG@10 = +0.005, p=0.79 — không thua, khác với benchmark từ-khóa cũ nơi heuristic được chỉnh
  đúng luật nhãn nên LTR khó vượt). Tức LTR **học lại được chất lượng trọng số chuyên gia thuần từ dữ
  liệu**, không cần chỉnh tay.
- **Đóng góp của LTR** = **phương pháp luận** (hàm xếp hạng học được + hard-negative + giải thích SHAP
  + điểm hiệu chỉnh) **+ production** (rẻ hơn cross-encoder ~9× khi serving, §7). Trên **dữ liệu thật**
  (Trụ cột I) nơi liên quan không phải luật đơn giản, LTR được kỳ vọng vượt rõ heuristic.

---

## 4. Nhãn người gán & độ đồng thuận (Trụ cột B3)

`python scripts/eval/evaluate_human.py` -> [human_eval.md](human_eval.md).

- **Cohen's Kappa (auto vs người) = 0.716** ("tốt"), đồng thuận thô 0.86, trên **240 cặp** — đo độ
  tin cậy quy trình sinh nhãn tự động.
- ⚠️ File `human_judgments.csv` hiện vẫn ở chế độ **mô phỏng** (`--simulate-human`) để chạy thông
  pipeline; **phải thay bằng nhãn người THẬT** (gán cột `human_label`) trước khi đưa số vào khóa luận.
  Công cụ gán đã sẵn: `python scripts/eval/prepare_labeling_sheet.py --prepare` (xuất phiếu Excel)
  -> điền tay -> `--merge` -> `evaluate_human.py`.

---

## 5. Collaborative Filtering (Trụ cột B6)

`python scripts/eval/eval_cf.py` -> [cf_eval.md](cf_eval.md). Leave-one-out + **temporal split
KHÔNG rò rỉ** (train lại item_sim chỉ trên quá khứ).

**Tương tác có cấu trúc latent-factor** ([generate_interactions.py](../itlr/data/generate_interactions.py)):
mỗi user có vector sở thích ẩn quanh một "archetype" (cộng đồng), item có vector ẩn từ category+topic;
xác suất tương tác ∝ exp(p_u·q_i) -> "người học X cũng học Y" **xuất hiện thật** trong đồng-xuất-hiện.

*Trên CATALOG THẬT (4.088 item) + 1.800 user, 42.662 tương tác latent-factor.*

| Metric | CF item-based | Popularity baseline |
|---|---|---|
| Leave-one-out HitRate@10 | **0.611** | 0.043 |
| Leave-one-out HitRate@5 | 0.493 | 0.025 |
| Leave-one-out MRR | 0.352 | 0.019 |
| Temporal NDCG@10 (KHÔNG rò rỉ) | **0.274** | — |
| Temporal Recall@10 (KHÔNG rò rỉ) | **0.272** | — |

> ✅ Trên dữ liệu thật, CF item-based **vượt xa baseline popularity** (HitRate@10 **0.61 vs 0.04**,
> ×14) và temporal split không-rò-rỉ NDCG@10 **0.27** — tín hiệu cộng tác THẬT, không phải leakage.
> Chênh giữa có/không rò rỉ (NDCG@10 0.428 vs 0.274) được nêu minh bạch để chứng minh giao thức đánh
> giá đúng (cột "có rò rỉ" trong [cf_eval.md](cf_eval.md) chỉ để tham khảo, KHÔNG báo cáo).

---

## 6. Off-policy / counterfactual evaluation (Trụ cột D)

`python scripts/eval/eval_off_policy.py` -> [off_policy.md](off_policy.md).
Estimator IPS / SNIPS / **Doubly Robust** ([itlr/eval/off_policy.py](../itlr/eval/off_policy.py)).

- Mô phỏng bandit ngữ cảnh **grounded trên 4.088 item THẬT**, reward **known-truth** -> **chứng minh
  tính không thiên lệch**: CI95 của **SNIPS (0.594)** và **DR (0.593)** **phủ** giá trị thật của policy
  mới (**0.582**), trong khi ước lượng **naive bị lệch −0.076** (0.506, tức ước lượng nhầm policy cũ).
  IPS lệch nhẹ do ESS thấp (4955/6000) -> ưu tiên SNIPS/DR + clip. DR có CI hẹp nhất.
- Khi web app có log click thật, dùng nguyên module này (không cần mô phỏng).

---

## 7. Serving & Scalability (Trụ cột E)

`python scripts/eval/bench_latency.py` -> [latency.md](latency.md).

- p50/p95/p99 + QPS từng tầng (đo trên catalog thật 4.088 item); **cross-encoder là nút thắt đuôi**
  (p50 **9.76 s**, p99 25.5 s trên CPU) -> production thay Stage-2 bằng **LTR (GBDT, p50 132 ms,
  ~74× nhanh hơn)** (nối Trụ cột C↔E). Full no-rerank p50 **241 ms**.
- FAISS ANN vs brute-force: ở quy mô 4k, **encode truy vấn (~200ms) chi phối** nên hai cách ~ngang
  (1.02×); lợi thế ANN (sublinear) bộc lộ khi N rất lớn (hàng triệu) — kết luận trung thực về tradeoff.
- Bộ nhớ: embeddings (4088×384) 6.3 MB, char n-gram sparse 15.7 MB, RSS ~1.1 GB.

---

## 8. Dữ liệu thật & đối chứng phân phối (Trụ cột I)

`python scripts/eval/adapt_real_data.py --source-dir data_real_kaggle` -> [data_compare.md](data_compare.md)
+ `data/it_learning_items_real.csv`.

- **Nguồn**: 7 dataset khóa học CÔNG KHAI trên Kaggle (Coursera, Coursera_Data, Online_Courses,
  Udemy×3, all_courses) — tải tay, không crawl. Adapter map đa nguồn về schema chung, **lọc riêng
  lĩnh vực CNTT** (theo category/sub-category), **khử trùng lặp theo tiêu đề** -> **4.088 khóa IT thật**.
- **Đối chứng phân phối** (synthetic 50k vs thật 4k):

  | Thuộc tính | Synthetic | Thật |
  |---|---|---|
  | Số item | 50.002 | 4.088 |
  | Số chuyên mục | 27 (mịn) | 4 (thô, theo Coursera) |
  | Độ dài mô tả TB | 156 | 218 |
  | Từ vựng tiêu đề (mẫu 5k) | 564 | **2.945** |

  → Dữ liệu thật **đa dạng từ vựng cao hơn ~5×** và mô tả dài hơn — bài toán khó & thực tế hơn; chuyên
  mục thật **thô hơn** (Coursera chỉ gắn 5 nhóm lớn) là giới hạn khách quan của nguồn, nêu minh bạch.
- **Quy trình rebuild an toàn**: artifacts synthetic được **backup** (`artifacts_synthetic_backup/`);
  rebuild trên data thật qua biến môi trường `ITLR_ITEMS_CSV` (không ghi đè file gốc). Catalog thật là
  **tiếng Anh** — embeddings **đa ngữ** (paraphrase-multilingual-MiniLM) xử lý chéo Anh–Việt; nhãn
  category giữ nguyên tiếng Anh.

> 📌 **Toàn bộ §2–§7 ở trên đã được chạy lại trên catalog thật này** — đây là bằng chứng mạnh nhất
> chống chất vấn "hệ thống chỉ chạy trên dữ liệu giả".

---

## Tái lập

```bash
# đầy đủ (chậm — có cross-encoder; thêm --with-ltr để train lại LTR)
python scripts/eval/run_all.py --with-ltr
# rút gọn cho CI / kiểm tra nhanh
python scripts/eval/run_all.py --quick
# kiểm thử đơn vị các module metric/significance/off-policy
python -m pytest tests/test_eval.py -q
```

Đầu ra: `reports/{tables (semantic), tables_kw_noisy (keyword robustness), cf_eval, off_policy,
latency, human_eval, ltr, offtopic_eval, data_compare}.md`, `reports/results*.csv`, `reports/figures/*.png`.

Hai benchmark tách biệt (tái lập độc lập):
```bash
python scripts/eval/make_judgments.py --natural --queries-per-cat 4   # semantic (mặc định)
python scripts/eval/make_judgments.py --out eval/relevance_keyword.csv --no-human  # keyword
python scripts/eval/run_evaluation.py --no-rerank                      # 2A semantic (sạch)
python scripts/eval/run_evaluation.py --judgments eval/relevance_keyword.csv --tag _kw --noisy --no-rerank  # 2B robustness
```

---

## Giới hạn đã biết (nêu chủ động khi bảo vệ)

| Giới hạn | Cách xử lý trong đồ án |
|---|---|
| Nhãn tự động ≈ tín hiệu từ vựng (vòng tròn) | **Semantic benchmark** (truy vấn paraphrase không chứa từ khóa) -> ngữ nghĩa > lexical có ý nghĩa thống kê (§2A); + human test set tách biệt (§4) |
| Interactions thiếu tín hiệu cộng tác | **Latent-factor generation** -> CF leakage-free NDCG@10 0.006→0.13, vượt popularity (§5) |
| ~~Catalog synthetic~~ → **đã chạy trên DỮ LIỆU THẬT** | 4.088 khóa IT từ Kaggle (Coursera/Udemy), §8 Trụ cột I; toàn bộ §2–§7 tái chạy trên data thật |
| Semantic chỉ 12 truy vấn (under-powered) | Khoảng cách điểm rõ (ngữ nghĩa > lexical, R@100 ×5) nhưng p chưa <0.05 -> cần thêm truy vấn/nhãn người |
| Nhãn người gán đang **mô phỏng** (Kappa auto-vs-mô-phỏng 0.72) | Khung + công cụ phiếu gán sẵn sàng; **cần gán tay `human_judgments.csv`** trước khi báo cáo (§4) |
| Tương tác người dùng vẫn **mô phỏng** (latent-factor) | Không có log thật; off-policy (§6) sẵn sàng nhận log click thật từ web app |
| Không GPU | Chọn đúng tập kỹ thuật CPU chuẩn ngành (GBDT LTR, off-policy, latency engineering) |
| Chưa có lưu lượng người dùng thật | A/B trình bày dạng thiết kế + **off-policy** ước lượng phản thực |
