import path from "node:path";
import { Router } from "express";
import jwt from "jsonwebtoken";
import multer from "multer";
import { query } from "../db/pool";
import { env } from "../config/env";
import { requireAdminAccess, ADM_VER } from "../middleware/auth";
import { authLimiter } from "../middleware/security";
import { parseYouTubeId } from "../services/social";
import { extractText, appendCatalogRow } from "../services/dataset";
import { AdminStats, AdminFileRow, AdminUserRow, AdminPostRow, BlobRow } from "../db/types";

export const adminRouter = Router();

const DOC_EXT = new Set([".pdf", ".doc", ".docx", ".xls", ".xlsx"]);
const extOf = (name: string) => path.extname(name || "").toLowerCase();
const utf8name = (name: string) => Buffer.from(name, "latin1").toString("utf8");
const adminUpload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 20 * 1024 * 1024 },
  fileFilter: (_req, file, cb) => cb(null, DOC_EXT.has(extOf(file.originalname))),
});
const PAGE_SIZE = 40;
const backTo = (req: { get(h: string): string | undefined }, fallback: string) =>
  req.get("referer") || fallback;

adminRouter.get("/login", (req, res) => {
  if (res.locals.isAdmin) return res.redirect("/admin");
  res.render("admin-login", { title: "Admin", error: "" });
});

adminRouter.post("/login", authLimiter, (req, res) => {
  if (String(req.body?.passcode || "") !== env.adminPasscode) {
    return res.status(401).render("admin-login", { title: "Admin", error: "Sai passcode." });
  }
  const token = jwt.sign({ adm: true, v: ADM_VER }, env.jwtSecret, { expiresIn: "1d" });
  res.cookie("adm", token, {
    httpOnly: true,
    sameSite: "lax",
    secure: env.isProd,
    maxAge: 24 * 60 * 60 * 1000,
  });
  res.redirect("/admin");
});

adminRouter.post("/logout", (_req, res) => {
  res.clearCookie("adm");
  res.redirect("/");
});

adminRouter.get("/", requireAdminAccess, async (_req, res) => {
  const [[stats], files, users, posts] = await Promise.all([
    query<AdminStats>(`SELECT
        (SELECT count(*) FROM users)::int          AS users,
        (SELECT count(*) FROM courses)::int        AS courses,
        (SELECT count(*) FROM enrollments)::int    AS enrollments,
        (SELECT count(*) FROM conversations)::int  AS conversations,
        (SELECT count(*) FROM messages)::int       AS messages,
        (SELECT count(*) FROM posts)::int          AS posts,
        (SELECT count(*) FROM post_comments)::int  AS comments,
        (SELECT count(*) FROM attachments)::int    AS attachments`),
    query<AdminFileRow>(
      `SELECT 'attachment' AS kind, a.id, a.filename AS name, a.mime, octet_length(a.data) AS bytes,
              u.email AS uploader, a.created_at, ('Khóa #' || a.course_id) AS context
         FROM attachments a LEFT JOIN users u ON u.id = a.user_id
       UNION ALL
       SELECT 'post-image', p.id, 'ảnh bài viết', p.image_mime, octet_length(p.image_data),
              u.email, p.created_at, ('Bài #' || p.id)
         FROM posts p JOIN users u ON u.id = p.user_id WHERE p.image_data IS NOT NULL
       UNION ALL
       SELECT 'post-doc', p.id, p.doc_original, p.doc_mime, octet_length(p.doc_data),
              u.email, p.created_at, ('Bài #' || p.id)
         FROM posts p JOIN users u ON u.id = p.user_id WHERE p.doc_data IS NOT NULL
       ORDER BY created_at DESC`,
    ),
    query<AdminUserRow>("SELECT id, name, email, role, created_at FROM users ORDER BY id"),
    query<AdminPostRow>(
      `SELECT p.id, u.name AS author, left(p.content, 60) AS content, p.created_at,
              (p.image_data IS NOT NULL) AS img, p.doc_original AS doc
         FROM posts p JOIN users u ON u.id = p.user_id ORDER BY p.id DESC`,
    ),
  ]);
  res.render("admin", { title: "Quản trị", stats, files, users, posts });
});

