import path from "node:path";
import { Router, Request, Response, NextFunction } from "express";
import multer from "multer";
import { z } from "zod";
import { query } from "../db/pool";
import { requireAuth } from "../middleware/auth";
import { recommender } from "../services/recommender";
import { renderMd, googleRefs } from "../services/markdown";
import { extractText, appendCatalogRow } from "../services/dataset";
import { addClient, broadcast, sendToUser, isOnline } from "../services/realtime";
import { acceptedFriendIds } from "../services/social";

export const apiRouter = Router();

apiRouter.get("/realtime", requireAuth, async (req, res) => {
  res.status(200).set({
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache, no-transform",
    Connection: "keep-alive",
    "X-Accel-Buffering": "no",
  });
  (res as any).flushHeaders?.();
  res.write("retry: 5000\n\n");
  res.write('event: ready\ndata: {"ok":true}\n\n');

  const uid = req.user!.id;
  const wasOnline = isOnline(uid);
  const remove = addClient(uid, res);

  try {
    const friends = await acceptedFriendIds(uid);
    if (!wasOnline) {
      await query("UPDATE users SET last_seen = now() WHERE id = $1", [uid]);
      friends.forEach((fid) => sendToUser(fid, "presence", { user: uid, online: true }));
    }
    const online = friends.filter((fid) => isOnline(fid));
    res.write(`event: presence_snapshot\ndata: ${JSON.stringify({ online })}\n\n`);
  } catch {  }

  const ping = setInterval(() => { try { res.write(": ping\n\n"); } catch {  } }, 25000);
  req.on("close", async () => {
    clearInterval(ping);
    remove();
    if (!isOnline(uid)) {
      try {
        await query("UPDATE users SET last_seen = now() WHERE id = $1", [uid]);
        const friends = await acceptedFriendIds(uid);
        const at = new Date().toISOString();
        friends.forEach((fid) => sendToUser(fid, "presence", { user: uid, online: false, last_seen: at }));
      } catch {  }
    }
  });
});

const chatSchema = z.object({
  message: z.string().trim().min(1),
  history: z.array(z.object({ role: z.string(), content: z.string() })).max(20).optional(),
  conversation_id: z.coerce.number().int().optional(),
});

apiRouter.post("/chat", requireAuth, async (req, res) => {
  const parsed = chatSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Thiếu nội dung tin nhắn." });
  const { message, history = [], conversation_id } = parsed.data;

  let data;
  try {
    data = await recommender.chat(message, history);
  } catch {
    return res.status(502).json({ error: "Không kết nối được trợ lý (recommender :8000)." });
  }

  let convId = conversation_id;
  if (req.user) {
    try {
      const uid = req.user.id;
      if (convId) {
        const own = await query("SELECT 1 FROM conversations WHERE id = $1 AND user_id = $2", [convId, uid]);
        if (!own.length) convId = undefined;
      }
      if (!convId) {
        const title = message.slice(0, 60) || "Cuộc trò chuyện mới";
        const rows = await query<{ id: number }>(
          "INSERT INTO conversations (user_id, title) VALUES ($1, $2) RETURNING id", [uid, title]
        );
        convId = rows[0].id;
      }
      await query("INSERT INTO messages (conversation_id, role, content) VALUES ($1,'user',$2)", [convId, message]);
      await query("INSERT INTO messages (conversation_id, role, content) VALUES ($1,'assistant',$2)", [convId, data.response || ""]);
      await query("UPDATE conversations SET updated_at = now() WHERE id = $1", [convId]);
    } catch (e) {
      console.warn("[chat] bỏ qua lưu lịch sử (có thể cookie cũ / user không tồn tại):", (e as Error).message);
      convId = undefined;
    }
  }

  res.json({
    response: data.response,
    response_html: renderMd(data.response || ""),
    recommendations: data.recommendations,
    intent: data.intent,
    references: googleRefs(message),
    conversation_id: convId ?? null,
  });
});

apiRouter.get("/conversations", requireAuth, async (req, res) => {
  const rows = await query(
    "SELECT id, title, updated_at FROM conversations WHERE user_id = $1 ORDER BY updated_at DESC LIMIT 50",
    [req.user!.id]
  );
  res.json(rows);
});

