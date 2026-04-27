from __future__ import annotations

import os
import datetime as dt
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dbfread import DBF


RPT_DIR = Path(r"C:\ISUCalcFS\reports\RpXiEn")
ODBC_DSN = "ISUCalcFS_Report"
ODBC_REG_PATH = r"HKCU:\Software\ODBC\ODBC.INI\ISUCalcFS_Report"


@dataclass(frozen=True)
class CrystalReportSpec:
    key: str
    filename: str
    title: str
    requires_segment: bool


RESULT_WITH_CLUB_NAMES = CrystalReportSpec(
    key="result",
    filename="ResultWithClubNamesApp.rpt",
    title="ResultWithClubNames",
    requires_segment=False,
)
RESULT_FOR_SEGMENT_DETAILS = CrystalReportSpec(
    key="segment_details",
    filename="ResultForSegmentDetailsApp.rpt",
    title="ResultForSegmentDetails",
    requires_segment=True,
)
JUDGES_SCORES = CrystalReportSpec(
    key="judges_scores",
    filename="JudgesScores_woSJDApp.rpt",
    title="JudgesScores",
    requires_segment=True,
)


class CrystalRptError(RuntimeError):
    pass


def _powershell_32_path() -> Path:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    return windir / "SysWOW64" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


def _ps_quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _formula_value(value: Any) -> str:
    try:
        f = float(value)
        if f == int(f):
            return str(int(f))
        return str(f)
    except (TypeError, ValueError):
        return "'" + str(value).replace("'", "''") + "'"


def crystal_selection_formula(cat_id: Any, scp_id: Any | None = None) -> str:
    parts = [f"{{CAT.CAT_ID}}={_formula_value(cat_id)}"]
    if scp_id is not None:
        parts.append(f"{{SCP.SCP_ID}}={_formula_value(scp_id)}")
    return " and ".join(parts)


def _same_id(a: Any, b: Any) -> bool:
    try:
        return int(float(a)) == int(float(b))
    except (TypeError, ValueError):
        return str(a).strip() == str(b).strip()


def _load_dbf(path: Path) -> list[dict[str, Any]]:
    return [dict(r) for r in DBF(path, encoding="cp1251", load=True, ignore_missing_memofile=True)]


def _copy_base_files(base_dir: Path, temp_dir: Path) -> None:
    for path in base_dir.iterdir():
        if path.is_file():
            shutil.copy2(path, temp_dir / path.name)


def _format_dbf_value(value: Any, field: Any, encoding: str = "cp1251") -> bytes:
    length = int(field.length)
    ftype = str(field.type)
    if value is None:
        value = ""
    if ftype in {"C", "M"}:
        raw = str(value).encode(encoding, errors="replace")[:length]
        return raw.ljust(length, b" ")
    if ftype in {"N", "F", "B", "Y"}:
        if value == "":
            value = 0
        try:
            number = float(value)
            if int(field.decimal_count):
                text = f"{number:>{length}.{int(field.decimal_count)}f}"
            else:
                text = f"{int(round(number)):>{length}d}"
        except (TypeError, ValueError, OverflowError):
            text = ""
        return text[-length:].rjust(length).encode("ascii", errors="replace")
    if ftype == "D":
        if isinstance(value, (dt.datetime, dt.date)):
            text = value.strftime("%Y%m%d")
        else:
            text = str(value).replace("-", "").replace(".", "")[:8] if value else ""
        return text.encode("ascii", errors="replace").ljust(length, b" ")
    if ftype == "L":
        text = "T" if bool(value) else "F"
        return text.encode("ascii")
    return str(value).encode(encoding, errors="replace")[:length].ljust(length, b" ")


def _write_dbf_like(template_path: Path, output_path: Path, rows: list[dict[str, Any]]) -> None:
    table = DBF(template_path, encoding="cp1251", load=False, ignore_missing_memofile=True)
    with template_path.open("rb") as f:
        header = bytearray(f.read(table.header.headerlen))
    today = dt.date.today()
    header[1] = today.year - 1900
    header[2] = today.month
    header[3] = today.day
    header[4:8] = len(rows).to_bytes(4, "little", signed=False)

    with output_path.open("wb") as f:
        f.write(header)
        for row in rows:
            f.write(b" ")
            for field in table.fields:
                f.write(_format_dbf_value(row.get(field.name), field))
        f.write(b"\x1A")


def _field_text_limit(path: Path, field_name: str, default: int = 50) -> int:
    try:
        table = DBF(path, encoding="cp1251", load=False, ignore_missing_memofile=True)
        for field in table.fields:
            if field.name.upper() == field_name.upper():
                return int(field.length)
    except Exception:
        return default
    return default


