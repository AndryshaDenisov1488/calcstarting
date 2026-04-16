from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from calcfs_pdf_export.dbf_utils import iter_dbf_files, load_records

SCHOOL_NAME_KEYWORDS = (
    "SCHOOL",
    "SCH",
    "TEAM",
    "CLUB",
    "CLB",
    "CSNAM",
    "ORG",
)


@dataclass
class FieldStats:
    table: str
    field: str
    non_empty_count: int
    unique_count: int
    top_values: list[tuple[str, int]]
    looks_like_school_field: bool


def _looks_text(value: Any) -> bool:
    return isinstance(value, str)


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def _is_school_like_field(field_name: str) -> bool:
    upper = field_name.upper()
    return any(keyword in upper for keyword in SCHOOL_NAME_KEYWORDS)


def collect_stats(base_dir: Path, top_limit: int) -> list[FieldStats]:
    stats: list[FieldStats] = []
    for dbf_path in iter_dbf_files(base_dir):
        records, _enc = load_records(dbf_path)
        if not records:
            continue

        field_names = list(records[0].keys())
        for field_name in field_names:
            values: list[str] = []
            for rec in records:
                raw = rec.get(field_name)
                if not _looks_text(raw):
                    continue
                text = _normalize_text(raw)
                if not text:
                    continue
                values.append(text)
            if not values:
                continue

            counter = Counter(values)
            stats.append(
                FieldStats(
                    table=dbf_path.stem.upper(),
                    field=field_name,
                    non_empty_count=len(values),
                    unique_count=len(counter),
                    top_values=counter.most_common(top_limit),
                    looks_like_school_field=_is_school_like_field(field_name),
                )
            )
    return stats


def print_report(stats: list[FieldStats]) -> None:
    school_like = [s for s in stats if s.looks_like_school_field]
    school_like.sort(key=lambda x: (x.table, x.field))

    print("=== Candidate fields for school/club/team ===")
    if not school_like:
        print("No candidate fields found by field name.")
    for s in school_like:
        print(f"\n[{s.table}.{s.field}] non-empty={s.non_empty_count} unique={s.unique_count}")
        for value, count in s.top_values:
            print(f"  {count:>4} | {value}")

    print("\n=== All text fields (summary) ===")
    all_sorted = sorted(stats, key=lambda x: (x.table, x.field))
    for s in all_sorted:
        mark = "*" if s.looks_like_school_field else " "
        print(f"{mark} {s.table}.{s.field}: non-empty={s.non_empty_count}, unique={s.unique_count}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan all DBF fields and show where school/club names are stored."
    )
    parser.add_argument(
        "base_dir",
        type=Path,
        help="Path to CalcFS folder with DBF files (for example: ./21220326БеккерФМ)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="How many most frequent values to show per field (default: 20)",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path to save full scan results as JSON",
    )
    args = parser.parse_args()

    base_dir = args.base_dir
    if not base_dir.is_dir():
        raise NotADirectoryError(str(base_dir))

    stats = collect_stats(base_dir, top_limit=max(1, int(args.top)))
    print_report(stats)

    if args.json_out:
        payload = [
            {
                "table": s.table,
                "field": s.field,
                "non_empty_count": s.non_empty_count,
                "unique_count": s.unique_count,
                "top_values": s.top_values,
                "looks_like_school_field": s.looks_like_school_field,
            }
            for s in stats
        ]
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSaved JSON report: {args.json_out}")


if __name__ == "__main__":
    main()
