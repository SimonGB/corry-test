@echo off
cd /d "%~dp0"
echo === FP Mailer Diagnose ===
echo.
if not exist ".venv\Scripts\python.exe" (
  echo FEHLER: .venv wurde nicht korrekt erstellt.
  echo Bitte INSTALLIEREN.bat erneut ausfuehren.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -c "import sys, ssl; print('Python:', sys.executable); print('Version:', sys.version); print('SSL:', ssl.OPENSSL_VERSION)"
echo.
".venv\Scripts\python.exe" -c "import tkinter, requests, bs4, keyring; print('Pakete: OK')"
echo.
echo Falls oben ein Fehler steht, kopiere die komplette Ausgabe in ChatGPT.
pause
