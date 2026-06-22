# Nền tảng học tập CNTT — Web app (Express + TypeScript + PostgreSQL)

Web app "thực tế" cho người học CNTT: tài khoản, duyệt/tìm khóa học & tài liệu, gợi ý cá nhân
hóa, trợ lý chatbot, lưu khóa học & theo dõi tiến độ. **Tích hợp** hệ thống gợi ý Python/FastAPI
(`itlr.api.server`) đang có làm "bộ não" ML.

## Kiến trúc (2 dịch vụ)
```
Browser ──SSR(EJS)──> Express+TS (:3000) ──pg──> PostgreSQL (users · courses · enrollments)
                            │
                            └──HTTP──> Recommender FastAPI (:8000)  [search · chat · for-you · personas]
```
- **Express+TS** (thư mục này `web/`): web/nghiệp vụ + Postgres. Render trang bằng EJS.
- **Recommender** (gốc repo, Python): search ngữ nghĩa, chatbot RAG (off-topic gate + khái niệm-trước), CF. **Không sửa.**
- Catalog 50k mục đồng bộ từ `../data/it_learning_items.csv` vào bảng `courses` (nguồn chính).

## Yêu cầu
- Node.js ≥ 18 (đã test Node 22)
- PostgreSQL ≥ 14 (đã test PostgreSQL 18)
- Python recommender chạy được (xem README gốc repo)

## Cài đặt & chạy
```bash
# 1) Cài deps
cd web
npm install

# 2) Cấu hình — tạo web/.env từ mẫu, sửa mật khẩu Postgres cho khớp máy bạn
#    DATABASE_URL=postgresql://postgres:<MẬT_KHẨU>@localhost:5432/it_learning
cp .env.example .env       # Windows PowerShell: Copy-Item .env.example .env

# 3) Tạo database (1 lần). Dùng psql của bản cài Postgres, ví dụ Windows:
#    & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -c "CREATE DATABASE it_learning"
createdb it_learning       # nếu có createdb trên PATH

# 4) Tạo bảng + nạp 50k khóa học từ CSV
npm run migrate
npm run seed               # nạp lại: npm run seed -- --force

# 5) Chạy 2 dịch vụ (2 terminal):
#    (a) Recommender (ở thư mục GỐC repo):
#        npm run dev           # uvicorn itlr.api.server:app :8000
#    (b) Web app (ở web/):
npm run dev                   # tsx watch :3000  -> mở http://localhost:3000
```

## Lệnh
| Lệnh | Tác dụng |
|------|----------|
| `npm run dev` | Chạy dev (tsx watch) tại `:3000` |
| `npm run migrate` | Tạo bảng từ `src/db/schema.sql` |
| `npm run seed` | Nạp catalog từ CSV (`-- --force` để nạp lại) |
| `npm run typecheck` | Kiểm tra TypeScript (không phát sinh JS) |
| `npm run build` / `start` | Biên dịch sang `dist/` rồi chạy bằng node |

## Tính năng
- **Auth (bắt buộc)**: PHẢI đăng ký/đăng nhập mới vào được mọi trang (cổng auth toàn cục); chưa đăng nhập → tự chuyển về `/login`. Mật khẩu băm bcrypt, JWT trong cookie httpOnly, vai trò `user`/`admin`.
- **Trang chủ** `/`: tìm kiếm nhanh, lĩnh vực phổ biến (từ Postgres), gợi ý câu hỏi chatbot.
- **Tìm kiếm** `/search`: gọi recommender (semantic search) → render kết quả.
- **Chi tiết** `/courses/:id`: dữ liệu từ Postgres + "khóa liên quan" (recommender) + lưu/tiến độ.
- **Dashboard** `/dashboard` (cần đăng nhập): khóa đã lưu + "Dành cho bạn" (CF).
- **Chatbot** `/chat`: proxy `/api/chat` sang recommender; markdown render server-side.
- **Admin** `/admin` (chỉ `admin`): thống kê + người dùng gần đây.

### Cấp quyền admin cho một tài khoản
```sql
UPDATE users SET role='admin' WHERE email='ban@example.com';
```

## Lưu ý
- Recommender chết → các trang ML hiện thông báo gọn (không crash app); trang DB vẫn chạy.
- Lỗi async (vd sai mật khẩu DB) được error handler bắt → trang 500 gọn, server không sập.
- `.env` chứa bí mật — đã được `.gitignore`.
