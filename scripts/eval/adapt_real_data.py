"""Adapter dữ liệu THẬT về schema catalog + đối chứng phân phối synthetic vs thật (Trụ cột I).

Chống chất vấn "dữ liệu giả": nạp các dataset khóa học CÔNG KHAI (Kaggle "Coursera/Udemy/Online
Courses" — tải tay, không cần crawl) rồi map sang schema hiện tại, LỌC riêng lĩnh vực CNTT/IT,
KHỬ TRÙNG LẶP, để rebuild artifacts trên dữ liệu thật; đồng thời sinh mục **đối chứng phân phối**
(độ dài mô tả, phân bố category, từ vựng) biện luận tính đại diện của dữ liệu synthetic.

Schema đích: item_id,title,type,level,description,category,topics,instructor,platform,link

Cách chạy:
    # chỉ thống kê phân phối catalog synthetic hiện tại:
    python scripts/eval/adapt_real_data.py --compare-only
    # map MỘT dataset thật -> data/it_learning_items_real.csv + đối chứng:
    python scripts/eval/adapt_real_data.py --source path/to/coursera.csv
    # HỢP NHẤT cả thư mục Kaggle (lọc IT + khử trùng lặp) -> catalog thật:
    python scripts/eval/adapt_real_data.py --source-dir data_real_kaggle

Đầu ra ghi vào FILE RIÊNG (it_learning_items_real.csv) — KHÔNG đụng synthetic gốc.
Rebuild trên dữ liệu thật:
    ITLR_ITEMS_CSV=data/it_learning_items_real.csv python -m itlr.pipelines.build_model  (v.v.)
"""

from __future__ import annotations

import argparse
import ast
import glob
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd  # noqa: E402

from itlr import config  # noqa: E402

# Heuristic ánh xạ tên cột nguồn -> trường schema (bao các dataset Coursera/Udemy/Online phổ biến).
COLUMN_ALIASES = {
    "title": ["course_title", "course title", "title", "name", "course_name", "course", "clean_title"],
    "description": ["description", "course_description", "short intro", "course short intro",
                    "what you will learn", "what you learn", "about", "summary"],
    "category": ["category", "subject", "primary_subject", "primary subject", "field", "domain",
                 "course_category", "keyword"],
    "subcategory": ["sub-category", "subcategory", "sub category"],
    "topics": ["skills", "skill gain", "gained skills", "skills gained", "tags", "topics", "keywords"],
    "instructor": ["instructor", "instructors", "teacher", "author", "organization", "partner",
                   "institution", "offered by", "created by", "provider"],
    "platform": ["platform", "site", "source", "provider", "offered by"],
    "link": ["url", "link", "course_url", "course url", "course_page"],
    "level": ["level", "difficulty", "course_level"],
}

# Từ khóa nhận diện lĩnh vực CNTT/IT (so khớp chuỗi con, viết thường) trên category + sub-category.
IT_CATEGORY_TERMS = [
    "computer science", "data science", "datascience", "information technology", "it &",
    "web development", "software development", "software", "programming", "machine learning",
    "deep learning", "artificial intelligence", "cloud computing", "cloud", "algorithms",
    "data analysis", "data engineering", "cybersecurity", "information security", "networking",
    "databases", "database", "devops", "mobile development", "game development", "blockchain",
    "computer", "coding", "developer", "it certifications",
]
# Mặc định nền tảng suy từ tên file (khi nguồn không có cột platform).
PLATFORM_BY_FILE = {
    "udemy": "Udemy", "coursera": "Coursera", "online_courses": "Multi-platform",
    "all_courses": "Multi-platform",
}

# Map cấp độ tiếng Anh -> nhãn tiếng Việt cho đồng nhất với catalog hiện tại.
LEVEL_VI = {
    "beginner": "Cơ bản", "introductory": "Cơ bản", "basic": "Cơ bản", "all": "Cơ bản",
    "intermediate": "Trung cấp", "mixed": "Trung cấp",
    "advanced": "Nâng cao", "expert": "Nâng cao",
}


def _find_col(cols_lower, candidates):
    for c in candidates:
        if c in cols_lower:
            return cols_lower[c]
    return None


def clean_topics(s: str) -> str:
    """Chuẩn hóa topics: chuỗi kiểu list Python ['a','b'] hoặc 'a|b;c' -> 'a, b, c'."""
    s = str(s).strip()
    if not s or s.lower() == "nan":
        return ""
    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, (list, tuple)):
                return ", ".join(str(x).strip() for x in parsed if str(x).strip())
        except (ValueError, SyntaxError):
            pass
    s = re.sub(r"[|;/]", ",", s)
    parts = [p.strip() for p in s.split(",") if p.strip()]
    return ", ".join(parts)


