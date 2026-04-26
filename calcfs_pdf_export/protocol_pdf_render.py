from __future__ import annotations

from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from calcfs_pdf_export.pdf_render import _register_unicode_fonts
from calcfs_pdf_export.protocol_report import (
    ElementScore,
    ProtocolParticipant,
    ProtocolSegmentBundle,
    format_int,
    format_score,
)


def _font_names() -> tuple[str, str]:
    return _register_unicode_fonts()


def _styles():
    font, bold = _font_names()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ProtocolTitle", parent=styles["Title"], fontName=bold, fontSize=13, leading=16, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="ProtocolSubtitle", parent=styles["Normal"], fontName=font, fontSize=9, leading=11, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="ProtocolNormal", parent=styles["Normal"], fontName=font, fontSize=7.5, leading=9))
    styles.add(ParagraphStyle(name="ProtocolSmall", parent=styles["Normal"], fontName=font, fontSize=6.2, leading=7.2))
    styles.add(ParagraphStyle(name="ProtocolCell", parent=styles["Normal"], fontName=font, fontSize=6.8, leading=8.0, alignment=TA_LEFT))
    return styles


def _p(text: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), style)


def _doc(path: str | Path, *, pagesize=A4) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        str(path),
        pagesize=pagesize,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )


def _header(bundle: ProtocolSegmentBundle, title: str, styles) -> list:
    parts = [
        Paragraph(bundle.event_name, styles["ProtocolTitle"]),
        Paragraph(bundle.event_place_line, styles["ProtocolSubtitle"]),
        Paragraph(bundle.event_date_line, styles["ProtocolSubtitle"]),
        Spacer(1, 3 * mm),
        Paragraph(title, styles["ProtocolTitle"]),
        Paragraph(f"{bundle.category_name} - {bundle.segment_name}", styles["ProtocolSubtitle"]),
        Spacer(1, 4 * mm),
    ]
    return parts


def _base_table_style(*, header_rows: int = 1, font_size: float = 6.8) -> TableStyle:
    font, bold = _font_names()
    return TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("FONTNAME", (0, 0), (-1, header_rows - 1), bold),
            ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("LEADING", (0, 0), (-1, -1), font_size + 1.2),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("BACKGROUND", (0, 0), (-1, header_rows - 1), colors.HexColor("#eeeeee")),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]
    )


def render_result_with_club_names_pdf(bundle: ProtocolSegmentBundle, output_pdf: str | Path) -> Path:
    styles = _styles()
    story = _header(bundle, "Result With Club Names", styles)
    data = [[
        "Place",
        "Start",
        "Name",
        "Club",
        "Rank",
        "Birth date",
        "Total",
        "TES",
        "PCS",
        "Ded.",
    ]]
    for p in bundle.participants:
        data.append(
            [
                format_int(p.place),
                format_int(p.start_num),
                _p(p.name, styles["ProtocolCell"]),
                _p(p.club, styles["ProtocolCell"]),
                p.active_rank,
                p.birth_date,
                format_score(p.total_score),
                format_score(p.tes),
                format_score(p.pcs),
                format_score(p.deductions),
            ]
        )
    table = Table(data, repeatRows=1, colWidths=[12 * mm, 12 * mm, 48 * mm, 45 * mm, 18 * mm, 22 * mm, 18 * mm, 16 * mm, 16 * mm, 14 * mm])
    table.setStyle(_base_table_style(font_size=7.0))
    table.setStyle(TableStyle([("ALIGN", (2, 1), (3, -1), "LEFT")]))
    story.append(table)
    _doc(output_pdf).build(story)
    return Path(output_pdf)


