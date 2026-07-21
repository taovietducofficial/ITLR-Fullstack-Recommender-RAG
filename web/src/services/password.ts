import crypto from "node:crypto";

export const PASSWORD_RE = /^(?=.*[a-z])(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{8,}$/;
export const PASSWORD_HINT =
  "Mật khẩu tối thiểu 8 ký tự, có chữ HOA, chữ thường và ký tự đặc biệt.";

export function isStrongPassword(p: string): boolean {
  return PASSWORD_RE.test(p);
}

const LOWER = "abcdefghijkmnpqrstuvwxyz";
const UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ";
const DIGIT = "23456789";
const SPECIAL = "!@#$%^&*-_=+?";

function pick(set: string): string {
  return set[crypto.randomInt(set.length)];
}

export function generatePassword(len = 10): string {
  len = Math.max(8, len);
  const all = LOWER + UPPER + DIGIT + SPECIAL;
  const chars = [pick(LOWER), pick(UPPER), pick(SPECIAL), pick(DIGIT)];
  while (chars.length < len) chars.push(pick(all));
  for (let i = chars.length - 1; i > 0; i--) {
    const j = crypto.randomInt(i + 1);
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  return chars.join("");
}
