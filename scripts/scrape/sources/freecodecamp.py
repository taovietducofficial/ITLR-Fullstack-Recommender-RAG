"""freeCodeCamp News (EN) — nội dung CC-licensed, RSS công khai.

RSS: https://www.freecodecamp.org/news/rss/ (mỗi <item> có title, link, description/content,
category). Parse bằng xml.etree.ElementTree (THƯ VIỆN CHUẨN — không cần lxml). RSS chỉ ~vài chục
item gần nhất nên thường ít hơn --max.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from scripts.scrape.base import BaseScraper

RSS = "https://www.freecodecamp.org/news/rss/"
NS = {"content": "http://purl.org/rss/1.0/modules/content/",
      "dc": "http://purl.org/dc/elements/1.1/"}


def _strip_html(html: str, limit: int = 500) -> str:
    text = BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:limit]


def _text(node) -> str:
    return (node.text or "").strip() if node is not None else ""


class FreeCodeCampScraper(BaseScraper):
    name = "freecodecamp"
    lang = "en"
    base_url = "https://www.freecodecamp.org"

    def scrape(self) -> list[dict]:
        resp = self.get(RSS)
        if resp is None:
            return []
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            print(f"  [skip] RSS không parse được: {e}", flush=True)
            return []

        rows: list[dict] = []
        for item in root.iter("item"):
            if len(rows) >= self.max_items:
                break
            title = _text(item.find("title"))
            link = _text(item.find("link"))
            if not title or not link:
                continue
            cats = [_text(c) for c in item.findall("category") if _text(c)]
            encoded = item.find("content:encoded", NS)
            desc_raw = _text(encoded) or _text(item.find("description"))
            rows.append({
                "title": title,
                "description": _strip_html(desc_raw),
                "category": (cats[0] if cats else "Programming"),
                "topics": ", ".join(cats),
                "instructor": _text(item.find("dc:creator", NS)) or "freeCodeCamp",
                "platform": "freeCodeCamp",
                "link": link,
                "level": "",
            })
        return rows
