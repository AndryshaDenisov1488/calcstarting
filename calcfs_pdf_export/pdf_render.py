from __future__ import annotations

import html
import logging
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from calcfs_pdf_export.starting_order_report import StartingOrderSheet

logger = logging.getLogger(__name__)
_FONT_REGULAR = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"


def _norm_text(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _category_heading_markup(category_name: str) -> str:
    """ReportLab Paragraph markup: one visual line per source line (combined sheets use \\n)."""
    lines = [ln.strip() for ln in (category_name or "").splitlines() if ln.strip()]
    if not lines:
        return _esc((category_name or "").strip())
    return "<br/>".join(_esc(ln) for ln in lines)


def _short_category_label(category_name: str) -> str:
    text = (category_name or "").strip()
    if not text:
        return ""
    if "." in text:
        return text.split(".", 1)[0].strip()
    return text


def _register_unicode_fonts() -> tuple[str, str]:
    candidates: list[tuple[Path, Path | None]] = [
        (Path(r"C:\Windows\Fonts\arial.ttf"), Path(r"C:\Windows\Fonts\arialbd.ttf")),
        (Path(r"C:\Windows\Fonts\DejaVuSans.ttf"), Path(r"C:\Windows\Fonts\DejaVuSans-Bold.ttf")),
    ]
    for regular_path, bold_path in candidates:
        if not regular_path.is_file():
            continue
        try:
            regular_name = f"CalcFS_{regular_path.stem}"
            if regular_name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(regular_name, str(regular_path)))
            bold_name = regular_name
            if bold_path and bold_path.is_file():
                bold_name = f"{regular_name}_Bold"
                if bold_name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
            logger.debug("Используем шрифт PDF: %s", regular_name)
            return regular_name, bold_name
        except Exception:
            continue
    return _FONT_REGULAR, _FONT_BOLD


