import { Pool } from "pg";
import { env } from "../config/env";

export const pool = new Pool({ connectionString: env.databaseUrl });

pool.on("error", (err) => {
  console.error("[pg] lỗi connection nhàn rỗi:", err.message);
});

export async function query<T = any>(text: string, params?: unknown[]): Promise<T[]> {
  const res = await pool.query(text, params as any[]);
  return res.rows as T[];
}
