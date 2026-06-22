import { query } from "../db/pool";

export type FriendStatus = "self" | "none" | "friends" | "pending_out" | "pending_in";

// Quan hệ giữa "me" và "other" (1 cạnh duy nhất, tra cả 2 chiều).
export async function friendStatus(me: number, other: number): Promise<FriendStatus> {
  if (me === other) return "self";
  const rows = await query<{ requester_id: number; status: string }>(
    `SELECT requester_id, status FROM friendships
      WHERE (requester_id = $1 AND addressee_id = $2) OR (requester_id = $2 AND addressee_id = $1)`,
    [me, other]
  );
  if (!rows.length) return "none";
  if (rows[0].status === "accepted") return "friends";
  return rows[0].requester_id === me ? "pending_out" : "pending_in";
}

// Danh sách id bạn bè đã chấp nhận (cho presence: báo online/offline tới đúng bạn bè).
export async function acceptedFriendIds(userId: number): Promise<number[]> {
  const rows = await query<{ id: number }>(
    `SELECT CASE WHEN requester_id = $1 THEN addressee_id ELSE requester_id END AS id
       FROM friendships WHERE status = 'accepted' AND (requester_id = $1 OR addressee_id = $1)`,
    [userId]
  );
  return rows.map((r) => r.id);
}

export async function areFriends(a: number, b: number): Promise<boolean> {
  const r = await query(
    `SELECT 1 FROM friendships WHERE status = 'accepted'
       AND ((requester_id = $1 AND addressee_id = $2) OR (requester_id = $2 AND addressee_id = $1))`,
    [a, b]
  );
  return r.length > 0;
}

// Trích YouTube video id từ URL (watch / youtu.be / embed / shorts) hoặc id thô 11 ký tự.
export function parseYouTubeId(input: string): string | null {
  const s = (input || "").trim();
  const m = s.match(/(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|embed\/|shorts\/|v\/))([A-Za-z0-9_-]{11})/);
  if (m) return m[1];
  if (/^[A-Za-z0-9_-]{11}$/.test(s)) return s;
  return null;
}
