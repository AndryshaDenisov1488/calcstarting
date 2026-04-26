from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from calcfs_pdf_export.calcfs_store import (
    CalcFsSnapshot,
    _id_key,
    category_label,
    event_date_range,
    event_place_and_arena,
    event_title,
    person_display_name,
    segment_label,
)
from calcfs_pdf_export.dbf_utils import rec_get
from calcfs_pdf_export.ids import normalize_id, same_id
from calcfs_pdf_export.starting_order_report import (
    _extract_birth_date,
    _guess_active_rank,
    _guess_club,
    _guess_school,
)


@dataclass
class ElementScore:
    number: int
    code: str
    info: str
    base_value: float | None
    goe: float | None
    judge_marks: list[str]
    result: float | None


@dataclass
class ComponentScore:
    name: str
    short_name: str
    factor: float | None
    judge_marks: list[str]
    result: float | None


@dataclass
class ProtocolParticipant:
    place: int | None
    start_num: int | None
    name: str
    club: str
    active_rank: str
    birth_date: str
    total_score: float | None
    tes: float | None
    pcs: float | None
    deductions: float | None
    component_scores: list[ComponentScore]
    element_scores: list[ElementScore]
    par: dict[str, Any]
    pct: dict[str, Any]
    prf: dict[str, Any]


@dataclass
class ProtocolSegmentBundle:
    event_name: str
    event_place_line: str
    event_date_line: str
    category_name: str
    segment_name: str
    cat_id: Any
    scp_id: Any
    judge_labels: list[str]
    component_labels: list[str]
    participants: list[ProtocolParticipant]


