"""Gộp CSV thô đã cào -> catalog THẬT (data/it_learning_items_scraped.csv) — TÁI DÙNG code sẵn có.

LƯU Ý: ghi ra FILE RIÊNG it_learning_items_scraped.csv (KHÔNG đè it_learning_items_real.csv của
nhánh Kaggle, cũng KHÔNG đè synthetic gốc). Đổi --dest nếu muốn nơi khác.

Luồng:
  1. EN: build_catalog(data/scraped/en/*.csv)  -> map schema + lọc IT + khử trùng lặp (adapt_real_data).
  2. Dịch title+description của phần EN sang VI (NLLB có cache — translate_catalog), trừ khi --no-translate.
  3. VI: build_catalog(data/scraped/vi/*.csv)   -> giữ nguyên tiếng Việt, không dịch.
  4. (Tùy chọn --merge-synthetic) nối thêm catalog synthetic hiện tại để LÀM PHONG PHÚ thay vì thay thế.
  5. concat -> khử trùng lặp theo norm_title -> đánh lại item_id -> ghi file đích + in đối chứng phân phối.

KHÔNG sửa adapt_real_data.py / translate_catalog.py — chỉ import lại hàm.

Cách chạy:
    set PYTHONUTF8=1                                   # Windows
    python scripts/scrape/build_scraped_catalog.py --merge-synthetic
    python scripts/scrape/build_scraped_catalog.py --no-translate   # nhanh, để kiểm thử
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd  # noqa: E402

from itlr import config  # noqa: E402
from scripts.eval.adapt_real_data import build_catalog, distribution_stats, norm_title  # noqa: E402

FINAL_COLS = ["item_id", "title", "type", "level", "description", "category", "topics",
              "instructor", "platform", "link"]
TRANSLATE_FIELDS = ["title", "description"]

# Lọc IT theo TỪ KHÓA trên title+category+topics (khớp ranh giới từ \b để tránh dương tính giả
# như "ai" trong "email"). Bao cả tag NGẮN của nguồn cào (python, webdev, ai...) lẫn thuật ngữ
# tiếng Việt cho Viblo — adapt_real_data.IT_CATEGORY_TERMS chỉ khớp tên category dài kiểu Kaggle
# nên KHÔNG nhận diện được tag ngắn; ta tự lọc rồi gọi build_catalog với it_only=False.
IT_KEYWORDS = [
    # ngôn ngữ / nền tảng
    "python", "javascript", "typescript", "java", "kotlin", "swift", "golang", "rust", "php",
    "ruby", "scala", "dart", "c\\+\\+", "c#", "sql", "nosql", "bash", "powershell",
    # web / app
    "web", "webdev", "html", "css", "react", "vue", "angular", "svelte", "node", "nodejs",
    "frontend", "backend", "fullstack", "api", "graphql", "rest", "android", "ios", "mobile",
    "flutter", "framework",
    # data / AI
    "ai", "ml", "machine learning", "deep learning", "data", "datascience", "data science",
    "nlp", "llm", "neural", "tensorflow", "pytorch", "analytics", "bigdata",
    # hạ tầng / vận hành
    "devops", "docker", "kubernetes", "cloud", "aws", "azure", "gcp", "linux", "server",
    "database", "git", "ci/cd", "microservice",
    # bảo mật / nền tảng CNTT
    "security", "cybersecurity", "hacking", "pentest", "blockchain", "crypto wallet",
    "programming", "coding", "developer", "software", "algorithm", "computer science", "code",
    # tiếng Việt (Viblo)
    "lập trình", "công nghệ", "phần mềm", "dữ liệu", "thuật toán", "máy tính", "mạng máy tính",
    "trí tuệ nhân tạo", "học máy", "cơ sở dữ liệu", "bảo mật",
]
_IT_RE = re.compile(r"\b(?:" + "|".join(IT_KEYWORDS) + r")\b", re.IGNORECASE)


def filter_it(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Giữ lại dòng có tín hiệu IT trên title+category+topics. In số bị loại."""
    if df.empty:
        return df
    hay = (df["title"].astype(str) + " | " + df["category"].astype(str) + " | "
           + df["topics"].astype(str))
    mask = hay.str.contains(_IT_RE)
    kept = df[mask].reset_index(drop=True)
    print(f"  Lọc IT [{label}]: {len(df)} -> {len(kept)} (loại {len(df) - len(kept)} ngoài chủ đề)",
          flush=True)
    return kept


