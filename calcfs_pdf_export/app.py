from __future__ import annotations

import json
import logging
import math
import re
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QTextOption
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from calcfs_pdf_export import __version__
from calcfs_pdf_export.calcfs_store import discover_cat_scp_pairs, event_date_range, event_title, load_calcfs_folder
from calcfs_pdf_export.dbf_utils import rec_get
from calcfs_pdf_export.evsk_titles import cat_key, category_by_id, official_title_for_category, rule_for_category
from calcfs_pdf_export.export_pipeline import export_protocol_bundle, export_starting_order_bundle
from calcfs_pdf_export.ids import same_id
from calcfs_pdf_export.rpt_export import JUDGES_SCORES, RESULT_FOR_SEGMENT_DETAILS, RESULT_WITH_CLUB_NAMES, RPT_DIR
from calcfs_pdf_export.starting_order_report import build_starting_order_rows

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


class _LabelToggleCheck(QLabel):
    """Подпись с переносом строк; клик переключает связанный QCheckBox."""

    def __init__(self, text: str, cb: QCheckBox) -> None:
        super().__init__(text)
        self._cb = cb
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._cb.toggle()
        super().mousePressEvent(event)


def _checkbox_with_wrapped_label(text: str) -> tuple[QWidget, QCheckBox]:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    cb = QCheckBox()
    lbl = _LabelToggleCheck(text, cb)
    lay.addWidget(cb, 0, Qt.AlignTop)
    lay.addWidget(lbl, 1)
    return row, cb


def _rpt_picker_row(label: str, default_path: Path, handler) -> tuple[QWidget, QLineEdit]:
    row = QWidget()
    lay = QVBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(3)
    lbl = QLabel(label)
    lbl.setWordWrap(True)
    edit_row = QWidget()
    edit_lay = QHBoxLayout(edit_row)
    edit_lay.setContentsMargins(0, 0, 0, 0)
    edit_lay.setSpacing(4)
    edit = QLineEdit(str(default_path))
    edit.setMinimumWidth(0)
    edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    btn = QPushButton("Обзор…")
    btn.setMinimumWidth(0)
    btn.clicked.connect(handler)
    edit_lay.addWidget(edit, 1)
    edit_lay.addWidget(btn, 0)
    lay.addWidget(lbl)
    lay.addWidget(edit_row)
    return row, edit