apiRouter.delete("/conversations/:id", requireAuth, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id)) return res.status(400).json({ error: "ID không hợp lệ." });
  await query("DELETE FROM conversations WHERE id = $1 AND user_id = $2", [id, req.user!.id]);
  res.json({ ok: true });
});

const saveSchema = z.object({
  course_id: z.coerce.number().int(),
  status: z.enum(["saved", "in_progress", "completed"]).optional(),
  progress: z.coerce.number().int().min(0).max(100).optional(),
});

apiRouter.post("/save", requireAuth, async (req, res) => {
  const parsed = saveSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Dữ liệu không hợp lệ." });
  const { course_id, status = "saved", progress = 0 } = parsed.data;

  const exists = await query("SELECT 1 FROM courses WHERE item_id = $1", [course_id]);
  if (!exists.length) return res.status(404).json({ error: "Khóa học không tồn tại." });

  const rows = await query<{ status: string; progress: number }>(
    `INSERT INTO enrollments (user_id, course_id, status, progress, updated_at)
       VALUES ($1, $2, $3, $4, now())
     ON CONFLICT (user_id, course_id)
       DO UPDATE SET status = EXCLUDED.status, progress = EXCLUDED.progress, updated_at = now()
     RETURNING status, progress`,
    [req.user!.id, course_id, status, progress]
  );
  res.json({ ok: true, enrollment: rows[0] });
});

apiRouter.post("/unsave", requireAuth, async (req, res) => {
  const id = parseInt(req.body?.course_id, 10);
  if (Number.isNaN(id)) return res.status(400).json({ error: "Thiếu course_id." });
  await query("DELETE FROM enrollments WHERE user_id = $1 AND course_id = $2", [req.user!.id, id]);
  res.json({ ok: true });
});

const ALLOWED = new Set([".pdf", ".doc", ".docx", ".xls", ".xlsx"]);
const IMG_EXT = new Set([".jpg", ".jpeg", ".png", ".gif", ".webp"]);
const extOf = (name: string) => path.extname(name || "").toLowerCase();
const utf8name = (name: string) => Buffer.from(name, "latin1").toString("utf8");

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 10 * 1024 * 1024 },
  fileFilter: (_req, file, cb) => cb(null, ALLOWED.has(extOf(file.originalname))),
});

apiRouter.post("/courses/:id/attachments", requireAuth, upload.single("file"), async (req, res) => {
  const courseId = parseInt(req.params.id, 10);
  if (Number.isNaN(courseId)) return res.status(400).json({ error: "Khóa học không hợp lệ." });
  if (!req.file) return res.status(400).json({ error: "Chỉ nhận file PDF, DOCX, XLS/XLSX (≤ 10MB)." });

  const exists = await query("SELECT 1 FROM courses WHERE item_id = $1", [courseId]);
  if (!exists.length) return res.status(404).json({ error: "Khóa học không tồn tại." });

  const original = utf8name(req.file.originalname);
  const text = await extractText(req.file.buffer, extOf(original));
  const approved = req.user!.role === "admin";
  const rows = await query(
    `INSERT INTO attachments (course_id, user_id, filename, mime, size, data, extracted_text, approved)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id, filename, mime, size, created_at`,
    [courseId, req.user!.id, original, req.file.mimetype, req.file.size, req.file.buffer, text || null, approved]
  );
  if (!approved) return res.json({ ok: true, pending: true });
  appendCatalogRow({
    title: original, description: text || original, type: "Tài liệu",
    category: "Tài liệu cộng đồng", instructor: req.user!.name, platform: `Khóa học #${courseId}`,
  }).catch((e) => console.error("[csv]", e.message));
  res.json({ ok: true, attachment: rows[0] });
});

apiRouter.delete("/attachments/:id", requireAuth, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id)) return res.status(400).json({ error: "ID không hợp lệ." });
  const rows = await query<{ user_id: number }>("SELECT user_id FROM attachments WHERE id = $1", [id]);
  const a = rows[0];
  if (!a) return res.status(404).json({ error: "Không tìm thấy file." });
  if (a.user_id !== req.user!.id && req.user!.role !== "admin")
    return res.status(403).json({ error: "Không có quyền xóa file này." });
  await query("DELETE FROM attachments WHERE id = $1", [id]);
  res.json({ ok: true });
});

