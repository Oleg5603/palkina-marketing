# Мастер-контекст для Гаврика (@mayroden_bot)
_Обновлён: 2026-06-30 (Galactic Academy). Читать целиком при старте сессии._

---

## Кто такой пользователь

Имя: Олег. Email: palkinoleg@gmail.com.  
Работает с несколькими проектами одновременно. Пишет по-русски. Хочет чтобы ИИ-ассистент понимал контекст всех проектов без повторных объяснений.  
Claude Code (claude-sonnet-4-6) — основной ассистент, работает локально через CLI. Гаврик (@mayroden_bot) — дополнительный агент через Telegram.

---

## ПРОЕКТ 1 — Sniper EA (торговая система) ★ АКТИВНЫЙ

**Суть:** Автоматизация паттерна П4 на XAUUSD M1 в MetaTrader 4.

**Расположение:** `C:\Users\HP\Форекс\sniper_ea\`

### Паттерн П4 (определение)
M15 импульс → пробой свинга (перелой/перехай) → откат в КЗ (35% импульса) → РМ на M1 → вход.  
Фильтр: H1 цена ≥ MA_Gap$ от H1 SMA-50 (оптимум MA_Gap=5$).

**Термины:**
- КЗ = Коррекционная Зона (зона 35% от импульса)
- РМ = Разворотный Момент (импульсная свеча M1, тело ≥ 0.3$ и ≥ 1.5× среднего)
- П4 = паттерн №4 (свинг + КЗ + РМ)
- ПД = Продолженное Движение (КЗ + РМ без пробоя свинга — следующий приоритет)
- CTR = Counter-RM close (закрытие при встречном РМ с прибылью ≥ порога)

### Файлы (актуальные версии на 2026-06-30)

| Файл | Версия | Путь |
|------|--------|------|
| EA (iCustom, реал) | v2.19 | `C:\Users\HP\Форекс\sniper_ea\Sniper3_EA.mq4` |
| EA (M15 встроен, тестер) | v3.2 | `C:\Users\HP\Форекс\sniper_ea\Sniper3_EA_M15.mq4` |
| Индикатор новый | v9 | `C:\Users\HP\Форекс\sniper_ea\Sniper9_Indicator.mq4` |
| Бэктест ядро | — | `C:\Users\HP\Форекс\sniper_ea\backtest_core.py` |
| M1 данные | — | `C:\Users\HP\Форекс\sniper_ea\xauusd_m1_cache.csv` |
| Онтология | — | `C:\Users\HP\Форекс\sniper_ea\trading_system_ontology.md` |

MT4 папка: `C:\Users\HP\AppData\Roaming\MetaQuotes\Terminal\8C90EA2342AB06D2F18007B06632DE4B\MQL4\`

### Эталонные результаты Python-бэктеста 2024

| Метрика | Значение |
|---------|----------|
| Сделок | 390 |
| WR | 36.9% |
| P&L | +43,087$ |
| Начальный баланс | 10,000$ |
| Макс. просадка | 11.9% |
| Убыточных месяцев | 0 |
| RR | 2.92:1 |

Лучшее улучшение: **CTR_MinProfit=140$** → +94,000$ за 2024 / +98,000$ за 2025.

### Параметры системы

```
M15_SW=3, P4MinImp=5.0, KZPct=0.35
RM_Min=0.3, RM_Rel=1.5, RM_AvgN=20
SL_Buf=1.5, TP_Ratio=3.0, RTZ=2.0
RiskPct=1.0 (1% на сделку)
DayLossPct=2.0
T_Zone=7200, T_Test=3600
SessFrom=8, SessTo=15 (UTC)
UseTrendH1=true, TrendMA=50 (H1 SMA)
MA_Gap=5.0$
CTR_MinProfit=140$ (обновлено в EA v2.19 и v3.2)
```

### Текущий статус (2026-06-30)

- `backtest_core.py` исправлен: `trend_up=trend_dn=True` по умолчанию → совпадает с эталоном (+43,087$)
- `Sniper3_EA_M15.mq4` v3.2: обновлён CTR_MinProfit 80→140$, нужна компиляция в MetaEditor (F7)
- Strategy Tester запущен на старом `Sniper3_EA.ex4` — результат плохой (-27$). Нужно тестировать `Sniper3_EA_M15.ex4`
- Следующий приоритет: запустить тестер с M15-советником, затем реализовать паттерн ПД

### Что проверено и отклонено

- Динамический TP (ATR×mult): работает в 2024, провал OOS 2025 → ОТКЛОНИТЬ
- Трейлинг стоп (SL→BE): P&L ниже эталона в 2025 → ОТКЛОНИТЬ
- Combo Trail+CTR: BE закрывает позицию до CTR → ОТКЛОНИТЬ
- M5 ZigZag (Sniper3_EA_ZZ5): 57 сделок, +5,240$ vs 390 сделок, +43,087$ → ХУЖЕ

---

## ПРОЕКТ 2 — Palkina Marketing

**Суть:** Маркетинг для психотерапевта Светланы Палкиной.

**Расположение:** `C:\Users\HP\semantic_scout\`

### Статус (2026-06)

| Этап | Статус |
|------|--------|
| Лендинг palkina-therapy.ru | ✅ Работает, форма Formspree xpqejgvl |
| Яндекс.Метрика (ID 109801157) | ✅ Цель form_submit подключена |
| Яндекс.Директ CSV | ✅ Готов, ждёт бюджет |
| VK группа `misemia` | ✅ Создана, контент-план 12 постов |
| VK парсинг аудитории | ❌ Заблокирован (нужен личный VK_USER_TOKEN) |
| Telegram-бот для клиентов | ❌ Не создан |
| `svet_bot` (внутренний) | ⚠️ Код готов, нет токена бота (@LanaS777Bot) |

**Агенты:** `C:\Users\HP\semantic_scout\agents\`  
Lead-counter cron job: `a79fdce1`, напоминает при 3 новых VK-клиентах, лимит 7 дней.

---

## ПРОЕКТ 3 — Sibvaleo

**Суть:** Flutter Windows-приложение подбора программ Siberian Wellness для консультантов.

**Расположение:** `C:\Projects\sibvaleo` (ОБЯЗАТЕЛЬНО латинский путь — кириллица ломает MSBuild)  
Оригинал: `C:\Users\HP\Проекты\sibvaleo` (для сборки НЕ использовать!)

**GitHub:** https://github.com/Oleg5603/sibvaleo.git (ветка master)  
**Готовый exe:** `C:\Users\HP\Desktop\Sibvaleo\sibvaleo.exe`

### Сборка

```bash
cd C:\Projects\sibvaleo
C:\flutter\bin\flutter.bat build windows --release
# Результат: build\windows\x64\runner\Release\
```

### Архитектура (Dart/Flutter, без сторонних пакетов)

- `lib/main.dart` — точка входа, загрузка products.json
- `lib/data/recommendation_engine.dart` — движок подбора
- `lib/screens/product_selection_screen.dart` — главный экран (1043 стр)
- `lib/utils/trial.dart` — триал 4 дня (`%LOCALAPPDATA%\sibvaleo\trial.json`)
- `lib/utils/activation.dart` — коды `SVLnnn-mmmmm`, алгоритм: `(n×37 + slot×7919 + 54321) % 100000`
- `assets/data/products.json` + `conditions.json` — база данных

---

## ПРОЕКТ 4 — PeriphEyes (тренировка зрения)

**Суть:** Прозрачный оверлей для тренировки периферического зрения, работает поверх любого окна.

**Файл:** `C:\Users\HP\Проекты\oftalm\periph_eyes\periph_eyes.py`  
**Технологии:** Python 3 + tkinter (только stdlib)

**Паттерны анимации:** Bloom, Depth, Drift, Gabor, Mix  
**Настройки:** `~/.periph_eyes.json`

**Следующий шаг:** системный трей (pystray) и горячая клавиша.

---

## ПРОЕКТ 5 — Galactic Academy

**Суть:** customtkinter-приложение — PDF-советник со Star Wars персонажами. Анализ параграфов через AI, TTS озвучка.

**Расположение:** `C:\Users\HP\Проекты\galactic_academy\`  
**GitHub:** https://github.com/Oleg5603/galactic-academy (master)  
**EXE дистрибутив:** `C:\Users\HP\Desktop\Общая\GalacticAcademy.zip` (94.8 МБ, PyInstaller --onedir)

### Персонажи и функции

| ID | Имя | Функция |
|----|-----|---------|
| yoda | Мастер Йода | 3-5 ключевых тезиса |
| vader | Дарт Вейдер | 3 вопроса для проверки |
| r2d2 | R2-D2 | Сложное — простыми словами |
| c3po | C-3PO | Термины и определения |
| obi | Оби-Ван Кеноби | Зачем это в жизни |

### Архитектура

- `main.py` — точка входа, load_dotenv через sys._MEIPASS в EXE
- `ai_analyzer.py` — OpenRouter API (openrouter/free), spellcheck (pyspellchecker)
- `tts/voice.py` — Edge TTS DmitryNeural (онлайн) → pyttsx3 Irina SAPI (оффлайн), воспроизведение через ctypes MCI
- `ui/app.py` — главный экран: PDF загрузка, выбор параграфа, панель персонажей, кнопка ⏹ стоп

### TTS голоса (все DmitryNeural, различие pitch/rate)

| Персонаж | pitch | rate |
|----------|-------|------|
| Йода | +8Hz | -40% (очень медленно) |
| Вейдер | -30Hz | -25% (низко, угрожающе) |
| R2D2 | +25Hz | +50% (быстро, дроид) |
| C3PO | +15Hz | +8% (формальный) |
| Оби-Ван | -5Hz | -10% (спокойный) |

### API

- **AI:** OpenRouter (`openrouter/free`) — ключ только в `.env` (OPENROUTER_API_KEY)
- **TTS:** Edge TTS (Microsoft Neural, бесплатно, онлайн) / pyttsx3 (оффлайн резерв)

### Статус (2026-06-30)

✅ Работает на ПК без VPN (OpenRouter вместо Groq)  
✅ Озвучка: Edge TTS онлайн + pyttsx3 оффлайн резерв  
✅ Кнопка ⏹ остановки голоса  
✅ Подсказки функций под каждым персонажем  
✅ Орфографическая проверка ответов (pyspellchecker ru)  
✅ EXE собран PyInstaller, ZIP в Desktop\Общая\

---

## Технические справки

### Git push через proxy (если нужен)
```bash
git -c http.proxy=socks5://127.0.0.1:10808 push origin master
```

### Python конвертация pandas timestamp в Unix
```python
dti.tz_convert('UTC').tz_localize(None).astype('datetime64[s]').astype(np.int64)
```

### precompute_zones() сигнатура
```python
bt_arr, bb_arr, bT_arr, bi_arr, st_arr, sb_arr, sT_arr, si_arr = precompute_zones(
    m15ts, m15h, m15l, is_hi15, is_lo15, M15_SW=3, P4MinImp=5.0, KZPct=0.35)
```

---

_Файл поддерживается автоматически Claude Code. При вопросах по проектам — читать этот файл целиком._
