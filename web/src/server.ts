import path from "node:path";
import "express-async-errors";
import express, { NextFunction, Request, Response } from "express";
import cookieParser from "cookie-parser";
import { env } from "./config/env";
import { loadUser } from "./middleware/auth";
import { securityHeaders, csrfProtection, globalLimiter } from "./middleware/security";
import { authRouter } from "./routes/auth.routes";
import { pagesRouter } from "./routes/pages.routes";
import { apiRouter } from "./routes/api.routes";
import { adminRouter } from "./routes/admin.routes";
import { socialRouter } from "./routes/social.routes";

const app = express();
app.disable("x-powered-by");
app.locals.ASSET_VER = Date.now();
app.set("trust proxy", 1);

app.use(securityHeaders);

app.set("view engine", "ejs");
app.set("views", path.join(__dirname, "views"));
app.use(express.static(path.join(__dirname, "public"), { maxAge: env.isProd ? "7d" : "1h" }));

app.use(express.urlencoded({ extended: true, limit: "1mb" }));
app.use(express.json({ limit: "1mb" }));
app.use(cookieParser());

app.use(globalLimiter);

app.use(loadUser);

app.use(csrfProtection);

const PUBLIC_PATHS = new Set(["/login", "/register", "/logout", "/forgot"]);
app.use((req: Request, res: Response, next: NextFunction) => {
  if (req.user || PUBLIC_PATHS.has(req.path) || req.path.startsWith("/admin")) return next();
  if (req.path.startsWith("/api/")) {
    res.status(401).json({ error: "Cần đăng nhập." });
    return;
  }
  res.redirect("/login?next=" + encodeURIComponent(req.originalUrl));
});

app.use("/", authRouter);
app.use("/", socialRouter);
app.use("/", pagesRouter);
app.use("/admin", adminRouter);
app.use("/api", apiRouter);

app.use((req: Request, res: Response) => {
  res.status(404).render("error", { title: "404", message: "Không tìm thấy trang: " + req.path });
});

app.use((err: any, _req: Request, res: Response, _next: NextFunction) => {
  console.error("[error]", err?.message || err);
  if (res.headersSent) return;
  res.status(500).render("error", { title: "Lỗi", message: "Đã có lỗi xảy ra phía máy chủ." });
});

app.listen(env.port, () => {
  console.log(`[web] Nền tảng học tập CNTT chạy tại http://localhost:${env.port}`);
  console.log(`[web] Recommender: ${env.recommenderUrl}`);
});
