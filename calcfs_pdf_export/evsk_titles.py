from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from calcfs_pdf_export.dbf_utils import rec_get
from calcfs_pdf_export.ids import same_id


@dataclass(frozen=True)
class EvskTitleRule:
    discipline: str
    rank: str
    age_groups: tuple[str, ...]


DISCIPLINES = {
    "S": "ОДИНОЧНОЕ КАТАНИЕ",
    "P": "ПАРНОЕ КАТАНИЕ",
    "D": "ТАНЦЫ НА ЛЬДУ",
    "Y": "СИНХРОННОЕ КАТАНИЕ",
}

RANKS = {
    "1": "1 СПОРТИВНЫЙ РАЗРЯД",
    "2": "2 СПОРТИВНЫЙ РАЗРЯД",
    "3": "3 СПОРТИВНЫЙ РАЗРЯД",
    "4": "1 ЮНОШЕСКИЙ РАЗРЯД",
    "5": "2 ЮНОШЕСКИЙ РАЗРЯД",
    "6": "3 ЮНОШЕСКИЙ РАЗРЯД",
    "u": "ЮНЫЙ ФИГУРИСТ",
    "c": "ЮНЫЙ ФИГУРИСТ",
    "v": "НОВИЧОК",
    "z": "ДЕБЮТ",
    "m": "МЛАДШИЙ СПЕЦИАЛЬНЫЙ РАЗРЯД",
}

SINGLE_FEMALE = {
    "1": ("ДЕВУШКИ (11-17 ЛЕТ)",),
    "2": ("ДЕВУШКИ (11-17 ЛЕТ)", "ДЕВОЧКИ (8-12 ЛЕТ)", "ДЕВОЧКИ (6-9 ЛЕТ)"),
    "3": ("ДЕВУШКИ (11-17 ЛЕТ)", "ДЕВОЧКИ (8-12 ЛЕТ)", "ДЕВОЧКИ (6-9 ЛЕТ)"),
    "4": ("ДЕВУШКИ (11-17 ЛЕТ)", "ДЕВОЧКИ (8-12 ЛЕТ)", "ДЕВОЧКИ (6-9 ЛЕТ)"),
    "5": ("ДЕВУШКИ (11-17 ЛЕТ)", "ДЕВОЧКИ (8-12 ЛЕТ)", "ДЕВОЧКИ (6-9 ЛЕТ)"),
    "6": ("ДЕВУШКИ (11-17 ЛЕТ)", "ДЕВОЧКИ (8-12 ЛЕТ)", "ДЕВОЧКИ (6-9 ЛЕТ)"),
}
SINGLE_MALE = {
    "1": ("ЮНОШИ (11-17 ЛЕТ)",),
    "2": ("ЮНОШИ (11-17 ЛЕТ)", "МАЛЬЧИКИ (8-12 ЛЕТ)", "МАЛЬЧИКИ (6-9 ЛЕТ)"),
    "3": ("ЮНОШИ (11-17 ЛЕТ)", "МАЛЬЧИКИ (8-12 ЛЕТ)", "МАЛЬЧИКИ (6-9 ЛЕТ)"),
    "4": ("ЮНОШИ (11-17 ЛЕТ)", "МАЛЬЧИКИ (8-12 ЛЕТ)", "МАЛЬЧИКИ (6-9 ЛЕТ)"),
    "5": ("ЮНОШИ (11-17 ЛЕТ)", "МАЛЬЧИКИ (8-12 ЛЕТ)", "МАЛЬЧИКИ (6-9 ЛЕТ)"),
    "6": ("ЮНОШИ (11-17 ЛЕТ)", "МАЛЬЧИКИ (8-12 ЛЕТ)", "МАЛЬЧИКИ (6-9 ЛЕТ)"),
}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _gender_key(value: Any) -> str:
    raw = _norm(value).upper()
    if raw.startswith("F"):
        return "F"
    if raw.startswith("M"):
        return "M"
    return "C"


def _age_sort_key(value: str) -> tuple[int, int, str]:
    numbers = [int(n) for n in re.findall(r"\d+", value)]
    if len(numbers) >= 2:
        return numbers[0], numbers[1], value
    if numbers:
        return numbers[0], numbers[0], value
    return 999, 999, value


def sort_age_groups(age_groups: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted((str(age).strip() for age in age_groups if str(age).strip()), key=_age_sort_key))


def _age_groups(cat_type: str, level: str, gender: str) -> tuple[str, ...]:
    if cat_type == "S":
        if gender == "F":
            return SINGLE_FEMALE.get(level, ())
        if gender == "M":
            return SINGLE_MALE.get(level, ())
        return ()
    if cat_type == "P":
        if level in {"1", "2"}:
            return ("ЮНОШИ (11-19 ЛЕТ), ДЕВУШКИ (11-17 ЛЕТ)",)
        if level in {"3", "4"}:
            return ("ЮНОШИ (11-19 ЛЕТ), ДЕВУШКИ (11-17 ЛЕТ)",)
        return ()
    if cat_type == "D":
        if level in {"1", "2"}:
            return ("ЮНОШИ (11-19 ЛЕТ), ДЕВУШКИ (11-17 ЛЕТ)",)
        if level == "3":
            return ("ЮНОШИ (11-19 ЛЕТ), ДЕВУШКИ (11-17 ЛЕТ)",)
        if level in {"4", "5", "6"}:
            return ("МАЛЬЧИКИ, ДЕВОЧКИ (8-12 ЛЕТ)", "МАЛЬЧИКИ, ДЕВОЧКИ (6-9 ЛЕТ)")
        return ()
    if cat_type == "Y":
        if level in {"1", "2"}:
            return ("ЮНОШИ, ДЕВУШКИ (10-15 ЛЕТ)",)
        if level in {"3", "4"}:
            return ("ЮНОШИ, ДЕВУШКИ (10-15 ЛЕТ)",)
    return ()


def rule_for_category(cat: dict[str, Any]) -> EvskTitleRule | None:
    cat_type = _norm(rec_get(cat, "CAT_TYPE")).upper()
    level = _norm(rec_get(cat, "CAT_LEVEL"))
    gender = _gender_key(rec_get(cat, "CAT_GENDER"))
    discipline = DISCIPLINES.get(cat_type)
    rank = RANKS.get(level)
    if not discipline or not rank:
        return None
    return EvskTitleRule(discipline=discipline, rank=rank, age_groups=_age_groups(cat_type, level, gender))


def official_title_for_category(
    cat: dict[str, Any],
    selected_age_groups: list[str] | tuple[str, ...] | None = None,
    *,
    include_discipline: bool = True,
) -> str | None:
    rule = rule_for_category(cat)
    if not rule:
        return None
    age_groups = sort_age_groups(tuple(selected_age_groups) if selected_age_groups is not None else rule.age_groups)
    lines = [rule.discipline] if include_discipline else []
    lines.append(rule.rank)
    if age_groups:
        lines.append(", ".join(age_groups))
    return "\r\n".join(lines)


def build_default_title_overrides(snapshot: Any, *, include_discipline: bool = True) -> dict[Any, str]:
    overrides: dict[Any, str] = {}
    for cat in snapshot.cat:
        title = official_title_for_category(cat, include_discipline=include_discipline)
        if title:
            overrides[rec_get(cat, "CAT_ID")] = title
    return overrides


def cat_key(cat_id: Any) -> str:
    return str(cat_id).strip()


def category_by_id(snapshot: Any, cat_id: Any) -> dict[str, Any] | None:
    for cat in snapshot.cat:
        if same_id(rec_get(cat, "CAT_ID"), cat_id):
            return cat
    return None
