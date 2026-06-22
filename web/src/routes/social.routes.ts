import path from "node:path";
import { Router } from "express";
import multer from "multer";
import { query } from "../db/pool";
import { requireAuth, signToken, setAuthCookie } from "../middleware/auth";
import { friendStatus, areFriends } from "../services/social";
import { fetchPosts } from "../services/posts";
import { sendToUser, isOnline } from "../services/realtime";
import { UserCard, ProfileRow, DmRow, DmMediaRow, DmSharedPost, DmSharedCourse } from "../db/types";

export const socialRouter = Router();

const avatarUpload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 4 * 1024 * 1024 },
  fileFilter: (_req, file, cb) => cb(null, /^image\//.test(file.mimetype)),
});

// ── Đính kèm trong tin nhắn: ảnh / video / tài liệu (PDF·DOCX·XLS) ─────────────
const DM_DOC_EXT = new Set([".pdf", ".doc", ".docx", ".xls", ".xlsx"]);
const DM_IMG_EXT = new Set([".jpg", ".jpeg", ".png", ".gif", ".webp"]);
const extOf = (name: string) => path.extname(name || "").toLowerCase();
// multer 1.x giải mã originalname theo latin1 -> sửa lại UTF-8 cho tên tiếng Việt.
const utf8name = (name: string) => Buffer.from(name, "latin1").toString("utf8");

const dmUpload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 60 * 1024 * 1024 }, // video tới 60MB
  fileFilter: (_req, file, cb) => {
    const e = extOf(file.originalname);
    if (file.fieldname === "image") cb(null, DM_IMG_EXT.has(e));
    else if (file.fieldname === "video") cb(null, /^video\//.test(file.mimetype));
    else if (file.fieldname === "doc") cb(null, DM_DOC_EXT.has(e));
    else cb(null, false);
  },
});

// Cột chọn cho 1 tin nhắn (kèm cờ media + id chia sẻ) — KHÔNG kéo bytea nặng về.
const DM_COLS = `id, sender_id, content, created_at, read_at,
  (image_data IS NOT NULL) AS has_image,
  (video_data IS NOT NULL) AS has_video,
  (doc_data   IS NOT NULL) AS has_doc, doc_original,
  shared_post_id, shared_course_id`;

// Gắn thêm bản xem trước cho bài viết / khóa học được chia sẻ trong tin nhắn.
async function enrichMessages(rows: DmRow[]): Promise<DmRow[]> {
  if (!rows.length) return rows;
  const postIds = [...new Set(rows.map((r) => r.shared_post_id).filter(Boolean))];
  const courseIds = [...new Set(rows.map((r) => r.shared_course_id).filter(Boolean))];

  const posts: Record<number, DmSharedPost> = {};
  if (postIds.length) {
    const ps = await query<DmSharedPost>(
      `SELECT p.id, left(p.content, 160) AS content, u.name AS author,
              (p.image_data IS NOT NULL) AS has_image, (p.video_data IS NOT NULL) AS has_video,
              (p.doc_data IS NOT NULL) AS has_doc
         FROM posts p JOIN users u ON u.id = p.user_id WHERE p.id = ANY($1::int[])`,
      [postIds]
    );
    ps.forEach((p) => (posts[p.id] = p));
  }
  const courses: Record<number, DmSharedCourse> = {};
  if (courseIds.length) {
    const cs = await query<DmSharedCourse>(
      "SELECT item_id, title, type, category FROM courses WHERE item_id = ANY($1::int[])",
      [courseIds]
    );
    cs.forEach((c) => (courses[c.item_id] = c));
  }
  rows.forEach((r) => {
    r.post = r.shared_post_id ? posts[r.shared_post_id] || null : null;
    r.course = r.shared_course_id ? courses[r.shared_course_id] || null : null;
  });
  return rows;
}

// ── Avatar: phục vụ ảnh từ DB ──────────────────────────────────────────────────
socialRouter.get("/api/avatar/:id", requireAuth, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id)) return res.status(404).end();
  const rows = await query<{ avatar_data: Buffer | null; avatar_mime: string | null }>(
    "SELECT avatar_data, avatar_mime FROM users WHERE id = $1", [id]
  );
  const u = rows[0];
  if (!u || !u.avatar_data) return res.status(404).end();
  res.setHeader("Content-Type", u.avatar_mime || "image/jpeg");
  res.setHeader("Cache-Control", "private, max-age=120");
  res.send(u.avatar_data);
});

