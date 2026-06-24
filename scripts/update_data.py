"""Pipeline CẬP NHẬT DỮ LIỆU 1 LỆNH (kiểu CD chạy local) — chạy nơi có Postgres + artifacts thật.

Chuỗi bước (fail-fast, có thể bỏ qua từng bước):
  1) CÀO   : scripts/scrape/run_scrape.py            -> data/scraped/<lang>/*.csv
  2) GỘP   : scripts/scrape/build_scraped_catalog.py --merge-into <csv>  (gộp + dịch EN->VI + khử trùng)
  3) DB    : web `npm run sync`  (UPSERT vào Postgres — GIỮ enrollments, không TRUNCATE)
  4) MODEL : python -m itlr.pipelines.build_model    (rebuild TF-IDF/BM25; KHÔNG đụng embeddings)

Tất cả trỏ về CÙNG một CSV (mặc định data/it_learning_items_real_vi.csv — đúng file web seed + recommender).

Cách chạy:
    python scripts/update_data.py                      # đủ 4 bước, --max 200/nguồn
    python scripts/update_data.py --max 500 --no-translate
    python scripts/update_data.py --skip-scrape        # chỉ gộp lại + DB + model
    python scripts/update_data.py --skip-db --skip-build  # chỉ cào + gộp (vd để lên lịch riêng)

Lên lịch định kỳ (Windows Task Scheduler): xem scripts/update_data.ps1.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_CSV = os.path.join("data", "it_learning_items_real_vi.csv")


def _child_env(extra: dict | None = None) -> dict:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if extra:
        env.update(extra)
    return env


def _csv_count(path: str) -> int | None:
    """Số khóa trong catalog CSV (None nếu chưa có file)."""
    if not os.path.exists(path):
        return None
    import pandas as pd
    return len(pd.read_csv(path))


def _embeddings_count() -> int | None:
    """Số vector trong artifacts/embeddings.pkl (None nếu chưa build embeddings)."""
    import pickle
    from itlr import config
    p = config.artifact("embeddings.pkl")
    if not os.path.exists(p):
        return None
    try:
        emb = pickle.load(open(p, "rb"))
        return emb.shape[0] if hasattr(emb, "shape") else len(emb)
    except Exception:
        return None


def reload_recommender():
    """Gọi recommender (:8000) nạp lại artifacts ngay (POST /admin/reload). CHỊU LỖI: nếu recommender
    chưa chạy thì chỉ nhắc, không làm hỏng pipeline."""
    import json
    import urllib.request
    url = os.environ.get("RECOMMENDER_URL", "http://localhost:8000").rstrip("/") + "/admin/reload"
    print(f"\n▶ 5/5 Nạp lại recommender: POST {url}", flush=True)
    try:
        req = urllib.request.Request(url, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.loads(r.read())
        print(f"✅ Recommender đã nạp lại artifacts: {d.get('items')} khóa.", flush=True)
    except Exception as e:
        print(f"ℹ️  Chưa gọi được /admin/reload ({e}).\n"
              f"   Recommender có thể CHƯA chạy — hãy khởi động/khởi động lại 'npm run dev' "
              f"để chatbot nạp dữ liệu mới.", flush=True)


def run(step: str, cmd, *, cwd=None, env=None, shell=False):
    """Chạy 1 bước, in tiêu đề + thời gian; raise nếu thất bại (fail-fast)."""
    print(f"\n{'='*70}\n▶ {step}\n  $ {cmd if shell else ' '.join(cmd)}\n{'='*70}", flush=True)
    t0 = time.time()
    res = subprocess.run(cmd, cwd=cwd or ROOT, env=env or _child_env(), shell=shell)
    dt = time.time() - t0
    if res.returncode != 0:
        print(f"✗ '{step}' THẤT BẠI (exit {res.returncode}, {dt:.0f}s) — dừng pipeline.", flush=True)
        sys.exit(res.returncode)
    print(f"✅ '{step}' xong ({dt:.0f}s).", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Pipeline cập nhật dữ liệu 1 lệnh (cào -> gộp -> DB -> model).")
    ap.add_argument("--csv", default=DEFAULT_CSV, help="Catalog đích (web seed + recommender dùng chung)")
    ap.add_argument("--source", default="all", help="Nguồn cào (vd viblo,devto) hoặc 'all'")
    ap.add_argument("--max", type=int, default=200, help="Số bản ghi tối đa mỗi nguồn")
    ap.add_argument("--delay", type=float, default=1.0, help="Giây nghỉ giữa request khi cào")
    ap.add_argument("--no-translate", action="store_true", help="Bỏ dịch EN->VI ở bước gộp (nhanh)")
    ap.add_argument("--skip-scrape", action="store_true")
    ap.add_argument("--skip-merge", action="store_true")
    ap.add_argument("--skip-db", action="store_true")
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--embeddings", choices=["auto", "always", "never"], default="auto",
                    help="Rebuild embeddings: auto = CHỈ khi số khóa đổi (mặc định, an toàn); "
                         "always = luôn rebuild; never = không rebuild (nếu số khóa đổi sẽ BỎ build_model "
                         "để tránh lệch item_list/embeddings).")
    ap.add_argument("--restart", action="store_true",
                    help="Sau khi build xong, gọi recommender (:8000) NẠP LẠI artifacts ngay "
                         "(POST /admin/reload) — chatbot thấy dữ liệu mới mà KHÔNG cần tắt/mở lại npm run dev.")
    args = ap.parse_args()

    csv_abs = os.path.abspath(os.path.join(ROOT, args.csv))
    py = sys.executable
    t0 = time.time()
    print(f"PIPELINE CẬP NHẬT DỮ LIỆU -> {args.csv}", flush=True)

    # 1) CÀO
    if not args.skip_scrape:
        run("1/4 Cào dữ liệu web",
            [py, "scripts/scrape/run_scrape.py", "--source", args.source,
             "--max", str(args.max), "--delay", str(args.delay)])
    else:
        print("\n(bỏ qua bước cào)", flush=True)

    # 2) GỘP (nạp vào CSV đích, giữ item_id cũ ổn định, khử trùng toàn cục, dịch EN->VI)
    if not args.skip_merge:
        merge_cmd = [py, "scripts/scrape/build_scraped_catalog.py", "--merge-into", args.csv]
        if args.no_translate:
            merge_cmd.append("--no-translate")
        run("2/4 Gộp vào catalog", merge_cmd)
    else:
        print("\n(bỏ qua bước gộp)", flush=True)

    # 3) DB: UPSERT vào Postgres (giữ enrollments). Chạy trong web/ để dùng web/.env (DATABASE_URL).
    if not args.skip_db:
        run("3/4 UPSERT Postgres (npm run sync)",
            "npm run sync", cwd=os.path.join(ROOT, "web"), shell=True,
            env=_child_env({"ITEMS_CSV": csv_abs}))
    else:
        print("\n(bỏ qua bước DB)", flush=True)

    # 4) MODEL: rebuild artifacts cho recommender — AN TOÀN với embeddings.
    #    item_list.pkl (build_model) và embeddings.pkl PHẢI cùng số khóa, nếu lệch -> tìm kiếm
    #    ngữ nghĩa HỎNG. Nên: số khóa ĐỔI -> rebuild CẢ embeddings; KHÔNG đổi -> chỉ build_model.
    built = False
    if not args.skip_build:
        new_n = _csv_count(csv_abs)
        emb_n = _embeddings_count()
        count_changed = emb_n is not None and new_n is not None and new_n != emb_n
        need_emb = args.embeddings == "always" or (args.embeddings == "auto" and count_changed)

        if count_changed and args.embeddings == "never":
            # Số khóa đổi nhưng người dùng cấm rebuild embeddings -> KHÔNG build_model (tránh lệch).
            print(f"\n⚠️  Số khóa đổi ({emb_n} -> {new_n}) nhưng --embeddings never.\n"
                  f"   BỎ QUA build_model để KHÔNG làm lệch item_list/embeddings (recommender giữ "
                  f"nguyên {emb_n} khóa — cũ nhưng nhất quán).\n"
                  f"   Muốn cập nhật đầy đủ: chạy lại với --embeddings auto (sẽ rebuild cả embeddings).",
                  flush=True)
        else:
            if count_changed:
                print(f"\nℹ️  Số khóa đổi ({emb_n} -> {new_n}) -> sẽ rebuild CẢ embeddings để giữ khớp "
                      f"(mất ~vài chục phút trên CPU).", flush=True)
            run("4/4 Rebuild artifacts (build_model)",
                [py, "-m", "itlr.pipelines.build_model"],
                env=_child_env({"ITLR_ITEMS_CSV": args.csv}))
            if need_emb:
                run("4b/4 Rebuild embeddings (giữ khớp item_list)",
                    [py, "-m", "itlr.pipelines.build_embeddings"],
                    env=_child_env({"ITLR_ITEMS_CSV": args.csv}))
            built = True
    else:
        print("\n(bỏ qua bước build_model)", flush=True)

    # 5) (tùy chọn) Bảo recommender nạp lại artifacts NGAY -> chatbot thấy dữ liệu mới, không cần
    #    tắt/mở lại npm run dev. Chỉ gọi khi THỰC SỰ có build (artifacts đổi).
    if args.restart:
        if built:
            reload_recommender()
        else:
            print("\n(--restart: không có build mới nên không cần nạp lại recommender)", flush=True)

    print(f"\n🎉 PIPELINE XONG sau {time.time()-t0:.0f}s. Catalog: {args.csv}", flush=True)
    if not args.restart:
        print("   Nhắc: chatbot (:8000) chỉ thấy dữ liệu mới sau khi nạp lại artifacts — chạy lại "
              "pipeline kèm --restart, hoặc khởi động lại 'npm run dev'.", flush=True)


if __name__ == "__main__":
    main()
