"""
Координатор — запускает агентов по порядку.

Полный цикл:
  1. audience_scout  → output/vk_audience.csv
  2. qualifier       → qualified_leads.json
  3. researcher      → enriched_leads.json
  4. commenter       → комментарии в VK (лимит 3/день)
  5. scheduler       → проверяет ответы, уведомляет Светлану

Запуск:
  python orchestrator.py              — полный цикл
  python orchestrator.py --step scout — только разведка
  python orchestrator.py --step comment --dry-run
"""

import argparse
import io
import logging
import subprocess
import sys
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("orchestrator")

_ROOT   = Path(__file__).parent
_PYTHON = sys.executable

_STEPS = {
    "scout":      _ROOT / "audience_scout.py",
    "qualify":    _ROOT / "qualifier.py",
    "research":   _ROOT / "researcher.py",
    "comment":    _ROOT / "commenter.py",
    "schedule":   _ROOT / "scheduler.py",
    "content":    _ROOT / "content_agent.py",   # ежедневный VK-пост
}


def run_step(name: str, extra_args: list[str] | None = None) -> bool:
    script = _STEPS.get(name)
    if not script or not script.exists():
        log.error("Шаг не найден: %s", name)
        return False

    cmd = [_PYTHON, str(script)] + (extra_args or [])
    log.info("▶ %s: %s", name, " ".join(cmd))

    result = subprocess.run(cmd, cwd=str(_ROOT))
    if result.returncode != 0:
        log.error("❌ Шаг завершился с ошибкой: %s (code %d)", name, result.returncode)
        return False

    log.info("✅ %s — готово", name)
    return True


def full_cycle(dry_run: bool) -> None:
    comment_args = ["--dry-run"] if dry_run else []

    steps = [
        ("scout",    []),
        ("qualify",  []),
        ("research", []),
        ("comment",  comment_args),
        ("schedule", []),
        ("content",  []),
    ]

    for name, args in steps:
        ok = run_step(name, args)
        if not ok:
            log.warning("Шаг «%s» не прошёл — продолжаю следующий", name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Координатор агентов")
    parser.add_argument("--step", choices=list(_STEPS.keys()),
                        help="Запустить только один шаг")
    parser.add_argument("--dry-run", action="store_true",
                        help="Передать --dry-run агентам, которые это поддерживают")
    args = parser.parse_args()

    if args.step:
        extra = ["--dry-run"] if args.dry_run and args.step in ("comment", "content") else []
        run_step(args.step, extra)
    else:
        full_cycle(args.dry_run)
