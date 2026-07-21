import { Request, Response, NextFunction } from "express";
import crypto from "node:crypto";
import helmet from "helmet";
import rateLimit from "express-rate-limit";
import { env } from "../config/env";

const CSRF_COOKIE = "csrf";

export const securityHeaders = helmet({
  contentSecurityPolicy: {
    useDefaults: true,
    directives: {
      "default-src": ["'self'"],
      "base-uri": ["'self'"],
      "form-action": ["'self'"],
      "frame-ancestors": ["'self'"],
      "script-src": ["'self'", "'unsafe-inline'"],
      "script-src-attr": ["'unsafe-inline'"],
      "style-src": ["'self'", "'unsafe-inline'"],
      "font-src": ["'self'"],
      "img-src": ["'self'", "data:", "blob:", "https://i.ytimg.com"],
      "media-src": ["'self'", "blob:", "data:"],
      "frame-src": ["https://www.youtube.com", "https://www.youtube-nocookie.com"],
      "connect-src": ["'self'"],
      "object-src": ["'none'"],
      "upgrade-insecure-requests": env.isProd ? [] : null,
    },
  },
  hsts: env.isProd ? { maxAge: 15552000, includeSubDomains: true } : false,
  crossOriginEmbedderPolicy: false,
  referrerPolicy: { policy: "strict-origin-when-cross-origin" },
});

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export function csrfProtection(req: Request, res: Response, next: NextFunction): void {
  let token: string | undefined = req.cookies?.[CSRF_COOKIE];
  if (!token || !/^[a-f0-9]{64}$/.test(token)) {
    token = crypto.randomBytes(32).toString("hex");
    res.cookie(CSRF_COOKIE, token, {
      httpOnly: false,
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
      res.status(403).render("error", {
        title: "403",
        message: "Yêu cầu không hợp lệ (CSRF). Hãy tải lại trang và thử lại.",
      });
    }
    return;
  }
  next();
}

const limiterOpts = {
  standardHeaders: true,
  legacyHeaders: false,
};

export const globalLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 300,
  ...limiterOpts,
  message: { error: "Bạn thao tác quá nhanh. Vui lòng thử lại sau giây lát." },
});

export const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 20,
  ...limiterOpts,
  skipSuccessfulRequests: true,
  message: { error: "Quá nhiều lần thử. Vui lòng đợi ít phút rồi thử lại." },
});