def _glob_csv(out_dir: str, lang: str) -> list[str]:
    return sorted(glob.glob(os.path.join(out_dir, lang, "*.csv")))


def translate_df(df: pd.DataFrame, batch: int) -> pd.DataFrame:
    """Dịch EN->VI cho title+description, dùng lại cache + model của translate_catalog."""
    from scripts.data.translate_catalog import load_cache, load_model, translate_missing

    cache = load_cache()
    print(f"  Cache dịch hiện có: {len(cache)} chuỗi", flush=True)
    print("  Tải model dịch (NLLB) ...", flush=True)
    tok, mdl = load_model()

    texts: list[str] = []
    for f in TRANSLATE_FIELDS:
        texts += df[f].astype(str).tolist()
    translate_missing(texts, tok, mdl, batch, cache)

    for f in TRANSLATE_FIELDS:
        df[f] = df[f].astype(str).map(lambda s: cache.get(s, s))
    return df


def main():
    ap = argparse.ArgumentParser(description="Gộp dữ liệu cào -> catalog thật.")
    ap.add_argument("--out-dir", default=config.data_file("scraped"), help="Thư mục chứa CSV thô đã cào")
    ap.add_argument("--dest", default=config.data_file("it_learning_items_scraped.csv"),
                    help="File catalog cào xuất ra (downstream dùng qua ITLR_ITEMS_CSV). "
                         "MẶC ĐỊNH file RIÊNG it_learning_items_scraped.csv để KHÔNG đè "
                         "it_learning_items_real.csv (catalog Kaggle) hay synthetic gốc.")
    ap.add_argument("--no-translate", action="store_true", help="Bỏ qua dịch EN->VI (giữ tiếng Anh)")
    ap.add_argument("--merge-synthetic", action="store_true",
                    help="Nối thêm catalog synthetic hiện tại (làm phong phú thay vì thay thế)")
    ap.add_argument("--merge-into",
                    help="NẠP dữ liệu cào VÀO một catalog có sẵn (vd data/it_learning_items_real_vi.csv): "
                         "GIỮ NGUYÊN item_id của catalog cũ, chỉ THÊM mục cào mới (khử trùng theo tiêu đề) "
                         "với item_id nối tiếp. Ghi đè CHÍNH file đó (nên backup trước).")
    ap.add_argument("--batch", type=int, default=32)
    args = ap.parse_args()

    frames: list[pd.DataFrame] = []

    # it_only=False: build_catalog chỉ khớp tên category dài kiểu Kaggle, không nhận tag ngắn của
    # nguồn cào -> ta tự lọc IT (filter_it) sau đó, có nhận diện tag ngắn + tiếng Việt.
    en_sources = _glob_csv(args.out_dir, "en")
    if en_sources:
        print(f"EN ({len(en_sources)} file):", [os.path.basename(s) for s in en_sources], flush=True)
        df_en = filter_it(build_catalog(en_sources, platform_default="Web", it_only=False), "EN")
        if not args.no_translate and len(df_en):
            df_en = translate_df(df_en, args.batch)
        else:
            print("  (bỏ qua dịch — giữ tiếng Anh)", flush=True)
        frames.append(df_en)

    vi_sources = _glob_csv(args.out_dir, "vi")
    if vi_sources:
        print(f"VI ({len(vi_sources)} file):", [os.path.basename(s) for s in vi_sources], flush=True)
        df_vi = filter_it(build_catalog(vi_sources, platform_default="Web", it_only=False), "VI")
        frames.append(df_vi)

    if args.merge_synthetic and os.path.exists(config.ITEMS_CSV):
        syn = pd.read_csv(config.ITEMS_CSV)
        print(f"Synthetic: nối thêm {len(syn)} mục từ {config.ITEMS_CSV}", flush=True)
        frames.append(syn[[c for c in FINAL_COLS if c in syn.columns]])

    if not frames:
        print("⚠️  Không tìm thấy CSV thô nào trong", args.out_dir,
              "- hãy chạy run_scrape.py trước.", flush=True)
        return

    scraped = pd.concat(frames, ignore_index=True)[FINAL_COLS]

    # Khi NẠP VÀO catalog có sẵn: đặt catalog cũ LÊN TRƯỚC (ưu tiên giữ bản cũ khi trùng), rồi
    # khử trùng lặp TOÀN CỤC -> đảm bảo "không có sự trùng lặp" kể cả trùng sẵn có trong file cũ.
    n_existing = 0
    if args.merge_into:
        existing = pd.read_csv(args.merge_into)
        existing = existing[[c for c in FINAL_COLS if c in existing.columns]]
        n_existing = len(existing)
        combined = pd.concat([existing, scraped], ignore_index=True)
        dest = args.merge_into
    else:
        combined = scraped
        dest = args.dest

    before = len(combined)
    combined["_key"] = combined["title"].map(norm_title)
    # Giữ bản có mô tả DÀI NHẤT khi trùng tiêu đề; sort ổn định -> ưu tiên thứ tự xuất hiện (cũ trước).
    combined = combined.sort_values("description", key=lambda s: s.astype(str).str.len(),
                                    ascending=False, kind="stable")
    df = combined.drop_duplicates(subset="_key").drop(columns="_key")
    # Sắp lại theo thứ tự ban đầu rồi đánh item_id liền mạch 1..n.
    df = df.sort_index().reset_index(drop=True)
    df["item_id"] = range(1, len(df) + 1)
    df = df[FINAL_COLS]

    # An toàn: điền ô rỗng/NaN bằng mặc định (như adapt_real_data) -> build_model.dropna() không rớt
    # dòng nào; cũng xử lý luôn NaN có sẵn trong catalog cũ.
    defaults = {"title": "Khóa học", "description": "Đang cập nhật", "topics": "Tổng quát",
                "instructor": "Đang cập nhật", "platform": "Đang cập nhật", "link": "Đang cập nhật",
                "category": "CNTT", "level": "Trung cấp", "type": "Khóa học"}
    for c, d_ in defaults.items():
        # fillna("") TRƯỚC khi astype(str): xử lý mọi kiểu NaN/<NA> (float nan lẫn pandas NA của
        # cột nullable/arrow) — nếu không, astype(str) trên cột nullable giữ nguyên NA -> lọt ra file.
        df[c] = df[c].fillna("").astype(str).replace(
            {"nan": "", "None": "", "NaN": "", "N/A": "", "NA": "", "<NA>": ""})
        df[c] = df[c].mask(df[c].str.strip() == "", d_)

    if args.merge_into:
        print(f"Nạp vào {os.path.basename(dest)}: {n_existing} cũ + {len(scraped)} cào -> "
              f"khử trùng lặp toàn cục {before} -> {len(df)} mục (item_id đánh lại 1..n)", flush=True)
    else:
        print(f"Catalog cào: khử trùng lặp {before} -> {len(df)} mục", flush=True)

    df.to_csv(dest, index=False, encoding="utf-8")
    print(f"-> {dest} ({len(df)} mục)", flush=True)
    args.dest = dest  # để dòng hướng dẫn rebuild bên dưới in đúng file

    try:  # đối chứng phân phối chỉ là thông tin -> lỗi ở đây KHÔNG được làm hỏng kết quả đã ghi.
        stats = distribution_stats(df, "scraped")
        print("Đối chứng phân phối:", {k: stats[k] for k in
                                        ("n", "n_categories", "desc_len_mean", "vocab_size")}, flush=True)
    except Exception as e:
        print(f"(bỏ qua đối chứng phân phối: {e})", flush=True)
    print("\nRebuild artifacts trên dữ liệu này:\n"
          f"  set ITLR_ITEMS_CSV={args.dest}\n"
          "  python -m itlr.pipelines.build_model", flush=True)


if __name__ == "__main__":
    main()
