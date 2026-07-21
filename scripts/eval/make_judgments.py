"""Sinh nhãn liên quan (relevance judgments) cho khung đánh giá.

Đầu ra:
  1) data/eval/relevance_judgments.csv  (nhãn bán-tự-động, dùng TRAIN/dev)
       Cột: query_id, query, category, topic, item_id, grade
       Quy tắc (rule-based trên TOÀN catalog, KHÔNG dùng retrieval -> không thiên lệch
       về hệ thống đang đánh giá):
         - một item là "liên quan" với truy vấn chủ đề T (trong chuyên mục C) nếu item
           CÓ DẠY chủ đề T (topic token khớp).
         - grade 2 (mạnh)  : khớp topic VÀ cùng category C.
         - grade 1 (một phần): khớp topic nhưng KHÁC category (liên quan chéo lĩnh vực).
         - grade 0          : không khớp topic -> không lưu (theo chuẩn qrels TREC).
       Cách này giữ tập liên quan TẬP TRUNG (vài chục–vài trăm item) -> Recall/MAP có ý nghĩa,
       đồng thời tránh "vòng tròn" vì nhãn sinh từ metadata, không từ điểm của hệ thống.

  2) data/eval/human_judgments.csv  (KHUNG nhãn vàng người gán, dùng TEST sạch)
       Lấy mẫu phân tầng ~N cặp (query, item) trải đều các mức grade tự động -> cột
       `human_label` để NGƯỜI gán tay (1 = liên quan, 0 = không). Cột `auto_grade` giữ để
       tính Cohen's Kappa (đồng thuận auto vs người) sau khi gán xong.
       Cờ --simulate-human: điền `human_label` bằng MÔ PHỎNG có nhiễu (CHỈ để chạy thử
       pipeline đầu-cuối) — phải thay bằng nhãn người THẬT trước khi dùng làm số liệu chính thức.

Cách chạy:
    python scripts/eval/make_judgments.py
    python scripts/eval/make_judgments.py --queries-per-cat 3 --human-pool 250 --simulate-human
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd  # noqa: E402

from itlr import config  # noqa: E402
from itlr.core.recommender import parse_topics  # noqa: E402

SKIP_CATEGORIES = {"Tài liệu cộng đồng"}

MIN_CAT_FREQ = 20
MAX_CAT_FREQ = 320
MAX_TOTAL_FREQ = 750


def top_topics_per_category(items: pd.DataFrame, per_cat: int) -> dict:
    """Với mỗi category, chọn `per_cat` topic có tần suất 'vừa phải' làm truy vấn.

    Tần suất vừa phải -> tập liên quan tập trung (vài chục–vài trăm item) thay vì hàng
    nghìn, để Recall@K / MAP / NDCG@K đều mang ý nghĩa (catalog synthetic dùng lại topic
    rất dày nên topic phổ biến nhất sẽ phủ cả nghìn item)."""
    total_freq: Counter = Counter()
    item_topics_all = [parse_topics(t) for t in items["topics"]]
    for ts in item_topics_all:
        total_freq.update(ts)

    out = {}
    for cat, group in items.groupby("category"):
        if cat in SKIP_CATEGORIES:
            continue
        counter: Counter = Counter()
        for topics_str in group["topics"]:
            for t in parse_topics(topics_str):
                if len(t) > 2:
                    counter[t] += 1
        eligible = [
            t for t, c in counter.items()
            if MIN_CAT_FREQ <= c <= MAX_CAT_FREQ and total_freq[t] <= MAX_TOTAL_FREQ
        ]
        eligible.sort(key=lambda t: counter[t], reverse=True)
        topics = eligible[:per_cat]
        if len(topics) < per_cat:
            extra = [t for t, c in counter.most_common() if t not in topics and c >= 5]
            topics += extra[: per_cat - len(topics)]
        if topics:
            out[cat] = topics
    return out


def build_queries(topic_map: dict) -> list:
    """Tạo danh sách truy vấn (qid, query_text, category, topic)."""
    queries = []
    qid = 0
    for cat, topics in topic_map.items():
        for topic in topics:
            qid += 1
            query_text = f"{topic} {cat}".strip()
            queries.append({
                "query_id": f"Q{qid:03d}",
                "query": query_text,
                "category": cat,
                "topic": topic,
            })
    return queries


import json  # noqa: E402


GLOSSARY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "itlr", "chatbot", "data", "it_glossary.json")
NAT_MIN_TOTAL, NAT_MAX_TOTAL = 30, 900


def _mask_terms(concept: dict, target_topics: set) -> set:
    """Tập token TIẾNG ANH cần XÓA khỏi định nghĩa để không lộ token topic (chống rò rỉ từ vựng).

    CHỈ mask token ASCII/tiếng Anh (tên topic catalog + alias tiếng Anh); GIỮ NGUYÊN mọi từ
    tiếng Việt (kể cả tên khái niệm) -> truy vấn đọc tự nhiên mà lexical vẫn không khai thác
    được token topic tiếng Anh có trọng số cao trong index."""
    terms = set()
    for s in list(concept.get("aliases", [])) + list(target_topics):
        for tok in str(s).lower().split():
            tok = tok.strip(".,:;()\"'")
            if len(tok) > 1 and tok.isascii():
                terms.add(tok)
    return terms


def _natural_query_text(concept: dict, target_topics: set, max_tokens: int = 28) -> str:
    """Dựng câu truy vấn từ định nghĩa, chỉ MASK token topic tiếng Anh; giữ nguyên tiếng Việt."""
    definition = str(concept.get("definition", "")).split(". ")[0]
    mask = _mask_terms(concept, target_topics)
    kept = []
    for raw in definition.split():
        word = raw.strip(".,:;()\"'")
        if not word:
            continue
        if word.isascii() and word.lower() in mask:
            continue
        kept.append(word)
        if len(kept) >= max_tokens:
            break
    return " ".join(kept).strip()


def load_glossary_natural_queries(items: pd.DataFrame, max_per_cat: int) -> list:
    """Sinh truy vấn tự nhiên từ glossary, gán topic mục tiêu + chuyên mục thống lĩnh từ catalog."""
    with open(GLOSSARY_PATH, encoding="utf-8") as f:
        concepts = json.load(f)["concepts"]

    total_freq: Counter = Counter()
    topic_cat: dict = {}
    for topics_str, cat in zip(items["topics"], items["category"]):
        for t in parse_topics(topics_str):
            total_freq[t] += 1
            topic_cat.setdefault(t, Counter())[cat] += 1
    catalog_topics = set(total_freq)

    by_cat: dict = {}
    for c in concepts.values():
        ttopics = {t.lower() for t in c.get("topics", [])} & catalog_topics
        if not ttopics:
            continue
        tot = sum(total_freq[t] for t in ttopics)
        if not (NAT_MIN_TOTAL <= tot <= NAT_MAX_TOTAL):
            continue
        cat_votes: Counter = Counter()
        for t in ttopics:
            cat_votes.update(topic_cat[t])
        target_cat = cat_votes.most_common(1)[0][0]
        qtext = _natural_query_text(c, ttopics)
        if len(qtext.split()) < 5:
            continue
        by_cat.setdefault(target_cat, []).append({
            "topics": ttopics, "category": target_cat, "query": qtext,
            "concept": c.get("name", ""), "ntot": tot,
        })

    queries, qid = [], 0
    for cat, lst in by_cat.items():
        lst.sort(key=lambda q: abs(q["ntot"] - 250))
        for q in lst[:max_per_cat]:
            qid += 1
            q["query_id"] = f"Q{qid:03d}"
            q["topic"] = sorted(q["topics"])[0]
            queries.append(q)
    return queries


def grade_item(query: dict, row_category: str, row_topics: set) -> int:
    """Quy tắc gán grade tự động cho một cặp (query, item).

    Hỗ trợ cả 1 topic (`query['topic']`) lẫn nhiều topic (`query['topics']` — chế độ natural):
    khớp NẾU item chứa BẤT KỲ topic mục tiêu nào (khớp chính xác token, không substring).
    """
    targets = query.get("topics") or {query["topic"]}
    topic_match = bool(set(targets) & row_topics)
    if not topic_match:
        return 0
    return 2 if row_category == query["category"] else 1


def generate_relevance(items: pd.DataFrame, queries: list) -> list:
    """Quét catalog, sinh các dòng qrels (chỉ lưu grade >= 1)."""
    item_topics = [parse_topics(t) for t in items["topics"]]
    item_cats = items["category"].tolist()
    item_ids = items["item_id"].astype(int).tolist()

    rows = []
    for q in queries:
        n_rel = 0
        for cat, topics, iid in zip(item_cats, item_topics, item_ids):
            g = grade_item(q, cat, topics)
            if g >= 1:
                rows.append({
                    "query_id": q["query_id"], "query": q["query"],
                    "category": q["category"], "topic": q["topic"],
                    "item_id": iid, "grade": g,
                })
                n_rel += 1
        if n_rel == 0:
            print(f"  [cảnh báo] {q['query_id']} '{q['query']}' không có item liên quan")
    return rows


def write_csv(path: str, rows: list, fieldnames: list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def sample_human_pool(qrels_rows: list, all_item_ids: list, pool_size: int, seed: int) -> list:
    """Lấy mẫu phân tầng cặp (query,item) cho người gán: trộn grade 2 / grade 1 / grade 0.

    grade-0 (negative) được lấy ngẫu nhiên trong catalog (không nằm trong qrels của query đó)
    để bộ test người gán có cả ca KHÔNG liên quan -> đo precision đúng nghĩa.
    """
    rng = random.Random(seed)
    by_query: dict = {}
    for r in qrels_rows:
        by_query.setdefault(r["query_id"], {"q": r, "pos": []})
        by_query[r["query_id"]]["pos"].append(r)

    qids = list(by_query.keys())
    if not qids:
        return []
    per_q = max(2, pool_size // len(qids))
    pool = []
    for qid, bucket in by_query.items():
        q = bucket["q"]
        pos = bucket["pos"]
        pos_ids = {p["item_id"] for p in pos}
        g2 = [p for p in pos if p["grade"] == 2]
        g1 = [p for p in pos if p["grade"] == 1]
        chosen = []
        rng.shuffle(g2); rng.shuffle(g1)
        chosen += g2[: max(1, per_q // 3)]
        chosen += g1[: max(1, per_q // 3)]
        n_neg = max(1, per_q - len(chosen))
        negs = []
        tries = 0
        while len(negs) < n_neg and tries < n_neg * 20:
            tries += 1
            iid = rng.choice(all_item_ids)
            if iid not in pos_ids:
                negs.append(iid)
        for p in chosen:
            pool.append({"query_id": qid, "query": q["query"], "item_id": p["item_id"],
                         "auto_grade": p["grade"], "human_label": ""})
        for iid in negs:
            pool.append({"query_id": qid, "query": q["query"], "item_id": iid,
                         "auto_grade": 0, "human_label": ""})
    rng.shuffle(pool)
    return pool[:pool_size] if pool_size else pool


def simulate_human(pool: list, seed: int) -> None:
    """[CHỈ ĐỂ THỬ PIPELINE] Điền human_label mô phỏng: ~88% đồng thuận với auto.

    auto_grade>=1 -> human 1, auto_grade 0 -> human 0, lật nhãn ~12% để tạo bất đồng
    thực tế (đo Cohen's Kappa < 1). KHÔNG dùng cho số liệu báo cáo chính thức.
    """
    rng = random.Random(seed + 99)
    for r in pool:
        base = 1 if int(r["auto_grade"]) >= 1 else 0
        r["human_label"] = str(1 - base if rng.random() < 0.12 else base)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries-per-cat", type=int, default=3)
    ap.add_argument("--human-pool", type=int, default=250)
    ap.add_argument("--natural", action="store_true",
                    help="Truy vấn câu hỏi tự nhiên từ glossary (không chứa token topic) -> "
                         "phá trần lexical, buộc hiểu ngữ nghĩa")
    ap.add_argument("--simulate-human", action="store_true",
                    help="Điền nhãn người MÔ PHỎNG (chỉ để chạy thử pipeline)")
    ap.add_argument("--out", default="eval/relevance_judgments.csv",
                    help="Đường dẫn qrels đầu ra (tương đối DATA_DIR)")
    ap.add_argument("--no-human", action="store_true",
                    help="Bỏ qua sinh human_judgments.csv (tránh ghi đè khi tạo benchmark phụ)")
    ap.add_argument("--seed", type=int, default=20240623)
    args = ap.parse_args()

    items = pd.read_csv(config.ITEMS_CSV).dropna(subset=["category", "topics"]).reset_index(drop=True)
    print(f"Catalog: {len(items)} items, {items['category'].nunique()} chuyên mục")

    if args.natural:
        queries = load_glossary_natural_queries(items, args.queries_per_cat)
        print(f"Sinh {len(queries)} truy vấn TỰ NHIÊN từ glossary (không lộ token topic)")
        for q in queries[:3]:
            print(f"   vd [{q['concept']}] -> \"{q['query'][:70]}...\"")
    else:
        topic_map = top_topics_per_category(items, args.queries_per_cat)
        queries = build_queries(topic_map)
        print(f"Sinh {len(queries)} truy vấn ({args.queries_per_cat}/chuyên mục)")

    qrels = generate_relevance(items, queries)
    rel_path = config.data_file(args.out)
    write_csv(rel_path, qrels, ["query_id", "query", "category", "topic", "item_id", "grade"])
    n_q = len({r["query_id"] for r in qrels})
    g2 = sum(1 for r in qrels if r["grade"] == 2)
    g1 = sum(1 for r in qrels if r["grade"] == 1)
    print(f"-> {rel_path}")
    print(f"   {len(qrels)} dòng qrels | {n_q} truy vấn | grade2={g2} grade1={g1}"
          f" | TB {len(qrels)/max(n_q,1):.0f} item liên quan/truy vấn")

    if args.no_human:
        return
    all_ids = items["item_id"].astype(int).tolist()
    pool = sample_human_pool(qrels, all_ids, args.human_pool, args.seed)
    if args.simulate_human:
        simulate_human(pool, args.seed)
        print("   [!] human_label = MÔ PHỎNG (--simulate-human) — thay bằng nhãn người THẬT trước khi báo cáo")
    hum_path = config.data_file("eval/human_judgments.csv")
    write_csv(hum_path, pool, ["query_id", "query", "item_id", "auto_grade", "human_label"])
    print(f"-> {hum_path}")
    print(f"   {len(pool)} cặp (query,item) chờ người gán "
          f"({'ĐÃ mô phỏng' if args.simulate_human else 'human_label TRỐNG — cần gán tay'})")


if __name__ == "__main__":
    main()
