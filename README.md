# Hệ thống gợi ý tài liệu & khóa học CNTT

Hệ thống gợi ý nội dung học tập CNTT sử dụng **Content-Based Filtering + TF-IDF + Cosine Similarity**. Ứng dụng gợi ý các khóa học và tài liệu IT tương tự dựa trên mô tả, chuyên mục, chủ đề, giảng viên và nền tảng.

## Tính năng

- Gợi ý **1000 khóa học và tài liệu CNTT** (Lập trình, AI/ML, Mạng máy tính, DevOps, ...)
- Lọc theo loại: Khóa học hoặc Tài liệu
- Hiển thị độ tương đồng (%) giữa các mục
- Giao diện web với **FastAPI** (API JSON + trang HTML, không cần Streamlit)

## Công nghệ sử dụng

| Thành phần | Công nghệ |
|---|---|
| ML Algorithm | Content-Based Filtering |
| Vectorization | TF-IDF (TfidfVectorizer) |
| Similarity | Cosine Similarity |
| Web | FastAPI + HTML/JS |
| Ngôn ngữ | Python 3.10+ |

## Cấu trúc dự án

```
├── app.py                          # Launcher web API (FastAPI)
├── build_model.py                  # Script huấn luyện mô hình
├── data/
│   └── it_learning_items.csv       # Dataset khóa học & tài liệu CNTT
├── artifacts/
│   ├── item_list.pkl               # Danh sách mục đã xử lý
│   └── similarity.pkl              # Ma trận cosine similarity
└── requirements.txt
```

## Cách chạy

### Bước 1: Tạo môi trường ảo

```bash
conda create -n it-recommender python=3.10 -y
conda activate it-recommender
```

### Bước 2: Cài đặt thư viện

```bash
pip install -r requirements.txt
```

### Bước 3: Huấn luyện mô hình

**Cách 1 — Script (nhanh):**
```bash
python build_model.py
```

**Cách 2 — Jupyter Notebook (xem từng bước train):**
```bash
pip install ipykernel jupyter
jupyter notebook "IT Learning Recommender System.ipynb"
```
Chạy **tất cả cell** theo thứ tự → lưu file `.pkl` vào `artifacts/`.

### Bước 4: Chạy ứng dụng

```bash
npm run dev                                # lệnh ngắn (gọi uvicorn qua venv)
# hoặc: uvicorn itlr.api.server:app --port 8000  /  python -m itlr.api  /  python app.py
```
Mở trình duyệt: **http://localhost:8000**

## Dataset

File `data/it_learning_items.csv` chứa 1000 mục gồm:

- **Khóa học**: Python, JavaScript, React, Machine Learning, DevOps, ...
- **Tài liệu**: Clean Code, Design Patterns, MDN Web Docs, TensorFlow Docs, ...

Các trường dữ liệu: `item_id`, `title`, `type`, `description`, `category`, `topics`, `instructor`, `platform`, `link`

## Thuật toán

1. **Content-Based Filtering:** tạo tags có trọng số (title ×4, topics ×4, category ×3, description ×2)
2. **TF-IDF:** vector hóa với tokenizer hỗ trợ tiếng Việt + stemming tiếng Anh
3. **Cosine Similarity:** tính độ tương đồng giữa các vector TF-IDF
4. **Hybrid Scoring:** `65% TF-IDF + 25% cùng chuyên mục + 10% chủ đề trùng (Jaccard)`
5. Trả về top 5 mục có điểm cao nhất

## Mở rộng

- Thêm dữ liệu vào `data/it_learning_items.csv`
- Chạy lại `python build_model.py`
- Khởi động lại web API
