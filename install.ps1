param([switch]$NoPause)
$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

Write-Host "=== FP Mailer Installation ===" -ForegroundColor Cyan

$python = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $python = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = "python"
} else {
    Write-Host "Python wurde nicht gefunden." -ForegroundColor Red
    Write-Host "Bitte Python 3 von https://www.python.org/downloads/windows/ installieren."
    Write-Host "Beim Installer 'Add python.exe to PATH' aktivieren, danach install.ps1 erneut starten."
    if (-not $NoPause) { Read-Host "Enter zum Beenden" }
    exit 1
}

if (-not (Test-Path ".venv")) {
    & $python -m venv .venv
}
$venvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$venvPythonw = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "FP Mailer.lnk"
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($shortcutPath)
$sc.TargetPath = $venvPythonw
$sc.Arguments = '"' + (Join-Path $ProjectDir 'fp_mailer_gui.py') + '"'
$sc.WorkingDirectory = $ProjectDir
$sc.Description = "FP Elektroniker-Grundpraktikum – nächste Gruppen prüfen (Dry Run)"
$sc.IconLocation = "$env:SystemRoot\System32\shell32.dll,220"
$sc.Save()

Write-Host ""
Write-Host "Fertig." -ForegroundColor Green
Write-Host "Auf dem Desktop liegt jetzt: FP Mailer"
Write-Host "Beim ersten Start werden Uni-ID und Passwort einmal abgefragt."
Write-Host "Das Passwort wird im Windows Credential Manager gespeichert, nicht im Projektordner."
Write-Host "Diese Version ist absichtlich DRY RUN und kann keine E-Mail senden."
if (-not $NoPause) { Read-Host "Enter zum Beenden" }
