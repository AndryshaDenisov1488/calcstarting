from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any

from calcfs_pdf_export.calcfs_store import (
    CalcFsSnapshot,
    _id_key,
    category_label,
    club_name,
    event_date_range,
    event_place_and_arena,
    event_title,
    person_display_name,
    segment_label,
)
from calcfs_pdf_export.dbf_utils import rec_get
from calcfs_pdf_export.ids import normalize_id, same_id

logger = logging.getLogger(__name__)


@dataclass
class StartingOrderRow:
    start_num: int
    name: str
    school: str
    club: str
    category_name: str
    active_rank: str
    birth_date: str
    coach_name: str
    warmup_group: int
    cat_id: Any
    scp_id: Any


@dataclass
class StartingOrderSheet:
    event_name: str
    event_place_line: str
    event_date_line: str
    category_name: str
    segment_name: str
    rows: list[StartingOrderRow]


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _extract_birth_date(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, dt.date):
        return value.strftime("%d.%m.%Y")
    text = str(value).strip()
    if not text:
        return "—"
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) == 8:
        y, m, d = digits[:4], digits[4:6], digits[6:8]
        return f"{d}.{m}.{y}"
    parts = text.replace("-", ".").replace("/", ".").split(".")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        a, b, c = parts
        if len(a) == 4:
            return f"{c.zfill(2)}.{b.zfill(2)}.{a.zfill(4)}"
        return f"{a.zfill(2)}.{b.zfill(2)}.{c.zfill(4)}"
    return text


def _guess_start_num(prf: dict[str, Any], fallback_index: int) -> int:
    raw = rec_get(
        prf,
        "PRF_STNUM",
        "PRF_STARTNO",
        "PRF_STARTNUM",
        "STNUM",
        "STARTNUM",
        "START_NUMBER",
    )
    num = _as_int(raw)
    if num is None or num <= 0:
        return fallback_index
    return num


def _guess_warmup_group(prf: dict[str, Any], fallback_group: int) -> int:
    raw = rec_get(
        prf,
        "PRF_STGNUM",
        "PRF_STGRP",
        "PRF_STGRNUM",
        "START_GROUP",
        "WARMUP",
    )
    grp = _as_int(raw)
    if grp is None or grp <= 0:
        return fallback_group
    return grp


def _guess_coach_name(par: dict[str, Any], pct: dict[str, Any]) -> str:
    """Имя тренера (в карточке CalcFS — Coach Name). В ISUCalcFS: PCT_COANAM."""
    val = rec_get(
        pct,
        "PCT_COANAM",
        "PCT_COACH",
        "PCT_COACHNAM",
        "PCT_COACHNAME",
        "PCT_COACH_NAME",
        "COACHNAME",
        "COACH_NAME",
        "COACH",
    )
    if not val:
        val = rec_get(
            par,
            "PAR_COANAM",
            "PAR_COACH",
            "PAR_COACHNAM",
            "PAR_COACHNAME",
            "PAR_COACH_NAME",
            "COACHNAME",
            "COACH_NAME",
            "COACH",
        )
    return str(val).strip() if val else "—"


def _guess_active_rank(par: dict[str, Any], pct: dict[str, Any]) -> str:
    val = rec_get(pct, "PCT_COMENT", "PCT_RANK", "PCT_CLASS", "PCT_NOTE")
    if not val:
        val = rec_get(par, "PAR_RANK", "PAR_CLASS", "PAR_NOTE")
    return str(val).strip() if val else "—"


def _extract_org_from_pct_ref(pct_ref: dict[str, Any] | None) -> str:
    if not pct_ref:
        return ""
    for field in ("PCT_CNAME", "PCT_PLNAME", "PCT_TLNAME", "PCT_SNAME"):
        val = pct_ref.get(field)
        if val and str(val).strip():
            return str(val).strip()
    return ""


def _guess_club(
    snapshot: CalcFsSnapshot,
    par: dict[str, Any],
    pct: dict[str, Any],
    pct_by: dict[Any, dict[str, Any]],
) -> str:
    from_pct = club_name(snapshot, rec_get(pct, "PCT_CLBID", "CLB_ID"))
    if from_pct != "—":
        return from_pct
    from_par = club_name(snapshot, rec_get(par, "PAR_CLBID", "CLB_ID"))
    if from_par != "—":
        return from_par

    clb_pct = pct_by.get(normalize_id(rec_get(par, "PAR_CLBID", "PCT_CLBID", "CLB_ID")))
    ref_val = _extract_org_from_pct_ref(clb_pct)
    if ref_val:
        return ref_val

    clb_pct2 = pct_by.get(normalize_id(rec_get(pct, "PCT_CLBID", "PAR_CLBID", "CLB_ID")))
    ref_val2 = _extract_org_from_pct_ref(clb_pct2)
    if ref_val2:
        return ref_val2

    txt = rec_get(pct, "PCT_CLBNAME", "PCT_CLUB", "PCT_TEAM")
    return str(txt).strip() if txt else "—"


