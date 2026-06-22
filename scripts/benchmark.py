"""Quick benchmark for tuned retrieval + chatbot."""
import os
import pickle
import sys

# Đưa thư mục gốc dự án vào sys.path để import package `itlr` khi chạy trực tiếp.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from itlr import config
from itlr.chatbot.chatbot import EducationalChatbot
from itlr.core.recommender import search_by_query

items = pickle.load(open(config.artifact("item_list.pkl"), "rb"))
model = pickle.load(open(config.artifact("retrieval_model.pkl"), "rb"))
bot = EducationalChatbot(items, model)

queries = [
    ("Goi y khoa hoc Machine Learning", "Trí tuệ nhân tạo"),
    ("Tim tai lieu Docker Kubernetes", "DevOps"),
    ("Lo trinh hoc An ninh mang", "An ninh mạng"),
    ("Hoc Python co ban", "Lập trình"),
    ("AWS va cloud computing", "Điện toán đám mây"),
    ("React frontend web", "Lập trình Web"),
    ("PostgreSQL database", "Cơ sở dữ liệu"),
]

hits = 0
for q, expected_cat in queries:
    results = search_by_query(items, model, q, top_n=1, use_mmr=True)
    r = bot.chat(q)
    top = results[0] if results else None
    ok = top and top["category"] == expected_cat
    hits += int(ok)
    title = top["title"][:42] if top else "NONE"
    print(f"[{'OK' if ok else 'MISS'}] {q}")
    print(f"      -> {title} | {top['category'] if top else '-'} | {top['score'] if top else 0}%")

print(f"\nCategory accuracy: {hits}/{len(queries)} = {hits/len(queries)*100:.0f}%")
