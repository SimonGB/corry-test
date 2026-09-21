# FP Mailer – Desktop Dry Run

Kleine Windows-Anwendung für Betreuer des Heidelberger Fortgeschrittenenpraktikums.
Sie liest die FP-Testatseite aus, findet den **nächsten tatsächlich belegten Termin**
für E01/E06/E07/E08/E09 und zeigt eine fertige Rundmail als Vorschau an.

> **Sicherheitszustand dieser Version:** Sie kann **keine E-Mail verschicken**. Es gibt
> absichtlich keinen SMTP-/Send-Code. Ein Doppelklick führt nur einen Dry Run aus.

## Was passiert beim Doppelklick?

1. Login auf `https://www.physi.uni-heidelberg.de/cgi-bin/fp/fp-testate.pl`
2. Es werden nur Tabellenzeilen mit Status `eingeteilt` ausgewertet.
3. Das Programm sucht den frühesten noch nicht vergangenen Termin.
4. Nur die tatsächlich belegten E01/E06/E07/E08/E09 werden übernommen.
5. Die Empfänger werden aus den `mail.pl?email=...`-Links ausgelesen und dedupliziert.
6. Betreff und Mailtext werden erzeugt.
7. Eine Vorschau öffnet sich. **Nichts wird versendet.**

Der Parser wurde gegen den gespeicherten Betreuerseiten-Snapshot vom September 2026 getestet.

## Installation auf Windows

### 1. Python installieren

Falls Python noch nicht installiert ist, Python 3 von python.org installieren.
Beim Windows-Installer am besten **Add python.exe to PATH** aktivieren.

### 2. Projekt herunterladen

ZIP entpacken, z. B. nach:

`C:\Users\<Name>\Documents\fp-mailer-desktop`

Den Ordner danach nicht mehr verschieben, weil die Desktop-Verknüpfung auf diesen Pfad zeigt.
Falls du ihn doch verschiebst, `INSTALLIEREN.bat` einfach erneut starten.

### 3. Einmal installieren

Doppelklick auf:

`INSTALLIEREN.bat`

Das Skript erstellt automatisch:

- eine eigene Python-Umgebung `.venv`
- alle benötigten Python-Pakete
- ein Desktop-Icon **FP Mailer**

### 4. Erster Start

Doppelklick auf **FP Mailer** auf dem Desktop.

Beim ersten Start fragt die Anwendung nach:

- Uni-ID
- Uni-Passwort

Die Uni-ID wird lokal in `%LOCALAPPDATA%\FP-Mailer\config.json` gespeichert.
Das Passwort wird über das Python-Paket `keyring` im **Windows Credential Manager**
gespeichert und steht weder im Quellcode noch in einer normalen Textdatei.

Danach genügt bei zukünftigen Starts ein Doppelklick auf das Desktop-Icon.

## Ergebnis

Die Anwendung zeigt unter anderem:

- nächster belegter Versuchstermin
- Anzahl der belegten Versuchspaare
- Namen und E-Mail-Adressen
- Betreff
- vollständigen Mailtext

Zusätzlich wird die letzte Vorschau gespeichert unter:

`%LOCALAPPDATA%\FP-Mailer\last_preview.txt`

Das Log liegt unter:

`%LOCALAPPDATA%\FP-Mailer\fp_mailer.log`

## VPN / Uni-Netz

Falls die Betreuerseite von außerhalb des Universitätsnetzes nicht erreichbar ist,
vor dem Start den Heidelberg-VPN (Cisco Secure Client) verbinden und danach das
Desktop-Icon erneut öffnen.

## Zugangsdaten ändern

Im Vorschaufenster auf **Zugangsdaten neu speichern** klicken.

## Warum es aktuell nicht senden kann

Die Dry-Run-Version enthält bewusst keinerlei SMTP-Sendefunktion. Damit kann sie beim
Testen nicht versehentlich Studierende anschreiben. Sobald die Erkennung im Alltag
zuverlässig funktioniert, kann in einer nächsten Version eine explizite Freigabe für
den Versand ergänzt werden.

## Dateien

- `fp_mailer_core.py` – Login, Parser und Auswahl der nächsten Gruppen
- `fp_mailer_gui.py` – Windows-Oberfläche / Dry Run
- `INSTALLIEREN.bat` – bequemer Installer per Doppelklick
- `install.ps1` – richtet venv und Desktop-Verknüpfung ein
- `requirements.txt` – Python-Abhängigkeiten