def render_result_for_segment_details_pdf(bundle: ProtocolSegmentBundle, output_pdf: str | Path) -> Path:
    styles = _styles()
    story = _header(bundle, "Result For Segment Details", styles)
    component_headers = bundle.component_labels[:8]
    data = [[
        "Place",
        "Name",
        "Club",
        "Total",
        "TES",
        "PCS",
        *component_headers,
        "Ded.",
    ]]
    for p in bundle.participants:
        comp_by_label = {
            (c.short_name or c.name): c.result
            for c in p.component_scores
        }
        data.append(
            [
                format_int(p.place),
                _p(p.name, styles["ProtocolSmall"]),
                _p(p.club, styles["ProtocolSmall"]),
                format_score(p.total_score),
                format_score(p.tes),
                format_score(p.pcs),
                *[format_score(comp_by_label.get(label)) for label in component_headers],
                format_score(p.deductions),
            ]
        )
    page_width = landscape(A4)[0] - 20 * mm
    fixed = [11 * mm, 40 * mm, 42 * mm, 16 * mm, 15 * mm, 15 * mm, 14 * mm]
    comp_width = max(10 * mm, (page_width - sum(fixed)) / max(1, len(component_headers)))
    col_widths = [11 * mm, 40 * mm, 42 * mm, 16 * mm, 15 * mm, 15 * mm, *([comp_width] * len(component_headers)), 14 * mm]
    table = Table(data, repeatRows=1, colWidths=col_widths)
    table.setStyle(_base_table_style(font_size=6.2))
    table.setStyle(TableStyle([("ALIGN", (1, 1), (2, -1), "LEFT")]))
    story.append(table)
    _doc(output_pdf, pagesize=landscape(A4)).build(story)
    return Path(output_pdf)


def _element_rows(elements: Iterable[ElementScore], judge_labels: list[str]) -> list[list[object]]:
    data: list[list[object]] = [["#", "Element", "Info", "Base", "GOE", *judge_labels, "Result"]]
    for element in elements:
        marks = element.judge_marks[: len(judge_labels)]
        marks += [""] * (len(judge_labels) - len(marks))
        data.append(
            [
                str(element.number),
                element.code,
                element.info,
                format_score(element.base_value),
                format_score(element.goe, signed=True),
                *marks,
                format_score(element.result),
            ]
        )
    return data


def _participant_score_block(participant: ProtocolParticipant, judge_labels: list[str], styles) -> KeepTogether:
    story: list = [
        Paragraph(
            f"{format_int(participant.place)}. {participant.name}    {participant.club}    Total: {format_score(participant.total_score)}",
            styles["ProtocolSubtitle"],
        ),
        Spacer(1, 1.5 * mm),
    ]
    element_data = _element_rows(participant.element_scores, judge_labels)
    element_widths = [7 * mm, 26 * mm, 10 * mm, 12 * mm, 12 * mm, *([8 * mm] * len(judge_labels)), 13 * mm]
    element_table = Table(element_data, repeatRows=1, colWidths=element_widths)
    element_table.setStyle(_base_table_style(font_size=5.8))
    story.append(element_table)
    if participant.component_scores:
        story.append(Spacer(1, 2 * mm))
        component_data = [["Program Component", "Factor", *judge_labels, "Score"]]
        for component in participant.component_scores:
            marks = component.judge_marks[: len(judge_labels)]
            marks += [""] * (len(judge_labels) - len(marks))
            component_data.append(
                [
                    component.name,
                    format_score(component.factor),
                    *marks,
                    format_score(component.result),
                ]
            )
        component_widths = [42 * mm, 13 * mm, *([8 * mm] * len(judge_labels)), 13 * mm]
        component_table = Table(component_data, repeatRows=1, colWidths=component_widths)
        component_table.setStyle(_base_table_style(font_size=5.8))
        component_table.setStyle(TableStyle([("ALIGN", (0, 1), (0, -1), "LEFT")]))
        story.append(component_table)
    if participant.deductions:
        story.append(Paragraph(f"Deductions: {format_score(participant.deductions)}", styles["ProtocolSmall"]))
    story.append(Spacer(1, 4 * mm))
    return KeepTogether(story)


def render_judges_scores_pdf(bundle: ProtocolSegmentBundle, output_pdf: str | Path) -> Path:
    styles = _styles()
    story = _header(bundle, "Judges Scores", styles)
    judge_labels = bundle.judge_labels[:12]
    for idx, participant in enumerate(bundle.participants):
        if idx:
            story.append(Spacer(1, 2 * mm))
        story.append(_participant_score_block(participant, judge_labels, styles))
        if idx and idx % 2 == 0:
            story.append(PageBreak())
    _doc(output_pdf, pagesize=landscape(A4)).build(story)
    return Path(output_pdf)