socialRouter.post("/api/account/avatar", requireAuth, avatarUpload.single("avatar"), async (req, res) => {
  if (!req.file) return res.status(400).json({ error: "Chỉ nhận ảnh (≤ 4MB)." });
  await query("UPDATE users SET avatar_data = $1, avatar_mime = $2 WHERE id = $3",
    [req.file.buffer, req.file.mimetype, req.user!.id]);
  res.redirect("/account");
});

// Đổi tên hiển thị (cập nhật lại JWT để navbar đổi theo).
socialRouter.post("/account/profile", requireAuth, async (req, res) => {
  const name = String(req.body?.name || "").trim().slice(0, 80);
  if (name) {
    await query("UPDATE users SET name = $1 WHERE id = $2", [name, req.user!.id]);
    setAuthCookie(res, signToken({ id: req.user!.id, email: req.user!.email, name, role: req.user!.role }));
  }
  res.redirect("/account");
});

// ── Trang hồ sơ user: bài viết + nút kết bạn / nhắn tin ────────────────────────
socialRouter.get("/u/:id", requireAuth, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id)) return res.status(404).render("error", { title: "404", message: "Không tìm thấy người dùng." });
  const rows = await query<ProfileRow>(
    `SELECT id, name, email, role, created_at, (avatar_data IS NOT NULL) AS has_avatar FROM users WHERE id = $1`, [id]
  );
  const profile = rows[0];
  if (!profile) return res.status(404).render("error", { title: "404", message: "Không tìm thấy người dùng." });

  const [[fc], posts] = await Promise.all([
    query<{ n: number }>(
      "SELECT count(*)::int AS n FROM friendships WHERE status='accepted' AND (requester_id=$1 OR addressee_id=$1)", [id]
    ),
    fetchPosts(req.user!.id, id),
  ]);
  const status = await friendStatus(req.user!.id, id);
  res.render("profile", { title: profile.name, profile, posts, status, friendCount: fc.n });
});

// ── Kết bạn ────────────────────────────────────────────────────────────────────
socialRouter.post("/api/friends/request", requireAuth, async (req, res) => {
  const to = parseInt(req.body?.to, 10);
  const me = req.user!.id;
  if (Number.isNaN(to) || to === me) return res.status(400).json({ error: "Không hợp lệ." });
  const exists = await query("SELECT 1 FROM users WHERE id = $1", [to]);
  if (!exists.length) return res.status(404).json({ error: "Người dùng không tồn tại." });
  const cur = await friendStatus(me, to);
  if (cur !== "none") return res.status(409).json({ error: "Đã có quan hệ kết bạn.", status: cur });
  const intro = String(req.body?.intro || "").trim().slice(0, 300);
  await query(
    "INSERT INTO friendships (requester_id, addressee_id, status, intro) VALUES ($1,$2,'pending',$3) ON CONFLICT DO NOTHING",
    [me, to, intro || null]
  );
  res.json({ ok: true, status: "pending_out" });
  // Realtime: báo lời mời kết bạn tới người nhận.
  sendToUser(to, "friend_request", { from: me, name: req.user!.name, intro: intro || "" });
});

socialRouter.post("/api/friends/accept", requireAuth, async (req, res) => {
  const from = parseInt(req.body?.from, 10);
  if (Number.isNaN(from)) return res.status(400).json({ error: "Không hợp lệ." });
  await query(
    "UPDATE friendships SET status='accepted' WHERE requester_id=$1 AND addressee_id=$2 AND status='pending'",
    [from, req.user!.id]
  );
  res.json({ ok: true });
  // Realtime: báo cho người đã gửi lời mời biết được chấp nhận.
  sendToUser(from, "friend_accept", { by: req.user!.id, name: req.user!.name });
});

socialRouter.post("/api/friends/remove", requireAuth, async (req, res) => {
  const other = parseInt(req.body?.user, 10);
  if (Number.isNaN(other)) return res.status(400).json({ error: "Không hợp lệ." });
  await query(
    `DELETE FROM friendships
      WHERE (requester_id=$1 AND addressee_id=$2) OR (requester_id=$2 AND addressee_id=$1)`,
    [req.user!.id, other]
  );
  res.json({ ok: true, status: "none" });
});