def render_starting_order_pdf(
    out_path: Path,
    sheet: StartingOrderSheet,
    *,
    include_active_rank: bool = True,
    include_birth_date: bool = True,
    include_coach: bool = False,
    pre_warmup_texts: dict[int, list[str]] | None = None,
    post_warmup_texts: dict[int, list[str]] | None = None,
) -> None:
    font_regular, font_bold = _register_unicode_fonts()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title="Starting order",
    )
    styles = getSampleStyleSheet()
    styles["Title"].fontName = font_bold
    styles["Heading2"].fontName = font_bold
    styles["Heading3"].fontName = font_bold
    styles["Normal"].fontName = font_regular
    styles["Normal"].fontSize = 9
    styles["Normal"].leading = 11
    styles["Heading2"].alignment = 1
    styles["Heading3"].alignment = 1
    warmup_style = styles["Normal"].clone("WarmupHeader")
    warmup_style.fontName = font_bold
    warmup_style.alignment = 1
    warmup_style.wordWrap = "CJK"
    hdr_tbl = styles["Normal"].clone("TblHdr")
    hdr_tbl.fontName = font_bold
    hdr_tbl.fontSize = 9
    hdr_tbl.leading = 11
    hdr_tbl.wordWrap = "CJK"
    hdr_c = hdr_tbl.clone("TblHdrC")
    hdr_c.alignment = TA_CENTER
    hdr_l = hdr_tbl.clone("TblHdrL")
    hdr_l.alignment = TA_LEFT
    cell_tbl = styles["Normal"].clone("TblCell")
    cell_tbl.fontName = font_regular
    cell_tbl.fontSize = 9
    cell_tbl.leading = 11
    cell_tbl.wordWrap = "CJK"
    cell_l = cell_tbl.clone("TblCellL")
    cell_l.alignment = TA_LEFT
    cell_c = cell_tbl.clone("TblCellC")
    cell_c.alignment = TA_CENTER
    story: list = []

    story.append(Paragraph(_esc(sheet.event_name), styles["Title"]))
    story.append(Spacer(1, 0.3 * cm))
    if sheet.event_place_line or sheet.event_date_line:
        # Ячейки Table — обычный текст, не Paragraph/XML; _esc давал видимые &quot;
        meta_data = [[_plain_text(sheet.event_place_line), _plain_text(sheet.event_date_line)]]
        meta_tbl = Table(meta_data, colWidths=[0.68 * doc.width, 0.32 * doc.width])
        meta_tbl.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), font_regular),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (0, 0), (0, 0), "LEFT"),
                    ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(meta_tbl)
        story.append(Spacer(1, 0.15 * cm))
    line2 = _category_heading_markup(sheet.category_name)
    story.append(Paragraph(f"<b>{line2}</b>", styles["Heading2"]))
    story.append(Paragraph("СТАРТОВЫЙ ЛИСТ", styles["Heading3"]))
    story.append(Spacer(1, 0.4 * cm))

    if not sheet.rows:
        story.append(Paragraph("<i>Нет записей для выбранной категории и сегмента.</i>", styles["Normal"]))
        doc.build(story)
        return

    coach_col: int | None = None
    _ci = 2
    if include_active_rank:
        _ci += 1
    if include_birth_date:
        _ci += 1
    if include_coach:
        coach_col = _ci
    header_cells: list = [
        Paragraph(_esc("Старт.") + "<br/>" + _esc("номер"), hdr_c),
        Paragraph(_esc("ФИО"), hdr_l),
    ]
    if include_active_rank:
        header_cells.append(Paragraph(_esc("Действующий") + "<br/>" + _esc("разряд"), hdr_c))
    if include_birth_date:
        header_cells.append(Paragraph(_esc("Дата рождения"), hdr_c))
    if include_coach:
        header_cells.append(Paragraph(_esc("Тренер"), hdr_l))
    data: list[list] = [header_cells]
    header_like_rows: list[int] = []
    warmup_block_ranges: list[tuple[int, int]] = []
    block_start: int | None = None
    last_group = -1
    col_count = len(header_cells)
    pre_warmup_texts = pre_warmup_texts or {}
    post_warmup_texts = post_warmup_texts or {}
    sorted_rows = list(sheet.rows)
    warmup_categories: dict[int, list[str]] = {}
    for r in sorted_rows:
        bucket = warmup_categories.setdefault(r.warmup_group, [])
        short_cat = _short_category_label(r.category_name)
        if short_cat and short_cat not in bucket:
            bucket.append(short_cat)
    for r in sorted_rows:
        if r.warmup_group != last_group:
            if last_group != -1:
                for note in post_warmup_texts.get(last_group, []):
                    note_row = [""] * col_count
                    note_row[0] = Paragraph(_esc(str(note).strip()), warmup_style)
                    data.append(note_row)
                    header_like_rows.append(len(data) - 1)
                if block_start is not None:
                    warmup_block_ranges.append((block_start, len(data) - 1))
            block_start = len(data)
            for note in pre_warmup_texts.get(r.warmup_group, []):
                note_row = [""] * col_count
                note_row[0] = Paragraph(_esc(str(note).strip()), warmup_style)
                data.append(note_row)
                header_like_rows.append(len(data) - 1)
            warmup_row = [""] * col_count
            cats = warmup_categories.get(r.warmup_group, [])
            cat_suffix = f" ({' + '.join(cats)})" if cats else ""
            warmup_row[0] = Paragraph(_esc(f"Разминка {r.warmup_group}{cat_suffix}"), warmup_style)
            data.append(warmup_row)
            header_like_rows.append(len(data) - 1)
            last_group = r.warmup_group
        school_line = r.school if r.school and r.school != "—" else r.club
        if _norm_text(school_line) == _norm_text(r.name):
            school_line = r.club if r.club and _norm_text(r.club) != _norm_text(r.name) else "—"
        fio_para = Paragraph(
            _esc(_plain_text(r.name)) + "<br/>" + _esc(_plain_text(school_line)),
            cell_l,
        )
        row = [
            Paragraph(_esc(str(r.start_num)), cell_c),
            fio_para,
        ]
        if include_active_rank:
            row.append(_p(str(r.active_rank), cell_c))
        if include_birth_date:
            row.append(_p(str(r.birth_date), cell_c))
        if include_coach:
            row.append(_p(str(r.coach_name), cell_l))
        data.append(row)
    if last_group != -1:
        for note in post_warmup_texts.get(last_group, []):
            note_row = [""] * col_count
            note_row[0] = Paragraph(_esc(str(note).strip()), warmup_style)
            data.append(note_row)
            header_like_rows.append(len(data) - 1)
        if block_start is not None:
            warmup_block_ranges.append((block_start, len(data) - 1))

    extra_fracs: list[float] = []
    if include_active_rank:
        extra_fracs.append(0.15)
    if include_birth_date:
        extra_fracs.append(0.15)
    if include_coach:
        extra_fracs.append(0.20)
    name_frac = 1.0 - 0.11 - sum(extra_fracs)
    name_frac = max(0.22, name_frac)
    col_widths = [0.11 * doc.width, name_frac * doc.width]
    col_widths.extend(f * doc.width for f in extra_fracs)

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (0, 0), (0, -1), "CENTER"),
                    ("ALIGN", (1, 1), (1, -1), "LEFT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9f9")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    ncols = len(header_cells)
    if ncols > 2:
        tbl.setStyle(TableStyle([("ALIGN", (2, 1), (ncols - 1, -1), "CENTER")]))
    if coach_col is not None:
        tbl.setStyle(
            TableStyle(
                [
                    ("ALIGN", (coach_col, 0), (coach_col, 0), "LEFT"),
                    ("ALIGN", (coach_col, 1), (coach_col, -1), "LEFT"),
                ]
            )
        )
    for row_idx in header_like_rows:
        tbl.setStyle(
            TableStyle(
                [
                    ("SPAN", (0, row_idx), (ncols - 1, row_idx)),
                    ("ALIGN", (0, row_idx), (ncols - 1, row_idx), "CENTER"),
                    ("BACKGROUND", (0, row_idx), (ncols - 1, row_idx), colors.HexColor("#f1f1f1")),
                    ("TOPPADDING", (0, row_idx), (ncols - 1, row_idx), 4),
                    ("BOTTOMPADDING", (0, row_idx), (ncols - 1, row_idx), 4),
                ]
            )
        )
    for start_row, end_row in warmup_block_ranges:
        tbl.setStyle(
            TableStyle(
                [
                    ("NOSPLIT", (0, start_row), (ncols - 1, end_row)),
                ]
            )
        )
    story.append(tbl)
    doc.build(story)
    logger.info("PDF записан: %s", out_path)


def _esc(text: str) -> str:
    text = html.unescape(str(text))
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _plain_text(text: str) -> str:
    """Текст для Table/Label без XML-экранирования (сущности из БД → символы)."""
    return html.unescape(str(text or ""))


def _p(text: str, style) -> Paragraph:
    """Ячейка таблицы: перенос слов по ширине колонки (ReportLab Paragraph)."""
    return Paragraph(_esc(_plain_text(text)), style)
