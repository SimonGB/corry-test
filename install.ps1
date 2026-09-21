param([switch]$NoPause)
$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

function Pause-IfNeeded {
    if (-not $NoPause) { Read-Host "Enter zum Beenden" | Out-Null }
}

function Test-PythonCandidate([string]$PythonPath) {
    if (-not $PythonPath -or -not (Test-Path $PythonPath)) { return $false }
    try {
        $null = & $PythonPath -c "import ssl, tkinter, venv; print(ssl.OPENSSL_VERSION)" 2>&1
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Find-UsablePython {
    $candidates = New-Object System.Collections.Generic.List[string]

    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            $lines = & py -0p 2>$null
            foreach ($line in $lines) {
                if ($line -match '([A-Za-z]:\.*python(?:\.exe)?)\s*$') {
                    $candidates.Add($Matches[1].Trim())
                }
            }
        } catch {}
    }

    foreach ($name in @("python", "python3")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source) { $candidates.Add($cmd.Source) }
    }

    $roots = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python"),
        "C:\Program Files\Python*"
    )
    foreach ($root in $roots) {
        if ($root -like '***') {
            Get-ChildItem $root -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                $p = Join-Path $_.FullName "python.exe"
                if (Test-Path $p) { $candidates.Add($p) }
            }
        } elseif (Test-Path $root) {
            Get-ChildItem $root -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending | ForEach-Object {
                $p = Join-Path $_.FullName "python.exe"
                if (Test-Path $p) { $candidates.Add($p) }
            }
        }
    }

    $seen = @{}
    foreach ($candidate in $candidates) {
        if ($seen.ContainsKey($candidate)) { continue }
        $seen[$candidate] = $true
        Write-Host "Pruefe Python: $candidate"
        if (Test-PythonCandidate $candidate) {
            return $candidate
        }
    }
    return $null
}

Write-Host "=== FP Mailer Installation ===" -ForegroundColor Cyan
Write-Host "Pruefe zuerst eine Python-Installation mit SSL, Tkinter und venv ..."

$python = Find-UsablePython

if (-not $python) {
    Write-Host ""
    Write-Host "Es wurde keine verwendbare Python-Installation gefunden." -ForegroundColor Red
    Write-Host "Mindestens eine gefundene Python-Version hat kein funktionierendes SSL-Modul."
    Write-Host "Das ist genau die Ursache fuer die Meldung 'ssl module in Python is not available'."
    Write-Host ""

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        $answer = Read-Host "Soll ich die offizielle Python-3.12-Version jetzt per winget installieren? (J/N)"
        if ($answer -match '^[JjYy]') {
            Write-Host "Installiere offizielle Python-Version ..." -ForegroundColor Yellow
            & winget install --id Python.Python.3.12 -e --scope user --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) {
                Write-Host "Die Python-Installation ueber winget ist fehlgeschlagen." -ForegroundColor Red
                Write-Host "Bitte Python manuell von https://www.python.org/downloads/windows/ installieren."
                Pause-IfNeeded
                exit 1
            }
            Start-Sleep -Seconds 2
            $python = Find-UsablePython
        }
    }

    if (-not $python) {
        Write-Host ""
        Write-Host "Bitte installiere Python 3.12 oder neuer von:" -ForegroundColor Yellow
        Write-Host "https://www.python.org/downloads/windows/"
        Write-Host "Danach INSTALLIEREN.bat erneut doppelklicken."
        Write-Host ""
        Write-Host "Wichtig: Eine vorhandene kaputte Python-Version musst du nicht zwingend deinstallieren;"
        Write-Host "der neue Installer sucht automatisch eine funktionierende Version heraus."
        Pause-IfNeeded
        exit 1
    }
}

Write-Host ""
Write-Host "Verwendetes Python: $python" -ForegroundColor Green
& $python -c "import sys, ssl; print('Python', sys.version.split()[0], '-', ssl.OPENSSL_VERSION)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Python-Selbsttest ist unerwartet fehlgeschlagen." -ForegroundColor Red
    Pause-IfNeeded
    exit 1
}

if (Test-Path ".venv") {
    Write-Host "Entferne vorhandene virtuelle Umgebung und erstelle sie sauber neu ..."
    Remove-Item ".venv" -Recurse -Force
}

Write-Host "Erstelle virtuelle Umgebung ..."
& $python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Virtuelle Umgebung konnte nicht erstellt werden." }

$venvPython  = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$venvPythonw = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"

Write-Host "Pruefe SSL in der neuen Umgebung ..."
& $venvPython -c "import ssl; print(ssl.OPENSSL_VERSION)"
if ($LASTEXITCODE -ne 0) { throw "SSL funktioniert auch in der neuen virtuellen Umgebung nicht." }

Write-Host "Installiere benoetigte Pakete ..."
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip konnte nicht aktualisiert werden." }

& $venvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Die benoetigten Python-Pakete konnten nicht installiert werden." }

Write-Host "Fuehre Endtest durch ..."
& $venvPython -c "import ssl, tkinter, requests, bs4, keyring; print('Alle Module OK')"
if ($LASTEXITCODE -ne 0) { throw "Der Endtest der Python-Module ist fehlgeschlagen." }

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "FP Mailer.lnk"
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($shortcutPath)
$sc.TargetPath = "powershell.exe"
$sc.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $ProjectDir "start_fp_mailer.ps1") + '"'
$sc.WorkingDirectory = $ProjectDir
$sc.Description = "FP Elektroniker-Grundpraktikum - naechste Gruppen pruefen (Dry Run)"
$sc.IconLocation = "$env:SystemRoot\System32\shell32.dll,220"
$sc.Save()

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host "Installation erfolgreich." -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green
Write-Host "Auf dem Desktop liegt jetzt: FP Mailer"
Write-Host "Beim ersten Start werden Uni-ID und Passwort einmal abgefragt."
Write-Host "Das Passwort wird im Windows Credential Manager gespeichert."
Write-Host "Diese Version ist weiterhin DRY RUN und kann keine E-Mail senden."
Pause-IfNeeded
