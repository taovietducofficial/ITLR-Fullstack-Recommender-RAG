# Triển khai bằng Docker (web + recommender + PostgreSQL)

Chạy cả hệ thống bằng **một lệnh** `docker compose up`. Ba container:

| Service | Vai trò | Cổng |
|---|---|---|
| `postgres` | Cơ sở dữ liệu (users, courses, enrollments, posts, **file lưu bytea**) | nội bộ 5432 |
| `recommender` | Python/FastAPI — search ngữ nghĩa, chatbot RAG, CF | nội bộ 8000 |
| `web` | Express/TS — giao diện, auth, blog; gọi recommender | **3000 → host** |

```
Browser → web (:3000) → postgres (:5432)
                      ↘ recommender (:8000)
```

## Yêu cầu
- **Docker** + **Docker Compose v2** (Docker Desktop hoặc Docker Engine).
- **Artifacts model** phải có sẵn trong `./artifacts/` (recommender mount read-only):
  ```bash
  python scripts/build_all.py     # tạo artifacts (chạy 1 lần, cần ~vài phút)
  ```
  và `./data/it_learning_items.csv` (catalog 50k) để seed.

## Các bước
```bash
# 1) Tạo file cấu hình bí mật
cp .env.docker.example .env        # rồi sửa POSTGRES_PASSWORD, JWT_SECRET, SMTP...

# 2) Khởi chạy (build image lần đầu hơi lâu vì cài torch/faiss)
docker compose up -d --build

# 3) Theo dõi tiến trình
docker compose logs -f web          # web: migrate -> seed 50k -> server
docker compose logs -f recommender  # recommender: tải model lần đầu (cần internet) -> [OK] sẵn sàng

# 4) Mở trình duyệt
#    http://localhost:3000
```
- Lần đầu: `web` tự **migrate + seed 50.000 courses**; `recommender` **tải model embedding/reranker** từ HuggingFace (lưu vào volume `hf-cache`, lần sau không tải lại).
- Recommender cần ~30–90s để nạp model ⇒ tab Tìm kiếm/Trợ lý có dữ liệu sau khi nó log `[OK] Engine sẵn sàng`. Web vẫn mở được ngay (trang DB chạy độc lập).

## Lệnh thường dùng
```bash
docker compose ps                  # trạng thái
docker compose logs -f <service>   # xem log
docker compose restart web         # khởi động lại 1 service
docker compose down                # dừng (GIỮ dữ liệu trong volume)
docker compose down -v             # dừng + XÓA dữ liệu (pgdata + hf-cache)
docker compose up -d --build web   # build lại riêng web sau khi sửa code
```

## Dữ liệu & lưu trữ
- **File upload (ảnh blog, tài liệu khóa học) lưu trong PostgreSQL (`bytea`)** ⇒ deploy nhiều instance / cloud không mất file khi restart.
- Dữ liệu DB nằm ở volume `pgdata`; cache model ở `hf-cache`. Sao lưu: `docker compose exec postgres pg_dump -U postgres it_learning > backup.sql`.

## Lưu ý production (nhiều người dùng)
- Đặt **`POSTGRES_PASSWORD`** và **`JWT_SECRET`** mạnh trong `.env`.
- Chạy sau **reverse proxy + HTTPS** (Nginx/Caddy/Traefik) rồi bật `NODE_ENV=production` cho `web` (cookie `secure`). Khi còn HTTP thuần thì để trống NODE_ENV (cookie vẫn hoạt động).
- Email quên mật khẩu: điền `SMTP_USER` + `SMTP_PASS` (App Password Gmail).
- Recommender khá nặng RAM (model + 50k embeddings) — cấp tối thiểu ~2–3GB RAM cho container đó.

## Deploy lên server không có sẵn artifacts
Hai cách:
1. **Mount (mặc định):** copy thư mục `artifacts/` + `data/` lên server cạnh `docker-compose.yml` rồi `docker compose up`.
2. **Bake vào image (self-contained):** bỏ dòng `artifacts`/`data` trong `.dockerignore`, thêm `COPY artifacts ./artifacts` và `COPY data ./data` vào `Dockerfile`, rồi build (image lớn hơn nhiều GB nhưng không cần mount).

## Khắc phục sự cố
- `recommender` log "Chưa có model artifacts" → thư mục `./artifacts` rỗng; chạy `python scripts/build_all.py` rồi `docker compose up -d`.
- Recommender không tải được model (mạng chặn HuggingFace) → cần internet ở lần chạy đầu, hoặc pre-cache model vào volume `hf-cache`.
- Web báo lỗi kết nối DB → kiểm tra `postgres` đã `healthy`: `docker compose ps`.
