#!/bin/sh
# Khởi động web container: tạo bảng + nạp catalog (idempotent) rồi chạy server.
# Postgres đã được docker-compose chờ "healthy" qua depends_on nên có thể migrate ngay.
# Chạy JS đã biên dịch trong dist/ (image runtime không có tsx/src).
set -e

echo "[entrypoint] migrate (tạo bảng nếu chưa có)..."
node dist/db/migrate.js

echo "[entrypoint] seed catalog (bỏ qua nếu đã có / thiếu CSV)..."
node dist/db/seed-courses.js || echo "[entrypoint] seed bỏ qua (đã có dữ liệu hoặc thiếu ITEMS_CSV)."

echo "[entrypoint] khởi động web server..."
exec node dist/server.js
