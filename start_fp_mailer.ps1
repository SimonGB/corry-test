$ErrorActionPreference = "SilentlyContinue"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$Pythonw = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
$Gui = Join-Path $ProjectDir "fp_mailer_gui.py"

Add-Type -AssemblyName PresentationFramework

function Show-Error([string]$Message) {
    [System.Windows.MessageBox]::Show(
        $Message,
        "FP Mailer",
        [System.Windows.MessageBoxButton]::OK,
        [System.Windows.MessageBoxImage]::Error
    ) | Out-Null
}

if (-not (Test-Path $Python) -or -not (Test-Path $Pythonw)) {
    Show-Error "FP Mailer ist noch nicht korrekt installiert. Bitte im Projektordner INSTALLIEREN.bat doppelklicken."
    exit 1
}

$check = & $Python -c "import ssl, tkinter, requests, bs4, keyring" 2>&1
if ($LASTEXITCODE -ne 0) {
    Show-Error ("Die FP-Mailer-Installation ist unvollstaendig.`n`n" + ($check -join "`n") + "`n`nBitte INSTALLIEREN.bat erneut ausfuehren.")
    exit 1
}

Start-Process -FilePath $Pythonw -ArgumentList ('"' + $Gui + '"') -WorkingDirectory $ProjectDir
