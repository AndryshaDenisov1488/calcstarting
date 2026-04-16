from __future__ import annotations

from typing import Any


def same_id(a: Any, b: Any) -> bool:
    """Сравнение идентификаторов из DBF (int/float/str)."""
    if a is None or b is None:
        return a is None and b is None
    if a == b:
        return True
    try:
        return int(float(a)) == int(float(b))
    except (TypeError, ValueError):
        return str(a).strip() == str(b).strip()


def normalize_id(val: Any) -> Any:
    """Приведение ID к int, если возможно."""
    if val is None:
        return None
    try:
        f = float(val)
        if f == int(f):
            return int(f)
        return f
    except (TypeError, ValueError):
        return val
