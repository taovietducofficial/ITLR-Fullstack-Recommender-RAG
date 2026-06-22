import crypto from "node:crypto";

// Chính sách: tối thiểu 8 ký tự, có chữ hoa, chữ thường và ký tự đặc biệt.
export const PASSWORD_RE = /^(?=.*[a-z])(?=.*[A-Z])(?=.*[^A-Za-z0-9]).{8,}$/;
export const PASSWORD_HINT = "Mật khẩu tối thiểu 8 ký tự, có chữ HOA, chữ thường và ký tự đặc biệt.";

export function isStrongPassword(p: string): boolean {
  return PASSWORD_RE.test(p);
}

const LOWER = "abcdefghijkmnpqrstuvwxyz"; // bỏ l dễ nhầm
const UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"; // bỏ I/O dễ nhầm
const DIGIT = "23456789";                 // bỏ 0/1 dễ nhầm
const SPECIAL = "!@#$%^&*-_=+?";

function pick(set: string): string {
  return set[crypto.randomInt(set.length)];
}

// Tạo mật khẩu ngẫu nhiên ĐẢM BẢO đủ lớp ký tự (>= 8, mặc định 10 cho mạnh hơn).
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