adminRouter.get("/file/:kind/:id/download", requireAdminAccess, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  const kind = req.params.kind;
  if (Number.isNaN(id)) return res.status(404).send("Not found");
  let row: BlobRow | undefined;
  if (kind === "attachment") {
    row = (
      await query<BlobRow>("SELECT filename, mime, data FROM attachments WHERE id=$1", [id])
    )[0];
  } else if (kind === "post-image") {
    row = (
      await query<BlobRow>(
        "SELECT 'image' AS filename, image_mime AS mime, image_data AS data FROM posts WHERE id=$1",
        [id],
      )
    )[0];
  } else if (kind === "post-doc") {
    row = (
      await query<BlobRow>(
        "SELECT doc_original AS filename, doc_mime AS mime, doc_data AS data FROM posts WHERE id=$1",
        [id],
      )
    )[0];
  }
  if (!row || !row.data) return res.status(404).send("Not found");
  res.setHeader("Content-Type", row.mime || "application/octet-stream");
  res.setHeader(
    "Content-Disposition",
    `attachment; filename*=UTF-8''${encodeURIComponent(row.filename || "file")}`,
  );
  res.send(row.data);
});

adminRouter.post("/file/:kind/:id/delete", requireAdminAccess, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  const kind = req.params.kind;
  if (!Number.isNaN(id)) {
    if (kind === "attachment") await query("DELETE FROM attachments WHERE id=$1", [id]);
    else if (kind === "post-image")
      await query("UPDATE posts SET image_data=NULL, image_mime=NULL WHERE id=$1", [id]);
    else if (kind === "post-doc")
      await query("UPDATE posts SET doc_data=NULL, doc_mime=NULL, doc_original=NULL WHERE id=$1", [
        id,
      ]);
  }
  res.redirect("/admin");
});

adminRouter.post("/user/:id/role", requireAdminAccess, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (!Number.isNaN(id))
    await query(
      "UPDATE users SET role = CASE WHEN role='admin' THEN 'user' ELSE 'admin' END WHERE id=$1",
      [id],
    );
  res.redirect("/admin");
});

adminRouter.post("/user/:id/delete", requireAdminAccess, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (!Number.isNaN(id)) await query("DELETE FROM users WHERE id=$1", [id]);
  res.redirect("/admin");
});

adminRouter.post("/post/:id/delete", requireAdminAccess, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (!Number.isNaN(id)) await query("DELETE FROM posts WHERE id=$1", [id]);
  res.redirect("/admin");
});

interface CatalogItem {
  item_id: number;
  title: string;
  category: string;
  level: string | null;
  n: number;
  pending: number;
}

async function renderCatalog(
  req: import("express").Request,
  res: import("express").Response,
  kind: "course" | "doc",
) {
  const type = kind === "course" ? "Khóa học" : "Tài liệu";
  const q = String(req.query.q || "").trim();
  const page = Math.max(1, parseInt(String(req.query.page || "1"), 10) || 1);
  const params: unknown[] = [type];
  let where = "type = $1";
  if (q) {
    params.push("%" + q + "%");
    where += ` AND title ILIKE $${params.length}`;
  }
  const [{ total }] = await query<{ total: number }>(
    `SELECT count(*)::int AS total FROM courses WHERE ${where}`,
    params,
  );
  const items = await query<CatalogItem>(
    `SELECT item_id, title, category, level FROM courses WHERE ${where} ORDER BY item_id LIMIT ${PAGE_SIZE} OFFSET ${(page - 1) * PAGE_SIZE}`,
    params,
  );
  const ids = items.map((i) => i.item_id);
  if (ids.length) {
    const tbl = kind === "course" ? "lessons" : "attachments";
    const counts = await query<{ course_id: number; n: number; pending: number }>(
      `SELECT course_id, count(*)::int AS n, count(*) FILTER (WHERE NOT approved)::int AS pending
         FROM ${tbl} WHERE course_id = ANY($1::int[]) GROUP BY course_id`,
      [ids],
    );
    const map: Record<number, { n: number; pending: number }> = {};
    counts.forEach((c) => {
      map[c.course_id] = { n: c.n, pending: c.pending };
    });
    items.forEach((it) => {
      it.n = map[it.item_id]?.n || 0;
      it.pending = map[it.item_id]?.pending || 0;
    });
  }
  res.render("admin-catalog", {
    title: kind === "course" ? "Khóa học" : "Mục tài liệu",
    kind,
    items,
    q,
    page,
    pages: Math.max(1, Math.ceil(total / PAGE_SIZE)),
    total,
  });
}
adminRouter.get("/courses", requireAdminAccess, (req, res) => renderCatalog(req, res, "course"));
adminRouter.get("/docs", requireAdminAccess, (req, res) => renderCatalog(req, res, "doc"));

