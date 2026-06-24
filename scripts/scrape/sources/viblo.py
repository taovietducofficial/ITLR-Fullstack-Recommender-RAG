"""Viblo (VI) — nền tảng blog kỹ thuật tiếng Việt, có API JSON công khai.

Endpoint danh sách bài: https://viblo.asia/api/posts?page=N (trả {data: [...], meta: {...}}).
Mỗi bài có title, contents/excerpt/promote (mô tả), tags (data[].name), user. Parse PHÒNG THỦ
(dùng .get + nhiều fallback) vì schema có thể đổi nhẹ giữa các phiên bản API.
"""

from __future__ import annotations

from scripts.scrape.base import BaseScraper

# Dùng feed "trending" thay vì "newest": feed newest công khai của Viblo hiện bị spam (rao bán
# tài khoản, vay crypto...) tràn ngập; trending là bài kỹ thuật được tương tác thật -> chất lượng cao.
API = "https://viblo.asia/api/posts/trending"


def _first_nonempty(d: dict, keys: list[str]) -> str:
    for k in keys:
        v = d.get(k)
        if v and str(v).strip():
            return str(v).strip()
    return ""


def _extract_tags(post: dict) -> list[str]:
    tags = post.get("tags")
    if isinstance(tags, dict):  # kiểu {"data": [...]}
        tags = tags.get("data", [])
    out = []
    for t in tags or []:
        if isinstance(t, dict):
            name = t.get("name") or t.get("slug")
            if name:
                out.append(str(name))
        elif t:
            out.append(str(t))
    return out


class VibloScraper(BaseScraper):
    name = "viblo"
    lang = "vi"
    base_url = "https://viblo.asia"

    def scrape(self) -> list[dict]:
        rows: list[dict] = []
        seen: set[str] = set()
        page = 1
        empty_pages = 0
        while len(rows) < self.max_items and empty_pages < 2:
            payload = self.get_json(API, params={"page": page})
            posts = (payload or {}).get("data") if isinstance(payload, dict) else None
            if not posts:
                empty_pages += 1
                page += 1
                continue
            empty_pages = 0
            for post in posts:
                if not isinstance(post, dict):
                    continue
                slug = _first_nonempty(post, ["slug"])
                user = post.get("user") or {}
                if isinstance(user, dict):
                    user = user.get("data", user)
                username = (user.get("username") if isinstance(user, dict) else "") or ""
                link = f"{self.base_url}/p/{slug}" if slug else _first_nonempty(post, ["url"])
                if not link or link in seen:
                    continue
                seen.add(link)
                tags = _extract_tags(post)
                rows.append({
                    "title": _first_nonempty(post, ["title"]),
                    "description": _first_nonempty(
                        post, ["contents_short", "promote", "excerpt", "contents", "summary"]),
                    "category": (tags[0] if tags else "Lập trình"),
                    "topics": ", ".join(tags),
                    "instructor": (user.get("name") if isinstance(user, dict) else "") or username,
                    "platform": "Viblo",
                    "link": link,
                    "level": "",
                })
                if len(rows) >= self.max_items:
                    break
            page += 1
        return rows[:self.max_items]