def clean_text(s: str) -> str:
    """Bỏ ngoặc list/quote thừa cho instructor/platform (vài nguồn lưu ['X', 'Y'])."""
    s = str(s).strip()
    if not s or s.lower() == "nan":
        return ""
    if s.startswith("[") and s.endswith("]"):
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, (list, tuple)):
                return ", ".join(str(x).strip() for x in parsed if str(x).strip())
        except (ValueError, SyntaxError):
            pass
    return s


def norm_title(s: str) -> str:
    """Khóa khử trùng lặp: viết thường, bỏ dấu câu, gộp khoảng trắng."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(s).lower())).strip()


# Gộp các biến thể tên chuyên mục về một nhãn chuẩn.
CATEGORY_NORMALIZE = {
    "datascience": "Data Science", "data science": "Data Science",
    "computer science": "Computer Science", "information technology": "Information Technology",
    "web development": "Web Development",
}


def norm_category(s: str) -> str:
    key = re.sub(r"\s+", " ", str(s).strip().lower())
    return CATEGORY_NORMALIZE.get(key, str(s).strip())


def map_level(s: str) -> str:
    s = str(s).strip().lower()
    for k, v in LEVEL_VI.items():
        if k in s:
            return v
    return "Trung cấp"


def adapt(source_path: str, platform_default: str, it_only: bool) -> pd.DataFrame:
    raw = pd.read_csv(source_path, low_memory=False)
    cols_lower = {c.lower().strip(): c for c in raw.columns}
    mapping = {field: _find_col(cols_lower, aliases) for field, aliases in COLUMN_ALIASES.items()}
    base = os.path.basename(source_path)
    plat = platform_default
    for key, p in PLATFORM_BY_FILE.items():
        if key in base.lower():
            plat = p
            break
    print(f"  [{base}] ánh xạ:", {k: v for k, v in mapping.items() if v})

    n = len(raw)
    title = raw[mapping["title"]].astype(str) if mapping["title"] else pd.Series([""] * n)
    category = raw[mapping["category"]].astype(str) if mapping["category"] else pd.Series(["CNTT"] * n)
    subcat = raw[mapping["subcategory"]].astype(str) if mapping["subcategory"] else pd.Series([""] * n)
    topics = (raw[mapping["topics"]].astype(str) if mapping["topics"] else pd.Series([""] * n)).map(clean_topics)
    if mapping["description"]:
        desc = raw[mapping["description"]].astype(str)
    else:
        desc = pd.Series([""] * n)

    out = pd.DataFrame()
    out["title"] = title.str.strip()
    out["type"] = "Khóa học"
    out["level"] = (raw[mapping["level"]].astype(str) if mapping["level"] else pd.Series(["Trung cấp"] * n)).map(map_level)
    out["description"] = desc.str.strip()
    out["category"] = category.str.strip().map(norm_category)
    out["_subcat"] = subcat.str.strip()
    out["topics"] = topics
    out["instructor"] = (raw[mapping["instructor"]].astype(str) if mapping["instructor"] else pd.Series(["N/A"] * n)).map(clean_text)
    out["platform"] = (raw[mapping["platform"]].astype(str).map(clean_text) if mapping["platform"] else pd.Series([plat] * n))
    out["platform"] = out["platform"].replace("", plat)
    out["link"] = raw[mapping["link"]].astype(str) if mapping["link"] else ""

    # Mô tả rỗng/nan -> tổng hợp từ tiêu đề + chủ đề để TF-IDF/embeddings có nội dung.
    empty_desc = out["description"].str.lower().isin(["", "nan"])
    out.loc[empty_desc, "description"] = (out["title"] + ". " + out["topics"]).str[:400]

    # Lọc CNTT/IT theo category + sub-category.
    if it_only:
        hay = (out["category"].astype(str).str.lower() + " " + out["_subcat"].astype(str).str.lower()).fillna("")
        mask = hay.apply(lambda h: any(t in str(h) for t in IT_CATEGORY_TERMS))
        out = out[mask]

    out = out[out["title"].str.len() > 3].drop(columns=["_subcat"])
    out = out.dropna(subset=["title", "description"]).reset_index(drop=True)
    return out


def build_catalog(sources: list[str], platform_default: str, it_only: bool) -> pd.DataFrame:
    frames = [adapt(s, platform_default, it_only) for s in sources]
    df = pd.concat(frames, ignore_index=True)
    before = len(df)
    df["_key"] = df["title"].map(norm_title)
    df = df.sort_values("description", key=lambda s: s.str.len(), ascending=False)  # giữ bản mô tả dài nhất
    df = df.drop_duplicates(subset="_key").drop(columns="_key").reset_index(drop=True)
    print(f"  Khử trùng lặp: {before} -> {len(df)} (loại {before - len(df)} tiêu đề trùng)")
    df.insert(0, "item_id", range(1, len(df) + 1))
    cols = ["item_id", "title", "type", "level", "description", "category", "topics",
            "instructor", "platform", "link"]
    df = df[cols]
    # build_model.py dùng dropna() -> mọi ô PHẢI có giá trị (NaN/"nan" -> điền mặc định).
    # Tránh các token pandas coi là NaN khi đọc lại ("N/A", "NA", "", ...) -> build_model.dropna() rớt dòng.
    defaults = {"title": "Khóa học", "description": "Đang cập nhật", "topics": "Tổng quát",
                "instructor": "Đang cập nhật", "platform": "Đang cập nhật", "link": "Đang cập nhật",
                "category": "CNTT", "level": "Trung cấp"}
    for c in cols:
        df[c] = df[c].astype(str).replace({"nan": "", "None": "", "NaN": "", "N/A": "", "NA": "", "n/a": ""})
        if c in defaults:
            df[c] = df[c].mask(df[c].str.strip() == "", defaults[c])
    return df


def distribution_stats(df: pd.DataFrame, name: str) -> dict:
    desc_len = df["description"].astype(str).map(len)
    vocab = Counter()
    for t in df["title"].astype(str).head(5000):
        vocab.update(re.findall(r"\w+", t.lower()))
    return {
        "name": name,
        "n": len(df),
        "n_categories": df["category"].nunique(),
        "desc_len_mean": float(desc_len.mean()),
        "desc_len_median": float(desc_len.median()),
        "vocab_size": len(vocab),
        "top_categories": df["category"].value_counts().head(8).to_dict(),
    }


def write_compare(syn: dict, real: dict | None):
    lines = ["# Đối chứng phân phối dữ liệu synthetic vs thật (Trụ cột I)\n",
             "| Thuộc tính | Synthetic | Thật |", "|---|---|---|"]
    for k, label in [("n", "Số item"), ("n_categories", "Số chuyên mục"),
                     ("desc_len_mean", "Độ dài mô tả TB"), ("desc_len_median", "Độ dài mô tả trung vị"),
                     ("vocab_size", "Kích thước từ vựng (title, mẫu 5k)")]:
        sv = f"{syn[k]:.1f}" if isinstance(syn[k], float) else syn[k]
        rv = (f"{real[k]:.1f}" if isinstance(real[k], float) else real[k]) if real else "—"
        lines.append(f"| {label} | {sv} | {rv} |")
    lines.append(f"\n**Top chuyên mục (synthetic):** {syn['top_categories']}")
    if real:
        lines.append(f"\n**Top chuyên mục (thật):** {real['top_categories']}")
        lines.append("\n*Biện luận tính đại diện: so sánh độ dài mô tả & độ phong phú từ vựng để đánh "
                     "giá dữ liệu synthetic có mô phỏng hợp lý dữ liệu thật không; chênh lệch lớn -> "
                     "nêu rõ giới hạn. Catalog thật là tiếng Anh (Coursera/Udemy) — embeddings đa ngữ "
                     "xử lý chéo Anh–Việt; nhãn category giữ nguyên tiếng Anh.*")
    else:
        lines.append("\n*Chạy với `--source-dir <thư mục csv>` để bổ sung cột 'Thật' và rebuild artifacts.*")
    out = config.ROOT / "reports" / "data_compare.md"
    os.makedirs(out.parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("-> reports/data_compare.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="MỘT CSV dataset thật")
    ap.add_argument("--source-dir", help="Thư mục chứa nhiều CSV Kaggle (hợp nhất)")
    ap.add_argument("--platform-default", default="Coursera")
    ap.add_argument("--no-it-filter", action="store_true", help="KHÔNG lọc riêng lĩnh vực CNTT")
    ap.add_argument("--compare-only", action="store_true")
    args = ap.parse_args()

    syn = distribution_stats(pd.read_csv(config.ITEMS_CSV), "synthetic")
    real = None
    sources = []
    if args.source_dir:
        sources = sorted(glob.glob(os.path.join(args.source_dir, "*.csv")))
    elif args.source:
        sources = [args.source]

    if sources and not args.compare_only:
        print(f"Nguồn ({len(sources)}):", [os.path.basename(s) for s in sources])
        catalog = build_catalog(sources, args.platform_default, it_only=not args.no_it_filter)
        dest = config.data_file("it_learning_items_real.csv")
        catalog.to_csv(dest, index=False, encoding="utf-8")
        print(f"-> {dest} ({len(catalog)} item IT thật)")
        print("   Rebuild: đặt ITLR_ITEMS_CSV trỏ file này rồi chạy build_model/embeddings/cf.")
        real = distribution_stats(catalog, "real")

    write_compare(syn, real)


if __name__ == "__main__":
    main()