apiRouter.get("/download/:id", requireAuth, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id)) return res.status(404).send("Not found");
  const rows = await query<{ filename: string; mime: string | null; data: Buffer }>(
    "SELECT filename, mime, data FROM attachments WHERE id = $1", [id]
  );
  const a = rows[0];
  if (!a) return res.status(404).send("Not found");
  res.setHeader("Content-Type", a.mime || "application/octet-stream");
  res.setHeader("Content-Disposition", `attachment; filename*=UTF-8''${encodeURIComponent(a.filename)}`);
  res.send(a.data);
});

apiRouter.get("/attachment/:id/inline", requireAuth, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id)) return res.status(404).send("Not found");
  const rows = await query<{ filename: string; mime: string | null; data: Buffer }>(
    "SELECT filename, mime, data FROM attachments WHERE id = $1", [id]
  );
  const a = rows[0];
  if (!a) return res.status(404).send("Not found");
  res.setHeader("Content-Type", a.mime || "application/octet-stream");
  res.setHeader("Content-Disposition", `inline; filename*=UTF-8''${encodeURIComponent(a.filename)}`);
  res.send(a.data);
});

apiRouter.get("/attachment/:id/text", requireAuth, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id)) return res.status(404).json({ error: "Not found" });
  const rows = await query<{ extracted_text: string | null; filename: string }>(
    "SELECT extracted_text, filename FROM attachments WHERE id = $1", [id]
  );
  const a = rows[0];
  if (!a) return res.status(404).json({ error: "Not found" });
  res.json({ filename: a.filename, text: a.extracted_text || "(Không trích xuất được nội dung văn bản từ file này.)" });
});

const postUpload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 60 * 1024 * 1024 },
  fileFilter: (_req, file, cb) => {
    const e = extOf(file.originalname);
    if (file.fieldname === "image") cb(null, IMG_EXT.has(e));
    else if (file.fieldname === "video") cb(null, /^video\//.test(file.mimetype));
    else if (file.fieldname === "doc") cb(null, ALLOWED.has(e));
    else cb(null, false);
  },
});

apiRouter.post(
  "/posts",
  requireAuth,
  postUpload.fields([{ name: "image", maxCount: 1 }, { name: "video", maxCount: 1 }, { name: "doc", maxCount: 1 }]),
  async (req, res) => {
    const content = String(req.body?.content || "").trim().slice(0, 5000);
    const files = req.files as { [k: string]: Express.Multer.File[] } | undefined;
    const image = files?.image?.[0];
    const video = files?.video?.[0];
    const doc = files?.doc?.[0];
    if (!content && !image && !video && !doc) return res.status(400).json({ error: "Hãy nhập nội dung hoặc đính kèm ảnh/video/tài liệu." });

    const docOriginal = doc ? utf8name(doc.originalname) : null;
    const rows = await query<{ id: number; created_at: string }>(
      `INSERT INTO posts (user_id, content, image_data, image_mime, video_data, video_mime, doc_data, doc_mime, doc_original)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id, created_at`,
      [req.user!.id, content, image?.buffer || null, image?.mimetype || null,
       video?.buffer || null, video?.mimetype || null, doc?.buffer || null, doc?.mimetype || null, docOriginal]
    );
    if (doc) {
      const text = await extractText(doc.buffer, extOf(doc.originalname));
      appendCatalogRow({
        title: docOriginal!, description: text || docOriginal!, type: "Tài liệu",
        category: "Tài liệu cộng đồng", instructor: req.user!.name, platform: "Cộng đồng",
      }).catch((e) => console.error("[csv]", e.message));
    }
    res.json({
      ok: true,
      post: {
        id: rows[0].id, content, author: req.user!.name,
        has_image: !!image, has_doc: !!doc, doc_original: docOriginal,
        likes: 0, liked: false, comments: [], created_at: rows[0].created_at, user_id: req.user!.id,
      },
    });
    broadcast("post_new", { id: rows[0].id, author: req.user!.name }, req.user!.id);
  }
);

apiRouter.get("/media/post/:id/image", requireAuth, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id)) return res.status(404).send("Not found");
  const rows = await query<{ image_data: Buffer | null; image_mime: string | null }>(
    "SELECT image_data, image_mime FROM posts WHERE id = $1", [id]
  );
  const p = rows[0];
  if (!p || !p.image_data) return res.status(404).send("Not found");
  res.setHeader("Content-Type", p.image_mime || "application/octet-stream");
  res.setHeader("Cache-Control", "private, max-age=86400");
  res.send(p.image_data);
});

