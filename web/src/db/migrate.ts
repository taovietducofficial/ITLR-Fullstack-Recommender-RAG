import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pool } from "./pool";

async function migrate() {
  const sql = readFileSync(join(__dirname, "schema.sql"), "utf-8");
  await pool.query(sql);
  console.log("[migrate] Đã áp dụng schema.sql — các bảng users/courses/enrollments sẵn sàng.");
  await pool.end();
}

migrate().catch((err) => {
  console.error("[migrate] LỖI:", err.message);
  process.exit(1);
});
