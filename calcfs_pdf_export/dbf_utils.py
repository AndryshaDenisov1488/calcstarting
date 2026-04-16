from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)

# Типичные кодировки CalcFS / русскоязычных DBF
_ENCODING_CANDIDATES = ("cp1251", "cp866", "latin-1")


def rec_get(record: dict[str, Any], *names: str) -> Any:
    """Регистронезависимый доступ к полям DBF."""
    upper_map = {str(k).upper(): v for k, v in record.items()}
    for name in names:
        key = name.upper()
        if key in upper_map:
            return upper_map[key]
    return None


def _normalize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        s = value.strip()
        return s if s else None
    return value


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    return {str(k).upper(): _normalize_value(v) for k, v in record.items()}


def open_dbf(path: Path) -> tuple[Any, str]:
    """
    Открывает DBF, перебирая кодировки. Возвращает (DBF-объект, использованная кодировка).
    Требует пакет dbfread.
    """
    from dbfread import DBF

    last_err: Exception | None = None
    for enc in _ENCODING_CANDIDATES:
        try:
            table = DBF(
                str(path),
                encoding=enc,
                ignore_missing_memofile=True,
                load=False,
            )
            # Проверочное чтение одной записи
            it = iter(table)
            next(it, None)
            logger.debug("DBF %s opened with encoding %s", path.name, enc)
            return table, enc
        except Exception as e:
            last_err = e
            logger.debug("DBF %s failed with %s: %s", path.name, enc, e)
    raise OSError(f"Не удалось открыть {path}: {last_err}") from last_err


def load_records(path: Path) -> tuple[list[dict[str, Any]], str]:
    """Загружает все записи в список словарей (ключи в верхнем регистре)."""
    table, enc = open_dbf(path)
    table.load()
    rows: list[dict[str, Any]] = []
    for rec in table:
        rows.append(normalize_record(dict(rec)))
    return rows, enc


def find_dbf(base: Path, stem: str) -> Path | None:
    """Ищет stem.dbf без учёта регистра."""
    if not base.is_dir():
        return None
    low = stem.lower()
    for p in base.iterdir():
        if p.is_file() and p.suffix.lower() == ".dbf" and p.stem.lower() == low:
            return p
    return None


def iter_dbf_files(base: Path) -> Iterator[Path]:
    if not base.is_dir():
        return
    for p in sorted(base.iterdir(), key=lambda x: x.name.lower()):
        if p.is_file() and p.suffix.lower() == ".dbf":
            yield p
