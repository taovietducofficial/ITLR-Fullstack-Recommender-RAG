import { Request, Response, NextFunction } from "express";
import jwt from "jsonwebtoken";
import { env } from "../config/env";

export interface AuthUser {
  id: number;
  email: string;
  name: string;
  role: "user" | "admin";
}

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Express {
    interface Request {
      user?: AuthUser;
    }
  }
}

const COOKIE = "token";

export function signToken(user: AuthUser): string {
  return jwt.sign(user, env.jwtSecret, { expiresIn: "7d" });
}

export function setAuthCookie(res: Response, token: string): void {
  res.cookie(COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: env.isProd,
    maxAge: 7 * 24 * 60 * 60 * 1000,
  });
}

export function clearAuthCookie(res: Response): void {
  res.clearCookie(COOKIE);
}

export function loadUser(req: Request, res: Response, next: NextFunction): void {
  const token = req.cookies?.[COOKIE];
  if (token) {
    try {
      const payload = jwt.verify(token, env.jwtSecret) as AuthUser & { iat?: number; exp?: number };
      req.user = { id: payload.id, email: payload.email, name: payload.name, role: payload.role };
    } catch {}
  }
  res.locals.user = req.user || null;
  res.locals.path = req.path;
  res.locals.isAdmin = hasAdminAccess(req);
  next();
}

export const ADM_VER = 2;

export function hasAdminAccess(req: Request): boolean {
  const c = req.cookies?.adm;
  if (c) {
    try {
      const p = jwt.verify(c, env.jwtSecret) as { adm?: boolean; v?: number };
      return p.adm === true && p.v === ADM_VER;
    } catch {}
  }
  return false;
}

export function requireAdminAccess(req: Request, res: Response, next: NextFunction): void {
  if (hasAdminAccess(req)) return next();
  res.redirect("/admin/login");
}

export function requireAuth(req: Request, res: Response, next: NextFunction): void {
  if (!req.user) {
    res.redirect("/login?next=" + encodeURIComponent(req.originalUrl));
    return;
  }
  next();
}

export function requireAdmin(req: Request, res: Response, next: NextFunction): void {
  if (!req.user) {
    res.redirect("/login");
    return;
  }
  if (req.user.role !== "admin") {
    res
      .status(403)
      .render("error", { title: "403", message: "Bạn không có quyền truy cập trang này." });
    return;
  }
  next();
}
