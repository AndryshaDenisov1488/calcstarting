from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from calcfs_pdf_export.calcfs_store import load_calcfs_folder
from calcfs_pdf_export.merge_pdfs import merge_pdf_files
from calcfs_pdf_export.pdf_render import render_starting_order_pdf
from calcfs_pdf_export.starting_order_report import (
    StartingOrderRow,
    StartingOrderSheet,
    build_starting_order_rows,
    regroup_rows,
)

logger = logging.getLogger(__name__)


def _combined_category_title(sheets: list[StartingOrderSheet]) -> str:
    names = [(s.category_name or "").strip() for s in sheets]
    return "\n".join(n for n in names if n)


@dataclass
class UnitResult:
    cat_id: object
    scp_id: object
    label: str
    ok: bool
    message: str
    pdf_path: Path | None


def export_starting_order_bundle(
    base_dir: Path,
    selected: list[tuple[object, object, str]],
    output_pdf: Path,
    *,
    keep_temp: bool = False,
    combine_selected_into_single_sheet: bool = False,
    regroup_warmups_for_combined: bool = True,
    warmup_size: int = 6,
    merge_group_map: dict[tuple[object, object], int] | None = None,
    group_warmup_size_map: dict[int, int] | None = None,
    group_insert_texts_map: dict[int, list[tuple[str, int, str]]] | None = None,
    include_active_rank: bool = True,
    include_birth_date: bool = True,
    include_coach: bool = False,
) -> tuple[list[UnitResult], Path | None]:
    """
    Формирует по PDF на каждую выбранную пару (CAT, SCP), объединяет в один файл.
    Порядок merge = порядок элементов в `selected` (детерминированно задаёт пользователь/GUI).

    Возвращает (результаты по единицам, путь итогового PDF или None если нечего мержить).
    """
    snapshot = load_calcfs_folder(base_dir)
    results: list[UnitResult] = []
    temp_dir = Path(tempfile.mkdtemp(prefix="calcfs_pdf_"))
    merged: Path | None = None

    try:
        for idx, (cat_id, scp_id, label) in enumerate(selected, start=1):
            part_path = temp_dir / f"part_{idx:04d}.pdf"
            try:
                sheet = build_starting_order_rows(snapshot, cat_id, scp_id)
                render_starting_order_pdf(
                    part_path,
                    sheet,
                    include_active_rank=include_active_rank,
                    include_birth_date=include_birth_date,
                    include_coach=include_coach,
                )
                results.append(
                    UnitResult(
                        cat_id=cat_id,
                        scp_id=scp_id,
                        label=label,
                        ok=True,
                        message="OK",
                        pdf_path=part_path,
                    )
                )
            except Exception as e:
                logger.exception("Ошибка отчёта для %s", label)
                results.append(
                    UnitResult(
                        cat_id=cat_id,
                        scp_id=scp_id,
                        label=label,
                        ok=False,
                        message=str(e),
                        pdf_path=None,
                    )
                )

        if merge_group_map:
            buckets: dict[int, list[tuple[object, object, str]]] = {}
            bucket_order: list[int] = []
            solo_counter = 100000
            for cat_id, scp_id, label in selected:
                gid = merge_group_map.get((cat_id, scp_id))
                if gid is None or gid <= 0:
                    gid = solo_counter
                    solo_counter += 1
                if gid not in buckets:
                    buckets[gid] = []
                    bucket_order.append(gid)
                buckets[gid].append((cat_id, scp_id, label))

            ok_parts = []
            for idx, gid in enumerate(bucket_order, start=1):
                group_selected = buckets[gid]
                ok_sheets: list[StartingOrderSheet] = []
                combined_rows: list[StartingOrderRow] = []
                for cat_id, scp_id, _ in group_selected:
                    sheet = build_starting_order_rows(snapshot, cat_id, scp_id)
                    if not sheet.rows:
                        continue
                    ok_sheets.append(sheet)
                    combined_rows.extend(sheet.rows)
                if not combined_rows:
                    continue
                if regroup_warmups_for_combined:
                    group_size = int((group_warmup_size_map or {}).get(gid, warmup_size))
                    combined_rows = regroup_rows(
                        combined_rows,
                        warmup_size=group_size,
                        reset_start_num_on_category_change=True,
                    )
                first = ok_sheets[0]
                pre_texts_by_warmup: dict[int, list[str]] = {}
                post_texts_by_warmup: dict[int, list[str]] = {}
                for mode, insert_idx, text in (group_insert_texts_map or {}).get(gid, []):
                    txt = str(text).strip()
                    if not txt:
                        continue
                    key = int(insert_idx)
                    if mode == "after":
                        post_texts_by_warmup.setdefault(key, []).append(txt)
                    else:
                        pre_texts_by_warmup.setdefault(key, []).append(txt)
                combined_sheet = StartingOrderSheet(
                    event_name=first.event_name,
                    event_place_line=first.event_place_line,
                    event_date_line=first.event_date_line,
                    category_name=_combined_category_title(ok_sheets),
                    segment_name="СТАРТОВЫЙ ЛИСТ",
                    rows=combined_rows,
                )
                part_path = temp_dir / f"part_group_{idx:04d}.pdf"
                render_starting_order_pdf(
                    part_path,
                    combined_sheet,
                    include_active_rank=include_active_rank,
                    include_birth_date=include_birth_date,
                    include_coach=include_coach,
                    pre_warmup_texts=pre_texts_by_warmup,
                    post_warmup_texts=post_texts_by_warmup,
                )
                ok_parts.append(part_path)
        elif combine_selected_into_single_sheet:
            ok_sheets: list[StartingOrderSheet] = []
            combined_rows: list[StartingOrderRow] = []
            for cat_id, scp_id, _ in selected:
                sheet = build_starting_order_rows(snapshot, cat_id, scp_id)
                if not sheet.rows:
                    continue
                ok_sheets.append(sheet)
                combined_rows.extend(sheet.rows)
            if combined_rows:
                if regroup_warmups_for_combined:
                    combined_rows = regroup_rows(
                        combined_rows,
                        warmup_size=warmup_size,
                        reset_start_num_on_category_change=True,
                    )
                first = ok_sheets[0]
                combined_sheet = StartingOrderSheet(
                    event_name=first.event_name,
                    event_place_line=first.event_place_line,
                    event_date_line=first.event_date_line,
                    category_name=_combined_category_title(ok_sheets),
                    segment_name="СТАРТОВЫЙ ЛИСТ",
                    rows=combined_rows,
                )
                one_path = temp_dir / "part_combined.pdf"
                render_starting_order_pdf(
                    one_path,
                    combined_sheet,
                    include_active_rank=include_active_rank,
                    include_birth_date=include_birth_date,
                    include_coach=include_coach,
                )
                for r in results:
                    if r.ok:
                        r.pdf_path = one_path
                ok_parts = [one_path]
            else:
                ok_parts = []
        else:
            ok_parts = [r.pdf_path for r in results if r.ok and r.pdf_path]

        if ok_parts:
            merged = merge_pdf_files(ok_parts, output_pdf)
        else:
            logger.error("Ни один фрагмент PDF не создан.")
    finally:
        if keep_temp:
            logger.info("Временные PDF сохранены в %s", temp_dir)
        else:
            for p in temp_dir.glob("*"):
                try:
                    p.unlink()
                except OSError:
                    pass
            try:
                temp_dir.rmdir()
            except OSError:
                logger.debug("Не удалось удалить временную папку %s", temp_dir)

    return results, merged