def _setup_logging(log_widget: QTextEdit) -> None:
    log_widget.setReadOnly(True)

    class QtHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            msg = self.format(record)
            log_widget.append(msg)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    qt_handler = QtHandler()
    qt_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(qt_handler)

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(stream)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"CalcFS PDF Export v{__version__}")
        self.resize(1680, 920)

        self._base_dir: Path | None = None
        self._pairs: list[tuple[object, object, str]] = []
        self._merge_groups: dict[tuple[object, object], int] = {}
        self._group_order: dict[int, list[tuple[object, object, str]]] = {}
        self._group_warmup_size: dict[int, int] = {}
        self._group_insert_texts: dict[int, list[tuple[str, int, str]]] = {}
        self._snapshot = None
        self._pair_participant_counts: dict[tuple[object, object], int] = {}
        self._category_age_selection: dict[str, list[str]] = {}
        self._protocol_age_checkboxes: list[QCheckBox] = []
        self._protocol_rpt_edits: dict[str, QLineEdit] = {}

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        header = QGroupBox("Источник данных")
        header_grid = QGridLayout(header)
        btn_dir = QPushButton("Выбрать папку соревнования…")
        btn_dir.clicked.connect(self.handle_pick_dir)
        self.lbl_dir = QLabel("Папка DBF: не выбрана")
        self.lbl_dir.setWordWrap(True)
        btn_scan = QPushButton("Обновить список")
        btn_scan.clicked.connect(self.handle_scan)
        header_grid.addWidget(btn_dir, 0, 0)
        header_grid.addWidget(self.lbl_dir, 0, 1, 1, 3)
        header_grid.addWidget(btn_scan, 1, 0)
        root.addWidget(header, 0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        left_panel = QWidget()
        left_panel.setMinimumWidth(880)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        categories_box = QGroupBox("Категории и сегменты")
        categories_box.setMinimumWidth(400)
        categories_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        categories_layout = QVBoxLayout(categories_box)
        self.lbl_list_title = QLabel("Доступные категория / сегмент (отметьте несколько):")
        self.lbl_list_title.setWordWrap(True)
        self.lbl_list_title.setMinimumWidth(0)
        categories_layout.addWidget(self.lbl_list_title)
        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(160)
        self.list_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.list_widget.setWordWrap(True)
        self.list_widget.setUniformItemSizes(False)
        self.list_widget.setSpacing(2)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget.setDragDropOverwriteMode(False)
        self.list_widget.setDropIndicatorShown(True)
        self.list_widget.itemClicked.connect(self._toggle_category_item_check)
        self.list_widget.itemSelectionChanged.connect(self._update_selected_stats_label)
        self.list_widget.itemSelectionChanged.connect(self._update_protocol_title_editor)
        categories_layout.addWidget(self.list_widget, 1)
        row_order = QGridLayout()
        row_order.setHorizontalSpacing(6)
        row_order.setVerticalSpacing(6)
        lbl_row = QLabel("Порядок строк:")
        row_order.addWidget(lbl_row, 0, 0, 1, 2)
        btn_check_all = QPushButton("Выбрать все")
        btn_check_all.clicked.connect(self.handle_check_all_categories)
        row_order.addWidget(btn_check_all, 1, 0)
        btn_uncheck_all = QPushButton("Снять все")
        btn_uncheck_all.clicked.connect(self.handle_uncheck_all_categories)
        row_order.addWidget(btn_uncheck_all, 1, 1)
        order_btns = [
            ("Вверх", self.handle_move_up),
            ("Вниз", self.handle_move_down),
            ("В начало", self.handle_move_top),
            ("В конец", self.handle_move_bottom),
        ]
        for i, (text, handler) in enumerate(order_btns):
            b = QPushButton(text)
            b.clicked.connect(handler)
            row_order.addWidget(b, 2 + i // 2, i % 2)
        categories_layout.addLayout(row_order)

        groups_box = QGroupBox("Порядок внутри группы склейки")
        groups_box.setMinimumWidth(380)
        groups_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        groups_layout = QVBoxLayout(groups_box)
        self.tabs_groups = QTabWidget()
        self.tabs_groups.setMinimumHeight(80)
        self.tabs_groups.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        groups_layout.addWidget(self.tabs_groups)

        # Рядом: одинаковая верхняя линия и полная высота окна для обоих блоков (нижние кнопки не «уезжают»)
        left_main_splitter = QSplitter(Qt.Horizontal)
        left_main_splitter.setChildrenCollapsible(False)
        left_main_splitter.addWidget(categories_box)
        left_main_splitter.addWidget(groups_box)
        left_main_splitter.setStretchFactor(0, 1)
        left_main_splitter.setStretchFactor(1, 1)
        left_main_splitter.setSizes([700, 620])
        left_layout.addWidget(left_main_splitter, 1)

        right_panel = QWidget()
        right_panel.setMinimumWidth(400)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        options_box = QGroupBox("Параметры формирования")
        options_layout = QVBoxLayout(options_box)
        w1, self.chk_combine_sheet = _checkbox_with_wrapped_label(
            "Объединить выбранные категории в один общий стартовый лист"
        )
        w2, self.chk_regroup_warmup = _checkbox_with_wrapped_label(
            "Пересобрать разминки для объединенного листа"
        )
        self.chk_regroup_warmup.setChecked(True)
        w3, self.chk_include_rank = _checkbox_with_wrapped_label("Добавлять колонку «Действующий разряд»")
        self.chk_include_rank.setChecked(True)
        w4, self.chk_include_birth = _checkbox_with_wrapped_label("Добавлять колонку «Дата рождения»")
        self.chk_include_birth.setChecked(True)
        w5, self.chk_include_coach = _checkbox_with_wrapped_label("Добавлять колонку «Тренер» (Coach Name)")
        self.chk_include_coach.setChecked(False)
        self.spn_warmup = QSpinBox()
        self.spn_warmup.setRange(1, 50)
        self.spn_warmup.setValue(6)
        self.spn_warmup.setPrefix("Участников в разминке: ")
        self.spn_warmup.setMinimumWidth(0)
        self.spn_warmup.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.spn_warmup.valueChanged.connect(self._update_group_stats_label)
        self.spn_merge_group = QSpinBox()
        self.spn_merge_group.setRange(1, 99)
        self.spn_merge_group.setValue(1)
        self.spn_merge_group.setPrefix("Группа склейки: ")
        self.spn_merge_group.setMinimumWidth(0)
        self.spn_merge_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        b_assign = QPushButton("Назначить группу выделенным")
        b_assign.setMinimumWidth(0)
        b_assign.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        b_assign.clicked.connect(self.handle_assign_group)
        self.btn_clear_group = QPushButton("Сбросить группы")
        self.btn_clear_group.setMinimumWidth(0)
        self.btn_clear_group.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.btn_clear_group.clicked.connect(self.handle_clear_groups)
        self.btn_save_layout = QPushButton("Запомнить разбиение")
        self.btn_save_layout.setMinimumWidth(0)
        self.btn_save_layout.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.btn_save_layout.clicked.connect(self.handle_save_layout)
        self.btn_export = QPushButton("Сформировать объединённый PDF…")
        self.btn_export.setMinimumWidth(0)
        self.btn_export.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.btn_export.clicked.connect(self.handle_export)
        self.btn_protocol_export = QPushButton("Сформировать итоговый протокол…")
        self.btn_protocol_export.setMinimumWidth(0)
        self.btn_protocol_export.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.btn_protocol_export.clicked.connect(self.handle_protocol_export)
        self.cmb_merge_from = QComboBox()
        self.cmb_merge_to = QComboBox()
        for cmb in (self.cmb_merge_from, self.cmb_merge_to):
            cmb.setMinimumWidth(0)
            cmb.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.btn_merge_groups = QPushButton("Объединить группу →")
        self.btn_merge_groups.setMinimumWidth(0)
        self.btn_merge_groups.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.btn_merge_groups.clicked.connect(self.handle_merge_groups)
        options_layout.addWidget(w1)
        options_layout.addWidget(w2)
        options_layout.addWidget(w3)
        options_layout.addWidget(w4)
        options_layout.addWidget(w5)
        # Вертикально на всю ширину колонки — при узкой правой панели ничего не режется
        spin_col = QVBoxLayout()
        spin_col.setSpacing(6)
        spin_col.addWidget(self.spn_warmup)
        spin_col.addWidget(self.spn_merge_group)
        spin_col.addWidget(b_assign)
        options_layout.addLayout(spin_col)
        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)
        for btn in (self.btn_clear_group, self.btn_save_layout, self.btn_export):
            btn_col.addWidget(btn)
        options_layout.addLayout(btn_col)
        merge_lbl = QLabel("Объединить группы склейки")
        merge_lbl.setWordWrap(True)
        merge_lbl.setMinimumWidth(0)
        options_layout.addWidget(merge_lbl)
        merge_col = QVBoxLayout()
        merge_col.setSpacing(6)
        merge_col.addWidget(self.cmb_merge_from)
        merge_col.addWidget(self.cmb_merge_to)
        merge_col.addWidget(self.btn_merge_groups)
        options_layout.addLayout(merge_col)

        top_right = QWidget()
        top_right.setMinimumWidth(320)
        top_right_layout = QVBoxLayout(top_right)
        top_right_layout.setContentsMargins(0, 0, 0, 0)
        top_right_layout.setSpacing(8)

        protocol_box = QGroupBox("Итоговый протокол")
        protocol_layout = QVBoxLayout(protocol_box)
        w_protocol_rpt, self.chk_protocol_use_rpt = _checkbox_with_wrapped_label(
            "Использовать штатные Crystal RPT из C:\\ISUCalcFS\\reports\\RpXiEn"
        )
        self.chk_protocol_use_rpt.setChecked(True)
        w_protocol_1, self.chk_protocol_result = _checkbox_with_wrapped_label("Окончательные места: ResultWithClubNames")
        w_protocol_2, self.chk_protocol_segment_details = _checkbox_with_wrapped_label("Горизонталка: ResultForSegmentDetails")
        w_protocol_3, self.chk_protocol_judges_scores = _checkbox_with_wrapped_label("Судейские оценки: JudgesScores")
        for cb in (self.chk_protocol_result, self.chk_protocol_segment_details, self.chk_protocol_judges_scores):
            cb.setChecked(True)
        protocol_layout.addWidget(w_protocol_rpt)
        protocol_layout.addWidget(w_protocol_1)
        protocol_layout.addWidget(w_protocol_2)
        protocol_layout.addWidget(w_protocol_3)
        rpt_box = QGroupBox("Шаблоны Crystal RPT")
        rpt_layout = QVBoxLayout(rpt_box)
        row_result, self.edt_rpt_result = _rpt_picker_row(
            "Окончательные места", RPT_DIR / RESULT_WITH_CLUB_NAMES.filename, lambda: self._pick_rpt_template("result")
        )
        row_details, self.edt_rpt_segment_details = _rpt_picker_row(
            "Горизонталки", RPT_DIR / RESULT_FOR_SEGMENT_DETAILS.filename, lambda: self._pick_rpt_template("segment_details")
        )
        row_judges, self.edt_rpt_judges_scores = _rpt_picker_row(
            "Судейские оценки", RPT_DIR / JUDGES_SCORES.filename, lambda: self._pick_rpt_template("judges_scores")
        )
        self._protocol_rpt_edits = {
            "result": self.edt_rpt_result,
            "segment_details": self.edt_rpt_segment_details,
            "judges_scores": self.edt_rpt_judges_scores,
        }
        for row in (row_result, row_details, row_judges):
            rpt_layout.addWidget(row)
        protocol_layout.addWidget(rpt_box)
        progress_box = QGroupBox("Ход формирования")
        progress_layout = QVBoxLayout(progress_box)
        self.lbl_protocol_progress = QLabel("Протокол ещё не формировался.")
        self.lbl_protocol_progress.setWordWrap(True)
        self.progress_protocol = QProgressBar()
        self.progress_protocol.setRange(0, 1)
        self.progress_protocol.setValue(0)
        progress_layout.addWidget(self.lbl_protocol_progress)
        progress_layout.addWidget(self.progress_protocol)
        protocol_layout.addWidget(progress_box)
        title_box = QGroupBox("Официальный заголовок категории")
        title_layout = QVBoxLayout(title_box)
        self.lbl_protocol_title_preview = QLabel("Выберите категорию, чтобы увидеть заголовок по ЕВСК.")
        self.lbl_protocol_title_preview.setWordWrap(True)
        title_layout.addWidget(self.lbl_protocol_title_preview)
        w_protocol_discipline, self.chk_protocol_include_discipline = _checkbox_with_wrapped_label(
            "Добавлять вид ФК в официальный заголовок"
        )
        self.chk_protocol_include_discipline.setChecked(True)
        self.chk_protocol_include_discipline.stateChanged.connect(lambda _state: self._on_protocol_title_option_changed())
        title_layout.addWidget(w_protocol_discipline)
        self.protocol_age_widget = QWidget()
        self.protocol_age_layout = QVBoxLayout(self.protocol_age_widget)
        self.protocol_age_layout.setContentsMargins(0, 0, 0, 0)
        self.protocol_age_layout.setSpacing(4)
        title_layout.addWidget(self.protocol_age_widget)
        protocol_layout.addWidget(title_box)
        protocol_layout.addWidget(self.btn_protocol_export)

        export_tabs = QTabWidget()
        start_tab = QWidget()
        start_tab_layout = QVBoxLayout(start_tab)
        start_tab_layout.setContentsMargins(0, 0, 0, 0)
        start_tab_layout.addWidget(options_box)
        protocol_tab = QWidget()
        protocol_tab_layout = QVBoxLayout(protocol_tab)
        protocol_tab_layout.setContentsMargins(0, 0, 0, 0)
        protocol_tab_layout.addWidget(protocol_box)
        export_tabs.addTab(start_tab, "Стартовые листы")
        export_tabs.addTab(protocol_tab, "Итоговый протокол")
        top_right_layout.addWidget(export_tabs, 0)

        stats_box = QGroupBox("Статистика")
        stats_layout = QVBoxLayout(stats_box)
        self.lbl_group_stats = QLabel("Группы склейки: не назначены")
        self.lbl_group_stats.setWordWrap(True)
        self.lbl_group_stats.setMinimumWidth(0)
        self.lbl_group_stats.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.lbl_selected_stats = QLabel("Выделение: строк 0, участников 0")
        self.lbl_selected_stats.setWordWrap(True)
        self.lbl_selected_stats.setMinimumWidth(0)
        self.lbl_selected_stats.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        stats_layout.addWidget(self.lbl_group_stats)
        stats_layout.addWidget(self.lbl_selected_stats)
        top_right_layout.addWidget(stats_box, 0)

        top_right_scroll = QScrollArea()
        top_right_scroll.setWidgetResizable(True)
        top_right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        top_right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        top_right_scroll.setWidget(top_right)

        logs_box = QGroupBox("Журнал")
        logs_box.setMinimumWidth(280)
        logs_layout = QVBoxLayout(logs_box)
        self.log = QTextEdit()
        self.log.setMinimumHeight(180)
        self.log.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.log.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.log.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        logs_layout.addWidget(self.log, 1)
        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.setChildrenCollapsible(False)
        right_splitter.addWidget(top_right_scroll)
        right_splitter.addWidget(logs_box)
        right_splitter.setStretchFactor(0, 5)
        right_splitter.setStretchFactor(1, 5)
        right_splitter.setSizes([360, 360])
        right_layout.addWidget(right_splitter, 1)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([1050, 620])

        self.btn_export.setStyleSheet("QPushButton { background-color: #2e7d32; color: white; font-weight: 600; }")
        self.btn_protocol_export.setStyleSheet("QPushButton { background-color: #1565c0; color: white; font-weight: 600; }")
        self.btn_clear_group.setStyleSheet("QPushButton { background-color: #c62828; color: white; font-weight: 600; }")

        _setup_logging(self.log)
        self._log = logging.getLogger(__name__)
        self._log.info("Готово к работе. Выберите папку с PRF.DBF / PAR.DBF.")

    def _state_file_path(self) -> Path | None:
        if not self._base_dir:
            return None
        return self._base_dir / ".calcfs_pdf_export_layout.json"

    def _pair_key(self, cat_id: object, scp_id: object) -> str:
        return f"{cat_id}|{scp_id}"

    def _sanitize_filename_part(self, value: str) -> str:
        txt = re.sub(r'[\\/:*?"<>|]+', " ", (value or "").strip())
        txt = re.sub(r"\s+", " ", txt).strip()
        return txt

    def _default_output_filename(self) -> str:
        if not self._snapshot:
            return "Стартовый протокол.pdf"
        chunks = ["Стартовый протокол"]
        date_part = self._sanitize_filename_part(event_date_range(self._snapshot))
        name_part = self._sanitize_filename_part(event_title(self._snapshot))
        if date_part:
            chunks.append(date_part)
        if name_part:
            chunks.append(name_part)
        return " ".join(chunks) + ".pdf"

    def _default_protocol_output_filename(self) -> str:
        if not self._snapshot:
            return "Итоговый протокол.pdf"
        chunks = ["Итоговый протокол"]
        date_part = self._sanitize_filename_part(event_date_range(self._snapshot))
        name_part = self._sanitize_filename_part(event_title(self._snapshot))
        if date_part:
            chunks.append(date_part)
        if name_part:
            chunks.append(name_part)
        return " ".join(chunks) + ".pdf"

    def handle_pick_dir(self) -> None:
        default_dir = Path(r"C:\ISUCalcFS")
        d = QFileDialog.getExistingDirectory(self, "Папка с DBF CalcFS", str(default_dir) if default_dir.is_dir() else "")
        if not d:
            return
        self._base_dir = Path(d)
        self.lbl_dir.setText(f"Папка DBF: {self._base_dir}")
        self._log.info("Выбрана папка: %s", self._base_dir)
        self.handle_scan()

    def _display_label(self, cat_id: object, scp_id: object, label: str) -> str:
        gid = self._merge_groups.get((cat_id, scp_id))
        return f"[Р{gid}] {label}" if gid else label

    def _refresh_labels(self) -> None:
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            c, s, label = it.data(Qt.UserRole)
            it.setText(self._display_label(c, s, label))

    def handle_scan(self) -> None:
        self.list_widget.clear()
        self._pairs = []
        self._merge_groups.clear()
        self._group_order.clear()
        self._group_warmup_size.clear()
        self._group_insert_texts.clear()
        self._snapshot = None
        self._pair_participant_counts.clear()
        self._category_age_selection.clear()
        self._update_protocol_title_editor()
        self.tabs_groups.clear()
        if not self._base_dir:
            QMessageBox.warning(self, "Папка", "Сначала выберите папку с DBF.")
            return
        try:
            self._snapshot = load_calcfs_folder(self._base_dir)
            self._pairs = discover_cat_scp_pairs(self._snapshot)
        except Exception as e:
            self._log.exception("Ошибка загрузки DBF")
            QMessageBox.critical(self, "Ошибка", str(e))
            return
        for cat_id, scp_id, label in self._pairs:
            item = QListWidgetItem(self._display_label(cat_id, scp_id, label))
            item.setData(Qt.UserRole, (cat_id, scp_id, label))
            item.setData(Qt.ItemDataRole.CheckStateRole, Qt.CheckState.Unchecked)
            item.setFlags(
                (item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
                & ~Qt.ItemFlag.ItemIsUserCheckable
                & ~Qt.ItemFlag.ItemIsDropEnabled
            )
            self.list_widget.addItem(item)
            self._pair_participant_counts[(cat_id, scp_id)] = 0
        for cat_id, scp_id, _ in self._pairs:
            try:
                self._pair_participant_counts[(cat_id, scp_id)] = len(build_starting_order_rows(self._snapshot, cat_id, scp_id).rows)
            except Exception:
                self._pair_participant_counts[(cat_id, scp_id)] = 0
        total_children = sum(self._pair_participant_counts.values())
        self.lbl_list_title.setText(f"Доступные категория / сегмент (отметьте несколько) — всего участников: {total_children}")
        self._log.info("Найдено вариантов: %s", len(self._pairs))
        state_path = self._state_file_path()
        if state_path and state_path.is_file():
            ans = QMessageBox.question(self, "Восстановление разбиения", "Найдено сохранённое разбиение. Открыть?", QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if ans == QMessageBox.Yes:
                try:
                    self._apply_layout_state(json.loads(state_path.read_text(encoding="utf-8")))
                except Exception:
                    self._log.exception("Ошибка восстановления сохраненного разбиения")
        self._update_group_stats_label()
        self._update_selected_stats_label()
        self._update_protocol_title_editor()

    def _collect_layout_state(self) -> dict:
        groups = {self._pair_key(c, s): int(g) for (c, s), g in self._merge_groups.items()}
        group_order = {str(g): [self._pair_key(c, s) for c, s, _ in rows] for g, rows in self._group_order.items()}
        group_texts = {
            str(g): [{"mode": m, "index": int(i), "text": str(t)} for m, i, t in inserts if str(t).strip()]
            for g, inserts in self._group_insert_texts.items()
        }
        return {
            "groups": groups,
            "group_order": group_order,
            "group_warmup_size": {str(k): int(v) for k, v in self._group_warmup_size.items()},
            "group_insert_texts": group_texts,
            "global_warmup_size": int(self.spn_warmup.value()),
            "protocol_age_groups": self._category_age_selection,
            "protocol_include_discipline": self.chk_protocol_include_discipline.isChecked(),
            "protocol_rpt_templates": {
                key: edit.text().strip()
                for key, edit in self._protocol_rpt_edits.items()
                if edit.text().strip()
            },
        }

    def _apply_layout_state(self, state: dict) -> None:
        known = {self._pair_key(c, s): (c, s, label) for c, s, label in self._pairs}
        self._merge_groups.clear()
        self._group_order.clear()
        self._group_warmup_size.clear()
        self._group_insert_texts.clear()
        for key, gid in (state.get("groups") or {}).items():
            row = known.get(str(key))
            if row:
                self._merge_groups[(row[0], row[1])] = int(gid)
        for gid_txt, keys in (state.get("group_order") or {}).items():
            gid = int(gid_txt)
            rows = []
            for key in keys or []:
                row = known.get(str(key))
                if row and self._merge_groups.get((row[0], row[1])) == gid:
                    rows.append(row)
            if rows:
                self._group_order[gid] = rows
        for gid_txt, v in (state.get("group_warmup_size") or {}).items():
            self._group_warmup_size[int(gid_txt)] = int(v)
        for gid_txt, inserts in (state.get("group_insert_texts") or {}).items():
            gid = int(gid_txt)
            parsed = []
            for it in inserts or []:
                mode = "after" if str((it or {}).get("mode")) == "after" else "before"
                idx = int((it or {}).get("index", 1))
                txt = str((it or {}).get("text", "")).strip()
                if txt:
                    parsed.append((mode, idx, txt))
            if parsed:
                self._group_insert_texts[gid] = parsed
        if state.get("global_warmup_size"):
            self.spn_warmup.setValue(max(1, int(state["global_warmup_size"])))
        age_state = state.get("protocol_age_groups") or {}
        self._category_age_selection = {
            str(k): [str(v).strip() for v in values or [] if str(v).strip()]
            for k, values in age_state.items()
        }
        if "protocol_include_discipline" in state:
            self.chk_protocol_include_discipline.setChecked(bool(state.get("protocol_include_discipline")))
        for key, path in (state.get("protocol_rpt_templates") or {}).items():
            edit = self._protocol_rpt_edits.get(str(key))
            if edit and str(path).strip():
                edit.setText(str(path).strip())
        self._refresh_labels()
        self._rebuild_group_tabs()
        self._update_protocol_title_editor()

    def _save_layout_state_silent(self) -> None:
        state_path = self._state_file_path()
        if not state_path:
            return
        try:
            state_path.write_text(json.dumps(self._collect_layout_state(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            self._log.exception("Не удалось сохранить настройки протокола")

    def handle_save_layout(self) -> None:
        state_path = self._state_file_path()
        if not state_path:
            return
        state_path.write_text(json.dumps(self._collect_layout_state(), ensure_ascii=False, indent=2), encoding="utf-8")
        self._log.info("Разбиение сохранено: %s", state_path)
        QMessageBox.information(self, "Сохранено", f"Разбиение сохранено:\n{state_path}")

    def _selected_indices(self) -> list[int]:
        row = self.list_widget.currentRow()
        return [row] if row >= 0 else []

    def _checked_category_items(self) -> list[QListWidgetItem]:
        return [
            self.list_widget.item(i)
            for i in range(self.list_widget.count())
            if self.list_widget.item(i).checkState() == Qt.CheckState.Checked
        ]

    def _toggle_category_item_check(self, item: QListWidgetItem) -> None:
        item.setCheckState(Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked)
        self._update_selected_stats_label()
        self._update_protocol_title_editor()

    def handle_check_all_categories(self) -> None:
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.CheckState.Checked)
        self._update_selected_stats_label()
        self._update_protocol_title_editor()

    def handle_uncheck_all_categories(self) -> None:
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(Qt.CheckState.Unchecked)
        self._update_selected_stats_label()
        self._update_protocol_title_editor()

    def handle_move_up(self) -> None:
        for idx in self._selected_indices():
            if idx <= 0:
                continue
            it = self.list_widget.takeItem(idx)
            self.list_widget.insertItem(idx - 1, it)
            self.list_widget.setCurrentItem(it)

    def handle_move_down(self) -> None:
        idxs = self._selected_indices()
        for idx in reversed(idxs):
            if idx >= self.list_widget.count() - 1:
                continue
            it = self.list_widget.takeItem(idx)
            self.list_widget.insertItem(idx + 1, it)
            self.list_widget.setCurrentItem(it)

    def handle_move_top(self) -> None:
        idxs = self._selected_indices()
        items = [self.list_widget.takeItem(i - off) for off, i in enumerate(idxs)]
        for pos, it in enumerate(items):
            self.list_widget.insertItem(pos, it)
            self.list_widget.setCurrentItem(it)

    def handle_move_bottom(self) -> None:
        idxs = self._selected_indices()
        items = [self.list_widget.takeItem(i - off) for off, i in enumerate(idxs)]
        start = self.list_widget.count()
        for pos, it in enumerate(items):
            self.list_widget.insertItem(start + pos, it)
            self.list_widget.setCurrentItem(it)

    def handle_assign_group(self) -> None:
        gid = int(self.spn_merge_group.value())
        items = self._checked_category_items() or self.list_widget.selectedItems()
        if not items:
            return
        for it in items:
            c, s, _ = it.data(Qt.UserRole)
            self._merge_groups[(c, s)] = gid
        self.list_widget.clearSelection()
        self._refresh_labels()
        self._rebuild_group_tabs()
        self._update_group_stats_label()
        self._update_selected_stats_label()
        self._log.info("Назначена группа Р%s для %s строк", gid, len(items))

    def handle_clear_groups(self) -> None:
        self._merge_groups.clear()
        self._group_order.clear()
        self._group_warmup_size.clear()
        self._group_insert_texts.clear()
        self._refresh_labels()
        self._rebuild_group_tabs()
        self._update_group_stats_label()

    def _refresh_merge_group_controls(self) -> None:
        gids = sorted(set(self._merge_groups.values()))
        self.cmb_merge_from.clear()
        self.cmb_merge_to.clear()
        for gid in gids:
            self.cmb_merge_from.addItem(f"Группа {gid}", gid)
            self.cmb_merge_to.addItem(f"Группа {gid}", gid)
        enabled = len(gids) >= 2
        self.cmb_merge_from.setEnabled(enabled)
        self.cmb_merge_to.setEnabled(enabled)
        self.btn_merge_groups.setEnabled(enabled)

    def handle_merge_groups(self) -> None:
        from_gid = self.cmb_merge_from.currentData()
        to_gid = self.cmb_merge_to.currentData()
        if from_gid is None or to_gid is None or from_gid == to_gid:
            return
        for key, gid in list(self._merge_groups.items()):
            if gid == from_gid:
                self._merge_groups[key] = to_gid
        if from_gid in self._group_order:
            self._group_order.setdefault(to_gid, []).extend(self._group_order[from_gid])
            self._group_order.pop(from_gid, None)
        self._group_warmup_size.pop(from_gid, None)
        self._group_insert_texts.pop(from_gid, None)
        self._refresh_labels()
        self._rebuild_group_tabs()
        self._update_group_stats_label()

    def _group_total_participants(self, gid: int) -> int:
        return sum(self._pair_participant_counts.get((c, s), 0) for c, s, _ in self._group_order.get(gid, []))

    def _group_warmup_count(self, gid: int) -> int:
        total = self._group_total_participants(gid)
        per = max(1, int(self._group_warmup_size.get(gid, self.spn_warmup.value())))
        return (total + per - 1) // per if total else 0

    def _split_counts_text(self, total: int, per_warmup: int) -> str:
        if total <= 0:
            return "0"
        size = max(1, int(per_warmup))
        groups = (total + size - 1) // size
        base = total // groups
        rem = total % groups
        chunks = [str(base)] * (groups - rem) + [str(base + 1)] * rem
        return " + ".join(chunks)

    def _update_group_tab_info(self, gid: int) -> None:
        total = self._group_total_participants(gid)
        per = int(self._group_warmup_size.get(gid, self.spn_warmup.value()))
        split = self._split_counts_text(total, per)
        for i in range(self.tabs_groups.count()):
            if self.tabs_groups.tabText(i) == f"Группа {gid}":
                page = self.tabs_groups.widget(i)
                lbl = page.findChild(QLabel, f"group_info_{gid}") if page else None
                if lbl:
                    lbl.setText(f"Участников: {total} | Разминки: {split}")
                break

    def _rebuild_group_tabs(self) -> None:
        self.tabs_groups.clear()
        if not self._merge_groups:
            p = QWidget()
            l = QVBoxLayout(p)
            hint = QLabel("Назначьте группы, чтобы управлять порядком внутри каждой группы")
            hint.setWordWrap(True)
            hint.setMinimumWidth(0)
            l.addWidget(hint)
            l.addStretch()
            self.tabs_groups.addTab(p, "Группы")
            self._refresh_merge_group_controls()
            return
        label_by_key = {}
        for i in range(self.list_widget.count()):
            c, s, label = self.list_widget.item(i).data(Qt.UserRole)
            label_by_key[(c, s)] = label
        groups: dict[int, list[tuple[object, object, str]]] = {}
        for key, gid in self._merge_groups.items():
            label = label_by_key.get(key)
            if label:
                groups.setdefault(gid, []).append((key[0], key[1], label))
        for gid, items in groups.items():
            current = self._group_order.get(gid, [])
            current_keys = {(c, s) for c, s, _ in current}
            merged = [x for x in current if (x[0], x[1]) in {(a, b) for a, b, _ in items}]
            for item in items:
                if (item[0], item[1]) not in current_keys:
                    merged.append(item)
            self._group_order[gid] = merged
        for gid in sorted(groups.keys()):
            tab = QWidget()
            v = QVBoxLayout(tab)
            top = QHBoxLayout()
            info = QLabel("")
            info.setObjectName(f"group_info_{gid}")
            info.setWordWrap(True)
            info.setMinimumWidth(0)
            info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            spn = QSpinBox()
            spn.setRange(1, 50)
            spn.setValue(int(self._group_warmup_size.get(gid, self.spn_warmup.value())))
            spn.setPrefix("В разминке: ")
            spn.valueChanged.connect(lambda _=0, g=gid: self._on_group_warmup_size_changed(g))
            top.addWidget(info, 1)
            top.addWidget(spn, 0)
            v.addLayout(top)
            ins = QVBoxLayout()
            txt = QLineEdit()
            txt.setObjectName(f"group_insert_text_{gid}")
            txt.setPlaceholderText("Добавить текстовый блок (например: ПОДГОТОВКА ЛЬДА)")
            ins.addWidget(txt)
            ins_row2 = QHBoxLayout()
            mode = QComboBox()
            mode.setObjectName(f"group_insert_mode_{gid}")
            mode.addItems(["Перед", "После"])
            before = QSpinBox()
            before.setObjectName(f"group_insert_before_{gid}")
            warmup_count = max(1, self._group_warmup_count(gid))
            before.setRange(1, warmup_count)
            before.setPrefix("Перед разминкой: ")
            mode.currentTextChanged.connect(
                lambda text, sp=before: sp.setPrefix("Перед разминкой: " if text == "Перед" else "После разминки: ")
            )
            b_add_text = QPushButton("Добавить текст")
            b_add_text.clicked.connect(lambda _=False, g=gid: self._add_group_text(g))
            ins_row2.addWidget(mode, 1)
            ins_row2.addWidget(before, 2)
            ins_row2.addWidget(b_add_text, 1)
            ins.addLayout(ins_row2)
            v.addLayout(ins)
            inserts = QListWidget()
            inserts.setObjectName(f"group_insert_list_{gid}")
            inserts.setMaximumHeight(90)
            inserts.setWordWrap(True)
            inserts.setUniformItemSizes(False)
            for m, n, t in self._group_insert_texts.get(gid, []):
                item = QListWidgetItem(f"{'Перед' if m == 'before' else 'После'} разминки {n}: {t}")
                item.setData(Qt.UserRole, (m, n, t))
                inserts.addItem(item)
            v.addWidget(inserts, 0)
            lw = QListWidget()
            lw.setObjectName(f"group_list_{gid}")
            lw.setWordWrap(True)
            lw.setUniformItemSizes(False)
            lw.setSpacing(2)
            lw.setSelectionMode(QListWidget.MultiSelection)
            for c, s, label in self._group_order.get(gid, []):
                it = QListWidgetItem(label)
                it.setData(Qt.UserRole, (c, s, label))
                lw.addItem(it)
            v.addWidget(lw, 1)
            row = QGridLayout()
            row.setHorizontalSpacing(6)
            row.setVerticalSpacing(6)
            grp_btns = [
                ("Вверх", lambda _=False, g=gid: self._move_in_group(g, "up")),
                ("Вниз", lambda _=False, g=gid: self._move_in_group(g, "down")),
                ("В начало", lambda _=False, g=gid: self._move_in_group(g, "top")),
                ("В конец", lambda _=False, g=gid: self._move_in_group(g, "bottom")),
                ("Убрать из группы", lambda _=False, g=gid: self._remove_from_group(g)),
                ("Удалить текст", lambda _=False, g=gid: self._remove_group_text(g)),
            ]
            for i, (text, cb) in enumerate(grp_btns):
                b = QPushButton(text)
                b.setMinimumWidth(0)
                b.clicked.connect(cb)
                row.addWidget(b, i // 2, i % 2)
            v.addLayout(row)
            self.tabs_groups.addTab(tab, f"Группа {gid}")
            self._update_group_tab_info(gid)
        self._refresh_merge_group_controls()

    def _group_list_widget(self, gid: int) -> QListWidget | None:
        for i in range(self.tabs_groups.count()):
            if self.tabs_groups.tabText(i) == f"Группа {gid}":
                page = self.tabs_groups.widget(i)
                return page.findChild(QListWidget, f"group_list_{gid}") if page else None
        return None

    def _selected_indices_in_list(self, lw: QListWidget) -> list[int]:
        return [i for i in range(lw.count()) if lw.item(i).isSelected()]

    def _sync_group_order_from_widget(self, gid: int, lw: QListWidget) -> None:
        self._group_order[gid] = [lw.item(i).data(Qt.UserRole) for i in range(lw.count())]

    def _move_in_group(self, gid: int, direction: str) -> None:
        lw = self._group_list_widget(gid)
        if not lw:
            return
        idxs = self._selected_indices_in_list(lw)
        if not idxs:
            return
        if direction == "up":
            for idx in idxs:
                if idx <= 0 or lw.item(idx - 1).isSelected():
                    continue
                it = lw.takeItem(idx)
                lw.insertItem(idx - 1, it)
                it.setSelected(True)
        elif direction == "down":
            for idx in reversed(idxs):
                if idx >= lw.count() - 1 or lw.item(idx + 1).isSelected():
                    continue
                it = lw.takeItem(idx)
                lw.insertItem(idx + 1, it)
                it.setSelected(True)
        elif direction == "top":
            items = [lw.takeItem(i - off) for off, i in enumerate(idxs)]
            for pos, it in enumerate(items):
                lw.insertItem(pos, it)
                it.setSelected(True)
        elif direction == "bottom":
            items = [lw.takeItem(i - off) for off, i in enumerate(idxs)]
            start = lw.count()
            for pos, it in enumerate(items):
                lw.insertItem(start + pos, it)
                it.setSelected(True)
        self._sync_group_order_from_widget(gid, lw)
        self._update_group_tab_info(gid)

    def _remove_from_group(self, gid: int) -> None:
        lw = self._group_list_widget(gid)
        if not lw:
            return
        idxs = self._selected_indices_in_list(lw)
        if not idxs:
            return
        drop = [lw.item(i).data(Qt.UserRole) for i in idxs]
        for c, s, _ in drop:
            self._merge_groups.pop((c, s), None)
        drop_keys = {(c, s) for c, s, _ in drop}
        if gid in self._group_order:
            keep = [x for x in self._group_order[gid] if (x[0], x[1]) not in drop_keys]
            if keep:
                self._group_order[gid] = keep
            else:
                self._group_order.pop(gid, None)
                self._group_warmup_size.pop(gid, None)
        self._refresh_labels()
        self._rebuild_group_tabs()
        self._update_group_stats_label()
        self._update_selected_stats_label()

    def _add_group_text(self, gid: int) -> None:
        for i in range(self.tabs_groups.count()):
            if self.tabs_groups.tabText(i) != f"Группа {gid}":
                continue
            page = self.tabs_groups.widget(i)
            txt = page.findChild(QLineEdit, f"group_insert_text_{gid}") if page else None
            mode = page.findChild(QComboBox, f"group_insert_mode_{gid}") if page else None
            spn = page.findChild(QSpinBox, f"group_insert_before_{gid}") if page else None
            if not txt or not spn or not mode:
                QMessageBox.warning(self, "Вставка текста", "Не удалось найти элементы управления вставкой.")
                return
            text = txt.text().strip()
            if not text:
                QMessageBox.warning(self, "Вставка текста", "Введите текст для вставки.")
                return
            before = int(spn.value())
            warmup_count = self._group_warmup_count(gid)
            if warmup_count < 1:
                QMessageBox.warning(self, "Вставка текста", "В группе нет разминок для вставки.")
                return
            if before > warmup_count:
                QMessageBox.warning(self, "Вставка текста", f"В группе только {warmup_count} разминки.")
                return
            insert_mode = "before" if mode.currentText() == "Перед" else "after"
            self._group_insert_texts.setdefault(gid, []).append((insert_mode, before, text))
            txt.clear()
            self._rebuild_group_tabs()
            self._log.info("В группу %s добавлен текст %s разминки %s: %s", gid, insert_mode, before, text)
            return

    def _remove_group_text(self, gid: int) -> None:
        for i in range(self.tabs_groups.count()):
            if self.tabs_groups.tabText(i) != f"Группа {gid}":
                continue
            page = self.tabs_groups.widget(i)
            lw = page.findChild(QListWidget, f"group_insert_list_{gid}") if page else None
            if not lw:
                return
            selected = lw.selectedItems()
            if not selected:
                return
            drop = {it.data(Qt.UserRole) for it in selected}
            self._group_insert_texts[gid] = [x for x in self._group_insert_texts.get(gid, []) if x not in drop]
            if not self._group_insert_texts[gid]:
                self._group_insert_texts.pop(gid, None)
            self._rebuild_group_tabs()
            return

    def _on_group_warmup_size_changed(self, gid: int) -> None:
        for i in range(self.tabs_groups.count()):
            if self.tabs_groups.tabText(i) == f"Группа {gid}":
                page = self.tabs_groups.widget(i)
                for spn in page.findChildren(QSpinBox):
                    if spn.prefix().startswith("В разминке"):
                        self._group_warmup_size[gid] = int(spn.value())
                        break
        self._update_group_tab_info(gid)
        self._update_group_stats_label()

    def _update_selected_stats_label(self) -> None:
        checked_items = self._checked_category_items()
        if not checked_items:
            self.lbl_selected_stats.setText("Отмечено: строк 0, участников 0")
            return
        rows = len(checked_items)
        participants = 0
        for it in checked_items:
            c, s, _ = it.data(Qt.UserRole)
            participants += self._pair_participant_counts.get((c, s), 0)
        self.lbl_selected_stats.setText(f"Отмечено: строк {rows}, участников {participants}")

    def _current_protocol_cat_id(self) -> object | None:
        current = self.list_widget.currentItem()
        if current:
            return current.data(Qt.UserRole)[0]
        checked_items = self._checked_category_items()
        if checked_items:
            return checked_items[0].data(Qt.UserRole)[0]
        if self.list_widget.count():
            return self.list_widget.item(0).data(Qt.UserRole)[0]
        return None

    def _clear_protocol_age_layout(self) -> None:
        self._protocol_age_checkboxes.clear()
        while self.protocol_age_layout.count():
            item = self.protocol_age_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _update_protocol_title_editor(self) -> None:
        if not hasattr(self, "protocol_age_layout"):
            return
        self._clear_protocol_age_layout()
        if not self._snapshot:
            self.lbl_protocol_title_preview.setText("Выберите папку и категорию, чтобы увидеть заголовок по ЕВСК.")
            return
        cat_id = self._current_protocol_cat_id()
        cat = category_by_id(self._snapshot, cat_id) if cat_id is not None else None
        if not cat:
            self.lbl_protocol_title_preview.setText("Выберите категорию, чтобы увидеть заголовок по ЕВСК.")
            return
        rule = rule_for_category(cat)
        if not rule:
            source = str(rec_get(cat, "CAT_NAME") or "").strip()
            self.lbl_protocol_title_preview.setText(
                "Для этой комбинации CAT_TYPE/CAT_LEVEL/CAT_GENDER пока нет правила. "
                f"Будет использовано исходное название:\n{source}"
            )
            return
        key = cat_key(rec_get(cat, "CAT_ID"))
        selected = self._category_age_selection.get(key, list(rule.age_groups))
        selected = [age for age in selected if age in rule.age_groups]
        for age in rule.age_groups:
            cb = QCheckBox(age)
            cb.setChecked(age in selected)
            cb.stateChanged.connect(lambda _state, cid=key: self._on_protocol_age_changed(cid))
            self.protocol_age_layout.addWidget(cb)
            self._protocol_age_checkboxes.append(cb)
        if not rule.age_groups:
            empty = QLabel("Для этого разряда возрастные группы не заданы в правилах.")
            empty.setWordWrap(True)
            self.protocol_age_layout.addWidget(empty)
        title = official_title_for_category(
            cat,
            selected,
            include_discipline=self.chk_protocol_include_discipline.isChecked(),
        )
        self.lbl_protocol_title_preview.setText(title or str(rec_get(cat, "CAT_NAME") or "").strip())

    def _on_protocol_title_option_changed(self) -> None:
        self._refresh_protocol_title_preview_only()
        self._save_layout_state_silent()

    def _on_protocol_age_changed(self, category_key: str) -> None:
        selected = [cb.text() for cb in self._protocol_age_checkboxes if cb.isChecked()]
        self._category_age_selection[category_key] = selected
        self._refresh_protocol_title_preview_only()
        self._save_layout_state_silent()

    def _refresh_protocol_title_preview_only(self) -> None:
        if not self._snapshot:
            return
        cat_id = self._current_protocol_cat_id()
        cat = category_by_id(self._snapshot, cat_id) if cat_id is not None else None
        if not cat:
            return
        key = cat_key(rec_get(cat, "CAT_ID"))
        title = official_title_for_category(
            cat,
            self._category_age_selection.get(key),
            include_discipline=self.chk_protocol_include_discipline.isChecked(),
        )
        if title:
            self.lbl_protocol_title_preview.setText(title)

    def _collect_protocol_title_overrides(self) -> dict[object, str]:
        if not self._snapshot:
            return {}
        overrides: dict[object, str] = {}
        for cat in self._snapshot.cat:
            key = cat_key(rec_get(cat, "CAT_ID"))
            title = official_title_for_category(
                cat,
                self._category_age_selection.get(key),
                include_discipline=self.chk_protocol_include_discipline.isChecked(),
            )
            if title:
                overrides[rec_get(cat, "CAT_ID")] = title
        return overrides

    def _pick_rpt_template(self, key: str) -> None:
        edit = self._protocol_rpt_edits.get(key)
        if not edit:
            return
        current = Path(edit.text().strip()) if edit.text().strip() else RPT_DIR
        start_dir = current.parent if current.is_file() else RPT_DIR
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать Crystal RPT", str(start_dir), "Crystal Reports (*.rpt)")
        if not path:
            return
        edit.setText(path)
        self._save_layout_state_silent()

    def _collect_protocol_rpt_templates(self) -> dict[str, Path]:
        templates: dict[str, Path] = {}
        for key, edit in self._protocol_rpt_edits.items():
            raw = edit.text().strip()
            if not raw:
                continue
            path = Path(raw)
            if path.is_file():
                templates[key] = path
            else:
                self._log.warning("RPT шаблон не найден и будет использован штатный: %s", path)
        return templates

    def _set_category_row_background(self, cat_id: object, color: QColor | None) -> None:
        brush = QBrush(color) if color else QBrush()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            row_cat_id, _, _ = item.data(Qt.UserRole)
            if same_id(row_cat_id, cat_id):
                item.setBackground(brush)

    def _reset_protocol_progress_ui(self) -> None:
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setBackground(QBrush())
        self.progress_protocol.setRange(0, 1)
        self.progress_protocol.setValue(0)
        self.lbl_protocol_progress.setText("Подготовка итогового протокола...")
        QApplication.processEvents()

    def _on_protocol_progress(self, event: dict[str, object]) -> None:
        total = int(event.get("total") or 0)
        completed = int(event.get("completed") or 0)
        if total > 0:
            self.progress_protocol.setRange(0, total)
            self.progress_protocol.setValue(min(completed, total))
        stage = str(event.get("stage") or "")
        cat_id = event.get("cat_id")
        report = str(event.get("report") or "")
        if stage == "start":
            self.lbl_protocol_progress.setText(f"Отчётов: 0 из {total}")
        elif stage == "report_start":
            if cat_id is not None:
                self._set_category_row_background(cat_id, QColor("#fff3cd"))
            self.lbl_protocol_progress.setText(f"Формируется: {report} ({completed} из {total})")
        elif stage == "report_done":
            self.lbl_protocol_progress.setText(f"Готово отчётов: {completed} из {total}")
        elif stage == "category_done":
            if cat_id is not None:
                self._set_category_row_background(cat_id, QColor("#d4edda"))
            self.lbl_protocol_progress.setText(f"Категория готова. Отчётов: {completed} из {total}")
        elif stage == "failed":
            if cat_id is not None:
                self._set_category_row_background(cat_id, QColor("#f8d7da"))
            self.lbl_protocol_progress.setText(f"Ошибка: {event.get('message')}")
        QApplication.processEvents()

    def _update_group_stats_label(self) -> None:
        if not self._merge_groups:
            self.lbl_group_stats.setText("Группы склейки: не назначены")
            return
        grouped: dict[int, list[tuple[object, object]]] = {}
        for (c, s), gid in self._merge_groups.items():
            grouped.setdefault(gid, []).append((c, s))
        parts = []
        for gid in sorted(grouped.keys()):
            total = sum(self._pair_participant_counts.get((c, s), 0) for c, s in grouped[gid])
            group_size = int(self._group_warmup_size.get(gid, self.spn_warmup.value()))
            warmup_count = math.ceil(total / max(1, group_size)) if total else 0
            parts.append(f"Р{gid}: участников {total}, разминок {warmup_count} (по {group_size})")
        self.lbl_group_stats.setText("Группы склейки: " + " | ".join(parts))

    def _collect_selected_pairs_for_export(self) -> list[tuple[object, object, str]] | None:
        selected_items = self._checked_category_items()
        selected: list[tuple[object, object, str]] = []
        use_group_default = self._merge_groups and not selected_items
        if use_group_default:
            label_by_key = {}
            for i in range(self.list_widget.count()):
                c, s, label = self.list_widget.item(i).data(Qt.UserRole)
                label_by_key[(c, s)] = label
            used: set[tuple[object, object]] = set()
            for gid in sorted(set(self._merge_groups.values())):
                for c, s, label in self._group_order.get(gid, []):
                    key = (c, s)
                    if self._merge_groups.get(key) != gid or key in used:
                        continue
                    selected.append((c, s, label))
                    used.add(key)
                for key, val_gid in self._merge_groups.items():
                    if val_gid != gid or key in used:
                        continue
                    label = label_by_key.get(key)
                    if label:
                        selected.append((key[0], key[1], label))
                        used.add(key)
            if not selected:
                QMessageBox.warning(self, "Выбор", "Назначьте хотя бы одну строку в группу склейки.")
                return None
        else:
            if not selected_items:
                QMessageBox.warning(self, "Выбор", "Поставьте галочку хотя бы у одной категории/сегмента.")
                return None
            for i in range(self.list_widget.count()):
                it = self.list_widget.item(i)
                if it.checkState() == Qt.CheckState.Checked:
                    selected.append(it.data(Qt.UserRole))
        return selected

    def handle_protocol_export(self) -> None:
        if not self._base_dir:
            QMessageBox.warning(self, "Папка", "Сначала выберите папку с DBF.")
            return
        selected = self._collect_selected_pairs_for_export()
        if not selected:
            return
        include_result = self.chk_protocol_result.isChecked()
        include_segment_details = self.chk_protocol_segment_details.isChecked()
        include_judges_scores = self.chk_protocol_judges_scores.isChecked()
        if not (include_result or include_segment_details or include_judges_scores):
            QMessageBox.warning(self, "Итоговый протокол", "Выберите хотя бы один блок протокола.")
            return
        dest, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить итоговый протокол",
            str((self._base_dir / self._default_protocol_output_filename()) if self._base_dir else Path(self._default_protocol_output_filename())),
            "PDF (*.pdf)",
        )
        if not dest:
            return
        out = Path(dest)
        self._save_layout_state_silent()
        self._reset_protocol_progress_ui()
        self._log.info("Экспорт итогового протокола: %s строк → %s", len(selected), out)
        results, merged = export_protocol_bundle(
            self._base_dir,
            selected,
            out,
            include_result=include_result,
            include_segment_details=include_segment_details,
            include_judges_scores=include_judges_scores,
            protocol_renderer="rpt" if self.chk_protocol_use_rpt.isChecked() else "python",
            category_title_overrides=self._collect_protocol_title_overrides(),
            rpt_template_paths=self._collect_protocol_rpt_templates(),
            progress_callback=self._on_protocol_progress,
        )
        for r in results:
            if r.ok:
                self._log.info("[OK] итоговый протокол: %s", r.label)
            else:
                self._log.error("[ОШИБКА] итоговый протокол: %s — %s", r.label, r.message)
        if merged:
            self._log.info("Готово: %s", merged)
            self.lbl_protocol_progress.setText(f"Готово: {merged}")
            if merged != out:
                QMessageBox.warning(
                    self,
                    "Файл был открыт",
                    f"Целевой PDF занят другим приложением.\nСохранено в новый файл:\n{merged}",
                )
            else:
                QMessageBox.information(self, "Готово", f"Итоговый протокол сохранён:\n{merged}")
        else:
            QMessageBox.critical(self, "Ошибка", "Не удалось создать ни одного фрагмента итогового протокола.")

    def handle_export(self) -> None:
        if not self._base_dir:
            QMessageBox.warning(self, "Папка", "Сначала выберите папку с DBF.")
            return
        selected = self._collect_selected_pairs_for_export()
        if not selected:
            return
        dest, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить объединённый PDF",
            str((self._base_dir / self._default_output_filename()) if self._base_dir else Path(self._default_output_filename())),
            "PDF (*.pdf)",
        )
        if not dest:
            return
        out = Path(dest)
        include_rank = self.chk_include_rank.isChecked()
        include_birth = self.chk_include_birth.isChecked()
        include_coach = self.chk_include_coach.isChecked()
        self._log.info("Экспорт %s фрагментов → %s", len(selected), out)
        self._log.info(
            "Опции колонок: разряд=%s, дата рождения=%s, тренер=%s",
            include_rank,
            include_birth,
            include_coach,
        )
        results, merged = export_starting_order_bundle(
            self._base_dir,
            selected,
            out,
            combine_selected_into_single_sheet=self.chk_combine_sheet.isChecked(),
            regroup_warmups_for_combined=self.chk_regroup_warmup.isChecked(),
            warmup_size=int(self.spn_warmup.value()),
            merge_group_map=dict(self._merge_groups),
            group_warmup_size_map=dict(self._group_warmup_size),
            group_insert_texts_map=dict(self._group_insert_texts),
            include_active_rank=include_rank,
            include_birth_date=include_birth,
            include_coach=include_coach,
        )
        for r in results:
            if r.ok:
                self._log.info("[OK] %s", r.label)
            else:
                self._log.error("[ОШИБКА] %s — %s", r.label, r.message)
        if merged:
            self._log.info("Готово: %s", merged)
            if merged != out:
                QMessageBox.warning(
                    self,
                    "Файл был открыт",
                    f"Целевой PDF занят другим приложением.\nСохранено в новый файл:\n{merged}",
                )
            else:
                QMessageBox.information(self, "Готово", f"PDF сохранён:\n{merged}")
        else:
            QMessageBox.critical(self, "Ошибка", "Не удалось создать ни одного фрагмента PDF.")


def run_app() -> None:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
