# CalcFS PDF Export

**Десктопное приложение для Windows** (Python / PySide6), которое читает папку соревнования **ISUCalcFS** (таблицы **DBF**), формирует **стартовые листы** с ФИО, клубом, разрядом, датой рождения, тренером и объединяет выбранные категории в **один PDF**.

Логика отчёта согласована с идеей шаблона `StartingOrderWithClubNames.rpt` (см. документацию в `docs/`); бинарный Crystal-`.rpt` **не исполняется** — выгрузка воспроизведена в Python.

---

## Возможности

| | |
|---|---|
| **Источник данных** | Папка с `PRF.DBF`, `PAR.DBF`, `PCT.DBF`, `EVT`, `CAT`, `SCP`, при необходимости `CLB` |
| **Интерфейс** | Выбор категорий/сегментов, группы склейки, порядок строк, размер разминки, вставки текста до/после разминки |
| **PDF** | Заголовок события, место, даты, список разрядов; таблица с переносом длинных строк (ФИО, школа, тренер) |
| **Колонки** | Действующий разряд, дата рождения, тренер (`PCT_COANAM` / Coach Name) — по желанию |
| **CLI** | Пакетная выгрузка без GUI (`python -m calcfs_pdf_export.cli`) |
| **Сборка** | Один переносимый `CalcFSPdfExport.exe` (PyInstaller, см. ниже) |

---

## Требования

- **Python 3.10+**
- Установленный **ISUCalcFS**: копия папки соревнования с DBF (файлы не должны быть заблокированы другим процессом)

---

## Установка из исходников

```powershell
git clone https://github.com/AndryshaDenisov1488/calcstarting.git
cd calcstarting
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Опционально: `pip install -e .` — после этого можно вызывать консольные скрипты из `pyproject.toml` без `PYTHONPATH`.

---

## Запуск GUI

```powershell
python -m calcfs_pdf_export
```

1. **Выбрать папку соревнования** (где лежат DBF).  
2. **Обновить список** категорий × сегментов.  
3. Отметить нужные строки, при необходимости настроить **группы склейки** и порядок.  
4. **Сформировать объединённый PDF** и указать путь сохранения.

Порядок страниц в итоговом PDF совпадает с **порядком строк в списке** (сверху вниз).

---

## Запуск без GUI (CLI)

```powershell
python -m calcfs_pdf_export.cli --base "C:\ISUCalcFS\1904ch" --out merged.pdf --all
```

Несколько пар «категория : сегмент» (как в DBF):

```powershell
python -m calcfs_pdf_export.cli --base "...\соревнование" --out out.pdf --pair 1:5 --pair 1:6
```

---

## Сборка переносимого `.exe`

```powershell
.\scripts\build_exe.ps1
```

Или вручную:

```powershell
pip install pyinstaller
pyinstaller --noconfirm --clean CalcFSPdfExport.spec
```

Готовый файл: **`dist\CalcFSPdfExport.exe`** (один файл, удобно копировать на другой ПК). Первый запуск может быть чуть дольше из‑за распаковки.

---

## Документация в репозитории

| Файл | Содержание |
|------|------------|
| [docs/RPT_ANALYSIS.md](docs/RPT_ANALYSIS.md) | Анализ `.rpt`, риски, таблицы DBF |
| [docs/REPORT_MAPPING_STARTING_ORDER.md](docs/REPORT_MAPPING_STARTING_ORDER.md) | Соответствие полей отчёта и DBF |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Архитектура модуля |
| [templates/report_profiles.yaml](templates/report_profiles.yaml) | Профиль отчёта (ориентир для развития) |

---

## Тесты

```powershell
pip install pytest
pytest tests -q
```

---

## Структура репозитория

```
calcstarting/
├── calcfs_pdf_export/     # Основной пакет (GUI, CLI, DBF, PDF)
├── docs/                  # Аналитика и маппинг полей
├── scripts/               # build_exe.ps1 и вспомогательные скрипты
├── templates/             # YAML-профили отчётов
├── tests/
├── assets/                # Иконка и ресурсы для сборки
├── CalcFSPdfExport.spec   # PyInstaller (one-file)
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## Ограничения

- Не претендует на **пиксель-в-пиксель** совпадение с Crystal Reports.
- Условная логика и подотчёты из `.rpt` **не** импортируются автоматически.
- Приложение **только читает** DBF и не меняет данные CalcFS.

---

## Данные и ответственность

Приложение не изменяет файлы пользователя, только читает их. Соблюдайте требования к персональным данным спортсменов при копировании и публикации PDF.

---

## Лицензия

Укажите лицензию по желанию (например MIT) — в репозитории файл `LICENSE` пока не добавлен.