def as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def scaled_score(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return int(round(float(value))) / 100.0
    except (TypeError, ValueError):
        return None


def format_score(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return ""
    if signed and value > 0:
        return f"+{value:.2f}"
    return f"{value:.2f}"


def format_int(value: int | None) -> str:
    return "" if value is None else str(value)


def _component_slots(scp: dict[str, Any]) -> list[tuple[str, str, float | None]]:
    slots: list[tuple[str, str, float | None]] = []
    for idx in range(1, 18):
        key = f"{idx:02d}"
        name = rec_get(scp, f"SCP_CRIT{key}")
        short = rec_get(scp, f"SCP_CRSH{key}")
        factor = scaled_score(rec_get(scp, f"SCP_CRFR{key}"))
        if name or short or factor:
            slots.append((str(name or short or f"Компонент {idx}").strip(), str(short or "").strip(), factor))
    return slots


def _judge_labels(snapshot: CalcFsSnapshot, scp: dict[str, Any]) -> list[str]:
    pct_by = _id_key(snapshot.pct, "PCT_ID", "ID")
    labels: list[str] = []
    jps = [r for r in getattr(snapshot, "jps", []) if same_id(rec_get(r, "SCP_ID"), rec_get(scp, "SCP_ID"))]
    jps.sort(key=lambda r: str(rec_get(r, "JPS_SORT") or ""))
    for row in jps:
        pct_id = rec_get(row, "PCT_ID")
        if as_int(pct_id) in (None, 0):
            continue
        label = str(rec_get(row, "JPS_TYPE") or "").strip()
        pct = pct_by.get(normalize_id(pct_id))
        if not label:
            label = person_display_name(pct) if pct else f"J{len(labels) + 1}"
        labels.append(label)
    if labels:
        return labels

    for idx in range(1, 16):
        pct_id = rec_get(scp, f"SCP_JID{idx:02d}")
        if as_int(pct_id) in (None, 0):
            continue
        labels.append(f"J{len(labels) + 1}")
    return labels or ["J1", "J2", "J3"]


def _judge_mark(value: Any, *, component: bool = False) -> str:
    if value is None or value == "":
        return ""
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return str(value).strip()
    if component:
        return f"{raw / 100:.2f}"
    # ISUCalcFS often keeps 9 in unused GOE slots. Hide it when it is not a valid GOE.
    if raw == 9:
        return ""
    if raw == int(raw):
        return str(int(raw))
    return f"{raw:.2f}"


def _deductions(prf: dict[str, Any]) -> float:
    total = 0.0
    for idx in range(1, 18):
        val = scaled_score(rec_get(prf, f"PRF_DED{idx:02d}"))
        if val:
            total += abs(val)
    return total


def _element_scores(prf: dict[str, Any], judge_count: int) -> list[ElementScore]:
    rows: list[ElementScore] = []
    for idx in range(1, 21):
        key = f"{idx:02d}"
        code = rec_get(prf, f"PRF_XNAE{key}", f"PRF_INAE{key}")
        base = scaled_score(rec_get(prf, f"PRF_XBVE{key}"))
        result = scaled_score(rec_get(prf, f"PRF_E{key}RES"))
        if not code and base is None and result is None:
            continue
        info = str(rec_get(prf, f"PRF_XCFE{key}", f"PRF_E{key}INF") or "").strip()
        marks = [_judge_mark(rec_get(prf, f"PRF_E{key}J{j:02d}")) for j in range(1, judge_count + 1)]
        goe = (result - base) if result is not None and base is not None else scaled_score(rec_get(prf, f"PRF_E{key}PNL"))
        rows.append(
            ElementScore(
                number=idx,
                code=str(code or "").strip(),
                info=info,
                base_value=base,
                goe=goe,
                judge_marks=marks,
                result=result,
            )
        )
    return rows


def _component_scores(prf: dict[str, Any], scp: dict[str, Any], judge_count: int) -> list[ComponentScore]:
    rows: list[ComponentScore] = []
    for idx, (name, short, factor) in enumerate(_component_slots(scp), start=1):
        # Component DBF fields are sparse and usually match the criterion number from SCP_CRIT##.
        key = None
        for candidate in range(1, 18):
            cand = f"{candidate:02d}"
            if rec_get(scp, f"SCP_CRIT{cand}") == name or rec_get(scp, f"SCP_CRSH{cand}") == short:
                key = cand
                break
        key = key or f"{idx:02d}"
        result = scaled_score(rec_get(prf, f"PRF_C{key}RES"))
        marks = [
            _judge_mark(
                rec_get(
                    prf,
                    f"PRF_C{key}J{j:02d}",
                    f"PRF_C{idx:02d}J{j:02d}",
                ),
                component=True,
            )
            for j in range(1, judge_count + 1)
        ]
        if result is None and not any(marks):
            continue
        rows.append(ComponentScore(name=name, short_name=short, factor=factor, judge_marks=marks, result=result))
    return rows


def _place(prf: dict[str, Any], par: dict[str, Any]) -> int | None:
    return as_int(rec_get(prf, "PRF_PLACE")) or as_int(rec_get(par, "PAR_TPLACE")) or as_int(rec_get(par, "PAR_PLACE1"))


def _total_score(prf: dict[str, Any], par: dict[str, Any]) -> float | None:
    return scaled_score(rec_get(prf, "PRF_POINTS")) or scaled_score(rec_get(par, "PAR_TPOINT")) or scaled_score(rec_get(par, "PAR_POINT1"))


def build_protocol_segment(snapshot: CalcFsSnapshot, cat_id: Any, scp_id: Any) -> ProtocolSegmentBundle:
    par_by = _id_key(snapshot.par, "PAR_ID", "ID")
    pct_by = _id_key(snapshot.pct, "PCT_ID", "ID")
    scp_by = _id_key(snapshot.scp, "SCP_ID", "ID")
    scp = scp_by.get(normalize_id(scp_id))
    if not scp:
        raise ValueError(f"Сегмент не найден: SCP_ID={scp_id}")

    judge_labels = _judge_labels(snapshot, scp)
    judge_count = max(1, min(15, len(judge_labels)))
    component_slots = _component_slots(scp)
    participants: list[ProtocolParticipant] = []

    for prf in snapshot.prf:
        if not same_id(rec_get(prf, "SCP_ID"), scp_id):
            continue
        par = par_by.get(normalize_id(rec_get(prf, "PAR_ID")))
        if not par or not same_id(rec_get(par, "CAT_ID"), cat_id):
            continue
        pct = pct_by.get(normalize_id(rec_get(par, "PCT_ID")))
        if not pct:
            continue
        club = _guess_club(snapshot, par, pct, pct_by)
        elements = _element_scores(prf, judge_count)
        components = _component_scores(prf, scp, judge_count)
        participants.append(
            ProtocolParticipant(
                place=_place(prf, par),
                start_num=as_int(rec_get(prf, "PRF_STNUM")),
                name=person_display_name(pct),
                club=_guess_school(par, pct, club),
                active_rank=_guess_active_rank(par, pct),
                birth_date=_extract_birth_date(rec_get(pct, "PCT_BDAY", "BDAY", "BIRTH_DATE")),
                total_score=_total_score(prf, par),
                tes=scaled_score(rec_get(prf, "PRF_M1RES", "PRF_M1TOT")),
                pcs=scaled_score(rec_get(prf, "PRF_M2RES", "PRF_M2TOT")),
                deductions=_deductions(prf),
                component_scores=components,
                element_scores=elements,
                par=par,
                pct=pct,
                prf=prf,
            )
        )

    participants.sort(
        key=lambda r: (
            r.place is None,
            r.place if r.place is not None else 9999,
            -(r.total_score or 0.0),
            r.start_num or 9999,
            r.name,
        )
    )
    return ProtocolSegmentBundle(
        event_name=event_title(snapshot),
        event_place_line=event_place_and_arena(snapshot),
        event_date_line=event_date_range(snapshot),
        category_name=category_label(snapshot, cat_id),
        segment_name=segment_label(snapshot, scp_id),
        cat_id=cat_id,
        scp_id=scp_id,
        judge_labels=judge_labels[:judge_count],
        component_labels=[short or name for name, short, _ in component_slots],
        participants=participants,
    )