// ── Trang bạn bè: lời mời đến + danh sách bạn ─────────────────────────────────
socialRouter.get("/friends", requireAuth, async (req, res) => {
  const me = req.user!.id;
  const [incoming, friends] = await Promise.all([
    query<UserCard>(
      `SELECT u.id, u.name, f.intro, (u.avatar_data IS NOT NULL) AS has_avatar
         FROM friendships f JOIN users u ON u.id = f.requester_id
        WHERE f.addressee_id = $1 AND f.status = 'pending' ORDER BY f.created_at DESC`, [me]
    ),
    query<UserCard>(
      `SELECT u.id, u.name, (u.avatar_data IS NOT NULL) AS has_avatar
         FROM friendships f
         JOIN users u ON u.id = CASE WHEN f.requester_id = $1 THEN f.addressee_id ELSE f.requester_id END
        WHERE f.status = 'accepted' AND (f.requester_id = $1 OR f.addressee_id = $1) ORDER BY u.name`, [me]
    ),
  ]);
  res.render("friends", { title: "Bạn bè", incoming, friends });
});

// ── Nhắn tin (chỉ giữa bạn bè) ────────────────────────────────────────────────
socialRouter.get("/messages", requireAuth, async (req, res) => {
  const me = req.user!.id;
  const friends = await query<UserCard>(
    `SELECT u.id, u.name, (u.avatar_data IS NOT NULL) AS has_avatar, u.last_seen
       FROM friendships f
       JOIN users u ON u.id = CASE WHEN f.requester_id = $1 THEN f.addressee_id ELSE f.requester_id END
      WHERE f.status = 'accepted' AND (f.requester_id = $1 OR f.addressee_id = $1) ORDER BY u.name`, [me]
  );
  friends.forEach((u) => (u.online = isOnline(u.id))); // presence ban đầu (SSE giữ cho cập nhật)

  let active: UserCard | null = null;
  let messages: DmRow[] = [];
  const other = parseInt(req.query.u as string, 10);
  if (!Number.isNaN(other) && (await areFriends(me, other))) {
    const ur = await query<UserCard>(
      "SELECT id, name, (avatar_data IS NOT NULL) AS has_avatar, last_seen FROM users WHERE id = $1", [other]
    );
    active = ur[0] || null;
    if (active) {
      active.online = isOnline(active.id);
      messages = await enrichMessages(
        await query<DmRow>(
          `SELECT ${DM_COLS} FROM direct_messages
            WHERE (sender_id=$1 AND recipient_id=$2) OR (sender_id=$2 AND recipient_id=$1)
            ORDER BY id`, [me, other]
        )
      );
      // Mở đoạn chat = đã đọc các tin nhận từ người này -> báo người gửi "đã xem".
      const read = await query<{ id: number }>(
        `UPDATE direct_messages SET read_at = now()
          WHERE recipient_id = $1 AND sender_id = $2 AND read_at IS NULL RETURNING id`, [me, other]
      );
      if (read.length) sendToUser(other, "dm_read", { by: me, at: new Date().toISOString() });
    }
  }
  res.render("messages", { title: "Tin nhắn", friends, active, messages, me });
});

