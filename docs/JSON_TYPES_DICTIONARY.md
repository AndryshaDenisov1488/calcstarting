# 📚 СЛОВАРЬ JSON ТИПОВ - ISUCalcFS → vMix

**Версия:** 1.0  
**Дата:** 26 января 2026  
**Источник:** Анализ `vmix_osis_bridge.py`, примеров JSON файлов и структуры DBF из `pm 2026`

---

## ⚠️ ВАЖНЫЕ ЗАМЕЧАНИЯ

### 1. Поля клуба (Club)

**КРИТИЧЕСКОЕ УТОЧНЕНИЕ:** Поля `Paper_Full_Name` и `Paper_List_Name`:

- ❌ **НЕ являются полями участника** из DBF таблицы `PCT.DBF`
- ✅ **Берутся из элемента `<Club>`** в XML OSIS (вложен в `<Person_Couple_Team>`)
- 📍 **В коде** (`vmix_osis_bridge.py`, строки 740-742):
  - `Paper_Full_Name` = `club_elem.get("PCT_CNAME", "")` (название клуба)
  - `Paper_List_Name` = `club_elem.get("PCT_PLNAME", "")` (полное название клуба для списков)
- 📋 **В DBF:** Поле `PCT_PLNAME` в таблице `PCT.DBF` - это Paper List Name **участника**, не клуба!

### 2. Пагинация (page)

**Назначение:** Разделение больших списков на страницы для отображения в vMix

- `startList.json` - **8 участников на страницу**
- `resultList.json` - **6 участников на страницу**
- `page: 0` - титульная страница (только заголовок)
- `page: 1, 2, 3...` - страницы с данными
- `lastPage: true` - флаг последней страницы

