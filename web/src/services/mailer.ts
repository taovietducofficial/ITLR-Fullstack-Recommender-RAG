import nodemailer from "nodemailer";

const user = process.env.SMTP_USER;
const pass = process.env.SMTP_PASS;
const host = process.env.SMTP_HOST;
const port = parseInt(process.env.SMTP_PORT || "587", 10);

export const mailConfigured = !!(user && pass);

const transporter = mailConfigured
  ? nodemailer.createTransport(
      host
        ? { host, port, secure: port === 465, auth: { user, pass } }
        : { service: "gmail", auth: { user: user as string, pass: pass as string } },
    )
  : null;

export async function sendNewPassword(to: string, password: string): Promise<boolean> {
  if (!transporter) return false;
  await transporter.sendMail({
    from: process.env.SMTP_FROM || `IT Learning <${user}>`,
    to,
    subject: "IT Learning — Mật khẩu mới của bạn",
    text:
      `Bạn vừa yêu cầu đặt lại mật khẩu.\n\n` +
      `Mật khẩu mới: ${password}\n\n` +
      `Hãy đăng nhập bằng mật khẩu này, sau đó vào trang Tài khoản để đổi mật khẩu mới.`,
    html:
      `<p>Bạn vừa yêu cầu đặt lại mật khẩu tại <b>IT Learning</b>.</p>` +
      `<p>Mật khẩu mới của bạn: <b style="font-size:18px;letter-spacing:1px">${password}</b></p>` +
      `<p>Hãy đăng nhập bằng mật khẩu này, sau đó vào trang <b>Tài khoản</b> để đổi mật khẩu mới.</p>`,
  });
  return true;
}
