"""dev.to (EN) — API công khai, có tài liệu: https://developers.forem.com/api

Lấy bài hướng dẫn theo tag (tutorial, beginners, ...). Mỗi article có title, description,
tag_list, user.name, url -> ánh xạ thẳng sang cột thô. Phân loại = tag đầu tiên.
"""

from __future__ import annotations

from scripts.scrape.base import BaseScraper

API = "https://dev.to/api/articles"
DEFAULT_TAGS = ["tutorial", "beginners", "python", "javascript", "webdev", "programming",
                "machinelearning", "datascience", "devops", "security"]


class DevtoScraper(BaseScraper):
    name = "devto"
    lang = "en"
    base_url = "https://dev.to"

    def scrape(self) -> list[dict]:
        rows: list[dict] = []
        seen: set[str] = set()
        per_page = 100
        for tag in DEFAULT_TAGS:
            if len(rows) >= self.max_items:
                break
            page = 1
            while len(rows) < self.max_items:
                data = self.get_json(API, params={"tag": tag, "per_page": per_page, "page": page})
                if not data:
                    break
                for art in data:
                    url = art.get("url") or ""
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    tags = art.get("tag_list") or []
                    if isinstance(tags, str):
                        tags = [t.strip() for t in tags.split(",") if t.strip()]
                    rows.append({
                        "title": art.get("title", ""),
                        "description": art.get("description", ""),
                        "category": (tags[0] if tags else tag),
                        "topics": ", ".join(tags),
                        "instructor": (art.get("user") or {}).get("name", ""),
                        "platform": "dev.to",
                        "link": url,
                        "level": "",
                    })
                    if len(rows) >= self.max_items:
                        break
                page += 1
        return rows[:self.max_items]
