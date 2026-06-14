"""
Собирает кампанию: берёт classified_keywords.json из Scout
и распределяет ключевые слова по группам объявлений.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from ad_texts import AdGroup, AD_GROUPS, CAMPAIGN_NEGATIVES

log = logging.getLogger(__name__)

CLASSIFIED_PATH = Path(__file__).parent.parent / "output" / "classified_keywords.json"


@dataclass
class KeywordEntry:
    keyword: str
    frequency: int
    intent: str
    categories: list[str]


@dataclass
class BuiltGroup:
    group: AdGroup
    keywords: list[KeywordEntry] = field(default_factory=list)


@dataclass
class Campaign:
    name: str
    site_url: str
    groups: list[BuiltGroup] = field(default_factory=list)
    campaign_negatives: list[str] = field(default_factory=list)


def build_campaign(site_url: str, campaign_name: str = "Психотерапевт — пары и брак") -> Campaign:
    keywords = _load_keywords()
    log.info("Загружено ключевых слов: %d", len(keywords))

    campaign = Campaign(
        name=campaign_name,
        site_url=site_url,
        campaign_negatives=CAMPAIGN_NEGATIVES,
    )

    for group_def in AD_GROUPS:
        built = BuiltGroup(group=group_def)
        for kw in keywords:
            if _matches_group(kw, group_def):
                built.keywords.append(kw)
        built.keywords.sort(key=lambda k: k.frequency, reverse=True)
        campaign.groups.append(built)
        log.info(
            "Группа '%s': %d ключевых слов",
            group_def.name, len(built.keywords),
        )

    _warn_unassigned(keywords, campaign)
    return campaign


def _load_keywords() -> list[KeywordEntry]:
    if not CLASSIFIED_PATH.exists():
        log.warning(
            "Файл %s не найден. Запусти сначала: python main.py из корня проекта.",
            CLASSIFIED_PATH,
        )
        return []
    with CLASSIFIED_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    return [
        KeywordEntry(
            keyword=d["keyword"],
            frequency=d["frequency"],
            intent=d["intent"],
            categories=d.get("categories", ["другое"]),
        )
        for d in data
    ]


def _matches_group(kw: KeywordEntry, group: AdGroup) -> bool:
    if kw.intent not in group.intent_filter:
        return False
    return group.category in kw.categories


def _warn_unassigned(keywords: list[KeywordEntry], campaign: Campaign) -> None:
    assigned = {
        kw.keyword
        for built in campaign.groups
        for kw in built.keywords
    }
    unassigned = [k for k in keywords if k.keyword not in assigned and k.intent != "low"]
    if unassigned:
        log.info(
            "Не попали ни в одну группу (high/medium): %d фраз — проверь категории в classifier.py",
            len(unassigned),
        )
        for k in unassigned[:10]:
            log.debug("  - %s (%s, %s)", k.keyword, k.intent, k.categories)