// Gửi tin nhắn: hỗ trợ multipart (ảnh/video/tài liệu) HOẶC JSON (text / chia sẻ post-khóa học).
socialRouter.post(
  "/api/messages",
  requireAuth,
  dmUpload.fields([{ name: "image", maxCount: 1 }, { name: "video", maxCount: 1 }, { name: "doc", maxCount: 1 }]),
  async (req, res) => {
    const me = req.user!.id;
    const to = parseInt(req.body?.to, 10);
    if (Number.isNaN(to)) return res.status(400).json({ error: "Người nhận không hợp lệ." });
    if (!(await areFriends(me, to))) return res.status(403).json({ error: "Chỉ nhắn tin được với bạn bè." });

    const content = String(req.body?.content || "").trim().slice(0, 4000);
    const files = req.files as { [k: string]: Express.Multer.File[] } | undefined;
    const image = files?.image?.[0];
    const video = files?.video?.[0];
    const doc = files?.doc?.[0];

    // Chia sẻ bài viết / khóa học vào đoạn chat (kiểm tra tồn tại để FK không lỗi).
    let sharedPostId: number | null = parseInt(req.body?.shared_post_id, 10);
    if (Number.isNaN(sharedPostId)) sharedPostId = null;
    else if (!(await query("SELECT 1 FROM posts WHERE id=$1", [sharedPostId])).length) sharedPostId = null;

    let sharedCourseId: number | null = parseInt(req.body?.shared_course_id, 10);
    if (Number.isNaN(sharedCourseId)) sharedCourseId = null;
    else if (!(await query("SELECT 1 FROM courses WHERE item_id=$1", [sharedCourseId])).length)
      return res.status(404).json({ error: "Khóa học không tồn tại." });

    if (!content && !image && !video && !doc && !sharedPostId && !sharedCourseId) {
      return res.status(400).json({ error: "Hãy nhập nội dung hoặc đính kèm ảnh/video/tài liệu." });
    }

    const docOriginal = doc ? utf8name(doc.originalname) : null;
    const rows = await query<DmRow>(
      `INSERT INTO direct_messages
         (sender_id, recipient_id, content, image_data, image_mime, video_data, video_mime,
          doc_data, doc_mime, doc_original, shared_post_id, shared_course_id)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
       RETURNING ${DM_COLS}`,
      [me, to, content, image?.buffer || null, image?.mimetype || null, video?.buffer || null,
       video?.mimetype || null, doc?.buffer || null, doc?.mimetype || null, docOriginal,
       sharedPostId, sharedCourseId]
    );
    const [message] = await enrichMessages(rows);
    res.json({ ok: true, message });
    // Realtime: đẩy tin nhắn tới người nhận ngay lập tức.
    sendToUser(to, "dm", { from: me, fromName: req.user!.name, message });
  }
);

// ── Realtime: "đang soạn tin" — chỉ đẩy SSE tạm thời, không lưu DB ────────────
socialRouter.post("/api/messages/:userId/typing", requireAuth, async (req, res) => {
  const me = req.user!.id;
  const other = parseInt(req.params.userId, 10);
  if (Number.isNaN(other)) return res.status(400).json({ error: "Không hợp lệ." });
  if (!(await areFriends(me, other))) return res.status(403).json({ error: "Chỉ với bạn bè." });
  res.json({ ok: true });
  sendToUser(other, "typing", { from: me, name: req.user!.name });
});

// ── Realtime: đánh dấu ĐÃ ĐỌC các tin nhận từ người này -> báo người gửi "đã xem" ──
socialRouter.post("/api/messages/:userId/read", requireAuth, async (req, res) => {
  const me = req.user!.id;
  const other = parseInt(req.params.userId, 10);
  if (Number.isNaN(other)) return res.status(400).json({ error: "Không hợp lệ." });
  if (!(await areFriends(me, other))) return res.status(403).json({ error: "Chỉ với bạn bè." });
  const rows = await query<{ id: number }>(
    `UPDATE direct_messages SET read_at = now()
      WHERE recipient_id = $1 AND sender_id = $2 AND read_at IS NULL RETURNING id`, [me, other]
  );
  res.json({ ok: true, count: rows.length });
  if (rows.length) sendToUser(other, "dm_read", { by: me, at: new Date().toISOString() });
});

// ── Backup lịch sử trò chuyện: tải về file HTML tự chứa (chỉ chủ cuộc trò chuyện) ──
function htmlEscape(s: string): string {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string)
  );
}

