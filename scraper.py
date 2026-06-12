"""
Scraper для Яндекс Wordstat.

Два режима (выбираются автоматически):
  1. Direct API — если задан YANDEX_DIRECT_TOKEN в .env (рекомендуется, в рамках ToS)
  2. Browser     — Playwright, если токена нет (требует логин/пароль)
"""

import json
import time
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import urllib.request
import urllib.parse
import urllib.error

from config import (
    YANDEX_LOGIN, YANDEX_PASSWORD, YANDEX_DIRECT_TOKEN,
    REGION_ID, REQUEST_DELAY, COOKIES_FILE,
)

log = logging.getLogger(__name__)


@dataclass
class RawKeyword:
    keyword: str
    frequency: int
    source_seed: str


# ---------------------------------------------------------------------------
# Режим 1: Яндекс Директ API (официальный, рекомендуемый)
# ---------------------------------------------------------------------------

class DirectAPIClient:
    """
    Использует метод KeywordForecast API Директа для получения частот.
    Документация: https://yandex.ru/dev/direct/doc/ref-v5/keywordstat/
    Требует токен OAuth (бесплатно, без лимита на запросы к Wordstat).
    """

    API_URL = "https://api.direct.yandex.com/json/v5/keywordstat"

    def __init__(self, token: str):
        self.token = token

    def get_frequencies(self, keywords: list[str], region_id: int) -> dict[str, int]:
        """Возвращает {keyword: frequency} для списка ключевых слов."""
        # API принимает до 10 000 фраз за раз, отправляем батчами по 200
        results: dict[str, int] = {}
        batch_size = 200
        for i in range(0, len(keywords), batch_size):
            batch = keywords[i: i + batch_size]
            data = self._request(batch, region_id)
            results.update(data)
            time.sleep(1)
        return results

    def _request(self, keywords: list[str], region_id: int) -> dict[str, int]:
        body = json.dumps({
            "method": "createOrUpdateKeywords",
            "params": {
                "Keywords": [
                    {"Keyword": kw, "RegionIds": [region_id]}
                    for kw in keywords
                ]
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            self.API_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept-Language": "ru",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            freq_map: dict[str, int] = {}
            for item in result.get("result", {}).get("Keywords", []):
                freq_map[item["Keyword"]] = item.get("Impressions", 0)
            return freq_map
        except Exception as exc:
            log.warning("Direct API ошибка: %s", exc)
            return {}


# ---------------------------------------------------------------------------
# Режим 2: Browser scraper (Playwright)
# ---------------------------------------------------------------------------

class WordstatBrowserScraper:
    WORDSTAT_URL = "https://wordstat.yandex.ru/"
    LOGIN_URL = "https://passport.yandex.ru/auth"

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._page = None

    def scrape(self, seeds: list[str]) -> list[RawKeyword]:
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        except ImportError:
            raise RuntimeError("Установи playwright: pip install playwright && playwright install chromium")

        results: list[RawKeyword] = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            context = browser.new_context(
                locale="ru-RU",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            )

            self._restore_cookies(context)
            self._page = context.new_page()

            if not self._is_logged_in():
                self._login(PWTimeout)

            self._save_cookies(context)

            for seed in seeds:
                log.info("Обрабатываю seed: %s", seed)
                try:
                    kws = self._fetch_keyword(seed)
                    results.extend(kws)
                    log.info("  → найдено %d фраз", len(kws))
                except Exception as exc:
                    log.warning("Ошибка при обработке '%s': %s", seed, exc)
                time.sleep(REQUEST_DELAY)

            browser.close()
        return results

    def _is_logged_in(self) -> bool:
        self._page.goto(self.WORDSTAT_URL)
        self._page.wait_for_load_state("networkidle", timeout=10_000)
        return "passport.yandex" not in self._page.url

    def _login(self, PWTimeout) -> None:
        if not YANDEX_LOGIN or not YANDEX_PASSWORD:
            raise ValueError("Заполни YANDEX_LOGIN и YANDEX_PASSWORD в .env")

        log.info("Логинюсь в Яндекс...")
        self._page.goto(self.LOGIN_URL)
        self._page.wait_for_selector('input[name="login"]', timeout=10_000)
        self._page.fill('input[name="login"]', YANDEX_LOGIN)
        self._page.click('button[type="submit"]')

        self._page.wait_for_selector('input[name="passwd"]', timeout=10_000)
        self._page.fill('input[name="passwd"]', YANDEX_PASSWORD)
        self._page.click('button[type="submit"]')

        # Ждём загрузки Wordstat после логина
        try:
            self._page.wait_for_selector(
                'input[class*="b-form-input__input"]', timeout=20_000
            )
        except PWTimeout:
            raise RuntimeError(
                "Логин завис — возможно, Яндекс просит капчу или 2FA. "
                "Запусти: python main.py --visible"
            )
        log.info("Логин успешен")

    def _fetch_keyword(self, seed: str) -> list[RawKeyword]:
        from playwright.sync_api import TimeoutError as PWTimeout

        # Сохраняем регион в URL при каждом переходе
        url = f"{self.WORDSTAT_URL}?region={REGION_ID}"
        self._page.goto(url)
        self._page.wait_for_selector('input[class*="b-form-input__input"]', timeout=10_000)

        search_input = self._page.locator('input[class*="b-form-input__input"]').first
        search_input.fill("")
        search_input.fill(seed)
        search_input.press("Enter")

        try:
            self._page.wait_for_selector(".b-words-table__table", timeout=12_000)
        except PWTimeout:
            log.warning("Таблица не появилась для '%s'", seed)
            return []

        # Собираем и основную колонку, и правую (похожие запросы)
        return self._parse_left_column(seed) + self._parse_right_column(seed)

    def _parse_left_column(self, seed: str) -> list[RawKeyword]:
        return self._parse_column(seed, ".b-words-table__table:first-child")

    def _parse_right_column(self, seed: str) -> list[RawKeyword]:
        return self._parse_column(seed, ".b-words-table__table:last-child")

    def _parse_column(self, seed: str, table_selector: str) -> list[RawKeyword]:
        results: list[RawKeyword] = []
        rows = self._page.locator(
            f"{table_selector} .b-words-table__item"
        ).all()

        for row in rows:
            try:
                kw_el = row.locator(".b-words-table__word-value")
                freq_el = row.locator(".b-words-table__count-cell")
                if not kw_el.count() or not freq_el.count():
                    continue

                keyword = kw_el.inner_text().strip()
                freq_raw = freq_el.inner_text().strip()
                frequency = self._parse_frequency(freq_raw)

                if keyword and frequency > 0:
                    results.append(RawKeyword(keyword=keyword, frequency=frequency, source_seed=seed))
            except Exception:
                continue
        return results

    @staticmethod
    def _parse_frequency(raw: str) -> int:
        """Парсит '1 234' или '1,234' или '12345' → int."""
        cleaned = re.sub(r"[\s\xa0,]", "", raw)
        return int(cleaned) if cleaned.isdigit() else 0

    def _restore_cookies(self, context) -> None:
        path = Path(COOKIES_FILE)
        if path.exists():
            try:
                cookies = json.loads(path.read_text(encoding="utf-8"))
                context.add_cookies(cookies)
                log.info("Сессия восстановлена из кэша")
            except Exception:
                pass

    def _save_cookies(self, context) -> None:
        Path(COOKIES_FILE).parent.mkdir(parents=True, exist_ok=True)
        cookies = context.cookies()
        Path(COOKIES_FILE).write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
        )


# ---------------------------------------------------------------------------
# Фасад — выбирает режим автоматически
# ---------------------------------------------------------------------------

def scrape_keywords(seeds: list[str], headless: bool = True) -> list[RawKeyword]:
    if YANDEX_DIRECT_TOKEN:
        log.info("Режим: Яндекс Директ API (официальный)")
        client = DirectAPIClient(YANDEX_DIRECT_TOKEN)
        freq_map = client.get_frequencies(seeds, REGION_ID)
        return [
            RawKeyword(keyword=kw, frequency=freq, source_seed=kw)
            for kw, freq in freq_map.items()
        ]
    else:
        log.info("Режим: Browser scraper (Playwright)")
        log.warning(
            "Рекомендуется использовать Яндекс Директ API — "
            "задай YANDEX_DIRECT_TOKEN в .env для работы в рамках ToS Яндекса."
        )
        scraper = WordstatBrowserScraper(headless=headless)
        return scraper.scrape(seeds)
