import { Router } from "express";
import { query } from "../db/pool";
import { requireAuth } from "../middleware/auth";
import { recommender, RecItem } from "../services/recommender";
import { renderMd } from "../services/markdown";
import { fetchPosts } from "../services/posts";
import { LessonRow } from "../db/types";

const LEVELS = ["Cơ bản", "Trung cấp", "Nâng cao"];

export const pagesRouter = Router();

interface Course {
  item_id: number;
  title: string;
  type: string;
  level: string | null;
  description: string;
  category: string;
  topics: string;
  instructor: string;
  platform: string;
  link: string;
}

async function savedIdSet(userId?: number): Promise<Set<number>> {
  if (!userId) return new Set<number>();
  const rows = await query<{ course_id: number }>(
    "SELECT course_id FROM enrollments WHERE user_id = $1",
    [userId],
  );
  return new Set(rows.map((r) => r.course_id));
}

pagesRouter.get("/", async (_req, res) => {
  const categories = await query<{ category: string; n: number }>(
    "SELECT category, count(*)::int AS n FROM courses WHERE category IS NOT NULL GROUP BY category ORDER BY n DESC LIMIT 8",
  );
  let prompts: string[] = [];
  try {
    prompts = (await recommender.suggested()).prompts;
  } catch {}
  res.render("home", { title: "Nền tảng học tập CNTT", categories, prompts });
});

pagesRouter.get("/search", async (req, res) => {
  const q = (req.query.q as string | undefined)?.trim() || "";
  const type = (req.query.type as string | undefined) || "";
  const level = ((req.query.level as string | undefined) || "").normalize("NFC");
  let minPct = parseInt((req.query.min_pct as string) || "90", 10);
  if (Number.isNaN(minPct)) minPct = 90;
  minPct = Math.min(100, Math.max(85, minPct));
  const savedIds = await savedIdSet(req.user?.id);
  const base = { q, type, level, levels: LEVELS, minPct, savedIds };
  if (!q) {
    return res.render("search", { title: "Tìm kiếm", data: null, recError: false, ...base });
  }
  try {
    const data = await recommender.search(q, type || null, minPct);
    if (level)
      data.results = data.results.filter((r) => (r.level || "").normalize("NFC") === level);
    res.render("search", { title: `Tìm: ${q}`, data, recError: false, ...base });
  } catch {
    res.render("search", { title: `Tìm: ${q}`, data: null, recError: true, ...base });
  }
});

pagesRouter.get("/courses/:id", async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id))
    return res.status(404).render("error", { title: "404", message: "Khóa học không tồn tại." });

  const rows = await query<Course>("SELECT * FROM courses WHERE item_id = $1", [id]);
  const course = rows[0];
  if (!course)
    return res
      .status(404)
      .render("error", { title: "404", message: "Không tìm thấy khóa học này." });

  let related: RecItem[] = [];
  try {
    related = (await recommender.search(course.title, null, 88)).results
      .filter((r) => r.item_id !== id)
      .slice(0, 4);
  } catch {}

  let enrollment: { status: string; progress: number } | null = null;
  if (req.user) {
    const er = await query<{ status: string; progress: number }>(
      "SELECT status, progress FROM enrollments WHERE user_id = $1 AND course_id = $2",
      [req.user.id, id],
    );
    enrollment = er[0] || null;
  }
  const savedIds = await savedIdSet(req.user?.id);
  const attachments = await query(
    `SELECT id, filename, mime, size,
            (extracted_text IS NOT NULL AND extracted_text <> '') AS has_text
       FROM attachments WHERE course_id = $1 AND approved ORDER BY id DESC`,
    [id],
  );
  const lessons = await query<LessonRow>(
    `SELECT l.id, l.title, l.youtube_id, l.added_by,
            EXISTS(SELECT 1 FROM lesson_progress lp WHERE lp.lesson_id = l.id AND lp.user_id = $2) AS done
       FROM lessons l WHERE l.course_id = $1 AND l.approved ORDER BY l.id`,
    [id, req.user?.id ?? 0],
  );
  res.render("course", {
    title: course.title,
    course,
    related,
    enrollment,
    savedIds,
    attachments,
    lessons,
  });
});

pagesRouter.get("/dashboard", requireAuth, async (req, res) => {
  const userId = req.user!.id;
  const saved = await query<Course & { status: string; progress: number }>(
    `SELECT c.*, e.status, e.progress
       FROM enrollments e JOIN courses c ON c.item_id = e.course_id
      WHERE e.user_id = $1
      ORDER BY e.updated_at DESC`,
    [userId],
  );

  let forYou: RecItem[] = [];
  let recError = false;
  try {
    const personas = await recommender.personas();
    const persona = personas[0]?.uid ?? 0;
    const interested = saved.map((c) => c.item_id);
    forYou = (await recommender.forYou(persona, interested)).recs.slice(0, 8);
  } catch {
    recError = true;
  }
  const savedIds = new Set(saved.map((c) => c.item_id));
  res.render("dashboard", { title: "Bảng điều khiển", saved, forYou, recError, savedIds });
});

pagesRouter.get("/blog", requireAuth, async (req, res) => {
  const posts = await fetchPosts(req.user!.id);
  res.render("blog", { title: "Cộng đồng IT", posts });
});

pagesRouter.get("/blog/:id", requireAuth, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (Number.isNaN(id))
    return res.status(404).render("error", { title: "404", message: "Bài viết không hợp lệ." });
  const posts = await fetchPosts(req.user!.id, undefined, id);
  if (!posts.length)
    return res
      .status(404)
      .render("error", { title: "404", message: "Bài viết không tồn tại hoặc đã bị xóa." });
  res.render("blog", { title: "Bài viết cộng đồng", posts, single: true });
});

pagesRouter.get("/chat", requireAuth, async (req, res) => {
  const uid = req.user!.id;
  let prompts: string[] = [];
  try {
    prompts = (await recommender.suggested()).prompts;
  } catch {}

  const conversations = await query(
    "SELECT id, title, updated_at FROM conversations WHERE user_id = $1 ORDER BY updated_at DESC LIMIT 50",
    [uid],
  );

  let messages: { role: string; html: string | null; content: string }[] = [];
  let activeId: number | null = null;
  const c = parseInt(req.query.c as string, 10);
  if (!Number.isNaN(c)) {
    const own = await query("SELECT 1 FROM conversations WHERE id = $1 AND user_id = $2", [c, uid]);
    if (own.length) {
      activeId = c;
      const rows = await query<{ role: string; content: string }>(
        "SELECT role, content FROM messages WHERE conversation_id = $1 ORDER BY id",
        [c],
      );
      messages = rows.map((m) => ({
        role: m.role,
        content: m.content,
        html: m.role === "assistant" ? renderMd(m.content) : null,
      }));
    }
  }
  res.render("chat", { title: "Trợ lý CNTT", prompts, conversations, messages, activeId });
});
