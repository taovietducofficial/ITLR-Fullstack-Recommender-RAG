import path from "node:path";
import "express-async-errors"; // cho phép lỗi trong handler async tự chuyển tới error handler (Express 4)
import express, { NextFunction, Request, Response } from "express";
import cookieParser from "cookie-parser";
import { env } from "./config/env";
import { loadUser } from "./middleware/auth";
import { securityHeaders, csrfProtection, globalLimiter, authLimiter } from "./middleware/security";
import { authRouter } from "./routes/auth.routes";
import { pagesRouter } from "./routes/pages.routes";
import { apiRouter } from "./routes/api.routes";
import { adminRouter } from "./routes/admin.routes";
import { socialRouter } from "./routes/social.routes";

const app = express();
app.disable("x-powered-by"); // không lộ "Express" trong header (an toàn hơn khi deploy)
app.set("trust proxy", 1);   // sau reverse proxy (Heroku) -> rate-limit lấy đúng IP, cookie secure đúng

// Security headers (helmet + CSP) — đặt SỚM để áp cho mọi phản hồi.
app.use(securityHeaders);

// View engine EJS (templates trong src/views, asset tĩnh trong src/public).
app.set("view engine", "ejs");
app.set("views", path.join(__dirname, "views"));
app.use(express.static(path.join(__dirname, "public"), { maxAge: env.isProd ? "7d" : 0 }));

// Parsers (giới hạn kích thước body chống lạm dụng).
app.use(express.urlencoded({ extended: true, limit: "1mb" }));
app.use(express.json({ limit: "1mb" }));
app.use(cookieParser());

// Chống lạm dụng/brute-force trên toàn site.
app.use(globalLimiter);

// Gắn user (nếu có cookie JWT) cho mọi request + EJS.
app.use(loadUser);

// CSRF (double-submit) — sau parsers/cookie, trước routes.
app.use(csrfProtection);

// CỔNG AUTH TOÀN CỤC: phải đăng nhập/đăng ký mới vào được phần mềm.
// Chưa đăng nhập -> chỉ cho phép trang đăng nhập/đăng ký/đăng xuất; còn lại chuyển về /login.
// (Asset tĩnh /styles.css, /app.js đã được express.static phục vụ TRƯỚC middleware này.)
// Khu vực /admin là TRANG RIÊNG, độc lập tài khoản user — tự bảo vệ bằng
// requireAdminAccess (passcode admin), nên cho đi qua cổng đăng nhập user.
const PUBLIC_PATHS = new Set(["/login", "/register", "/logout", "/forgot"]);
app.use((req: Request, res: Response, next: NextFunction) => {
  if (req.user || PUBLIC_PATHS.has(req.path) || req.path.startsWith("/admin")) return next();
  if (req.path.startsWith("/api/")) {
    res.status(401).json({ error: "Cần đăng nhập." });
    return;
  }
  res.redirect("/login?next=" + encodeURIComponent(req.originalUrl));
});

// Routes
app.use("/", authRouter);
app.use("/", socialRouter);
app.use("/", pagesRouter);
app.use("/admin", adminRouter);
app.use("/api", apiRouter);

// 404
app.use((req: Request, res: Response) => {
  res.status(404).render("error", { title: "404", message: "Không tìm thấy trang: " + req.path });
});

// Error handler tập trung
app.use((err: any, _req: Request, res: Response, _next: NextFunction) => {
  console.error("[error]", err?.message || err);
  if (res.headersSent) return;
  res.status(500).render("error", { title: "Lỗi", message: "Đã có lỗi xảy ra phía máy chủ." });
});

app.listen(env.port, () => {
  console.log(`[web] Nền tảng học tập CNTT chạy tại http://localhost:${env.port}`);
  console.log(`[web] Recommender: ${env.recommenderUrl}`);
});
