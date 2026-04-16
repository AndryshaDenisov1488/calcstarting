from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from calcfs_pdf_export.calcfs_store import _id_key, load_calcfs_folder
from calcfs_pdf_export.dbf_utils import rec_get
from calcfs_pdf_export.ids import normalize_id


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _iter_named_values(pct: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for field in (
        "PCT_CNAME",
        "PCT_PLNAME",
        "PCT_SNAME",
        "PCT_PSNAME",
        "PCT_TLNAME",
        "PCT_TSNAME",
        "PCT_SCHOOL",
        "PCT_TEAM",
        "PCT_SCHOOLNAME",
    ):
        val = _norm(pct.get(field))
        if val:
            out.append((field, val))
    return out


def _iter_clb_values(clb: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for field in (
        "CLB_NAME",
        "CLB_CNAME",
        "CLB_LONGNAME",
        "CLB_PAPERFULLNAME",
        "PAPER_FULL_NAME",
        "PAPERFULLNAME",
        "NAME",
    ):
        val = _norm(clb.get(field))
        if val:
            out.append((field, val))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dump all school-like values with source tags for CalcFS DBF folder."
    )
    parser.add_argument("base_dir", type=Path, help="Path to CalcFS folder, e.g. C:\\ISUCalcFS\\11042026")
    parser.add_argument("--json-out", type=Path, default=None, help="Optional path for JSON output")
    parser.add_argument("--top", type=int, default=500, help="Max schools to print in terminal")
    parser.add_argument(
        "--include-non-full",
        action="store_true",
        help="Include non-full tags (search/list/short variants) in JSON payload",
    )
    args = parser.parse_args()

    snapshot = load_calcfs_folder(args.base_dir)
    par_by = snapshot.par
    pct_by = _id_key(snapshot.pct, "PCT_ID", "ID")
    clb_by = _id_key(snapshot.clb, "CLB_ID", "ID")

    schools: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[str, list[str]] = defaultdict(list)

    for par in par_by:
        par_id = _norm(rec_get(par, "PAR_ID", "ID"))
        pct_id = normalize_id(rec_get(par, "PCT_ID"))
        pct = pct_by.get(pct_id)
        if not pct:
            continue

        for tag, val in _iter_named_values(pct):
            schools[val][tag] += 1
            if len(examples[val]) < 3:
                examples[val].append(f"PAR_ID={par_id}, PCT_ID={_norm(pct_id)}")

        # Link by PAR_CLBID -> PCT_ID (used in some CalcFS bases)
        clb_pct = pct_by.get(normalize_id(rec_get(par, "PAR_CLBID", "PCT_CLBID", "CLB_ID")))
        if clb_pct:
            for tag, val in _iter_named_values(clb_pct):
                schools[val][f"PAR_CLBID->{tag}"] += 1
                if len(examples[val]) < 3:
                    examples[val].append(
                        f"PAR_ID={par_id}, PCT_ID={_norm(pct_id)}, PAR_CLBID={_norm(rec_get(par, 'PAR_CLBID'))}"
                    )
        clb = clb_by.get(normalize_id(rec_get(par, "PAR_CLBID", "CLB_ID")))
        if clb:
            for tag, val in _iter_clb_values(clb):
                schools[val][f"PAR_CLBID->CLB.{tag}"] += 1
                if len(examples[val]) < 3:
                    examples[val].append(
                        f"PAR_ID={par_id}, PCT_ID={_norm(pct_id)}, PAR_CLBID={_norm(rec_get(par, 'PAR_CLBID'))}"
                    )

    rows = sorted(
        schools.items(),
        key=lambda x: sum(x[1].values()),
        reverse=True,
    )

    def _is_full_tag(tag: str) -> bool:
        upper = tag.upper()
        if "SEARCH" in upper:
            return False
        if "LIST" in upper:
            return False
        if "SNAME" in upper or "TSNAME" in upper or "PSNAME" in upper:
            return False
        return any(x in upper for x in ("NAME", "CNAME", "LONGNAME", "PAPERFULL", "PAPER_FULL"))

    print("=== Schools from FULL-NAME sources only ===")
    full_rows: list[tuple[str, Counter[str], int]] = []
    for school, tags in rows:
        full_tags = Counter({k: v for k, v in tags.items() if _is_full_tag(k)})
        if not full_tags:
            continue
        full_rows.append((school, full_tags, sum(full_tags.values())))
    full_rows.sort(key=lambda x: x[2], reverse=True)
    for idx, (school, tags, total) in enumerate(full_rows[: max(1, args.top)], start=1):
        tags_txt = ", ".join(f"{k}:{v}" for k, v in tags.most_common())
        ex = " | ".join(examples.get(school, []))
        print(f"{idx:>3}. {school}")
        print(f"     total={total}; tags=[{tags_txt}]")
        if ex:
            print(f"     examples: {ex}")

    print("\n=== All schools with all source tags ===")
    for idx, (school, tags) in enumerate(rows[: max(1, args.top)], start=1):
        total = sum(tags.values())
        tags_txt = ", ".join(f"{k}:{v}" for k, v in tags.most_common())
        ex = " | ".join(examples.get(school, []))
        print(f"{idx:>3}. {school}")
        print(f"     total={total}; tags=[{tags_txt}]")
        if ex:
            print(f"     examples: {ex}")

    payload_full = [
        {
            "school": school,
            "total": int(total),
            "tags": dict(tags),
            "examples": examples.get(school, []),
        }
        for school, tags, total in full_rows
    ]
    payload_all = [
        {
            "school": school,
            "total": int(sum(tags.values())),
            "tags": dict(tags),
            "examples": examples.get(school, []),
        }
        for school, tags in rows
    ]
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        payload = payload_all if args.include_non_full else payload_full
        args.json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSaved JSON: {args.json_out}")


if __name__ == "__main__":
    main()
