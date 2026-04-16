# Сборка одного переносного CalcFSPdfExport.exe (PyInstaller one-file).
# Требуется: .venv с зависимостями из requirements.txt
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}
& .\.venv\Scripts\pip.exe install -r requirements.txt pyinstaller
& .\.venv\Scripts\pyinstaller.exe --noconfirm --clean CalcFSPdfExport.spec
Write-Host "Done: $root\dist\CalcFSPdfExport.exe"
