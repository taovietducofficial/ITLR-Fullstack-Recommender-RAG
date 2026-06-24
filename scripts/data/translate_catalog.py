"""Dịch catalog khóa học EN -> VI (offline) cho bản demo tiếng Việt — CÓ CHECKPOINT.

Chỉ dịch **title + description**: giữ nguyên category/topics/instructor/platform/link.
Model offline facebook/nllb-200-distilled-600M (tải 1 lần ~2.4GB rồi chạy offline) — chất
lượng cao cho thuật ngữ IT, fast tokenizer hợp transformers 5.x.

ĐẶC ĐIỂM CHỐNG MẤT TIẾN ĐỘ:
  - Lưu cache dịch ra `data/translation_cache.json` sau mỗi lô -> KILL/tắt máy giữa chừng
    KHÔNG mất; chạy lại sẽ TIẾP TỤC từ chỗ dở (bỏ qua chuỗi đã dịch).
  - In tiến độ rõ ràng (flush ngay) -> theo dõi được %.
  - Greedy (num_beams=1) + sắp theo độ dài -> nhanh hơn ~2x bản beams=2.

Cách chạy (nên redirect log để xem tiến độ, KHÔNG pipe qua grep gây buffer):
    python -u scripts/data/translate_catalog.py \
        --in data/it_learning_items_real.csv \
        --out data/it_learning_items_real_vi.csv  > reports/translate.log 2>&1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd  # noqa: E402

from itlr import config  # noqa: E402

MODEL = "facebook/nllb-200-distilled-600M"
CACHE_PATH = config.data_file("translation_cache.json")
SKIP_VALUES = {"Đang cập nhật", "Tổng quát", "CNTT", ""}
SAVE_EVERY = 200  # lưu cache ra đĩa sau mỗi N chuỗi dịch được


def load_model():
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(MODEL)
    tok.src_lang = "eng_Latn"
    mdl = AutoModelForSeq2SeqLM.from_pretrained(MODEL)
    mdl.eval()
    return tok, mdl


def load_cache() -> dict[str, str]:
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict[str, str]):
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)  # ghi nguyên tử -> không hỏng cache nếu tắt giữa chừng


def translate_missing(texts: list[str], tok, mdl, batch_size: int, cache: dict[str, str]):
    import torch

    vie = tok.convert_tokens_to_ids("vie_Latn")
    uniq = {t for t in texts if t and t.strip() and t not in SKIP_VALUES}
    todo = sorted((t for t in uniq if t not in cache), key=len)  # sắp theo độ dài -> batch hiệu quả
    total = len(todo)
    print(f"  Tổng chuỗi duy nhất: {len(uniq)} | đã có trong cache: {len(uniq)-total} | "
          f"cần dịch: {total}", flush=True)
    if total == 0:
        return

    t0 = time.time()
    done = 0
    since_save = 0
    for i in range(0, total, batch_size):
        chunk = todo[i:i + batch_size]
        enc = tok(chunk, return_tensors="pt", padding=True, truncation=True, max_length=400)
        with torch.no_grad():
            gen = mdl.generate(**enc, forced_bos_token_id=vie, num_beams=1, max_new_tokens=256)
        for src, g in zip(chunk, gen):
            cache[src] = tok.decode(g, skip_special_tokens=True).strip()
        done += len(chunk)
        since_save += len(chunk)
        if since_save >= SAVE_EVERY or done == total:
            save_cache(cache)
            since_save = 0
            rate = done / max(time.time() - t0, 1e-9)
            eta = (total - done) / max(rate, 1e-9)
            print(f"  {done}/{total} ({100*done/total:.1f}%) | {rate:.1f} chuỗi/s | "
                  f"ETA ~{eta/60:.0f} phút | cache đã lưu", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/it_learning_items_real.csv")
    ap.add_argument("--out", dest="out", default="data/it_learning_items_real_vi.csv")
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--fields", default="title,description")
    args = ap.parse_args()

    df = pd.read_csv(args.inp)
    fields = [f.strip() for f in args.fields.split(",") if f.strip() in df.columns]
    print(f"Nạp {len(df)} khóa từ {args.inp}; dịch trường: {fields}", flush=True)

    cache = load_cache()
    print(f"Cache hiện có: {len(cache)} chuỗi (chạy lại sẽ tiếp tục, không dịch lại)", flush=True)

    print(f"Tải model {MODEL} ...", flush=True)
    tok, mdl = load_model()

    all_texts: list[str] = []
    for f in fields:
        all_texts += df[f].astype(str).tolist()
    translate_missing(all_texts, tok, mdl, args.batch, cache)

    # Áp cache vào dataframe (chuỗi không có trong cache -> giữ nguyên, vd placeholder VI).
    for f in fields:
        df[f] = df[f].astype(str).map(lambda s: cache.get(s, s))
    df.to_csv(args.out, index=False, encoding="utf-8")
    print(f"-> {args.out} ({len(df)} khóa, đã dịch {fields})", flush=True)
    print("   Tiếp theo: rebuild artifacts (ITLR_ITEMS_CSV trỏ file này) + re-seed web.", flush=True)


if __name__ == "__main__":
    main()