def _guess_school(par: dict[str, Any], pct: dict[str, Any], club: str) -> str:
    val = rec_get(par, "PAR_CSNAM", "PAR_SCHOOL", "PAR_TEAM", "PAR_SCH")
    if not val:
        val = rec_get(pct, "PCT_SCHOOL", "PCT_TEAM", "PCT_SCH", "PCT_SCHOOLNAME")
    if val and str(val).strip():
        return str(val).strip()
    return club


def _guess_person_name(par: dict[str, Any], pct: dict[str, Any]) -> str:
    val = rec_get(
        pct,
        "PCT_PRINTLONGNAME",
        "PRINTLONGNAME",
        "PRINT LONG NAME",
        "PRINT_LONG_NAME",
        "PCT_PLNAME",
        "PLNAME",
    )
    if not val:
        val = rec_get(par, "PAR_PRINTLONGNAME", "PRINTLONGNAME")
    if val and str(val).strip():
        return str(val).strip()
    return person_display_name(pct)


def build_starting_order_rows(
    snapshot: CalcFsSnapshot,
    cat_id: Any,
    scp_id: Any,
) -> StartingOrderSheet:
    par_by = _id_key(snapshot.par, "PAR_ID", "ID")
    pct_by = _id_key(snapshot.pct, "PCT_ID", "ID")

    tmp: list[StartingOrderRow] = []
    seq = 0
    scp_ids = set(_id_key(snapshot.scp, "SCP_ID", "ID").keys())
    for pr in snapshot.prf:
        if not same_id(rec_get(pr, "SCP_ID"), scp_id):
            continue
        if normalize_id(rec_get(pr, "SCP_ID")) not in scp_ids:
            continue
        par = par_by.get(normalize_id(rec_get(pr, "PAR_ID")))
        if not par or not same_id(rec_get(par, "CAT_ID"), cat_id):
            continue
        pct = pct_by.get(normalize_id(rec_get(par, "PCT_ID")))
        if not pct:
            continue
        seq += 1
        start_num = _guess_start_num(pr, seq)
        warmup = _guess_warmup_group(pr, ((seq - 1) // 6) + 1)
        person_name = _guess_person_name(par, pct)
        club = _guess_club(snapshot, par, pct, pct_by)
        tmp.append(
            StartingOrderRow(
                start_num=start_num,
                name=person_name,
                school=_guess_school(par, pct, club),
                club=club,
                category_name=category_label(snapshot, cat_id),
                active_rank=_guess_active_rank(par, pct),
                birth_date=_extract_birth_date(rec_get(pct, "PCT_BDAY", "BDAY", "BIRTH_DATE")),
                coach_name=_guess_coach_name(par, pct),
                warmup_group=warmup,
                cat_id=cat_id,
                scp_id=scp_id,
            )
        )

    tmp.sort(key=lambda r: (r.warmup_group, r.start_num, r.name))
    if tmp and len({r.start_num for r in tmp}) == 1:
        logger.warning("Стартовые номера выглядят некорректно (одинаковы). Использована fallback-нумерация.")
        for i, row in enumerate(tmp, start=1):
            row.start_num = i

    return StartingOrderSheet(
        event_name=event_title(snapshot),
        event_place_line=event_place_and_arena(snapshot),
        event_date_line=event_date_range(snapshot),
        category_name=category_label(snapshot, cat_id),
        segment_name=segment_label(snapshot, scp_id),
        rows=tmp,
    )


def regroup_rows(
    rows: list[StartingOrderRow],
    warmup_size: int,
    *,
    reset_start_num_on_category_change: bool = False,
) -> list[StartingOrderRow]:
    if warmup_size < 1:
        warmup_size = 6
    if not rows:
        return []

    total = len(rows)
    group_count = (total + warmup_size - 1) // warmup_size
    base = total // group_count
    rem = total % group_count
    chunk_sizes = [base] * (group_count - rem) + [base + 1] * rem

    out: list[StartingOrderRow] = []
    idx = 0
    warmup_no = 1
    last_cat = None
    start_no = 1
    for size in chunk_sizes:
        for _ in range(size):
            src = rows[idx]
            idx += 1
            if reset_start_num_on_category_change and last_cat != src.cat_id:
                start_no = 1
                last_cat = src.cat_id
            cloned = StartingOrderRow(
                start_num=start_no if reset_start_num_on_category_change else len(out) + 1,
                name=src.name,
                school=src.school,
                club=src.club,
                category_name=src.category_name,
                active_rank=src.active_rank,
                birth_date=src.birth_date,
                coach_name=src.coach_name,
                warmup_group=warmup_no,
                cat_id=src.cat_id,
                scp_id=src.scp_id,
            )
            out.append(cloned)
            start_no += 1
        warmup_no += 1
    return out