async function renderManage(
  req: import("express").Request,
  res: import("express").Response,
  kind: "course" | "doc",
) {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id))
    return res.status(404).render("error", { title: "404", message: "Không hợp lệ." });
  const [course] = await query(
    "SELECT item_id, title, type, category, level, description, platform, instructor, link FROM courses WHERE item_id = $1",
    [id],
  );
  if (!course)
    return res.status(404).render("error", { title: "404", message: "Không tìm thấy mục này." });
  let lessons: unknown[] = [],
    attachments: unknown[] = [];
  if (kind === "course") {
    lessons = await query(
      "SELECT id, title, youtube_id, approved FROM lessons WHERE course_id = $1 ORDER BY approved, id",
      [id],
    );
  } else {
    attachments = await query(
      `SELECT a.id, a.filename, a.mime, a.size, a.approved, u.email AS uploader
         FROM attachments a LEFT JOIN users u ON u.id = a.user_id WHERE a.course_id = $1 ORDER BY a.approved, a.id DESC`,
      [id],
    );
  }
  res.render("admin-manage", { title: course.title, kind, course, lessons, attachments });
}
adminRouter.get("/courses/:id", requireAdminAccess, (req, res) => renderManage(req, res, "course"));
adminRouter.get("/docs/:id", requireAdminAccess, (req, res) => renderManage(req, res, "doc"));

adminRouter.post("/courses/:id/lessons", requireAdminAccess, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  const ytId = parseYouTubeId(String(req.body?.url || ""));
  const title =
    String(req.body?.title || "")
      .trim()
      .slice(0, 200) || "Bài học video";
  if (!Number.isNaN(id) && ytId) {
    await query(
      "INSERT INTO lessons (course_id, title, youtube_id, approved) VALUES ($1,$2,$3,true)",
      [id, title, ytId],
    );
  }
  res.redirect("/admin/courses/" + id);
});

adminRouter.post(
  "/docs/:id/attachments",
  requireAdminAccess,
  adminUpload.single("file"),
  async (req, res) => {
    const id = parseInt(req.params.id, 10);
    if (!Number.isNaN(id) && req.file) {
      const original = utf8name(req.file.originalname);
      const text = await extractText(req.file.buffer, extOf(original));
      await query(
        `INSERT INTO attachments (course_id, user_id, filename, mime, size, data, extracted_text, approved)
         VALUES ($1,NULL,$2,$3,$4,$5,$6,true)`,
        [id, original, req.file.mimetype, req.file.size, req.file.buffer, text || null],
      );
      appendCatalogRow({
        title: original,
        description: text || original,
        type: "Tài liệu",
        category: "Tài liệu cộng đồng",
        instructor: "Admin",
        platform: `Khóa học #${id}`,
      }).catch((e) => console.error("[csv]", e.message));
    }
    res.redirect("/admin/docs/" + id);
  },
);

adminRouter.get("/pending", requireAdminAccess, async (_req, res) => {
  const [lessons, attachments] = await Promise.all([
    query(`SELECT l.id, l.title, l.youtube_id, l.course_id, c.title AS course_title, u.email AS uploader
             FROM lessons l JOIN courses c ON c.item_id = l.course_id LEFT JOIN users u ON u.id = l.added_by
            WHERE NOT l.approved ORDER BY l.id`),
    query(`SELECT a.id, a.filename, a.mime, a.size, a.course_id, c.title AS course_title, u.email AS uploader
             FROM attachments a JOIN courses c ON c.item_id = a.course_id LEFT JOIN users u ON u.id = a.user_id
            WHERE NOT a.approved ORDER BY a.id`),
  ]);
  res.render("admin-pending", { title: "Chờ duyệt", lessons, attachments });
});

adminRouter.post("/lessons/:id/approve", requireAdminAccess, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (!Number.isNaN(id)) await query("UPDATE lessons SET approved = true WHERE id = $1", [id]);
  res.redirect(backTo(req, "/admin/pending"));
});
adminRouter.post("/lessons/:id/delete", requireAdminAccess, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (!Number.isNaN(id)) await query("DELETE FROM lessons WHERE id = $1", [id]);
  res.redirect(backTo(req, "/admin/pending"));
});
adminRouter.post("/attachments/:id/approve", requireAdminAccess, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (!Number.isNaN(id)) {
    const r = await query<{ filename: string; course_id: number; extracted_text: string | null }>(
      "UPDATE attachments SET approved = true WHERE id = $1 RETURNING filename, course_id, extracted_text",
      [id],
    );
    if (r[0])
      appendCatalogRow({
        title: r[0].filename,
        description: r[0].extracted_text || r[0].filename,
        type: "Tài liệu",
        category: "Tài liệu cộng đồng",
        instructor: "Đóng góp",
        platform: `Khóa học #${r[0].course_id}`,
      }).catch((e) => console.error("[csv]", e.message));
  }
  res.redirect(backTo(req, "/admin/pending"));
});
adminRouter.post("/attachments/:id/delete", requireAdminAccess, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (!Number.isNaN(id)) await query("DELETE FROM attachments WHERE id = $1", [id]);
  res.redirect(backTo(req, "/admin/pending"));
});
