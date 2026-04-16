from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

OLE_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")


def describe_rpt_file(path: Path) -> str:
    """
    Краткое описание .rpt для логов.
    Если установлен olefile — добавляет список потоков OLE.
    """
    if not path.is_file():
        return f"Файл не найден: {path}"
    head = path.read_bytes()[:8]
    if head != OLE_MAGIC:
        return f"{path.name}: не OLE Compound Document (сигнатура {head.hex()})"

    lines = [f"{path.name}: OLE Compound Document (вероятно Crystal/legacy report)."]
    try:
        import olefile
    except ImportError:
        lines.append(
            "Для списка потоков установите: pip install olefile (опционально)."
        )
        return "\n".join(lines)

    try:
        ole = olefile.OleFileIO(str(path))
        try:
            lst = ole.listdir()
            lines.append(f"Потоки OLE ({len(lst)}):")
            for e in lst[:80]:
                lines.append("  • " + "/".join(e))
            if len(lst) > 80:
                lines.append(f"  … и ещё {len(lst) - 80}")
        finally:
            ole.close()
    except Exception as e:
        lines.append(f"Ошибка чтения OLE: {e}")
    return "\n".join(lines)