Подробнее см. раздел [Назначение пагинации](#-назначение-пагинации-page)

---

## 📋 ОГЛАВЛЕНИЕ

1. [startList.json](#startlistjson) - Стартовый лист
2. [warm-group.json](#warm-groupjson) - Разминка
3. [segment.json](#segmentjson) - Информация о сегменте
4. [judges.json](#judgesjson) - Судьи
5. [NameData.json](#namedatajson) - Данные участника
6. [2_Score.json](#2_scorejson) - Второй экран счета
7. [1s2ScoreIResult.json](#1s2scoreresultjson) - Первый экран счета с результатом
8. [3rdScoreIResult.json](#3rdscoreresultjson) - Третий экран счета
9. [ELEM.json](#elemjson) - Элементы программы
10. [ELS.json](#elsjson) - Последний элемент
11. [LTV.json](#ltvjson) - Лидер в технических элементах
12. [resultList.json](#resultlistjson) - Промежуточные результаты
13. [victory.json](#victoryjson) - Победители
14. [Time.json](#timejson) - Время выступления

---

## 1. startList.json

**Файл:** `startList.json`  
**Тип:** `"STR"` (Start List)  
**Функция генерации:** `write_start_list()` (строки 336-371)  
**Триггер:** Команда `Segment_Start` в OSIS

### Структура JSON:

```json
{
  "type": "STR",
  "data": [
    {
      "page": 0,
      "title": [
        {
          "resultName": "Стартовый лист",
          "eventName": "...",
          "categoryName": "...",
          "fullCategoryName": "...",
          "segmentName": "..."
        }
      ]
    },
    {
      "participants": [
        {
          "tRank": "1",
          "nation": "RUS",
          "tPoints": "59.43",
          "sNumber": "54",
          "name": "Софья ВАГИНА"
        }
      ],
      "title": [...],
      "page": 1
    },
    {
      "page": 2,
      "lastPage": true
    }
  ]
}
```

### Описание полей:

#### Корневой уровень:
| Поле | Тип | Описание |
|------|-----|----------|
| `type` | `string` | Всегда `"STR"` |
| `data` | `array` | Массив страниц стартового листа |

#### Элемент `data[0]` (титульная страница):
| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `page` | `number` | Константа `0` | Номер страницы (0 = титульная) |
| `title` | `array` | `build_title()` | Массив с заголовком (обычно 1 элемент) |

#### Элемент `title[0]`:
| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `resultName` | `string` | Константа `"Стартовый лист"` | Название результата |
| `eventName` | `string` | `state.event_name` → `Event.Name` | Название соревнования |
| `categoryName` | `string` | `state.category_name` → `Category.Name` | Название категории |
| `fullCategoryName` | `string` | `categoryName + " " + segmentName` | Полное название |
| `segmentName` | `string` | `state.segment_name` → `Segment.Name` | Название сегмента |

#### Элемент `data[N]` (страницы с участниками):
| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `participants` | `array` | `state.start_list` | Массив участников (до 8 на страницу) |
| `title` | `array` | `build_title()` | Заголовок страницы |
| `page` | `number` | Индекс страницы | Номер страницы (начиная с 1) |
| `lastPage` | `boolean` | `page_index == len(pages)` | Флаг последней страницы |

#### Элемент `participants[]`:
| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `tRank` | `string` | `category_results_by_participant_id[participant_id].TRank` | Место в категории |
| `nation` | `string` | `participants_by_id[participant_id].Nation` | Страна участника |
| `tPoints` | `string` | `category_results_by_participant_id[participant_id].TPoint` | Общие баллы |
| `sNumber` | `string` | `start_list_entry.Start_Number` | Стартовый номер |
| `name` | `string` | `participant_display_name(participant)` | Имя участника |

### Источники данных в OSIS/XML:

1. **`state.start_list`** - заполняется из `Segment_Start_List/Performance`:
   - `Start_Number` - стартовый номер
   - `ID` - ID участника
   - `Start_Group_Number` - номер группы разминки

2. **`state.participants_by_id`** - заполняется из `Participant_List/Participant`:
   - `Nation` - страна
   - `TV_Long_Name`, `Full_Name`, `Short_Name` - варианты имени

3. **`state.category_results_by_participant_id`** - заполняется из `Category_Result_List/Participant`:
   - `TRank` - место в категории
   - `TPoint` - общие баллы

---

## 2. warm-group.json

**Файл:** `warm-group.json`  
**Тип:** `"WUP"` (Warm-up)  
**Функция генерации:** `write_warmup()` (строки 374-409)  
**Триггер:** Команда `NAM` или обновление разминки

### Структура JSON:

```json
{
  "type": "WUP",
  "data": [
    {
      "participants": [
        {
          "nation": "RUS",
          "tRank": "1",
          "club": "ООО Академия...",
          "tPoints": "59.43",
          "tIndex": "1",
          "name": "Софья ВАГИНА"
        }
      ],
      "title": [
        {
          "resultName": "Разминка №9",
          "eventName": "...",
          "categoryName": "...",
          "segmentName": "...",
          "startGroup": "9",
          "fullCategoryName": "... - Разминка №9"
        }
      ]
    }
  ]
}
```

### Описание полей:

#### Корневой уровень:
| Поле | Тип | Описание |
|------|-----|----------|
| `type` | `string` | Всегда `"WUP"` |
| `data` | `array` | Массив с данными разминки (обычно 1 элемент) |

#### Элемент `data[0]`:
| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `participants` | `array` | Фильтрация `state.start_list` по группе | Участники текущей группы разминки |
| `title` | `array` | `build_title()` + модификация | Заголовок с номером группы |

#### Элемент `participants[]`:
| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `nation` | `string` | `participants_by_id[participant_id].Nation` | Страна |
| `tRank` | `string` | `category_results_by_participant_id[participant_id].TRank` | Место |
| `club` | `string` | `get_club_name(participant, state.club_field)` | Клуб/школа |
| `tPoints` | `string` | `category_results_by_participant_id[participant_id].TPoint` | Баллы |
| `tIndex` | `string` | `category_results_by_participant_id[participant_id].TIndex` | Индекс |
| `name` | `string` | `participant_display_name(participant)` | Имя |

#### Элемент `title[0]`:
| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `resultName` | `string` | `f"Разминка №{group_number}"` | Название с номером группы |
| `startGroup` | `string` | `entry.Start_Group_Number` | Номер группы разминки |
| `fullCategoryName` | `string` | `categoryName + " " + segmentName + " - " + resultName` | Полное название |

### Источники данных:

1. **Группа разминки** определяется из:
   - `state.current_participant_id` → `start_list_entry.Start_Group_Number`
   - Или из `state.warmup_groups` (список групп)

2. **Клуб** берется через `get_club_name()`:
   - **ВАЖНО:** Поля `Paper_Full_Name` и `Paper_List_Name` НЕ являются полями участника в DBF!
   - Эти поля извлекаются из элемента `<Club>` в XML (не из таблицы участников)
   - Если `club_field == "Paper Full Name"`: `club_elem.PCT_CNAME` (название клуба) или `participant.Club`
   - Если `club_field == "Paper List Name"`: `club_elem.PCT_PLNAME` (Paper List Name клуба) или `participant.Club`
   - Иначе: `participant.Club` → `club_elem.PCT_CNAME`
   
   **Источник в XML:** `<Participant>/<Person_Couple_Team>/<Club>`:
   - `PCT_CNAME` - название клуба (используется как "Name" и "Paper Full Name")
   - `PCT_PLNAME` - полное название клуба для списков (используется как "Paper List Name")
   
   **В DBF:** Клубы хранятся отдельно (таблица CLB), но в OSIS/XML передаются вложенными элементами

---

## 3. segment.json

**Файл:** `segment.json`  
**Тип:** `"SEG"` (Segment)  
**Функция генерации:** `write_segment_title()` (строки 412-423)  
**Триггер:** `Segment_Start` или `Event_Overview`

### Структура JSON:

```json
{
  "type": "SEG",
  "data": [
    {
      "eventname": "Первенство Москвы",
      "categoryname": "Дeвoчки, младшая группa",
      "segmentname": "Короткая программа"
    }
  ]
}
```

### Описание полей:

| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `type` | `string` | Константа `"SEG"` | Тип JSON |
| `data` | `array` | Массив с одним элементом | Данные сегмента |
| `data[0].eventname` | `string` | `state.event_name` → `Event.Name` | Название соревнования |
| `data[0].categoryname` | `string` | `state.category_name` → `Category.Name` | Название категории |
| `data[0].segmentname` | `string` | `state.segment_name` → `Segment.Name` | Название сегмента |

### Источники данных:

- `state.event_name` - из `Event.Name` в XML
- `state.category_name` - из `Category.Name` (по `Category_ID`)
- `state.segment_name` - из `Segment.Name` (по `Segment_ID`)

---

## 4. judges.json

**Файл:** `judges.json`  
**Тип:** `"JDG"` (Judges)  
**Функция генерации:** `write_judges()` (строки 426-437)  
**Триггер:** `Segment_Start` (когда есть `Event_Officials_List`)

### Структура JSON:

```json
{
  "type": "JDG",
  "data": [
    {
      "judges": [
        {
          "func": "JDG",
          "nation": "RUS",
          "name": "Татьяна ФЕДОРОВА"
        }
      ]
    }
  ]
}
```

### Описание полей:

| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `type` | `string` | Константа `"JDG"` | Тип JSON |
| `data` | `array` | Массив с одним элементом | Данные судей |
| `data[0].judges` | `array` | `state.officials` | Список судей |
| `judges[].func` | `string` | `official.Function` | Функция (JDG, ERF, TCO, TSP, STS, DOP) |
| `judges[].nation` | `string` | `official.Nation` | Страна судьи |
| `judges[].name` | `string` | `official.Full_Name` | Полное имя судьи |

### Источники данных:

- `state.officials` - заполняется из `Event_Officials_List/Official`:
  - `Function` - функция судьи
  - `Nation` - страна
  - `Full_Name` - полное имя

---

## 5. NameData.json

**Файл:** `NameData.json`  
**Тип:** `"NAM"` (Name)  
**Функция генерации:** `update_name_data()` (строки 764-794)  
**Триггер:** Команда `NAM` в OSIS

### Структура JSON:

```json
{
  "data": [
    {
      "currentSegmentRank": "1",
      "familiName": "ВАГИНА",
      "nation": "RUS",
      "givenName": "Софья",
      "club": "ООО Академия...",
      "num": "54",
      "pointsNided": "",
      "name": "Софья ВАГИНА",
      "coach": "Евгений Плющенко",
      "eventname": "Первенство Москвы",
      "categoryname": "Дeвoчки, младшая группa",
      "music": "Милана Пономаренко Прекрасное далёко",
      "segmentname": "Короткая программа",
      "type": "NAM"
    }
  ]
}
```

### Описание полей:

| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `data` | `array` | Массив с одним элементом | Данные участника |
| `data[0].type` | `string` | Константа `"NAM"` | Тип данных |
| `data[0].currentSegmentRank` | `string` | `segment_results_by_participant_id[participant_id].Rank` | Место в сегменте |
| `data[0].familiName` | `string` | `split_name(participant)[0]` → `Family_Name` | Фамилия |
| `data[0].givenName` | `string` | `split_name(participant)[1]` → `Given_Name` | Имя |
| `data[0].name` | `string` | `split_name(participant)[2]` или `participant_display_name()` | Полное имя |
| `data[0].nation` | `string` | `participant.Nation` | Страна |
| `data[0].club` | `string` | `get_club_name(participant, state.club_field)` | Клуб/школа |
| `data[0].num` | `string` | `action.Current_Start_Number` | Стартовый номер |
| `data[0].pointsNided` | `string` | `start_entry.Points_Needed1` | Нужные баллы |
| `data[0].coach` | `string` | `participant.Coach` | Тренер |
| `data[0].eventname` | `string` | `state.event_name` | Название соревнования |
| `data[0].categoryname` | `string` | `state.category_name` | Название категории |
| `data[0].segmentname` | `string` | `state.segment_name` | Название сегмента |
| `data[0].music` | `string` | `participant.Music` | Музыка |

### Источники данных:

1. **Имя участника** (`split_name()`):
   - `Family_Name` - фамилия
   - `Given_Name` - имя
   - Если нет, парсится из `TV_Long_Name`, `Full_Name`, `Short_Name`

2. **Место в сегменте**:
   - `state.segment_results_by_participant_id[participant_id].Rank`

3. **Стартовый номер**:
   - `action.Current_Start_Number` из OSIS команды `NAM`

4. **Нужные баллы**:
   - `start_entry.Points_Needed1` из стартового списка

---

## 6. 2_Score.json

**Файл:** `2_Score.json`  
**Тип:** `"2SC"` (2nd Score)  
**Функция генерации:** `update_1s1()` (строки 832-860)  
**Триггер:** Команда `1S1` в OSIS

### Структура JSON:

```json
{
  "data": [
    {
      "place": "1",
      "tes": "32.72",
      "points": "59.43",
      "criteria": [
        {"point": "6.75", "index": "1"},
        {"point": "6.83", "index": "3"},
        {"point": "6.50", "index": "5"}
      ],
      "type": "2SC",
      "club": "ООО Академия...",
      "currentStartNumber": "54",
      "bonus": "0.00",
      "deduction": "-",
      "tcs": "26.71",
      "name": "Софья ВАГИНА"
    }
  ]
}
```

### Описание полей:

| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `data[0].type` | `string` | Константа `"2SC"` | Тип данных |
| `data[0].place` | `string` | `segment_results_by_participant_id[participant_id].Rank` | Место в сегменте |
| `data[0].tes` | `string` | `prf_details.attrs.TES` | Технические элементы (Technical Element Score) |
| `data[0].points` | `string` | `prf_details.attrs.Points` | Общие баллы |
| `data[0].tcs` | `string` | `prf_details.attrs.TCS` | Компоненты программы (Total Component Score) |
| `data[0].bonus` | `string` | `prf_details.attrs.Bonus` | Бонус |
| `data[0].deduction` | `string` | `format_deduction(prf_details.attrs.Ded_Sum)` | Штрафы (форматируется) |
| `data[0].criteria` | `array` | `prf_details.criteria` | Компоненты программы |
| `data[0].criteria[].point` | `string` | `criteria.Points` | Балл компонента |
| `data[0].criteria[].index` | `string` | `criteria.Index` | Индекс компонента |
| `data[0].club` | `string` | `get_club_name(participant, state.club_field)` | Клуб |
| `data[0].currentStartNumber` | `string` | `action.Current_Start_Number` | Стартовый номер |
| `data[0].name` | `string` | `participant_display_name(participant)` | Имя |

### Источники данных:

1. **`prf_details`** - парсится из `Prf_Details` в XML:
   - `TES` - технические элементы
   - `Points` - общие баллы
   - `TCS` - компоненты программы
   - `Bonus` - бонус
   - `Ded_Sum` - сумма штрафов

2. **`criteria`** - из `Criteria_List/Criteria`:
   - `Points` - балл компонента
   - `Index` - индекс компонента (1, 3, 5 и т.д.)

3. **Форматирование штрафов** (`format_deduction()`):
   - Если `"0.00"` или `"0"` → `"-"`
   - Иначе возвращает значение

---

## 7. 1s2ScoreIResult.json

**Файл:** `1s2ScoreIResult.json`  
**Тип:** `"1SC"` (1st Score)  
**Функция генерации:** `update_1s2()` (строки 863-900)  
**Триггер:** Команда `1S2` в OSIS

### Структура JSON:

```json
{
  "data": [
    {
      "place": "1",
      "bonus": "0.00",
      "id": "6",
      "nation": "RUS",
      "tes": "32.72",
      "club": "ООО Академия...",
      "tPoints": "59.43",
      "deduction": "-",
      "points": "59.43",
      "name": "Софья ВАГИНА",
      "tRank": "1",
      "categoryName": "Дeвoчки, младшая группa",
      "tcs": "26.71",
      "criteria": [...],
      "type": "1SC",
      "eventName": "Первенство Москвы",
      "segmentName": "Короткая программа"
    }
  ]
}
```

### Описание полей:

| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `data[0].type` | `string` | Константа `"1SC"` | Тип данных |
| `data[0].place` | `string` | `result.Rank` или `prf_details.attrs` | Место в сегменте |
| `data[0].tRank` | `string` | `result.Rank` | Место в сегменте (дубликат) |
| `data[0].tes` | `string` | `result.TES` или `prf_details.attrs.TES` | Технические элементы |
| `data[0].points` | `string` | `result.Points` или `prf_details.attrs.Points` | Баллы сегмента |
| `data[0].tPoints` | `string` | `result.Points` или `prf_details.attrs.Points` | Баллы сегмента (дубликат) |
| `data[0].tcs` | `string` | `result.TCS` или `prf_details.attrs.TCS` | Компоненты |
| `data[0].bonus` | `string` | `result.Bonus` или `prf_details.attrs.Bonus` | Бонус |
| `data[0].deduction` | `string` | `format_deduction(result.Ded_Sum)` | Штрафы |
| `data[0].criteria` | `array` | `prf_details.criteria` | Компоненты программы |
| `data[0].id` | `string` | `participant_id` | ID участника |
| `data[0].name` | `string` | `participant_display_name(participant)` | Имя |
| `data[0].nation` | `string` | `participant.Nation` | Страна |
| `data[0].club` | `string` | `get_club_name(participant, state.club_field)` | Клуб |
| `data[0].categoryName` | `string` | `state.category_name` | Категория |
| `data[0].eventName` | `string` | `state.event_name` | Соревнование |
| `data[0].segmentName` | `string` | `state.segment_name` | Сегмент |

### Источники данных:

1. **`result`** - из `Segment_Result_List/Performance`:
   - `Rank` - место
   - `TES`, `TCS`, `Points`, `Bonus`, `Ded_Sum` - баллы

2. **`prf_details`** - из последнего `Prf_Details` (кэшируется в `state.last_prf_details`)

3. **Приоритет данных:**
   - Сначала берется из `result`
   - Если нет, используется `prf_details.attrs`

---

## 8. 3rdScoreIResult.json

**Файл:** `3rdScoreIResult.json`  
**Тип:** `"3SC"` (3rd Score)  
**Функция генерации:** `write_third_score()` (строки 552-600)  
**Триггер:** Команда `1S3` в OSIS

### Структура JSON:

```json
{
  "data": [
    {
      "type": "3SC",
      "data": [
        {
          "color": "ORA",
          "current": true,
          "tRank": "1",
          "tPoints": "59.43",
          "nation": "RUS",
          "name": "Софья ВАГИНА"
        },
        {
          "color": "BL2",
          "current": false,
          "tRank": "2",
          "tPoints": "56.76",
          "nation": "RUS",
          "name": "Ангелина ПЕНЬКОВАЯ"
        }
      ],
      "eventName": "Первенство Москвы",
      "categoryName": "Дeвoчки, младшая группa",
      "segmentName": "Короткая программа"
    }
  ]
}
```

### Описание полей:

| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `data[0].type` | `string` | Константа `"3SC"` | Тип данных |
| `data[0].data` | `array` | Топ-4 из `category_results_by_participant_id` | Список лидеров (до 4) |
| `data[0].data[].color` | `string` | `"ORA"` если текущий, иначе `["BL2", "BL3", "BL4"][idx]` | Цвет для отображения |
| `data[0].data[].current` | `boolean` | `participant_id == current_id` | Флаг текущего участника |
| `data[0].data[].tRank` | `string` | `entry.TRank` | Место в категории |
| `data[0].data[].tPoints` | `string` | `entry.TPoint` | Общие баллы |
| `data[0].data[].nation` | `string` | `participant.Nation` | Страна |
| `data[0].data[].name` | `string` | `participant_display_name(participant)` | Имя |
| `data[0].eventName` | `string` | `state.event_name` | Соревнование |
| `data[0].categoryName` | `string` | `state.category_name` | Категория |
| `data[0].segmentName` | `string` | `state.segment_name` | Сегмент |

### Источники данных:

1. **Топ-4 участника**:
   - Берется из `category_results_by_participant_id`
   - Сортируется по `TRank`
   - Берется первые 4
   - Если текущий участник не в топ-4, заменяется последний

2. **Исключение снятых**:
   - Участники с `TRank == "0"` исключаются

3. **Цвета**:
   - `"ORA"` (оранжевый) - для текущего участника
   - `"BL2"`, `"BL3"`, `"BL4"` (синие) - для остальных

---

## 9. ELEM.json

**Файл:** `ELEM.json`  
**Тип:** Нет типа (только данные)  
**Функция генерации:** `write_elem()` (строки 470-477)  
**Триггер:** Команда `ELS` в OSIS

### Структура JSON:

```json
{
  "data": [
    {
      "XGOE": "1.59",
      "element": 0,
      "XBV": "5.30",
      "BG": "GRE",
      "longName": "Triple Flip",
      "points": "6.89",
      "name": "3F"
    },
    {
      "XGOE": 0,
      "element": 1,
      "XBV": 0,
      "BG": "null",
      "longName": "",
      "points": 0,
      "name": ""
    }
  ]
}
```

### Описание полей:

| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `data` | `array` | Массив из 12 элементов | Все элементы программы |
| `data[].element` | `number` | Индекс (0-11) | Номер элемента (0-based) |
| `data[].name` | `string` | `element.Elm_Name` | Короткое название элемента |
| `data[].longName` | `string` | `element.Elm_Name_Long` | Полное название элемента |
| `data[].XBV` | `string` | `element.Elm_XBV` | Базовая стоимость (Base Value) |
| `data[].XGOE` | `string` | `element.Elm_XGOE` | GOE (Grade of Execution) |
| `data[].points` | `string` | `element.Points` | Итоговые баллы элемента |
| `data[].BG` | `string` | `"GRE"` если `points > 0`, иначе `"null"` | Флаг успешного элемента |

### Источники данных:

1. **Элементы** - из `Prf_Details/Element_List/Element`:
   - `Index` - индекс элемента (1-based, конвертируется в 0-based)
   - `Elm_Name` - короткое название
   - `Elm_Name_Long` - полное название
   - `Elm_XBV` - базовая стоимость
   - `Elm_XGOE` - GOE
   - `Points` - итоговые баллы

2. **Заполнение**:
   - Создается массив из 12 элементов (все пустые)
   - Заполняются только те, для которых есть данные в XML
   - Индекс элемента: `Index - 1` (конвертация из 1-based в 0-based)

---

## 10. ELS.json

**Файл:** `ELS.json`  
**Тип:** `"ELS"` (Last Element)  
**Функция генерации:** `write_els()` (строки 480-508)  
**Триггер:** Команда `ELS` в OSIS

### Структура JSON:

```json
{
  "data": [
    {
      "type": "ELS",
      "data": [
        {
          "XGOE": "0.88",
          "XBV": "3.30",
          "BG": "GRE",
          "longName": "Step Sequence 3",
          "points": "4.18",
          "name": "StSq3"
        }
      ]
    }
  ]
}
```

### Описание полей:

| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `data` | `array` | Массив с одним элементом | Обертка |
| `data[0].type` | `string` | Константа `"ELS"` | Тип данных |
| `data[0].data` | `array` | Последний элемент из списка | Данные последнего элемента |
| `data[0].data[0].name` | `string` | `last_element.Elm_Name` | Короткое название |
| `data[0].data[0].longName` | `string` | `last_element.Elm_Name_Long` | Полное название |
| `data[0].data[0].XBV` | `string` | `last_element.Elm_XBV` | Базовая стоимость |
| `data[0].data[0].XGOE` | `string` | `last_element.Elm_XGOE` | GOE |
| `data[0].data[0].points` | `string` | `last_element.Points` | Итоговые баллы |
| `data[0].data[0].BG` | `string` | `"GRE"` если `points > 0`, иначе `"null"` | Флаг успешного элемента |

### Источники данных:

1. **Последний элемент**:
   - Берется элемент с максимальным `Index` из `prf_details.elements`
   - Если элементов нет, возвращается пустой массив

2. **Структура полей** - аналогична `ELEM.json`

### ⚠️ ВАЖНО: Поля клуба (Club)

**КРИТИЧЕСКОЕ УТОЧНЕНИЕ:** Поля `Paper_Full_Name` и `Paper_List_Name` в коде `vmix_osis_bridge.py`:

1. **НЕ являются полями участника из DBF таблицы PCT.DBF**
2. **Берутся из элемента `<Club>` в XML OSIS**, который вложен в `<Person_Couple_Team>`
3. **В коде (строки 740-742):**
   ```python
   participant_data["Club"] = club_elem.get("PCT_CNAME", "")  # Name
   participant_data["Paper_Full_Name"] = club_elem.get("PCT_CNAME", "")  # Paper Full Name
   participant_data["Paper_List_Name"] = club_elem.get("PCT_PLNAME", "")  # Paper List Name
   ```

4. **Источник в XML:**
   ```xml
   <Participant>
     <Person_Couple_Team>
       <Club>
         <PCT_CNAME>Название клуба</PCT_CNAME>      <!-- Используется как "Name" и "Paper Full Name" -->
         <PCT_PLNAME>Полное название для списков</PCT_PLNAME>  <!-- Используется как "Paper List Name" -->
       </Club>
     </Person_Couple_Team>
   </Participant>
   ```

5. **В DBF:**
   - Клубы могут храниться в отдельной таблице (если есть CLB.DBF)
   - Но в OSIS/XML они передаются как вложенные элементы
   - Поле `PCT_PLNAME` в таблице PCT.DBF - это Paper List Name **участника**, не клуба!

---

## 11. LTV.json

**Файл:** `LTV.json`  
**Тип:** `"LTV"` (Leader Technical Value)  
**Функция генерации:** `update_ltv()` (строки 797-820)  
**Триггер:** Команда `LTV` в OSIS

### Структура JSON:

```json
{
  "data": [
    {
      "type": "LTV",
      "data": [
        {
          "lider": "32.72",
          "LName": "Софья ВАГИНА",
          "TES": "32.72",
          "Cname": "Софья ВАГИНА",
          "TotalLider": "32.72"
        }
      ]
    }
  ]
}
```

### Описание полей:

| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `data[0].type` | `string` | Константа `"LTV"` | Тип данных |
| `data[0].data` | `array` | Массив с одним элементом | Данные лидера |
| `data[0].data[0].TES` | `string` | `prf_details.attrs.TES` | Технические элементы |
| `data[0].data[0].lider` | `string` | `prf_details.attrs.TES` | Лидер (дубликат TES) |
| `data[0].data[0].TotalLider` | `string` | `prf_details.attrs.TES` | Общий лидер (дубликат TES) |
| `data[0].data[0].LName` | `string` | `participant_display_name(participant)` | Имя лидера |
| `data[0].data[0].Cname` | `string` | `participant_display_name(participant)` | Имя (дубликат) |

### Источники данных:

1. **TES** - из `Prf_Details.TES`
2. **Имя** - из `participant_display_name(participant)`

**Примечание:** Все поля `lider`, `TotalLider` дублируют `TES` - возможно, для совместимости с разными версиями vMix.

---

## 12. resultList.json

**Файл:** `resultList.json`  
**Тип:** `"RES"` (Results)  
**Функция генерации:** `write_result_list()` (строки 511-549)  
**Триггер:** Команда `1S3` в OSIS

### Структура JSON:

```json
{
  "type": "RES",
  "data": [
    {
      "page": 0,
      "title": [...]
    },
    {
      "participants": [
        {
          "tRank": "1",
          "club": "ООО Академия...",
          "tPoints": "59.43",
          "nation": "RUS",
          "name": "Софья ВАГИНА"
        }
      ],
      "title": [...],
      "page": 1
    }
  ]
}
```

### Описание полей:

| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `type` | `string` | Константа `"RES"` | Тип JSON |
| `data` | `array` | Массив страниц | Страницы результатов |
| `data[0]` | `object` | Титульная страница | Заголовок (page=0) |
| `data[N].participants` | `array` | `category_results_by_participant_id` | Участники (до 6 на страницу) |
| `data[N].participants[].tRank` | `string` | `entry.TRank` | Место в категории |
| `data[N].participants[].club` | `string` | `get_club_name(participant, state.club_field)` | Клуб |
| `data[N].participants[].tPoints` | `string` | `entry.TPoint` | Общие баллы |
| `data[N].participants[].nation` | `string` | `participant.Nation` | Страна |
| `data[N].participants[].name` | `string` | `participant_display_name(participant)` | Имя |
| `data[N].page` | `number` | Индекс страницы | Номер страницы |
| `data[N].lastPage` | `boolean` | `page_index == len(pages)` | Флаг последней страницы |

### Источники данных:

1. **Участники** - из `category_results_by_participant_id`:
   - Сортировка по `TRank`
   - Исключение участников с `TRank == "0"` (снятые)

2. **Пагинация**:
   - 6 участников на страницу
   - Первая страница (page=0) - только заголовок

---

## 13. victory.json

**Файл:** `victory.json`  
**Тип:** `"VIC"` (Victory)  
**Функция генерации:** `write_victory()` (строки 603-624)  
**Триггер:** Команда `1S3` в OSIS

### Структура JSON:

```json
{
  "type": "VIC",
  "data": [
    {
      "place": 1,
      "category": "Дeвoчки, младшая группa",
      "club": "ООО Академия...",
      "nation": "RUS",
      "name": "Софья ВАГИНА"
    },
    {
      "place": 2,
      "category": "Дeвoчки, младшая группa",
      "club": "ООО СетПоинт",
      "nation": "RUS",
      "name": "Ангелина ПЕНЬКОВАЯ"
    },
    {
      "place": 3,
      "category": "Дeвoчки, младшая группa",
      "club": "АНО ДО ШФК СТАРТ",
      "nation": "RUS",
      "name": "Ульяна ВОЛК"
    }
  ]
}
```

### Описание полей:

| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `type` | `string` | Константа `"VIC"` | Тип JSON |
| `data` | `array` | Топ-3 из `category_results_by_participant_id` | Победители (первые 3 места) |
| `data[].place` | `number` | `safe_int(entry.TRank)` | Место (1, 2, 3) |
| `data[].name` | `string` | `participant_display_name(participant)` | Имя |
| `data[].club` | `string` | `get_club_name(participant, state.club_field)` | Клуб |
| `data[].nation` | `string` | `participant.Nation` | Страна |
| `data[].category` | `string` | `state.category_name` | Категория |

### Источники данных:

1. **Топ-3**:
   - Берется из `category_results_by_participant_id`
   - Сортировка по `TRank`
   - Исключение участников с `TRank == "0"`
   - Берется первые 3

---

## 14. Time.json

**Файл:** `Time.json`  
**Тип:** `"time"`  
**Функция генерации:** `update_time()` (строки 647-650)  
**Триггер:** Команды `TIM`, `TFW`, `TCL` в OSIS

### Структура JSON:

```json
{
  "data": [
    {
      "time": "0:18",
      "type": "time"
    }
  ]
}
```

### Описание полей:

| Поле | Тип | Источник | Описание |
|------|-----|----------|----------|
| `data` | `array` | Массив с одним элементом | Данные времени |
| `data[0].type` | `string` | Константа `"time"` | Тип данных |
| `data[0].time` | `string` | `format_running_time(action.Running_Time)` | Отформатированное время |

### Источники данных:

1. **Время** - из `action.Running_Time`:
   - Форматируется через `format_running_time()`

2. **Форматирование времени** (`format_running_time()`):
   - Если уже в формате `"MM:SS"` → возвращается как есть
   - Если в формате `"MM.SS"` → конвертируется в `"MM:SS"`
   - Если число (секунды) → конвертируется в `"MM:SS"`
   - Примеры:
     - `"18"` → `"0:18"`
     - `"1.30"` → `"1:30"`
     - `"2:15"` → `"2:15"`

---

## 📊 СВОДНАЯ ТАБЛИЦА JSON ФАЙЛОВ

| Файл | Тип | Триггер | Страниц | Участников на страницу |
|------|-----|---------|---------|------------------------|
| `startList.json` | `STR` | `Segment_Start` | Много | 8 |
| `warm-group.json` | `WUP` | `NAM` | 1 | Все в группе |
| `segment.json` | `SEG` | `Segment_Start` | 1 | - |
| `judges.json` | `JDG` | `Segment_Start` | 1 | - |
| `NameData.json` | `NAM` | `NAM` | 1 | 1 |
| `2_Score.json` | `2SC` | `1S1` | 1 | 1 |
| `1s2ScoreIResult.json` | `1SC` | `1S2` | 1 | 1 |
| `3rdScoreIResult.json` | `3SC` | `1S3` | 1 | До 4 |
| `ELEM.json` | - | `ELS` | 1 | 12 элементов |
| `ELS.json` | `ELS` | `ELS` | 1 | 1 элемент |
| `LTV.json` | `LTV` | `LTV` | 1 | 1 |
| `resultList.json` | `RES` | `1S3` | Много | 6 |
| `victory.json` | `VIC` | `1S3` | 1 | 3 |
| `Time.json` | `time` | `TIM/TFW/TCL` | 1 | - |

---

## 🔍 КЛЮЧЕВЫЕ ФУНКЦИИ И ИХ НАЗНАЧЕНИЕ

### Функции форматирования:

1. **`build_title(state, result_name)`** - создает заголовок:
   - `resultName` - название результата
   - `eventName` - соревнование
   - `categoryName` - категория
   - `segmentName` - сегмент
   - `fullCategoryName` - полное название

2. **`split_name(participant)`** - разбивает имя:
   - Возвращает: `(family, given, display)`
   - Источники: `Family_Name`, `Given_Name`, или парсинг из `TV_Long_Name`

3. **`participant_display_name(participant)`** - получает отображаемое имя:
   - Приоритет: `TV_Long_Name` → `Full_Name` → `Short_Name` → `""`

4. **`get_club_name(participant, club_field)`** - получает название клуба:
   - `"Name"` → `participant.Club`
   - `"Paper Full Name"` → `participant.Paper_Full_Name` или `participant.Club`
   - `"Paper List Name"` → `participant.Paper_List_Name` или `participant.Club`

5. **`format_deduction(value)`** - форматирует штрафы:
   - `"0.00"` или `"0"` → `"-"`
   - Иначе → значение как есть

6. **`format_running_time(raw)`** - форматирует время:
   - Конвертирует различные форматы в `"MM:SS"`

7. **`safe_int(value)`** - безопасное преобразование в int:
   - Возвращает `0` при ошибке

---

## 📝 ПРИМЕЧАНИЯ

1. **Исключение снятых участников:**
   - Участники с `TRank == "0"` исключаются из:
     - `resultList.json`
     - `3rdScoreIResult.json`
     - `victory.json`

2. **Приоритет данных:**
   - В `1s2ScoreIResult.json` сначала используется `result`, затем `prf_details.attrs`

3. **Кэширование:**
   - `state.last_prf_details` - кэширует последние `Prf_Details`
   - Используется в `update_1s2()` если нет данных в `result`

4. **Пагинация (page):**
   - **Назначение:** Разделение больших списков на страницы для отображения в vMix
   - **Причина:** vMix имеет ограничения на количество элементов, которые можно отобразить одновременно
   - **Реализация:**
     - `startList.json` - **8 участников на страницу** (page_size = 8)
     - `resultList.json` - **6 участников на страницу** (page_size = 6)
   - **Структура страниц:**
     - `page: 0` - титульная страница (только заголовок)
     - `page: 1, 2, 3...` - страницы с данными
     - `lastPage: true` - флаг последней страницы (на последней странице)
   - **Использование в vMix:**
     - vMix читает JSON и отображает страницы последовательно
     - Можно переключать страницы вручную или автоматически
     - Каждая страница содержит заголовок (`title`) и данные (`participants`)

5. **Индексация элементов:**
   - В XML элементы имеют `Index` (1-based)
   - В JSON конвертируется в 0-based (`Index - 1`)

6. **Поля клуба (Club):**
   - **ВАЖНО:** `Paper_Full_Name` и `Paper_List_Name` - это НЕ поля участника в DBF!
   - Эти поля извлекаются из элемента `<Club>` в XML OSIS
   - В DBF таблице `PCT.DBF` есть поле `PCT_PLNAME` (Paper List Name), но это для участника, не клуба
   - Клубы в XML передаются как вложенные элементы с полями:
     - `PCT_CNAME` - название клуба (используется как "Name" и "Paper Full Name")
     - `PCT_PLNAME` - полное название для списков (используется как "Paper List Name")

---

## 🔍 СООТВЕТСТВИЕ ПОЛЕЙ DBF ↔ JSON

### Таблица участников (PCT.DBF) → JSON поля

| Поле DBF | Тип | Длина | JSON поле | Где используется |
|----------|-----|-------|-----------|------------------|
| `PCT_ID` | N | 8 | `id`, `participant_id` | Везде (ключ) |
| `PCT_CNAME` | C | 60 | `name`, `full_name` | NameData, все списки |
| `PCT_PLNAME` | C | 73 | `official_name` | Для участника (НЕ для клуба!) |
| `PCT_SNAME` | C | 8 | `short_name` | - |
| `PCT_GNAME` | C | 30 | `givenName` | NameData |
| `PCT_FNAME` | C | 30 | `familiName` | NameData |
| `PCT_FNAMEC` | C | 30 | - | Фамилия заглавными |
| `PCT_BDAY` | D | 8 | `birth_date` | - |
| `PCT_GENDER` | C | 1 | `gender` | - |
| `PCT_CLBID` | N | 8 | `club_id` | Связь с клубом |
| `PCT_NAT` | C | 3 | `nation` | Все списки |
| `PCT_COANAM` | C | 40 | `coach` | NameData |
| `PCT_SPMNAM` | C | 40 | `music` (SP) | NameData |
| `PCT_FSMNAM` | C | 40 | `music` (FS) | NameData |
| `PCT_COMENT` | C | 40 | `rank` | Разряд |

### Таблица участников категории (PAR.DBF) → JSON поля

| Поле DBF | Тип | JSON поле | Где используется |
|----------|-----|-----------|------------------|
| `PAR_ID` | N | `participant_id` | Ключ |
| `PAR_TPOINT` | N | `tPoints` | Все результаты (делится на 100) |
| `PAR_TPLACE` | N | `tRank` | Все результаты |
| `PAR_POINT1` | N | `points` (сегмент 1) | - |
| `PAR_PLACE1` | N | `place` (сегмент 1) | - |
| `PAR_STAT` | C | `status` | Статус участия |

### Таблица выступлений (PRF.DBF) → JSON поля

| Поле DBF | JSON поле | Где используется |
|----------|-----------|------------------|
| `PRF_TES` | `tes` | 2_Score, 1s2ScoreIResult |
| `PRF_TCS` | `tcs` | 2_Score, 1s2ScoreIResult |
| `PRF_POINTS` | `points` | 2_Score, 1s2ScoreIResult |
| `PRF_BONUS` | `bonus` | 2_Score, 1s2ScoreIResult |
| `PRF_DED_SUM` | `deduction` | 2_Score, 1s2ScoreIResult |

### Элементы выступления (PRF.DBF) → ELEM.json

| Поле DBF | JSON поле | Описание |
|----------|-----------|----------|
| `PRF_XNAE01-20` | `name` | Короткое название элемента |
| `PRF_XNLE01-20` | `longName` | Полное название элемента |
| `PRF_XBVE01-20` | `XBV` | Базовая стоимость |
| `PRF_E01-20PNL` | `XGOE` | GOE (Grade of Execution) |
| `PRF_E01-20RES` | `points` | Итоговые баллы элемента |

### Клубы (Club в XML) → JSON поля

**ВАЖНО:** Клубы в OSIS/XML передаются как вложенные элементы, не из отдельной таблицы DBF!

| Поле XML (Club) | JSON поле | Описание |
|-----------------|-----------|----------|
| `PCT_CNAME` | `club` (Name) | Название клуба |
| `PCT_CNAME` | `club` (Paper Full Name) | То же что Name |
| `PCT_PLNAME` | `club` (Paper List Name) | Полное название для списков |

---

## 📄 НАЗНАЧЕНИЕ ПАГИНАЦИИ (page)

### Зачем нужна пагинация?

1. **Ограничения vMix:**
   - vMix имеет ограничения на количество элементов, которые можно отобразить одновременно
   - Большие списки (50+ участников) не помещаются на один экран

2. **Удобство отображения:**
   - Разделение на страницы позволяет показывать данные порциями
   - Каждая страница имеет заголовок для контекста
   - Можно переключать страницы вручную или автоматически

3. **Производительность:**
   - Меньше данных на странице = быстрее рендеринг
   - Можно загружать страницы по требованию

### Как работает пагинация:

```python
# Пример из startList.json:
page_size = 8  # 8 участников на страницу
pages = [entries[i:i+page_size] for i in range(0, len(entries), page_size)]

# Результат:
# page 0: титульная страница (только заголовок)
# page 1: участники 1-8
# page 2: участники 9-16
# page 3: участники 17-24
# ...
# page N: последняя страница (lastPage: true)
```

### JSON файлы с пагинацией:

1. **`startList.json`** (STR):
   - **8 участников на страницу**
   - Используется для отображения стартового списка
   - Титульная страница (page=0) + страницы с участниками

2. **`resultList.json`** (RES):
   - **6 участников на страницу**
   - Используется для отображения промежуточных результатов
   - Меньше участников на страницу, т.к. больше информации на каждого

### Структура страницы:

```json
{
  "page": 1,                    // Номер страницы (начиная с 1)
  "participants": [...],        // Данные участников (до page_size штук)
  "title": [{...}],            // Заголовок страницы
  "lastPage": true             // Только на последней странице
}
```

### Использование в vMix:

- vMix читает JSON и отображает страницы последовательно
- Можно настроить автоматическое переключение страниц
- Или переключать вручную через триггеры
- Каждая страница - отдельный слайд/сцена в vMix

---

**Конец словаря**
