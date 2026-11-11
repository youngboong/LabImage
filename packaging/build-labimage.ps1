param([string]$Python = ".\.venv\Scripts\python.exe")
$ErrorActionPreference = "Stop"
$labRoot = Split-Path -Parent $PSScriptRoot
Push-Location $labRoot
try {
    & $Python -m PyInstaller packaging/LabImage.spec --workpath build/labimage --noconfirm
    if ($LASTEXITCODE -ne 0) { throw "LabImage build failed. Check the build log." }
    Write-Output "Built: $labRoot\dist\LabImage\LabImage.exe"
} finally { Pop-Location }