apiRouter.get("/media/post/:id/doc", requireAuth, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id)) return res.status(404).send("Not found");
  const rows = await query<{ doc_data: Buffer | null; doc_mime: string | null; doc_original: string | null }>(
    "SELECT doc_data, doc_mime, doc_original FROM posts WHERE id = $1", [id]
  );
  const p = rows[0];
  if (!p || !p.doc_data) return res.status(404).send("Not found");
  res.setHeader("Content-Type", p.doc_mime || "application/octet-stream");
  res.setHeader("Content-Disposition", `attachment; filename*=UTF-8''${encodeURIComponent(p.doc_original || "tai-lieu")}`);
  res.send(p.doc_data);
});

apiRouter.get("/media/post/:id/video", requireAuth, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id)) return res.status(404).send("Not found");
  const rows = await query<{ video_data: Buffer | null; video_mime: string | null }>(
    "SELECT video_data, video_mime FROM posts WHERE id = $1", [id]
  );
  const p = rows[0];
  if (!p || !p.video_data) return res.status(404).send("Not found");
  const buf = p.video_data, total = buf.length;
  res.setHeader("Content-Type", p.video_mime || "video/mp4");
  res.setHeader("Accept-Ranges", "bytes");
  const range = req.headers.range;
  if (range) {
    const m = /bytes=(\d*)-(\d*)/.exec(range);
    const start = m && m[1] ? parseInt(m[1], 10) : 0;
    const end = m && m[2] ? parseInt(m[2], 10) : total - 1;
    if (start > end || start >= total) {
      res.status(416).setHeader("Content-Range", `bytes */${total}`);
      return res.end();
    }
    res.status(206);
    res.setHeader("Content-Range", `bytes ${start}-${end}/${total}`);
    res.setHeader("Content-Length", end - start + 1);
    return res.end(buf.subarray(start, end + 1));
  }
  res.setHeader("Content-Length", total);
  res.end(buf);
});

apiRouter.post("/posts/:id/like", requireAuth, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id)) return res.status(400).json({ error: "ID không hợp lệ." });
  const uid = req.user!.id;
  const has = await query("SELECT 1 FROM post_likes WHERE post_id = $1 AND user_id = $2", [id, uid]);
  let liked: boolean;
  if (has.length) {
    await query("DELETE FROM post_likes WHERE post_id = $1 AND user_id = $2", [id, uid]);
    liked = false;
  } else {
    await query("INSERT INTO post_likes (post_id, user_id) VALUES ($1,$2) ON CONFLICT DO NOTHING", [id, uid]);
    liked = true;
  }
  const [{ n }] = await query<{ n: number }>("SELECT count(*)::int AS n FROM post_likes WHERE post_id = $1", [id]);
  res.json({ ok: true, liked, count: n });
  broadcast("post_like", { postId: id, count: n });
});

apiRouter.post("/posts/:id/comments", requireAuth, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  const content = String(req.body?.content || "").trim().slice(0, 2000);
  if (Number.isNaN(id) || !content) return res.status(400).json({ error: "Bình luận trống." });
  const rows = await query<{ id: number; created_at: string }>(
    "INSERT INTO post_comments (post_id, user_id, content) VALUES ($1,$2,$3) RETURNING id, created_at",
    [id, req.user!.id, content]
  );
  res.json({ ok: true, comment: { id: rows[0].id, author: req.user!.name, content, created_at: rows[0].created_at } });
  broadcast("post_comment", { postId: id, author: req.user!.name, content }, req.user!.id);
});

apiRouter.delete("/posts/:id", requireAuth, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id)) return res.status(400).json({ error: "ID không hợp lệ." });
  const rows = await query<{ user_id: number }>("SELECT user_id FROM posts WHERE id = $1", [id]);
  const p = rows[0];
  if (!p) return res.status(404).json({ error: "Không tìm thấy bài viết." });
  if (p.user_id !== req.user!.id && req.user!.role !== "admin")
    return res.status(403).json({ error: "Không có quyền xóa bài này." });
  await query("DELETE FROM posts WHERE id = $1", [id]);
  res.json({ ok: true });
});

