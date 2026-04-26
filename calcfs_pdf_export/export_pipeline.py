from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from calcfs_pdf_export.calcfs_store import load_calcfs_folder
from calcfs_pdf_export.dbf_utils import rec_get
from calcfs_pdf_export.evsk_titles import build_default_title_overrides
from calcfs_pdf_export.ids import same_id
from calcfs_pdf_export.merge_pdfs import merge_pdf_files
from calcfs_pdf_export.pdf_render import render_starting_order_pdf
from calcfs_pdf_export.protocol_pdf_render import (
    render_judges_scores_pdf,
    render_result_for_segment_details_pdf,
    render_result_with_club_names_pdf,
)
from calcfs_pdf_export.protocol_report import build_protocol_segment
from calcfs_pdf_export.rpt_export import (
    JUDGES_SCORES,
    RESULT_FOR_SEGMENT_DETAILS,
    RESULT_WITH_CLUB_NAMES,
    export_crystal_report_pdf,
)
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


def _final_scp_id_for_category(snapshot, cat_id: object, fallback_scp_id: object) -> object:
    for cat in snapshot.cat:
        if not same_id(rec_get(cat, "CAT_ID"), cat_id):
            continue
        final_scp = rec_get(cat, "CAT_LSCPID", "CAT_SCPID2", "CAT_SCPID1")
        if final_scp not in (None, "", 0):
            return final_scp
    return fallback_scp_id


def _title_override_for_category(title_overrides: dict[object, str], cat_id: object) -> str | None:
    for key, title in title_overrides.items():
        if same_id(key, cat_id):
            return title
    return None


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


