import { createReadStream } from "node:fs";
import { join } from "node:path";
import { pipeline } from "node:stream/promises";
import { from as copyFrom } from "pg-copy-streams";
import { pool } from "./pool";

// ĐỒNG BỘ catalog vào bảng courses theo kiểu UPSERT (INSERT ... ON CONFLICT DO UPDATE).
// Khác `seed-courses.ts` (TRUNCATE CASCADE -> mất enrollments): script này CHỈ chèn khóa mới và
// cập nhật khóa đã đổi theo item_id -> GIỮ NGUYÊN enrollments (khóa user đã lưu/tiến độ). Hợp cho
// pipeline cập nhật dữ liệu định kỳ (CI/CD). Chạy: npm run sync  (CSV qua ITEMS_CSV hoặc mặc định).
const CSV = process.env.ITEMS_CSV || join(__dirname, "..", "..", "..", "data", "it_learning_items.csv");
const COLS = "item_id,title,type,level,description,category,topics,instructor,platform,link";

async function sync() {
  const client = await pool.connect();
  try {
    // 1) Nạp CSV vào bảng TẠM (cùng cấu trúc) bằng COPY — nhanh, không đụng bảng thật.
    //    BEGIN TRƯỚC rồi mới CREATE TEMP ... ON COMMIT DROP: nếu tạo ngoài transaction, implicit
    //    commit sẽ drop bảng tạm ngay -> COPY báo "relation does not exist".
    await client.query("BEGIN");
    await client.query("CREATE TEMP TABLE courses_stage (LIKE courses INCLUDING DEFAULTS) ON COMMIT DROP");
    const ingest = client.query(
      copyFrom(`COPY courses_stage (${COLS}) FROM STDIN WITH (FORMAT csv, HEADER true)`)
    );
    await pipeline(createReadStream(CSV), ingest);

    // 2) UPSERT từ bảng tạm -> courses. DISTINCT ON (item_id) phòng CSV lỡ trùng id.
    //    xmax = 0 ở RETURNING => dòng vừa CHÈN mới (phân biệt với dòng được CẬP NHẬT).
    const setClause = COLS.split(",")
      .filter((c) => c !== "item_id")
      .map((c) => `${c} = EXCLUDED.${c}`)
      .join(", ");
    const res = await client.query(
      `WITH up AS (
         INSERT INTO courses (${COLS})
         SELECT DISTINCT ON (item_id) ${COLS} FROM courses_stage ORDER BY item_id
         ON CONFLICT (item_id) DO UPDATE SET ${setClause}
         RETURNING (xmax = 0) AS inserted
       )
       SELECT count(*) FILTER (WHERE inserted)      AS inserted,
              count(*) FILTER (WHERE NOT inserted)  AS updated
       FROM up`
    );
    await client.query("COMMIT");

    const { inserted, updated } = res.rows[0];
    const total = await client.query("SELECT count(*)::int AS n FROM courses");
    console.log(`[sync] UPSERT từ ${CSV}: +${inserted} mới, ~${updated} cập nhật. ` +
                `Tổng courses = ${total.rows[0].n} (enrollments GIỮ NGUYÊN).`);
  } catch (err) {
    await client.query("ROLLBACK").catch(() => {});
    throw err;
  } finally {
    client.release();
    await pool.end();
  }
}

sync().catch((err) => {
  console.error("[sync] LỖI:", err.message);
  process.exit(1);
});