socialRouter.get("/api/messages/:userId/export", requireAuth, async (req, res) => {
  const me = req.user!.id;
  const other = parseInt(req.params.userId, 10);
  if (Number.isNaN(other)) return res.status(400).send("Không hợp lệ.");
  if (!(await areFriends(me, other))) return res.status(403).send("Chỉ tải được lịch sử với bạn bè.");

  const [meRow] = await query<{ name: string }>("SELECT name FROM users WHERE id=$1", [me]);
  const [otherRow] = await query<{ name: string }>("SELECT name FROM users WHERE id=$1", [other]);
  const msgs = await enrichMessages(
    await query<DmRow>(
      `SELECT ${DM_COLS} FROM direct_messages
        WHERE (sender_id=$1 AND recipient_id=$2) OR (sender_id=$2 AND recipient_id=$1)
        ORDER BY id`,
      [me, other]
    )
  );

  const meName = htmlEscape(meRow?.name || "Tôi");
  const otherName = htmlEscape(otherRow?.name || "Bạn");
  const exportedAt = new Date().toLocaleString("vi-VN");
  const rows = msgs
    .map((m) => {
      const mine = m.sender_id === me;
      const who = mine ? meName : otherName;
      const time = new Date(m.created_at).toLocaleString("vi-VN");
      const parts: string[] = [];
      if (m.content) parts.push(htmlEscape(m.content));
      if (m.has_image) parts.push("🖼️ [Hình ảnh]");
      if (m.has_video) parts.push("🎬 [Video]");
      if (m.has_doc) parts.push("📎 [Tài liệu: " + htmlEscape(m.doc_original || "tài liệu") + "]");
      if (m.post) parts.push("↪ [Chia sẻ bài viết của " + htmlEscape(m.post.author) + "]");
      if (m.course) parts.push("📚 [Chia sẻ khóa học: " + htmlEscape(m.course.title) + "]");
      return `<div class="dm ${mine ? "me" : "them"}"><div class="who">${who} · <span>${htmlEscape(time)}</span></div><div class="bubble">${parts.join("<br>") || "(trống)"}</div></div>`;
    })
    .join("\n");

  const html = `<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lịch sử trò chuyện · ${meName} & ${otherName}</title>
<style>
  :root{--brand:#4f46e5;--ink:#0f1222;--muted:#6b7280;--line:#e7e9f0;--bg:#f6f7fb}
  *{box-sizing:border-box}
  body{margin:0;font-family:'Segoe UI',system-ui,-apple-system,Roboto,sans-serif;background:var(--bg);color:var(--ink);line-height:1.55}
  .wrap{max-width:760px;margin:0 auto;padding:24px 16px 64px}
  header{text-align:center;padding:24px;background:linear-gradient(135deg,#6366f1,#7c3aed);color:#fff;border-radius:18px;margin-bottom:20px;box-shadow:0 18px 40px rgba(99,102,241,.25)}
  header h1{margin:0 0 6px;font-size:1.3rem}
  header p{margin:0;opacity:.9;font-size:.9rem}
  .log{display:flex;flex-direction:column;gap:10px}
  .dm{max-width:78%;display:flex;flex-direction:column;gap:4px}
  .dm.me{align-self:flex-end;align-items:flex-end}
  .dm.them{align-self:flex-start}
  .who{font-size:.74rem;color:var(--muted);padding:0 6px}
  .bubble{padding:10px 14px;border-radius:16px;font-size:.95rem;overflow-wrap:anywhere;white-space:pre-wrap;box-shadow:0 1px 2px rgba(16,18,34,.06)}
  .dm.them .bubble{background:#fff;border:1px solid var(--line)}
  .dm.me .bubble{background:var(--brand);color:#fff}
  footer{text-align:center;color:var(--muted);font-size:.8rem;margin-top:28px}
</style></head>
<body><div class="wrap">
<header><h1>💬 Lịch sử trò chuyện</h1><p>${meName} &amp; ${otherName} · ${msgs.length} tin nhắn · Xuất lúc ${htmlEscape(exportedAt)}</p></header>
<div class="log">
${rows || '<p style="text-align:center;color:var(--muted)">Chưa có tin nhắn nào.</p>'}
</div>
<footer>Bản sao lưu cá nhân do bạn tải về từ Nền tảng học tập CNTT.</footer>
</div></body></html>`;

  const fname = `lich-su-tro-chuyen-${otherName}-${Date.now()}.html`.replace(/[^\w.\-]+/g, "_");
  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.setHeader("Content-Disposition", `attachment; filename*=UTF-8''${encodeURIComponent(fname)}`);
  res.send(html);
});

socialRouter.get("/api/messages/:userId", requireAuth, async (req, res) => {
  const other = parseInt(req.params.userId, 10);
  const after = parseInt((req.query.after as string) || "0", 10) || 0;
  if (Number.isNaN(other)) return res.status(400).json({ error: "Không hợp lệ." });
  if (!(await areFriends(req.user!.id, other))) return res.status(403).json({ error: "Chỉ xem được với bạn bè." });
  const rows = await enrichMessages(
    await query<DmRow>(
      `SELECT ${DM_COLS} FROM direct_messages
        WHERE ((sender_id=$1 AND recipient_id=$2) OR (sender_id=$2 AND recipient_id=$1)) AND id > $3
        ORDER BY id`, [req.user!.id, other, after]
    )
  );
  res.json({ messages: rows, me: req.user!.id });
});