def export_protocol_bundle(
    base_dir: Path,
    selected: list[tuple[object, object, str]],
    output_pdf: Path,
    *,
    include_result: bool = True,
    include_segment_details: bool = True,
    include_judges_scores: bool = True,
    keep_temp: bool = False,
    protocol_renderer: str = "rpt",
    category_title_overrides: dict[object, str] | None = None,
    rpt_template_paths: dict[str, Path] | None = None,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
) -> tuple[list[UnitResult], Path | None]:
    """
    Формирует итоговый протокол: ResultWithClubNames, ResultForSegmentDetails,
    JudgesScores для каждой выбранной пары в пользовательском порядке.
    """
    if not (include_result or include_segment_details or include_judges_scores):
        raise ValueError("Выберите хотя бы один блок итогового протокола.")

    if protocol_renderer not in {"rpt", "python"}:
        raise ValueError("protocol_renderer должен быть 'rpt' или 'python'.")

    snapshot = load_calcfs_folder(base_dir)
    title_overrides = category_title_overrides if category_title_overrides is not None else build_default_title_overrides(snapshot)
    rpt_paths = rpt_template_paths or {}
    results: list[UnitResult] = []
    temp_dir = Path(tempfile.mkdtemp(prefix="calcfs_protocol_pdf_"))
    merged: Path | None = None
    ok_parts: list[Path] = []

    try:
        if protocol_renderer == "rpt":
            category_groups: dict[object, list[tuple[object, object, str]]] = {}
            category_order: list[object] = []
            for cat_id, scp_id, label in selected:
                if cat_id not in category_groups:
                    category_groups[cat_id] = []
                    category_order.append(cat_id)
                category_groups[cat_id].append((cat_id, scp_id, label))

            total_reports = sum(
                (1 if include_result else 0)
                + len(category_groups[cat_id]) * ((1 if include_segment_details else 0) + (1 if include_judges_scores else 0))
                for cat_id in category_order
            )
            completed_reports = 0
            if progress_callback:
                progress_callback({"stage": "start", "completed": completed_reports, "total": total_reports})

            part_idx = 1
            for cat_idx, cat_id in enumerate(category_order, start=1):
                group = category_groups[cat_id]
                group_created: list[Path] = []
                failed = False
                message = "OK"
                try:
                    if include_result:
                        # ResultWithClubNames is category-level: for multi-segment categories it shows the final sum.
                        final_scp_id = _final_scp_id_for_category(snapshot, cat_id, group[-1][1])
                        path = temp_dir / f"protocol_{cat_idx:04d}_{part_idx:04d}_result_rpt.pdf"
                        part_idx += 1
                        if progress_callback:
                            progress_callback({"stage": "report_start", "completed": completed_reports, "total": total_reports, "cat_id": cat_id, "report": RESULT_WITH_CLUB_NAMES.title})
                        export_crystal_report_pdf(
                            base_dir=base_dir,
                            report_spec=RESULT_WITH_CLUB_NAMES,
                            output_pdf=path,
                            cat_id=cat_id,
                            scp_id=final_scp_id,
                            category_title_overrides=title_overrides,
                            rpt_path_override=rpt_paths.get("result"),
                        )
                        completed_reports += 1
                        if progress_callback:
                            progress_callback({"stage": "report_done", "completed": completed_reports, "total": total_reports, "cat_id": cat_id, "report": RESULT_WITH_CLUB_NAMES.title})
                        group_created.append(path)
                    for _, scp_id, _ in group:
                        if include_segment_details:
                            path = temp_dir / f"protocol_{cat_idx:04d}_{part_idx:04d}_segment_details_rpt.pdf"
                            part_idx += 1
                            if progress_callback:
                                progress_callback({"stage": "report_start", "completed": completed_reports, "total": total_reports, "cat_id": cat_id, "scp_id": scp_id, "report": RESULT_FOR_SEGMENT_DETAILS.title})
                            export_crystal_report_pdf(
                                base_dir=base_dir,
                                report_spec=RESULT_FOR_SEGMENT_DETAILS,
                                output_pdf=path,
                                cat_id=cat_id,
                                scp_id=scp_id,
                                category_title_overrides=title_overrides,
                                rpt_path_override=rpt_paths.get("segment_details"),
                            )
                            completed_reports += 1
                            if progress_callback:
                                progress_callback({"stage": "report_done", "completed": completed_reports, "total": total_reports, "cat_id": cat_id, "scp_id": scp_id, "report": RESULT_FOR_SEGMENT_DETAILS.title})
                            group_created.append(path)
                        if include_judges_scores:
                            path = temp_dir / f"protocol_{cat_idx:04d}_{part_idx:04d}_judges_scores_rpt.pdf"
                            part_idx += 1
                            if progress_callback:
                                progress_callback({"stage": "report_start", "completed": completed_reports, "total": total_reports, "cat_id": cat_id, "scp_id": scp_id, "report": JUDGES_SCORES.title})
                            export_crystal_report_pdf(
                                base_dir=base_dir,
                                report_spec=JUDGES_SCORES,
                                output_pdf=path,
                                cat_id=cat_id,
                                scp_id=scp_id,
                                category_title_overrides=title_overrides,
                                rpt_path_override=rpt_paths.get("judges_scores"),
                            )
                            completed_reports += 1
                            if progress_callback:
                                progress_callback({"stage": "report_done", "completed": completed_reports, "total": total_reports, "cat_id": cat_id, "scp_id": scp_id, "report": JUDGES_SCORES.title})
                            group_created.append(path)
                    ok_parts.extend(group_created)
                    if progress_callback:
                        progress_callback({"stage": "category_done", "completed": completed_reports, "total": total_reports, "cat_id": cat_id})
                except Exception as e:
                    failed = True
                    message = str(e)
                    logger.exception("Ошибка итогового протокола для категории %s", cat_id)
                    if progress_callback:
                        progress_callback({"stage": "failed", "completed": completed_reports, "total": total_reports, "cat_id": cat_id, "message": message})

                for row_cat_id, row_scp_id, row_label in group:
                    results.append(
                        UnitResult(
                            cat_id=row_cat_id,
                            scp_id=row_scp_id,
                            label=row_label,
                            ok=not failed,
                            message=message,
                            pdf_path=group_created[-1] if group_created and not failed else None,
                        )
                    )
        else:
            for idx, (cat_id, scp_id, label) in enumerate(selected, start=1):
                try:
                    created: list[Path] = []
                    bundle = build_protocol_segment(snapshot, cat_id, scp_id)
                    if include_result:
                        path = temp_dir / f"protocol_{idx:04d}_01_result.pdf"
                        render_result_with_club_names_pdf(bundle, path)
                        created.append(path)
                    if include_segment_details:
                        path = temp_dir / f"protocol_{idx:04d}_02_segment_details.pdf"
                        render_result_for_segment_details_pdf(bundle, path)
                        created.append(path)
                    if include_judges_scores:
                        path = temp_dir / f"protocol_{idx:04d}_03_judges_scores.pdf"
                        render_judges_scores_pdf(bundle, path)
                        created.append(path)
                    ok_parts.extend(created)
                    results.append(UnitResult(cat_id=cat_id, scp_id=scp_id, label=label, ok=True, message="OK", pdf_path=created[-1] if created else None))
                except Exception as e:
                    logger.exception("Ошибка итогового протокола для %s", label)
                    results.append(UnitResult(cat_id=cat_id, scp_id=scp_id, label=label, ok=False, message=str(e), pdf_path=None))

        if ok_parts:
            merged = merge_pdf_files(ok_parts, output_pdf)
        else:
            logger.error("Ни один фрагмент итогового протокола не создан.")
    finally:
        if keep_temp:
            logger.info("Временные PDF итогового протокола сохранены в %s", temp_dir)
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
