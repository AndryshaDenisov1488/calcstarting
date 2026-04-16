from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _build_fallback_destination(destination: Path) -> Path:
    stem = destination.stem
    suffix = destination.suffix or ".pdf"
    parent = destination.parent
    n = 1
    while True:
        cand = parent / f"{stem}_{n}{suffix}"
        if not cand.exists():
            return cand
        n += 1


def merge_pdf_files(paths: list[Path], destination: Path) -> Path:
    """Объединяет PDF в заданном порядке (pypdf)."""
    from pypdf import PdfWriter, PdfReader

    destination.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for p in paths:
        if not p.is_file():
            logger.warning("Пропуск отсутствующего файла: %s", p)
            continue
        reader = PdfReader(str(p))
        for page in reader.pages:
            writer.add_page(page)
    try:
        with destination.open("wb") as f:
            writer.write(f)
        logger.info("Итоговый PDF: %s (%s страниц)", destination, len(writer.pages))
        return destination
    except PermissionError:
        fallback = _build_fallback_destination(destination)
        with fallback.open("wb") as f:
            writer.write(f)
        logger.warning("Целевой PDF занят. Сохранено в резервный файл: %s", fallback)
        return fallback
