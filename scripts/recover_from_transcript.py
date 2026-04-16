from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(r"c:\Users\Андрюша\Documents\Хранилище\Разработки\Разное\calcstarting").resolve()
TRANSCRIPT = Path(
    r"c:\Users\Андрюша\.cursor\projects\c-Users-Documents-calcstarting\agent-transcripts\ca115516-a459-45d5-a5c1-75e90f23b3ba\ca115516-a459-45d5-a5c1-75e90f23b3ba.jsonl"
)


def _normalize_path(raw: str) -> Path:
    return Path(raw).resolve()


def _is_in_project(path: Path) -> bool:
    try:
        path.relative_to(ROOT)
        return True
    except ValueError:
        return False


def _replay_write(op_input: dict) -> bool:
    path_raw = op_input.get("path")
    if not path_raw:
        return False
    path = _normalize_path(path_raw)
    if not _is_in_project(path):
        return False
    content = op_input.get("contents", "")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _replay_strreplace(op_input: dict) -> tuple[bool, bool]:
    path_raw = op_input.get("path")
    if not path_raw:
        return (False, False)
    path = _normalize_path(path_raw)
    if not _is_in_project(path):
        return (False, False)
    if not path.exists():
        return (True, False)
    old = op_input.get("old_string", "")
    new = op_input.get("new_string", "")
    text = path.read_text(encoding="utf-8")
    if old not in text:
        return (True, False)
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    return (True, True)


def main() -> None:
    if not TRANSCRIPT.exists():
        raise FileNotFoundError(TRANSCRIPT)

    writes = 0
    str_seen = 0
    str_ok = 0

    for line in TRANSCRIPT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = obj.get("message") or {}
        content = msg.get("content") or []
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "tool_use":
                continue
            name = item.get("name")
            op_input = item.get("input") or {}
            if name == "Write" and isinstance(op_input, dict):
                if _replay_write(op_input):
                    writes += 1
            elif name == "StrReplace" and isinstance(op_input, dict):
                seen, applied = _replay_strreplace(op_input)
                if seen:
                    str_seen += 1
                    if applied:
                        str_ok += 1

    print(f"Writes applied: {writes}")
    print(f"StrReplace seen: {str_seen}")
    print(f"StrReplace applied: {str_ok}")


if __name__ == "__main__":
    main()
