"""Lớp nền cho mọi scraper — cào HTTP TĨNH lịch sự (tôn trọng robots.txt, rate-limit, retry).

Mỗi scraper con chỉ cần override `scrape()` trả về list dict với KEY chuẩn khớp COLUMN_ALIASES
trong scripts/eval/adapt_real_data.py:
    title, description, category, topics, instructor, platform, link, level
(thiếu key nào -> adapt_real_data tự điền mặc định, nên không bắt buộc đủ hết).

Nguyên tắc:
  - Đọc & cache robots.txt; URL bị cấm -> BỎ QUA (in cảnh báo), không cào.
  - Rate-limit (sleep `delay` giây giữa các request) + retry/backoff khi 429/5xx.
  - User-Agent định danh dự án (lịch sự, dễ chặn nếu cần).
"""

from __future__ import annotations

import os
import time
import urllib.robotparser
from urllib.parse import urlparse

import pandas as pd
import requests

# Cột chuẩn cho CSV thô — KHỚP alias trong adapt_real_data.COLUMN_ALIASES.
RAW_COLUMNS = ["title", "description", "category", "topics", "instructor", "platform", "link", "level"]

USER_AGENT = (
    "ITLR-Recommender-DataBot/1.0 (+https://github.com/taovietducofficial; "
    "academic dataset enrichment; respects robots.txt)"
)


class BaseScraper:
    """Lớp nền. Lớp con đặt `name`, `lang` ("vi"/"en"), `base_url` và override `scrape()`."""

    name: str = "base"
    lang: str = "en"
    base_url: str = ""

    def __init__(self, max_items: int = 200, delay: float = 1.0, timeout: float = 20.0):
        self.max_items = max_items
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._last_request = 0.0
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}

    # ── robots.txt ────────────────────────────────────────────────────────────
    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser:
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        rp = self._robots.get(origin)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            # Tải robots.txt bằng SESSION của ta (đúng User-Agent). KHÔNG dùng rp.read():
            # nó fetch bằng UA "Python-urllib" mặc định -> site sau Cloudflare trả 403 ->
            # robotparser tưởng "disallow_all" và chặn nhầm MỌI URL.
            try:
                resp = self.session.get(origin + "/robots.txt", timeout=self.timeout)
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    rp.parse([])  # không có/đọc được robots -> mặc định cho phép (vẫn rate-limit)
            except requests.RequestException:
                rp.parse([])
            self._robots[origin] = rp
        return rp

    def allowed(self, url: str) -> bool:
        try:
            return self._robots_for(url).can_fetch(USER_AGENT, url)
        except Exception:
            return True

    # ── HTTP có rate-limit + retry ──────────────────────────────────────────────
    def _throttle(self):
        wait = self.delay - (time.time() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.time()

    def get(self, url: str, *, params: dict | None = None, retries: int = 3):
        """GET có kiểm robots + rate-limit + retry/backoff. Trả Response hoặc None nếu bị cấm/lỗi."""
        if not self.allowed(url):
            print(f"  [skip: blocked by robots] {url}", flush=True)
            return None
        for attempt in range(retries):
            self._throttle()
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as e:
                print(f"  [retry {attempt + 1}/{retries}] lỗi mạng: {e}", flush=True)
                time.sleep(2 ** attempt)
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                print(f"  [retry {attempt + 1}/{retries}] HTTP {resp.status_code} cho {url}", flush=True)
                time.sleep(2 ** attempt)
                continue
            if resp.status_code != 200:
                print(f"  [skip] HTTP {resp.status_code} cho {url}", flush=True)
                return None
            return resp
        return None

    def get_json(self, url: str, *, params: dict | None = None):
        resp = self.get(url, params=params)
        if resp is None:
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    # ── Giao diện cào ────────────────────────────────────────────────────────────
    def scrape(self) -> list[dict]:
        """Lớp con override: trả list bản ghi (dict với key trong RAW_COLUMNS)."""
        raise NotImplementedError

    # ── Ghi CSV thô ────────────────────────────────────────────────────────────
    @staticmethod
    def to_csv(rows: list[dict], path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        df = pd.DataFrame(rows)
        # Bảo đảm có đủ cột chuẩn (thiếu -> rỗng) và đúng thứ tự.
        for c in RAW_COLUMNS:
            if c not in df.columns:
                df[c] = ""
        df = df[RAW_COLUMNS]
        df.to_csv(path, index=False, encoding="utf-8")
        return len(df)
