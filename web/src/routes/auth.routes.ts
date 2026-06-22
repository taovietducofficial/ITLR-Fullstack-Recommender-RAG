import { Router } from "express";
import bcrypt from "bcryptjs";
import { z } from "zod";
import { query } from "../db/pool";
import { AuthUser, signToken, setAuthCookie, clearAuthCookie, requireAuth } from "../middleware/auth";
import { PASSWORD_RE, PASSWORD_HINT, generatePassword } from "../services/password";
import { sendNewPassword } from "../services/mailer";
import { authLimiter } from "../middleware/security";

export const authRouter = Router();

const strongPassword = z.string().regex(PASSWORD_RE, PASSWORD_HINT).max(100);

const registerSchema = z.object({
  name: z.string().trim().min(1, "Vui lòng nhập tên").max(80),
  email: z.string().trim().email("Email không hợp lệ"),
  password: strongPassword,
});

const loginSchema = z.object({
  email: z.string().trim().email("Email không hợp lệ"),
  password: z.string().min(1, "Vui lòng nhập mật khẩu"),
});

function safeNext(raw: unknown): string {
  const n = typeof raw === "string" ? raw : "";
  return n.startsWith("/") && !n.startsWith("//") ? n : "/dashboard";
}

authRouter.get("/register", (req, res) => {
  if (req.user) return res.redirect("/dashboard");
  res.render("auth/register", { title: "Đăng ký", errors: [], values: {} });
});

authRouter.post("/register", authLimiter, async (req, res) => {
  const parsed = registerSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).render("auth/register", {
      title: "Đăng ký",
      errors: parsed.error.issues.map((i) => i.message),
      values: req.body,
    });
  }
  const { name, email, password } = parsed.data;
  try {
    const hash = await bcrypt.hash(password, 10);
    const rows = await query<AuthUser>(
      "INSERT INTO users (name, email, password_hash) VALUES ($1, $2, $3) RETURNING id, email, name, role",
      [name, email, hash]
    );
    const user = rows[0];
    setAuthCookie(res, signToken(user));
    res.redirect("/dashboard");
  } catch (err: any) {
    const dup = err?.code === "23505"; // unique_violation
    res.status(dup ? 409 : 500).render("auth/register", {
      title: "Đăng ký",
      errors: [dup ? "Email này đã được đăng ký." : "Lỗi hệ thống, thử lại sau."],
      values: req.body,
    });
  }
});

authRouter.get("/login", (req, res) => {
  if (req.user) return res.redirect("/dashboard");
  res.render("auth/login", { title: "Đăng nhập", errors: [], values: {}, next: req.query.next || "" });
});

authRouter.post("/login", authLimiter, async (req, res) => {
  const parsed = loginSchema.safeParse(req.body);
  const nextUrl = safeNext(req.body?.next);
  if (!parsed.success) {
    return res.status(400).render("auth/login", {
      title: "Đăng nhập",
      errors: parsed.error.issues.map((i) => i.message),
      values: req.body,
      next: req.body?.next || "",
    });
  }
  const { email, password } = parsed.data;
  const rows = await query<{ id: number; email: string; name: string; role: "user" | "admin"; password_hash: string }>(
    "SELECT id, email, name, role, password_hash FROM users WHERE email = $1",
    [email]
  );
  const u = rows[0];
  if (!u || !(await bcrypt.compare(password, u.password_hash))) {
    return res.status(401).render("auth/login", {
      title: "Đăng nhập",
      errors: ["Email hoặc mật khẩu không đúng."],
      values: req.body,
      next: req.body?.next || "",
    });
  }
  setAuthCookie(res, signToken({ id: u.id, email: u.email, name: u.name, role: u.role }));
  res.redirect(nextUrl);
});

authRouter.post("/logout", (req, res) => {
  clearAuthCookie(res);
  res.redirect("/");
});

// ── Quên mật khẩu: tạo mật khẩu ngẫu nhiên, gửi email (hoặc hiện ở chế độ dev) ──
authRouter.get("/forgot", (req, res) => {
  if (req.user) return res.redirect("/account");
  res.render("auth/forgot", { title: "Quên mật khẩu", error: "", done: false, devPassword: "", email: "" });
});

authRouter.post("/forgot", authLimiter, async (req, res) => {
  const email = String(req.body?.email || "").trim();
  const view = (extra: object) =>
    res.render("auth/forgot", { title: "Quên mật khẩu", error: "", done: false, devPassword: "", email, ...extra });

  if (!/^\S+@\S+\.\S+$/.test(email)) return view({ error: "Email không hợp lệ." });

  const rows = await query<{ id: number }>("SELECT id FROM users WHERE email = $1", [email]);
  if (!rows.length) return view({ error: "Email này chưa được đăng ký." });

  const newPass = generatePassword(10);
  const hash = await bcrypt.hash(newPass, 10);
  await query("UPDATE users SET password_hash = $1 WHERE id = $2", [hash, rows[0].id]);

  let sent = false;
  try {
    sent = await sendNewPassword(email, newPass);
  } catch {
    sent = false;
  }
  // Có SMTP -> chỉ báo đã gửi. Không có SMTP (dev) -> hiện mật khẩu để bạn thử ngay.
  view({ done: true, devPassword: !sent ? newPass : "" });
});

// ── Trang Tài khoản: đổi mật khẩu ──────────────────────────────────────────────
async function hasAvatar(userId: number): Promise<boolean> {
  const r = await query<{ a: boolean }>("SELECT (avatar_data IS NOT NULL) AS a FROM users WHERE id = $1", [userId]);
  return !!r[0]?.a;
}

authRouter.get("/account", requireAuth, async (req, res) => {
  res.render("account", { title: "Tài khoản", error: "", ok: false, hasAvatar: await hasAvatar(req.user!.id) });
});

const changeSchema = z.object({
  current: z.string().min(1, "Nhập mật khẩu hiện tại"),
  password: strongPassword,
  confirm: z.string(),
}).refine((d) => d.password === d.confirm, { message: "Xác nhận mật khẩu không khớp", path: ["confirm"] });

authRouter.post("/account/password", requireAuth, async (req, res) => {
  const av = await hasAvatar(req.user!.id);
  const view = (extra: object) => res.render("account", { title: "Tài khoản", error: "", ok: false, hasAvatar: av, ...extra });
  const parsed = changeSchema.safeParse(req.body);
  if (!parsed.success) return view({ error: parsed.error.issues.map((i) => i.message).join(" · ") });

  const rows = await query<{ password_hash: string }>("SELECT password_hash FROM users WHERE id = $1", [req.user!.id]);
  if (!rows.length || !(await bcrypt.compare(parsed.data.current, rows[0].password_hash))) {
    return view({ error: "Mật khẩu hiện tại không đúng." });
  }
  const hash = await bcrypt.hash(parsed.data.password, 10);
  await query("UPDATE users SET password_hash = $1 WHERE id = $2", [hash, req.user!.id]);
  view({ ok: true });
});
