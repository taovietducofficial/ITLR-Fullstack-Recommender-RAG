import { promises as fsp, existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

export async function extractText(buf: Buffer, ext: string): Promise<string> {
  try {
    if (ext === ".pdf") {
      // @ts-expect-error - import thẳng lib để bỏ qua debug wrapper của pdf-parse
      const mod: any = await import("pdf-parse/lib/pdf-parse.js");
      const pdf = mod.default || mod;
      const d = await pdf(buf);
      return d.text || "";
    }
    if (ext === ".docx" || ext === ".doc") {
      const m: any = await import("mammoth");
      const fn = m.extractRawText || (m.default && m.default.extractRawText);
      const r = await fn({ buffer: buf });
      return r.value || "";
    }
    if (ext === ".xlsx" || ext === ".xls") {
      const XLSX: any = await import("xlsx");
      const wb = XLSX.read(buf, { type: "buffer" });
      return wb.SheetNames.map((n: string) => XLSX.utils.sheet_to_csv(wb.Sheets[n])).join("\n");
    }
  } catch (e) {
    console.error("[extractText]", (e as Error).message);
  }
  return "";
}

export function cleanForCsv(text: string, max = 3000): string {
  return (text || "").replace(/\s+/g, " ").trim().slice(0, max);
}

const CSV =
  process.env.ITEMS_CSV || join(__dirname, "..", "..", "..", "data", "it_learning_items.csv");
const COLS = [
  "item_id",
  "title",
  "type",
  "level",
  "description",
  "category",
  "topics",
  "instructor",
  "platform",
  "link",
];
let nextId: number | null = null;

function readLastId(): number {
  if (!existsSync(CSV)) return 0;
  const lines = readFileSync(CSV, "utf8").trimEnd().split(/\r?\n/);
  for (let i = lines.length - 1; i >= 1; i--) {
    const n = parseInt(lines[i].split(",")[0], 10);
    if (!Number.isNaN(n)) return n;
  }
  return 0;
}

function csvField(v: unknown): string {
  const s = v == null ? "" : String(v);
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

export interface CatalogRow {
  title: string;
  description: string;
  type?: string;
  level?: string;
  category?: string;
  topics?: string;
  instructor?: string;
  platform?: string;
  link?: string;
}

export async function appendCatalogRow(row: CatalogRow): Promise<number> {
  if (nextId == null) nextId = readLastId();
  nextId += 1;
  const id = nextId;
  const rec: Record<string, unknown> = {
    item_id: id,
    title: row.title || `Tài liệu ${id}`,
    type: row.type || "Tài liệu",
    level: row.level || "",
    description: cleanForCsv(row.description || row.title || ""),
    category: row.category || "Tài liệu cộng đồng",
    topics: row.topics || "",
    instructor: row.instructor || "",
    platform: row.platform || "Tải lên",
    link: row.link || "",
  };
  const line = COLS.map((c) => csvField(rec[c])).join(",") + "\n";
  await fsp.appendFile(CSV, line, "utf8");
  return id;
}
