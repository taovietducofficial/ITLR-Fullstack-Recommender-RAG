"""
Build tuned content-based recommendation + retrieval model.

Algorithms: Multi-field TF-IDF + BM25 + Hybrid Scoring v2 + MMR
Run: python build_model.py
"""

import os
import pickle
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd

from itlr import config
from itlr.core.bm25 import BM25Index
from itlr.core.recommender import (
    build_field_corpus,
    build_retrieval_model,
    create_vectorizer,
    detect_category_from_query,
    search_by_query,
)

EVAL_QUERIES = [
    ("Machine Learning khóa học", "Trí tuệ nhân tạo", "machine learning"),
    ("tài liệu Docker Kubernetes DevOps", "DevOps", "docker"),
    ("học Python lập trình cơ bản", "Lập trình", "python"),
    ("An ninh mạng cybersecurity", "An ninh mạng", "security"),
    ("React JavaScript frontend", "Lập trình Web", "react"),
    ("PostgreSQL database SQL", "Cơ sở dữ liệu", "sql"),
    ("AWS cloud computing", "Điện toán đám mây", "aws"),
    ("Deep Learning neural network", "Trí tuệ nhân tạo", "deep learning"),
    ("Flutter mobile app", "Lập trình Mobile", "flutter"),
    ("Blockchain Web3", "Blockchain & Web3", "blockchain"),
]


def evaluate_retrieval(item_list, retrieval_model):
    """Measure category hit rate and topic relevance on labeled queries."""
    cat_hits = 0
    topic_hits = 0
    total = len(EVAL_QUERIES)

    for query, expected_cat, expected_topic in EVAL_QUERIES:
        results = search_by_query(item_list, retrieval_model, query, top_n=3, use_mmr=False)
        if not results:
            continue

        top = results[0]
        if top["category"] == expected_cat:
            cat_hits += 1
        elif detect_category_from_query(query, [top["category"]]) == expected_cat:
            cat_hits += 0.5

        topic_norm = expected_topic.lower()
        title_desc = (top["title"] + " " + top["topics"] + " " + top["description"]).lower()
        if topic_norm in title_desc:
            topic_hits += 1

    cat_rate = cat_hits / total * 100
    topic_rate = topic_hits / total * 100
    avg_score = 0.0

    for query, _, _ in EVAL_QUERIES:
        results = search_by_query(item_list, retrieval_model, query, top_n=1, use_mmr=False)
        if results:
            avg_score += results[0]["score"]
    avg_score = avg_score / total

    return {
        "category_accuracy": round(cat_rate, 1),
        "topic_accuracy": round(topic_rate, 1),
        "avg_top1_score": round(avg_score, 1),
    }


def main():
    items = pd.read_csv(config.ITEMS_CSV)
    items.dropna(inplace=True)

    keep_cols = [
        "item_id", "title", "type", "description", "category",
        "topics", "instructor", "platform", "link",
    ]
    if "level" in items.columns:
        keep_cols.insert(3, "level")
    item_list = items[keep_cols].copy()

    fields = ["full", "title", "topics"]
    vectorizers = {}
    matrices = {}

    for field in fields:
        corpus = build_field_corpus(items, field)
        vectorizer = create_vectorizer()
        matrices[field] = vectorizer.fit_transform(corpus)
        vectorizers[field] = vectorizer

    raw_docs = [
        f"{row['title']} {row['topics']} {row['category']} {row['description']}"
        for _, row in items.iterrows()
    ]
    bm25 = BM25Index(k1=1.4, b=0.75).fit(raw_docs)

    retrieval_model = build_retrieval_model(item_list, vectorizers, matrices, bm25)

    os.makedirs(config.ARTIFACTS_DIR, exist_ok=True)
    with open(config.artifact("item_list.pkl"), "wb") as f:
        pickle.dump(item_list, f)
    with open(config.artifact("tfidf_vectorizer.pkl"), "wb") as f:
        pickle.dump(vectorizers["full"], f)
    with open(config.artifact("tfidf_matrix.pkl"), "wb") as f:
        pickle.dump(matrices["full"], f)
    with open(config.artifact("retrieval_model.pkl"), "wb") as f:
        pickle.dump(retrieval_model, f)

    metrics = evaluate_retrieval(item_list, retrieval_model)

    print("=" * 60)
    print("Tuned Model: Multi-field TF-IDF + BM25 + Hybrid v2 + MMR")
    print("=" * 60)
    print(f"Items: {len(item_list)}")
    print(f"TF-IDF features (full): {matrices['full'].shape[1]}")
    print()
    print("Retrieval Quality (10 labeled queries):")
    print(f"  Category accuracy @top1: {metrics['category_accuracy']}%")
    print(f"  Topic relevance @top1:   {metrics['topic_accuracy']}%")
    print(f"  Avg top-1 score:         {metrics['avg_top1_score']}%")
    print()

    print("Query-based retrieval samples:")
    for q, _, _ in EVAL_QUERIES[:3]:
        results = search_by_query(item_list, retrieval_model, q, top_n=2, use_mmr=True)
        print(f"  Q: {q}")
        for r in results:
            print(f"     -> {r['title'][:45]} ({r['category']}) {r['score']}%")


if __name__ == "__main__":
    main()
