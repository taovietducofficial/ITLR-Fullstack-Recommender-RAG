import dotenv from "dotenv";

dotenv.config();

function required(name: string, fallback?: string): string {
  const v = process.env[name] ?? fallback;
  if (v === undefined || v === "") {
    throw new Error(`Thiếu biến môi trường ${name}. Hãy tạo web/.env từ .env.example.`);
  }
  return v;
}

const isProd = process.env.NODE_ENV === "production";

const jwtSecret = required("JWT_SECRET", "dev-secret-change-me");
if (isProd && (jwtSecret === "dev-secret-change-me" || jwtSecret.length < 32)) {
  throw new Error("JWT_SECRET phải đặt mạnh (≥ 32 ký tự) khi chạy production.");
}
const adminPasscode = process.env.ADMIN_PASSCODE || "1";
if (isProd && adminPasscode === "1") {
  throw new Error("ADMIN_PASSCODE phải đổi khác mặc định khi chạy production.");
}

export const env = {
  port: parseInt(process.env.PORT || "3000", 10),
  databaseUrl: required(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/it_learning",
  ),
  jwtSecret,
  recommenderUrl: (process.env.RECOMMENDER_URL || "http://localhost:8000").replace(/\/$/, ""),
  adminPasscode,
  isProd,
};
