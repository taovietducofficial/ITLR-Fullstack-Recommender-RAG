"""Sổ đăng ký scraper: tên ngắn -> class. (lang lấy từ thuộc tính class.)

Thêm nguồn mới = tạo class trong sources/ kế thừa BaseScraper rồi đăng ký vào dict dưới đây.
Mỗi nguồn TỰ tôn trọng robots.txt (qua BaseScraper); chỉ thêm nguồn có API/RSS công khai hợp lệ.
"""

from __future__ import annotations

from scripts.scrape.base import BaseScraper
from scripts.scrape.sources.devto import DevtoScraper
from scripts.scrape.sources.freecodecamp import FreeCodeCampScraper
from scripts.scrape.sources.viblo import VibloScraper

SCRAPERS: dict[str, type[BaseScraper]] = {
    "viblo": VibloScraper,                 # VI — API JSON công khai
    "devto": DevtoScraper,                 # EN — API JSON công khai (Forem)
    "freecodecamp": FreeCodeCampScraper,   # EN — RSS (nội dung CC)
}


def get_scraper(name: str) -> type[BaseScraper]:
    if name not in SCRAPERS:
        raise KeyError(f"Không có scraper '{name}'. Hợp lệ: {', '.join(SCRAPERS)}")
    return SCRAPERS[name]
