"""CLI điều phối cào dữ liệu -> CSV thô tách theo ngôn ngữ.

Cào các nguồn đã chọn (HTTP tĩnh, tôn trọng robots.txt + rate-limit) rồi ghi mỗi nguồn vào
    <out-dir>/<lang>/<source>.csv      (vd data/scraped/vi/viblo.csv, data/scraped/en/devto.csv)
CSV thô có cột khớp adapt_real_data.COLUMN_ALIASES -> bước gộp dùng build_scraped_catalog.py.

Cách chạy (nên giới hạn nhỏ khi thử trước):
    python scripts/scrape/run_scrape.py --source viblo,devto,f8 --max 200
    python scripts/scrape/run_scrape.py --source all --max 500 --delay 1.5

Bước tiếp theo: python scripts/scrape/build_scraped_catalog.py  (gộp + dịch -> catalog thật).
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from itlr import config  # noqa: E402
from scripts.scrape.registry import SCRAPERS, get_scraper  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Cào dữ liệu IT từ web -> CSV thô (theo ngôn ngữ).")
    ap.add_argument("--source", default="all",
                    help=f"Danh sách nguồn ngăn cách dấu phẩy, hoặc 'all'. Hợp lệ: {', '.join(SCRAPERS)}")
    ap.add_argument("--max", type=int, default=200, help="Số bản ghi tối đa mỗi nguồn")
    ap.add_argument("--out-dir", default=config.data_file("scraped"), help="Thư mục gốc xuất CSV thô")
    ap.add_argument("--delay", type=float, default=1.0, help="Giây nghỉ giữa các request (lịch sự)")
    args = ap.parse_args()

    names = list(SCRAPERS) if args.source.strip().lower() == "all" else \
        [s.strip() for s in args.source.split(",") if s.strip()]

    total = 0
    for name in names:
        try:
            cls = get_scraper(name)
        except KeyError as e:
            print(f"{e}", flush=True)
            continue
        scraper = cls(max_items=args.max, delay=args.delay)
        print(f"Cào '{name}' (lang={scraper.lang}, tối đa {args.max}) ...", flush=True)
        try:
            rows = scraper.scrape()
        except Exception as e:
            print(f"  lỗi khi cào '{name}': {e}", flush=True)
            continue
        dest = os.path.join(args.out_dir, scraper.lang, f"{name}.csv")
        n = scraper.to_csv(rows, dest)
        total += n
        print(f"  {n} bản ghi -> {dest}", flush=True)

    print(f"\nXong: tổng {total} bản ghi. Tiếp theo:\n"
          f"  python scripts/scrape/build_scraped_catalog.py --merge-synthetic", flush=True)


if __name__ == "__main__":
    main()
