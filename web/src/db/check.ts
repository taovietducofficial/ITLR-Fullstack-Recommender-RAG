import { pool, query } from "./pool";

function section(title: string, rows: any[]) {
  console.log(`\n=== ${title} (${rows.length}) ===`);
  console.table(rows.length ? rows : [{ "(trống)": "" }]);
}

async function check() {
  const [counts] = await query<any>(`SELECT
      (SELECT count(*) FROM users)::int          AS users,
      (SELECT count(*) FROM courses)::int        AS courses,
      (SELECT count(*) FROM enrollments)::int    AS enrollments,
      (SELECT count(*) FROM conversations)::int  AS conversations,
      (SELECT count(*) FROM messages)::int       AS messages,
      (SELECT count(*) FROM posts)::int          AS posts,
      (SELECT count(*) FROM post_likes)::int     AS post_likes,
      (SELECT count(*) FROM post_comments)::int  AS post_comments,
      (SELECT count(*) FROM attachments)::int    AS attachments`);
  console.log("\n================== TỔNG QUAN DỮ LIỆU ==================");
  console.table([counts]);

  section(
    "NGƯỜI DÙNG",
    await query<any>("SELECT id, name, email, role, created_at FROM users ORDER BY id"),
  );

  console.log("\n=== KHÓA HỌC/TÀI LIỆU: phân bố theo lĩnh vực ===");
  console.table(
    await query<any>(
      "SELECT category, count(*)::int AS n FROM courses GROUP BY category ORDER BY n DESC",
    ),
  );
  section(
    "KHÓA HỌC (5 mẫu)",
    await query<any>(
      "SELECT item_id, title, type, level, category FROM courses ORDER BY item_id LIMIT 5",
    ),
  );

  section(
    "ENROLLMENTS (khóa đã lưu)",
    await query<any>(
      `SELECT u.email, c.title, e.status, e.progress, e.updated_at
       FROM enrollments e JOIN users u ON u.id = e.user_id JOIN courses c ON c.item_id = e.course_id
      ORDER BY e.updated_at DESC`,
    ),
  );

  section(
    "HỘI THOẠI CHATBOT",
    await query<any>(
      `SELECT cv.id, u.email AS "user", cv.title,
            (SELECT count(*) FROM messages m WHERE m.conversation_id = cv.id)::int AS messages,
            cv.updated_at
       FROM conversations cv JOIN users u ON u.id = cv.user_id
      ORDER BY cv.updated_at DESC`,
    ),
  );

  section(
    "TIN NHẮN (15 gần nhất)",
    await query<any>(
      `SELECT id, conversation_id AS conv, role, left(content, 60) AS content, created_at
       FROM messages ORDER BY id DESC LIMIT 15`,
    ),
  );

  section(
    "BÀI VIẾT BLOG",
    await query<any>(
      `SELECT p.id, u.name AS author, left(p.content, 40) AS content,
            (p.image_data IS NOT NULL) AS has_img,
            p.doc_original AS doc,
            (SELECT count(*) FROM post_likes l WHERE l.post_id = p.id)::int AS likes,
            (SELECT count(*) FROM post_comments c WHERE c.post_id = p.id)::int AS comments,
            p.created_at
       FROM posts p JOIN users u ON u.id = p.user_id ORDER BY p.id DESC`,
    ),
  );

  section(
    "BÌNH LUẬN",
    await query<any>(
      `SELECT c.id, c.post_id, u.name AS author, left(c.content, 50) AS content, c.created_at
       FROM post_comments c JOIN users u ON u.id = c.user_id ORDER BY c.id`,
    ),
  );

  section(
    "FILE ĐÍNH KÈM KHÓA HỌC",
    await query<any>(
      `SELECT a.id, a.course_id, a.filename, a.mime, octet_length(a.data) AS bytes, u.email AS uploader
       FROM attachments a LEFT JOIN users u ON u.id = a.user_id ORDER BY a.id`,
    ),
  );

  await pool.end();
}

check().catch((err) => {
  console.error("[check] LỖI:", err.message);
  console.error("Gợi ý: kiểm tra web/.env (DATABASE_URL) và Postgres đang chạy.");
  process.exit(1);
});