def _fits_dbf_text(value: str, limit: int, encoding: str = "cp1251") -> bool:
    return len(value.encode(encoding, errors="replace")) <= limit


def _split_for_dbf_fields(value: str, first_limit: int, second_limit: int, encoding: str = "cp1251") -> tuple[str, str]:
    text = " ".join(str(value or "").replace("\r\n", "\n").replace("\r", "\n").split())
    if not text:
        return "", ""
    if _fits_dbf_text(text, first_limit, encoding):
        return text, ""

    parts = [part.strip() for part in text.split(",") if part.strip()]
    first_parts: list[str] = []
    rest_parts: list[str] = []
    for part in parts:
        candidate = ", ".join(first_parts + [part])
        if first_parts and not _fits_dbf_text(candidate, first_limit, encoding):
            rest_parts.append(part)
        elif not first_parts and not _fits_dbf_text(candidate, first_limit, encoding):
            rest_parts.append(part)
        else:
            first_parts.append(part)
    first = ", ".join(first_parts)
    second = ", ".join(rest_parts)
    if _fits_dbf_text(second, second_limit, encoding):
        return first, second

    encoded = second.encode(encoding, errors="replace")[:second_limit]
    return first, encoded.decode(encoding, errors="ignore").rstrip(" ,")


def _split_category_title(title: str, *, tvname_limit: int = 50, name2l_limit: int = 50) -> tuple[str, str, str]:
    lines = [line.strip() for line in title.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    if len(lines) >= 2:
        main_title = ", ".join(lines[:2])
        age_title = ", ".join(lines[2:])
        age_part_1, age_part_2 = _split_for_dbf_fields(age_title, tvname_limit, name2l_limit)
        return main_title, age_part_1, age_part_2
    return title.strip(), "", ""


def _apply_category_title_overrides(temp_dir: Path, category_title_overrides: dict[Any, str] | None) -> None:
    if not category_title_overrides:
        return
    cat_path = temp_dir / "CAT.DBF"
    if not cat_path.is_file():
        return
    tvname_limit = _field_text_limit(cat_path, "CAT_TVNAME")
    name2l_limit = _field_text_limit(cat_path, "CAT_NAME2L")
    rows = _load_dbf(cat_path)
    for row in rows:
        for cat_id, title in category_title_overrides.items():
            if _same_id(row.get("CAT_ID"), cat_id):
                main_title, age_part_1, age_part_2 = _split_category_title(
                    title,
                    tvname_limit=tvname_limit,
                    name2l_limit=name2l_limit,
                )
                row["CAT_NAME"] = main_title
                row["CAT_TVNAME"] = age_part_1
                row["CAT_NAME2L"] = age_part_2
                break
    _write_dbf_like(cat_path, cat_path, rows)


def _prepare_pprf_rows(base_dir: Path, cat_id: Any, scp_id: Any) -> list[dict[str, Any]]:
    prf_rows = _load_dbf(base_dir / "PRF.DBF")
    par_rows = _load_dbf(base_dir / "PAR.DBF")
    par_by_id = {str(p.get("PAR_ID")).strip(): p for p in par_rows}
    selected: list[dict[str, Any]] = []
    for prf in prf_rows:
        if not _same_id(prf.get("SCP_ID"), scp_id):
            continue
        par = par_by_id.get(str(prf.get("PAR_ID")).strip())
        if not par or not _same_id(par.get("CAT_ID"), cat_id):
            continue
        if str(prf.get("PRF_STAT") or "").strip() != "O":
            continue
        try:
            if int(prf.get("PRF_PLACE") or 0) <= 0:
                continue
        except (TypeError, ValueError):
            continue
        row = dict(prf)
        row["PCT_ID"] = par.get("PCT_ID")
        row.setdefault("TEM_ID", 0)
        row.setdefault("CTE_ID", 0)
        selected.append(row)
    return selected


def _prepare_jes_rows(pprf_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for prf in pprf_rows:
        row: dict[str, Any] = {
            "JES_ID": prf.get("PRF_ID"),
            "PAR_ID": prf.get("PAR_ID"),
            "SCP_ID": prf.get("SCP_ID"),
            "JES_STNUM": prf.get("PRF_STNUM"),
            "JES_STGNUM": prf.get("PRF_STGNUM"),
            "JES_PLACE": prf.get("PRF_PLACE"),
            "JES_INDEX": prf.get("PRF_INDEX"),
        }
        for element in range(1, 21):
            ekey = f"{element:02d}"
            row[f"JES_MINE{ekey}"] = 2
            row[f"JES_CASE{ekey}"] = "0000000000000000"
            row[f"JES_GOAV{ekey}"] = prf.get(f"PRF_E{ekey}RES")
            row[f"JES_ELBO{ekey}"] = prf.get(f"PRF_XBVE{ekey}")
            row[f"JES_E{ekey}DED"] = prf.get(f"PRF_E{ekey}DED")
            for judge in range(1, 16):
                jkey = f"{judge:02d}"
                row[f"JES_J{jkey}E{ekey}"] = prf.get(f"PRF_E{ekey}J{jkey}")
        for component in range(1, 11):
            ckey = f"{component:02d}"
            row[f"JES_MINC{ckey}"] = 2
            row[f"JES_CASC{ckey}"] = "0000000000000000"
            row[f"JES_CRAV{ckey}"] = prf.get(f"PRF_C{ckey}RES")
            for judge in range(1, 16):
                jkey = f"{judge:02d}"
                row[f"JES_J{jkey}C{ckey}"] = prf.get(f"PRF_C{ckey}J{jkey}")
        for deduction in range(1, 4):
            dkey = f"{deduction:02d}"
            row[f"JES_JDED{dkey}"] = prf.get(f"PRF_DED{dkey}")
            for judge in range(1, 16):
                jkey = f"{judge:02d}"
                row[f"JES_J{jkey}D{dkey}"] = prf.get(f"PRF_D{dkey}J{jkey}")
        rows.append(row)
    return rows


def _prepare_report_temp_base(
    base_dir: Path,
    *,
    category_title_overrides: dict[Any, str] | None = None,
    cat_id: Any | None = None,
    scp_id: Any | None = None,
) -> tempfile.TemporaryDirectory[str]:
    temp = tempfile.TemporaryDirectory(prefix="calcfs_rpt_base_")
    temp_dir = Path(temp.name)
    _copy_base_files(base_dir, temp_dir)
    _apply_category_title_overrides(temp_dir, category_title_overrides)
    if cat_id is not None and scp_id is not None:
        pprf_rows = _prepare_pprf_rows(base_dir, cat_id, scp_id)
        _write_dbf_like(base_dir / "PPRF.DBF", temp_dir / "PPRF.DBF", pprf_rows)
        _write_dbf_like(base_dir / "JES.DBF", temp_dir / "JES.DBF", _prepare_jes_rows(pprf_rows))
    return temp


def export_crystal_report_pdf(
    *,
    base_dir: Path,
    report_spec: CrystalReportSpec,
    output_pdf: Path,
    cat_id: Any,
    scp_id: Any | None = None,
    rpt_dir: Path = RPT_DIR,
    category_title_overrides: dict[Any, str] | None = None,
    rpt_path_override: Path | None = None,
) -> Path:
    rpt_path = rpt_path_override or (rpt_dir / report_spec.filename)
    if not rpt_path.is_file():
        raise FileNotFoundError(f"Не найден Crystal report: {rpt_path}")
    if report_spec.requires_segment and scp_id is None:
        raise ValueError(f"{report_spec.title} требует SCP_ID")

    base_dir = base_dir.resolve()
    output_pdf = output_pdf.resolve()
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    formula = crystal_selection_formula(cat_id, scp_id)
    ps_exe = _powershell_32_path()
    if not ps_exe.is_file():
        raise CrystalRptError(f"Не найден 32-bit PowerShell: {ps_exe}")

    temp_base: tempfile.TemporaryDirectory[str] | None = None
    report_base_dir = base_dir
    if report_spec.requires_segment or category_title_overrides:
        temp_base = _prepare_report_temp_base(
            base_dir,
            category_title_overrides=category_title_overrides,
            cat_id=cat_id if report_spec.requires_segment else None,
            scp_id=scp_id if report_spec.requires_segment else None,
        )
        report_base_dir = Path(temp_base.name)
    needs_rv_workaround = report_spec.key == "result"
    rv_path = rpt_path.parent.parent.parent / "im" / "standcat.xls"
    rv_preexisting = rv_path.exists()

    script = f"""
$ErrorActionPreference = 'Stop'
$dsnPath = { _ps_quote(ODBC_REG_PATH) }
$base = { _ps_quote(report_base_dir) }
$rpt = { _ps_quote(rpt_path) }
$out = { _ps_quote(output_pdf) }
$formula = { _ps_quote(formula) }
$needsRv = ${str(needs_rv_workaround).lower()}
$old = $null
$jesBackups = @()
$rvCreated = $false
$rvPath = Join-Path (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $rpt))) 'im\standcat.xls'
try {{
  if ($needsRv -and !(Test-Path $rvPath)) {{
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $rvPath) | Out-Null
    $excel = New-Object -ComObject Excel.Application
    $excel.DisplayAlerts = $false
    $wb = $excel.Workbooks.Add()
    $ws = $wb.Worksheets.Item(1)
    $ws.Name = 'RV'
    $ws.Cells.Item(1, 1).Value2 = 'index'
    $ws.Cells.Item(1, 2).Value2 = 'award'
    $ws.Cells.Item(2, 1).Value2 = 0
    $ws.Cells.Item(2, 2).Value2 = ''
    $wb.SaveAs($rvPath, -4143)
    $wb.Close($false)
    $excel.Quit()
    $rvCreated = $true
  }}
  $old = (Get-ItemProperty $dsnPath).SourceDB
  Set-ItemProperty $dsnPath -Name SourceDB -Value $base
  $app = New-Object -ComObject CrystalRuntime.Application
  $report = $app.OpenReport($rpt)
  $report.EnableParameterPrompting = $false
  try {{
    for ($i=1; $i -le $report.FormulaFields.Count; $i++) {{
      $formulaField = $report.FormulaFields.Item($i)
      $formulaName = ''
      try {{ $formulaName = [string]$formulaField.Name }} catch {{}}
      if ($formulaName -match '^\{{?@?MessageL[Ii]ne[12]\}}?$') {{
        $formulaField.Text = '""'
      }}
    }}
  }} catch {{}}
  for ($i=1; $i -le $report.Database.Tables.Count; $i++) {{
    $table = $report.Database.Tables.Item($i)
    if ($table.Name -eq 'RV_') {{
      # ResultWithClubNames.rpt has an Excel RV$ table; keep its native binding.
    }} elseif ($table.Name -eq 'JES') {{
      $jes = Join-Path $base 'JES.DBF'
      $target = $null
      try {{ $target = [string]$table.LogOnServerName }} catch {{}}
      if ((Test-Path $jes) -and $target -and $target.ToLower().EndsWith('jes.dbf')) {{
        $targetDir = Split-Path -Parent $target
        if ($targetDir) {{ New-Item -ItemType Directory -Force -Path $targetDir | Out-Null }}
        $backup = $null
        if (Test-Path $target) {{
          $backup = $target + '.calcfs_pdf_export.bak'
          Copy-Item $target $backup -Force
        }}
        Copy-Item $jes $target -Force
        $jesBackups += [pscustomobject]@{{ Target = $target; Backup = $backup }}
      }} elseif (Test-Path $jes) {{
        try {{ $table.SetLogOnInfo($jes, '', '', '') }} catch {{}}
        try {{ $table.ConnectBufferString = 'Data File=' + $jes }} catch {{}}
      }}
    }} else {{
      try {{ $table.SetLogOnInfo({ _ps_quote(ODBC_DSN) }, '', '', '') }} catch {{}}
      try {{ $table.ConnectBufferString = 'DSN={ ODBC_DSN };SourceDB=' + $base + ';SourceType=DBF;Exclusive=No;' }} catch {{}}
    }}
  }}
  try {{ $report.DiscardSavedData() }} catch {{}}
  $report.RecordSelectionFormula = $formula
  $report.ExportOptions.DestinationType = 1
  $report.ExportOptions.FormatType = 31
  $report.ExportOptions.DiskFileName = $out
  $report.Export($false)
  if (!(Test-Path $out)) {{ throw 'Crystal export finished without output PDF.' }}
  Write-Output ('OK ' + $out)
}} finally {{
  foreach ($item in $jesBackups) {{
    try {{
      if ($item.Backup -and (Test-Path $item.Backup)) {{
        Move-Item $item.Backup $item.Target -Force
      }} elseif ($item.Target -and (Test-Path $item.Target)) {{
        Remove-Item $item.Target -Force
      }}
    }} catch {{}}
  }}
  if ($old -ne $null) {{
    try {{ Set-ItemProperty $dsnPath -Name SourceDB -Value $old }} catch {{}}
  }}
  if ($rvCreated -and (Test-Path $rvPath)) {{
    try {{
      $report = $null
      $app = $null
      [System.GC]::Collect()
      [System.GC]::WaitForPendingFinalizers()
      Start-Sleep -Milliseconds 200
      Remove-Item $rvPath -Force
    }} catch {{}}
  }}
}}
"""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8-sig") as f:
            script_path = Path(f.name)
            f.write(script)
        try:
            proc = subprocess.run(
                [str(ps_exe), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        finally:
            try:
                script_path.unlink()
            except OSError:
                pass
    finally:
        if temp_base is not None:
            temp_base.cleanup()
        if needs_rv_workaround and not rv_preexisting and rv_path.exists():
            try:
                rv_path.unlink()
            except OSError:
                pass

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise CrystalRptError(f"Crystal export failed for {report_spec.title}: {detail}")
    return output_pdf
