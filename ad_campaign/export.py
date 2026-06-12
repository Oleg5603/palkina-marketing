"""
Экспорт кампании в два формата:
  1. CSV — совместимый с импортом Яндекс Директ (Инструменты → Импорт/Экспорт)
  2. Markdown — читаемый отчёт для согласования с терапевтом
"""

import csv
import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from builder import Campaign, BuiltGroup

log = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "output"


# ---------------------------------------------------------------------------
# CSV — формат Яндекс Директ
# ---------------------------------------------------------------------------

# Колонки в формате Директа (упрощённый вариант для ручного импорта)
DIRECT_CSV_COLUMNS = [
    "Название кампании",
    "Название группы",
    "Заголовок 1",
    "Заголовок 2",
    "Текст",
    "Ссылка",
    "Отображаемый путь 1",
    "Ключевые фразы",
    "Минус-фразы группы",
    "Минус-фразы кампании",
    "Статус",
]


def export_csv(campaign: Campaign, path: Path | None = None) -> Path:
    if path is None:
        path = OUTPUT_DIR / "direct_campaign.csv"

    rows = []
    campaign_negatives_str = " | ".join(f"-{w}" for w in campaign.campaign_negatives)

    for built in campaign.groups:
        if not built.keywords:
            log.info("Группа '%s' — нет ключей, пропускаем", built.group.name)
            continue

        keywords_str = "\n".join(kw.keyword for kw in built.keywords)
        group_negatives_str = " | ".join(f"-{w}" for w in built.group.group_negatives)

        for ad in built.group.ads:
            _check_limits(ad, built.group.name)
            rows.append({
                "Название кампании": campaign.name,
                "Название группы": built.group.name,
                "Заголовок 1": ad.title1,
                "Заголовок 2": ad.title2,
                "Текст": ad.text,
                "Ссылка": f"{campaign.site_url.rstrip('/')}/",
                "Отображаемый путь 1": ad.display_path,
                "Ключевые фразы": keywords_str,
                "Минус-фразы группы": group_negatives_str,
                "Минус-фразы кампании": campaign_negatives_str if rows == [] else "",
                "Статус": "Активно",
            })

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:  # utf-8-sig для Excel
        writer = csv.DictWriter(f, fieldnames=DIRECT_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    log.info("CSV → %s (%d объявлений)", path, len(rows))
    return path


# ---------------------------------------------------------------------------
# JSON — полная структура кампании
# ---------------------------------------------------------------------------

def export_json(campaign: Campaign, path: Path | None = None) -> Path:
    if path is None:
        path = OUTPUT_DIR / "campaign_full.json"

    data = {
        "campaign": campaign.name,
        "site_url": campaign.site_url,
        "exported_at": datetime.now().isoformat(),
        "campaign_negatives": campaign.campaign_negatives,
        "groups": [
            {
                "name": built.group.name,
                "category": built.group.category,
                "keywords_count": len(built.keywords),
                "total_frequency": sum(k.frequency for k in built.keywords),
                "keywords": [
                    {"keyword": k.keyword, "frequency": k.frequency, "intent": k.intent}
                    for k in built.keywords
                ],
                "ads": [asdict(ad) for ad in built.group.ads],
                "quick_links": [asdict(ql) for ql in built.group.quick_links],
                "group_negatives": built.group.group_negatives,
            }
            for built in campaign.groups
        ],
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    log.info("JSON → %s", path)
    return path


# ---------------------------------------------------------------------------
# Markdown — читаемый отчёт
# ---------------------------------------------------------------------------

def export_markdown(campaign: Campaign, path: Path | None = None) -> Path:
    if path is None:
        path = OUTPUT_DIR / "campaign_report.md"

    lines = [
        f"# Рекламная кампания: {campaign.name}",
        f"*Сайт: {campaign.site_url} | Дата: {datetime.now().strftime('%d.%m.%Y')}*",
        "",
        "---",
        "",
    ]

    total_kw = sum(len(b.keywords) for b in campaign.groups)
    total_freq = sum(k.frequency for b in campaign.groups for k in b.keywords)
    lines += [
        f"**Групп объявлений:** {len(campaign.groups)}  ",
        f"**Ключевых слов:** {total_kw}  ",
        f"**Суммарная частота / мес:** {total_freq:,}",
        "",
        "---",
        "",
    ]

    for built in campaign.groups:
        if not built.keywords:
            continue

        top_kw = built.keywords[:5]
        freq_sum = sum(k.frequency for k in built.keywords)

        lines += [
            f"## {built.group.name}",
            "",
            f"Ключевых слов: **{len(built.keywords)}** | "
            f"Суммарная частота: **{freq_sum:,}** показов/мес",
            "",
            "### Объявления",
            "",
        ]

        for i, ad in enumerate(built.group.ads, 1):
            lines += [
                f"**Вариант {i}**",
                "",
                f"| | |",
                f"|---|---|",
                f"| Заголовок 1 | {ad.title1} `({len(ad.title1)}/56)` |",
                f"| Заголовок 2 | {ad.title2} `({len(ad.title2)}/30)` |",
                f"| Текст | {ad.text} `({len(ad.text)}/81)` |",
                f"| Путь | /{ad.display_path} |",
                "",
            ]

        lines += [
            "### Топ-5 ключевых слов группы",
            "",
            "| Фраза | Частота/мес | Интент |",
            "|---|---|---|",
        ]
        for kw in top_kw:
            lines.append(f"| {kw.keyword} | {kw.frequency:,} | {kw.intent} |")

        if built.group.group_negatives:
            lines += [
                "",
                f"**Минус-слова группы:** {', '.join(built.group.group_negatives)}",
            ]

        lines += ["", "---", ""]

    lines += [
        "## Минус-слова кампании",
        "",
        ", ".join(campaign.campaign_negatives),
        "",
        "---",
        "",
        "## Быстрые ссылки (одинаковые для всех групп)",
        "",
        "| Заголовок | URL | Описание |",
        "|---|---|---|",
    ]
    for ql in campaign.groups[0].group.quick_links if campaign.groups else []:
        lines.append(f"| {ql.title} | {campaign.site_url}{ql.url_suffix} | {ql.description} |")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Markdown отчёт → %s", path)
    return path


# ---------------------------------------------------------------------------
# Валидация лимитов символов
# ---------------------------------------------------------------------------

def _check_limits(ad, group_name: str) -> None:
    issues = []
    if len(ad.title1) > 56:
        issues.append(f"title1 ({len(ad.title1)} > 56 символов)")
    if len(ad.title2) > 30:
        issues.append(f"title2 ({len(ad.title2)} > 30 символов)")
    if len(ad.text) > 81:
        issues.append(f"text ({len(ad.text)} > 81 символа)")
    if len(ad.display_path) > 20:
        issues.append(f"display_path ({len(ad.display_path)} > 20 символов)")
    if issues:
        log.warning("Группа '%s', объявление '%s': %s", group_name, ad.title1, "; ".join(issues))
