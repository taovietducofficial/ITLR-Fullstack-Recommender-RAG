import { createReadStream } from "node:fs";
import { join } from "node:path";
import { pipeline } from "node:stream/promises";
import { from as copyFrom } from "pg-copy-streams";
import { pool } from "./pool";

// Nạp catalog từ data/it_learning_items.csv vào bảng courses bằng COPY (nhanh, ~50k dòng).
// Thứ tự cột CSV trùng bảng courses: item_id,title,type,level,description,category,topics,instructor,platform,link
// Chạy: npm run seed   (đã có dữ liệu -> bỏ qua; nạp lại: npm run seed -- --force)
// Đường dẫn CSV: ưu tiên ITEMS_CSV (dùng trong Docker), mặc định theo layout repo.
const CSV = process.env.ITEMS_CSV || join(__dirname, "..", "..", "..", "data", "it_learning_items.csv");

async function seed() {
  const client = await pool.connect();
  try {
    const { rows } = await client.query("SELECT count(*)::int AS n FROM courses");
    const n = rows[0].n as number;
    const force = process.argv.includes("--force") || process.env.FORCE === "1";

    if (n > 0 && !force) {
      console.log(`[seed] courses đã có ${n} dòng — bỏ qua. Nạp lại: npm run seed -- --force`);
      return;
    }
    if (n > 0) {
      await client.query("TRUNCATE courses CASCADE"); // CASCADE: xóa cả enrollments tham chiếu
      console.log("[seed] Đã TRUNCATE courses (force).");
    }

    const ingest = client.query(
      copyFrom(
        "COPY courses (item_id,title,type,level,description,category,topics,instructor,platform,link) " +
        "FROM STDIN WITH (FORMAT csv, HEADER true)"
      )
    );
    await pipeline(createReadStream(CSV), ingest);

    const after = await client.query("SELECT count(*)::int AS n FROM courses");
    console.log(`[seed] Đã nạp ${after.rows[0].n} courses từ ${CSV}`);
  } finally {
    client.release();
    await pool.end();
  }
}

seed().catch((err) => {
  console.error("[seed] LỖI:", err.message);
  process.exit(1);
});
