"""
Запуск:
  python ad_campaign/main.py --url https://ваш-сайт.ru

Создаёт в output/:
  campaign_report.md   — читаемый отчёт, согласуйте с терапевтом
  direct_campaign.csv  — готов к импорту в Яндекс Директ
  campaign_full.json   — полная структура для дальнейших скриптов
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))  # чтобы найти output/

from builder import build_campaign
from export import export_csv, export_json, export_markdown

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("ad_campaign")


def main() -> None:
    parser = argparse.ArgumentParser(description="Campaign Builder — Яндекс Директ")
    parser.add_argument(
        "--url",
        required=True,
        help="URL сайта терапевта, например: https://example.ru",
    )
    parser.add_argument(
        "--name",
        default="Палкина С.Ф. — психотерапевт для пар",
        # URL сайта: https://palkina-therapy.ru
        help="Название кампании в Директе",
    )
    args = parser.parse_args()

    if not args.url.startswith("http"):
        log.error("URL должен начинаться с http:// или https://")
        sys.exit(1)

    log.info("=== Сборка кампании ===")
    campaign = build_campaign(site_url=args.url, campaign_name=args.name)

    total_kw = sum(len(b.keywords) for b in campaign.groups)
    if total_kw == 0:
        log.warning(
            "Ключевых слов не найдено. Сначала запусти Semantic Scout: "
            "python main.py (из корневой папки)"
        )

    log.info("=== Экспорт ===")
    md_path = export_markdown(campaign)
    csv_path = export_csv(campaign)
    json_path = export_json(campaign)

    log.info("")
    log.info("Готово:")
    log.info("  Отчёт для согласования → %s", md_path)
    log.info("  Импорт в Директ        → %s", csv_path)
    log.info("  Полная структура JSON  → %s", json_path)
    log.info("")
    log.info("Следующий шаг: открой %s, согласуй тексты, затем загрузи CSV в Яндекс Директ:", md_path)
    log.info("  Директ → Инструменты → Импорт/Экспорт кампаний → Загрузить CSV")


if __name__ == "__main__":
    main()
