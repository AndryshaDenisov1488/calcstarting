from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from calcfs_pdf_export.dbf_utils import find_dbf, load_records, rec_get
from calcfs_pdf_export.ids import normalize_id

logger = logging.getLogger(__name__)


@dataclass
class CalcFsSnapshot:
    """Загруженные таблицы и служебная информация."""

    base_dir: Path
    encodings_used: dict[str, str]
    evt: list[dict[str, Any]]
    cat: list[dict[str, Any]]
    scp: list[dict[str, Any]]
    par: list[dict[str, Any]]
    pct: list[dict[str, Any]]
    prf: list[dict[str, Any]]
    clb: list[dict[str, Any]]
    jps: list[dict[str, Any]]


def _load_table(base: Path, stem: str) -> tuple[list[dict[str, Any]], str] | tuple[list, str]:
    p = find_dbf(base, stem)
    if not p:
        return [], ""
    rows, enc = load_records(p)
    return rows, enc


def _id_key(rows: list[dict[str, Any]], *candidates: str) -> dict[Any, dict[str, Any]]:
    out: dict[Any, dict[str, Any]] = {}
    for r in rows:
        pk = None
        for c in candidates:
            pk = rec_get(r, c)
            if pk is not None:
                break
        if pk is None:
            continue
        out[normalize_id(pk)] = r
    return out


def load_calcfs_folder(base: Path) -> CalcFsSnapshot:
    """
    Загружает основные DBF из папки соревнования.
    Отсутствие EVT/CLB не фатально.
    """
    if not base.is_dir():
        raise NotADirectoryError(str(base))

    encodings: dict[str, str] = {}
    tables: dict[str, list] = {}
    for stem in ("EVT", "CAT", "SCP", "PAR", "PCT", "PRF", "CLB", "JPS"):
        rows, enc = _load_table(base, stem)
        tables[stem.lower()] = rows
        if enc:
            encodings[stem] = enc

    prf = tables["prf"]
    par = tables["par"]
    if not prf:
        raise FileNotFoundError(
            f"В {base} не найден PRF.DBF или файл пуст — это обязательная таблица для стартового списка."
        )
    if not par:
        raise FileNotFoundError(f"В {base} не найден PAR.DBF или файл пуст.")

    return CalcFsSnapshot(
        base_dir=base.resolve(),
        encodings_used=encodings,
        evt=tables["evt"],
        cat=tables["cat"],
        scp=tables["scp"],
        par=par,
        pct=tables["pct"],
        prf=prf,
        clb=tables["clb"],
        jps=tables["jps"],
    )


def event_title(snapshot: CalcFsSnapshot) -> str:
    """Первое непустое имя события из EVT (assumption: одно соревнование)."""
    for r in snapshot.evt:
        name = rec_get(r, "EVT_NAME", "EVT_LONGNAME", "EVT_DESC", "NAME", "TITLE")
        if name:
            return str(name).strip()
    return "Соревнование"


def event_place_and_arena(snapshot: CalcFsSnapshot) -> str:
    for r in snapshot.evt:
        place = rec_get(r, "EVT_PLACE", "PLACE", "CITY")
        arena = rec_get(r, "EVT_R1NAM", "EVT_ARENA", "ARENA", "RINK")
        arena_txt = str(arena).strip() if arena and str(arena).strip() else ""
        place_txt = str(place).strip() if place and str(place).strip() else ""
        if arena_txt and place_txt:
            return f"{arena_txt}\n{place_txt}"
        if arena_txt:
            return arena_txt
        if place_txt:
            return place_txt
    return ""


def event_date_range(snapshot: CalcFsSnapshot) -> str:
    for r in snapshot.evt:
        beg = rec_get(r, "EVT_BEGDAT", "BEG_DATE", "DATE_FROM")
        end = rec_get(r, "EVT_ENDDAT", "END_DATE", "DATE_TO")
        beg_txt = _fmt_date(beg)
        end_txt = _fmt_date(end)
        if beg_txt and end_txt:
            return f"{beg_txt}    -    {end_txt}"
        if beg_txt:
            return beg_txt
        if end_txt:
            return end_txt
    return ""


def _fmt_date(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, dt.date):
        return value.strftime("%d.%m.%Y")
    return str(value).strip()


def category_label(snapshot: CalcFsSnapshot, cat_id: Any) -> str:
    norm = normalize_id(cat_id)
    fallback = f"Категория #{cat_id}"
    for r in snapshot.cat:
        rid = normalize_id(rec_get(r, "CAT_ID", "ID"))
        if rid != norm:
            continue
        name = rec_get(r, "CAT_NAME", "CAT_LONGNAME", "CAT_DESC", "NAME", "LONGNAME")
        if name and str(name).strip():
            return str(name).strip()
    return fallback


