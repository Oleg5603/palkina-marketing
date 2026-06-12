"""
Запуск:
  python main.py              — headless, credentials из .env
  python main.py --visible    — открыть браузер (нужно для капчи/2FA)
  python main.py --no-scrape  — только классификация уже собранного raw.json
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from dataclasses import asdict

from config import SEED_KEYWORDS, OUTPUT_DIR, MIN_FREQUENCY
from scraper import scrape_keywords, RawKeyword
from classifier import classify_all, ClassifiedKeyword

# ---------------------------------------------------------------------------
# Логирование
# ---------------------------------------------------------------------------

os.makedirs("logs", exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"logs/scout_{timestamp}.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("main")

RAW_PATH = os.path.join(OUTPUT_DIR, "raw_keywords.json")
RESULT_PATH = os.path.join(OUTPUT_DIR, "classified_keywords.json")
REPORT_PATH = os.path.join(OUTPUT_DIR, "report.md")


# ---------------------------------------------------------------------------
# Этапы
# ---------------------------------------------------------------------------

def run_scrape(headless: bool) -> list[RawKeyword]:
    log.info("=== ЭТАП 1: Сбор из Wordstat ===")
    raw = scrape_keywords(SEED_KEYWORDS, headless=headless)

    raw = [r for r in raw if r.frequency >= MIN_FREQUENCY]

    seen: set[str] = set()
    deduped: list[RawKeyword] = []
    for r in raw:
        key = r.keyword.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    log.info("Уникальных фраз (freq ≥ %d): %d", MIN_FREQUENCY, len(deduped))

    with open(RAW_PATH, "w", encoding="utf-8") as f:
        json.dump([asdict(r) for r in deduped], f, ensure_ascii=False, indent=2)
    log.info("Сырые данные → %s", RAW_PATH)
    return deduped


def load_raw() -> list[RawKeyword]:
    with open(RAW_PATH, encoding="utf-8") as f:
        return [RawKeyword(**d) for d in json.load(f)]


def run_classify(raw: list[RawKeyword]) -> list[ClassifiedKeyword]:
    log.info("=== ЭТАП 2: Классификация интента ===")
    classified = classify_all(raw)

    stats = {"high": 0, "medium": 0, "low": 0}
    for c in classified:
        stats[c.intent] += 1
    log.info("high=%d  medium=%d  low=%d", stats["high"], stats["medium"], stats["low"])

    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump([asdict(c) for c in classified], f, ensure_ascii=False, indent=2)
    log.info("Классифицированные данные → %s", RESULT_PATH)
    return classified


def write_report(classified: list[ClassifiedKeyword]) -> None:
    log.info("=== ЭТАП 3: Генерация отчёта ===")

    def table_rows(items: list[ClassifiedKeyword]) -> list[str]:
        rows = []
        for c in items[:40]:
            emotions = ", ".join(c.emotion) if c.emotion else "—"
            cats = ", ".join(c.categories)
            rows.append(f"| {c.keyword} | {c.frequency:,} | {cats} | {emotions} | {c.ad_headline} |")
        return rows

    high = sorted([c for c in classified if c.intent == "high"], key=lambda x: x.frequency, reverse=True)
    medium = sorted([c for c in classified if c.intent == "medium"], key=lambda x: x.frequency, reverse=True)

    header = "| Ключевая фраза | Частота/мес | Категория | Эмоции | Заголовок для Директа |"
    divider = "|---|---|---|---|---|"

    lines = [
        f"# Семантический отчёт — {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        "",
        f"Всего фраз: **{len(classified)}** | High: **{len(high)}** | Medium: **{len(medium)}**",
        "",
        "---",
        "",
        "## High Intent — прямой запрос специалиста (в заголовки объявлений)",
        "",
        header, divider,
        *table_rows(high),
        "",
        "## Medium Intent — осознаёт боль (темы лендингов и статей)",
        "",
        header, divider,
        *table_rows(medium),
        "",
        "---",
        "",
        "## Как использовать",
        "",
        "**High intent** → копируй «Заголовок для Директа» прямо в объявление",
        "",
        "**Medium intent** → создай отдельный лендинг под каждую категорию",
        "(пример: `/izmena` → «Помощь психолога после измены»)",
        "",
        "*Данные: Яндекс Wordstat. Только публичная агрегированная статистика запросов — персональных данных нет.*",
    ]

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log.info("Отчёт → %s", REPORT_PATH)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Semantic Scout")
    parser.add_argument("--visible", action="store_true", help="Открыть браузер (для 2FA/капчи)")
    parser.add_argument("--no-scrape", action="store_true", help="Взять raw из файла, не парсить")
    args = parser.parse_args()

    if args.no_scrape:
        if not os.path.exists(RAW_PATH):
            log.error("Файл %s не найден. Запусти без --no-scrape.", RAW_PATH)
            sys.exit(1)
        raw = load_raw()
        log.info("Загружено: %d фраз", len(raw))
    else:
        raw = run_scrape(headless=not args.visible)

    classified = run_classify(raw)
    write_report(classified)
    log.info("Готово → %s", REPORT_PATH)


if __name__ == "__main__":
    main()
