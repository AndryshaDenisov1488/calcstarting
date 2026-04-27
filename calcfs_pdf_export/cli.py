"""
Запуск: python -m calcfs_pdf_export.cli --base "C:\\ISUCalcFS\\pm 2026" --out out.pdf --all
или перечислить пары: --pair cat_id:scp_id (повторяемо).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from calcfs_pdf_export.calcfs_store import discover_cat_scp_pairs, load_calcfs_folder
from calcfs_pdf_export.evsk_titles import build_default_title_overrides
from calcfs_pdf_export.ids import normalize_id
from calcfs_pdf_export.export_pipeline import export_protocol_bundle, export_starting_order_bundle

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"


def main() -> int:
    parser = argparse.ArgumentParser(description="Экспорт стартового порядка или итогового протокола (CalcFS DBF) в PDF без GUI.")
    parser.add_argument("--base", required=True, type=Path, help="Папка с PRF.DBF, PAR.DBF, …")
    parser.add_argument("--out", required=True, type=Path, help="Итоговый объединённый PDF")
    parser.add_argument("--all", action="store_true", help="Все найденные пары категория×сегмент")
    parser.add_argument(
        "--pair",
        action="append",
        default=[],
        metavar="CAT:SCP",
        help="Пара ID (повторить для нескольких). Пример: --pair 1:5 --pair 1:6",
    )
    parser.add_argument("--keep-temp", action="store_true", help="Не удалять временные part_*.pdf")
    parser.add_argument("--protocol", action="store_true", help="Сформировать итоговый протокол вместо стартового листа")
    parser.add_argument(
        "--protocol-renderer",
        choices=["rpt", "python"],
        default="rpt",
        help="Рендер итогового протокола: штатные Crystal RPT или Python/reportlab fallback",
    )
    parser.add_argument("--no-result", action="store_true", help="В protocol mode не добавлять ResultWithClubNames")
    parser.add_argument("--no-segment-details", action="store_true", help="В protocol mode не добавлять ResultForSegmentDetails")
    parser.add_argument("--no-judges-scores", action="store_true", help="В protocol mode не добавлять JudgesScores")
    parser.add_argument("--result-rpt", type=Path, help="Путь к RPT-шаблону для ResultWithClubNames")
    parser.add_argument("--segment-details-rpt", type=Path, help="Путь к RPT-шаблону для ResultForSegmentDetails")
    parser.add_argument("--judges-scores-rpt", type=Path, help="Путь к RPT-шаблону для JudgesScores")
    parser.add_argument(
        "--no-protocol-discipline",
        action="store_true",
        help="Не добавлять вид ФК в официальный заголовок итогового протокола",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format=_LOG_FORMAT)

    snap = load_calcfs_folder(args.base)
    catalog = discover_cat_scp_pairs(snap)
    by_label = {(normalize_id(c), normalize_id(s)): (c, s, lbl) for c, s, lbl in catalog}

    if args.all:
        selected = [(c, s, lbl) for c, s, lbl in catalog]
    else:
        selected = []
        for raw in args.pair:
            if ":" not in raw:
                logging.error("Неверный --pair %r, ожидается CAT:SCP", raw)
                return 2
            a, b = raw.split(":", 1)
            try:
                cat_id = normalize_id(int(a.strip()))
                scp_id = normalize_id(int(b.strip()))
            except ValueError:
                cat_id, scp_id = normalize_id(a.strip()), normalize_id(b.strip())
            key = (cat_id, scp_id)
            if key not in by_label:
                logging.error("Пара не найдена в базе: %s:%s", cat_id, scp_id)
                return 2
            selected.append(by_label[key])

    if not selected:
        logging.error("Укажите --all или хотя бы одну --pair CAT:SCP")
        return 2

    if args.protocol:
        rpt_template_paths = {
            key: path
            for key, path in {
                "result": args.result_rpt,
                "segment_details": args.segment_details_rpt,
                "judges_scores": args.judges_scores_rpt,
            }.items()
            if path is not None
        }
        results, merged = export_protocol_bundle(
            args.base,
            selected,
            args.out,
            keep_temp=args.keep_temp,
            include_result=not args.no_result,
            include_segment_details=not args.no_segment_details,
            include_judges_scores=not args.no_judges_scores,
            protocol_renderer=args.protocol_renderer,
            category_title_overrides=build_default_title_overrides(
                snap,
                include_discipline=not args.no_protocol_discipline,
            ),
            rpt_template_paths=rpt_template_paths,
        )
    else:
        results, merged = export_starting_order_bundle(
            args.base,
            selected,
            args.out,
            keep_temp=args.keep_temp,
        )
    for r in results:
        logging.info("%s %s: %s", "OK" if r.ok else "FAIL", r.label, r.message)
    if not merged:
        return 1
    logging.info("Итог: %s", merged)
    return 0


def run_cli() -> None:
    """Точка входа для setuptools console_scripts."""
    raise SystemExit(main())


if __name__ == "__main__":
    run_cli()