def segment_label(snapshot: CalcFsSnapshot, scp_id: Any) -> str:
    scp_by = _id_key(snapshot.scp, "SCP_ID", "ID")
    r = scp_by.get(normalize_id(scp_id))
    if not r:
        return f"Сегмент #{scp_id}"
    name = rec_get(r, "SCP_NAME", "SCP_LONGNAME", "SCP_DESC", "NAME", "LONGNAME")
    return str(name).strip() if name else f"Сегмент #{scp_id}"


def club_name(snapshot: CalcFsSnapshot, pct_clbid: Any) -> str:
    if pct_clbid is None or pct_clbid == 0 or pct_clbid == "":
        return "—"
    if not snapshot.clb:
        return "—"
    clb_by = _id_key(snapshot.clb, "CLB_ID", "ID")
    r = clb_by.get(normalize_id(pct_clbid))
    if not r:
        return "—"
    name = rec_get(
        r,
        "CLB_PAPERFULLNAME",
        "CLB_PAPERLISTNAME",
        "PAPER_FULL_NAME",
        "PAPERFULLNAME",
        "CLB_NAME",
        "CLB_CNAME",
        "CLB_LONGNAME",
        "NAME",
        "CNAME",
    )
    return str(name).strip() if name else "—"


def person_display_name(pct: dict[str, Any]) -> str:
    # PCT_CNAME = «Complete Name» часто с инициалом отчества; PCT_PLNAME = «Print Long Name» — полное отчество.
    long_name = rec_get(
        pct,
        "PCT_PRINTLONGNAME",
        "PCT_PLNAME",
        "PLNAME",
    )
    if long_name and str(long_name).strip():
        return str(long_name).strip()
    full = rec_get(pct, "PCT_CNAME", "PCT_LONGNAME")
    if full:
        return str(full).strip()
    g = rec_get(pct, "PCT_GNAME", "GIVENNAME", "FIRSTNAME")
    f = rec_get(pct, "PCT_FNAME", "FAMILYNAME", "LASTNAME")
    parts = [str(x).strip() for x in (g, f) if x]
    return " ".join(parts) if parts else "—"


def discover_cat_scp_pairs(snapshot: CalcFsSnapshot) -> list[tuple[Any, Any, str]]:
    """
    Находит пары (CAT_ID, SCP_ID), для которых есть PRF+PAR.
    Возвращает список (cat_id, scp_id, метка для UI).
    """
    par_by = _id_key(snapshot.par, "PAR_ID", "ID")
    valid_scp_ids = set(_id_key(snapshot.scp, "SCP_ID", "ID").keys())
    valid_cat_ids = set(_id_key(snapshot.cat, "CAT_ID", "ID").keys())
    pairs: dict[tuple[Any, Any], int] = {}
    category_counts: dict[Any, int] = {}

    for par in snapshot.par:
        cat_id = normalize_id(rec_get(par, "CAT_ID"))
        if cat_id is None:
            continue
        category_counts[cat_id] = category_counts.get(cat_id, 0) + 1

    for pr in snapshot.prf:
        par_id = rec_get(pr, "PAR_ID")
        scp_id = normalize_id(rec_get(pr, "SCP_ID"))
        if par_id is None or scp_id is None or scp_id not in valid_scp_ids:
            continue
        par = par_by.get(normalize_id(par_id))
        if not par:
            logger.warning("PRF ссылается на отсутствующий PAR_ID=%s", par_id)
            continue
        cat_id = normalize_id(rec_get(par, "CAT_ID"))
        if cat_id is None or (valid_cat_ids and cat_id not in valid_cat_ids):
            continue
        key = (cat_id, scp_id)
        pairs[key] = pairs.get(key, 0) + 1

    def _num_key(x: Any) -> tuple[int, Any]:
        try:
            return (0, int(float(x)))
        except (TypeError, ValueError):
            return (1, str(x))

    result: list[tuple[Any, Any, str]] = []
    for (cat_id, scp_id) in sorted(pairs.keys(), key=lambda p: (_num_key(p[0]), _num_key(p[1]))):
        cat_total = category_counts.get(cat_id, 0)
        seg_total = pairs[(cat_id, scp_id)]
        label = (
            f"{category_label(snapshot, cat_id)} / {segment_label(snapshot, scp_id)} "
            f"(в категории: {cat_total}, в сегменте: {seg_total})"
        )
        result.append((cat_id, scp_id, label))
    return result