// ── Phục vụ media của tin nhắn (chỉ người gửi/người nhận xem được) ─────────────
socialRouter.get("/api/messages/media/:id/:kind", requireAuth, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  const kind = req.params.kind; // image | video | doc
  if (Number.isNaN(id) || !["image", "video", "doc"].includes(kind)) return res.status(404).send("Not found");
  const rows = await query<DmMediaRow>(
    `SELECT sender_id, recipient_id, ${kind}_data AS data, ${kind}_mime AS mime, doc_original
       FROM direct_messages WHERE id=$1`, [id]
  );
  const m = rows[0];
  const me = req.user!.id;
  if (!m || !m.data) return res.status(404).send("Not found");
  if (m.sender_id !== me && m.recipient_id !== me) return res.status(403).send("Forbidden");

  if (kind === "video") {
    const buf: Buffer = m.data, total = buf.length;
    res.setHeader("Content-Type", m.mime || "video/mp4");
    res.setHeader("Accept-Ranges", "bytes");
    const range = req.headers.range;
    if (range) {
      const mt = /bytes=(\d*)-(\d*)/.exec(range);
      const start = mt && mt[1] ? parseInt(mt[1], 10) : 0;
      const end = mt && mt[2] ? parseInt(mt[2], 10) : total - 1;
      if (start > end || start >= total) { res.status(416).setHeader("Content-Range", `bytes */${total}`); return res.end(); }
      res.status(206);
      res.setHeader("Content-Range", `bytes ${start}-${end}/${total}`);
      res.setHeader("Content-Length", end - start + 1);
      return res.end(buf.subarray(start, end + 1));
    }
    res.setHeader("Content-Length", total);
    return res.end(buf);
  }

  res.setHeader("Content-Type", m.mime || "application/octet-stream");
  if (kind === "doc") {
    res.setHeader("Content-Disposition", `attachment; filename*=UTF-8''${encodeURIComponent(m.doc_original || "tai-lieu")}`);
  } else {
    res.setHeader("Cache-Control", "private, max-age=86400");
  }
  res.send(m.data);
});

// Danh sách bạn bè (cho hộp thoại "Chia sẻ vào tin nhắn").
socialRouter.get("/api/friends/list", requireAuth, async (req, res) => {
  const me = req.user!.id;
  const friends = await query<UserCard>(
    `SELECT u.id, u.name, (u.avatar_data IS NOT NULL) AS has_avatar
       FROM friendships f
       JOIN users u ON u.id = CASE WHEN f.requester_id = $1 THEN f.addressee_id ELSE f.requester_id END
      WHERE f.status = 'accepted' AND (f.requester_id = $1 OR f.addressee_id = $1) ORDER BY u.name`, [me]
  );
  res.json({ friends });
});

// ── Chia sẻ bài viết về trang cá nhân ─────────────────────────────────────────
socialRouter.post("/api/posts/:id/share", requireAuth, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id)) return res.status(400).json({ error: "Không hợp lệ." });
  // Lấy gốc thật: nếu bài này cũng là share thì trỏ về bài gốc đầu tiên.
  const src = await query<{ shared_from: number | null }>("SELECT shared_from FROM posts WHERE id = $1", [id]);
  if (!src.length) return res.status(404).json({ error: "Bài viết không tồn tại." });
  const origin = src[0].shared_from || id;
  const content = String(req.body?.content || "").trim().slice(0, 2000);
  await query("INSERT INTO posts (user_id, content, shared_from) VALUES ($1,$2,$3)", [req.user!.id, content, origin]);
  res.json({ ok: true });
});

// Lỗi từ multer (file quá lớn...) -> trả JSON rõ ràng thay vì trang HTML 500.
socialRouter.use((err: any, _req: any, res: any, next: any) => {
  if (err instanceof multer.MulterError) {
    const msg = err.code === "LIMIT_FILE_SIZE"
      ? "File quá lớn (tối đa 60MB cho video, nhỏ hơn cho ảnh/tài liệu)."
      : "Tải lên không hợp lệ: " + err.message;
    res.status(400).json({ error: msg });
    return;
  }
  next(err);
});
