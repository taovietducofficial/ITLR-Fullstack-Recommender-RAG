import { Request, Response, NextFunction } from "express";
import crypto from "node:crypto";
import helmet from "helmet";
import rateLimit from "express-rate-limit";
import { env } from "../config/env";

/* ════════════════════════════════════════════════════════════════════════════
   Lớp bảo mật tập trung: security headers (helmet/CSP), CSRF (double-submit),
   rate limiting. Mục tiêu: phòng XSS · clickjacking · brute-force · CSRF.
   ════════════════════════════════════════════════════════════════════════════ */

const CSRF_COOKIE = "csrf";

// ── Security headers + Content-Security-Policy ────────────────────────────────
// CSP cho phép: tài nguyên 'self', Google Fonts, nhúng YouTube (bài học), ảnh/video
// data:/blob: (avatar & media inline). Cho phép inline style/script vì giao diện
// dùng nhiều style="" và vài handler inline — bù lại mọi output đều được escape.
export const securityHeaders = helmet({
  contentSecurityPolicy: {
    useDefaults: true,
    directives: {
      "default-src": ["'self'"],
      "base-uri": ["'self'"],
      "form-action": ["'self'"],
      "frame-ancestors": ["'self'"],
      "script-src": ["'self'", "'unsafe-inline'"],
      // Cho phép handler inline (onsubmit="confirm()", onchange="submit()") — nếu chặn
      // ('none' mặc định của helmet) thì các nút xác nhận xóa & đổi avatar sẽ hỏng.
      "script-src-attr": ["'unsafe-inline'"],
      "style-src": ["'self'", "'unsafe-inline'"],
      "font-src": ["'self'"], // font Inter tự host trong /fonts — không phụ thuộc bên ngoài
      "img-src": ["'self'", "data:", "blob:", "https://i.ytimg.com"],
      "media-src": ["'self'", "blob:", "data:"],
      "frame-src": ["https://www.youtube.com", "https://www.youtube-nocookie.com"],
      "connect-src": ["'self'"],
      "object-src": ["'none'"],
      "upgrade-insecure-requests": env.isProd ? [] : null,
    },
  },
  // HSTS chỉ bật khi chạy production (https). Mặc định helmet ổn cho phần còn lại.
  hsts: env.isProd ? { maxAge: 15552000, includeSubDomains: true } : false,
  crossOriginEmbedderPolicy: false, // để nhúng YouTube/iframe không bị chặn
  referrerPolicy: { policy: "strict-origin-when-cross-origin" },
});

// ── CSRF: double-submit cookie ────────────────────────────────────────────────
// Đặt 1 token ngẫu nhiên vào cookie 'csrf' (đọc được bằng JS). Với mọi request
// thay đổi dữ liệu (POST/PUT/PATCH/DELETE) phải gửi lại token đó qua:
//   header  X-CSRF-Token   (fetch JSON / FormData), hoặc
//   field   _csrf          (form urlencoded), hoặc
//   query   _csrf          (form multipart — body chưa parse kịp).
// Token phải KHỚP cookie thì mới hợp lệ → site khác không đọc được cookie nên
// không giả mạo được request.
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export function csrfProtection(req: Request, res: Response, next: NextFunction): void {
  let token: string | undefined = req.cookies?.[CSRF_COOKIE];
  if (!token || !/^[a-f0-9]{64}$/.test(token)) {
    token = crypto.randomBytes(32).toString("hex");
    res.cookie(CSRF_COOKIE, token, {
      httpOnly: false, // JS cần đọc để gắn header
      sameSite: "lax",
      secure: env.isProd,
      maxAge: 7 * 24 * 60 * 60 * 1000,
    });
  }
  res.locals.csrfToken = token;

  if (SAFE_METHODS.has(req.method)) return next();

  const sent =
    (req.headers["x-csrf-token"] as string | undefined) ||
    (req.body && typeof req.body === "object" ? req.body._csrf : undefined) ||
    (req.query?._csrf as string | undefined);

  if (!sent || sent !== token) {
    if (req.path.startsWith("/api/")) {
      res.status(403).json({ error: "Phiên không hợp lệ (CSRF). Hãy tải lại trang." });
    } else {
      res.status(403).render("error", { title: "403", message: "Yêu cầu không hợp lệ (CSRF). Hãy tải lại trang và thử lại." });
    }
    return;
  }
  next();
}

// ── Rate limiters ─────────────────────────────────────────────────────────────
// Chống lạm dụng/brute-force. Bộ đếm theo IP, trả 429 khi vượt ngưỡng.
const limiterOpts = {
  standardHeaders: true,
  legacyHeaders: false,
};

// Toàn cục: nới tay, chỉ chặn lạm dụng cực đoan.
export const globalLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 300,
  ...limiterOpts,
  message: { error: "Bạn thao tác quá nhanh. Vui lòng thử lại sau giây lát." },
});

// Đăng nhập/đăng ký/quên mật khẩu/admin: siết chặt chống dò mật khẩu.
export const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 20,
  ...limiterOpts,
  skipSuccessfulRequests: true,
  message: { error: "Quá nhiều lần thử. Vui lòng đợi ít phút rồi thử lại." },
});