async function recomputeProgress(userId: number, courseId: number): Promise<{ progress: number; status: string }> {
  const [{ total }] = await query<{ total: number }>("SELECT count(*)::int AS total FROM lessons WHERE course_id = $1 AND approved", [courseId]);
  const [{ done }] = await query<{ done: number }>(
    `SELECT count(*)::int AS done FROM lesson_progress lp JOIN lessons l ON l.id = lp.lesson_id
      WHERE l.course_id = $1 AND lp.user_id = $2`, [courseId, userId]
  );
  const progress = total > 0 ? Math.round((done / total) * 100) : 0;
  const status = progress >= 100 && total > 0 ? "completed" : progress > 0 ? "in_progress" : "saved";
  await query(
    `INSERT INTO enrollments (user_id, course_id, status, progress, updated_at)
       VALUES ($1,$2,$3,$4,now())
     ON CONFLICT (user_id, course_id) DO UPDATE SET status = EXCLUDED.status, progress = EXCLUDED.progress, updated_at = now()`,
    [userId, courseId, status, progress]
  );
  return { progress, status };
}

apiRouter.post("/courses/:id/lessons", requireAuth, async (req, res) => {
  const courseId = parseInt(req.params.id, 10);
  const { parseYouTubeId } = await import("../services/social");
  const ytId = parseYouTubeId(String(req.body?.url || ""));
  const title = String(req.body?.title || "").trim().slice(0, 200) || "Bài học video";
  if (Number.isNaN(courseId) || !ytId) return res.status(400).json({ error: "Link YouTube không hợp lệ." });
  const exists = await query("SELECT 1 FROM courses WHERE item_id = $1", [courseId]);
  if (!exists.length) return res.status(404).json({ error: "Khóa học không tồn tại." });
  const approved = req.user!.role === "admin";
  const rows = await query<{ id: number }>(
    "INSERT INTO lessons (course_id, title, youtube_id, added_by, approved) VALUES ($1,$2,$3,$4,$5) RETURNING id",
    [courseId, title, ytId, req.user!.id, approved]
  );
  if (!approved) return res.json({ ok: true, pending: true });
  res.json({ ok: true, lesson: { id: rows[0].id, title, youtube_id: ytId, done: false } });
});

apiRouter.post("/lessons/:id/complete", requireAuth, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id)) return res.status(400).json({ error: "ID không hợp lệ." });
  const rows = await query<{ course_id: number }>("SELECT course_id FROM lessons WHERE id = $1", [id]);
  if (!rows.length) return res.status(404).json({ error: "Bài học không tồn tại." });
  const undo = req.body?.undo === true || req.body?.undo === "true";
  if (undo) await query("DELETE FROM lesson_progress WHERE user_id = $1 AND lesson_id = $2", [req.user!.id, id]);
  else await query("INSERT INTO lesson_progress (user_id, lesson_id) VALUES ($1,$2) ON CONFLICT DO NOTHING", [req.user!.id, id]);
  const p = await recomputeProgress(req.user!.id, rows[0].course_id);
  res.json({ ok: true, done: !undo, ...p });
});

apiRouter.delete("/lessons/:id", requireAuth, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id)) return res.status(400).json({ error: "ID không hợp lệ." });
  const rows = await query<{ course_id: number; added_by: number | null }>(
    "SELECT course_id, added_by FROM lessons WHERE id = $1", [id]
  );
  const l = rows[0];
  if (!l) return res.status(404).json({ error: "Không tìm thấy." });
  if (l.added_by !== req.user!.id && req.user!.role !== "admin")
    return res.status(403).json({ error: "Không có quyền xóa bài học này." });
  await query("DELETE FROM lessons WHERE id = $1", [id]);
  const p = await recomputeProgress(req.user!.id, l.course_id);
  res.json({ ok: true, ...p });
});

apiRouter.use((err: unknown, _req: Request, res: Response, next: NextFunction) => {
  if (err instanceof multer.MulterError) {
    const msg = err.code === "LIMIT_FILE_SIZE"
      ? "File quá lớn (ảnh ≤ 15MB, tài liệu ≤ 10MB)."
      : "Tải lên không hợp lệ: " + err.message;
    res.status(400).json({ error: msg });
    return;
  }
  next(err);
});
