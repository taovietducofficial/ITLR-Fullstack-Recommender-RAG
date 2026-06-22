import { Response } from "express";

/* ════════════════════════════════════════════════════════════════════════════
   Realtime qua Server-Sent Events (SSE). Hub trong bộ nhớ tiến trình:
   - Mỗi client (1 tab đã đăng nhập) giữ 1 kết nối SSE, gắn theo userId.
   - Server đẩy sự kiện tới đúng user (sendToUser) hoặc mọi người (broadcast).
   Gửi dữ liệu vẫn đi qua các POST hiện có; SSE chỉ dùng để NHẬN cập nhật.

   Lưu ý mở rộng: hub này theo từng tiến trình. Khi chạy nhiều instance
   (vd nhiều dyno Heroku) cần thay bằng pub/sub dùng chung (Redis...).
   ════════════════════════════════════════════════════════════════════════════ */

interface Client {
  userId: number;
  res: Response;
}

const clients = new Set<Client>();

// Đăng ký 1 client; trả về hàm gỡ bỏ khi kết nối đóng.
export function addClient(userId: number, res: Response): () => void {
  const c: Client = { userId, res };
  clients.add(c);
  return () => clients.delete(c);
}

function write(res: Response, event: string, data: unknown): void {
  try {
    res.write(`event: ${event}\n`);
    res.write(`data: ${JSON.stringify(data)}\n\n`);
  } catch {
    /* kết nối đã đóng — sẽ được dọn khi 'close' kích hoạt */
  }
}

// Gửi tới mọi tab của một user.
export function sendToUser(userId: number, event: string, data: unknown): void {
  for (const c of clients) if (c.userId === userId) write(c.res, event, data);
}

// Gửi tới tất cả (trừ exceptUserId nếu có) — dùng cho feed cộng đồng.
export function broadcast(event: string, data: unknown, exceptUserId?: number): void {
  for (const c of clients) if (c.userId !== exceptUserId) write(c.res, event, data);
}

// Số kết nối đang mở (cho chẩn đoán/health).
export function liveCount(): number {
  return clients.size;
}

// Presence: user có ÍT NHẤT một tab đang mở kết nối SSE -> coi như online.
export function isOnline(userId: number): boolean {
  for (const c of clients) if (c.userId === userId) return true;
  return false;
}
